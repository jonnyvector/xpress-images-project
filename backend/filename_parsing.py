"""Best-effort extraction of a material/wood name from an image filename.

Owns the heuristics for mapping arbitrary exported filenames (which carry
product/model-code prefixes, style tokens, version suffixes, and `_rtf`
markers) onto known material types. This is pure string logic with no HTTP or
storage concerns — the media router imports `extract_wood_name` from here.
"""

from __future__ import annotations

import re

from backend.materials import normalize_material_key

_TRAILING_VERSION_RE = re.compile(r"\s*\(?(\d+)\)?\s*$")

# Matches a leading product/model+style prefix like "DR1-df-slab_", "DN917 Slab Plain_".
# We find potential split points (underscores) and try each from left to right,
# accepting the first one whose remainder resolves to a known material.
_MODEL_CODE_RE = re.compile(r"^[A-Za-z]+\d+", re.IGNORECASE)

_TRAILING_RTF_RE = re.compile(r"[-_]rtf$", re.IGNORECASE)


def _match_color_key(color_part: str, wood_types: dict[str, dict]) -> str | None:
    """Try exact then prefix match against wood_types, return name or None."""
    color_part = _TRAILING_RTF_RE.sub("", color_part)
    key = normalize_material_key(color_part)
    if not key:
        return None
    wt = wood_types.get(key)
    if wt:
        return wt["name"]
    prefix = key + "-"
    matches = [k for k in wood_types if k.startswith(prefix)]
    if len(matches) == 1:
        return wood_types[matches[0]]["name"]
    if len(matches) > 1:
        matches.sort(key=len)
        return wood_types[matches[0]]["name"]
    return None


def extract_wood_name(stem: str, wood_types: dict[str, dict]) -> str:
    """Best-effort extraction of a wood name from a filename stem."""
    clean = _TRAILING_VERSION_RE.sub("", stem).strip()

    # Try progressively shorter suffixes against wood_types keys (exact match).
    tokens = re.split(r"[_\-]+", clean)
    for start in range(len(tokens)):
        candidate = "-".join(tokens[start:])
        key = normalize_material_key(candidate)
        wt = wood_types.get(key)
        if wt:
            return wt["name"]

    # Try splitting at each underscore position after a model code prefix.
    # e.g. "DR1-df-slab_black_rtf" -> try "black_rtf", then "rtf"
    #      "KB732_alabaster_taction_rtf" -> try "alabaster_taction_rtf", then "taction_rtf"
    # Accept the first (longest) remainder that resolves to a known material.
    underscore_positions = [i for i, c in enumerate(clean) if c == "_"]
    for pos in underscore_positions:
        remainder = clean[pos + 1:]
        name = _match_color_key(remainder, wood_types)
        if name:
            return name

    # Final fallback: strip model code and trailing _rtf, title-case
    m = _MODEL_CODE_RE.match(clean)
    if m:
        rest = clean[m.end():].lstrip(" _-")
        rest = _TRAILING_RTF_RE.sub("", rest)
        if rest:
            return rest.replace("_", " ").replace("-", " ").title()

    clean = _TRAILING_RTF_RE.sub("", clean)
    return clean.replace("_", " ").replace("-", " ").title()
