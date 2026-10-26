"""Best-seller coverage: join the sales CSVs with generated projects.

Owns the CSV product lists, the fuzzy style/SKU token extraction, and the
name-based match logic that decides whether a project covers a product. Pure
functions are kept side-effect-free so the matching is unit-testable.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from backend.palette import compute_gap, distinct_generated
from backend.qa.approvals import get_approval_store
from backend.shopify_live import SNAPSHOT_FILENAME, drop_archived, load_snapshot
from backend.shopify_products import SHOPIFY_CSV_FILENAME, load_shopify_products
from backend.signoff import GATE_KEYS, is_stale, load_signoff

if TYPE_CHECKING:
    from backend.qa.approvals import ApprovalStore
    from backend.state import ProjectState

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


def words(text: str) -> list[str]:
    """Split into lowercase alphanumeric words."""
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def extract_match_tokens(title: str) -> set[str]:
    """Extract lowercase match tokens (style words and/or SKUs) from a title."""
    parentheticals = re.findall(r"\(([^)]*)\)", title)
    base = re.sub(r"\([^)]*\)", " ", title)
    base = re.sub(r'\d+/\d+"?', " ", base)  # strip size fractions like 3/4"

    candidates = words(base)
    for chunk in parentheticals:
        candidates.extend(words(chunk))

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


DATA_DIR = Path("docs/sales/data")

CATEGORIES: list[dict] = [
    {
        "key": "wood_cabinet_doors",
        "label": "Wood Cabinet Doors",
        "material": "wood",
        "product_type": "Cabinet Door",
        "csv": "wood_cabinet_doors.csv",
    },
    {
        "key": "wood_drawer_fronts",
        "label": "Wood Drawer Fronts",
        "material": "wood",
        "product_type": "Drawer Front",
        "csv": "wood_drawer_fronts.csv",
    },
    {
        "key": "thermofoil_cabinet_doors",
        "label": "Thermofoil Cabinet Doors",
        "material": "rtf",
        "product_type": "Cabinet Door",
        "csv": "thermofoil_cabinet_doors.csv",
    },
    {
        "key": "thermofoil_drawer_fronts",
        "label": "Thermofoil Drawer Fronts",
        "material": "rtf",
        "product_type": "Drawer Front",
        "csv": "thermofoil_drawer_fronts.csv",
    },
]


def load_products(csv_path: Path) -> list[tuple[str, float, int]]:
    """Read (title, net_sales, quantity) rows from a sales CSV; [] if missing."""
    if not csv_path.exists():
        return []
    rows: list[tuple[str, float, int]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 3:
                continue
            try:
                rows.append((row[0], float(row[1]), int(float(row[2]))))
            except ValueError:
                continue
    return rows


def title_matches(tokens: set[str], candidate_title: str) -> bool:
    """True if any token is a whole word in candidate_title."""
    return bool(tokens & set(words(candidate_title)))


# Shopify title words that describe construction, not which product it is.
_LISTING_GENERIC_WORDS = _GENERIC_WORDS | {
    "raised",
    "recessed",
    "panel",
    "slab",
    "arched",
    "cathedral",
}


@lru_cache(maxsize=4096)
def _title_words(title: str) -> frozenset[str]:
    # Cached: every coverage row is scored against every listing title.
    return frozenset(words(title))


def _is_same_kind(category: dict, words: set[str]) -> bool:
    is_drawer = "drawer" in words
    if category["product_type"] == "Drawer Front" and not is_drawer:
        return False
    if category["product_type"] == "Cabinet Door" and ("door" not in words or is_drawer):
        return False
    return ("thermofoil" in words) == (category["material"] == "rtf")


def is_catalog_listing(category: dict, title: str) -> bool:
    """A store product that belongs in this coverage category.

    Only real doors and drawer fronts ("Cabinet Door" / "Drawer Front" in the
    title), never ZMC listings or cabinets like "RTA 1-Door Base Cabinet".
    """
    words = _title_words(title)
    if "zmc" in words:
        return False
    lowered = title.lower()
    if "cabinet door" not in lowered and "drawer front" not in lowered:
        return False
    return _is_same_kind(category, words)


def listings_fully_imaged(matches: list[dict]) -> bool | None:
    """Whether a row's matched listings count as done on Shopify.

    None when nothing matched. Only ACTIVE listings count (a draft isn't on the
    storefront; CSV rows carry no status and count as active), and every one
    of them must be complete, so a finished sibling can't vouch for an
    unfinished one.
    """
    if not matches:
        return None
    active = [m for m in matches if m.get("status", "ACTIVE") == "ACTIVE"]
    return bool(active) and all(m["fully_imaged"] for m in active)


def match_shopify_listings(category: dict, tokens: set[str], listings: list[dict]) -> list[dict]:
    """The Shopify products that are this coverage row's listing(s).

    Sharing any one style word over-matches ("Shaker Cabinet Door" would claim
    the Shaker drawer front and every "(Shaker Style)" thermofoil door), so:
    the listing must be the same kind of product as the category, a part
    number (DRS131) must appear exactly, and otherwise only the listings that
    share the MOST words with the row are kept ("Mitered Adobe" beats "Adobe").
    """
    skus = {t for t in tokens if any(ch.isdigit() for ch in t)}
    scored: list[tuple[int, int, dict]] = []
    for listing in listings:
        words = _title_words(listing["title"])
        if "zmc" in words:  # separate ZMC-branded listings are out of scope
            continue
        if not _is_same_kind(category, words):
            continue
        score = len((skus or tokens) & words)
        if score:
            # Words the row doesn't have ("mitered") mark a sibling product;
            # fewer wins a tie.
            extra = len(words - tokens - _LISTING_GENERIC_WORDS)
            scored.append((score, -extra, listing))
    best = max(((score, neg_extra) for score, neg_extra, _ in scored), default=None)
    return [listing for score, neg_extra, listing in scored if (score, neg_extra) == best]


def joined_words(text: str) -> str:
    """Lowercase alphanumerics only: 'journey_5-piece' -> 'journey5piece'."""
    return "".join(words(text))


def fits_listing(project_name: str, listing_title: str) -> bool:
    """A name-matched project really is this listing's style.

    Coverage rows match on any shared word, so plain "revere" matches "Revere
    Mitered". Here every distinguishing word of the listing must be in the
    project name; for a part-numbered listing (DRS131) the part number alone
    is enough.
    """
    name_words = set(words(project_name))
    joined = joined_words(project_name)
    tokens = extract_match_tokens(listing_title) - _LISTING_GENERIC_WORDS
    skus = {t for t in tokens if any(ch.isdigit() for ch in t)}
    if skus and any(sku in joined for sku in skus):
        return True
    rest = tokens - skus
    return bool(rest) and all(t in name_words or t in joined for t in rest)


def project_matches(project: ProjectState, tokens: set[str]) -> bool:
    """True if any token is a whole word in the project's name."""
    return title_matches(tokens, project.name)


