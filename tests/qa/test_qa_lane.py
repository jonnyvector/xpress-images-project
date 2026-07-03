"""M7: async QA lane — verdicts at generation time, off the critical path.

The lane judges each stored image on its own executor: generation status
never waits on the judge, one semaphore slot spans an entire judge() call,
judge failures get exactly one automatic re-judge, and the policy composition
receives the live approval state (replica_approved + approved keys).
"""

import threading
from pathlib import Path

from backend.qa.approvals import Approval, ApprovalStore
from backend.qa.judge import JudgeResult
from backend.qa.qa_lane import QaLane
from backend.state import ProjectStore, new_image_id


class RecordingSemaphore:
    """Counts acquisitions so we can prove one slot spans one judge() call."""

    def __init__(self) -> None:
        self.acquisitions = 0
        self._lock = threading.Lock()

    def __enter__(self) -> "RecordingSemaphore":
        with self._lock:
            self.acquisitions += 1
        return self

    def __exit__(self, *args: object) -> None:
        pass


class FakeJudge:
    """Scripted judge: pops one JudgeResult per judge() call."""

    def __init__(self, results: list[JudgeResult], gate: threading.Event | None = None):
        self.results = list(results)
        self.calls = 0
        self.gate = gate  # when set, judge() blocks until released

    def judge(self, candidate) -> JudgeResult:
        self.calls += 1
        if self.gate is not None:
            assert self.gate.wait(timeout=30)
        result = self.results.pop(0)
        result.key = candidate.key
        return result


def _passing(key: str = "k") -> JudgeResult:
    return JudgeResult(
        key=key, panel_layout_match=5, proportions_match=5,
        profile_character_match=5, material_realism=5, swatch_fidelity=5,
        verdict="pass", confidence="high", reason="looks right",
    )


def _error(key: str = "k") -> JudgeResult:
    return JudgeResult(key=key, verdict="error", confidence="low", reason="api down")


def _project_with_variant(tmp_path: Path, *, approved_replica: bool = True):
    """A learned project with sample, replica, and one stored variant."""
    store = ProjectStore(persist_dir=tmp_path / "projects")
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.save_upload(project.id, "door.jpg", b"sample-bytes")
    store.update(
        project.id,
        has_signature=True,
        learned_signature=b"sig",
        base_door_image=b"replica-bytes",
        base_image_id=new_image_id(),
        door_style="shaker",
    )
    record = store.record_result(project.id, "Oak", image_data=b"variant-bytes")
    approvals = ApprovalStore(tmp_path / "approvals.json")
    if approved_replica:
        approvals.set(
            Approval(
                image_id=store.get(project.id).base_image_id,
                project_id=project.id, kind="replica", verdict="approved",
            )
        )
    return store, store.get(project.id), record, approvals


def _lane(
    judge: FakeJudge, approvals: ApprovalStore, **kwargs
) -> tuple[QaLane, RecordingSemaphore]:
    sem = RecordingSemaphore()
    lane = QaLane(
        judge_factory=lambda api_key: judge,
        semaphore=sem,
        approvals=approvals,
        measure_fn=kwargs.pop("measure_fn", lambda **kw: None),
        **kwargs,
    )
    return lane, sem


def test_variant_verdict_persisted_with_status_transitions(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path)
    lane, sem = _lane(FakeJudge([_passing()]), approvals)

    future = lane.enqueue(store, project.id, record.image_id, "key", kind="variant")
    future.result(timeout=30)

    verdict = store.get(project.id).qa_verdicts[record.image_id]
    assert verdict["qa_status"] == "done"
    assert verdict["verdict"] == "pass"
    assert verdict["reason"] == "looks right"
    assert verdict["scores"]["panel_layout_match"] == 5
    assert verdict["judged_at"]
    # One semaphore slot for the whole judge() call.
    assert sem.acquisitions == 1


def test_unapproved_replica_makes_variant_needs_human(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path, approved_replica=False)
    lane, _ = _lane(FakeJudge([_passing()]), approvals)
    lane.enqueue(store, project.id, record.image_id, "key", kind="variant").result(timeout=30)

    verdict = store.get(project.id).qa_verdicts[record.image_id]
    assert verdict["verdict"] == "needs_human"
    assert "replica not approved" in verdict["reason"]


def test_replica_qa_uses_sample_reference_advisory(tmp_path: Path) -> None:
    store, project, _, approvals = _project_with_variant(tmp_path, approved_replica=True)
    measured: list[dict] = []

    def measure_fn(**kw):
        measured.append(kw)
        return None

    lane, _ = _lane(FakeJudge([_passing()]), approvals, measure_fn=measure_fn)
    lane.enqueue(
        store, project.id, project.base_image_id, "key", kind="replica"
    ).result(timeout=30)

    verdict = store.get(project.id).qa_verdicts[project.base_image_id]
    assert verdict["qa_status"] == "done"
    # Replica measures against the SAMPLE photo (advisory), never itself.
    assert measured and measured[0]["reference"] == "sample"
    assert measured[0]["reference_path"].name == "upload.bin"


