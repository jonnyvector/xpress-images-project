"""Best-seller coverage: join the sales CSVs with generated projects.

Owns the CSV product lists, the fuzzy style/SKU token extraction, and the
name-based match logic that decides whether a project covers a product. Pure
functions are kept side-effect-free so the matching is unit-testable.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import TYPE_CHECKING

from backend.qa.approvals import get_approval_store
from backend.shopify_products import SHOPIFY_CSV_FILENAME, load_shopify_products

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
    return bool(tokens & set(_words(candidate_title)))


def project_matches(project: ProjectState, tokens: set[str]) -> bool:
    """True if any token is a whole word in the project's name."""
    return title_matches(tokens, project.name)


def load_overrides(data_dir: Path) -> set[str]:
    """Product titles manually marked covered (work done outside the app).

    Read from ``coverage_overrides.json`` next to the CSVs; missing or
    malformed file just means no overrides.
    """
    path = data_dir / "coverage_overrides.json"
    if not path.exists():
        return set()
    try:
        import json

        data = json.loads(path.read_text())
        return {str(t) for t in data.get("covered", [])}
    except (ValueError, OSError):
        return set()


def _approval_progress(project: ProjectState, approval_store: ApprovalStore) -> tuple[int, int]:
    """(approved_count, total) for a project's current result records."""
    total = len(project.results)
    approved = sum(
        1
        for record in project.results
        if (a := approval_store.get(record.image_id)) is not None and a.verdict == "approved"
    )
    return approved, total


def compute_coverage(
    projects: list[ProjectState],
    data_dir: Path = DATA_DIR,
    approval_store: ApprovalStore | None = None,
) -> list[dict]:
    """Build per-category coverage data joining the CSVs with projects."""
    overrides = load_overrides(data_dir)
    shopify_products = load_shopify_products(data_dir / SHOPIFY_CSV_FILENAME)
    store = approval_store if approval_store is not None else get_approval_store()
    categories: list[dict] = []
    for cat in CATEGORIES:
        candidates = [
            p
            for p in projects
            if p.material_type == cat["material"]
            and p.product_type == cat["product_type"]
        ]
        products: list[dict] = []
        covered_count = 0
        for title, net_sales, quantity in load_products(data_dir / cat["csv"]):
            tokens = extract_match_tokens(title)
            matched = [p for p in candidates if project_matches(p, tokens)]
            matched.sort(key=lambda p: 0 if p.results else 1)  # results-bearing first
            manual = title in overrides
            is_covered = manual or any(p.results for p in matched)
            if is_covered:
                covered_count += 1

            primary = next((p for p in matched if p.results), None)
            approved_count, approved_total = (
                _approval_progress(primary, store) if primary is not None else (0, 0)
            )

            shopify_matches = [
                sp for sp in shopify_products if title_matches(tokens, sp["title"])
            ]
            on_shopify = (
                any(sp["fully_imaged"] for sp in shopify_matches) if shopify_matches else None
            )

            products.append(
                {
                    "title": title,
                    "net_sales": net_sales,
                    "quantity": quantity,
                    "covered": is_covered,
                    "manual": manual,
                    "matched_project_ids": [p.id for p in matched],
                    "approved_count": approved_count,
                    "approved_total": approved_total,
                    "on_shopify": on_shopify,
                }
            )
        categories.append(
            {
                "key": cat["key"],
                "label": cat["label"],
                "covered": covered_count,
                "total": len(products),
                "products": products,
            }
        )
    return categories
