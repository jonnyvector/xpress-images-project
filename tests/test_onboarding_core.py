"""M1: pure onboarding policy — quality gate, best-of, verdict→action, ladder."""

from backend.onboarding import (
    VARIANT_AUTO_ACCEPT,
    VARIANT_ESCALATE,
    VARIANT_REGENERATE,
    LearnConditioning,
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


def test_learn_conditioning_ladder():
    assert learn_conditioning(0) == LearnConditioning(False, 0.0, "")
    assert learn_conditioning(1).learn_in_maple is True
    assert learn_conditioning(1).temperature == 0.0
    a2 = learn_conditioning(2, low_dim="profile_character_match")
    assert a2.learn_in_maple is False and a2.extra_note and a2.temperature == 0.0
    a3 = learn_conditioning(3, low_dim="profile_character_match")
    assert a3.learn_in_maple is True and a3.extra_note
    a4 = learn_conditioning(4, low_dim="panel_layout_match")
    assert a4.temperature > 0.0 and a4.extra_note
    # temperature rises but is capped
    assert learn_conditioning(20).temperature <= 0.6


def test_rtf_ladder_never_uses_maple():
    # allow_maple=False (RTF): no attempt may render in maple wood.
    for attempt in range(8):
        cond = learn_conditioning(attempt, low_dim="profile_character_match", allow_maple=False)
        assert cond.learn_in_maple is False, attempt
    # variety still comes from a rising temperature on later attempts
    assert learn_conditioning(1, allow_maple=False).temperature == 0.0
    assert learn_conditioning(3, low_dim="panel_layout_match", allow_maple=False).temperature > 0.0
    assert learn_conditioning(20, allow_maple=False).temperature <= 0.6
