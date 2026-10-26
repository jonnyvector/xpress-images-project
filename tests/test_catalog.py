"""Command center: colour matching, project fit, front styles, sales parsing."""

import pytest

from backend.catalog import (
    color_key,
    fits_listing,
    project_style,
    unordered_color_key,
)
from backend.shopify_live import ShopifyCliError, fetch_sales, summarize_product


@pytest.mark.parametrize(
    ("shopify", "stored"),
    [
        ("Pecan-Hickory Select", "Pecan Hickory Select"),
        ("MDF Panel w/ Maple Paint Grade Frame", "MDF Panel / Maple Paint Grade Frame"),
        ("949W White (Smooth)", "949W White"),
        ("White Oak Rift Sawn", "White Oak Rift"),
        ("Rain Cloud", "Raincloud"),
        ("Alder Natural", "Alder Natural (New Sample)"),
        ("Raw MDF Only (Primer Ready) ML5", "MDF"),
    ],
)
def test_color_key_matches_shopify_names_to_swatches(shopify, stored):
    assert color_key(shopify) == color_key(stored)


def test_color_key_keeps_distinct_woods_apart():
    assert color_key("Red Oak Select") != color_key("White Oak Select")
    assert color_key("Maple Select") != color_key("Plain Sliced Maple Select")


def test_unordered_key_catches_swapped_words():
    assert unordered_color_key("Birch Natural") == unordered_color_key("Natural Birch")
    assert unordered_color_key("Vertical Grain Fir") == unordered_color_key("Fir Vertical Grain")


def test_plain_project_does_not_fit_mitered_listing():
    assert fits_listing("revere", "Revere Raised Panel Cabinet Door")
    assert not fits_listing("revere", "Revere Mitered Raised Panel Cabinet Door")
    assert fits_listing("revere_mitered", "Revere Mitered Raised Panel Cabinet Door")


def test_part_number_alone_fits():
    title = "DRS131 Recessed Panel Thermofoil Cabinet Door (Shaker Style)"
    assert fits_listing("DRS131 maple", title)


def test_project_style_from_name():
    assert project_style("journey_5-piece") == "5-Piece"
    assert project_style("mission-3-4-routed-drawer-front_maple_select") == "Routed"
    assert project_style("eagle") is None


def test_summary_keeps_variant_cells():
    node = {
        "id": "gid://shopify/Product/9",
        "handle": "h",
        "title": "T",
        "status": "ACTIVE",
        "variantsCount": {"count": 2},
        "variants": {
            "nodes": [
                {
                    "id": "gid://shopify/ProductVariant/1",
                    "title": "Red Oak Select / Solid",
                    "selectedOptions": [
                        {"name": "Wood Type", "value": "Red Oak Select"},
                        {"name": "Front Style", "value": "Solid"},
                    ],
                    "image": {"url": "https://cdn/a.png"},
                },
                {"id": "gid://shopify/ProductVariant/2", "title": "Alder", "image": None},
            ]
        },
    }
    summary = summarize_product(node)
    assert summary["id"] == "9"
    first, second = summary["variants"]
    assert first["id"] == "1"
    assert first["options"] == {"Wood Type": "Red Oak Select", "Front Style": "Solid"}
    assert first["image_state"] == "own"
    assert second["image_state"] == "none" and second["image_url"] is None


def _sales_runner(rows, parse_errors=None):
    def runner(query, variables):
        assert "shopifyqlQuery" in query
        return {"shopifyqlQuery": {"tableData": {"rows": rows}, "parseErrors": parse_errors or []}}

    return runner


def test_fetch_sales_sums_by_variant_and_product():
    rows = [
        {"product_id": "9", "product_variant_id": "1", "net_items_sold": "3", "net_sales": "30.5"},
        {"product_id": "9", "product_variant_id": "2", "net_items_sold": "2", "net_sales": "20"},
        # deleted one-off variant: counts toward the product only
        {"product_id": "9", "product_variant_id": "77", "net_items_sold": "1", "net_sales": "5"},
        {"product_id": None, "product_variant_id": None, "net_items_sold": "9", "net_sales": "-1"},
        {"product_id": "0", "product_variant_id": "0", "net_items_sold": "4", "net_sales": "8"},
    ]
    sales = fetch_sales(_sales_runner(rows))
    assert sales["by_variant"]["1"] == [3, 30.5]
    assert sales["by_product"]["9"] == [6, 55.5]
    assert "0" not in sales["by_product"]


def test_fetch_sales_rejects_parse_errors():
    with pytest.raises(ShopifyCliError):
        fetch_sales(_sales_runner([], parse_errors=["bad"]))


def test_rejected_images_never_fill_a_cell():
    from types import SimpleNamespace

    from backend.catalog import local_images

    project = SimpleNamespace(
        id="p",
        name="eagle",
        results=[
            SimpleNamespace(image_id="a", wood_name="Red Oak Select"),
            SimpleNamespace(image_id="b", wood_name="Alder Natural"),
        ],
    )
    store = SimpleNamespace(get=lambda i: SimpleNamespace(verdict="rejected") if i == "a" else None)
    exact, _ = local_images(project, store)
    assert color_key("Red Oak Select") not in exact  # operator rejected it
    assert exact[color_key("Alder Natural")]["verdict"] is None


def test_match_swatches_to_shopify_colors():
    from backend.catalog import match_swatches

    colors = ["Red Oak Select", "Pecan-Hickory Natural", "Rain Cloud", "Walnut Rustic Knotty"]
    swatches = [
        ("red-oak-select", "Red Oak Select"),
        ("red-oak-select-new", "Red Oak Select (New Sample)"),
        ("pecan", "Pecan Hickory Natural"),
        ("raincloud", "Raincloud"),
        ("maple-select", "Maple Select"),
    ]
    keys, unmatched = match_swatches(colors, swatches)
    assert keys == ["red-oak-select", "red-oak-select-new", "pecan", "raincloud"]
    assert unmatched == ["Walnut Rustic Knotty"]


def test_not_generated_badge_tolerates_spelling():
    from backend.routers.projects_common import _wood_name_key as key

    assert key("Pecan Hickory Natural") == key("Pecan-Hickory Natural")
    assert key("Natural Birch") == key("Birch Natural")
    assert key("MDF Panel / Soft Maple Frame") == key("MDF Panel w/ Soft Maple Frame")
    assert key("Alder Natural") != key("Alder Natural (New Sample)")  # its own swatch
