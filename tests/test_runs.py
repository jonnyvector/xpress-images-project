"""M2: generation-run manifests — planned work, attempts, spend counters.

The manifest is the persisted, inspectable record of one generation run and
the atomicity authority for the cost cap: counters increment under a lock
BEFORE each API submission. A manifest still ``running`` at store load means
the process died mid-run — it flips to ``truncated`` and is surfaced, never
silently reported done.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import backend.worker as worker
from backend.runs import RunManifest
from backend.state import ProjectStore


def test_create_persists_planned_and_snapshot(tmp_path: Path) -> None:
    config = {"run_cost_cap_usd": 10.0, "image_cost_usd": 0.134}
    run = RunManifest.create(
        tmp_path, planned=[("Oak", "id-oak"), ("Cherry", "id-cherry")], config=config
    )
    config["run_cost_cap_usd"] = 999.0  # mutate source after create

    data = json.loads((tmp_path / "runs" / f"{run.run_id}.json").read_text())
    assert data["status"] == "running"
    assert data["planned"] == [
        {"wood_name": "Oak", "image_id": "id-oak"},
        {"wood_name": "Cherry", "image_id": "id-cherry"},
    ]
    assert data["config_snapshot"]["run_cost_cap_usd"] == 10.0  # snapshot immutable
    assert data["images_submitted"] == 0
    assert data["unconsented_images"] == 0
    assert data["started_at"]


def test_submit_counters_are_atomic_and_split(tmp_path: Path) -> None:
    run = RunManifest.create(tmp_path, planned=[], config={})
    n = 40
    with ThreadPoolExecutor(max_workers=8) as pool:
        for f in [pool.submit(run.submit) for _ in range(n)]:
            f.result()
        for f in [pool.submit(run.submit, unconsented=True) for _ in range(10)]:
            f.result()

    data = json.loads(run.path.read_text())
    assert data["images_submitted"] == n + 10  # no lost increments
    assert data["unconsented_images"] == 10  # unconsented tracked separately


def test_attempts_append_and_finish(tmp_path: Path) -> None:
    run = RunManifest.create(tmp_path, planned=[("Oak", "id-1")], config={})
    run.record_attempt(image_id="id-1", wood_name="Oak", attempt=0, verdict=None)
    run.record_attempt(image_id="id-2", wood_name="Oak", attempt=1, verdict="regenerate",
                       active=False)
    run.finish("done")

    data = json.loads(run.path.read_text())
    assert data["status"] == "done"
    assert [a["image_id"] for a in data["attempts"]] == ["id-1", "id-2"]
    assert data["attempts"][1]["verdict"] == "regenerate"
    assert data["attempts"][1]["active"] is False


def test_running_manifest_flips_to_truncated_on_load(tmp_path: Path) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    pdir = tmp_path / project.id
    run = RunManifest.create(pdir, planned=[("Oak", "id-1")], config={})
    assert json.loads(run.path.read_text())["status"] == "running"

    reloaded_store = ProjectStore(persist_dir=tmp_path)  # simulates process restart
    assert json.loads(run.path.read_text())["status"] == "truncated"
    reloaded = reloaded_store.get(project.id)
    assert reloaded is not None
    assert run.run_id in reloaded.truncated_runs  # surfaced, not silent

    # A finished manifest is left alone and not surfaced.
    run2 = RunManifest.create(pdir, planned=[], config={})
    run2.finish("done")
    third = ProjectStore(persist_dir=tmp_path).get(project.id)
    assert third is not None
    assert run2.run_id not in third.truncated_runs


class _FakeVariationResult:
    error = None
    image_data = b"variant-img"
    thought_signature = None


class _FakeGenerator:
    def __init__(self, **kwargs: object) -> None:
        pass

    def generate_variation(self, **kwargs: object) -> _FakeVariationResult:
        return _FakeVariationResult()

    def generate_variation_from_reference(self, **kwargs: object) -> _FakeVariationResult:
        return _FakeVariationResult()


def test_run_generation_creates_and_closes_manifest(tmp_path, monkeypatch) -> None:
    store = ProjectStore(persist_dir=tmp_path)
    project = store.create(name="Door 1", product_type="Cabinet Door")
    monkeypatch.setattr(worker, "DoorGenerator", _FakeGenerator)
    monkeypatch.setattr(worker, "OUTPUT_DIR", tmp_path.parent / "out")

    selections = [
        {"wood_name": "Oak", "swatch_path": None, "wood_description": None,
         "reference_image": None, "image_id": "pre-Oak"},
        {"wood_name": "Cherry", "swatch_path": None, "wood_description": None,
         "reference_image": None, "image_id": "pre-Cherry"},
    ]
    run = RunManifest.create(
        tmp_path / project.id,
        planned=[(s["wood_name"], s["image_id"]) for s in selections],
        config={},
    )
    worker._run_generation(
        store, project.id, "key", b"sig", "recessed_panel", selections,
        "9:16", "", run=run,
    )

    data = json.loads(run.path.read_text())
    assert data["status"] == "done"
    assert data["images_submitted"] == 2  # incremented before each submission
    # Submission-time identity: stored records carry the planned image_ids.
    refreshed = store.get(project.id)
    assert refreshed is not None
    assert {r.image_id for r in refreshed.results} == {"pre-Oak", "pre-Cherry"}
    assert {a["image_id"] for a in data["attempts"]} == {"pre-Oak", "pre-Cherry"}