def test_variant_geometry_references_replica(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path)
    measured: list[dict] = []

    def measure_fn(**kw):
        measured.append(kw)
        return None

    lane, _ = _lane(FakeJudge([_passing()]), approvals, measure_fn=measure_fn)
    lane.enqueue(store, project.id, record.image_id, "key", kind="variant").result(timeout=30)

    assert measured and measured[0]["reference"] == "replica"
    assert measured[0]["reference_path"].name == "base_door.bin"


def test_judge_error_rejudges_exactly_once_then_error(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path)
    judge = FakeJudge([_error(), _error()])
    lane, _ = _lane(judge, approvals)
    lane.enqueue(store, project.id, record.image_id, "key", kind="variant").result(timeout=30)

    assert judge.calls == 2  # original + exactly one automatic re-judge
    verdict = store.get(project.id).qa_verdicts[record.image_id]
    assert verdict["verdict"] == "error"
    assert verdict["gates_as"] == "needs_human"
    assert verdict["qa_status"] == "done"


def test_judge_error_then_success_recovers(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path)
    judge = FakeJudge([_error(), _passing()])
    lane, _ = _lane(judge, approvals)
    lane.enqueue(store, project.id, record.image_id, "key", kind="variant").result(timeout=30)

    assert judge.calls == 2
    assert store.get(project.id).qa_verdicts[record.image_id]["verdict"] == "pass"


def test_slow_judge_never_blocks_generation_status(tmp_path: Path) -> None:
    store, project, record, approvals = _project_with_variant(tmp_path)
    gate = threading.Event()
    lane, _ = _lane(FakeJudge([_passing()], gate=gate), approvals)

    future = lane.enqueue(store, project.id, record.image_id, "key", kind="variant")
    # Generation finishes while the judge hangs.
    store.update(project.id, generation_status="done")
    assert store.get(project.id).generation_status == "done"
    verdict = store.get(project.id).qa_verdicts[record.image_id]
    assert verdict["qa_status"] in ("pending", "judging")  # visibly in flight

    gate.set()
    future.result(timeout=30)
    assert store.get(project.id).qa_verdicts[record.image_id]["qa_status"] == "done"


def test_missing_image_skips_quietly(tmp_path: Path) -> None:
    store, project, _, approvals = _project_with_variant(tmp_path)
    lane, _ = _lane(FakeJudge([_passing()]), approvals)
    future = lane.enqueue(store, project.id, "no-such-image", "key", kind="variant")
    assert future.result(timeout=30) is None
    assert "no-such-image" not in store.get(project.id).qa_verdicts


# --- worker wiring ------------------------------------------------------------


class RecordingLane:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue(self, store, project_id, image_id, api_key, *, kind, swatch_path=None):
        self.enqueued.append({"image_id": image_id, "kind": kind})


class _FakeResult:
    error = None
    image_data = b"img"
    thought_signature = b"sig"


class _FakeGen:
    def __init__(self, **kw): ...
    def generate_variation(self, **kw): return _FakeResult()
    def generate_variation_from_reference(self, **kw): return _FakeResult()
    def learn_door_style(self, **kw): return _FakeResult()


def test_worker_enqueues_qa_for_learn_generation_and_retry(tmp_path, monkeypatch) -> None:
    import backend.worker as worker

    store = ProjectStore(persist_dir=tmp_path / "projects")
    project = store.create(name="Door 1", product_type="Cabinet Door")
    lane = RecordingLane()
    monkeypatch.setattr(worker, "get_qa_lane", lambda: lane)
    monkeypatch.setattr(worker, "DoorGenerator", _FakeGen)
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path / "out")

    # learn -> replica enqueued
    worker._run_learn(store, project.id, "key", b"up", "recessed_panel", "D", "9:16")
    replica_id = store.get(project.id).base_image_id
    assert {"image_id": replica_id, "kind": "replica"} in lane.enqueued

    # generation -> one variant enqueue per stored image, by planned id
    selections = [
        {"wood_name": "Oak", "swatch_path": None, "wood_description": None,
         "reference_image": None, "image_id": "gen-oak"},
    ]
    worker._run_generation(
        store, project.id, "key", b"sig", "recessed_panel", selections, "9:16", ""
    )
    assert {"image_id": "gen-oak", "kind": "variant"} in lane.enqueued

    # retry -> fresh image id enqueued
    worker._run_retry(
        store, project.id, "key", 0, b"sig", "recessed_panel",
        {"wood_name": "Oak", "swatch_path": None, "wood_description": None,
         "reference_image": None},
        "9:16", "",
    )
    retried_id = store.get(project.id).results[0].image_id
    assert retried_id != "gen-oak"
    assert {"image_id": retried_id, "kind": "variant"} in lane.enqueued
