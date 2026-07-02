"""Build output/.qa/review.html from cached judge verdicts + policy.

Usage:
    uv run python scripts/qa_report.py
    uv run python scripts/qa_report.py --model gemini-3-pro-preview

Only images with a cached verdict appear (run scripts/qa_eval.py first). Pass the same
--model used for that qa_eval.py run so the report reads the matching config-hash cache dir.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.qa.corpus import walk_corpus
from backend.qa.judge import JudgeResult, VisionJudge
from backend.qa.policy import decide, load_policy
from backend.qa.report import render_review_report
from backend.qa.thumbs import export_thumb

QA_DIR = Path("output/.qa")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="override judge model")
    args = parser.parse_args()

    candidates = {c.key: c for c in walk_corpus(Path("output/.projects"), Path("swatches"))}
    kwargs = {"model": args.model} if args.model else {}
    judge = VisionJudge(
        api_key="unused-cache-only", client=object(), cache_dir=QA_DIR / "verdicts", **kwargs
    )
    verdict_dir = QA_DIR / "verdicts" / judge.config_hash()
    policy = load_policy()
    items = []
    thumb_urls: dict[str, dict[str, str]] = {}
    if verdict_dir.exists():
        for path in sorted(verdict_dir.glob("*.json")):
            result = JudgeResult(**json.loads(path.read_text()))
            candidate = candidates.get(result.key)
            if candidate is None:
                continue
            decision = decide(result, candidate, policy)
            items.append((candidate, result, decision))
            if decision.verdict != "pass":
                urls: dict[str, str] = {}
                for role, src in (("img", candidate.image_path),
                                  ("sample", candidate.sample_path),
                                  ("swatch", candidate.swatch_path)):
                    if src is None:
                        continue
                    thumb = export_thumb(src, QA_DIR / "site" / "thumbs")
                    if thumb is not None:
                        urls[role] = f"site/thumbs/{thumb.name}"
                thumb_urls[candidate.key] = urls
    out = QA_DIR / "review.html"
    QA_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(render_review_report(items, thumb_urls))
    flagged = sum(1 for it in items if it[2].verdict != "pass")
    print(f"{len(items)} judged, {flagged} flagged -> {out}")


if __name__ == "__main__":
    main()
