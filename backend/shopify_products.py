"""Shopify product image coverage: parse a Matrixify-style variant CSV.

Owns detecting, per product (grouped by Handle), whether every variant row
has an image set. Mirrors coverage.py's tolerant CSV-loading conventions so
a partial/malformed store export never blocks the coverage page from
loading.
"""

from __future__ import annotations

import csv
from pathlib import Path

SHOPIFY_CSV_FILENAME = "shopify_products.csv"

REQUIRED_HEADERS = {"Handle", "Title"}
IMAGE_HEADER_CANDIDATES = ("Variant Image", "Image Src")


def has_recognizable_headers(header: list[str]) -> bool:
    """True if header has Handle, Title, and one of the known image columns."""
    fields = set(header)
    if not fields >= REQUIRED_HEADERS:
        return False
    return any(h in fields for h in IMAGE_HEADER_CANDIDATES)


def load_shopify_products(csv_path: Path) -> list[dict]:
    """Read Shopify variant rows and group into per-product image coverage.

    Returns [] if the file is missing, empty, or lacks recognizable
    Handle/Title/image-column headers. Rows with a blank Handle are
    skipped. Products are returned in first-seen Handle order.
    """
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not has_recognizable_headers(list(reader.fieldnames)):
            return []
        image_header = next(
            (h for h in IMAGE_HEADER_CANDIDATES if h in reader.fieldnames), None
        )
        groups: dict[str, dict] = {}
        order: list[str] = []
        for row in reader:
            handle = (row.get("Handle") or "").strip()
            if not handle:
                continue
            if handle not in groups:
                groups[handle] = {"title": "", "total_count": 0, "imaged_count": 0}
                order.append(handle)
            group = groups[handle]
            group["total_count"] += 1
            title = (row.get("Title") or "").strip()
            if title and not group["title"]:
                group["title"] = title
            if image_header and (row.get(image_header) or "").strip():
                group["imaged_count"] += 1

    products: list[dict] = []
    for handle in order:
        g = groups[handle]
        products.append(
            {
                "handle": handle,
                "title": g["title"] or handle,
                "total_count": g["total_count"],
                "imaged_count": g["imaged_count"],
                "fully_imaged": g["total_count"] > 0 and g["imaged_count"] == g["total_count"],
            }
        )
    return products
