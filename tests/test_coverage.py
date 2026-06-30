from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.coverage import (
    CATEGORIES,
    compute_coverage,
    extract_match_tokens,
    load_products,
    project_matches,
)
from backend.state import ProjectState


def test_extract_tokens_plain_wood_name():
    assert extract_match_tokens("Shaker Cabinet Door") == {"shaker"}


def test_extract_tokens_strips_size_prefix():
    assert extract_match_tokens('3/4" Heritage Cabinet Door') == {"heritage"}


def test_extract_tokens_includes_parenthetical_style():
    assert extract_match_tokens("Tacoma Cabinet Door (Plank Style)") == {"tacoma", "plank"}


def test_extract_tokens_thermofoil_sku_only():
    assert extract_match_tokens("AR756 Thermofoil Cabinet Door") == {"ar756"}


def test_extract_tokens_thermofoil_sku_plus_parenthetical():
    assert extract_match_tokens(
        "DRS131 Thermofoil Cabinet Door (Shaker Style)"
    ) == {"drs131", "shaker"}


def test_extract_tokens_drops_pure_digits_and_generic_words():
    # "Drawer Front", "Style", and bare size digits must not become tokens
    assert extract_match_tokens("Revere Drawer Front") == {"revere"}


def _project(**kw) -> ProjectState:
    base = dict(id="p1", name="x", product_type="Cabinet Door", material_type="wood")
    base.update(kw)
    return ProjectState(**base)


def test_categories_cover_all_four_lists():
    keys = {c["key"] for c in CATEGORIES}
    assert keys == {
        "wood_cabinet_doors",
        "wood_drawer_fronts",
        "thermofoil_cabinet_doors",
        "thermofoil_drawer_fronts",
    }


def test_load_products_missing_file_returns_empty(tmp_path: Path):
    assert load_products(tmp_path / "nope.csv") == []


def test_project_matches_on_name_word():
    assert project_matches(_project(name="My Shaker upload"), {"shaker"}) is True
    assert project_matches(_project(name="door1.jpg"), {"shaker"}) is False


def test_project_matches_on_door_style_key():
    assert project_matches(_project(name="door1", door_style="solid_plank"), {"plank"}) is True


def test_compute_coverage_marks_covered_only_with_results(tmp_path: Path):
    csv = tmp_path / "wood_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
        '"Revere Cabinet Door",50.0,2\n'
    )
    # Shaker project WITH a result -> covered; Revere project WITHOUT results -> matched-not-covered
    shaker = _project(id="s1", name="Shaker", results=[("Maple", b"img")])
    revere = _project(id="r1", name="Revere", results=[])
    cats = compute_coverage([shaker, revere], data_dir=tmp_path)
    wood_cd = next(c for c in cats if c["key"] == "wood_cabinet_doors")

    assert wood_cd["total"] == 2
    assert wood_cd["covered"] == 1
    shaker_row = next(p for p in wood_cd["products"] if p["title"] == "Shaker Cabinet Door")
    revere_row = next(p for p in wood_cd["products"] if p["title"] == "Revere Cabinet Door")
    assert shaker_row["covered"] is True
    assert shaker_row["matched_project_ids"] == ["s1"]
    assert revere_row["covered"] is False
    assert revere_row["matched_project_ids"] == ["r1"]


def test_compute_coverage_filters_by_material_and_form(tmp_path: Path):
    csv = tmp_path / "thermofoil_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"DRS131 Thermofoil Cabinet Door (Shaker Style)",10.0,1\n'
    )
    # A wood project named "Shaker" must NOT cover an rtf product.
    wood_shaker = _project(id="w1", name="Shaker", material_type="wood", results=[("M", b"x")])
    cats = compute_coverage([wood_shaker], data_dir=tmp_path)
    tf_cd = next(c for c in cats if c["key"] == "thermofoil_cabinet_doors")
    assert tf_cd["covered"] == 0
    assert tf_cd["products"][0]["matched_project_ids"] == []


def test_coverage_endpoint_returns_four_categories():
    with TestClient(app) as client:
        resp = client.get("/api/coverage")
    assert resp.status_code == 200
    data = resp.json()
    keys = {c["key"] for c in data["categories"]}
    assert keys == {
        "wood_cabinet_doors",
        "wood_drawer_fronts",
        "thermofoil_cabinet_doors",
        "thermofoil_drawer_fronts",
    }
    wood_cd = next(c for c in data["categories"] if c["key"] == "wood_cabinet_doors")
    assert wood_cd["total"] >= 1
    assert "covered" in wood_cd
    assert {"title", "net_sales", "quantity", "covered", "matched_project_ids"} <= set(
        wood_cd["products"][0].keys()
    )
