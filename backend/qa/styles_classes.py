"""Route a door_style key to a geometry measurement class (the single routing truth).

Kept separate from policy and eval so both share one mapping. Three classes:

- ``frame_standard`` — rectangular frame-and-(flat/recessed)-panel doors with
  ordinary frame widths. Stiles, rails, and the recessed-panel boundary are
  cleanly measurable as structural ratios.
- ``frame_narrow`` — the skinny-shaker family (~7/8"–1.25" frames). Same
  geometry, but a distinct threshold class because the frame occupies a much
  smaller fraction of the door.
- ``excluded`` — anything the deterministic core cannot measure reliably:
  slabs, bevels, tongue-and-groove planks, louvers, radius/arched panels,
  raised (beveled) panels, glass, and unknown/minimal test styles.

Fail-safe: every catalog key is mapped explicitly, and any unknown or ``None``
style resolves to ``excluded`` so the geometry gate never runs on something it
cannot trust. If a catalog key is added without a mapping here,
``test_every_catalog_key_is_mapped`` fails.
"""

FRAME_STANDARD = "frame_standard"
FRAME_NARROW = "frame_narrow"
EXCLUDED = "excluded"

# Explicit mapping for every key in backend/styles/catalog.py.
STYLE_CLASSES: dict[str, str] = {
    # --- frame_standard: rectangular framed recessed/flat panel doors ---
    "minimal": FRAME_STANDARD,
    "recessed_panel": FRAME_STANDARD,
    "terracina": FRAME_STANDARD,
    "shaker_cope_stick": FRAME_STANDARD,
    "shaker_flat_step": FRAME_STANDARD,
    "recessed_panel_center_stile": FRAME_STANDARD,
    "recessed_panel_applied_molding": FRAME_STANDARD,
    "graham": FRAME_STANDARD,
    "hayes": FRAME_STANDARD,
    "mitered_recessed_panel_applied_molding": FRAME_STANDARD,
    "shaker_bevel": FRAME_STANDARD,  # standard shaker; edge merely eased
    "shaker": FRAME_STANDARD,
    "rtf_drawer_shaker_shallow": FRAME_STANDARD,
    "rtf_drawer_shaker": FRAME_STANDARD,
    "drawer_recessed_panel": FRAME_STANDARD,
    "drawer_alpine": FRAME_STANDARD,  # flat rectangular applied trim, recessed panel
    "drawer_durango": FRAME_STANDARD,  # framed recessed drawer (wide stiles)
    "drawer_durango_minimal": FRAME_STANDARD,
    "drawer_shaker": FRAME_STANDARD,
    "drawer_routed": FRAME_STANDARD,  # single piece routed to a frame+panel face
    # --- frame_narrow: skinny-shaker family (~7/8"–1.25" frames) ---
    "mitered_flat_panel": FRAME_NARROW,  # "Skinny Shaker Mitered"
    "rtf_drawer_shaker_skinny": FRAME_NARROW,  # 7/8" frame
    "drawer_journey": FRAME_NARROW,  # ~1" skinny shaker mitered
    # --- excluded: unmeasurable construction or unknown/minimal test styles ---
    "davenport": EXCLUDED,  # tongue-and-groove plank panel + beads
    "rtf_minimal": EXCLUDED,  # minimal test, unknown structure
    "vienna": EXCLUDED,  # slab veneer with bead molding
    "mission": EXCLUDED,  # cathedral arch (radius/arched)
    "recessed_panel_arched": EXCLUDED,  # arched recessed panel — not a measurable rectangle
    "raised_panel": EXCLUDED,  # raised/beveled panel
    "raised_panel_radius": EXCLUDED,  # raised panel, radius corners
    "solid_plank": EXCLUDED,  # solid slab
    "louver": EXCLUDED,  # louver slats
    "rtf_drawer_minimal": EXCLUDED,  # minimal test, unknown structure
    "rtf_drawer_bevel": EXCLUDED,  # single-slab bevel
    "drawer_raised_panel": EXCLUDED,  # raised/beveled panel
    "drawer_raised_panel_radius": EXCLUDED,  # raised panel, radius corners
    "drawer_solid_plank": EXCLUDED,  # solid slab
    "drawer_harmony": EXCLUDED,  # raised rounded outer-edge profile
    "drawer_minimal": EXCLUDED,  # minimal test, unknown structure
}


def style_class(door_style: str | None) -> str:
    """Return the geometry class for a door_style. Unknown/None -> ``excluded``."""
    if not door_style:
        return EXCLUDED
    return STYLE_CLASSES.get(door_style, EXCLUDED)
