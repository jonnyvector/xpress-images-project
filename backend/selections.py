"""Swatch-selection resolution: selected swatch keys -> generation selections.

Owns the one resolver used by the worker (generation), the generation gate
(GT-002 counts RESOLVED selections), and the cost estimate — so all three
always agree on what will actually be generated. Resolution is tolerant:
unresolvable swatches are silently dropped, virtual entries borrow a real
swatch via ``swatch_key``, and description-only entries generate from text.

Not responsible for: generation dispatch (worker) or gate decisions (routers).
"""

from pathlib import Path

from backend.materials import (
    get_swatch_files,
    load_material_types,
    normalize_material_key,
    resolve_swatch_path,
    swatch_name_from_path,
)

# Styles where the product is a single flat surface (no separate frame and panel).
# These use flat_panel_description from wood_types.json when available.
FLAT_PANEL_STYLES = {"vienna", "solid_plank", "drawer_solid_plank", "rtf_drawer_bevel"}


def _get_material_description(
    swatch_path: Path,
    material_types: dict[str, dict],
    door_style: str | None = None,
) -> str | None:
    key = normalize_material_key(swatch_path.stem)
    wt = material_types.get(key)
    if not wt:
        return None
    # Use flat-panel-specific description when the style has no frame+panel
    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
        return wt["flat_panel_description"]
    return wt.get("description") or None


def build_selections(
    selected_swatches: list[str],
    door_style: str | None = None,
    material_type: str = "wood",
) -> list[dict]:
    """Build the selections list from selected swatch keys."""
    wood_types = load_material_types(material_type)
    all_swatch_files = get_swatch_files(material_type)
    selections: list[dict] = []
    for p in selected_swatches:
        if p.startswith("virtual:"):
            key = p[8:]
            wt = wood_types.get(key, {})
            borrowed = resolve_swatch_path(wt.get("swatch_key", ""), all_swatch_files)
            desc = (
                _get_material_description(borrowed, wood_types, door_style)
                if borrowed
                else wt.get("description")
            )
            selections.append(
                {
                    "wood_name": wt.get("name", key),
                    "swatch_path": borrowed,
                    "wood_description": desc,
                    "reference_image": None,
                }
            )
        else:
            swatch_path = Path(p)
            # If the stored value doesn't exist as a file, resolve it as a key
            if not swatch_path.exists():
                key = normalize_material_key(p)
                # Check if it's a virtual wood type (has swatch_key in wood_types.json)
                wt = wood_types.get(key, {})
                if wt.get("swatch_key"):
                    borrowed = resolve_swatch_path(wt["swatch_key"], all_swatch_files)
                    desc = wt.get("description")
                    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
                        desc = wt["flat_panel_description"]
                    selections.append(
                        {
                            "wood_name": wt.get("name", key),
                            "swatch_path": borrowed,
                            "wood_description": desc,
                            "reference_image": None,
                        }
                    )
                    continue
                # Description-only entry (no swatch_key, no physical file)
                if wt.get("description") and not resolve_swatch_path(key, all_swatch_files):
                    desc = wt.get("description")
                    if door_style in FLAT_PANEL_STYLES and wt.get("flat_panel_description"):
                        desc = wt["flat_panel_description"]
                    selections.append(
                        {
                            "wood_name": wt.get("name", key),
                            "swatch_path": None,
                            "wood_description": desc,
                            "reference_image": None,
                        }
                    )
                    continue
                resolved = resolve_swatch_path(key, all_swatch_files)
                if not resolved:
                    resolved = resolve_swatch_path(
                        normalize_material_key(swatch_path.stem),
                        all_swatch_files,
                    )
                if resolved:
                    swatch_path = resolved
                else:
                    continue  # skip missing swatches
            key_lookup = normalize_material_key(swatch_path.stem)
            wt = wood_types.get(key_lookup, {})
            selections.append(
                {
                    "wood_name": wt.get("name", swatch_name_from_path(swatch_path)),
                    "swatch_path": swatch_path,
                    "wood_description": _get_material_description(
                        swatch_path, wood_types, door_style,
                    ),
                    "reference_image": None,
                    "hex": wt.get("hex"),
                    "rtf_finish": wt.get("finish"),
                }
            )
    return selections
