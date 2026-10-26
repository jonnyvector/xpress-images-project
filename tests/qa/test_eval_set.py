"""Judge-comparison answer key and the OpenRouter judge."""

import json
from pathlib import Path

import httpx
from PIL import Image

from backend.qa.corpus import Candidate
from backend.qa.eval_set import build_eval_set, bulk_approval_ids
from backend.qa.openrouter_judge import OpenRouterJudge


def _approval(image_id, verdict, at, project="p1", reasons=()):
    return {
        "image_id": image_id,
        "project_id": project,
        "verdict": verdict,
        "decided_at": f"2026-07-01T10:{at}+00:00",
        "reasons": list(reasons),
    }


def test_approve_all_bursts_are_detected():
    burst = [_approval(f"b{i}", "approved", f"00:{i:02d}") for i in range(5)]
    single = [_approval("s1", "approved", "30:00")]
    assert bulk_approval_ids(burst + single) == {f"b{i}" for i in range(5)}


def test_rejections_in_a_burst_still_count(tmp_path: Path):
    img = tmp_path / "x.bin"
    img.write_bytes(b"x")
    cands = {
        f"p1:0:variant:{i}": Candidate(
            f"p1:0:variant:{i}",
            "p1",
            "Door",
            None,
            0,
            "variant",
            i,
            "Oak",
            img,
            None,
            None,
            "accept",
        )
        for i in range(7)
    }
    approvals = [_approval(f"b{i}", "approved", f"00:{i:02d}") for i in range(5)]
    approvals.append(_approval("r1", "rejected", "00:06", reasons=["profile_character"]))
    approvals.append(_approval("s1", "approved", "40:00"))
    id_to_key = {"r1": "p1:0:variant:5", "s1": "p1:0:variant:6"}
    id_to_key |= {f"b{i}": f"p1:0:variant:{i}" for i in range(5)}
    labels = [{"key": "p1:0:variant:0", "verdict": "reject", "reasons": []}]

    items = {i.key: i for i in build_eval_set(cands, labels, approvals, id_to_key)}
    assert items["p1:0:variant:0"].source == "label"  # label beats the bulk approval
    assert items["p1:0:variant:5"].truth == "reject"
    assert items["p1:0:variant:6"].truth == "accept"  # clicked on its own
    assert set(items) == {"p1:0:variant:0", "p1:0:variant:5", "p1:0:variant:6"}


def test_openrouter_judge_parses_and_counts_cost(tmp_path: Path):
    img = tmp_path / "g.png"
    Image.new("RGB", (40, 60), "tan").save(img)
    cand = Candidate(
        "p:0:variant:0", "p", "Door", None, 0, "variant", 0, "Oak", img, img, None, "accept"
    )
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["model"] = body["model"]
        seen["images"] = sum(
            1 for part in body["messages"][0]["content"] if part["type"] == "image_url"
        )
        verdict = {
            "panel_layout_match": 5,
            "proportions_match": 5,
            "profile_character_match": 4,
            "material_realism": 5,
            "swatch_fidelity": 5,
            "artifacts": [],
            "verdict": "pass",
            "confidence": "high",
            "reason": "same door",
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(verdict)}}],
                "usage": {"cost": 0.02},
            },
        )

    judge = OpenRouterJudge(
        "k",
        "anthropic/claude-opus-5.5",
        cache_dir=tmp_path / "cache",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = judge.judge(cand)
    assert result.verdict == "pass" and result.profile_character_match == 4
    assert seen == {"model": "anthropic/claude-opus-5.5", "images": 2}  # sample + generated
    assert judge.cost_usd == 0.02
    assert judge.judge(cand).verdict == "pass"  # cached: no second charge
    assert judge.cost_usd == 0.02


def test_corner_closeups_follow_the_prompt(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("backend.qa.openrouter_judge.time.sleep", lambda s: None)
    img = tmp_path / "g.png"
    Image.new("RGB", (40, 60), "tan").save(img)
    cand = Candidate(
        "p:0:variant:0", "p", "Door", None, 0, "variant", 0, "Oak", img, img, None, "accept"
    )
    kinds = []

    def handler(request: httpx.Request) -> httpx.Response:
        kinds.extend(part["type"] for part in json.loads(request.content)["messages"][0]["content"])
        return httpx.Response(500)

    judge = OpenRouterJudge(
        "k",
        "m",
        cache_dir=tmp_path / "cache",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        ignore_shape=True,
        corners=True,
    )
    judge._judge_once(cand)
    # sample + generated, the rubric, then the two corner close-ups
    assert kinds[:5] == ["image_url", "image_url", "text", "image_url", "image_url"]
    assert judge.prompt_variant == "ignore_shape+corners"


def test_bad_key_is_not_retried(tmp_path: Path, monkeypatch):
    """401/402 won't fix themselves; retrying only burns time (and credit)."""
    monkeypatch.setattr("backend.qa.openrouter_judge.time.sleep", lambda s: None)
    img = tmp_path / "g.png"
    Image.new("RGB", (40, 60), "tan").save(img)
    cand = Candidate(
        "p:0:variant:0", "p", "Door", None, 0, "variant", 0, "Oak", img, img, None, "accept"
    )
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "bad key"})

    judge = OpenRouterJudge(
        "k",
        "m",
        cache_dir=tmp_path / "c",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = judge._judge_once(cand)
    assert result.verdict == "error" and "401" in result.reason
    assert len(calls) == 1
