"""Structured per-door specs for wood cabinet doors.

Single source of truth for wood door structure (style, panel type, frame width,
joint), derived from catalog descriptions by scripts/classify_wood_doors.py and
reviewed by the operator. Replaces the unreliable catalog-folder->style rule.
"""

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WOOD_SPECS_PATH = Path("docs/sales/data/wood_door_specs.json")

# stiles at/under this read as a thin "skinny shaker" frame; standard shaker
# stiles run ~2.25-3"
THIN_FRAME_MAX_IN = 2.25

_PANELS = {"flat", "raised", "slab", "louver", "beadboard"}


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
        door_style = row.get("door_style")
        if not door_style or not isinstance(door_style, str):
            raise ValueError(
                f"wood_door_specs.json: {name!r} has invalid door_style: {door_style!r}"
            )
        panel = row.get("panel")
        if panel not in _PANELS:
            raise ValueError(
                f"wood_door_specs.json: {name!r} has invalid panel: {panel!r}"
            )
        out[name] = WoodSpec(
            door_style=door_style,
            panel=panel,
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
        if spec.frame_width_in <= THIN_FRAME_MAX_IN:
            parts.append(
                f"The frame is exactly {spec.frame_width_in:g} inches wide — thin; "
                "reproduce the frame at that exact width and do NOT widen it."
            )
        else:
            parts.append(
                f"The frame is exactly {spec.frame_width_in:g} inches wide — "
                "reproduce the frame at that exact width, neither wider nor narrower."
            )
    return " ".join(parts)
