"""A product counts as imaged when it has a distinct image per variant.

Shopify's standard product export keeps a product's gallery in `Image Src` on
extra rows, not on the variant rows — so "every row has an image" is meaningless
there. What matters is whether there are as many distinct images as there are
variants: Option1 is "Wood Type", so one image per variant means every wood has
a picture.

Real-data reference (xpress-cabinet-doors.csv, 139 products): wedgewood has 36
wood types and 4 images — not done. 33 of 139 products pass this rule.
"""

from pathlib import Path

from backend.shopify_products import load_shopify_products

# The shape Shopify actually exports: variant rows carry Option1/SKU and no
# image; the gallery arrives on trailing rows that carry only Image Src.
STANDARD_EXPORT = (
    "Handle,Title,Option1 Name,Option1 Value,Variant SKU,Image Src,Variant Image\n"
    "wedgewood,Wedgewood Door,Wood Type,Maple,W-MAPLE,https://cdn/a.jpg,\n"
    "wedgewood,,Wood Type,Oak,W-OAK,https://cdn/b.jpg,\n"
    "wedgewood,,Wood Type,Cherry,W-CHERRY,,\n"
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "shopify_products.csv"
    path.write_text(body)
    return path


def test_fewer_images_than_variants_is_not_imaged(tmp_path: Path):
    # 3 wood types, 2 images — one wood has no picture.
    products = load_shopify_products(_write(tmp_path, STANDARD_EXPORT))
    assert len(products) == 1
    p = products[0]
    assert p["variant_count"] == 3
    assert p["image_count"] == 2
    assert p["fully_imaged"] is False


def test_one_distinct_image_per_variant_is_imaged(tmp_path: Path):
    products = load_shopify_products(
        _write(
            tmp_path,
            STANDARD_EXPORT.replace(
                "wedgewood,,Wood Type,Cherry,W-CHERRY,,\n",
                "wedgewood,,Wood Type,Cherry,W-CHERRY,https://cdn/c.jpg,\n",
            ),
        )
    )
    assert products[0]["image_count"] == 3
    assert products[0]["fully_imaged"] is True


def test_gallery_rows_without_variants_still_count_toward_images(tmp_path: Path):
    # Trailing gallery rows carry an image but no Option1/SKU — they are images,
    # not variants, which is exactly why row-count-based counting was wrong.
    products = load_shopify_products(
        _write(
            tmp_path,
            STANDARD_EXPORT + "wedgewood,,,,,https://cdn/c.jpg,\n",
        )
    )
    p = products[0]
    assert p["variant_count"] == 3
    assert p["image_count"] == 3
    assert p["fully_imaged"] is True


def test_duplicate_image_urls_count_once(tmp_path: Path):
    # The same URL repeated across rows is one picture, not three.
    products = load_shopify_products(
        _write(
            tmp_path,
            "Handle,Title,Option1 Value,Variant SKU,Image Src\n"
            "d,Door,Maple,D-1,https://cdn/same.jpg\n"
            "d,,Oak,D-2,https://cdn/same.jpg\n"
            "d,,Cherry,D-3,https://cdn/same.jpg\n",
        )
    )
    assert products[0]["image_count"] == 1
    assert products[0]["fully_imaged"] is False


def test_variant_image_column_also_counts(tmp_path: Path):
    # Matrixify-style exports put a distinct image on each variant row.
    products = load_shopify_products(
        _write(
            tmp_path,
            "Handle,Title,Variant SKU,Variant Image\n"
            "d,Door,D-1,https://cdn/1.jpg\n"
            "d,,D-2,https://cdn/2.jpg\n",
        )
    )
    assert products[0]["variant_count"] == 2
    assert products[0]["image_count"] == 2
    assert products[0]["fully_imaged"] is True


def test_product_with_no_variants_is_not_imaged(tmp_path: Path):
    # Nothing to compare against — do not claim it is done.
    products = load_shopify_products(
        _write(tmp_path, "Handle,Title,Image Src\nd,Door,https://cdn/1.jpg\n")
    )
    assert products[0]["variant_count"] == 0
    assert products[0]["fully_imaged"] is False


def test_more_images_than_variants_is_imaged(tmp_path: Path):
    # A big gallery on a two-wood product still means every wood can have one.
    products = load_shopify_products(
        _write(
            tmp_path,
            "Handle,Title,Option1 Value,Variant SKU,Image Src\n"
            "d,Door,Maple,D-1,https://cdn/1.jpg\n"
            "d,,Oak,D-2,https://cdn/2.jpg\n"
            "d,,,,https://cdn/3.jpg\n",
        )
    )
    assert products[0]["fully_imaged"] is True
