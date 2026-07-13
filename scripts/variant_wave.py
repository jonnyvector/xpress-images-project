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


def approved_wood_names(project, approvals) -> set:
    """Wood names whose variant the operator has APPROVED for this project."""
    ok = {a.image_id for a in approvals.for_project(project.id)
          if a.kind == "variant" and a.verdict == "approved"}
    return {r.wood_name for r in project.results if r.image_id in ok}


def topup_swatch_paths(project, approved_names) -> list:
    """Palette swatch paths for woods that LACK an approved variant (D-007:
    top-ups never regenerate operator-approved work)."""
    from backend.selections import build_selections

    sels = build_selections(project.selected_swatches or [],
                            door_style=project.door_style,
                            material_type=project.material_type)
    return [s["swatch_path"] for s in sels
            if s["wood_name"] not in approved_names and s.get("swatch_path")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doors", required=True, help="comma-separated door names")
    ap.add_argument("--no-auto-accept", action="store_true",
                    help="queue every variant for the operator instead")
    ap.add_argument("--topup", action="store_true",
                    help="generate ONLY woods lacking an approved variant "
                         "(reset_existing=False; protects approved work)")
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
        approved = approved_wood_names(p, approvals)
        if approved and not args.topup:
            print(f"[{door}] REFUSED — {len(approved)} operator-approved variants "
                  "exist; a full re-run would destroy them. Use --topup.", flush=True)
            summary.append({"door": door, "status": "refused_has_approved",
                            "approved": len(approved)})
            continue
        if args.topup:
            swatches = topup_swatch_paths(p, approved)
            reset = False
            if not swatches:
                print(f"[{door}] SKIP — every palette wood already approved", flush=True)
                summary.append({"door": door, "status": "complete"})
                continue
        else:
            swatches, reset = palette, True
        mode = getattr(p, "variant_hint_mode", "styled")
        print(f"[{door}] generating {len(swatches)} variants (project {p.id}, "
              f"hint={mode}, reset={reset})…", flush=True)
        # timeout must cover generation AND the QA lane judging all ~38
        # variants (~15-25 min) — the 300s default snapshots too early and
        # auto-accept misses judged-later passes.
        out = onboard_variants(store, p.id, key, swatches, timeout=2400.0,
                               reset_existing=reset,
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
