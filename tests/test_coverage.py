from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.coverage import (
    CATEGORIES,
    compute_coverage,
    extract_match_tokens,
    load_products,
    project_matches,
    title_matches,
)
from backend.qa.approvals import Approval, ApprovalStore
from backend.state import ProjectState, ResultRecord


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


def test_project_matches_ignores_door_style():
    # door_style holds geometry words (e.g. "solid_plank") that must NOT match product tokens
    assert project_matches(_project(name="door1", door_style="solid_plank"), {"plank"}) is False


def test_matched_project_ids_orders_results_bearing_first(tmp_path):
    csv = tmp_path / "wood_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    empty = _project(id="empty", name="Shaker", results=[])
    full = _project(id="full", name="Shaker", results=[ResultRecord(image_id="img1", wood_name="Maple")])
    cats = compute_coverage([empty, full], data_dir=tmp_path)
    wood_cd = next(c for c in cats if c["key"] == "wood_cabinet_doors")
    row = wood_cd["products"][0]
    assert row["covered"] is True
    assert row["matched_project_ids"][0] == "full"  # results-bearing first
    assert set(row["matched_project_ids"]) == {"empty", "full"}


def test_compute_coverage_marks_covered_only_with_results(tmp_path: Path):
    csv = tmp_path / "wood_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
        '"Revere Cabinet Door",50.0,2\n'
    )
    # Shaker project WITH a result -> covered; Revere project WITHOUT results -> matched-not-covered
    shaker = _project(id="s1", name="Shaker", results=[ResultRecord(image_id="img1", wood_name="Maple")])
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
    wood_shaker = _project(id="w1", name="Shaker", material_type="wood", results=[ResultRecord(image_id="img1", wood_name="M")])
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


def test_title_matches_checks_whole_word_overlap():
    assert title_matches({"shaker"}, "My Shaker Upload") is True
    assert title_matches({"shaker"}, "door1.jpg") is False


def test_compute_coverage_reports_approval_progress(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    records = [
        ResultRecord(image_id="img1", wood_name="Maple"),
        ResultRecord(image_id="img2", wood_name="Oak"),
    ]
    project = _project(id="s1", name="Shaker", results=records)
    store = ApprovalStore(path=tmp_path / "approvals.json")
    store.set(Approval(image_id="img1", project_id="s1", kind="variant", verdict="approved"))

    cats = compute_coverage([project], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["approved_count"] == 1
    assert row["approved_total"] == 2


def test_compute_coverage_approval_zero_total_when_no_results(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    project = _project(id="s1", name="Shaker", results=[])
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([project], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["approved_count"] == 0
    assert row["approved_total"] == 0


def test_compute_coverage_on_shopify_true_when_fully_imaged(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,https://cdn/2.jpg\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is True


def test_compute_coverage_on_shopify_false_when_partially_imaged(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is False


def test_compute_coverage_on_shopify_none_when_no_csv_uploaded(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is None


def test_compute_coverage_on_shopify_none_when_no_title_match(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is None
