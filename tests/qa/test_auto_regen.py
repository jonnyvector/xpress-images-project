"""M11: auto-regeneration — bounded, cap-checked retries driven by verdicts.

A ``regenerate`` verdict spawns a fresh attempt (new image_id, attempt K+1)
through the QA lane's regen hook; the chain stops on pass, after
``max_auto_retries``, or when the unconsented-spend cap trips (GT-003 on the
run manifest, never in project.errors). The best attempt by judge score sum
ends up active; ties break to the highest attempt number; every attempt's
bytes stay on disk.
"""

import json
import threading
from pathlib import Path

from backend.qa.approvals import Approval, ApprovalStore
from backend.qa.judge import JudgeResult
from backend.qa.qa_lane import QaLane, RegenContext
from backend.runs import RunManifest
from backend.state import ProjectStore, new_image_id


class NullSemaphore:
    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass


class FakeJudge:
    def __init__(self, results: list[JudgeResult]):
        self.results = list(results)
        self.calls = 0

    def judge(self, candidate) -> JudgeResult:
        self.calls += 1
        result = self.results.pop(0)
        result.key = candidate.key
        return result


class FakeGen:
    """Scripted attempt generator: returns fresh image bytes per call."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self):
        self.calls += 1
        data = f"attempt-{self.calls}".encode()

        class R:
            error = None
            image_data = data

        return R()


def _judge_result(verdict: str, score: int) -> JudgeResult:
    return JudgeResult(
        key="k", panel_layout_match=score, proportions_match=score,
        profile_character_match=score, material_realism=score, swatch_fidelity=score,
        verdict=verdict, confidence="high", reason=f"{verdict}@{score}",
    )


def _rig(tmp_path: Path, judge_results: list[JudgeResult], *, cap_usd: float = 10.0):
    store = ProjectStore(persist_dir=tmp_path / "projects")
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.save_upload(project.id, "door.jpg", b"sample")
    store.update(
        project.id, has_signature=True, learned_signature=b"sig",
        base_door_image=b"replica", base_image_id=new_image_id(),
        door_style="shaker",
    )
    approvals = ApprovalStore(tmp_path / "approvals.json")
    approvals.set(Approval(
        image_id=store.get(project.id).base_image_id,
        project_id=project.id, kind="replica", verdict="approved",
    ))
    initial_id = new_image_id()
    record = store.record_result(
        project.id, "Oak", image_data=b"attempt-0", image_id=initial_id
    )
    run = RunManifest.create(
        store.project_dir(project.id),
        planned=[("Oak", initial_id)],
        config={"max_auto_retries": 2, "run_cost_cap_usd": cap_usd,
                "image_cost_usd": 0.134},
    )
    run.submit()  # the consented initial image
    judge = FakeJudge(judge_results)
    gen = FakeGen()
    lane = QaLane(
        judge_factory=lambda api_key: judge,
        semaphore=NullSemaphore(),
        approvals=approvals,
        measure_fn=lambda **kw: None,
    )
    ctx = RegenContext(run=run, generate=gen, wood_name="Oak",
                       attempt_ids=[initial_id])
    return store, project, record, run, judge, gen, lane, ctx


def _drain(lane: QaLane) -> None:
    """Wait for the lane's executor to go idle (chains enqueue follow-ups)."""
    for _ in range(200):
        if not lane._executor._work_queue.qsize() and lane.idle():
            return
        threading.Event().wait(0.05)


def test_regenerate_spawns_attempt_and_stops_on_pass(tmp_path: Path) -> None:
    store, project, record, run, judge, gen, lane, ctx = _rig(
        tmp_path, [_judge_result("fail", 3), _judge_result("pass", 5)]
    )
    lane.enqueue(store, project.id, record.image_id, "key",
                 kind="variant", regen=ctx).result(timeout=30)
    _drain(lane)

    assert gen.calls == 1  # one retry, then pass stopped the chain
    assert judge.calls == 2
    active = store.get(project.id).results[0]
    assert active.attempt == 1
    assert active.image_id != record.image_id  # fresh identity
    assert active.image_data == b"attempt-1"
    # Chain accounting on the manifest.
    _, unconsented = run.counters()
    assert unconsented == 1


def test_max_retries_then_best_attempt_wins(tmp_path: Path) -> None:
    # All three attempts flagged regenerate; middle attempt scores highest.
    store, project, record, run, judge, gen, lane, ctx = _rig(
        tmp_path,
        [_judge_result("fail", 2), _judge_result("fail", 4), _judge_result("fail", 3)],
    )
    lane.enqueue(store, project.id, record.image_id, "key",
                 kind="variant", regen=ctx).result(timeout=30)
    _drain(lane)

    assert gen.calls == 2  # max_auto_retries
    active = store.get(project.id).results[0]
    assert active.attempt == 1  # score 4x5=20 beats 2s and 3s
    assert active.image_data == b"attempt-1"
    # Every attempt's bytes retained on disk.
    d = store.project_dir(project.id)
    attempt_files = sorted(f.name for f in d.glob("result_0_attempt_*.bin"))
    assert len(attempt_files) == 2  # the two non-active attempts


