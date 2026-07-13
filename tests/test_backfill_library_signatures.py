"""Tests for scripts/backfill_library_signatures.py (library signature backfill)."""

import json
from pathlib import Path

from scripts.backfill_library_signatures import build_plan


def make_source(
    projects_dir: Path,
    pid: str,
    name: str,
    *,
    base_image_id: str = "bid-source-1",
    material_type: str = "wood",
) -> None:
    d = projects_dir / pid
    d.mkdir(parents=True)
    manifest = {
        "id": pid,
        "name": name,
        "product_type": "Cabinet Door",
        "material_type": material_type,
        "door_style": "recessed_panel",
        "corner_style": "sharp",
        "style_notes": "narrow frame",
        "profile_spec": ["flat outer edge"],
        "profile_image_path": None,
        "variant_hint_mode": "lean",
        "gemini_model": "gemini-3-pro-image-preview",
        "selected_swatches": ["cherry-select"],
        "upload_filename": "door.png",
        "result_names": [],
        "result_records": [],
        "base_image_id": base_image_id,
        "qa_verdicts": {base_image_id: {"verdict": "pass", "kind": "replica"}},
        "errors": [],
        "signature_version": 0,
        "version_count": 0,
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    (d / "signature.bin").write_bytes(b"SIGNATURE-BYTES")
    (d / "base_door.bin").write_bytes(b"REPLICA-BYTES")
    (d / "upload.bin").write_bytes(b"UPLOAD-BYTES")


def make_library(
    projects_dir: Path, pid: str, name: str, *, n_results: int = 2
) -> None:
    d = projects_dir / pid
    d.mkdir(parents=True)
    manifest = {
        "id": pid,
        "name": name,
        "product_type": "Cabinet Door",
        "material_type": "wood",
        "door_style": None,
        "corner_style": "sharp",
        "style_notes": "",
        "gemini_model": "gemini-3-pro-image-preview",
        "selected_swatches": [],
        "upload_filename": None,
        "result_names": [f"Wood {i}" for i in range(n_results)],
        "errors": [],
        "signature_version": 0,
        "version_count": 0,
    }
    (d / "manifest.json").write_text(json.dumps(manifest))
    for i in range(n_results):
        (d / f"result_{i}.bin").write_bytes(b"IMG-%d" % i)


def make_approvals(path: Path, image_ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "approvals": [
                    {
                        "image_id": iid,
                        "project_id": "src",
                        "kind": "replica",
                        "verdict": "approved",
                        "reasons": [],
                        "note": "",
                        "decided_at": "2026-01-01T00:00:00+00:00",
                    }
                    for iid in image_ids
                ]
            }
        )
    )


def test_build_plan_copies_generation_fields(tmp_path):
    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    make_source(projects, "src00001", "frontier")
    make_library(projects, "lib00001", "Frontier_new_wm", n_results=3)
    make_approvals(approvals, ["bid-source-1"])

    items, skipped = build_plan(projects, approvals, {"lib00001": "src00001"})

    assert skipped == []
    assert len(items) == 1
    item = items[0]
    assert item.library_id == "lib00001"
    assert item.source_id == "src00001"
    assert item.fields["door_style"] == "recessed_panel"
    assert item.fields["corner_style"] == "sharp"
    assert item.fields["material_type"] == "wood"
    assert item.fields["style_notes"] == "narrow frame"
    assert item.fields["profile_spec"] == ["flat outer edge"]
    assert item.fields["variant_hint_mode"] == "lean"
    assert item.fields["base_image_id"] == "bid-source-1"
    assert item.fields["upload_filename"] == "door.png"
    assert item.replica_verdict == {"verdict": "pass", "kind": "replica"}
    assert item.has_upload is True
    assert item.result_count_before == 3
    assert item.warnings == []


