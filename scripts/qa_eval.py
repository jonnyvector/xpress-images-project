"""Run the vision judge over labeled images and score it against the labels.

Usage:
    uv run python scripts/qa_eval.py            # train split (non-holdout)
    uv run python scripts/qa_eval.py --holdout  # final check, run sparingly
    uv run python scripts/qa_eval.py --limit 20 # cap API spend while iterating

Judge verdicts are cached in output/.qa/verdicts/<config-hash>/, so re-runs only pay for
new images or a changed prompt/model.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from backend.qa.corpus import walk_corpus
from backend.qa.eval import evaluate, is_holdout, replica_review_load
from backend.qa.judge import VisionJudge
from backend.qa.labels import LabelStore
from backend.qa.policy import REPLICA_REVIEW_REASON, Decision, decide, load_policy

QA_DIR = Path("output/.qa")


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
    decisions = {}
    for i, label in enumerate(judged_labels, 1):
        candidate = candidates[label.key]
        if candidate.sample_path is None:
            decisions[label.key] = Decision(label.key, "needs_human", "no sample photo on file")
            print(f"[{i}/{len(judged_labels)}] {label.key}: needs_human (no sample, not judged)")
            continue
        if (
            policy.replica_review
            and candidate.kind == "replica"
            and candidate.key not in approved_keys
        ):
            decisions[label.key] = Decision(label.key, "needs_human", REPLICA_REVIEW_REASON)
            print(f"[{i}/{len(judged_labels)}] {label.key}: needs_human (replica review)")
            continue
        result = judge.judge(candidate)
        decisions[label.key] = decide(result, candidate, policy, approved_keys=approved_keys)
        print(f"[{i}/{len(judged_labels)}] {label.key}: {decisions[label.key].verdict}")

    metrics = evaluate(judged_labels, decisions, candidates)
    print(f"\n== {split} metrics (judge config {judge.config_hash()}) ==")
    print(f"n={metrics.n}  rejects={metrics.n_rejects}  accepts={metrics.n_accepts}")
    print(f"replica review load: {replica_review_load(decisions.values())} routed to human (D1)")
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
    report_path.write_text(json.dumps({"split": split, **asdict(metrics)}, indent=1))
    print(f"\nwritten: {report_path}")


if __name__ == "__main__":
    main()
