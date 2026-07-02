"""Score a judge+policy configuration against human labels."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field

from backend.qa.corpus import Candidate
from backend.qa.labels import Label
from backend.qa.policy import REPLICA_REVIEW_REASON, Decision


def is_holdout(project_id: str) -> bool:
    """Deterministic ~20% holdout split, by project so tuning can't leak."""
    return int(hashlib.sha1(project_id.encode()).hexdigest(), 16) % 5 == 0


def replica_review_load(decisions: Iterable[Decision]) -> int:
    """How many decisions are replica-anchor human reviews (D1 routing)."""
    return sum(1 for d in decisions if d.reason == REPLICA_REVIEW_REASON)


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
