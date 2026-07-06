#!/usr/bin/env python
"""Batch-onboard WOOD cabinet doors to queued, judge-clean replicas.

Wood mirrors the RTF onboarding flow, with three differences:
- material_type="wood" and the 38 wood swatches;
- door_style + conditioning notes come from docs/sales/data/wood_door_specs.json
  (see backend/wood_specs.py), not from the catalog folder — the Decore
  "raised-panel" folder groups by frame construction, not panel raise, so it
  can't be trusted as a style signal on its own;
- the maple-learn rung is re-enabled (a real wood-grain anchor trick for wood,
  unlike RTF where it wrongly rendered wood).

Usage:
    uv run python scripts/onboard_wood.py [--only NAME] [--cap 5] [--ceiling 6.0]
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
from backend.onboarding import QUEUED_READY, Spend, onboard_replica  # noqa: E402
from backend.state import ProjectStore  # noqa: E402
from backend.wood_specs import WoodSpec, learn_notes, load_wood_specs  # noqa: E402


def door_spec(name: str, specs: dict[str, "WoodSpec"]) -> tuple[str | None, str]:
    """(door_style, conditioning notes) for a door from the spec file.
    Returns (None, "") when the door isn't in the spec — caller skips it."""
    spec = specs.get(name)
    if spec is None:
        return None, ""
    return spec.door_style, learn_notes(spec)


CATALOG = Path.home() / "Desktop" / "Xpress" / "Decore Catalog" / "wood"
DEFAULT_SUMMARY = Path("output/.onboard/wood_replicas_summary.json")

# First batch — top uncovered wood cabinet doors by sales.
# ("Custom Cabinet Door" is skipped: it's a catch-all, not an onboardable profile.)
DOORS = [
    "Tacoma", "Journey", "Camden", "Newbury", "Chapman",       # batch 1
    "Talbot", "Tuscany", "Cabrillo", "Laredo", "Terracina",    # batch 2
    "Dylan", "Sheffield", "Sullivan", "Executive", "Fiesta",   # batch 3
]

# Catalog profile folders to search for a door's hero image.
_PROFILE_STYLE = [("raised-panel", "raised_panel"), ("inset-panel", "recessed_panel")]


def resolve(name: str) -> Path | None:
    """Locate a wood door's hero image in the catalog (either profile folder)."""
    lname = name.lower()
    for sub, _ in _PROFILE_STYLE:
        base = CATALOG / sub
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir():
                dn = d.name.lower()
                if dn == lname or dn.startswith(lname + "-") or dn.startswith(lname + " "):
                    door = d / "hero" / "door.jpg"
                    if door.exists():
                        return door
    return None


def already_onboarded(store: ProjectStore, name: str):
    """A prior WOOD CABINET DOOR project for this door with a learned replica.
    Scoped to cabinet doors so a same-named drawer-front project isn't matched.
    """
    for p in store.list_projects():
        if (name.lower() in p.name.lower()
                and getattr(p, "product_type", "") == "Cabinet Door"
                and getattr(p, "material_type", "") == "wood"
                and getattr(p, "has_signature", False)):
            return p
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="onboard just this door name")
    ap.add_argument("--cap", type=int, default=5, help="max re-learn attempts per door")
    ap.add_argument("--ceiling", type=float, default=6.0, help="run spend ceiling (USD)")
    ap.add_argument("--force", action="store_true", help="re-onboard even if already done")
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    palette = [str(p) for p in get_swatch_files("wood")]  # full wood palette for later variants
    spend = Spend(ceiling_usd=args.ceiling)
    specs = load_wood_specs()

    summary = []
    for name in DOORS:
        if args.only and name != args.only:
            continue
        src = resolve(name)
        if src is None:
            print(f"[{name}] SKIP — no source image in the wood catalog")
            summary.append({"code": name, "status": "skipped_no_source"})
            continue
        style, notes = door_spec(name, specs)
        if style is None:
            print(f"[{name}] SKIP — no entry in wood_door_specs.json (classify first)")
            summary.append({"code": name, "status": "skipped_no_spec"})
            continue

        existing = already_onboarded(store, name)
        if existing and not args.force:
            print(f"[{name}] SKIP — already onboarded (project {existing.id})")
            summary.append({"code": name, "status": "skipped_exists", "project_id": existing.id})
            continue

        upload = src.read_bytes()
        if existing and args.force:
            print(f"[{name}] RE-ONBOARDING in place (project {existing.id}) [{style}]…", flush=True)
            proj = existing
        else:
            print(f"[{name}] onboarding [{style}]…", flush=True)
            proj = store.create(name=f"{name} Cabinet Door", product_type="Cabinet Door",
                                material_type="wood")
        store.update(proj.id, door_style=style, corner_style="sharp",
                     style_notes=notes, selected_swatches=palette)
        store.save_upload(proj.id, f"{name}.jpg", upload)

        res = onboard_replica(store, proj.id, key, upload, attempt_cap=args.cap,
                              min_score=3, spend=spend, allow_maple=True)
        row = asdict(res)
        row["project_id"] = proj.id
        row["style"] = style
        summary.append(row)
        tag = "READY" if res.status == QUEUED_READY else res.status.upper()
        print(f"[{name}] {tag} — {res.attempts} attempt(s), best min-score "
              f"{res.best_min_score}, project {proj.id} (spent ${spend.spent_usd:.2f})", flush=True)

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2))
    print(f"\nRun complete. Total spend ${spend.spent_usd:.2f}. Summary → {args.summary}")


if __name__ == "__main__":
    main()
