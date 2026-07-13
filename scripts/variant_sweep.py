#!/usr/bin/env python
"""Recovery/closeout sweep for variant batches whose QA judging outlived the
wave process: re-enqueue unjudged variants, wait for the lane to drain, then
apply the D-003 auto-accept policy (judge pass -> approved; everything else
stays queued for the operator).

Usage:
    uv run python scripts/variant_sweep.py --doors "Baldwin,Boston,..." [--no-auto-accept]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402
from variant_wave import approved_project  # noqa: E402

from backend.onboarding import VARIANT_AUTO_ACCEPT, variant_action  # noqa: E402
from backend.qa.approvals import Approval, get_approval_store  # noqa: E402
from backend.qa.qa_lane import get_qa_lane  # noqa: E402
from backend.selections import build_selections  # noqa: E402
from backend.state import ProjectStore  # noqa: E402


def swatch_by_wood_name(project) -> dict:
    """wood_name -> swatch Path, rebuilt exactly as generation built it."""
    sels = build_selections(project.selected_swatches or [],
                            door_style=project.door_style,
                            material_type=project.material_type)
    return {s["wood_name"]: s.get("swatch_path") for s in sels}


def unjudged(project):
    for r in project.results:
        v = project.qa_verdicts.get(r.image_id)
        if not v or v.get("qa_status") != "done":
            yield r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doors", required=True)
    ap.add_argument("--no-auto-accept", action="store_true")
    ap.add_argument("--timeout", type=float, default=2400.0)
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    approvals = get_approval_store()
    doors = [d.strip() for d in args.doors.split(",") if d.strip()]

    targets = []
    for door in doors:
        p = approved_project(store, approvals, door)
        if p is None:
            print(f"[{door}] SKIP — no approved current replica", flush=True)
            continue
        targets.append((door, p.id))

    # Re-enqueue everything unjudged, then wait for the lane to drain.
    lane = get_qa_lane()
    pending_total = 0
    for door, pid in targets:
        p = store.get(pid)
        swatches = swatch_by_wood_name(p)
        todo = list(unjudged(p))
        pending_total += len(todo)
        for r in todo:
            lane.enqueue(store, pid, r.image_id, key, kind="variant",
                         swatch_path=swatches.get(r.wood_name))
        print(f"[{door}] re-enqueued {len(todo)} unjudged variants", flush=True)

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        remaining = sum(len(list(unjudged(store.get(pid)))) for _, pid in targets)
        if remaining == 0:
            break
        print(f"…{remaining} still judging", flush=True)
        time.sleep(15)

    # Block until the lane's executor is truly empty. A process exiting (or a
    # second process starting) while lane threads still save from THIS store's
    # snapshot clobbers other writers — one mutating process at a time, run to
    # full drain (learned 2026-07-11, wave-1 verdict clobbering).
    lane._executor.shutdown(wait=True)

    # Apply the auto-accept policy over final verdicts.
    for door, pid in targets:
        p = store.get(pid)
        decided = {a.image_id for a in approvals.for_project(pid)}
        accepted = queued = 0
        for r in p.results:
            if r.image_id in decided:
                continue
            v = p.qa_verdicts.get(r.image_id) or {}
            if v.get("qa_status") != "done":
                queued += 1
                continue
            if not args.no_auto_accept and variant_action(v) == VARIANT_AUTO_ACCEPT:
                approvals.set(Approval(
                    image_id=r.image_id, project_id=pid, kind="variant",
                    verdict="approved", note="variant sweep auto-accept (judge pass)",
                ))
                accepted += 1
            else:
                queued += 1
        print(f"[{door}] swept — {accepted} auto-accepted, {queued} for operator",
              flush=True)


if __name__ == "__main__":
    main()
