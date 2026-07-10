#!/usr/bin/env python
"""Run variant generation for a wave of APPROVED replicas (D-003 pipeline:
judge passes auto-accept, unsure variants queue for the operator).

Usage:
    uv run python scripts/variant_wave.py --doors "Baldwin,Boston,..." [--no-auto-accept]

Each door's project must have an operator-approved replica; projects are
matched case-insensitively on normalized name (wood cabinet doors only).
Sequential per door — onboard_variants waits for the batch + QA lane.
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
from backend.qa.approvals import get_approval_store  # noqa: E402
from backend.state import ProjectStore  # noqa: E402


def norm(name: str) -> str:
    for suf in (" Cabinet Door", " Drawer Front"):
        if name.endswith(suf):
            name = name[: -len(suf)]
    return name.lower()


def approved_project(store, approvals, door: str):
    """The project whose CURRENT replica the operator approved, for this door."""
    want = door.lower()
    for p in store.list_projects():
        if (norm(p.name) == want
                and getattr(p, "product_type", "") == "Cabinet Door"
                and getattr(p, "material_type", "") == "wood"
                and p.base_image_id):
            for a in approvals.for_project(p.id):
                if a.image_id == p.base_image_id and a.verdict == "approved":
                    return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doors", required=True, help="comma-separated door names")
    ap.add_argument("--no-auto-accept", action="store_true",
                    help="queue every variant for the operator instead")
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    approvals = get_approval_store()
    palette = get_swatch_files("wood")
    doors = [d.strip() for d in args.doors.split(",") if d.strip()]

    summary = []
    for door in doors:
        p = approved_project(store, approvals, door)
        if p is None:
            print(f"[{door}] SKIP — no operator-approved current replica", flush=True)
            summary.append({"door": door, "status": "skipped_not_approved"})
            continue
        print(f"[{door}] generating {len(palette)} variants (project {p.id})…", flush=True)
        # timeout must cover generation AND the QA lane judging all ~38
        # variants (~15-25 min) — the 300s default snapshots too early and
        # auto-accept misses judged-later passes.
        out = onboard_variants(store, p.id, key, palette, timeout=2400.0,
                               auto_accept=not args.no_auto_accept)
        print(f"[{door}] done — {out['total']} generated, "
              f"{len(out['accepted'])} auto-accepted, {len(out['queued'])} queued",
              flush=True)
        summary.append({"door": door, "project_id": p.id, **{
            "total": out["total"], "accepted": len(out["accepted"]),
            "queued": len(out["queued"])}})

    # Single-writer rule: never exit while the in-process QA lane still holds
    # work — lingering threads keep saving from this process's stale snapshot
    # and clobber later writers (learned 2026-07-11).
    from backend.qa.qa_lane import get_qa_lane
    get_qa_lane()._executor.shutdown(wait=True)

    out_path = Path("output/.onboard/variant_wave_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWave complete. Summary → {out_path}", flush=True)


if __name__ == "__main__":
    main()