def test_tie_breaks_to_highest_attempt(tmp_path: Path) -> None:
    store, project, record, run, judge, gen, lane, ctx = _rig(
        tmp_path,
        [_judge_result("fail", 3), _judge_result("fail", 3), _judge_result("fail", 3)],
    )
    lane.enqueue(store, project.id, record.image_id, "key",
                 kind="variant", regen=ctx).result(timeout=30)
    _drain(lane)
    active = store.get(project.id).results[0]
    assert active.attempt == 2  # deterministic: equal scores -> latest attempt


def test_needs_human_never_retries(tmp_path: Path) -> None:
    store, project, record, run, judge, gen, lane, ctx = _rig(
        tmp_path, [_judge_result("pass", 5)]
    )
    # Unapproved replica route: variant gates needs_human transitively.
    approvals = ApprovalStore(tmp_path / "approvals2.json")  # empty store
    lane2 = QaLane(
        judge_factory=lambda api_key: judge,
        semaphore=NullSemaphore(),
        approvals=approvals,
        measure_fn=lambda **kw: None,
    )
    lane2.enqueue(store, project.id, record.image_id, "key",
                  kind="variant", regen=ctx).result(timeout=30)
    _drain(lane2)
    assert gen.calls == 0
    verdict = store.get(project.id).qa_verdicts[record.image_id]
    assert verdict["verdict"] == "needs_human"


def test_cap_breach_records_gt003_on_manifest_not_errors(tmp_path: Path) -> None:
    # cap = one unconsented image: the second retry must be refused.
    store, project, record, run, judge, gen, lane, ctx = _rig(
        tmp_path,
        [_judge_result("fail", 2), _judge_result("fail", 4)],
        cap_usd=0.134,
    )
    lane.enqueue(store, project.id, record.image_id, "key",
                 kind="variant", regen=ctx).result(timeout=30)
    _drain(lane)

    assert gen.calls == 1  # second retry blocked by cap
    data = json.loads(run.path.read_text())
    assert any(e.get("code") == "GT-003" for e in data.get("events", []))
    _, unconsented = run.counters()
    assert unconsented == 1  # breach increment rolled back
    assert all("GT-003" not in err for _, err in store.get(project.id).errors)
    # Best of the two judged attempts is active (attempt 1, score 4).
    assert store.get(project.id).results[0].attempt == 1


def test_concurrent_chains_do_not_misbind(tmp_path: Path) -> None:
    """Two wood slots retrying simultaneously keep their identities separate."""
    store = ProjectStore(persist_dir=tmp_path / "projects")
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.save_upload(project.id, "door.jpg", b"sample")
    store.update(
        project.id, has_signature=True, learned_signature=b"sig",
        base_door_image=b"replica", base_image_id=new_image_id(),
        door_style="shaker",
    )
    approvals = ApprovalStore(tmp_path / "approvals.json")
    approvals.set(Approval(
        image_id=store.get(project.id).base_image_id,
        project_id=project.id, kind="replica", verdict="approved",
    ))

    class KeyedJudge:
        """fail the initial images, pass regenerated attempts — by content."""

        def judge(self, candidate) -> JudgeResult:
            initial = candidate.image_path.read_bytes().startswith(b"init-")
            r = _judge_result("fail" if initial else "pass", 3 if initial else 5)
            r.key = candidate.key
            return r

    judge = KeyedJudge()
    lane = QaLane(
        judge_factory=lambda api_key: judge,
        semaphore=NullSemaphore(),
        approvals=approvals,
        measure_fn=lambda **kw: None,
    )
    ids, ctxs = [], []
    run = RunManifest.create(
        store.project_dir(project.id), planned=[],
        config={"max_auto_retries": 2, "run_cost_cap_usd": 10.0,
                "image_cost_usd": 0.134},
    )
    for wood in ("Oak", "Cherry"):
        iid = new_image_id()
        store.record_result(project.id, wood, image_data=f"init-{wood}".encode(),
                            image_id=iid)
        ids.append(iid)
        ctxs.append(RegenContext(run=run, generate=FakeGen(), wood_name=wood,
                                 attempt_ids=[iid]))

    futures = [
        lane.enqueue(store, project.id, iid, "key", kind="variant", regen=ctx)
        for iid, ctx in zip(ids, ctxs, strict=True)
    ]
    for f in futures:
        f.result(timeout=30)
    _drain(lane)

    final = store.get(project.id)
    by_wood = {r.wood_name: r for r in final.results}
    assert by_wood["Oak"].attempt == 1 and by_wood["Cherry"].attempt == 1
    assert by_wood["Oak"].image_id != by_wood["Cherry"].image_id
    # Each chain's passing attempt is active with its own verdict.
    for r in final.results:
        assert final.qa_verdicts[r.image_id]["verdict"] == "pass"
