"""M1: stable image identity — ResultRecord, migration, archive carriage.

Trust state (approvals, QA verdicts) keys off stable per-image ``image_id``s,
never positional indices. These tests pin the identity layer: records survive
save/load, old tuple-format projects migrate non-destructively, and archives
carry records + verdicts so history survives re-learn.
"""

import json
from pathlib import Path

import backend.worker as worker
from backend.state import ProjectStore, ResultRecord, new_image_id


def _old_format_project(persist_dir: Path) -> Path:
    """Hand-build a pre-migration project dir (manifest has no result_records)."""
    d = persist_dir / "oldproj1"
    d.mkdir(parents=True)
    (d / "signature.bin").write_bytes(b"\x00SIGNATURE-BYTES\xff" * 4)
    (d / "base_door.bin").write_bytes(b"\x89BASEDOOR")
    (d / "result_0.bin").write_bytes(b"IMG0")
    (d / "result_1.bin").write_bytes(b"IMG1")
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "id": "oldproj1",
                "name": "Old Format",
                "product_type": "Cabinet Door",
                "result_names": ["Cherry Natural", "Walnut Select"],
                "errors": [],
                "signature_version": 0,
                "version_count": 0,
            }
        )
    )
    return d


def test_result_record_roundtrip(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")

    rec = store.record_result(project.id, "Oak", image_data=b"img-bytes")
    assert isinstance(rec, ResultRecord)
    assert rec.wood_name == "Oak"
    assert rec.attempt == 0
    assert len(rec.image_id) == 32  # uuid4 hex
    assert rec.created_at  # ISO stamp set by the store

    # A fresh store re-reads the same identity from disk.
    reloaded = ProjectStore(persist_dir=tmp_path).get(project.id)
    assert reloaded is not None
    assert len(reloaded.results) == 1
    got = reloaded.results[0]
    assert got.image_id == rec.image_id
    assert got.wood_name == "Oak"
    assert got.attempt == 0
    assert got.created_at == rec.created_at
    assert got.image_data == b"img-bytes"


def test_old_tuple_format_migrates_with_generated_ids(tmp_path: Path) -> None:
    _old_format_project(tmp_path)
    store = ProjectStore(persist_dir=tmp_path)

    project = store.get("oldproj1")
    assert project is not None
    assert [r.wood_name for r in project.results] == ["Cherry Natural", "Walnut Select"]
    assert all(len(r.image_id) == 32 for r in project.results)
    assert all(r.attempt == 0 for r in project.results)
    assert len({r.image_id for r in project.results}) == 2  # unique
    assert project.results[0].image_data == b"IMG0"

    # Migrated ids are stable across a save + reload cycle.
    ids = [r.image_id for r in project.results]
    store.save("oldproj1")
    again = ProjectStore(persist_dir=tmp_path).get("oldproj1")
    assert again is not None
    assert [r.image_id for r in again.results] == ids


def test_migration_is_nondestructive(tmp_path: Path) -> None:
    d = _old_format_project(tmp_path)
    sig_before = (d / "signature.bin").read_bytes()
    files_before = {p.name for p in d.iterdir()}

    store = ProjectStore(persist_dir=tmp_path)
    store.save("oldproj1")  # triggers manifest upgrade

    assert (d / "signature.bin").read_bytes() == sig_before  # byte-identical
    files_after = {p.name for p in d.iterdir()}
    assert files_before <= files_after  # nothing deleted or renamed
    # Manifest was upgraded in place with records for every result.
    manifest = json.loads((d / "manifest.json").read_text())
    assert len(manifest["result_records"]) == 2
    # result_names stays for older readers (corpus walker, offline eval).
    assert manifest["result_names"] == ["Cherry Natural", "Walnut Select"]


class _FakeLearnResult:
    error = None
    thought_signature = b"sig-bytes"
    image_data = b"replica-bytes"


class _FakeGenerator:
    def __init__(self, **kwargs: object) -> None:
        pass

    def learn_door_style(self, **kwargs: object) -> _FakeLearnResult:
        return _FakeLearnResult()


class _NoopLane:
    def enqueue(self, *args: object, **kwargs: object) -> None:
        pass


def test_replica_gets_image_id_at_learn_store_time(tmp_path, monkeypatch) -> None:
    store = ProjectStore(persist_dir=tmp_path / "projects")
    project = store.create(name="Door 1", product_type="Cabinet Door")
    monkeypatch.setattr(worker, "DoorGenerator", _FakeGenerator)
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(worker, "get_qa_lane", lambda: _NoopLane())  # identity test only

    worker._run_learn(
        store, project.id, "key", b"upload", "recessed_panel", "Door 1", "9:16"
    )

    learned = store.get(project.id)
    assert learned is not None
    assert learned.base_image_id is not None and len(learned.base_image_id) == 32
    first_id = learned.base_image_id

    # Persisted: a fresh store sees the same replica identity.
    reloaded = ProjectStore(persist_dir=tmp_path / "projects").get(project.id)
    assert reloaded is not None
    assert reloaded.base_image_id == first_id

    # Re-learn = new replica image = new identity (old approval must not carry).
    worker._run_learn(
        store, project.id, "key", b"upload", "recessed_panel", "Door 1", "9:16"
    )
    relearned = store.get(project.id)
    assert relearned is not None
    assert relearned.base_image_id != first_id
    assert relearned.qa_verdicts == {}  # verdicts of wiped results don't linger


def test_record_retry_result_returns_fresh_record(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    first = store.record_result(project.id, "Oak", image_data=b"old")
    assert isinstance(first, ResultRecord)

    retried = store.record_retry_result(project.id, 0, "Oak", image_data=b"new")
    assert isinstance(retried, ResultRecord)
    assert retried.image_id != first.image_id  # a new image is a new identity
    refreshed = store.get(project.id)
    assert refreshed is not None
    assert refreshed.results[0].image_id == retried.image_id
    assert refreshed.results[0].image_data == b"new"


def test_archive_carries_records_and_verdicts(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.update(
        project.id, base_door_image=b"replica", base_image_id=new_image_id(),
        learned_signature=b"sig", has_signature=True,
    )
    rec = store.record_result(project.id, "Oak", image_data=b"img")
    assert isinstance(rec, ResultRecord)

    # A verdict lands for the variant (schema formalized in M7; stored verbatim).
    store.set_qa_verdict(project.id, rec.image_id, {"verdict": "pass", "reason": "ok"})

    version = store.archive_current_version(project.id)
    assert version == 1

    vdir = tmp_path / project.id / "versions" / "v1"
    records = json.loads((vdir / "result_records.json").read_text())
    assert records[0]["image_id"] == rec.image_id
    verdicts = json.loads((vdir / "qa_verdicts.json").read_text())
    assert verdicts[rec.image_id]["verdict"] == "pass"


def test_restore_roundtrips_records_and_verdicts(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    base_id = new_image_id()
    store.update(
        project.id, base_door_image=b"replica-v1", base_image_id=base_id,
        learned_signature=b"sig-v1", has_signature=True,
    )
    rec = store.record_result(project.id, "Oak", image_data=b"img-v1")
    assert isinstance(rec, ResultRecord)
    store.set_qa_verdict(project.id, rec.image_id, {"verdict": "pass", "reason": "ok"})

    store.archive_current_version(project.id)
    # Simulate a re-learn wiping current state (worker does this on re-learn).
    store.update(
        project.id, results=[], qa_verdicts={}, base_image_id=None, base_door_image=None
    )

    assert store.restore_version(project.id, 1) is True
    restored = store.get(project.id)
    assert restored is not None
    assert restored.results[0].image_id == rec.image_id  # identity survives round-trip
    assert restored.results[0].image_data == b"img-v1"
    assert restored.qa_verdicts[rec.image_id]["verdict"] == "pass"
    assert restored.base_image_id == base_id
