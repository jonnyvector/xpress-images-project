"""Uploading a Shopify export stamps in_shopify sign-offs for imaged products.

The operator's decision is still what counts — the CSV is simply a bulk way to
record it. So the upload only ever ADDS stamps for fully-imaged matches; it
never revokes a sign-off, and it never overwrites one a human already made.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.routers.coverage as cov_router
from backend.app import app
from backend.signoff import load_signoff
from backend.state import ProjectStore

TITLE = "AR756 Thermofoil Cabinet Door"

# Two wood-type variants. "Imaged" means at least one distinct image per
# variant, so the second file is one image short.
CSV_FULLY_IMAGED = (
    "Handle,Title,Option1 Value,Variant SKU,Variant Image\n"
    "ar756,AR756 Thermofoil Cabinet Door,Maple,AR756-MAPLE,https://cdn/a.png\n"
    "ar756,,Oak,AR756-OAK,https://cdn/b.png\n"
)
CSV_PARTIALLY_IMAGED = (
    "Handle,Title,Option1 Value,Variant SKU,Variant Image\n"
    "ar756,AR756 Thermofoil Cabinet Door,Maple,AR756-MAPLE,https://cdn/a.png\n"
    "ar756,,Oak,AR756-OAK,\n"
)


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


def _upload(client, body: str):
    return client.post(
        "/api/coverage/shopify-csv",
        files={"file": ("shopify.csv", body, "text/csv")},
    )


def _row(response, title: str = TITLE) -> dict:
    return next(
        p for c in response.json()["categories"] for p in c["products"] if p["title"] == title
    )


def test_fully_imaged_product_is_marked_in_shopify(client, data_dir):
    assert _row(client.get("/api/coverage"))["in_shopify"] is False

    response = _upload(client, CSV_FULLY_IMAGED)
    assert response.status_code == 200
    assert _row(response)["in_shopify"] is True

    stamp = load_signoff(data_dir)[TITLE]["in_shopify"]
    assert stamp["by"] == "shopify-csv"
    assert stamp["at"]


def test_partially_imaged_product_is_not_marked(client, data_dir):
    response = _upload(client, CSV_PARTIALLY_IMAGED)
    assert response.status_code == 200
    assert _row(response)["in_shopify"] is False
    assert "in_shopify" not in load_signoff(data_dir).get(TITLE, {})


def test_category_count_reflects_the_upload(client):
    before = next(
        c for c in client.get("/api/coverage").json()["categories"]
        if c["key"] == "thermofoil_cabinet_doors"
    )["in_shopify_count"]

    response = _upload(client, CSV_FULLY_IMAGED)
    after = next(
        c for c in response.json()["categories"] if c["key"] == "thermofoil_cabinet_doors"
    )["in_shopify_count"]
    assert after == before + 1


def test_upload_never_revokes_an_existing_signoff(client, data_dir):
    # Human marks it in Shopify, then a later export shows it only partly imaged.
    client.post(f"/api/coverage/{TITLE}/signoff", json={"gate": "shopify", "value": True})
    response = _upload(client, CSV_PARTIALLY_IMAGED)

    assert _row(response)["in_shopify"] is True
    assert load_signoff(data_dir)[TITLE]["in_shopify"]["by"] == "operator"


def test_upload_does_not_overwrite_a_human_stamp(client, data_dir):
    client.post(f"/api/coverage/{TITLE}/signoff", json={"gate": "shopify", "value": True})
    _upload(client, CSV_FULLY_IMAGED)

    # Provenance must still read as the human's, not the CSV's.
    assert load_signoff(data_dir)[TITLE]["in_shopify"]["by"] == "operator"


def test_upload_leaves_the_variations_gate_alone(client, data_dir):
    _upload(client, CSV_FULLY_IMAGED)

    row = _row(client.get("/api/coverage"))
    assert row["variations_complete"] is False
    assert "variations_complete" not in load_signoff(data_dir).get(TITLE, {})


def test_rejected_upload_stamps_nothing(client, data_dir):
    response = _upload(client, "Nope,Not,Valid\n1,2,3\n")
    assert response.status_code == 400
    assert load_signoff(data_dir) == {}
