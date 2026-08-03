"""coverage_overrides.json is retired: sign-off is now the only source of truth.

Task 5 migrates the five titles that used to rely on this file into the
sign-off record; until then those titles are expected to read as not covered.
This file now asserts that a leftover coverage_overrides.json is inert.
"""

import json
from pathlib import Path

from backend.coverage import compute_coverage


def test_leftover_overrides_file_no_longer_marks_product_covered(tmp_path: Path) -> None:
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
    assert "manual" not in fs842
    assert fs842["covered"] is False
    assert dr133["covered"] is False
    assert cat["covered"] == 0


def test_missing_or_bad_overrides_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n"Shaker Cabinet Door",1.0,1\n'
    )
    categories = compute_coverage([], data_dir=tmp_path)  # no overrides file
    assert categories[0]["products"][0]["covered"] is False

    (tmp_path / "coverage_overrides.json").write_text("{not json")
    categories = compute_coverage([], data_dir=tmp_path)  # malformed -> ignored
    assert categories[0]["products"][0]["covered"] is False
