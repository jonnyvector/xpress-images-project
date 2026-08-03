"""Palette arithmetic for coverage: expected colours vs. generated colours.

Advisory only. The result is evidence shown to the operator at sign-off; it
never decides coverage. "Expected" is a starting set to subtract from, not a
completion target — some styles legitimately skip colours.
"""

from backend.materials import load_material_types


def full_palette(material: str) -> list[str]:
    """Every colour name defined for a material, sorted.

    Includes description-only entries that have no swatch file, because those
    still generate.
    """
    types = load_material_types(material)
    return sorted({(wt.get("name") or key) for key, wt in types.items()})


def distinct_generated(project) -> set[str]:
    """Distinct colour names present in a project's results.

    Distinct, not len(results): re-attempts leave duplicates behind, so a raw
    count reads complete while colours are missing (AP768: 45 results, 43
    colours).
    """
    if project is None:
        return set()
    return {r.wood_name for r in project.results}


def compute_gap(material: str, excluded: list[str], project) -> dict:
    """Expected minus generated, with excluded colours removed from expected."""
    excluded_set = set(excluded or [])
    expected = [c for c in full_palette(material) if c not in excluded_set]
    generated = distinct_generated(project) & set(expected)
    return {
        "expected": len(expected),
        "generated": len(generated),
        "missing": sorted(set(expected) - generated),
        "excluded": sorted(excluded_set),
    }
