#!/usr/bin/env python
"""Generate the graduated-trust small variant batch (5 colors) for approved doors.

For each approved replica: generate 5 diverse variants, let the QA lane judge and
auto-regenerate, then auto-accept the judge passes and leave anything unsure
queued for the operator (D-003). This is the "5 variants, you check, then bulk"
step of the graduated-trust workflow.

Usage:
    uv run python scripts/onboard_variants.py [--only CODE]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402

from backend.materials import get_swatch_files, resolve_swatch_path  # noqa: E402
from backend.onboarding import onboard_variants  # noqa: E402
from backend.state import ProjectStore  # noqa: E402

DEFAULT_SUMMARY = Path("output/.onboard/variants_summary.json")

# Approved replicas (operator-approved this session).
APPROVED = [
    ("KB732", "46fb3d64"),
    ("FR556", "78d4105b"),
    ("DP8", "5597d56d"),
    ("AP768", "abdf99a1"),
]

# A diverse 5-color reliability probe: pure white (geometry-anchor case), a mid
# grey solid, a bold color, and two woodgrains (grain-direction rule).
BATCH_STEMS = [
    "White-Supermatte",
    "Gauntlet-Grey-Supermatte",
    "Green-Supermatte",
    "White-Woodgrain",
    "Alabaster-Taction-Oak",
]


def resolve_batch() -> list[Path]:
    files = get_swatch_files("rtf")
    out = []
    for stem in BATCH_STEMS:
        p = resolve_swatch_path(stem, files)
        if p:
            out.append(p)
        else:
            print(f"  (warning: swatch {stem} not found — skipping)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="just this door code")
    ap.add_argument("--auto-accept", action="store_true",
                    help="approve judge passes automatically (default: queue all for review)")
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY,
                    help="where to write the run summary JSON")
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    batch = resolve_batch()
    print(f"batch colors: {[p.stem for p in batch]}\n")

    summary = []
    for code, pid in APPROVED:
        if args.only and code != args.only:
            continue
        print(f"[{code}] generating {len(batch)}-variant batch…", flush=True)
        res = onboard_variants(store, pid, key, batch, auto_accept=args.auto_accept)
        res["code"] = code
        res["project_id"] = pid
        summary.append(res)
        if args.auto_accept:
            print(f"[{code}] {len(res['accepted'])}/{res['total']} auto-accepted; "
                  f"{len(res['queued'])} queued for you", flush=True)
        else:
            print(f"[{code}] {res['total']} generated, all queued for your review "
                  f"({len(res['accepted'])} the judge would have passed)", flush=True)

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2))
    print(f"\nDone. Summary → {args.summary}")


if __name__ == "__main__":
    main()
