from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.labels import Label, LabelStore
from backend.qa.sheet import render_index, render_project_sheet


def test_render_project_sheet_contains_cards(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    candidates = [c for c in walk_corpus(projects_dir, swatches_dir) if c.project_id == "abc123"]
    labels = LabelStore(tmp_path / "labels.json")
    labels.set(Label(key="abc123:0:variant:0", verdict="reject", reasons=["artifacts"]))
    thumb_urls = {
        c.key: {"img": f"thumbs/{c.key.replace(':', '_')}.jpg", "sample": "thumbs/s.jpg"}
        for c in candidates
    }
    html_out = render_project_sheet("Shaker Maple", candidates, labels, thumb_urls)
    assert 'data-key="abc123:0:variant:0"' in html_out
    assert 'class="card reject"' in html_out  # explicit label wins over presumed
    assert 'class="card accept"' in html_out  # presumed accept for unlabeled current
    assert "geometry_drift" in html_out  # reason checkboxes present
    assert "Cherry Natural" in html_out


def test_render_index_lists_projects() -> None:
    html_out = render_index([("abc123", "Shaker Maple", 2, 5), ("def456", "Durango", 0, 1)])
    assert "Shaker Maple" in html_out
    assert "2 / 5" in html_out
    assert 'href="project_abc123.html"' in html_out
