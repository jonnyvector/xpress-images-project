import json
from pathlib import Path

import pytest

from backend.qa.corpus import Candidate
from backend.qa.geometry import GeometryConfig, GeometryReport, measure
from backend.qa.judge import JudgeResult
from backend.qa.policy import (
    TRANSITIVE_REVIEW_REASON,
    PolicyConfig,
    decide,
    load_policy,
)

FIXTURES = Path(__file__).parent / "fixtures" / "geometry"
needs_fixtures = pytest.mark.skipif(
    not FIXTURES.exists(), reason="real-photo fixtures not exported (M4 spike)"
)


def _candidate(
    style: str | None = "shaker",
    sample_path: Path | None = Path("sample.bin"),
    kind: str = "variant",
) -> Candidate:
    index = -1 if kind == "replica" else 0
    return Candidate(
        key=f"p:0:{kind}:{index}", project_id="p", project_name="P", door_style=style,
        version=0, kind=kind, index=index, wood_name="Cherry Natural",
        image_path=Path("x.bin"), sample_path=sample_path, swatch_path=None, presumed="accept",
    )


def _result(**overrides: object) -> JudgeResult:
    base = dict(
        key="p:0:variant:0", panel_layout_match=5, proportions_match=5,
        profile_character_match=5, material_realism=5, swatch_fidelity=5,
        artifacts=[], verdict="pass", confidence="high", reason="ok",
    )
    base.update(overrides)
    return JudgeResult(**base)  # type: ignore[arg-type]


CONFIG = PolicyConfig(min_score=4, untrusted_styles=["applied_molding"])


def test_high_confidence_pass() -> None:
    assert decide(_result(), _candidate(), CONFIG).verdict == "pass"


def test_fail_verdict_regenerates() -> None:
    d = decide(_result(verdict="fail", reason="stiles wider"), _candidate(), CONFIG)
    assert d.verdict == "regenerate"
    assert "stiles wider" in d.reason


def test_low_score_regenerates_even_if_judge_said_pass() -> None:
    d = decide(_result(proportions_match=3), _candidate(), CONFIG)
    assert d.verdict == "regenerate"


