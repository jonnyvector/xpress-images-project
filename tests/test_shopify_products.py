"""Shopify product image coverage: parsing, grouping, and malformed input.

The per-variant image rule itself is covered in test_shopify_variant_images.py.
"""

from pathlib import Path

from backend.shopify_products import has_recognizable_headers, load_shopify_products


def test_missing_file_returns_empty(tmp_path: Path):
    assert load_shopify_products(tmp_path / "nope.csv") == []


def test_empty_file_returns_empty(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text("")
    assert load_shopify_products(csv_path) == []


def test_unrecognized_headers_returns_empty(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text("Foo,Bar\nx,y\n")
    assert load_shopify_products(csv_path) == []


def test_has_recognizable_headers_requires_handle_title_and_image_column():
    assert has_recognizable_headers(["Handle", "Title", "Variant Image"]) is True
    assert has_recognizable_headers(["Handle", "Title", "Image Src"]) is True
    assert has_recognizable_headers(["Handle", "Title"]) is False
    assert has_recognizable_headers(["Foo", "Bar"]) is False


def test_groups_variants_by_handle_fully_imaged(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,https://cdn/2.jpg\n"
        "shaker-cabinet-door,,SCD-CHERRY,https://cdn/3.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert len(products) == 1
    p = products[0]
    assert p["handle"] == "shaker-cabinet-door"
    assert p["title"] == "Shaker Cabinet Door"
    assert p["variant_count"] == 3
    assert p["image_count"] == 3
    assert p["fully_imaged"] is True


def test_partially_imaged_product_is_not_fully_imaged(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
        "revere-cabinet-door,,RCD-OAK,\n"
    )
    products = load_shopify_products(csv_path)
    p = products[0]
    assert p["variant_count"] == 2
    assert p["image_count"] == 1
    assert p["fully_imaged"] is False


def test_falls_back_to_image_src_column_when_variant_image_absent(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Image Src\n"
        "tacoma-cabinet-door,Tacoma Cabinet Door,TCD-MAPLE,https://cdn/1.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert products[0]["fully_imaged"] is True


def test_skips_rows_with_blank_handle(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        ",,,\n"
    )
    products = load_shopify_products(csv_path)
    assert len(products) == 1


def test_ragged_row_missing_trailing_columns_does_not_raise(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door\n"
    )
    products = load_shopify_products(csv_path)
    p = products[0]
    # The ragged row names no variant and carries no image — it must be counted
    # as neither, rather than raising on the missing trailing columns.
    assert p["variant_count"] == 1
    assert p["image_count"] == 1
    assert p["fully_imaged"] is True


def test_multiple_products_preserve_first_seen_order(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/2.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert [p["handle"] for p in products] == ["revere-cabinet-door", "shaker-cabinet-door"]
