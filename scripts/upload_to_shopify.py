"""Push operator-approved local images onto a Shopify product's variants.

Reads image files from a local folder, matches each to a variant by wood/color
name, always prints a preview, and only writes to Shopify when --confirm is
passed. See docs/superpowers/specs/2026-08-14-shopify-image-upload-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.coverage import CATEGORIES, DATA_DIR, load_products
from backend.filename_parsing import extract_wood_name
from backend.shopify_admin import Variant


def normalize_name(value: str) -> str:
    return value.strip().casefold()


@dataclass
class MatchResult:
    path: Path
    wood_name: str
    variant_id: str | None


def match_files_to_variants(
    files: list[Path], wood_types: dict[str, dict], variants: list[Variant]
) -> list[MatchResult]:
    by_normalized = {normalize_name(v.option_value): v.id for v in variants}
    results = []
    for path in files:
        wood_name = extract_wood_name(path.stem, wood_types)
        variant_id = by_normalized.get(normalize_name(wood_name))
        results.append(MatchResult(path=path, wood_name=wood_name, variant_id=variant_id))
    return results


def resolve_material_type(title: str, data_dir: Path = DATA_DIR) -> str:
    """Find which sales-CSV category (and therefore material_type) a product
    title belongs to, the same way backend/routers/coverage.py validates
    titles for sign-off writes."""
    for cat in CATEGORIES:
        titles = {t for t, _, _ in load_products(data_dir / cat["csv"])}
        if title in titles:
            return cat["material"]
    raise SystemExit(f"Unknown product title: {title!r} (not found in any sales CSV)")


def print_preview(matches: list[MatchResult]) -> None:
    matched = [m for m in matches if m.variant_id is not None]
    unmatched = [m for m in matches if m.variant_id is None]
    print(f"Matched ({len(matched)}):")
    for m in matched:
        print(f"  {m.path.name} -> {m.wood_name}")
    print(f"Unmatched ({len(unmatched)}):")
    for m in unmatched:
        print(f"  {m.path.name} -> {m.wood_name} (no variant match)")
