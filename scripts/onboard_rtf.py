#!/usr/bin/env python
"""Batch-onboard RTF cabinet doors to queued, judge-clean replicas.

For each door: create a project, upload the local catalog source photo, and run
the autonomous replica loop (learn → judge → re-learn ≤ cap) until the judge is
clean, then STOP — the replica waits in the operator Review tab for approval
(Stage-A gate honored, D-001). Variants are a separate, later phase.

Usage:
    uv run python scripts/onboard_rtf.py [--only CODE] [--cap 5] [--ceiling 8.0]
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402

from backend.materials import get_swatch_files  # noqa: E402
from backend.onboarding import (  # noqa: E402
    QUEUED_READY,
    Spend,
    onboard_replica,
)
from backend.state import ProjectStore  # noqa: E402

CATALOG = Path.home() / "Desktop" / "Xpress" / "Decore Catalog" / "rtf"
DEFAULT_SUMMARY = Path("output/.onboard/replicas_summary.json")

# The next 5 uncovered thermofoil cabinet doors (D-004), with per-door style.
DOORS = [
    {
        "code": "FR556",
        "door_style": "raised_panel",
        "notes": (
            "Reproduce the EXACT profile from the reference photo. The frame is "
            "FLAT, and at its INNER EDGE there is a distinct STEP — a clean "
            "right-angle step DOWN — before the surface bevels down into the "
            "recess around the raised center panel. This stepped inner edge is "
            "the defining detail; it is NOT a smooth continuous cove or ogee. "
            "The center panel is raised with a flat field and crisp bevels; keep "
            "the border between frame and panel narrow. White RTF, smooth. "
            "Square outer corners."
        ),
    },
    {
        "code": "KB732",
        "door_style": "solid_plank",
        "notes": (
            "Single flat slab door with a wide beveled/chamfered perimeter that "
            "runs to a flat center field; no separate frame or panel; smooth "
            "uniform thermofoil; square outer corners."
        ),
    },
    {
        "code": "DT223",
        "door_style": "shaker_bevel",
        # Minimal on purpose: the shaker_bevel learn_prompt + the RTF material
        # instruction (auto-injected from material_type) + the sample photo carry
        # it. Verbose notes made the model add a trim-like inner profile.
        "notes": "",
    },
    {
        "code": "DP8",
        "door_style": "raised_panel",
        "notes": (
            "Raised center panel with an ARCHED (cathedral) top rail — the raised "
            "field follows a soft arch at the top and is square at the bottom; "
            "rounded inside edge; square outer corners."
        ),
    },
    {
        "code": "AP768",
        "door_style": "recessed_panel_arched",  # arched → geometry-excluded
        "notes": (
            "Recessed routed center panel with an ARCHED (cathedral) top; ogee "
            "inner profile around the panel opening; arched top rail; square "
            "outer corners."
        ),
    },
]


def source_image(code: str, catalog: Path = CATALOG) -> Path | None:
    p = catalog / f"{code}-3-4" / "hero" / "door.jpg"
    return p if p.exists() else None


def already_onboarded(store: ProjectStore, code: str):
    """A prior project for this door that already has a learned replica."""
    for p in store.list_projects():
        if code.lower() in p.name.lower() and getattr(p, "has_signature", False):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="onboard just this door code")
    ap.add_argument("--cap", type=int, default=5, help="max re-learn attempts per door")
    ap.add_argument("--ceiling", type=float, default=8.0, help="run spend ceiling (USD)")
    ap.add_argument("--force", action="store_true",
                    help="re-onboard in place even if the door already has a replica")
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY,
                    help="where to write the run summary JSON")
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    palette = [str(p) for p in get_swatch_files("rtf")]  # full palette for later variants
    spend = Spend(ceiling_usd=args.ceiling)

    summary = []
    for spec in DOORS:
        code = spec["code"]
        if args.only and code != args.only:
            continue

        src = source_image(code)
        if src is None:
            print(f"[{code}] SKIP — no source image at {CATALOG}/{code}-3-4/hero/door.jpg")
            summary.append({"code": code, "status": "skipped_no_source"})
            continue

        existing = already_onboarded(store, code)
        if existing and not args.force:
            print(f"[{code}] SKIP — already onboarded (project {existing.id})")
            summary.append({"code": code, "status": "skipped_exists", "project_id": existing.id})
            continue

        upload_bytes = src.read_bytes()
        if existing and args.force:
            print(f"[{code}] RE-ONBOARDING in place (project {existing.id})…", flush=True)
            proj = existing
        else:
            print(f"[{code}] onboarding ({spec['door_style']})…", flush=True)
            proj = store.create(
                name=f"{code} Thermofoil Cabinet Door",
                product_type="Cabinet Door",
                material_type="rtf",
            )
        store.update(
            proj.id, door_style=spec["door_style"], corner_style="sharp",
            style_notes=spec["notes"], selected_swatches=palette,
        )
        store.save_upload(proj.id, f"{code}.jpg", upload_bytes)

        res = onboard_replica(
            store, proj.id, key, upload_bytes,
            attempt_cap=args.cap, min_score=3, spend=spend,
            allow_maple=False,  # RTF: a maple render would look like wood (D-009)
        )
        row = asdict(res)
        row["project_id"] = proj.id
        summary.append(row)
        tag = "READY" if res.status == QUEUED_READY else res.status.upper()
        print(f"[{code}] {tag} — {res.attempts} attempt(s), "
              f"best min-score {res.best_min_score}, project {proj.id} "
              f"(spent ${spend.spent_usd:.2f})", flush=True)

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2))
    print(f"\nRun complete. Total spend ${spend.spent_usd:.2f}. Summary → {args.summary}")


if __name__ == "__main__":
    main()
