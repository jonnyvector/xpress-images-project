"""Refresh from Shopify: live snapshot (images + sales) drives coverage.

The CLI call is replaced by a fake, so these tests never touch a store.
"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.routers.coverage as cov_router
from backend.app import app
from backend.shopify_live import ShopifyCliError
from backend.signoff import load_signoff
from backend.state import ProjectStore

TITLE = "AR756 Thermofoil Cabinet Door"


def _listing(fully_imaged: bool, status: str = "ACTIVE") -> dict:
    return {
        "handle": "ar756",
        "title": "AR756 Raised Panel Thermofoil Cabinet Door",
        "status": status,
        "variant_count": 2,
        "own_image_count": 2 if fully_imaged else 1,
        "missing_variants": [] if fully_imaged else ["Bisque"],
        "shared_variants": [],
        "fully_imaged": fully_imaged,
    }


SALES = {"days": 365, "by_variant": {"1": [3, 30.0]}, "by_product": {"9": [3, 30.0]}}


@pytest.fixture(autouse=True)
def fake_sales(monkeypatch):
    """Never let a test read the real store's sales report."""
    monkeypatch.setattr(cov_router, "fetch_sales", lambda: SALES)


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    src = Path("docs/sales/data")
    shutil.copy(src / "thermofoil_cabinet_doors.csv", tmp_path / "thermofoil_cabinet_doors.csv")
    monkeypatch.setattr(cov_router, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    with TestClient(app) as c:
        monkeypatch.setattr(
            app.state, "project_store", ProjectStore(persist_dir=tmp_path / "projects")
        )
        yield c


def _fake_shopify(monkeypatch, products=None, error=None):
    def fake():
        if error:
            raise error
        return products

    monkeypatch.setattr(cov_router, "fetch_products", fake)


def _row(response, title: str = TITLE) -> dict:
    return next(
        p for c in response.json()["categories"] for p in c["products"] if p["title"] == title
    )


def test_refresh_reports_missing_variants_and_marks_source_live(client, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=False)])
    response = client.post("/api/coverage/shopify-refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["shopify_source"] == "live"
    assert body["shopify_synced_at"]
    row = _row(response)
    assert row["on_shopify"] is False
    assert row["shopify_listings"][0]["missing_variants"] == ["Bisque"]


def test_refresh_never_writes_signoffs(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])
    response = client.post("/api/coverage/shopify-refresh")

    assert _row(response)["on_shopify"] is True
    assert _row(response)["in_shopify"] is False
    assert "in_shopify" not in load_signoff(data_dir).get(TITLE, {})


def test_archived_listings_are_ignored(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True, status="ARCHIVED")])
    response = client.post("/api/coverage/shopify-refresh")

    row = _row(response)
    assert row["shopify_listings"] == []
    assert row["in_shopify"] is False
    assert "in_shopify" not in load_signoff(data_dir).get(TITLE, {})


def test_snapshot_persists_for_later_reads(client, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=False)])
    client.post("/api/coverage/shopify-refresh")

    later = client.get("/api/coverage")
    assert later.json()["shopify_source"] == "live"
    assert _row(later)["shopify_listings"][0]["handle"] == "ar756"


def test_lapsed_login_returns_409_with_fix(client, data_dir, monkeypatch):
    _fake_shopify(
        monkeypatch, error=ShopifyCliError("No stored app authentication", needs_auth=True)
    )
    response = client.post("/api/coverage/shopify-refresh")

    assert response.status_code == 409
    assert "scripts/shopauth.sh" in response.json()["detail"]
    assert not (data_dir / "shopify_live.json").exists()


def test_other_cli_failure_returns_502(client, monkeypatch):
    _fake_shopify(monkeypatch, error=ShopifyCliError("Throttled"))
    assert client.post("/api/coverage/shopify-refresh").status_code == 502


def test_before_any_sync_source_is_empty(client):
    body = client.get("/api/coverage").json()
    assert body["shopify_source"] is None
    assert body["shopify_synced_at"] is None


def test_refresh_never_overwrites_a_human_stamp(client, data_dir, monkeypatch):
    client.post(f"/api/coverage/{TITLE}/signoff", json={"gate": "shopify", "value": True})
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])
    client.post("/api/coverage/shopify-refresh")

    assert load_signoff(data_dir)[TITLE]["in_shopify"]["by"] == "operator"


