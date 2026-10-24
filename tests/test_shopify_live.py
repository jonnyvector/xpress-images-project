"""Live Shopify image status: image classification, per-wood summary, paging."""

import json

import pytest

from backend.shopify_live import (
    ShopifyCliError,
    _cli_error,
    classify_image,
    fetch_products,
    load_snapshot,
    save_snapshot,
    summarize_product,
)

CDN = "https://cdn.shopify.com/s/files/1/0669/7228/7298/files/"


def _variant(wood, url=None, style=None):
    opts = [{"name": "Wood Type", "value": wood}]
    if style:
        opts.append({"name": "Front Style", "value": style})
    return {
        "title": " / ".join(o["value"] for o in opts),
        "selectedOptions": opts,
        "image": {"url": url} if url else None,
    }


def _product(variants, title="Shaker Cabinet Door", handle="shaker"):
    return {"handle": handle, "title": title, "status": "ACTIVE", "variants": {"nodes": variants}}


@pytest.mark.parametrize(
    "url, own, expected",
    [
        (CDN + "Shaker_new_wm_maple_paint_grade.png?v=1", ["Maple Paint Grade"], "ai"),
        # "w/ " becomes "w__" in exports; Shopify's dedupe UUID suffix is ignored
        (
            CDN + "Shaker_new_wm_mdf_panel_w__maple_paint_grade_frame_"
            "82692594-a3b3-40d4-b573-9a025fdbee94.png",
            ["MDF Panel w/ Maple Paint Grade Frame"],
            "ai",
        ),
        # tool's "(New Sample)" swatch tail
        (
            CDN + "Shaker_flat_panel_alder_rustic_knotty__new_sample.png",
            ["Alder Rustic Knotty"],
            "ai",
        ),
        # store and tool name some woods differently
        (CDN + "Shaker_new_wm_red_oak_rift.png", ["Red Oak Rift Sawn"], "ai"),
        (CDN + "Shaker_new_wm_red_oak_quarter_sawn.png", ["Red Oak Quarter Sawn"], "ai"),
        (CDN + "auburn_natural_birch.png", ["Birch Natural"], "ai"),
        (CDN + "thermofoil_cabinet_door_white_high_gloss.png", ["High Gloss White"], "ai"),
        (CDN + "drs131_df_slab_949w_white.png", ["949W White (Smooth)"], "ai"),
        (
            CDN + "bronco_mdf_panel_maple_paint_grade_frame.png",
            ["MDF Panel w/ Maple Paint Grade Frame"],
            "ai",
        ),
        # a different oak is not this wood
        (CDN + "Shaker_new_wm_white_oak_rift.png", ["Red Oak Rift Sawn"], "photo"),
        (CDN + "840R_Mission_ALDS_wL.jpg", ["Alder Select"], "photo"),
        (CDN + "century.png", ["Maple Select"], "photo"),
        (None, ["Maple Select"], "none"),
    ],
)
def test_classify_image(url, own, expected):
    assert classify_image(url, own, own) == expected


def test_classify_flags_another_variants_wood_as_mismatch():
    url = CDN + "revere_drawer_front_maple_select.png"
    assert (
        classify_image(url, ["Maple Natural", "Solid"], ["Maple Natural", "Maple Select"])
        == "mismatch"
    )


def test_summary_reports_missing_and_mismatched_woods():
    p = summarize_product(
        _product(
            [
                _variant("Maple Select", CDN + "Shaker_maple_select.png"),
                _variant("Cherry Natural", CDN + "supplier_cherry.jpg"),
                _variant("Walnut Natural"),
                _variant("Red Oak Select", CDN + "Shaker_maple_select.png"),
            ]
        )
    )
    assert p["wood_count"] == 4
    assert p["ai_wood_count"] == 1
    assert p["missing_woods"] == ["Cherry Natural", "Walnut Natural"]
    assert p["mismatched_woods"] == ["Red Oak Select"]
    assert p["fully_imaged"] is False


def test_wood_counts_only_when_every_front_style_has_its_image():
    p = summarize_product(
        _product(
            [
                _variant("Maple Select", CDN + "Revere_routed_maple_select.png", "Routed"),
                _variant("Maple Select", None, "Solid"),
                _variant("Cherry Select", CDN + "Revere_routed_cherry_select.png", "Routed"),
                _variant("Cherry Select", CDN + "Revere_solid_cherry_select.png", "Solid"),
            ]
        )
    )
    assert p["wood_count"] == 2
    assert p["missing_woods"] == ["Maple Select"]
    assert p["ai_wood_count"] == 1


def test_fully_imaged_needs_every_wood_and_at_least_one():
    done = summarize_product(_product([_variant("Maple Select", CDN + "X_maple_select.png")]))
    assert done["fully_imaged"] is True
    assert summarize_product(_product([]))["fully_imaged"] is False


def test_fetch_follows_pagination():
    pages = [
        {
            "products": {
                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                "nodes": [_product([], handle="a")],
            }
        },
        {
            "products": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [_product([], handle="b")],
            }
        },
    ]
    seen = []

    def runner(query, variables):
        assert "mutation" not in query
        seen.append(variables["after"])
        return pages[len(seen) - 1]

    assert [p["handle"] for p in fetch_products(runner)] == ["a", "b"]
    assert seen == [None, "c1"]


