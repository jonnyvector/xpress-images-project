"""Push operator-approved local images onto a Shopify product's variants.

Reads image files from a local folder, matches each to a variant by wood/color
name, always prints a preview, and only writes to Shopify when --confirm is
passed. See docs/superpowers/specs/2026-08-14-shopify-image-upload-design.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from backend.coverage import CATEGORIES, DATA_DIR, load_products  # noqa: E402
from backend.filename_parsing import extract_wood_name  # noqa: E402
from backend.materials import MIME_MAP, load_material_types  # noqa: E402
from backend.routers.projects_media import IMAGE_EXTENSIONS  # noqa: E402
from backend.shopify_admin import (  # noqa: E402
    ShopifyApiError,
    Variant,
    append_media_to_variant,
    create_product_media,
    create_staged_upload,
    fetch_variants,
    upload_staged_file,
    wait_for_media_ready,
)
from backend.signoff import (  # noqa: E402
    SIGNOFF_LOCK,
    load_signoff,
    load_signoff_strict,
    save_signoff,
    set_shopify_product,
)


def normalize_name(value: str) -> str:
    return value.strip().casefold()


@dataclass
class MatchResult:
    path: Path
    wood_name: str
    variant_id: str | None


def find_ambiguous_variants(variants: list[Variant]) -> list[list[Variant]]:
    """Groups of 2+ variants that share a normalized option value.

    A product with a second option dimension (e.g. Size, Finish) or two
    variants that normalize to the same wood/color name would otherwise let
    match_files_to_variants() silently collapse them to "last one wins" —
    an image could then get pushed to the wrong live variant. Callers must
    exclude these groups from the match dict entirely."""
    by_value: dict[str, list[Variant]] = {}
    for v in variants:
        by_value.setdefault(normalize_name(v.option_value), []).append(v)
    return [group for group in by_value.values() if len(group) > 1]


def match_files_to_variants(
    files: list[Path], wood_types: dict[str, dict], variants: list[Variant]
) -> list[MatchResult]:
    """Match each file to a variant by normalized option value.

    Variants whose normalized option value collides with another variant's
    are ambiguous (see find_ambiguous_variants) and are never used as a
    match target — files that would have matched them fall through to
    unmatched, same as today's no-match case."""
    ambiguous_ids = {v.id for group in find_ambiguous_variants(variants) for v in group}
    by_normalized = {
        normalize_name(v.option_value): v.id for v in variants if v.id not in ambiguous_ids
    }
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


def print_preview(
    matches: list[MatchResult], ambiguous_groups: list[list[Variant]] | None = None
) -> None:
    matched = [m for m in matches if m.variant_id is not None]
    unmatched = [m for m in matches if m.variant_id is None]
    print(f"Matched ({len(matched)}):")
    for m in matched:
        print(f"  {m.path.name} -> {m.wood_name}")
    print(f"Unmatched ({len(unmatched)}):")
    for m in unmatched:
        print(f"  {m.path.name} -> {m.wood_name} (no variant match)")
    ambiguous_groups = ambiguous_groups or []
    ambiguous_count = sum(len(group) for group in ambiguous_groups)
    if ambiguous_groups:
        print(f"Ambiguous (skipped) ({ambiguous_count}):")
        for group in ambiguous_groups:
            value = group[0].option_value
            ids = ", ".join(v.id for v in group)
            print(f"  {value!r} shared by {len(group)} variants -> {ids} (excluded, not matchable)")


def read_shopify_credentials() -> tuple[str, str]:
    """SHOPIFY_STORE_DOMAIN + SHOPIFY_ADMIN_API_TOKEN from the project .env,
    overriding any stale shell export (same pattern as
    scripts/_onboard_common.py's GEMINI_API_KEY handling)."""
    load_dotenv(override=True)
    domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "")
    token = os.environ.get("SHOPIFY_ADMIN_API_TOKEN", "")
    if not domain or not token:
        raise SystemExit(
            "SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must be set in .env"
        )
    return domain, token


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload approved local images to a Shopify product's variants."
    )
    parser.add_argument(
        "--title", required=True,
        help="Sales-CSV product title (matches the coverage sign-off record)",
    )
    parser.add_argument(
        "--folder", required=True, help="Local folder of approved images to upload"
    )
    parser.add_argument(
        "--product",
        help="Shopify product id/gid, e.g. gid://shopify/Product/123. "
        "Persisted to the sign-off record for future runs.",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually write to Shopify. Without this flag, only a preview is "
        "printed. Re-running with --confirm does not check for images already "
        "on the variant and will add a duplicate.",
    )
    args = parser.parse_args()

    store_domain, token = read_shopify_credentials()
    material_type = resolve_material_type(args.title)

    record = load_signoff(DATA_DIR)
    entry = record.get(args.title) or {}
    product_id = args.product or entry.get("shopify_product_id")
    if not product_id:
        raise SystemExit(
            f"No Shopify product linked to {args.title!r} yet. Pass --product once to link it."
        )
    if args.product:
        with SIGNOFF_LOCK:
            record = load_signoff_strict(DATA_DIR)
            record = set_shopify_product(record, args.title, args.product)
            save_signoff(DATA_DIR, record)

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Not a directory: {args.folder}")
    files = sorted(
        f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not files:
        raise SystemExit(f"No image files found in {args.folder}")

    wood_types = load_material_types(material_type)

    with httpx.Client(timeout=30.0) as client:
        variants = fetch_variants(client, store_domain, token, product_id)
        matches = match_files_to_variants(files, wood_types, variants)
        ambiguous_groups = find_ambiguous_variants(variants)
        print_preview(matches, ambiguous_groups)

        if not args.confirm:
            print("\nDry run only — pass --confirm to upload the matched files.")
            return

        matched = [m for m in matches if m.variant_id is not None]
        failures: list[tuple[str, str]] = []
        for m in matched:
            try:
                content = m.path.read_bytes()
                mime_type = MIME_MAP.get(m.path.suffix.lower(), "image/png")
                target = create_staged_upload(
                    client, store_domain, token, m.path.name, mime_type, len(content)
                )
                upload_staged_file(client, target, m.path.name, mime_type, content)
                media_id = create_product_media(
                    client, store_domain, token, product_id, target["resourceUrl"], m.wood_name
                )
                wait_for_media_ready(client, store_domain, token, media_id)
                append_media_to_variant(
                    client, store_domain, token, product_id, m.variant_id, media_id
                )
                print(f"  uploaded: {m.path.name} -> {m.wood_name}")
            except (ShopifyApiError, httpx.HTTPError) as exc:
                failures.append((m.path.name, str(exc)))
                print(f"  FAILED: {m.path.name} -> {exc}")

    if failures:
        print(f"\n{len(failures)} file(s) failed:")
        for name, msg in failures:
            print(f"  {name}: {msg}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
