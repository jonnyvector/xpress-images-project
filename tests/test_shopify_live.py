"""Live Shopify image status: per-variant unique-image summary, paging, CLI errors."""

import json

import pytest

from backend.shopify_live import (
    ShopifyCliError,
    _cli_error,
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


def test_every_variant_with_its_own_image_is_fully_imaged():
    p = summarize_product(
        _product(
            [
                _variant("Maple Select", CDN + "Revere_routed_maple_select.png", "Routed"),
                _variant("Maple Select", CDN + "Revere_solid_maple_select.png", "Solid"),
                _variant("Cherry Select", CDN + "anything_at_all.jpg", "Routed"),
            ]
        )
    )
    assert p["variant_count"] == 3
    assert p["own_image_count"] == 3
    assert p["fully_imaged"] is True


OLD_PHOTO = CDN + "811P_Arcadia_MAPL_wL.jpg"
WOODS = ["Maple Select", "Cherry Select", "Red Oak Select", "Ash Select"]


def test_photo_reused_across_many_variants_and_missing_image_are_reported():
    p = summarize_product(
        _product(
            [_variant(w, OLD_PHOTO) for w in WOODS]
            + [_variant("Walnut Natural"), _variant("Alder Select", CDN + "a_alder_select.png")]
        )
    )
    assert p["own_image_count"] == 1
    assert p["shared_variants"] == WOODS
    assert p["missing_variants"] == ["Walnut Natural"]
    assert p["fully_imaged"] is False


def test_pair_of_look_alike_options_may_share_an_image():
    # The store gives "MDF Panel w/ Maple Paint Grade Frame / Routed" the
    # "Maple Paint Grade / Routed" image on purpose.
    image = CDN + "heritage_routed_maple_paint_grade.png"
    p = summarize_product(
        _product(
            [
                _variant("Maple Paint Grade", image, "Routed"),
                _variant("MDF Panel w/ Maple Paint Grade Frame", image, "Routed"),
            ]
        )
    )
    assert p["shared_variants"] == []
    assert p["fully_imaged"] is True


def test_reupload_suffix_does_not_hide_a_reused_photo():
    uploads = [OLD_PHOTO, OLD_PHOTO.replace(".jpg", "_82692594-a3b3-40d4-b573-9a025fdbee94.jpg")]
    p = summarize_product(_product([_variant(w, uploads[i % 2]) for i, w in enumerate(WOODS)]))
    assert p["shared_variants"] == WOODS
    assert p["fully_imaged"] is False


def test_product_with_no_variants_is_not_fully_imaged():
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


from backend.coverage import listings_fully_imaged  # noqa: E402


def test_tied_listings_must_all_be_complete():
    done = {"fully_imaged": True, "status": "ACTIVE"}
    not_done = {"fully_imaged": False, "status": "ACTIVE"}
    assert listings_fully_imaged([done, not_done]) is False
    assert listings_fully_imaged([done, done]) is True
    assert listings_fully_imaged([]) is None
    assert listings_fully_imaged([{"fully_imaged": True, "status": "DRAFT"}]) is False


def test_snapshot_from_an_older_version_asks_for_a_refresh(tmp_path):
    from backend.coverage import load_shopify_source

    save_snapshot(tmp_path, [{"handle": "a", "title": "A", "status": "ACTIVE", "wood_count": 2}])
    products, meta = load_shopify_source(tmp_path)
    assert products == []
    assert meta["error"] == "Saved Shopify data is from an older version"
