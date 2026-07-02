import json
from pathlib import Path

import pytest

from backend.qa.corpus import walk_corpus
from backend.qa.labels import Label, LabelStore
from backend.qa.sheet import parse_label_post, render_index, render_project_sheet


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


def test_parse_label_post_valid_body() -> None:
    raw = b'{"key":"abc123:0:variant:0","verdict":"reject","reasons":["artifacts"]}'
    assert parse_label_post(raw) == Label(
        key="abc123:0:variant:0", verdict="reject", reasons=["artifacts"]
    )


def test_parse_label_post_defaults_reasons() -> None:
    label = parse_label_post(b'{"key":"k","verdict":"accept"}')
    assert label.reasons == []


def test_parse_label_post_malformed_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_label_post(b"not json")


def test_parse_label_post_missing_field() -> None:
    with pytest.raises(KeyError):
        parse_label_post(b'{"verdict":"accept"}')


def test_bad_verdict_rejected_by_store(tmp_path: Path) -> None:
    labels = LabelStore(tmp_path / "labels.json")
    with pytest.raises(ValueError):
        labels.set(parse_label_post(b'{"key":"k","verdict":"maybe"}'))
