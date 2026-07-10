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

Doors to onboard are selected from the spec file, not a hardcoded list:
--only NAME (one door), --doors "A,B,C" (an explicit set), or --all (every
door in wood_door_specs.json). A door still needs a resolvable catalog image.

Usage:
    uv run python scripts/onboard_wood.py --only NAME   [--force] [--cap 5]
    uv run python scripts/onboard_wood.py --doors "Tacoma,Talbot,Cabrillo" --force
    uv run python scripts/onboard_wood.py --all --ceiling 40
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


def canonical_name(name: str, specs: dict[str, "WoodSpec"]) -> str:
    """Fold a requested door name onto its spec key case-insensitively.

    Rosters are often built from stored PROJECT names, which are lowercase
    ("indiana"), while spec keys and catalog folders are capitalized
    ("Indiana"). Without this, a lowercase name silently SKIPs on
    door_spec's exact-match lookup (the 2026-07-09 casing gremlin, which
    dropped 7 doors mid-batch). Returns the spec's canonical casing when a
    case-insensitive match exists, else the name unchanged."""
    if name in specs:
        return name
    lower = name.lower()
    for key in specs:
        if key.lower() == lower:
            return key
    return name


CATALOG = Path.home() / "Desktop" / "Xpress" / "Decore Catalog" / "wood"
DEFAULT_SUMMARY = Path("output/.onboard/wood_replicas_summary.json")

# Catalog profile folders to search for a door's hero image.
_PROFILE_STYLE = [("raised-panel", "raised_panel"), ("inset-panel", "recessed_panel")]


def select_doors(spec_names, only=None, doors=None, all_=False) -> list[str]:
    """Which doors to onboard this run — exactly one selector must be given.
    --only NAME -> [NAME]; --doors "A, B" -> ["A","B"]; --all -> every spec
    name (sorted). Names needn't be in the spec here; main() skips ones without
    a spec entry or a source image."""
    if sum([bool(only), bool(doors), all_]) != 1:
        raise SystemExit("choose exactly one of --only, --doors, or --all")
    if all_:
        names = sorted(spec_names)
    elif only:
        names = [only]
    else:
        names = [d.strip() for d in doors.split(",") if d.strip()]
    names = list(dict.fromkeys(names))  # dedupe, keep order — never onboard a door twice per run
    if not names:
        raise SystemExit("no doors selected")
    return names


def _door_dirs(name: str, catalog: Path = CATALOG):
    """Catalog folders matching a door name, across both profile folders."""
    lname = name.lower()
    for sub, _ in _PROFILE_STYLE:
        base = catalog / sub
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir():
                dn = d.name.lower()
                if dn == lname or dn.startswith(lname + "-") or dn.startswith(lname + " "):
                    yield d


def resolve(name: str, catalog: Path = CATALOG) -> Path | None:
    """Locate a wood door's hero image in the catalog (either profile folder)."""
    for d in _door_dirs(name, catalog):
        door = d / "hero" / "door.jpg"
        if door.exists():
            return door
    return None


def resolve_profile(name: str, catalog: Path = CATALOG) -> Path | None:
    """Locate a door's cross-section drawing (the profile anchor), if any."""
    for d in _door_dirs(name, catalog):
        drawing = d / "profile" / "3d-profile.jpg"
        if drawing.exists():
            return drawing
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
    ap.add_argument("--doors", help="comma-separated door names to onboard")
    ap.add_argument("--all", action="store_true", help="onboard every door in the spec file")
    ap.add_argument("--cap", type=int, default=5, help="max re-learn attempts per door")
    ap.add_argument("--ceiling", type=float, default=6.0, help="run spend ceiling (USD)")
    ap.add_argument("--force", action="store_true", help="re-onboard even if already done")
    ap.add_argument("--respec", action="store_true",
                    help="re-extract the profile spec even if one is stored")
    ap.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    args = ap.parse_args()

    key = read_api_key()
    store = ProjectStore(persist_dir=Path("output/.projects"))
    palette = [str(p) for p in get_swatch_files("wood")]  # full wood palette for later variants
    spend = Spend(ceiling_usd=args.ceiling)
    specs = load_wood_specs()
    names = select_doors(list(specs), only=args.only, doors=args.doors, all_=args.all)

    summary = []
    for raw_name in names:
        # Canonicalize casing up front so resolve, door_spec, project naming
        # and already_onboarded all agree regardless of how the roster was built.
        name = canonical_name(raw_name, specs)
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

        profile = resolve_profile(name)
        profile_bytes = (profile.read_bytes() or None) if profile else None
        if profile_bytes is None:
            print(f"[{name}] note — no 3d-profile cross-section in catalog; "
                  "onboarding without anchor")

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
                     style_notes=notes, selected_swatches=palette,
                     profile_image_path=str(profile) if profile else None)
        store.save_upload(proj.id, f"{name}.jpg", upload)

        if args.respec:
            store.update(proj.id, profile_spec=None)

        res = onboard_replica(store, proj.id, key, upload, attempt_cap=args.cap,
                              min_score=3, spend=spend, allow_maple=True,
                              profile_bytes=profile_bytes,
                              lean_notes=notes)  # lean tail: spec width note only (D-012)
        row = asdict(res)
        row["project_id"] = proj.id
        row["style"] = style
        summary.append(row)
        tag = "READY" if res.status == QUEUED_READY else res.status.upper()
        print(f"[{name}] {tag} — {res.attempts} attempt(s), best min-score "
              f"{res.best_min_score}, project {proj.id} (spent ${spend.spent_usd:.2f})", flush=True)
        if res.defects:
            print(f"[{name}]   defects: {'; '.join(res.defects[:5])}", flush=True)

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2))
    print(f"\nRun complete. Total spend ${spend.spent_usd:.2f}. Summary → {args.summary}")


if __name__ == "__main__":
    main()
