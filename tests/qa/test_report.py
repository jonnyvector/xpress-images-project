from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.judge import JudgeResult
from backend.qa.policy import Decision
from backend.qa.report import render_review_report


def test_report_shows_flagged_hides_passed(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    flagged = candidates["abc123:0:variant:0"]
    passed = candidates["abc123:0:variant:1"]
    items = [
        (
            flagged,
            JudgeResult(key=flagged.key, verdict="fail", reason="stiles 10% wider"),
            Decision(flagged.key, "regenerate", "stiles 10% wider"),
        ),
        (
            passed,
            JudgeResult(key=passed.key, verdict="pass", confidence="high", reason="ok"),
            Decision(passed.key, "pass", "ok"),
        ),
    ]
    thumb_urls = {flagged.key: {"img": "thumbs/a.jpg", "sample": "thumbs/s.jpg"}}
    html_out = render_review_report(items, thumb_urls)
    assert "stiles 10% wider" in html_out
    assert flagged.key in html_out
    assert passed.key not in html_out  # passes summarized, not carded
    assert "1 passed" in html_out
