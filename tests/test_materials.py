from pathlib import Path

from backend import materials


def test_normalize_material_key() -> None:
    assert materials.normalize_material_key("White_Oak") == "white-oak"


def test_swatch_name_from_path() -> None:
    assert materials.swatch_name_from_path(Path("white_oak_select.jpg")) == "White Oak Select"


def test_resolve_swatch_path(tmp_path: Path) -> None:
    swatch = tmp_path / "White_Oak.jpg"
    swatch.write_bytes(b"x")
    resolved = materials.resolve_swatch_path("white-oak", [swatch])
    assert resolved == swatch
