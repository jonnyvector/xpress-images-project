"""M9: reliability ledger — pipeline-vs-operator agreement, honestly measured.

Agreement counts only DECISIVE pipeline verdicts (pass / regenerate): a
pipeline that defers (needs_human / error) demonstrates no discriminative
skill and must not inflate the number that justifies bulk unlock (D-008).
"""

import json
from pathlib import Path

from backend.qa.reliability import aggregate, append_record


def _rec(path: Path, pipeline: str | None, human: str, *, kind: str = "variant",
         style: str = "frame_standard", image_id: str = "i") -> None:
    append_record(
        path,
        image_id=image_id,
        project_id="p1",
        kind=kind,
        style_class=style,
        pipeline_verdict=pipeline,
        human_verdict=human,
        reasons=[],
    )


def test_append_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "reliability.jsonl"
    _rec(path, "pass", "approved", image_id="a")
    _rec(path, "regenerate", "rejected", image_id="b")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["image_id"] == "a"
    assert lines[0]["pipeline_verdict"] == "pass"
    assert lines[0]["at"]  # timestamped


def test_agreement_decisive_only(tmp_path: Path) -> None:
    path = tmp_path / "reliability.jsonl"
    _rec(path, "pass", "approved")        # agree
    _rec(path, "regenerate", "rejected")  # agree
    _rec(path, "pass", "rejected")        # DISAGREE
    _rec(path, "needs_human", "rejected") # deferral — NOT agreement
    _rec(path, "error", "approved")       # deferral — NOT agreement
    _rec(path, None, "approved")          # QA incomplete — excluded entirely

    agg = aggregate(path)
    total = agg["total"]
    assert total["decisive_n"] == 3
    assert total["agreement_rate"] == 2 / 3
    assert total["deferral_n"] == 2
    assert total["deferral_rate"] == 2 / 5  # deferrals over verdict-bearing records
    assert total["null_n"] == 1
    assert total["disagreements"] == 1


def test_splits_by_kind_and_style(tmp_path: Path) -> None:
    path = tmp_path / "reliability.jsonl"
    _rec(path, "pass", "approved", kind="replica", style="frame_standard")
    _rec(path, "pass", "rejected", kind="variant", style="frame_narrow")

    agg = aggregate(path)
    assert agg["by_kind"]["replica"]["agreement_rate"] == 1.0
    assert agg["by_kind"]["variant"]["agreement_rate"] == 0.0
    assert agg["by_style_class"]["frame_narrow"]["disagreements"] == 1


def test_aggregate_missing_file_is_empty(tmp_path: Path) -> None:
    agg = aggregate(tmp_path / "missing.jsonl")
    assert agg["total"]["decisive_n"] == 0
    assert agg["total"]["agreement_rate"] is None  # no data is not 100%
