# Wood Onboarding Foundation — Pillar 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the wood driver's unreliable catalog-folder→style rule with a
per-door structured spec derived from each door's `product.json` description +
image, so styles are correct (plank/louver/shaker/raised/…) and the exact frame
width drives proportions.

**Architecture:** A checked-in data file `docs/sales/data/wood_door_specs.json`
is the single source of truth for wood door structure. A loader
(`backend/wood_specs.py`) parses it into `WoodSpec` records and builds a minimal
conditioning note from the frame width. `scripts/onboard_wood.py` reads specs via
the loader instead of the folder. A one-time classifier
(`scripts/classify_wood_doors.py`) produces the JSON from catalog descriptions +
images for operator review.

**Tech Stack:** Python 3.12, `uv`, pytest, ruff; `google-genai` (via existing
`DoorGenerator`/`genai.Client` pattern) for the classifier.

## Global Constraints

- Run everything with `uv run` (e.g. `uv run pytest`, `uv run python ...`).
- `door_style` values MUST be keys of the door-category entries in
  `backend/styles/catalog.py::STYLES`. Valid values: `davenport`, `rtf_minimal`,
  `minimal`, `recessed_panel`, `vienna`, `terracina`, `shaker_cope_stick`,
  `shaker_flat_step`, `recessed_panel_center_stile`,
  `recessed_panel_applied_molding`, `graham`, `hayes`,
  `mitered_recessed_panel_applied_molding`, `mitered_flat_panel`, `shaker_bevel`,
  `shaker`, `mission`, `raised_panel`, `raised_panel_radius`, `solid_plank`,
  `louver`, `recessed_panel_arched`.
- `panel` is one of: `flat`, `raised`, `slab`, `louver`, `beadboard`.
- Minimal-prompt rule: conditioning notes carry *specific facts* (a frame width
  number), never verbose marketing prose.
- Read `GEMINI_API_KEY` from `.env` via `scripts/_onboard_common.read_api_key`.
- Lint clean: `uv run ruff check backend/ scripts/ tests/`.

---

### Task 1: WoodSpec loader + frame-width conditioning note

**Files:**
- Create: `backend/wood_specs.py`
- Create: `docs/sales/data/wood_door_specs.json` (seed with a few real rows)
- Test: `tests/test_wood_specs.py`

**Interfaces:**
- Produces:
  - `@dataclass WoodSpec(door_style: str, panel: str, frame_width_in: float | None, joint: str | None, arched: bool, notes: str)`
  - `load_wood_specs(path: Path = DEFAULT_WOOD_SPECS_PATH) -> dict[str, WoodSpec]` — maps door name → WoodSpec; missing file → `{}`.
  - `learn_notes(spec: WoodSpec) -> str` — minimal conditioning string; includes the exact frame width when present.
  - `DEFAULT_WOOD_SPECS_PATH = Path("docs/sales/data/wood_door_specs.json")`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_wood_specs.py
from pathlib import Path

from backend.wood_specs import WoodSpec, load_wood_specs, learn_notes


def _write(tmp_path, data):
    import json
    p = tmp_path / "wood_door_specs.json"
    p.write_text(json.dumps(data))
    return p


def test_load_parses_rows(tmp_path):
    p = _write(tmp_path, {
        "Newbury": {"door_style": "shaker", "panel": "flat", "frame_width_in": 2.0,
                    "joint": "miter", "arched": False, "notes": "skinny shaker"},
        "Tacoma": {"door_style": "solid_plank", "panel": "slab", "frame_width_in": None,
                   "joint": None, "arched": False, "notes": "solid plank"},
    })
    specs = load_wood_specs(p)
    assert specs["Newbury"] == WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker")
    assert specs["Tacoma"].frame_width_in is None
    assert specs["Tacoma"].door_style == "solid_plank"


def test_missing_file_is_empty(tmp_path):
    assert load_wood_specs(tmp_path / "nope.json") == {}


