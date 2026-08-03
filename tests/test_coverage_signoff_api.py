import json
import shutil
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import backend.routers.coverage as cov_router
from backend.app import app
from backend.signoff import SIGNOFF_FILENAME
from backend.state import ProjectStore, ResultRecord

TITLE = "AR756 Thermofoil Cabinet Door"


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    """Point the router at a scratch data dir seeded with the real CSVs."""
    src = Path("docs/sales/data")
    for name in ("thermofoil_cabinet_doors.csv",):
        shutil.copy(src / name, tmp_path / name)
    monkeypatch.setattr(cov_router, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def client(data_dir, tmp_path, monkeypatch):
    with TestClient(app) as c:
        # The lifespan wires up the real output/.projects store; swap it for a
        # scratch one so these tests never depend on the operator's projects.
        monkeypatch.setattr(
            app.state, "project_store", ProjectStore(persist_dir=tmp_path / "projects")
        )
        yield c


def _canonical_project(client, colours: list[str]) -> str:
    """Create a project with these colours and make it TITLE's canonical."""
    store = app.state.project_store
    project = store.create(name="AR756", product_type="Cabinet Door", material_type="rtf")
    project.results = [
        ResultRecord(image_id=f"img{i}", wood_name=c) for i, c in enumerate(colours)
    ]
    r = client.put(f"/api/coverage/{quote(TITLE)}/canonical", json={"project_id": project.id})
    assert r.status_code == 200
    return project.id


def _record(data_dir: Path) -> dict:
    return json.loads((data_dir / SIGNOFF_FILENAME).read_text())


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
    # A real gap: a canonical project exists and is missing most of the palette.
    _canonical_project(client, ["Bisque"])
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True})
    assert r.status_code == 409
    assert "missing" in r.json()["detail"].lower()


def test_variations_signoff_with_acknowledge_succeeds(client, data_dir):
    _canonical_project(client, ["Bisque"])
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True, "acknowledge_gap": True})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["variations_complete"] is True
    stamp = _record(data_dir)[TITLE]["variations_complete"]
    assert stamp["acknowledged_gap"] is True
    assert stamp["result_count"] == 1


def test_no_canonical_project_is_not_a_gap(client, data_dir):
    # Nothing to compare against is an absence of evidence, not a gap: the
    # guard must not fire and the record must not claim an acknowledgement.
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True})
    assert r.status_code == 200
    stamp = _record(data_dir)[TITLE]["variations_complete"]
    assert stamp["acknowledged_gap"] is False


def test_no_canonical_project_stamps_null_result_count(client, data_dir):
    # 0 would make the row read stale the moment a canonical project is picked.
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True})
    assert r.status_code == 200
    assert _record(data_dir)[TITLE]["variations_complete"]["result_count"] is None

    _canonical_project(client, ["Bisque", "Niagara"])
    row = next(p for c in client.get("/api/coverage").json()["categories"]
               for p in c["products"] if p["title"] == TITLE)
    assert row["stale"] is False


def test_acknowledge_gap_ignored_when_there_is_no_canonical(client, data_dir):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True, "acknowledge_gap": True})
    assert r.status_code == 200
    assert _record(data_dir)[TITLE]["variations_complete"]["acknowledged_gap"] is False


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


CORRUPT = '<<<<<<< HEAD\n{"Other Door": {"in_shopify": {"by": "j", "at": "t"}}}\n'


@pytest.mark.parametrize(
    ("method", "endpoint", "body"),
    [
        ("post", "signoff", {"gate": "shopify", "value": True}),
        ("put", "canonical", None),  # filled in with a real project id
        ("put", "exclusions", {"colors": ["Bisque"]}),
    ],
)
def test_corrupt_record_returns_500_and_writes_nothing(
    client, data_dir, method, endpoint, body
):
    # The record is git-tracked human judgment: a writer that cannot read it
    # must stop, not replace it with its own one-entry view.
    if body is None:
        project = app.state.project_store.create(
            name="AR756", product_type="Cabinet Door", material_type="rtf"
        )
        body = {"project_id": project.id}
    (data_dir / SIGNOFF_FILENAME).write_text(CORRUPT)

    r = getattr(client, method)(f"/api/coverage/{quote(TITLE)}/{endpoint}", json=body)
    assert r.status_code == 500
    assert SIGNOFF_FILENAME in r.json()["detail"]
    assert (data_dir / SIGNOFF_FILENAME).read_text() == CORRUPT


def test_writers_hold_the_lock_across_load_and_save(client, monkeypatch):
    """Load and save must happen inside one critical section.

    Two concurrent writers each load the whole record and save the whole
    record, so a lock around save alone still loses the loser's entry.
    """
    from backend.signoff import SIGNOFF_LOCK

    seen: list[tuple[str, bool]] = []
    real_load = cov_router.load_signoff_strict
    real_save = cov_router.save_signoff

    def spy_load(d):
        seen.append(("load", SIGNOFF_LOCK.locked()))
        return real_load(d)

    def spy_save(d, record):
        seen.append(("save", SIGNOFF_LOCK.locked()))
        return real_save(d, record)

    monkeypatch.setattr(cov_router, "load_signoff_strict", spy_load)
    monkeypatch.setattr(cov_router, "save_signoff", spy_save)

    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": True})
    assert r.status_code == 200
    assert seen == [("load", True), ("save", True)]


def test_revoking_gate_clears_it(client):
    client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                json={"gate": "shopify", "value": True})
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": False})
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["in_shopify"] is False
