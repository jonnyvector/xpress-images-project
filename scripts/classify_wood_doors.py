#!/usr/bin/env python
"""One-time classifier: catalog description + image -> structured wood door spec.

Writes/updates docs/sales/data/wood_door_specs.json for operator review. The
catalog folder is NOT trusted for style; the description + image are.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from backend.styles.catalog import STYLES  # noqa: E402
from backend.wood_specs import DEFAULT_WOOD_SPECS_PATH  # noqa: E402

CATALOG = Path.home() / "Desktop" / "Xpress" / "Decore Catalog" / "wood"
_TEST_STYLES = {"minimal", "rtf_minimal"}
DOOR_STYLES = sorted(
    k for k, v in STYLES.items()
    if v.get("category") == "door" and k not in _TEST_STYLES
)
PANELS = ["flat", "raised", "slab", "louver", "beadboard"]
MODEL = "gemini-3.1-pro-preview"


def build_prompt(name: str, description: str) -> str:
    return (
        f"You are classifying a cabinet door named {name!r} for a generation "
        "pipeline. Use BOTH the manufacturer description and the image. Do NOT "
        "trust any folder name.\n\n"
        f"DESCRIPTION: {description}\n\n"
        "Return ONLY a JSON object with these fields:\n"
        f"  door_style: one of {DOOR_STYLES}\n"
        f"  panel: one of {PANELS}\n"
        "  frame_width_in: the frame/stile width in inches as a number if the "
        "description states it (e.g. '2\" frame width' -> 2.0), else null\n"
        "  joint: one of \"miter\", \"butt\", \"cope\", or null\n"
        "  arched: true if the top rail/panel is an arch or cathedral, else false\n"
        "  notes: a short phrase (max 8 words) capturing the defining detail\n"
        "Pick the door_style that best matches the actual construction: a solid "
        "plank/slab is solid_plank, a louvered face is louver, a flat recessed "
        "panel is shaker (or shaker_bevel if it has a small inner bevel), a raised "
        "field is raised_panel, an arched recessed panel is recessed_panel_arched."
    )


def parse_spec(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].removeprefix("json").strip()
    row = json.loads(text)
    if row.get("door_style") not in DOOR_STYLES:
        raise ValueError(f"invalid door_style: {row.get('door_style')!r}")
    if row.get("panel") not in PANELS:
        raise ValueError(f"invalid panel: {row.get('panel')!r}")
    return {
        "door_style": row["door_style"],
        "panel": row["panel"],
        "frame_width_in": row.get("frame_width_in"),
        "joint": row.get("joint"),
        "arched": bool(row.get("arched", False)),
        "notes": str(row.get("notes", ""))[:60],
    }


def classify_door(client, name: str, description: str, image_path: Path) -> dict:
    parts = [
        types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg"),
        types.Part.from_text(text=build_prompt(name, description)),
    ]
    contents = [types.Content(role="user", parts=parts)]
    last = ""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=MODEL, contents=contents)
            return parse_spec(resp.text or "")
        except Exception as exc:  # noqa: BLE001 - retry then re-raise
            last = str(exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"classify failed for {name}: {last}")


def should_skip(name: str, existing: dict, force: bool) -> bool:
    """Preserve operator-edited rows on re-run unless --force is passed."""
    return name in existing and not force


def _iter_catalog():
    for sub in ("raised-panel", "inset-panel"):
        base = CATALOG / sub
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            door = d / "hero" / "door.jpg"
            prod = d / "product.json"
            if door.exists() and prod.exists():
                meta = json.loads(prod.read_text())
                yield meta.get("name", d.name), meta.get("description", ""), door


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="classify just this door name")
    ap.add_argument("--out", type=Path, default=DEFAULT_WOOD_SPECS_PATH)
    ap.add_argument(
        "--force", action="store_true",
        help="re-classify doors already present in the spec file (default: preserve them)",
    )
    args = ap.parse_args()

    client = genai.Client(api_key=read_api_key())
    out = {}
    if args.out.exists():
        out = json.loads(args.out.read_text())
    for name, desc, door in _iter_catalog():
        if args.only and name != args.only:
            continue
        if should_skip(name, out, args.force):
            print(f"{name}: skip (already in spec; --force to reclassify)")
            continue
        try:
            out[name] = classify_door(client, name, desc, door)
            print(f"{name}: {out[name]['door_style']} / {out[name]['panel']}"
                  f" frame={out[name]['frame_width_in']}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAILED — {exc}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"\nWrote {len(out)} specs -> {args.out}  (REVIEW before onboarding)")


if __name__ == "__main__":
    main()
