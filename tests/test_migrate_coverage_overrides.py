import json
from pathlib import Path

from backend.signoff import load_signoff
from scripts.migrate_coverage_overrides import migrate


def test_migrates_both_gates(tmp_path: Path):
    (tmp_path / "coverage_overrides.json").write_text(
        json.dumps({"covered": ["FS842 Thermofoil Cabinet Door"]})
    )
    n = migrate(tmp_path, now="2026-08-03T00:00:00Z")
    assert n == 1
    record = load_signoff(tmp_path)
    entry = record["FS842 Thermofoil Cabinet Door"]
    assert entry["variations_complete"]["by"] == "migrated"
    assert entry["in_shopify"]["by"] == "migrated"
    assert entry["variations_complete"]["acknowledged_gap"] is True


def test_missing_overrides_file_is_a_noop(tmp_path: Path):
    assert migrate(tmp_path, now="2026-08-03T00:00:00Z") == 0
    assert load_signoff(tmp_path) == {}


def test_does_not_clobber_existing_signoff(tmp_path: Path):
    (tmp_path / "coverage_overrides.json").write_text(json.dumps({"covered": ["A"]}))
    (tmp_path / "coverage_signoff.json").write_text(
        json.dumps({"B": {"canonical_project_id": "keep"}})
    )
    migrate(tmp_path, now="2026-08-03T00:00:00Z")
    record = load_signoff(tmp_path)
    assert record["B"]["canonical_project_id"] == "keep"
    assert "A" in record