def test_cli_auth_error_is_flagged():
    out = json.dumps(
        {
            "error": {
                "type": "abort",
                "message": "No stored app authentication found for x.myshopify.com.",
            }
        }
    )
    err = _cli_error(out)
    assert isinstance(err, ShopifyCliError)
    assert err.needs_auth is True
    assert "No stored app authentication" in str(err)


def test_cli_other_error_is_not_auth():
    assert _cli_error("Throttled: query cost exceeded").needs_auth is False
    assert _cli_error("Leaky bucket: token budget exhausted, retry later").needs_auth is False


def test_cli_next_steps_pointing_at_store_auth_count_as_auth():
    out = json.dumps(
        {
            "error": {
                "message": "Access denied.",
                "nextSteps": ["Run shopify store auth --store x.myshopify.com to authenticate"],
            }
        }
    )
    assert _cli_error(out).needs_auth is True


def test_fetch_rejects_graphql_errors():
    def runner(query, variables):
        return {"errors": [{"message": "MAX_COST_EXCEEDED"}]}

    with pytest.raises(ShopifyCliError, match="MAX_COST_EXCEEDED"):
        fetch_products(runner)


def test_truncated_product_is_never_fully_imaged():
    node = _product([_variant("Maple Select", CDN + "X_maple_select.png")])
    node["variantsCount"] = {"count": 300}
    assert summarize_product(node)["fully_imaged"] is False


def test_snapshot_round_trip(tmp_path):
    saved = save_snapshot(tmp_path, [{"handle": "a"}])
    loaded = load_snapshot(tmp_path)
    assert loaded == saved
    assert loaded["fetched_at"]


def test_missing_or_corrupt_snapshot_is_none(tmp_path):
    assert load_snapshot(tmp_path) is None
    (tmp_path / "shopify_live.json").write_text("{not json")
    assert load_snapshot(tmp_path) is None


# --- matching coverage rows to Shopify listings (backend/coverage.py) ---
from backend.coverage import CATEGORIES, extract_match_tokens, match_shopify_listings  # noqa: E402

WOOD_DOORS, WOOD_DRAWERS, RTF_DOORS, _ = CATEGORIES


def _match(category, row_title, listing_titles):
    listings = [{"title": t} for t in listing_titles]
    return [
        m["title"]
        for m in match_shopify_listings(category, extract_match_tokens(row_title), listings)
    ]


def test_match_requires_same_kind_of_product():
    titles = [
        "Shaker Recessed Panel Cabinet Door",
        "Shaker Drawer Front",
        "DRS131 Recessed Panel Thermofoil Cabinet Door",
        '3016 SHAKER CROWN 2-3/4", 8 Foot',
    ]
    assert _match(WOOD_DOORS, "Shaker Cabinet Door", titles) == [
        "Shaker Recessed Panel Cabinet Door"
    ]
    assert _match(WOOD_DRAWERS, "Shaker Drawer Front", titles) == ["Shaker Drawer Front"]


def test_part_number_is_decisive_for_thermofoil():
    titles = [
        "DRS131 Recessed Panel Thermofoil Cabinet Door",
        "DSS218 Thermofoil Cabinet Door (Shaker Style)",
    ]
    assert _match(RTF_DOORS, "DRS131 Thermofoil Cabinet Door (Shaker Style)", titles) == [
        "DRS131 Recessed Panel Thermofoil Cabinet Door"
    ]


def test_most_shared_words_wins_then_fewest_extra_words():
    titles = [
        "Adobe Recessed Panel Cabinet Door",
        "Adobe Mitered Recessed Panel Cabinet Door",
        "ZMC | Adobe Cabinet Door",
    ]
    assert _match(WOOD_DOORS, "Mitered Adobe Cabinet Door", titles) == [
        "Adobe Mitered Recessed Panel Cabinet Door"
    ]
    assert _match(WOOD_DOORS, "Adobe Cabinet Door", titles) == ["Adobe Recessed Panel Cabinet Door"]


def test_door_shape_words_do_not_count_as_a_different_product():
    titles = ["Mission Cathedral Recessed Panel Cabinet Door", "ZMC | Mission Cabinet Door"]
    assert _match(WOOD_DOORS, "Mission Cabinet Door", titles) == [
        "Mission Cathedral Recessed Panel Cabinet Door"
    ]


def test_no_shared_word_means_no_match():
    assert _match(WOOD_DOORS, "Fiesta Cabinet Door", ["Shaker Recessed Panel Cabinet Door"]) == []


def test_zmc_listings_are_never_matched():
    assert _match(WOOD_DOORS, "Shaker Cabinet Door", ["ZMC | Shaker Cabinet Door"]) == []


def test_front_style_value_never_makes_an_image_count():
    # "Routed" is a front style; only the wood ("Maple Select") may match.
    node = _product([_variant("Maple Select", CDN + "door_routed.png", "Routed")])
    assert summarize_product(node)["ai_wood_count"] == 0


from backend.coverage import listings_fully_imaged  # noqa: E402


def test_tied_listings_must_all_be_complete():
    done = {"fully_imaged": True, "status": "ACTIVE"}
    not_done = {"fully_imaged": False, "status": "ACTIVE"}
    assert listings_fully_imaged([done, not_done]) is False
    assert listings_fully_imaged([done, done]) is True
    assert listings_fully_imaged([]) is None
    assert listings_fully_imaged([{"fully_imaged": True, "status": "DRAFT"}]) is False