def test_low_confidence_pass_needs_human() -> None:
    d = decide(_result(confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_error_needs_human() -> None:
    d = decide(_result(verdict="error", confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_untrusted_style_needs_human_regardless() -> None:
    d = decide(_result(), _candidate(style="applied_molding"), CONFIG)
    assert d.verdict == "needs_human"


def test_no_sample_photo_needs_human_even_on_perfect_pass() -> None:
    d = decide(_result(), _candidate(sample_path=None), CONFIG)
    assert d.verdict == "needs_human"
    assert "sample" in d.reason.lower()


def test_load_policy_default_file() -> None:
    config = load_policy(Path("backend/qa/policy_config.json"))
    assert config.min_score >= 1
    assert config.replica_review is True


def test_unapproved_replica_needs_human_even_on_perfect_pass() -> None:
    replica = _candidate(kind="replica")
    d = decide(_result(key=replica.key), replica, CONFIG)
    assert d.verdict == "needs_human"
    assert d.reason == "replica review: geometry anchor"


def test_approved_replica_falls_through_to_normal_precedence() -> None:
    replica = _candidate(kind="replica")
    d = decide(_result(key=replica.key), replica, CONFIG, approved_keys=frozenset({replica.key}))
    assert d.verdict == "pass"


def test_replica_review_disabled_reproduces_old_behavior() -> None:
    config = PolicyConfig(min_score=4, untrusted_styles=["applied_molding"], replica_review=False)
    replica = _candidate(kind="replica")
    d = decide(_result(key=replica.key), replica, config)
    assert d.verdict == "pass"


# --- reshaped 12-step precedence (D-010) ---------------------------------------


def _report(
    status: str = "ok",
    confidence: str = "high",
    reference: str = "replica",
    max_delta: float = 0.0,
    detail: str = "",
) -> GeometryReport:
    return GeometryReport(
        key="p:0:variant:0", status=status, confidence=confidence, reference=reference,
        aspect_delta=0.0, stile_deltas={}, rail_deltas={}, boundary_deltas=[],
        unmatched_boundaries=0, max_delta=max_delta,
        detail=detail or f"{status}; worst stile.left={max_delta:.3f}",
    )


def test_variant_of_unapproved_replica_needs_human_transitive() -> None:
    d = decide(_result(), _candidate(), CONFIG, replica_approved=False)
    assert d.verdict == "needs_human"
    assert d.reason == TRANSITIVE_REVIEW_REASON


def test_transitive_review_disabled_falls_through() -> None:
    config = PolicyConfig(min_score=4, transitive_replica_review=False)
    d = decide(_result(), _candidate(), config, replica_approved=False)
    assert d.verdict == "pass"


def test_transitive_rule_does_not_apply_to_replicas() -> None:
    # A replica's own gate is step 3 (replica review); replica_approved is
    # about the variant's anchor and must not double-fire on replicas.
    replica = _candidate(kind="replica")
    d = decide(
        _result(key=replica.key), replica, CONFIG,
        approved_keys=frozenset({replica.key}), replica_approved=False,
    )
    assert d.verdict == "pass"


def test_high_confidence_replica_drift_overrides_passing_judge() -> None:
    geo = _report(status="drift", confidence="high", reference="replica",
                  max_delta=0.045, detail="drift; worst stile.left=0.045 (thr 0.030)")
    d = decide(_result(), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "regenerate"
    assert "stile.left" in d.reason  # names the worst measurement


def test_sample_reference_drift_needs_human_even_at_high_confidence() -> None:
    geo = _report(status="drift", confidence="high", reference="sample", max_delta=0.05)
    d = decide(_result(), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "needs_human"


def test_sample_reference_drift_needs_human_at_low_confidence() -> None:
    geo = _report(status="drift", confidence="low", reference="sample", max_delta=0.05)
    d = decide(_result(), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "needs_human"


def test_low_confidence_replica_drift_needs_human() -> None:
    geo = _report(status="drift", confidence="low", reference="replica", max_delta=0.05)
    d = decide(_result(), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "needs_human"


def test_unmeasurable_needs_human() -> None:
    geo = _report(status="unmeasurable", confidence="low", detail="GEO-002: box check failed")
    d = decide(_result(), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "needs_human"
    assert "GEO-002" in d.reason


def test_judge_fail_plus_unmeasurable_regenerates_asymmetry() -> None:
    # Confidently bad -> regenerate, not human: judge fail (step 6) beats
    # unmeasurable (step 10).
    geo = _report(status="unmeasurable", confidence="low")
    d = decide(_result(verdict="fail", reason="warped"), _candidate(), CONFIG, geometry=geo)
    assert d.verdict == "regenerate"


def test_geometry_ok_passes_through() -> None:
    d = decide(_result(), _candidate(), CONFIG, geometry=_report())
    assert d.verdict == "pass"


def test_geometry_none_is_byte_identical_to_pre_geometry_behavior() -> None:
    scenarios = [
        (_result(), _candidate()),
        (_result(verdict="fail", reason="bad"), _candidate()),
        (_result(confidence="low"), _candidate()),
        (_result(verdict="error", confidence="low"), _candidate()),
        (_result(proportions_match=2), _candidate()),
        (_result(), _candidate(style="applied_molding")),
        (_result(), _candidate(sample_path=None)),
        (_result(key="p:0:replica:-1"), _candidate(kind="replica")),
    ]
    for result, candidate in scenarios:
        assert decide(result, candidate, CONFIG, geometry=None) == decide(
            result, candidate, CONFIG
        )


def test_load_policy_parses_nested_geometry(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({
        "min_score": 4,
        "geometry": {
            "measurable_styles": ["frame_standard", "frame_narrow"],
            "drift_thresholds": {"frame_standard": 0.03, "frame_narrow": 0.015},
            "working_width": 1024,
        },
    }))
    config = load_policy(path)
    assert isinstance(config.geometry, GeometryConfig)
    assert config.geometry.measurable_styles == ["frame_standard", "frame_narrow"]
    assert config.geometry.drift_thresholds["frame_narrow"] == 0.015
    assert config.geometry.working_width == 1024
    assert config.geometry.aspect_threshold == 0.04  # default preserved
    assert config.transitive_replica_review is True


def test_load_policy_geometry_absent_disables(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"min_score": 4}))
    assert load_policy(path).geometry is None


def test_committed_policy_config_has_geometry_thresholds() -> None:
    config = load_policy(Path("backend/qa/policy_config.json"))
    assert config.geometry is not None
    assert config.geometry.drift_thresholds["frame_standard"] == 0.03
    assert config.geometry.drift_thresholds["frame_narrow"] == 0.015


# --- M5 acceptance on real fixtures (D-010) -------------------------------------

VARIANT_MISS_KEYS = [
    "7efd9e3d:1:variant:2",
    "571ae351:1:variant:0",
    "4ebf2d15:1:variant:0",
    "4ebf2d15:1:variant:1",
    "b684d34b:0:variant:0",
]


def _fixture_entry(key: str) -> dict:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    return next(e for e in manifest if e["key"] == key)


def _fixture_candidate(entry: dict) -> Candidate:
    pid, version, kind, index = entry["key"].split(":")
    return Candidate(
        key=entry["key"], project_id=pid, project_name=pid,
        door_style=entry["door_style"], version=int(version), kind=kind,
        index=int(index), wood_name="Cherry Natural",
        image_path=FIXTURES / entry["images"]["candidate"],
        sample_path=FIXTURES / entry["images"]["sample"],
        swatch_path=None, presumed="reject",
    )


@needs_fixtures
@pytest.mark.parametrize("key", VARIANT_MISS_KEYS)
def test_variant_misses_route_needs_human_via_transitive_rule(key: str) -> None:
    # All 5 missed variants belong to label-rejected replicas: production
    # semantics say variants of an unapproved replica never ship, whatever
    # the judge or geometry says about them individually.
    entry = _fixture_entry(key)
    candidate = _fixture_candidate(entry)
    geo = None
    if "replica" in entry["images"]:
        geo = measure(
            FIXTURES / entry["images"]["replica"], candidate.image_path, key,
            _geometry_config(), entry["style_class"], reference="replica",
        )
    d = decide(_result(key=key), candidate, CONFIG, geometry=geo, replica_approved=False)
    assert d.verdict == "needs_human"
    assert d.reason == TRANSITIVE_REVIEW_REASON


def _geometry_config() -> GeometryConfig:
    return GeometryConfig(
        measurable_styles=["frame_standard", "frame_narrow"],
        drift_thresholds={"frame_standard": 0.03, "frame_narrow": 0.015},
    )


@needs_fixtures
@pytest.mark.parametrize("key", ["2564359f:0:variant:0", "2564359f:0:variant:2"])
def test_accepted_variants_measure_ok_high_and_pass(key: str) -> None:
    entry = _fixture_entry(key)
    candidate = _fixture_candidate(entry)
    geo = measure(
        FIXTURES / entry["images"]["replica"], candidate.image_path, key,
        _geometry_config(), entry["style_class"], reference="replica",
    )
    assert geo.status == "ok"
    assert geo.confidence == "high"
    d = decide(_result(key=key), candidate, CONFIG, geometry=geo, replica_approved=True)
    assert d.verdict == "pass"
