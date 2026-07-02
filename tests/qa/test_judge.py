import json
from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.judge import VisionJudge


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    def generate_content(self, *, model: str, contents: object, config: object = None):
        self.calls += 1
        return FakeResponse(self.texts.pop(0))


class FakeClient:
    def __init__(self, texts: list[str]) -> None:
        self.models = FakeModels(texts)


GOOD = json.dumps(
    {
        "panel_layout_match": 5, "proportions_match": 5, "profile_character_match": 4,
        "material_realism": 5, "swatch_fidelity": 5, "artifacts": [],
        "verdict": "pass", "confidence": "high", "reason": "matches sample",
    }
)
LOW_FAIL = GOOD.replace('"high"', '"low"').replace('"pass"', '"fail"')


def _candidate(projects_dir: Path, swatches_dir: Path):
    return next(
        c for c in walk_corpus(projects_dir, swatches_dir) if c.key == "abc123:0:variant:0"
    )


def test_judge_parses_and_caches(projects_dir: Path, swatches_dir: Path, tmp_path: Path) -> None:
    client = FakeClient([GOOD])
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    c = _candidate(projects_dir, swatches_dir)

    result = judge.judge(c)
    assert result.verdict == "pass" and result.confidence == "high"
    assert result.panel_layout_match == 5

    again = judge.judge(c)  # would raise IndexError if it hit the fake again
    assert again.verdict == "pass"
    assert client.models.calls == 1


def test_low_confidence_triggers_majority_vote(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    client = FakeClient([LOW_FAIL, LOW_FAIL, GOOD])  # 2 fail votes of 3 -> fail
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    result = judge.judge(_candidate(projects_dir, swatches_dir))
    assert client.models.calls == 3
    assert result.verdict == "fail"
    assert result.votes == 3


def test_unparseable_response_yields_error_verdict(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    client = FakeClient(["not json at all"] * 3)
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    result = judge.judge(_candidate(projects_dir, swatches_dir))
    assert result.verdict == "error"
    assert result.confidence == "low"


def test_valid_json_wrong_shape_reports_unparseable_not_api_error(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    client = FakeClient(["[1, 2, 3]"] * 3)  # valid JSON, wrong shape (top-level array)
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    result = judge.judge(_candidate(projects_dir, swatches_dir))
    assert result.verdict == "error"
    assert "unparseable" in result.reason
    assert "api error" not in result.reason
