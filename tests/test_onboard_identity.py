"""onboard_replica with identity gate: stubbed learn/extract/identity, real store."""
from backend.onboarding import (
    QUEUED_NEEDS_HUMAN,
    QUEUED_READY,
    defect_note,
    onboard_replica,
)
from backend.qa.judge import IdentityResult
from backend.state import ProjectStore

GOOD_SCORES = {k: 4 for k in (
    "panel_layout_match", "proportions_match", "profile_character_match",
    "material_realism", "swatch_fidelity")}


def _verdict():
    return {"qa_status": "done", "scores": dict(GOOD_SCORES), "geometry": None}


def make_learn_fn(counter):
    """Synchronous stub: each call installs a new 'replica' and a done verdict."""
    def learn_fn(store, project, api_key, upload_bytes, **kw):
        counter["n"] += 1
        bid = f"img{counter['n']}"
        store.update(project.id, learning_status="done", base_image_id=bid,
                     base_door_image=f"replica{counter['n']}".encode(),
                     qa_verdicts={bid: _verdict()})
    return learn_fn


def _store(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Talbot", product_type="Cabinet Door", material_type="wood")
    return store, p.id


def test_defect_note_lists_defects_and_caps_at_five():
    note = defect_note(["a", "b", "c", "d", "e", "f"])
    # substring checks on bare "a".."f" are unsafe here: the fixed prose contains
    # "differed", which itself contains "f" — assert on the numbered item instead.
    assert "(1) a" in note and "(5) e" in note and "(6) f" not in note
    assert defect_note([]) == ""


def test_clean_identity_queues_ready_and_stores_facts(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    facts = ["panel: louver, tight pitch"]
    calls = []

    def identity_fn(src, rep, f):
        calls.append(f)
        return IdentityResult(key="k", disqualified=False, defects=[])

    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None,
        learn_fn=make_learn_fn(counter),
        extract_fn=lambda src: facts, identity_fn=identity_fn,
    )
    assert res.status == QUEUED_READY and res.attempts == 1
    assert store.get(pid).profile_spec == facts   # extracted once, persisted
    assert calls == [facts]                       # judge saw the facts


def test_defects_feed_next_attempt_conditioning(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_notes = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_notes.append(kw.get("style_notes", ""))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["slats too widely spaced"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: ["panel: louver"], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_READY and res.attempts == 2
    assert "slats too widely spaced" in seen_notes[1]   # defect-guided re-learn
    assert "panel: louver" in seen_notes[0]             # facts guide attempt 1


def test_cap_hit_finalizes_fewest_defects(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["d1", "d2"]),
        IdentityResult(key="k", disqualified=True, defects=["d1"]),        # best
        IdentityResult(key="k", disqualified=True, defects=["d1", "d2", "d3"]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=2, spend=None,
        learn_fn=make_learn_fn(counter),
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_NEEDS_HUMAN and res.attempts == 3
    assert res.defects == ["d1"]
    assert store.get(pid).base_image_id == "img2"       # best attempt restored


def test_extraction_failure_falls_back_to_old_gate(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}

    def broken_extract(src):
        raise RuntimeError("boom")

    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=1, spend=None,
        learn_fn=make_learn_fn(counter), extract_fn=broken_extract,
        identity_fn=lambda *a: IdentityResult(key="k", verdict="error", reason="api"),
    )
    # identity errored -> old min-score gate; GOOD_SCORES pass min 3
    assert res.status == QUEUED_READY
    assert store.get(pid).profile_spec is None


def test_profile_anchor_attaches_only_after_first_disqualification(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_profiles = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_profiles.append(kw.get("profile_bytes"))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["raise too gradual"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
        profile_bytes=b"xsec",
    )
    assert res.status == QUEUED_READY and res.attempts == 2
    assert seen_profiles == [None, b"xsec"]   # attempt 1 native, retries anchored


def test_no_profile_bytes_means_none_on_every_attempt(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_profiles = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_profiles.append(kw.get("profile_bytes"))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["d"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_READY
    assert seen_profiles == [None, None]