def test_refresh_never_revokes_a_signoff(client, data_dir, monkeypatch):
    client.post(f"/api/coverage/{TITLE}/signoff", json={"gate": "shopify", "value": True})
    _fake_shopify(monkeypatch, [_listing(fully_imaged=False)])
    response = client.post("/api/coverage/shopify-refresh")

    assert _row(response)["in_shopify"] is True


def test_refresh_leaves_the_variations_gate_alone(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])
    client.post("/api/coverage/shopify-refresh")

    assert "variations_complete" not in load_signoff(data_dir).get(TITLE, {})


def test_response_carries_admin_link_base(client):
    assert (
        client.get("/api/coverage")
        .json()["shopify_admin_url"]
        .startswith("https://admin.shopify.com/store/")
    )


def test_draft_listing_is_never_stamped(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True, status="DRAFT")])
    response = client.post("/api/coverage/shopify-refresh")

    row = _row(response)
    assert row["on_shopify"] is False
    assert row["shopify_listings"][0]["status"] == "DRAFT"  # still shown, labelled
    assert "in_shopify" not in load_signoff(data_dir).get(TITLE, {})


def test_empty_store_read_keeps_previous_snapshot(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=False)])
    client.post("/api/coverage/shopify-refresh")
    before = (data_dir / "shopify_live.json").read_text()

    _fake_shopify(monkeypatch, [])
    assert client.post("/api/coverage/shopify-refresh").status_code == 502
    assert (data_dir / "shopify_live.json").read_text() == before


def test_unreadable_snapshot_is_reported_not_hidden(client, data_dir):
    (data_dir / "shopify_live.json").write_text("{broken")
    body = client.get("/api/coverage").json()
    assert body["shopify_error"]
    assert body["shopify_source"] is None


def test_second_refresh_while_one_runs_is_refused(client, monkeypatch):
    assert cov_router._REFRESH_LOCK.acquire(blocking=False)
    try:
        assert client.post("/api/coverage/shopify-refresh").status_code == 409
    finally:
        cov_router._REFRESH_LOCK.release()


def test_sales_saved_with_snapshot(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])
    assert client.post("/api/coverage/shopify-refresh").status_code == 200
    snapshot = json.loads((data_dir / "shopify_live.json").read_text())
    assert snapshot["sales"] == SALES
    assert snapshot["sales_error"] is None


def test_sales_failure_does_not_block_refresh(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])

    def no_scope():
        raise ShopifyCliError("Access denied for shopifyqlQuery")

    monkeypatch.setattr(cov_router, "fetch_sales", no_scope)
    assert client.post("/api/coverage/shopify-refresh").status_code == 200
    snapshot = json.loads((data_dir / "shopify_live.json").read_text())
    assert snapshot["sales"] is None  # nothing to keep yet
    assert "Access denied" in snapshot["sales_error"]


def test_failed_sales_read_keeps_last_good_sales(client, data_dir, monkeypatch):
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True)])
    assert client.post("/api/coverage/shopify-refresh").status_code == 200  # saves SALES

    def no_scope():
        raise ShopifyCliError("Access denied for shopifyqlQuery")

    monkeypatch.setattr(cov_router, "fetch_sales", no_scope)
    assert client.post("/api/coverage/shopify-refresh").status_code == 200
    snapshot = json.loads((data_dir / "shopify_live.json").read_text())
    assert snapshot["sales"] == SALES
    assert "Access denied" in snapshot["sales_error"]


def test_store_only_rows_accept_sign_off(client, data_dir, monkeypatch):
    """Coverage lists active store products missing from the sales CSV; their
    sign-off controls must work too."""
    store_only = {
        **_listing(fully_imaged=True),
        "handle": "zz",
        "title": "Zephyr Thermofoil Cabinet Door",
    }
    _fake_shopify(monkeypatch, [_listing(fully_imaged=True), store_only])
    assert client.post("/api/coverage/shopify-refresh").status_code == 200
    resp = client.put(
        "/api/coverage/Zephyr Thermofoil Cabinet Door/exclusions", json={"colors": []}
    )
    assert resp.status_code == 200