def _approval_progress(project: ProjectState, approval_store: ApprovalStore) -> tuple[int, int]:
    """(approved_count, total) for a project's current result records."""
    total = len(project.results)
    approved = sum(
        1
        for record in project.results
        if (a := approval_store.get(record.image_id)) is not None and a.verdict == "approved"
    )
    return approved, total


def load_shopify_source(data_dir: Path) -> tuple[list[dict], dict]:
    """Shopify products for coverage, plus where they came from.

    The live snapshot (Refresh from Shopify) wins; the old CSV export is only a
    fallback until the first live sync.
    """
    snapshot = load_snapshot(data_dir)
    if snapshot is not None:
        products = drop_archived(snapshot["products"])
        if any(not all(k in p for k in _LISTING_KEYS) for p in products):
            # Saved by an older version with a different "done" rule.
            error = "Saved Shopify data is from an older version"
            return [], {"source": None, "synced_at": None, "error": error}
        return products, {"source": "live", "synced_at": snapshot.get("fetched_at")}
    if (data_dir / SNAPSHOT_FILENAME).exists():
        # Don't quietly fall back to the old CSV: the live data was lost.
        return [], {"source": None, "synced_at": None, "error": "Saved Shopify data is unreadable"}
    csv_products = load_shopify_products(data_dir / SHOPIFY_CSV_FILENAME)
    return csv_products, {"source": "csv" if csv_products else None, "synced_at": None}


_LISTING_KEYS = (
    "fully_imaged",
    "handle",
    "title",
    "status",
    "variant_count",
    "own_image_count",
    "missing_variants",
    "shared_variants",
)


