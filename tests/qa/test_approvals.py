"""M4: ApprovalStore — the production record of human verdicts.

Keyed by stable image_id (D-006), separate from the frozen calibration
labels (D-011). Read by worker threads (approved_ids feeds policy.decide)
while the API writes — so every access holds the store's internal lock.
"""

import threading
from pathlib import Path

import pytest

from backend.qa.approvals import Approval, ApprovalStore


def _approval(image_id: str = "img-1", **overrides: object) -> Approval:
    base = dict(
        image_id=image_id, project_id="proj-a", kind="replica", verdict="approved"
    )
    base.update(overrides)
    return Approval(**base)  # type: ignore[arg-type]


def test_roundtrip_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "approvals.json"
    store = ApprovalStore(path)
    store.set(_approval("img-1"))
    store.set(
        _approval(
            "img-2", kind="variant", verdict="rejected",
            reasons=["geometry_drift"], note="stiles off",
        )
    )

    reloaded = ApprovalStore(path)
    got = reloaded.get("img-2")
    assert got is not None
    assert got.verdict == "rejected"
    assert got.reasons == ["geometry_drift"]
    assert got.note == "stiles off"
    assert got.project_id == "proj-a"
    assert reloaded.approved_ids() == frozenset({"img-1"})


def test_for_project_filters(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.json")
    store.set(_approval("img-1", project_id="proj-a"))
    store.set(_approval("img-2", project_id="proj-b"))
    assert [a.image_id for a in store.for_project("proj-a")] == ["img-1"]


def test_upsert_replaces(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.json")
    store.set(_approval("img-1", verdict="rejected", reasons=["artifacts"]))
    store.set(_approval("img-1", verdict="approved"))
    got = store.get("img-1")
    assert got is not None
    assert got.verdict == "approved"
    assert got.reasons == []
    assert store.approved_ids() == frozenset({"img-1"})


def test_decided_at_stamped_by_store(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.json")
    store.set(_approval("img-1"))
    got = store.get("img-1")
    assert got is not None
    assert got.decided_at  # ISO 8601 stamp
    assert "T" in got.decided_at


def test_rejects_bad_input(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.json")
    with pytest.raises(ValueError):
        store.set(_approval(verdict="maybe"))
    with pytest.raises(ValueError):
        store.set(_approval(verdict="rejected", reasons=["too_ugly"]))
    with pytest.raises(ValueError):
        store.set(_approval(kind="thumbnail"))


def test_concurrent_readers_and_writers(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.json")
    errors: list[Exception] = []
    stop = threading.Event()

    def writer() -> None:
        try:
            for i in range(200):
                store.set(_approval(f"img-{i}"))
        except Exception as exc:  # noqa: BLE001 — surface any race
            errors.append(exc)
        finally:
            stop.set()

    def reader() -> None:
        try:
            while not stop.is_set():
                ids = store.approved_ids()
                assert all(i.startswith("img-") for i in ids)
                store.for_project("proj-a")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors
    assert len(store.approved_ids()) == 200
    # And the file on disk is valid JSON with all 200 entries.
    assert len(ApprovalStore(tmp_path / "approvals.json").approved_ids()) == 200