def test_learn_notes_includes_exact_frame_width():
    note = learn_notes(WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker"))
    assert "2" in note and "inch" in note.lower()
    # no frame width -> no frame sentence
    assert "frame is exactly" not in learn_notes(
        WoodSpec("solid_plank", "slab", None, None, False, "plank"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wood_specs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.wood_specs'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/wood_specs.py
"""Structured per-door specs for wood cabinet doors.

Single source of truth for wood door structure (style, panel type, frame width,
joint), derived from catalog descriptions by scripts/classify_wood_doors.py and
reviewed by the operator. Replaces the unreliable catalog-folder->style rule.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WOOD_SPECS_PATH = Path("docs/sales/data/wood_door_specs.json")


@dataclass
class WoodSpec:
    door_style: str
    panel: str  # flat | raised | slab | louver | beadboard
    frame_width_in: float | None
    joint: str | None  # miter | butt | cope | None
    arched: bool
    notes: str


def load_wood_specs(path: Path = DEFAULT_WOOD_SPECS_PATH) -> dict[str, WoodSpec]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    out: dict[str, WoodSpec] = {}
    for name, row in data.items():
        out[name] = WoodSpec(
            door_style=row["door_style"],
            panel=row["panel"],
            frame_width_in=row.get("frame_width_in"),
            joint=row.get("joint"),
            arched=bool(row.get("arched", False)),
            notes=row.get("notes", ""),
        )
    return out


def learn_notes(spec: WoodSpec) -> str:
    """Minimal conditioning: the exact frame width is the specific fact that
    beats the model's fatten-the-frame prior. No marketing prose."""
    parts: list[str] = []
    if spec.frame_width_in is not None:
        parts.append(
            f"The frame is exactly {spec.frame_width_in:g} inches wide — thin; "
            "reproduce the frame at that exact width and do NOT widen it."
        )
    return " ".join(parts)
```

- [ ] **Step 4: Seed the data file with a few real rows**

```json
{
  "Newbury": {"door_style": "shaker", "panel": "flat", "frame_width_in": 2.0, "joint": "miter", "arched": false, "notes": "skinny shaker, solid panel"},
  "Tacoma": {"door_style": "solid_plank", "panel": "slab", "frame_width_in": null, "joint": null, "arched": false, "notes": "solid plank"},
  "Talbot": {"door_style": "louver", "panel": "louver", "frame_width_in": 2.25, "joint": null, "arched": false, "notes": "louver-look on solid panel"},
  "Camden": {"door_style": "recessed_panel", "panel": "beadboard", "frame_width_in": null, "joint": "butt", "arched": false, "notes": "beaded panel, butt-joint frame"},
  "Sheffield": {"door_style": "raised_panel", "panel": "raised", "frame_width_in": null, "joint": "miter", "arched": false, "notes": "miter joint, raised panel"}
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_wood_specs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/wood_specs.py tests/test_wood_specs.py docs/sales/data/wood_door_specs.json
git commit -m "feat(wood): WoodSpec loader + frame-width conditioning note"
```

---

### Task 2: onboard_wood reads the spec file (drop folder→style + OVERRIDES)

**Files:**
- Modify: `scripts/onboard_wood.py`
- Test: `tests/test_onboard_wood_spec.py`

**Interfaces:**
- Consumes: `backend.wood_specs.load_wood_specs`, `learn_notes`, `WoodSpec`.
- Produces: `door_spec(name, specs) -> tuple[str, str]` returning `(door_style, notes)` for a door, using the spec file (not the folder). `resolve(name)` keeps finding the source image + returns only the path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboard_wood_spec.py
import importlib.util
from pathlib import Path

from backend.wood_specs import WoodSpec

_spec = importlib.util.spec_from_file_location(
    "onboard_wood", Path(__file__).resolve().parents[1] / "scripts" / "onboard_wood.py")
onboard_wood = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(onboard_wood)


def test_door_spec_uses_spec_file_not_folder():
    specs = {"Tacoma": WoodSpec("solid_plank", "slab", None, None, False, "plank"),
             "Newbury": WoodSpec("shaker", "flat", 2.0, "miter", False, "skinny shaker")}
    style, notes = onboard_wood.door_spec("Tacoma", specs)
    assert style == "solid_plank"       # folder says raised-panel; spec wins
    assert notes == ""                  # no frame width -> no note
    style2, notes2 = onboard_wood.door_spec("Newbury", specs)
    assert style2 == "shaker"
    assert "2 inches" in notes2


def test_door_spec_missing_entry_returns_none_style():
    style, notes = onboard_wood.door_spec("Unlisted", {})
    assert style is None and notes == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_onboard_wood_spec.py -v`
Expected: FAIL with `AttributeError: module 'onboard_wood' has no attribute 'door_spec'`

- [ ] **Step 3: Add the `door_spec` helper and remove OVERRIDES**

In `scripts/onboard_wood.py`, add the import and helper near the top (after the
existing imports):

```python
from backend.wood_specs import WoodSpec, learn_notes, load_wood_specs  # noqa: E402


def door_spec(name: str, specs: dict[str, "WoodSpec"]) -> tuple[str | None, str]:
    """(door_style, conditioning notes) for a door from the spec file.
    Returns (None, "") when the door isn't in the spec — caller skips it."""
    spec = specs.get(name)
    if spec is None:
        return None, ""
    return spec.door_style, learn_notes(spec)
```

Delete the `_NARROW_SHAKER_NOTE` constant and the entire `OVERRIDES` dict (the
spec file subsumes them).

- [ ] **Step 4: Rewire `main()` to use `door_spec` + `resolve` for the image only**

Change `resolve(name)` to return just the source path (drop the folder-derived
style), and in `main()` replace the style/notes derivation:

```python
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
```

In `main()`, after loading the store, load specs once:

```python
    specs = load_wood_specs()
```

Replace the per-door body's `src, style = resolve(name)` block and the
`store.update(..., door_style=style, style_notes="")` call with:

```python
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
        ...
        store.update(proj.id, door_style=style, corner_style="sharp",
                     style_notes=notes, selected_swatches=palette)
```

(Keep the existing `already_onboarded`, `create`/`--force`, `save_upload`, and
`onboard_replica(... allow_maple=True)` logic unchanged.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_onboard_wood_spec.py tests/test_wood_specs.py -v`
Expected: PASS

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check scripts/onboard_wood.py backend/wood_specs.py
git add scripts/onboard_wood.py tests/test_onboard_wood_spec.py
git commit -m "feat(wood): drive door_style + frame note from wood_door_specs.json"
```

---

### Task 3: The one-time classifier

**Files:**
- Create: `scripts/classify_wood_doors.py`
- Test: `tests/test_classify_wood_doors.py`

**Interfaces:**
- Consumes: `scripts/_onboard_common.read_api_key`; `genai.Client` (via
  `google.genai`); the door-category `STYLES` keys.
- Produces:
  - `build_prompt(name: str, description: str) -> str`
  - `parse_spec(text: str) -> dict` — parses the model's JSON reply into a row for
    `wood_door_specs.json`; raises `ValueError` on an invalid `door_style`/`panel`.
  - `classify_door(client, name, description, image_path) -> dict` — one model call
    with retry, returns the parsed row.
  - a `main()` that walks the wood catalog and writes/updates
    `docs/sales/data/wood_door_specs.json`.

- [ ] **Step 1: Write the failing test (pure functions, fake client)**

```python
# tests/test_classify_wood_doors.py
import importlib.util
import pytest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "classify_wood_doors", Path(__file__).resolve().parents[1] / "scripts" / "classify_wood_doors.py")
cwd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cwd)


def test_prompt_names_the_door_and_lists_valid_styles():
    p = cwd.build_prompt("Talbot", "louver-like detailing... 2-1/4\" wide frame")
    assert "Talbot" in p and "louver" in p
    assert "solid_plank" in p and "raised_panel" in p  # enum offered to the model


def test_parse_valid_row():
    row = cwd.parse_spec('{"door_style":"louver","panel":"louver",'
                         '"frame_width_in":2.25,"joint":null,"arched":false,"notes":"louver"}')
    assert row["door_style"] == "louver" and row["frame_width_in"] == 2.25


def test_parse_rejects_bad_style():
    with pytest.raises(ValueError):
        cwd.parse_spec('{"door_style":"not_a_style","panel":"flat","arched":false,"notes":""}')


def test_parse_rejects_bad_panel():
    with pytest.raises(ValueError):
        cwd.parse_spec('{"door_style":"shaker","panel":"weird","arched":false,"notes":""}')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_classify_wood_doors.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement the classifier**

```python
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

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from _onboard_common import read_api_key  # noqa: E402
from backend.styles.catalog import STYLES  # noqa: E402
from backend.wood_specs import DEFAULT_WOOD_SPECS_PATH  # noqa: E402

CATALOG = Path.home() / "Desktop" / "Xpress" / "Decore Catalog" / "wood"
DOOR_STYLES = sorted(k for k, v in STYLES.items() if v.get("category") == "door")
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
            time.sleep(2 ** attempt)
    raise RuntimeError(f"classify failed for {name}: {last}")


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
    args = ap.parse_args()

    client = genai.Client(api_key=read_api_key())
    out = {}
    if args.out.exists():
        out = json.loads(args.out.read_text())
    for name, desc, door in _iter_catalog():
        if args.only and name != args.only:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_classify_wood_doors.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check scripts/classify_wood_doors.py
git add scripts/classify_wood_doors.py tests/test_classify_wood_doors.py
git commit -m "feat(wood): one-time description+image door classifier"
```

---

### Task 4: Run the classifier, review specs, re-onboard mis-styled doors

This task spends tokens and needs the operator — it produces the real data and
corrects the doors already onboarded with wrong styles.

- [ ] **Step 1: Full suite green first**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 2: Classify the golden 5 and confirm they're right**

Run:
```bash
for d in Tacoma Talbot Camden Sheffield Newbury; do
  uv run python scripts/classify_wood_doors.py --only "$d"
done
```
Expected stdout: Tacoma→solid_plank/slab, Talbot→louver/louver (frame 2.25),
Camden→beadboard panel, Sheffield→raised_panel/raised, Newbury→shaker/flat
(frame 2.0). If any is wrong, fix `build_prompt` wording and re-run.

- [ ] **Step 3: Classify the full wood catalog**

Run: `uv run python scripts/classify_wood_doors.py`
Then **operator reviews `docs/sales/data/wood_door_specs.json`** and hand-corrects
any misreads (it's plain JSON). Commit the reviewed file:
```bash
git add docs/sales/data/wood_door_specs.json
git commit -m "data(wood): classified + reviewed wood door specs"
```

- [ ] **Step 4: Re-onboard the doors whose folder-derived style was wrong**

For each door the spec now styles differently than it was onboarded (at minimum
Tacoma, Talbot, Camden, Journey, Dylan — and any others surfaced in review):
```bash
uv run python scripts/onboard_wood.py --only Tacoma --force
```
Then reload the dev server (`touch backend/app.py`) and eyeball the replica in
the Review tab. These now use the correct style + exact frame-width note.

- [ ] **Step 5: Full suite + lint, final commit**

Run: `uv run pytest -q && uv run ruff check backend/ scripts/ tests/`
Expected: PASS / All checks passed.
```bash
git commit -am "chore(wood): re-onboard mis-styled doors on corrected specs" || true
```

---

## Self-Review

**Spec coverage (Pillar 1 of the design):**
- "Stop deriving from the folder / spec file is source of truth" → Task 1 (loader)
  + Task 2 (driver reads it).
- "LLM classifier from description + image → structured spec" → Task 3.
- "frame_width_in becomes a specific-fact conditioning line" → Task 1 `learn_notes`
  + Task 2 wiring.
- "classify ALL wood doors; flag already-approved mis-styled ones" → Task 4.
- "OVERRIDES removed / subsumed" → Task 2 Step 3.
Pillar 2 (canonical-door species judge) is a SEPARATE plan — not in scope here.

**Placeholder scan:** none — every code/step has concrete content and commands.

**Type consistency:** `WoodSpec(door_style, panel, frame_width_in, joint, arched,
notes)` used identically in Tasks 1–2; `door_spec()` returns `(str|None, str)` in
Task 2 test and impl; `parse_spec()` returns the same dict shape written to the
JSON and read by `load_wood_specs`.
