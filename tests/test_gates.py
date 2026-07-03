"""M5: server-enforced generation gates + approval endpoints.

Stage A is absolute: no variant generation without an operator-approved
replica (GT-001, 409). Stage B caps resolved selections at the small-batch
limit while bulk is locked (GT-002, 422). Gates count RESOLVED selections —
the same list the worker will generate — and empty resolution is rejected
(GT-006, 400). Approval writes validate image-belongs-to-project (GT-005).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.qa.approvals as approvals_mod
import backend.routers.projects_generation as gen_mod
from backend.app import app
from backend.qa.approvals import ApprovalStore
from backend.qa.trust_config import TrustConfig, load_trust_config
from backend.state import ProjectStore, new_image_id


@pytest.fixture
def client(tmp_path, monkeypatch):
    approval_store = ApprovalStore(tmp_path / "approvals.json")
    monkeypatch.setattr(approvals_mod, "_default_store", approval_store)
    with TestClient(app) as c:
        c.app.state.project_store = ProjectStore(persist_dir=tmp_path / "projects")
        yield c


def _learned_project(client: TestClient, *, swatches: int = 3):
    """Create a project that has 'learned' (signature + replica with id)."""
    store = client.app.state.project_store
    project = store.create(name="Door 1", product_type="Cabinet Door")
    store.update(
        project.id,
        has_signature=True,
        learned_signature=b"sig",
        base_door_image=b"replica",
        base_image_id=new_image_id(),
        selected_swatches=[f"swatch_{i}" for i in range(swatches)],
    )
    return store.get(project.id)


def _fake_resolver(n: int):
    return lambda keys, door_style=None, material_type="wood": [
        {"wood_name": f"W{i}", "swatch_path": None, "wood_description": None,
         "reference_image": None}
        for i in range(n)
    ]


def _approve_replica(client: TestClient, project) -> None:
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": project.base_image_id, "verdict": "approved"},
    )
    assert resp.status_code == 200


# --- generation gates ---------------------------------------------------------


def test_unapproved_replica_blocks_generation(client, monkeypatch) -> None:
    project = _learned_project(client)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(3))
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 409
    assert "GT-001" in resp.json()["detail"]


def test_over_limit_while_bulk_locked_is_422(client, monkeypatch) -> None:
    project = _learned_project(client, swatches=6)
    _approve_replica(client, project)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(6))
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 422
    assert "GT-002" in resp.json()["detail"]


def test_empty_resolution_is_400(client, monkeypatch) -> None:
    project = _learned_project(client)
    _approve_replica(client, project)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(0))
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 400
    assert "GT-006" in resp.json()["detail"]


def test_approved_within_limit_starts_run(client, monkeypatch) -> None:
    project = _learned_project(client)
    _approve_replica(client, project)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(3))
    started: list[str] = []
    monkeypatch.setattr(
        gen_mod, "start_generation", lambda store, p, key: started.append(p.id)
    )
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 200
    assert started == [project.id]


def test_trust_config_parse_error_falls_back_conservative(tmp_path: Path) -> None:
    bad = tmp_path / "trust_config.json"
    bad.write_text("{not json")
    config = load_trust_config(bad)
    assert config.bulk_unlocked is False
    assert config.small_batch_limit == 5
    assert config.run_cost_cap_usd == 10.0
    # Missing file falls back the same way.
    assert load_trust_config(tmp_path / "missing.json") == TrustConfig()


def test_default_trust_config_file_is_conservative() -> None:
    config = load_trust_config()  # the committed backend/qa/trust_config.json
    assert config.bulk_unlocked is False
    assert config.small_batch_limit == 5


# --- approval endpoints -------------------------------------------------------


def test_approval_rejects_foreign_image_id(client) -> None:
    project = _learned_project(client)
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": "not-an-image-of-this-project", "verdict": "approved"},
    )
    assert resp.status_code == 400
    assert "GT-005" in resp.json()["detail"]


def test_approval_persists_and_reports_state(client) -> None:
    project = _learned_project(client)
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": project.base_image_id, "verdict": "approved"},
    )
    assert resp.status_code == 200
    assert resp.json()["replica_approved"] is True

    listing = client.get(f"/api/projects/{project.id}/approvals")
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["image_id"] == project.base_image_id
    assert items[0]["kind"] == "replica"
    assert items[0]["verdict"] == "approved"


def test_variant_approval_kind_derived(client) -> None:
    project = _learned_project(client)
    store = client.app.state.project_store
    record = store.record_result(project.id, "Oak", image_data=b"img")
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": record.image_id, "verdict": "rejected",
              "reasons": ["geometry_drift"]},
    )
    assert resp.status_code == 200
    items = client.get(f"/api/projects/{project.id}/approvals").json()
    got = next(a for a in items if a["image_id"] == record.image_id)
    assert got["kind"] == "variant"
    assert got["reasons"] == ["geometry_drift"]


def test_revocation_does_not_cancel_running_generation(client, monkeypatch) -> None:
    project = _learned_project(client)
    _approve_replica(client, project)
    store = client.app.state.project_store
    store.update(project.id, generation_status="running")

    # Operator rejects the replica mid-run: accepted, run untouched.
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": project.base_image_id, "verdict": "rejected",
              "reasons": ["geometry_drift"]},
    )
    assert resp.status_code == 200
    assert store.get(project.id).generation_status == "running"

    # But the NEXT generate is gated.
    store.update(project.id, generation_status="done")
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(3))
    blocked = client.post(
        f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"}
    )
    assert blocked.status_code == 409
    assert "GT-001" in blocked.json()["detail"]


def test_replica_approved_on_project_and_status_responses(client) -> None:
    project = _learned_project(client)
    before = client.get(f"/api/projects/{project.id}").json()
    assert before["replica_approved"] is False

    _approve_replica(client, project)
    after = client.get(f"/api/projects/{project.id}").json()
    assert after["replica_approved"] is True
    status = client.get(f"/api/projects/{project.id}/generate/status").json()
    assert status["replica_approved"] is True


def test_migrated_project_gets_replica_id_on_load(tmp_path: Path) -> None:
    # Old-format project: base_door.bin exists, manifest has no base_image_id.
    d = tmp_path / "legacy01"
    d.mkdir(parents=True)
    (d / "signature.bin").write_bytes(b"sig")
    (d / "base_door.bin").write_bytes(b"replica")
    (d / "manifest.json").write_text(json.dumps({
        "id": "legacy01", "name": "Legacy", "product_type": "Cabinet Door",
        "result_names": [], "errors": [],
    }))
    store = ProjectStore(persist_dir=tmp_path)
    project = store.get("legacy01")
    assert project is not None
    assert project.base_image_id is not None  # approvable without re-learn
    store.save("legacy01")
    reloaded = ProjectStore(persist_dir=tmp_path).get("legacy01")
    assert reloaded.base_image_id == project.base_image_id  # stable once saved


def test_rejudge_endpoint_validates_and_enqueues(client, monkeypatch) -> None:
    import backend.routers.qa as qa_router

    project = _learned_project(client)
    enqueued: list[tuple[str, str]] = []

    class FakeLane:
        def enqueue(self, store, project_id, image_id, api_key, *, kind, swatch_path=None):
            enqueued.append((image_id, kind))

    monkeypatch.setattr(qa_router, "get_qa_lane", lambda: FakeLane())

    ok = client.post(
        f"/api/projects/{project.id}/images/{project.base_image_id}/rejudge",
        headers={"X-API-Key": "k"},
    )
    assert ok.status_code == 200
    assert enqueued == [(project.base_image_id, "replica")]

    bad = client.post(
        f"/api/projects/{project.id}/images/not-mine/rejudge",
        headers={"X-API-Key": "k"},
    )
    assert bad.status_code == 400
    assert "GT-005" in bad.json()["detail"]


def test_approval_appends_ledger_record(client, monkeypatch, tmp_path) -> None:
    import backend.qa.reliability as rel
    import backend.routers.qa as qa_router

    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(
        qa_router, "append_record",
        lambda **kw: rel.append_record(ledger, **kw),
    )
    project = _learned_project(client)
    store = client.app.state.project_store
    # A done pipeline verdict exists for the replica at decision time.
    store.set_qa_verdict(
        project.id, project.base_image_id,
        {"verdict": "pass", "qa_status": "done", "reason": "ok"},
    )
    _approve_replica(client, project)

    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["pipeline_verdict"] == "pass"
    assert records[0]["human_verdict"] == "approved"
    assert records[0]["kind"] == "replica"


def test_ledger_failure_never_blocks_approval(client, monkeypatch) -> None:
    import backend.routers.qa as qa_router

    def boom(**kw):
        raise OSError("disk full")

    monkeypatch.setattr(qa_router, "append_record", boom)
    project = _learned_project(client)
    resp = client.post(
        f"/api/projects/{project.id}/approvals",
        json={"image_id": project.base_image_id, "verdict": "approved"},
    )
    assert resp.status_code == 200  # approval persisted despite ledger failure
    assert resp.json()["replica_approved"] is True


def test_reliability_endpoint_returns_aggregates(client) -> None:
    resp = client.get("/api/qa/reliability")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body and "by_kind" in body and "by_style_class" in body


def test_estimate_reports_gate_and_costs(client, monkeypatch) -> None:
    project = _learned_project(client)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(3))

    # Stage A: replica unapproved
    est = client.get(f"/api/projects/{project.id}/generate/estimate").json()
    assert est["gate_ok"] is False
    assert "GT-001" in est["gate_reason"]
    assert est["stage"] == "A"

    # Stage B: approved, within limit
    _approve_replica(client, project)
    est = client.get(f"/api/projects/{project.id}/generate/estimate").json()
    assert est["gate_ok"] is True
    assert est["stage"] == "B"
    assert est["images"] == 3
    assert abs(est["est_cost_usd"] - 3 * 0.134) < 1e-9
    assert abs(est["worst_case_usd"] - (3 * 0.134 + 10.0)) < 1e-9

    # Over limit while bulk locked
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(7))
    est = client.get(f"/api/projects/{project.id}/generate/estimate").json()
    assert est["gate_ok"] is False
    assert "GT-002" in est["gate_reason"]

    # Empty resolution
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(0))
    est = client.get(f"/api/projects/{project.id}/generate/estimate").json()
    assert est["gate_ok"] is False
    assert "GT-006" in est["gate_reason"]


def _write_trust_config(path: Path, **overrides) -> Path:
    base = {
        "small_batch_limit": 5, "bulk_unlocked": False,
        "bulk_unlocked_style_classes": [], "max_auto_retries": 2,
        "run_cost_cap_usd": 10.0, "image_cost_usd": 0.134,
    }
    base.update(overrides)
    path.write_text(json.dumps(base))
    return path


def test_style_class_unlock_lifts_gt002(client, monkeypatch, tmp_path) -> None:
    from backend.qa.trust_config import load_trust_config as real_load

    project = _learned_project(client, swatches=8)
    client.app.state.project_store.update(project.id, door_style="shaker")
    _approve_replica(client, project)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(8))
    started: list[str] = []
    monkeypatch.setattr(
        gen_mod, "start_generation", lambda store, p, key: started.append(p.id)
    )

    # Locked: 8 resolved > 5 -> GT-002.
    cfg = _write_trust_config(tmp_path / "tc.json")
    monkeypatch.setattr(gen_mod, "load_trust_config", lambda: real_load(cfg))
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 422

    # Unlock shaker's style-class (frame_standard): bulk allowed for it only.
    _write_trust_config(cfg, bulk_unlocked_style_classes=["frame_standard"])
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 200
    assert started == [project.id]

    est = client.get(f"/api/projects/{project.id}/generate/estimate")
    # estimate uses its own load; patch it too for stage reporting
    monkeypatch.setattr(
        "backend.routers.projects_generation.load_trust_config", lambda: real_load(cfg)
    )
    est = client.get(f"/api/projects/{project.id}/generate/estimate").json()
    assert est["stage"] == "C"

    # Config edit re-locks the NEXT request — no restart needed.
    _write_trust_config(cfg, bulk_unlocked_style_classes=[])
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 422


def test_global_bulk_unlock(client, monkeypatch, tmp_path) -> None:
    from backend.qa.trust_config import load_trust_config as real_load

    project = _learned_project(client, swatches=40)
    _approve_replica(client, project)
    monkeypatch.setattr(gen_mod, "build_selections", _fake_resolver(40))
    monkeypatch.setattr(gen_mod, "start_generation", lambda store, p, key: None)
    cfg = _write_trust_config(tmp_path / "tc.json", bulk_unlocked=True)
    monkeypatch.setattr(gen_mod, "load_trust_config", lambda: real_load(cfg))
    resp = client.post(f"/api/projects/{project.id}/generate", headers={"X-API-Key": "k"})
    assert resp.status_code == 200
