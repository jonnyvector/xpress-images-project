"""Command center read model: every active door and drawer front on Shopify.

Per product, and per variant (one cell per option): is the AI image live on
Shopify, generated here but not uploaded, or missing; plus last year's sales
so the hottest sellers get done first. Built from the saved Shopify snapshot
(Refresh from Shopify) and the local projects; never calls Shopify itself.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from backend.coverage import (
    CATEGORIES,
    compute_coverage,
    fits_listing,
    is_catalog_listing,
    joined_words,
    load_shopify_source,
    words,
)
from backend.shopify_live import ADMIN_PRODUCTS_URL

if TYPE_CHECKING:
    from backend.qa.approvals import ApprovalStore
    from backend.state import ProjectState

STYLE_OPTION = "Front Style"

# Words that differ between Shopify option names and generated swatch names
# without changing the colour: "949W White (Smooth)" is the "949W White" swatch,
# "MDF Panel w/ ..." is stored as "MDF Panel / ...", re-runs end in "Revised",
# Shopify's "White Oak Rift Sawn" is the "White Oak Rift" swatch.
_NOISE_WORDS = {"w", "new", "sample", "rtf", "revised", "copy", "sawn"}
_PAINT_GRADE_FRAME = "maplepaintgradeframe"
_VERDICT_RANK = {"approved": 2, None: 1, "rejected": 0}


def _color_words(name: str) -> list[str]:
    return [w for w in words(re.sub(r"\([^)]*\)", " ", name)) if w not in _NOISE_WORDS]


# Cached: the same few hundred colour names are keyed for ~16k variants.
@lru_cache(maxsize=4096)
def color_key(name: str) -> str:
    """Spacing/punctuation-free colour key: 'Pecan-Hickory Select' == 'Pecan Hickory Select'."""
    key = "".join(_color_words(name))
    if key.startswith("rawmdfonly"):  # "Raw MDF Only (Primer Ready) ML5" is the MDF swatch
        return "mdf"
    return key


@lru_cache(maxsize=4096)
def unordered_color_key(name: str) -> str:
    """Word-order-free key: 'Natural Birch' == 'Birch Natural'. Fallback only,
    since 'Rain Cloud' must still equal 'Raincloud' through color_key."""
    return "+".join(sorted(_color_words(name)))


def _style_prefix_stripped(key: str, project_name: str) -> str | None:
    """Folder imports sometimes prefix the style: 'Adobe Alder Natural' in an
    Adobe project is 'aldernatural'. None when there is no such prefix."""
    style = joined_words(project_name)
    for n in range(len(key) - 3, 2, -1):
        if style.startswith(key[:n]):
            return key[n:]
    return None


def local_images(project: ProjectState, store: ApprovalStore) -> tuple[dict, dict]:
    """(exact, fallback): colour key -> the project's best image of that colour.

    Approved beats unreviewed beats rejected; later beats earlier. `fallback`
    holds keys with a style prefix removed and word-order-free keys, used only
    when nothing matches exactly.
    """
    exact: dict[str, tuple] = {}
    fallback: dict[str, tuple] = {}
    for idx, record in enumerate(project.results):
        key = color_key(record.wood_name)
        if key.endswith(_PAINT_GRADE_FRAME):
            # "Adobe Maple Paint Grade Frame" is the MDF-panel variant.
            key = "mdfpanel" + _PAINT_GRADE_FRAME
        approval = store.get(record.image_id)
        verdict = approval.verdict if approval is not None else None
        if verdict == "rejected":  # the operator said no: that colour still needs an image
            continue
        score = (_VERDICT_RANK.get(verdict, 1), idx)
        image = {
            "project_id": project.id,
            "wood_name": record.wood_name,
            "verdict": verdict,
            "url": f"/api/projects/{project.id}/results/{idx}/image"
            f"?watermark=false&v={record.image_id}",
        }
        stripped = _style_prefix_stripped(key, project.name)
        unordered = unordered_color_key(record.wood_name)
        for table, k in ((exact, key), (fallback, stripped), (fallback, unordered)):
            if k and (k not in table or score > table[k][0]):
                table[k] = (score, image)
    return (
        {k: image for k, (_, image) in exact.items()},
        {k: image for k, (_, image) in fallback.items()},
    )


def _material_value(variant: dict) -> str:
    """The wood/colour option of a variant (everything but Front Style)."""
    values = [v for name, v in variant["options"].items() if name != STYLE_OPTION]
    return " / ".join(values) if values else variant["title"]


# Drawer-front "Front Style" option values, and how project names spell them.
_STYLE_SPELLINGS = {
    "5-Piece": ("5piece", "fivepiece"),
    "Routed": ("routed",),
    "Solid": ("solid", "slab"),
}


def project_style(project_name: str) -> str | None:
    """The front style a project was made for, when its name says so."""
    joined = joined_words(project_name)
    for style, spellings in _STYLE_SPELLINGS.items():
        if any(sp in joined for sp in spellings):
            return style
    return None


def listing_projects(canonical_id, matched_ids, title: str, by_id: dict) -> list:
    """This listing's doors, best first: the canonical pick on Coverage, then
    name-matched doors that fit, those with images before those without
    (a door just started still belongs on its product page)."""
    out = []
    if canonical_id in by_id:
        out.append(by_id[canonical_id])
    fitting = [
        by_id[pid]
        for pid in matched_ids
        if pid in by_id and by_id[pid] not in out and fits_listing(by_id[pid].name, title)
    ]
    out.extend(sorted(fitting, key=lambda p: not p.results))  # stable: keeps coverage order
    return out


def _project_for_variant(projects: list[tuple[ProjectState, str | None]], style: str | None):
    """A drawer front's 5-piece project can't stand in for its Routed cell.

    `projects` pairs each candidate with its project_style(), best first.
    """
    if style is None:
        return projects[0][0] if projects else None
    for wanted in (style, None):
        match = next((p for p, p_style in projects if p_style == wanted), None)
        if match is not None:
            return match
    return None


def _coverage_doors(projects, store, data_dir) -> dict[str, tuple[str | None, list[str]]]:
    """Listing handle -> (canonical door id, name-matched door ids), as Coverage decides."""
    shopify = load_shopify_source(data_dir)
    out: dict[str, tuple[str | None, list[str]]] = {}
    for category in compute_coverage(projects, data_dir, approval_store=store, shopify=shopify):
        for row in category["products"]:
            for listing in row["shopify_listings"]:
                out.setdefault(
                    listing["handle"], (row["canonical_project_id"], row["matched_project_ids"])
                )
    return out


def door_listings(
    projects: list[ProjectState], snapshot: dict, store: ApprovalStore, data_dir, door_id: str
) -> list[dict]:
    """The active Shopify listings this door's images belong to."""
    by_id = {p.id: p for p in projects}
    doors = _coverage_doors(projects, store, data_dir)
    out = []
    for product in snapshot["products"]:
        if product.get("status") != "ACTIVE" or not any(
            is_catalog_listing(c, product["title"]) for c in CATEGORIES
        ):
            continue
        canonical_id, matched_ids = doors.get(product["handle"], (None, []))
        if door_id in (canonical_id, *matched_ids) and any(
            p.id == door_id
            for p in listing_projects(canonical_id, matched_ids, product["title"], by_id)
        ):
            out.append(product)
    return out


