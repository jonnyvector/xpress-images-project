"""Manual coverage overrides: operator-declared done, no project match needed."""

import json
from pathlib import Path

from backend.coverage import compute_coverage


def test_override_marks_product_covered(tmp_path: Path) -> None:
    (tmp_path / "thermofoil_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"FS842 Thermofoil Cabinet Door",14112.0,155\n'
        '"DR133 Thermofoil Cabinet Door (Victoria Style)",4286.0,37\n'
    )
    (tmp_path / "coverage_overrides.json").write_text(
        json.dumps({"covered": ["FS842 Thermofoil Cabinet Door"]})
    )
    categories = compute_coverage([], data_dir=tmp_path)
    cat = next(c for c in categories if c["key"] == "thermofoil_cabinet_doors")
    fs842 = next(p for p in cat["products"] if p["title"].startswith("FS842"))
    dr133 = next(p for p in cat["products"] if p["title"].startswith("DR133"))
    assert fs842["covered"] is True
    assert fs842["manual"] is True
    assert dr133["covered"] is False
    assert cat["covered"] == 1


def test_missing_or_bad_overrides_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n"Shaker Cabinet Door",1.0,1\n'
    )
    categories = compute_coverage([], data_dir=tmp_path)  # no overrides file
    assert categories[0]["products"][0]["covered"] is False

    (tmp_path / "coverage_overrides.json").write_text("{not json")
    categories = compute_coverage([], data_dir=tmp_path)  # malformed -> ignored
    assert categories[0]["products"][0]["covered"] is False
