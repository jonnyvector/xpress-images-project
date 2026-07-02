"""Turn a JudgeResult into pass / regenerate / needs_human. Fail-safe: doubt -> human.

Implements the reshaped 12-step precedence (D-010): replica anchors are
human-reviewed (D1), variants of unapproved replicas never ship (transitive
rule), render-vs-render geometry drift at high confidence is a hard gate,
photo-reference (sample) geometry is advisory only — it routes to a human,
never auto-regenerates. `geometry=None` leaves pre-geometry behavior
byte-identical.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.geometry import GeometryConfig, GeometryReport
from backend.qa.judge import JudgeResult

DEFAULT_POLICY_PATH = Path("backend/qa/policy_config.json")
REPLICA_REVIEW_REASON = "replica review: geometry anchor"
TRANSITIVE_REVIEW_REASON = "replica not approved"


@dataclass
class PolicyConfig:
    min_score: int = 4
    untrusted_styles: list[str] = field(default_factory=list)
    replica_review: bool = True  # replicas are geometry anchors: human-review unless approved
    transitive_replica_review: bool = True  # variants of unapproved replicas never ship
    geometry: GeometryConfig | None = None  # None -> geometry checks disabled


@dataclass
class Decision:
    key: str
    verdict: str  # "pass" | "regenerate" | "needs_human"
    reason: str


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> PolicyConfig:
    data = json.loads(path.read_text())
    return PolicyConfig(
        min_score=int(data.get("min_score", 4)),
        untrusted_styles=list(data.get("untrusted_styles", [])),
        replica_review=bool(data.get("replica_review", True)),
        transitive_replica_review=bool(data.get("transitive_replica_review", True)),
        geometry=_parse_geometry(data.get("geometry")),
    )


def _parse_geometry(data: dict | None) -> GeometryConfig | None:
    if data is None:
        return None
    config = GeometryConfig(
        measurable_styles=list(data.get("measurable_styles", [])),
        drift_thresholds={k: float(v) for k, v in data.get("drift_thresholds", {}).items()},
    )
    if "working_width" in data:
        config.working_width = int(data["working_width"])
    for name in (
        "aspect_threshold",
        "min_box_fraction",
        "min_peak_prominence",
        "max_match_residual",
    ):
        if name in data:
            setattr(config, name, float(data[name]))
    return config


def decide(
    result: JudgeResult,
    candidate: Candidate,
    config: PolicyConfig,
    geometry: GeometryReport | None = None,
    approved_keys: frozenset[str] = frozenset(),
    replica_approved: bool = True,
) -> Decision:
    # 1. untrusted style
    if candidate.door_style in config.untrusted_styles:
        return Decision(result.key, "needs_human", f"untrusted style: {candidate.door_style}")
    # 2. no sample photo
    if candidate.sample_path is None:
        return Decision(result.key, "needs_human", "no sample photo on file")
    # 3. replica review (D1): the human-approved replica is the geometry anchor
    if (
        config.replica_review
        and candidate.kind == "replica"
        and candidate.key not in approved_keys
    ):
        return Decision(result.key, "needs_human", REPLICA_REVIEW_REASON)
    # 4. transitive replica approval: variants of an unapproved replica never ship
    if config.transitive_replica_review and candidate.kind == "variant" and not replica_approved:
        return Decision(result.key, "needs_human", TRANSITIVE_REVIEW_REASON)
    # 5. judge error
    if result.verdict == "error":
        return Decision(result.key, "needs_human", f"judge error: {result.reason}")
    # 6. judge fail / low scores (before unmeasurable: confidently bad -> regenerate)
    scores = {
        "panel_layout_match": result.panel_layout_match,
        "proportions_match": result.proportions_match,
        "profile_character_match": result.profile_character_match,
        "material_realism": result.material_realism,
        "swatch_fidelity": result.swatch_fidelity,
    }
    low = [f"{name}={value}" for name, value in scores.items() if value < config.min_score]
    if result.verdict == "fail" or low:
        detail = result.reason or "judge fail"
        if low:
            detail += f" (low scores: {', '.join(low)})"
        return Decision(result.key, "regenerate", detail)
    if geometry is not None:
        # 7. render-vs-render hard gate: high-confidence drift vs replica
        if (
            geometry.status == "drift"
            and geometry.confidence == "high"
            and geometry.reference == "replica"
        ):
            return Decision(result.key, "regenerate", f"geometry drift: {geometry.detail}")
        # 8. photo comparison is advisory (A-001): drift vs sample -> human, any confidence
        if geometry.status == "drift" and geometry.reference == "sample":
            return Decision(
                result.key,
                "needs_human",
                f"geometry drift vs sample (advisory): {geometry.detail}",
            )
        # 9. low-confidence drift
        if geometry.status == "drift":
            return Decision(
                result.key, "needs_human", f"low-confidence geometry drift: {geometry.detail}"
            )
        # 10. unmeasurable (measurable classes only — excluded classes get geometry=None)
        if geometry.status == "unmeasurable":
            return Decision(
                result.key, "needs_human", f"geometry unmeasurable: {geometry.detail}"
            )
    # 11. judge low confidence
    if result.confidence == "low":
        return Decision(result.key, "needs_human", "low judge confidence")
    # 12. pass
    return Decision(result.key, "pass", result.reason)
