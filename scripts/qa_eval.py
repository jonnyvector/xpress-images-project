"""Run the vision judge + geometry gate over labeled images and score against labels.

Usage:
    uv run python scripts/qa_eval.py            # train split (non-holdout)
    uv run python scripts/qa_eval.py --holdout  # final check, run sparingly
    uv run python scripts/qa_eval.py --limit 20 # cap API spend while iterating

Judge verdicts are cached in output/.qa/verdicts/<config-hash>/, geometry reports in
output/.qa/geometry/<config-hash>/, so re-runs only pay for new images or changed config.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.qa.corpus import Candidate, walk_corpus
from backend.qa.eval import (
    evaluate,
    excluded_count,
    geometry_attribution,
    is_holdout,
    replica_review_load,
    transitive_review_load,
)
from backend.qa.geometry import GeometryReport, measure_cached
from backend.qa.judge import VisionJudge
from backend.qa.labels import LabelStore
from backend.qa.policy import (
    REPLICA_REVIEW_REASON,
    TRANSITIVE_REVIEW_REASON,
    Decision,
    PolicyConfig,
    decide,
    load_policy,
)
from backend.qa.styles_classes import style_class

QA_DIR = Path("output/.qa")
GEOMETRY_CACHE = QA_DIR / "geometry"


def replica_key_for(candidate: Candidate) -> str:
    return f"{candidate.project_id}:{candidate.version}:replica:-1"


def geometry_for(
    candidate: Candidate,
    policy: PolicyConfig,
    candidates: dict[str, Candidate],
) -> GeometryReport | None:
    """Style routing + reference selection (D-010): variant -> replica primary,
    replica -> sample. Excluded classes and disabled geometry -> None (judge-only)."""
    if policy.geometry is None:
        return None
    cls = style_class(candidate.door_style)
    if cls not in policy.geometry.measurable_styles:
        return None
    if candidate.kind == "variant":
        replica = candidates.get(replica_key_for(candidate))
        if replica is not None and replica.image_path.exists():
            reference_path, reference = replica.image_path, "replica"
        elif candidate.sample_path is not None:
            reference_path, reference = candidate.sample_path, "sample"
        else:
            return None
    else:  # replica -> sample (advisory)
        if candidate.sample_path is None:
            return None
        reference_path, reference = candidate.sample_path, "sample"
    return measure_cached(
        reference_path, candidate.image_path, candidate.key, policy.geometry, cls,
        reference=reference, cache_dir=GEOMETRY_CACHE,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", action="store_true", help="score the holdout split")
    parser.add_argument(
        "--limit", type=int, default=0, help="max images to judge (0 = all)"
    )
    parser.add_argument("--model", default=None, help="override judge model")
    args = parser.parse_args()

    load_dotenv(override=True)  # project .env wins over stale shell exports
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set (see .env)")

    labels = LabelStore(QA_DIR / "labels.json").all()
    approved_keys = frozenset(
        label.key for label in labels if label.verdict == "accept"
    )
    candidates = {
        c.key: c for c in walk_corpus(Path("output/.projects"), Path("swatches"))
    }
    judged_labels = [
        label
        for label in labels
        if label.key in candidates
        and is_holdout(candidates[label.key].project_id) == args.holdout
    ]
    if args.limit:
        judged_labels = judged_labels[: args.limit]
    split = "holdout" if args.holdout else "train"
    print(f"{len(judged_labels)} labeled images in {split} split")

    kwargs = {"model": args.model} if args.model else {}
    judge = VisionJudge(api_key=api_key, cache_dir=QA_DIR / "verdicts", **kwargs)
    policy = load_policy()
    decisions: dict[str, Decision] = {}
    baseline: dict[str, Decision] = {}  # same pipeline, geometry disabled
    for i, label in enumerate(judged_labels, 1):
        candidate = candidates[label.key]
        replica_approved = (
            replica_key_for(candidate) in approved_keys
            if candidate.kind == "variant"
            else True
        )
        # Short-circuits that mirror decide() steps 2-4 without paying for a judge
        # call; these fire identically with or without geometry.
        short: Decision | None = None
        if candidate.sample_path is None:
            short = Decision(label.key, "needs_human", "no sample photo on file")
        elif (
            policy.replica_review
            and candidate.kind == "replica"
            and candidate.key not in approved_keys
        ):
            short = Decision(label.key, "needs_human", REPLICA_REVIEW_REASON)
        elif policy.transitive_replica_review and not replica_approved:
            short = Decision(label.key, "needs_human", TRANSITIVE_REVIEW_REASON)
        if short is not None:
            decisions[label.key] = baseline[label.key] = short
            print(f"[{i}/{len(judged_labels)}] {label.key}: needs_human ({short.reason})")
            continue
        result = judge.judge(candidate)
        geometry = geometry_for(candidate, policy, candidates)
        decisions[label.key] = decide(
            result, candidate, policy, geometry=geometry,
            approved_keys=approved_keys, replica_approved=replica_approved,
        )
        baseline[label.key] = decide(
            result, candidate, policy, geometry=None,
            approved_keys=approved_keys, replica_approved=replica_approved,
        )
        geo_note = f" [geo: {geometry.status}/{geometry.confidence}]" if geometry else ""
        print(f"[{i}/{len(judged_labels)}] {label.key}: {decisions[label.key].verdict}{geo_note}")

    metrics = evaluate(judged_labels, decisions, candidates)
    attr = geometry_attribution(judged_labels, decisions, baseline)
    excluded = excluded_count(candidates[label.key] for label in judged_labels)
    print(f"\n== {split} metrics (judge config {judge.config_hash()}) ==")
    print(f"n={metrics.n}  rejects={metrics.n_rejects}  accepts={metrics.n_accepts}")
    print(f"replica review load: {replica_review_load(decisions.values())} routed to human (D1)")
    print(
        f"transitive replica load: {transitive_review_load(decisions.values())} "
        "variants of unapproved replicas routed to human"
    )
    print(
        f"geometry attribution: {attr.geometry_only_catches} geometry-only catches, "
        f"{attr.geometry_added_false_flags} geometry-added false flags"
    )
    print(f"excluded-class candidates (judge-only): {excluded}")
    print(f"reject recall:   {metrics.reject_recall:.1%}  (target >= 95%)")
    print(f"false-flag rate: {metrics.false_flag_rate:.1%}  (target <= 20%)")
    print("recall by reason:")
    for reason, (caught, total) in metrics.recall_by_reason.items():
        print(f"  {reason}: {caught}/{total}")
    print("by door style:")
    for style, stats in metrics.by_style.items():
        print(
            f"  {style}: recall {stats['reject_recall']:.0%} "
            f"({stats['n_rejects']:.0f} rejects), "
            f"false flags {stats['false_flag_rate']:.0%} ({stats['n_accepts']:.0f} accepts)"
        )
    report_path = QA_DIR / "eval_report.json"
    QA_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"split": split, **asdict(metrics), **asdict(attr)}, indent=1)
    )
    print(f"\nwritten: {report_path}")


if __name__ == "__main__":
    main()
