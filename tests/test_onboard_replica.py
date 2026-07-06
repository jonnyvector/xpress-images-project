"""M3: replica onboarding loop — re-learn on weak, stop on ready, best-of on cap."""


from backend.onboarding import (
    CEILING_HIT,
    ONBOARD_ERROR,
    QUEUED_NEEDS_HUMAN,
    QUEUED_READY,
    Spend,
    onboard_replica,
)


class FakeProject:
    def __init__(self, name):
        self.name = name
        self.style_notes = ""
        self.learning_status = "idle"
        self.base_image_id = None
        self.base_door_image = None
        self.learned_signature = None
        self.has_signature = False
        self.qa_verdicts = {}


class FakeStore:
    """In-memory store; the fake learn_fn writes learn+judge results directly."""

    def __init__(self, project):
        self._p = project

    def get(self, _pid):
        return self._p

    def save(self, _pid):
        pass

    def set_active_replica(self, _pid, *, image, signature, base_image_id, verdict):
        self._p.base_door_image = image
        self._p.learned_signature = signature
        self._p.has_signature = bool(signature)
        self._p.base_image_id = base_image_id
        self._p.qa_verdicts = {base_image_id: verdict} if verdict else {}
        return True


def _verdict(min_dim, geometry=None):
    scores = {k: 5 for k in (
        "panel_layout_match", "proportions_match", "profile_character_match",
        "material_realism", "swatch_fidelity")}
    scores["profile_character_match"] = min_dim
    return {"qa_status": "done", "verdict": "needs_human", "gates_as": "needs_human",
            "scores": scores, "geometry": geometry}


def _make_learn_fn(script):
    """Return a fake start_learning that pops the next verdict from `script`
    and writes it into the project as a finished learn+judge."""
    state = {"n": 0}

    def learn_fn(store, project, api_key, upload_bytes, **kw):
        i = state["n"]
        state["n"] += 1
        vid = f"img{i}"
        project.learning_status = "done"
        project.base_image_id = vid
        project.base_door_image = f"bytes{i}".encode()
        project.learned_signature = f"sig{i}".encode()
        project.has_signature = True
        project.qa_verdicts = {vid: script[i]}

    return learn_fn


def _run(script, **kw):
    store = FakeStore(FakeProject("TESTDOOR"))
    return onboard_replica(store, "pid", "key", b"upload",
                           learn_fn=_make_learn_fn(script), timeout=1, **kw), store


def test_stops_immediately_when_first_replica_is_clean():
    res, _ = _run([_verdict(5)])
    assert res.status == QUEUED_READY
    assert res.attempts == 1
    assert res.best_min_score == 5


def test_relearns_until_clean():
    res, store = _run([_verdict(2), _verdict(2), _verdict(4)])
    assert res.status == QUEUED_READY
    assert res.attempts == 3
    assert store.get("pid").base_image_id == "img2"


def test_geometry_drift_forces_relearn_even_if_scores_high():
    res, _ = _run([_verdict(5, geometry="drift"), _verdict(5, geometry="ok")])
    assert res.status == QUEUED_READY
    assert res.attempts == 2


def test_cap_reached_restores_best_attempt_and_flags_human():
    # all weak; attempt 1 is strongest (min 4 but with... use sums)
    script = [_verdict(2), _verdict(4), _verdict(2), _verdict(2), _verdict(2), _verdict(2)]
    res, store = _run(script, attempt_cap=5, min_score=5)
    assert res.status == QUEUED_NEEDS_HUMAN
    assert res.attempts == 6
    # best was attempt index 1 (img1) — restored as active
    assert store.get("pid").base_image_id == "img1"
    assert res.base_image_id == "img1"


def test_spend_ceiling_halts_before_exhausting_cap():
    script = [_verdict(2)] * 6
    spend = Spend(ceiling_usd=0.134 * 2)  # room for 2 learns
    res, _ = _run(script, attempt_cap=5, spend=spend)
    assert res.status in (CEILING_HIT, QUEUED_NEEDS_HUMAN)
    assert spend.spent_usd <= spend.ceiling_usd + 1e-9


def test_learn_failure_escalates():
    def broken_learn(store, project, api_key, upload_bytes, **kw):
        project.learning_status = "error"

    store = FakeStore(FakeProject("D"))
    res = onboard_replica(store, "pid", "key", b"u", learn_fn=broken_learn, timeout=1)
    assert res.status == ONBOARD_ERROR
