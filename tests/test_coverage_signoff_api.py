from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.app import app

TITLE = "AR756 Thermofoil Cabinet Door"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Point the router at a scratch data dir seeded with the real CSVs."""
    import shutil

    import backend.routers.coverage as cov_router

    src = Path("docs/sales/data")
    for name in ("thermofoil_cabinet_doors.csv",):
        shutil.copy(src / name, tmp_path / name)
    monkeypatch.setattr(cov_router, "DATA_DIR", tmp_path)
    with TestClient(app) as c:
        yield c


def test_canonical_rejects_unknown_project(client):
    r = client.put(f"/api/coverage/{quote(TITLE)}/canonical", json={"project_id": "nope"})
    assert r.status_code == 422


def test_signoff_shopify_gate_succeeds(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": True})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["in_shopify"] is True


def test_variations_signoff_blocked_by_gap(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True})
    assert r.status_code == 409
    assert "missing" in r.json()["detail"].lower()


def test_variations_signoff_with_acknowledge_succeeds(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True, "acknowledge_gap": True})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["variations_complete"] is True


def test_unknown_title_404(client):
    r = client.post(f"/api/coverage/{quote('No Such Door')}/signoff",
                    json={"gate": "shopify", "value": True})
    assert r.status_code == 404


def test_unknown_gate_422(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "bogus", "value": True})
    assert r.status_code == 422


def test_exclusions_round_trip(client):
    r = client.put(f"/api/coverage/{quote(TITLE)}/exclusions",
                   json={"colors": ["Bisque", "Bisque"]})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["excluded_colors"] == ["Bisque"]


def test_revoking_gate_clears_it(client):
    client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                json={"gate": "shopify", "value": True})
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": False})
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["in_shopify"] is False
