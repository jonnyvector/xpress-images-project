"""Score a judge+policy configuration against human labels."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.qa.corpus import Candidate
from backend.qa.labels import Label
from backend.qa.policy import REPLICA_REVIEW_REASON, TRANSITIVE_REVIEW_REASON, Decision
from backend.qa.styles_classes import EXCLUDED, style_class


def is_holdout(project_id: str) -> bool:
    """Deterministic ~20% holdout split, by project so tuning can't leak."""
    return int(hashlib.sha1(project_id.encode()).hexdigest(), 16) % 5 == 0


def replica_review_load(decisions: Iterable[Decision]) -> int:
    """How many decisions are replica-anchor human reviews (D1 routing)."""
    return sum(1 for d in decisions if d.reason == REPLICA_REVIEW_REASON)


def transitive_review_load(decisions: Iterable[Decision]) -> int:
    """How many decisions are variants routed to human via the transitive rule."""
    return sum(1 for d in decisions if d.reason == TRANSITIVE_REVIEW_REASON)


def excluded_count(candidates: Iterable[Candidate]) -> int:
    """How many candidates route to the excluded class (judge-only, no geometry)."""
    return sum(1 for c in candidates if style_class(c.door_style) == EXCLUDED)


@dataclass
class GeometryAttribution:
    """What the geometry gate changed relative to a geometry=None baseline."""

    geometry_only_catches: int = 0  # rejects flagged only with geometry on
    geometry_added_false_flags: int = 0  # accepts flagged only with geometry on


def geometry_attribution(
    labels: list[Label],
    decisions: dict[str, Decision],
    baseline: dict[str, Decision],
) -> GeometryAttribution:
    """Diff decisions against the same pipeline with geometry disabled."""
    attr = GeometryAttribution()
    for label in labels:
        decision = decisions.get(label.key)
        base = baseline.get(label.key)
        if decision is None or base is None:
            continue
        flagged = decision.verdict != "pass"
        base_flagged = base.verdict != "pass"
        if not flagged or base_flagged:
            continue
        if label.verdict == "reject":
            attr.geometry_only_catches += 1
        else:
            attr.geometry_added_false_flags += 1
    return attr


@dataclass
class EvalMetrics:
    n: int = 0
    n_rejects: int = 0
    n_accepts: int = 0
    reject_recall: float = 0.0
    false_flag_rate: float = 0.0
    recall_by_reason: dict[str, tuple[int, int]] = field(default_factory=dict)
    by_style: dict[str, dict[str, float]] = field(default_factory=dict)


def evaluate(
    labels: list[Label],
    decisions: dict[str, Decision],
    candidates: dict[str, Candidate],
    holdout_only: bool = False,
) -> EvalMetrics:
    caught = missed = false_flags = accepts = 0
    reason_caught: dict[str, int] = {}
    reason_total: dict[str, int] = {}
    style_stats: dict[str, dict[str, int]] = {}
    n = 0
    for label in labels:
        candidate = candidates.get(label.key)
        decision = decisions.get(label.key)
        if candidate is None or decision is None:
            continue
        if holdout_only and not is_holdout(candidate.project_id):
            continue
        n += 1
        flagged = decision.verdict != "pass"
        style = candidate.door_style or "unknown"
        stats = style_stats.setdefault(
            style, {"caught": 0, "rejects": 0, "flags": 0, "accepts": 0}
        )
        if label.verdict == "reject":
            stats["rejects"] += 1
            for reason in label.reasons or ["other"]:
                reason_total[reason] = reason_total.get(reason, 0) + 1
                if flagged:
                    reason_caught[reason] = reason_caught.get(reason, 0) + 1
            if flagged:
                caught += 1
                stats["caught"] += 1
            else:
                missed += 1
        else:
            accepts += 1
            stats["accepts"] += 1
            if flagged:
                false_flags += 1
                stats["flags"] += 1

    rejects = caught + missed
    return EvalMetrics(
        n=n,
        n_rejects=rejects,
        n_accepts=accepts,
        reject_recall=caught / rejects if rejects else 0.0,
        false_flag_rate=false_flags / accepts if accepts else 0.0,
        recall_by_reason={
            r: (reason_caught.get(r, 0), t) for r, t in sorted(reason_total.items())
        },
        by_style={
            s: {
                "reject_recall": v["caught"] / v["rejects"] if v["rejects"] else 1.0,
                "false_flag_rate": v["flags"] / v["accepts"] if v["accepts"] else 0.0,
                "n_rejects": float(v["rejects"]),
                "n_accepts": float(v["accepts"]),
            }
            for s, v in sorted(style_stats.items())
        },
    )
