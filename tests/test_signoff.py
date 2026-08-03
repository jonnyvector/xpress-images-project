import json
from pathlib import Path

import pytest

from backend.signoff import (
    GATE_KEYS,
    SIGNOFF_FILENAME,
    is_stale,
    load_signoff,
    save_signoff,
    set_canonical,
    set_exclusions,
    set_gate,
)


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_signoff(tmp_path) == {}


def test_load_malformed_file_returns_empty(tmp_path: Path) -> None:
    (tmp_path / SIGNOFF_FILENAME).write_text("{not json")
    assert load_signoff(tmp_path) == {}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    record = {"Shaker Cabinet Door": {"canonical_project_id": "abc123"}}
    save_signoff(tmp_path, record)
    assert load_signoff(tmp_path) == record


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    save_signoff(tmp_path, {"A": {}})
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [SIGNOFF_FILENAME]


def test_set_gate_stamps_who_and_when(tmp_path: Path) -> None:
    record = set_gate({}, "Shaker Cabinet Door", "variations", True,
                      by="jonny", at="2026-08-03T14:22:00Z", result_count=43)
    entry = record["Shaker Cabinet Door"]["variations_complete"]
    assert entry == {
        "by": "jonny",
        "at": "2026-08-03T14:22:00Z",
        "result_count": 43,
        "acknowledged_gap": False,
    }


def test_shopify_gate_omits_result_count() -> None:
    record = set_gate({}, "A", "shopify", True, by="jonny", at="2026-08-03T00:00:00Z")
    assert record["A"]["in_shopify"] == {"by": "jonny", "at": "2026-08-03T00:00:00Z"}


def test_clearing_gate_deletes_the_key() -> None:
    record = set_gate({}, "A", "variations", True, by="j", at="t", result_count=1)
    record = set_gate(record, "A", "variations", False, by="j", at="t2")
    assert "variations_complete" not in record["A"]


def test_unknown_gate_raises() -> None:
    with pytest.raises(ValueError):
        set_gate({}, "A", "bogus", True, by="j", at="t")


def test_set_canonical_and_exclusions_preserve_other_fields() -> None:
    record = set_gate({}, "A", "shopify", True, by="j", at="t")
    record = set_canonical(record, "A", "proj1")
    record = set_exclusions(record, "A", ["Black Oak"])
    assert record["A"]["canonical_project_id"] == "proj1"
    assert record["A"]["excluded_colors"] == ["Black Oak"]
    assert record["A"]["in_shopify"]["by"] == "j"


def test_exclusions_are_deduped_and_sorted() -> None:
    record = set_exclusions({}, "A", ["Niagara", "Black Oak", "Niagara"])
    assert record["A"]["excluded_colors"] == ["Black Oak", "Niagara"]


def test_is_stale_true_when_count_moved() -> None:
    entry = {"variations_complete": {"by": "j", "at": "t", "result_count": 43,
                                     "acknowledged_gap": False}}
    assert is_stale(entry, 44) is True
    assert is_stale(entry, 43) is False


def test_is_stale_false_when_never_signed_off() -> None:
    assert is_stale({}, 12) is False


def test_gate_keys_mapping_is_exact() -> None:
    assert GATE_KEYS == {"variations": "variations_complete", "shopify": "in_shopify"}


def test_saved_file_is_readable_json(tmp_path: Path) -> None:
    save_signoff(tmp_path, {"A": {"excluded_colors": []}})
    data = json.loads((tmp_path / SIGNOFF_FILENAME).read_text())
    assert data == {"A": {"excluded_colors": []}}
