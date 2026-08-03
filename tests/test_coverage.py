from pathlib import Path

from fastapi.testclient import TestClient

import backend.routers.coverage as coverage_router
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
    full = _project(id="full", name="Shaker",
                    results=[ResultRecord(image_id="img1", wood_name="Maple")])
    cats = compute_coverage([empty, full], data_dir=tmp_path)
    wood_cd = next(c for c in cats if c["key"] == "wood_cabinet_doors")
    row = wood_cd["products"][0]
    # Coverage is now decided by sign-off, not results; no signoff record exists here.
    assert row["covered"] is False
    assert row["matched_project_ids"][0] == "full"  # results-bearing first
    assert set(row["matched_project_ids"]) == {"empty", "full"}


def test_compute_coverage_results_alone_do_not_mark_covered(tmp_path: Path):
    csv = tmp_path / "wood_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
        '"Revere Cabinet Door",50.0,2\n'
    )
    # Having generated results no longer implies covered -- only a sign-off does.
    shaker = _project(id="s1", name="Shaker",
                      results=[ResultRecord(image_id="img1", wood_name="Maple")])
    revere = _project(id="r1", name="Revere", results=[])
    cats = compute_coverage([shaker, revere], data_dir=tmp_path)
    wood_cd = next(c for c in cats if c["key"] == "wood_cabinet_doors")

    assert wood_cd["total"] == 2
    assert wood_cd["covered"] == 0
    shaker_row = next(p for p in wood_cd["products"] if p["title"] == "Shaker Cabinet Door")
    revere_row = next(p for p in wood_cd["products"] if p["title"] == "Revere Cabinet Door")
    assert shaker_row["covered"] is False
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
    wood_shaker = _project(id="w1", name="Shaker", material_type="wood",
                           results=[ResultRecord(image_id="img1", wood_name="M")])
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


def test_compute_coverage_rejected_verdict_does_not_count_as_approved(tmp_path: Path):
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
    store.set(Approval(image_id="img2", project_id="s1", kind="variant", verdict="rejected"))

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


def test_upload_shopify_csv_persists_and_refreshes_coverage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    csv_bytes = (
        b"Handle,Title,Variant SKU,Variant Image\n"
        b"shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", csv_bytes, "text/csv")},
        )
    assert resp.status_code == 200
    assert (tmp_path / "shopify_products.csv").exists()
    data = resp.json()
    wood_cd = next(c for c in data["categories"] if c["key"] == "wood_cabinet_doors")
    row = next(p for p in wood_cd["products"] if p["title"] == "Shaker Cabinet Door")
    assert row["on_shopify"] is True


def test_upload_shopify_csv_rejects_empty_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", b"", "text/csv")},
        )
    assert resp.status_code == 400
    assert not (tmp_path / "shopify_products.csv").exists()


def test_upload_shopify_csv_rejects_unrecognized_headers(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", b"Foo,Bar\nx,y\n", "text/csv")},
        )
    assert resp.status_code == 400
    assert not (tmp_path / "shopify_products.csv").exists()


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


def _project_with_colours(
    pid: str, name: str, colours: list[str], material: str = "rtf"
) -> ProjectState:
    p = ProjectState(id=pid, name=name, product_type="Cabinet Door", material_type=material)
    p.results = [ResultRecord(image_id=f"{pid}-{i}", wood_name=c)
                 for i, c in enumerate(colours)]
    return p


def test_results_alone_no_longer_mark_covered(tmp_path: Path):
    project = _project_with_colours("p1", "AR756", ["Bisque"])
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff={})
    rows = [r for c in cats for r in c["products"] if "AR756" in r["title"]]
    assert rows, "expected an AR756 row in the fixtures"
    assert all(r["variations_complete"] is False for r in rows)
    assert all(r["in_shopify"] is False for r in rows)


def test_signoff_drives_the_two_gates():
    project = _project_with_colours("p1", "AR756", ["Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {
        "variations_complete": {"by": "j", "at": "t", "result_count": 1,
                                "acknowledged_gap": True},
        "in_shopify": {"by": "j", "at": "t"},
    }}
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["variations_complete"] is True
    assert row["in_shopify"] is True


def test_gap_reads_canonical_project_only_not_the_union():
    # Two projects match the same product; only the canonical one counts.
    canonical = _project_with_colours("good", "AR756", ["Bisque"])
    decoy = _project_with_colours("decoy", "AR756-test", ["Niagara", "Snow White", "Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {"canonical_project_id": "good"}}
    cats = compute_coverage([canonical, decoy], data_dir=Path("docs/sales/data"),
                            signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"]["generated"] == 1
    assert "Niagara" in row["gap"]["missing"]


def test_excluded_colours_shrink_expected():
    project = _project_with_colours("p1", "AR756", [])
    title = "AR756 Thermofoil Cabinet Door"
    base = compute_coverage([project], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "p1"}})
    base_row = next(r for c in base for r in c["products"] if r["title"] == title)
    with_excl = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff={
        title: {"canonical_project_id": "p1", "excluded_colors": ["Bisque"]}})
    excl_row = next(r for c in with_excl for r in c["products"] if r["title"] == title)
    assert excl_row["gap"]["expected"] == base_row["gap"]["expected"] - 1
    assert "Bisque" not in excl_row["gap"]["missing"]


def test_duplicate_attempts_count_once():
    project = _project_with_colours("p1", "AR756", ["Bisque", "Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "p1"}})
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"]["generated"] == 1


def test_stale_flag_when_colour_count_moved():
    project = _project_with_colours("p1", "AR756", ["Bisque", "Niagara"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {
        "canonical_project_id": "p1",
        "variations_complete": {"by": "j", "at": "t", "result_count": 1,
                                "acknowledged_gap": True},
    }}
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["stale"] is True


def test_category_counts_both_gates():
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {"variations_complete": {"by": "j", "at": "t", "result_count": 0,
                                               "acknowledged_gap": True}}}
    cats = compute_coverage([], data_dir=Path("docs/sales/data"), signoff=signoff)
    cat = next(c for c in cats if c["key"] == "thermofoil_cabinet_doors")
    assert cat["variations_complete"] == 1
    assert cat["in_shopify_count"] == 0


def test_missing_canonical_project_yields_null_gap():
    title = "AR756 Thermofoil Cabinet Door"
    cats = compute_coverage([], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "gone"}})
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"] is None