def _coverage_row(
    title: str,
    net_sales: float,
    quantity: int,
    shopify_matches: list[dict],
    *,
    cat: dict,
    candidates: list[ProjectState],
    by_id: dict[str, ProjectState],
    record: dict[str, dict],
    store: ApprovalStore,
    live: bool,
) -> dict:
    """One coverage row: a product with its projects, sign-offs and Shopify status."""
    tokens = extract_match_tokens(title)
    matched = [p for p in candidates if project_matches(p, tokens)]
    matched.sort(key=lambda p: 0 if p.results else 1)  # results-bearing first
    entry = record.get(title) or {}

    canonical_id = entry.get("canonical_project_id")
    canonical = by_id.get(canonical_id) if canonical_id else None
    excluded = list(entry.get("excluded_colors") or [])
    gap = compute_gap(cat["material"], excluded, canonical) if canonical is not None else None

    variations_done = GATE_KEYS["variations"] in entry
    shopify_done = GATE_KEYS["shopify"] in entry

    primary = next((p for p in matched if p.results), None)
    approved_count, approved_total = (
        _approval_progress(primary, store) if primary is not None else (0, 0)
    )

    return {
        "title": title,
        "net_sales": net_sales,
        "quantity": quantity,
        "covered": variations_done,
        "matched_project_ids": [p.id for p in matched],
        "approved_count": approved_count,
        "approved_total": approved_total,
        "on_shopify": listings_fully_imaged(shopify_matches),
        # Per-variant detail exists only in the live snapshot, not the CSV.
        "shopify_listings": [{k: sp[k] for k in _LISTING_KEYS} for sp in shopify_matches]
        if live
        else [],
        "variations_complete": variations_done,
        "in_shopify": shopify_done,
        "canonical_project_id": canonical_id,
        "excluded_colors": excluded,
        "gap": gap,
        "stale": is_stale(entry, len(distinct_generated(canonical)))
        if canonical is not None
        else False,
    }


def compute_coverage(
    projects: list[ProjectState],
    data_dir: Path = DATA_DIR,
    approval_store: ApprovalStore | None = None,
    signoff: dict[str, dict] | None = None,
    shopify: tuple[list[dict], dict] | None = None,
) -> list[dict]:
    """Build per-category coverage data joining the CSVs with projects.

    Coverage is decided ONLY by the sign-off record. The palette gap and the
    approval/Shopify signals are advisory evidence for the operator.
    `shopify` is load_shopify_source()'s result, for callers that already have it.
    """
    record = load_signoff(data_dir) if signoff is None else signoff
    shopify_products, shopify_meta = shopify or load_shopify_source(data_dir)
    live = shopify_meta["source"] == "live"
    store = approval_store if approval_store is not None else get_approval_store()
    by_id = {p.id: p for p in projects}
    categories: list[dict] = []
    for cat in CATEGORIES:
        candidates = [
            p
            for p in projects
            if p.material_type == cat["material"] and p.product_type == cat["product_type"]
        ]
        products: list[dict] = []
        row_context = {
            "cat": cat,
            "candidates": candidates,
            "by_id": by_id,
            "record": record,
            "store": store,
            "live": live,
        }
        claimed: set[str] = set()
        for title, net_sales, quantity in load_products(data_dir / cat["csv"]):
            shopify_matches = match_shopify_listings(
                cat, extract_match_tokens(title), shopify_products
            )
            claimed.update(m["handle"] for m in shopify_matches)
            products.append(
                _coverage_row(title, net_sales, quantity, shopify_matches, **row_context)
            )

        # Every other active product of this kind on the store, so coverage
        # lists the whole catalogue, not only the best-sellers in the CSV.
        if live:
            extras = [
                listing
                for listing in shopify_products
                if listing["handle"] not in claimed
                and listing.get("status", "ACTIVE") == "ACTIVE"
                and is_catalog_listing(cat, listing["title"])
            ]
            for listing in sorted(extras, key=lambda listing: listing["title"].lower()):
                products.append(_coverage_row(listing["title"], 0.0, 0, [listing], **row_context))
        n_variations = sum(p["variations_complete"] for p in products)
        categories.append(
            {
                "key": cat["key"],
                "label": cat["label"],
                "covered": n_variations,
                "total": len(products),
                "variations_complete": n_variations,
                "in_shopify_count": sum(p["in_shopify"] for p in products),
                "products": products,
            }
        )
    return categories
