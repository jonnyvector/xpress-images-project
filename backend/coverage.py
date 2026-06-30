"""Best-seller coverage: join the sales CSVs with generated projects.

Owns the CSV product lists, the fuzzy style/SKU token extraction, and the
name-based match logic that decides whether a project covers a product. Pure
functions are kept side-effect-free so the matching is unit-testable.
"""

from __future__ import annotations

import re

# Words that carry no style meaning and must never become match tokens.
_GENERIC_WORDS = {
    "thermofoil",
    "cabinet",
    "door",
    "drawer",
    "front",
    "style",
    "dbq",
}


def _words(text: str) -> list[str]:
    """Split into lowercase alphanumeric words."""
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def extract_match_tokens(title: str) -> set[str]:
    """Extract lowercase match tokens (style words and/or SKUs) from a title."""
    parentheticals = re.findall(r"\(([^)]*)\)", title)
    base = re.sub(r"\([^)]*\)", " ", title)
    base = re.sub(r'\d+/\d+"?', " ", base)  # strip size fractions like 3/4"

    candidates = _words(base)
    for chunk in parentheticals:
        candidates.extend(_words(chunk))

    tokens: set[str] = set()
    for word in candidates:
        if word in _GENERIC_WORDS:
            continue
        if word.isdigit():
            continue
        if len(word) < 2:
            continue
        tokens.add(word)
    return tokens
