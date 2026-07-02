from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.eval import evaluate, is_holdout
from backend.qa.labels import Label
from backend.qa.policy import Decision


def _candidate(key: str, style: str = "shaker") -> Candidate:
    pid = key.split(":")[0]
    return Candidate(
        key=key,
        project_id=pid,
        project_name=pid,
        door_style=style,
        version=0,
        kind="variant",
        index=0,
        wood_name="Cherry Natural",
        image_path=Path("x.bin"),
        sample_path=None,
        swatch_path=None,
        presumed="accept",
    )


def test_is_holdout_deterministic_and_partial() -> None:
    ids = [f"proj{i}" for i in range(200)]
    first = [is_holdout(i) for i in ids]
    assert first == [is_holdout(i) for i in ids]  # stable
    frac = sum(first) / len(first)
    assert 0.05 < frac < 0.4  # roughly a fifth


def test_evaluate_recall_and_false_flags() -> None:
    labels = [
        Label(key="a:0:variant:0", verdict="reject", reasons=["geometry_drift"]),
        Label(key="a:0:variant:1", verdict="reject", reasons=["artifacts"]),
        Label(key="a:0:variant:2", verdict="accept"),
        Label(key="a:0:variant:3", verdict="accept"),
    ]
    decisions = {
        "a:0:variant:0": Decision(
            "a:0:variant:0", "regenerate", "bad geometry"
        ),  # caught
        "a:0:variant:1": Decision("a:0:variant:1", "pass", "looks fine"),  # MISSED reject
        "a:0:variant:2": Decision("a:0:variant:2", "pass", "ok"),  # correct pass
        "a:0:variant:3": Decision(
            "a:0:variant:3", "needs_human", "low conf"
        ),  # false flag
    }
    candidates = {label.key: _candidate(label.key) for label in labels}
    m = evaluate(labels, decisions, candidates)
    assert m.n == 4 and m.n_rejects == 2 and m.n_accepts == 2
    assert m.reject_recall == 0.5
    assert m.false_flag_rate == 0.5
    assert m.recall_by_reason["geometry_drift"] == (1, 1)
    assert m.recall_by_reason["artifacts"] == (0, 1)
    assert "shaker" in m.by_style
