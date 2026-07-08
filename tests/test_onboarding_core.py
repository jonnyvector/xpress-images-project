"""M1: pure onboarding policy — quality gate, best-of, verdict→action, ladder."""

from backend.onboarding import (
    VARIANT_AUTO_ACCEPT,
    VARIANT_ESCALATE,
    VARIANT_REGENERATE,
    best_attempt_index,
    is_done,
    learn_conditioning,
    lowest_dim,
    replica_queue_ready,
    score_sum,
    variant_action,
)


def _verdict(scores, geometry=None, qa_status="done", **extra):
    d = {"qa_status": qa_status, "scores": dict(scores), "geometry": geometry}
    d.update(extra)
    return d


ALL5 = {
    "panel_layout_match": 5,
    "proportions_match": 5,
    "profile_character_match": 5,
    "material_realism": 5,
    "swatch_fidelity": 5,
}


def test_queue_ready_when_all_dims_meet_min_and_no_drift():
    assert replica_queue_ready(_verdict(ALL5), min_score=3)
    assert replica_queue_ready(_verdict({**ALL5, "profile_character_match": 3}), min_score=3)


def test_not_ready_when_a_dim_below_min():
    assert not replica_queue_ready(_verdict({**ALL5, "profile_character_match": 2}), min_score=3)


def test_not_ready_on_geometry_drift_even_with_high_scores():
    assert not replica_queue_ready(_verdict(ALL5, geometry="drift"), min_score=3)


def test_unmeasurable_geometry_passes_geometry_check():
    assert replica_queue_ready(_verdict(ALL5, geometry="unmeasurable"), min_score=3)
    assert replica_queue_ready(_verdict(ALL5, geometry=None), min_score=3)


def test_not_ready_while_judging_or_missing_scores():
    assert not replica_queue_ready({"qa_status": "judging", "verdict": None}, min_score=3)
    assert not replica_queue_ready({"qa_status": "done"}, min_score=3)
    assert not is_done({"qa_status": "pending"})


def test_best_attempt_by_score_sum_ties_to_latest():
    weak = _verdict({**ALL5, "profile_character_match": 2})   # sum 22
    strong = _verdict(ALL5)                                   # sum 25
    assert best_attempt_index([weak, strong]) == 1
    # tie → latest
    assert best_attempt_index([_verdict(ALL5), _verdict(ALL5)]) == 1
    assert best_attempt_index([]) == -1
    assert score_sum(_verdict(ALL5)) == 25


def test_variant_action_mapping():
    assert variant_action({"gates_as": "pass"}) == VARIANT_AUTO_ACCEPT
    assert variant_action({"gates_as": "regenerate"}) == VARIANT_REGENERATE
    assert variant_action({"gates_as": "needs_human"}) == VARIANT_ESCALATE
    assert variant_action({"verdict": "error"}) == VARIANT_ESCALATE
    assert variant_action({}) == VARIANT_ESCALATE


def test_lowest_dim_targets_weakest():
    assert lowest_dim(_verdict({**ALL5, "profile_character_match": 1})) == "profile_character_match"
    assert lowest_dim({"scores": {}}) is None


def test_learn_conditioning_fixed_split_wood():
    # lean-conditioning D-008: 0 native · 1 maple · 2+ lean tail, all temp 0.
    a0 = learn_conditioning(0)
    assert a0.learn_in_maple is False and a0.temperature == 0.0
    assert a0.extra_note == "" and a0.lean is False
    a1 = learn_conditioning(1)
    assert a1.learn_in_maple is True and a1.temperature == 0.0 and a1.lean is False
    for attempt in (2, 3, 7, 20):
        cond = learn_conditioning(attempt, low_dim="profile_character_match")
        assert cond.lean is True, attempt
        assert cond.learn_in_maple is False and cond.extra_note == ""
        assert cond.temperature == 0.0   # rising-temp schedule removed (D-006)


def test_rtf_ladder_never_uses_maple_and_goes_lean():
    # allow_maple=False (RTF): 0 native · 1 native+corrective · 2+ lean tail.
    for attempt in range(8):
        cond = learn_conditioning(attempt, low_dim="profile_character_match",
                                  allow_maple=False)
        assert cond.learn_in_maple is False, attempt
        assert cond.temperature == 0.0, attempt
    a1 = learn_conditioning(1, low_dim="profile_character_match", allow_maple=False)
    assert a1.lean is False and a1.extra_note   # corrective survives on rung 1
    assert learn_conditioning(2, allow_maple=False).lean is True