def test_build_plan_detects_half_backfilled(tmp_path):
    """Library with signature.bin but manifest lacking base_image_id flags as HALF-BACKFILLED."""
    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    make_source(projects, "src00001", "frontier")
    make_library(projects, "lib00001", "Frontier_new_wm")
    # Simulate crash mid-apply: signature.bin written, but manifest never updated
    (projects / "lib00001" / "signature.bin").write_bytes(b"SIGNATURE-BYTES")
    make_approvals(approvals, ["bid-source-1"])

    items, skipped = build_plan(projects, approvals, {"lib00001": "src00001"})

    assert items == []
    assert len(skipped) == 1
    assert "HALF-BACKFILLED" in skipped[0]


def test_build_plan_skips_backfilled_and_pending(tmp_path):
    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    make_source(projects, "src00001", "frontier")
    make_library(projects, "lib00001", "Frontier_new_wm")
    # Already backfilled: library has a signature and complete manifest.
    (projects / "lib00001" / "signature.bin").write_bytes(b"X")
    # Give it a base_image_id so it's not detected as half-backfilled
    manifest = json.loads((projects / "lib00001" / "manifest.json").read_text())
    manifest["base_image_id"] = "bid-001"
    (projects / "lib00001" / "manifest.json").write_text(json.dumps(manifest))

    make_library(projects, "lib00002", "Durango_new_wm")
    make_approvals(approvals, ["bid-source-1"])

    items, skipped = build_plan(
        projects, approvals, {"lib00001": "src00001", "lib00002": None}
    )

    assert items == []
    assert len(skipped) == 2
    assert any("already has signature.bin" in s for s in skipped)
    assert any("pending visual confirmation" in s for s in skipped)


def test_build_plan_warns_on_unapproved_replica(tmp_path):
    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    make_source(projects, "src00001", "indiana")
    make_library(projects, "lib00001", "Indiana_new_wm")
    make_approvals(approvals, [])  # nothing approved

    items, skipped = build_plan(projects, approvals, {"lib00001": "src00001"})

    assert len(items) == 1
    assert any("not approved" in w for w in items[0].warnings)


def test_apply_backfills_and_preserves_results(tmp_path):
    from scripts.backfill_library_signatures import apply_plan, verify

    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    backup = tmp_path / "backup"
    make_source(projects, "src00001", "frontier")
    make_library(projects, "lib00001", "Frontier_new_wm", n_results=3)
    make_approvals(approvals, ["bid-source-1"])
    result_bytes_before = [
        (projects / "lib00001" / f"result_{i}.bin").read_bytes() for i in range(3)
    ]

    items, _ = build_plan(projects, approvals, {"lib00001": "src00001"})
    apply_plan(projects, items, backup)

    lib_dir = projects / "lib00001"
    assert (lib_dir / "signature.bin").read_bytes() == b"SIGNATURE-BYTES"
    assert (lib_dir / "base_door.bin").read_bytes() == b"REPLICA-BYTES"
    assert (lib_dir / "upload.bin").read_bytes() == b"UPLOAD-BYTES"
    # Backup of the pre-write manifest exists.
    assert (backup / "lib00001" / "manifest.json").exists()
    assert json.loads((backup / "lib00001" / "files_added.json").read_text()) == [
        "signature.bin",
        "base_door.bin",
        "upload.bin",
    ]
    # Results untouched, byte for byte.
    for i in range(3):
        assert (lib_dir / f"result_{i}.bin").read_bytes() == result_bytes_before[i]
    # Manifest carries the generation-critical fields + replica verdict.
    manifest = json.loads((lib_dir / "manifest.json").read_text())
    assert manifest["door_style"] == "recessed_panel"
    assert manifest["base_image_id"] == "bid-source-1"
    assert manifest["upload_filename"] == "door.png"
    assert manifest["qa_verdicts"]["bid-source-1"] == {
        "verdict": "pass",
        "kind": "replica",
    }
    # Source untouched.
    src_manifest = json.loads((projects / "src00001" / "manifest.json").read_text())
    assert src_manifest["name"] == "frontier"
    # Post-verify passes: fresh store sees signature + replica + 3 results.
    assert verify(projects, items) == []
    # Idempotent: a second plan pass now skips the library.
    items2, skipped2 = build_plan(projects, approvals, {"lib00001": "src00001"})
    assert items2 == []
    assert any("already has signature.bin" in s for s in skipped2)
