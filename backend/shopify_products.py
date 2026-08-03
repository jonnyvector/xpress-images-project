"""Shopify product image coverage: does each variant have its own image?

Owns detecting, per product (grouped by Handle), whether there are at least as
many DISTINCT images as there are variants. Option1 is "Wood Type" in this
store, so one image per variant means every wood has a picture.

Counting "rows with an image set" does not work on Shopify's standard product
export: a product's gallery lives in ``Image Src`` on extra rows that carry no
variant at all, while ``Variant Image`` is usually blank. Measured on a real
139-product export, every product had rows without an image and none would have
qualified, while 33 genuinely had an image per wood type.

Mirrors coverage.py's tolerant CSV-loading conventions so a partial or
malformed store export never blocks the coverage page from loading.
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


VARIANT_HEADER_CANDIDATES = ("Variant SKU", "Option1 Value")


def load_shopify_products(csv_path: Path) -> list[dict]:
    """Read Shopify rows and group into per-product image coverage.

    Returns [] if the file is missing, empty, or lacks recognizable
    Handle/Title/image-column headers. Rows with a blank Handle are skipped.
    Products are returned in first-seen Handle order.

    A row counts as a VARIANT when it names one (a Variant SKU or an Option1
    Value); a row contributes an IMAGE when either image column holds a URL.
    The two are counted independently because a single export row can be one,
    the other, or both. Image URLs are de-duplicated: the same picture repeated
    across rows is one picture, not several.
    """
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not has_recognizable_headers(list(reader.fieldnames)):
            return []
        image_headers = [h for h in IMAGE_HEADER_CANDIDATES if h in reader.fieldnames]
        variant_headers = [h for h in VARIANT_HEADER_CANDIDATES if h in reader.fieldnames]
        groups: dict[str, dict] = {}
        order: list[str] = []
        for row in reader:
            handle = (row.get("Handle") or "").strip()
            if not handle:
                continue
            if handle not in groups:
                groups[handle] = {"title": "", "variant_count": 0, "images": set()}
                order.append(handle)
            group = groups[handle]
            title = (row.get("Title") or "").strip()
            if title and not group["title"]:
                group["title"] = title
            if any((row.get(h) or "").strip() for h in variant_headers):
                group["variant_count"] += 1
            for header in image_headers:
                url = (row.get(header) or "").strip()
                if url:
                    group["images"].add(url)

    products: list[dict] = []
    for handle in order:
        g = groups[handle]
        variant_count = g["variant_count"]
        image_count = len(g["images"])
        products.append(
            {
                "handle": handle,
                "title": g["title"] or handle,
                "variant_count": variant_count,
                "image_count": image_count,
                # No variants means nothing to compare against — never claim done.
                "fully_imaged": variant_count > 0 and image_count >= variant_count,
            }
        )
    return products
