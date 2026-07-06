#!/usr/bin/env python
"""Bulk-generate the full RTF palette for doors whose sample batch passed review.

For each door, generates every palette color NOT already present (the operator-
approved sample variants are kept), lets the QA lane judge + auto-regenerate, and
(with auto-accept on, the default here) approves judge passes — leaving only
unsure variants in the Review tab.

Usage:
    uv run python scripts/onboard_bulk.py [--only CODE] [--review]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402

from backend.materials import get_swatch_files  # noqa: E402
from backend.onboarding import onboard_variants  # noqa: E402
from backend.state import ProjectStore  # noqa: E402

DEFAULT_SUMMARY = Path("output/.onboard/bulk_summary.json")

# Doors whose 5-color sample batch passed operator review (ready to bulk).
DOORS = [
    ("FR556", "78d4105b"),
    ("DP8", "5597d56d"),
    ("KB732", "46fb3d64"),
    ("AP768", "abdf99a1"),
]


def _norm(s: str) -> str:
    return s.lower().replace(" ", "").replace("-", "").replace("_", "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="just this door code")
    ap.add_argument("--review", action="store_true",
                    help="queue everything for review instead of auto-accepting passes")
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    palette = get_swatch_files("rtf")

    summary = []
    for code, pid in DOORS:
        if args.only and code != args.only:
            continue
        project = store.get(pid)
        have = {_norm(r.wood_name) for r in project.results}
        remaining = [p for p in palette if _norm(p.stem) not in have]
        if not remaining:
            print(f"[{code}] already complete ({len(project.results)} variants)")
            continue

        print(f"[{code}] bulking {len(remaining)} remaining colors "
              f"(keeping {len(project.results)} approved)…", flush=True)
        res = onboard_variants(
            store, pid, key, remaining,
            reset_existing=False, auto_accept=not args.review, timeout=1200.0,
        )
        res["code"] = code
        res["project_id"] = pid
        summary.append(res)
        print(f"[{code}] {len(res['accepted'])}/{res['total']} passed"
              + ("" if args.review else " (auto-accepted)")
              + f"; {len(res['queued'])} queued for you", flush=True)

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2))
    print(f"\nDone. Summary → {args.summary}")


if __name__ == "__main__":
    main()
