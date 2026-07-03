"""M3: shared selection resolver — one resolver for router, worker, estimate.

``build_selections`` moves out of the worker so the generation gate (GT-002)
and the cost estimate count the SAME resolved selections the worker will
actually generate — including its silent drop of unresolvable swatches.
"""

from pathlib import Path

import backend.selections as selections_mod
from backend.selections import build_selections

WOOD_TYPES = {
    "cherry-natural": {"name": "Cherry Natural", "description": "warm cherry"},
    "vinyl-oak": {
        "name": "Vinyl Oak",
        "description": "framed description",
        "flat_panel_description": "flat description",
        "swatch_key": "cherry-natural",
    },
    "desc-only": {"name": "Desc Only", "description": "no swatch file"},
    "flat-plank": {
        "name": "Flat Plank",
        "description": "framed description",
        "flat_panel_description": "flat description",
    },
}


def _fixture_swatches(tmp_path: Path) -> dict[str, Path]:
    p = tmp_path / "cherry_natural.jpg"
    p.write_bytes(b"\xff\xd8jpeg")
    return {"cherry-natural": p}


def _patch(monkeypatch, tmp_path: Path) -> None:
    files = _fixture_swatches(tmp_path)
    monkeypatch.setattr(selections_mod, "load_material_types", lambda mt: WOOD_TYPES)
    monkeypatch.setattr(selections_mod, "get_swatch_files", lambda mt: files)
    monkeypatch.setattr(
        selections_mod, "resolve_swatch_path", lambda key, f: f.get(key)
    )


def test_virtual_swatch_borrows_and_describes(tmp_path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path)
    out = build_selections(["virtual:vinyl-oak"])
    assert len(out) == 1
    assert out[0]["wood_name"] == "Vinyl Oak"
    assert out[0]["swatch_path"] is not None  # borrowed from swatch_key


def test_unresolvable_swatch_silently_dropped(tmp_path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path)
    out = build_selections(["/nonexistent/mystery_wood.jpg"])
    assert out == []  # dropped, not raised — gate must count the same way


def test_description_only_entry_kept_without_swatch(tmp_path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path)
    out = build_selections(["desc-only"])
    assert len(out) == 1
    assert out[0]["swatch_path"] is None
    assert out[0]["wood_description"] == "no swatch file"


def test_flat_panel_style_uses_flat_description(tmp_path, monkeypatch) -> None:
    _patch(monkeypatch, tmp_path)
    out = build_selections(["flat-plank"], door_style="solid_plank")
    assert out[0]["wood_description"] == "flat description"
    # Non-flat-panel style keeps the framed description.
    framed = build_selections(["flat-plank"], door_style="shaker")
    assert framed[0]["wood_description"] == "framed description"


def test_worker_uses_shared_resolver() -> None:
    import backend.worker as worker

    assert worker.build_selections is build_selections  # single source of truth
    assert not hasattr(worker, "_build_selections")  # private copy deleted