def listing_colors(listings: list[dict]) -> list[str]:
    """Distinct wood/colour option values across the listings, in Shopify order."""
    seen: dict[str, None] = {}
    for product in listings:
        for v in product["variants"]:
            seen.setdefault(_material_value(v), None)
    return list(seen)


def match_swatches(
    colors: list[str], swatches: list[tuple[str, str]]
) -> tuple[list[str], list[str]]:
    """(swatch keys sold on the listing, Shopify colours with no swatch).

    swatches are (key, display name) pairs; matching uses the same colour
    keys as the Products page.
    """
    by_key = {color_key(c): c for c in colors}
    by_unordered = {unordered_color_key(c): c for c in colors}
    keys, matched = [], set()
    for swatch_key, name in swatches:
        color = by_key.get(color_key(name)) or by_unordered.get(unordered_color_key(name))
        if color is not None:
            keys.append(swatch_key)
            matched.add(color)
    return keys, [c for c in colors if c not in matched]


def build_catalog(
    projects: list[ProjectState],
    snapshot: dict,
    store: ApprovalStore,
    data_dir,
    *,
    handle: str | None = None,
    include_variants: bool = True,
) -> list[dict]:
    """Every active catalog listing with per-variant cells, hottest first.

    handle= builds just that listing; include_variants=False keeps only the
    per-product counts (the list page).
    """
    sales = snapshot.get("sales") or {}
    by_variant = sales.get("by_variant") or {}
    by_product = sales.get("by_product") or {}
    by_id = {p.id: p for p in projects}
    projects_by_handle = _coverage_doors(projects, store, data_dir)

    image_cache: dict[str, tuple[dict, dict]] = {}
    out: list[dict] = []
    for product in snapshot["products"]:
        if product.get("status") != "ACTIVE" or (handle and product["handle"] != handle):
            continue
        category = next((c for c in CATEGORIES if is_catalog_listing(c, product["title"])), None)
        if category is None:
            continue
        canonical_id, matched_ids = projects_by_handle.get(product["handle"], (None, []))
        candidates = [
            (p, project_style(p.name))
            for p in listing_projects(canonical_id, matched_ids, product["title"], by_id)
        ]

        variants = []
        for v in product["variants"]:
            material = _material_value(v)
            key = color_key(material)
            style = v["options"].get(STYLE_OPTION)
            project = _project_for_variant(candidates, style)
            local = None
            if project is not None:
                if project.id not in image_cache:
                    image_cache[project.id] = local_images(project, store)
                exact, fallback = image_cache[project.id]
                local = (
                    exact.get(key)
                    or fallback.get(key)
                    or fallback.get(unordered_color_key(material))
                )
            units, net = by_variant.get(v["id"], [0, 0.0])
            live = v["image_state"] == "own"
            variants.append(
                {
                    "id": v["id"],
                    "title": v["title"],
                    "material": material,
                    "style": style,
                    "units": units,
                    "net_sales": round(net, 2),
                    "image_state": v["image_state"],
                    "shopify_image": v["image_url"],
                    "local": local,
                    "cell": "live" if live else "generated" if local else "missing",
                }
            )
        units, net = by_product.get(product["id"], [0, 0.0])
        cells = [v["cell"] for v in variants]
        project = candidates[0][0] if candidates else None
        out.append(
            {
                "id": product["id"],
                "admin_url": f"{ADMIN_PRODUCTS_URL}/{product['id']}",
                "handle": product["handle"],
                "title": product["title"],
                "category": category["key"],
                "category_label": category["label"],
                "product_type": category["product_type"],
                "material_type": category["material"],
                "units": units,
                "net_sales": round(net, 2),
                # Sales of variants since deleted, which have no cell.
                "other_units": max(0, units - sum(v["units"] for v in variants)),
                "variant_count": len(variants),
                "live": cells.count("live"),
                "generated": cells.count("generated"),
                "missing": cells.count("missing"),
                "done": product["fully_imaged"],
                "project_id": project.id if project is not None else None,
                "project_name": project.name if project is not None else None,
                "variants": variants if include_variants else [],
            }
        )
    out.sort(key=lambda p: (-p["units"], p["title"].lower()))
    return out
