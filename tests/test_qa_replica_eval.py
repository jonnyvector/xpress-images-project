import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "qa_replica_eval", Path(__file__).resolve().parents[1] / "scripts" / "qa_replica_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

SINCE = "2026-07-06T10:00"


def test_session_replica_decisions_filters_kind_and_date():
    rows = [
        {"kind": "replica", "verdict": "rejected", "decided_at": "2026-07-06T10:22",
         "project_id": "a", "image_id": "i1"},
        {"kind": "variant", "verdict": "rejected", "decided_at": "2026-07-06T10:22",
         "project_id": "b", "image_id": "i2"},
        {"kind": "replica", "verdict": "approved", "decided_at": "2026-07-03T09:00",
         "project_id": "c", "image_id": "i3"},
        {"kind": "replica", "verdict": "approved", "decided_at": "2026-07-07T02:26",
         "project_id": "d", "image_id": "i4"},
    ]
    got = ev.session_replica_decisions(rows, SINCE)
    assert [r["project_id"] for r in got] == ["a", "d"]


def test_resolve_replica_image_active_then_versions(tmp_path: Path):
    d = tmp_path / "proj"
    (d / "versions" / "v1").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"base_image_id": "cur"}))
    (d / "base_door.bin").write_bytes(b"current")
    (d / "versions" / "v1" / "meta.json").write_text(json.dumps({"base_image_id": "old"}))
    (d / "versions" / "v1" / "base_door.bin").write_bytes(b"old")

    assert ev.resolve_replica_image(d, "cur") == d / "base_door.bin"
    assert ev.resolve_replica_image(d, "old") == d / "versions" / "v1" / "base_door.bin"
    assert ev.resolve_replica_image(d, "gone") is None


def test_rates():
    rows = [
        {"operator": "rejected", "disqualified": True},
        {"operator": "rejected", "disqualified": False},
        {"operator": "approved", "disqualified": False},
        {"operator": "approved", "disqualified": True},
        {"operator": "approved", "disqualified": False},
    ]
    r = ev.rates(rows)
    assert r["catch_rate"] == 0.5          # 1 of 2 rejects caught
    assert r["false_fail_rate"] == 1 / 3   # 1 of 3 approves failed
    assert r["accepted"] is False          # gate: >=0.80 and <=0.20
