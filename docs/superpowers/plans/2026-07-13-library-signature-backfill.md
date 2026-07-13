# Library Signature Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill replica (`base_door.bin`), thought signature (`signature.bin`), upload, and generation-critical manifest fields into the 24 `*_new_wm` library projects so the UI can generate variations from them.

**Architecture:** A single reusable script, `scripts/backfill_library_signatures.py`, with an explicit library→source mapping table. Planning reads manifests as plain JSON (read-only); applying goes through `ProjectStore` so persistence stays canonical. Dry-run by default, `--apply` writes, `--compare-report` emits an HTML side-by-side for the 5 ambiguous doors.

**Tech Stack:** Python 3.12, stdlib only + existing `backend.state.ProjectStore` / `backend.qa.approvals.ApprovalStore`. Tests with pytest via `uv run pytest`.

**Spec:** `docs/superpowers/specs/2026-07-13-library-signature-backfill-design.md`

## Global Constraints

- Single-writer rule: the script MUST abort if anything is listening on port 8000 (dev server). Real runs happen with the server stopped.
- Source projects are strictly read-only. Never write to a source project dir.
- Never modify library `result_*.bin` contents, project `name`, `id`, or `selected_swatches`.
- `--dry-run` is the default behavior; writes happen only with `--apply`.
- Idempotent: skip any library project that already has `signature.bin`.
- Backups go to `output/.onboard/backfill_backup/<library_id>/` before any write.
- `base_image_id` is copied verbatim from the source (carries the global replica approval; GT-001 passes). NEVER mint a new id.
- Never trigger re-learn on a library project (`worker.py:342` wipes results).
- Run all commands from the repo root: `/Users/jonathanhicks/dev/xpress-images-project`.

---

### Task 1: Plan builder (`build_plan`) with tests

**Files:**
- Create: `scripts/backfill_library_signatures.py`
- Test: `tests/test_backfill_library_signatures.py`

**Interfaces:**
- Produces: `PlanItem` dataclass; `build_plan(projects_dir: Path, approvals_path: Path, mapping: dict[str, str | None]) -> tuple[list[PlanItem], list[str]]` (items, skipped-reasons). Task 2 consumes `PlanItem` fields exactly as defined here.
- Produces (test helpers reused by Task 2 tests): `make_source(...)`, `make_library(...)`, `make_approvals(...)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill_library_signatures.py`:

```python
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


def test_build_plan_skips_backfilled_and_pending(tmp_path):
    projects = tmp_path / "projects"
    approvals = tmp_path / "approvals.json"
    make_source(projects, "src00001", "frontier")
    make_library(projects, "lib00001", "Frontier_new_wm")
    # Already backfilled: library has a signature.
    (projects / "lib00001" / "signature.bin").write_bytes(b"X")
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_backfill_library_signatures.py -v`
Expected: FAIL at import — `ModuleNotFoundError: No module named 'scripts.backfill_library_signatures'` (or missing `scripts/__init__.py` — if so, `scripts/` already has `__pycache__` from existing scripts run as files; add nothing, the import works because pytest rootdir is the repo and `scripts` contains `.py` files. If the import truly fails on package resolution, create empty `scripts/__init__.py`.)

- [ ] **Step 3: Write the plan-builder implementation**

Create `scripts/backfill_library_signatures.py`:

```python
"""Backfill replica + thought signature into *_new_wm library projects.

Library projects (*_new_wm) hold the finished watermark-cleaned variant sets
but were created by copying variant images only — no signature.bin (thought
signature), no base_door.bin (approved replica), no upload.bin, and manifests
missing door_style / base_image_id. The UI therefore cannot generate more
variations from them. This script copies those files plus the generation-
critical manifest fields from each door's source (working) project.

Safety: run from the repo root with the dev server STOPPED (ProjectStore is
not multi-process safe; the script aborts if port 8000 is listening).
Dry-run by default; --apply writes. Idempotent: libraries that already have
signature.bin are skipped. Source projects are never written. base_image_id
is copied VERBATIM so the replica's existing global approval carries over
(GT-001). Spec: docs/superpowers/specs/2026-07-13-library-signature-backfill-design.md
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import socket
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.qa.approvals import ApprovalStore  # noqa: E402
from backend.state import ProjectStore  # noqa: E402

PROJECTS_DIR = REPO_ROOT / "output" / ".projects"
APPROVALS_PATH = REPO_ROOT / "output" / ".qa" / "approvals.json"
BACKUP_DIR = REPO_ROOT / "output" / ".onboard" / "backfill_backup"
COMPARE_REPORT = REPO_ROOT / "output" / ".onboard" / "backfill_compare.html"

# library_id -> source_id. None = pending visual confirmation (CANDIDATES).
# Derived 2026-07-13 by case-insensitive name-stem match, source must hold
# signature.bin + base_door.bin. Inventory: spec §Inventory.
MAPPING: dict[str, str | None] = {
    "123fe10f": "9f98e1fa",  # Campbell_new_wm      <- campbell
    "12d5f927": "a3453f05",  # Hamilton_new_wm      <- Hamilton Cabinet Door
    "2246bbc1": "02afd676",  # Connecticut_new_wm   <- connecticut
    "42a5ceae": None,        # Shaker_new_wm        — ambiguous
    "473248ee": "ca7c7f92",  # Josephine_new_wm     <- Josephine
    "4fdd9a63": "6d2bb325",  # Isabella_new_wm      <- isabella
    "599471c0": "a2c466f8",  # Arcadia_new_wm       <- arcadia
    "5b1939b4": "b558a816",  # Hayes_new_wm         <- hayes
    "5d811e2a": "5357bc46",  # Indiana_new_wm       <- indiana (replica unapproved)
    "82a8b0b7": "9e726e6c",  # Eldridge_new_wm      <- Eldridge
    "8ec7f68a": "5875fc02",  # Laguna_new_wm        <- Laguna
    "950e8411": "a9f04868",  # Frontier_new_wm      <- frontier
    "9bce8708": "b48dfef2",  # Artesia_new_wm       <- artesia
    "9d8a5618": None,        # Highpointe_new_wm    — ambiguous
    "ac084bf5": "ec593b7e",  # Estrella_new_wm      <- estrella
    "c3ac38ec": "c9ff205d",  # Alpine_new_wm        <- alpine
    "c81e6ddf": None,        # Durango_new_wm       — ambiguous
    "d0d227d0": "2564359f",  # Adobe_new_wm         <- adobe
    "dc8e7e9a": "dcf543e4",  # Kennedy_new_wm       <- Kennedy
    "dca2a561": None,        # Graham_new_wm        — ambiguous
    "defe8a7d": "35113f5a",  # Cascade_new_wm       <- cascade
    "e56a767d": None,        # Mission_new_wm       — ambiguous
    "ef5204ed": "7ef841e3",  # Jasper_new_wm        <- jasper
    "f3910c7d": "1de2743f",  # Cougar_new_wm        <- Cougar
}

# Candidate source ids for the doors pending visual confirmation.
# (rtf 'shaker' be9cf476 excluded: library projects are all wood.)
CANDIDATES: dict[str, list[str]] = {
    "42a5ceae": ["6176c0db"],              # Shaker: minimal
    "9d8a5618": ["045eb318", "0894d760"],  # Highpointe
    "c81e6ddf": ["92e60a19", "2b51d74d"],  # Durango
    "dca2a561": ["18460a95", "906db949"],  # Graham
    "e56a767d": ["b2bc733b", "7634b572", "27eef02f"],  # Mission
}

COPY_FIELDS = (
    "door_style",
    "corner_style",
    "material_type",
    "style_notes",
    "profile_spec",
    "profile_image_path",
    "variant_hint_mode",
    "base_image_id",
    "upload_filename",
)


@dataclass
class PlanItem:
    library_id: str
    library_name: str
    source_id: str
    source_name: str
    fields: dict
    has_upload: bool
    result_count_before: int
    replica_verdict: dict | None = None
    warnings: list[str] = field(default_factory=list)


def _read_manifest(projects_dir: Path, pid: str) -> dict:
    return json.loads((projects_dir / pid / "manifest.json").read_text())


def build_plan(
    projects_dir: Path,
    approvals_path: Path,
    mapping: dict[str, str | None],
) -> tuple[list[PlanItem], list[str]]:
    """Read-only planning pass. Returns (items to apply, skip/abort reasons)."""
    approved = (
        ApprovalStore(approvals_path).approved_ids()
        if approvals_path.exists()
        else frozenset()
    )
    items: list[PlanItem] = []
    skipped: list[str] = []
    for lib_id, src_id in mapping.items():
        if src_id is None:
            skipped.append(f"{lib_id}: pending visual confirmation (see CANDIDATES)")
            continue
        lib_dir = projects_dir / lib_id
        src_dir = projects_dir / src_id
        if (lib_dir / "signature.bin").exists():
            skipped.append(f"{lib_id}: already has signature.bin — idempotent skip")
            continue
        lib = _read_manifest(projects_dir, lib_id)
        src = _read_manifest(projects_dir, src_id)
        missing = [
            f for f in ("signature.bin", "base_door.bin") if not (src_dir / f).exists()
        ]
        if missing:
            skipped.append(f"{lib_id}: source {src_id} missing {missing} — NOT applied")
            continue
        warnings: list[str] = []
        bid = src.get("base_image_id")
        if bid not in approved:
            warnings.append(
                "source replica not in global approval store — GT-001 will gate "
                "generation until the replica is approved in the UI"
            )
        if src.get("material_type", "wood") != lib.get("material_type", "wood"):
            warnings.append(
                f"material_type mismatch: source={src.get('material_type')} "
                f"library={lib.get('material_type')}"
            )
        n_results = len(lib.get("result_records") or lib.get("result_names") or [])
        items.append(
            PlanItem(
                library_id=lib_id,
                library_name=lib["name"],
                source_id=src_id,
                source_name=src["name"],
                fields={k: src.get(k) for k in COPY_FIELDS},
                has_upload=(src_dir / "upload.bin").exists(),
                result_count_before=n_results,
                replica_verdict=src.get("qa_verdicts", {}).get(bid) if bid else None,
                warnings=warnings,
            )
        )
    return items, skipped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_backfill_library_signatures.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Lint and commit**

```bash
npm run lint
git add scripts/backfill_library_signatures.py tests/test_backfill_library_signatures.py
git commit -m "feat(backfill): plan builder for library signature backfill"
```

---

### Task 2: Apply + backup + verify with tests

**Files:**
- Modify: `scripts/backfill_library_signatures.py` (append functions)
- Test: `tests/test_backfill_library_signatures.py` (append test)

**Interfaces:**
- Consumes: `PlanItem`, `build_plan` from Task 1 (exact fields as defined there).
- Produces: `apply_plan(projects_dir: Path, items: list[PlanItem], backup_dir: Path) -> None`; `verify(projects_dir: Path, items: list[PlanItem]) -> list[str]` (empty list = all good); `server_running(port: int = 8000) -> bool`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_backfill_library_signatures.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_backfill_library_signatures.py::test_apply_backfills_and_preserves_results -v`
Expected: FAIL — `ImportError: cannot import name 'apply_plan'`

- [ ] **Step 3: Implement apply/verify/guard**

Append to `scripts/backfill_library_signatures.py`:

```python
def apply_plan(
    projects_dir: Path, items: list[PlanItem], backup_dir: Path
) -> None:
    """Write signature/replica/upload + manifest fields via ProjectStore.

    Mutation idiom mirrors the routers: get() -> set fields -> save(id).
    Source dirs are only ever read.
    """
    store = ProjectStore(projects_dir)
    for item in items:
        lib_dir = projects_dir / item.library_id
        src_dir = projects_dir / item.source_id

        bdir = backup_dir / item.library_id
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lib_dir / "manifest.json", bdir / "manifest.json")
        files_added = ["signature.bin", "base_door.bin"] + (
            ["upload.bin"] if item.has_upload else []
        )
        (bdir / "files_added.json").write_text(json.dumps(files_added))

        project = store.get(item.library_id)
        if project is None:
            raise RuntimeError(f"{item.library_id} not loaded by ProjectStore")
        project.learned_signature = (src_dir / "signature.bin").read_bytes()
        project.base_door_image = (src_dir / "base_door.bin").read_bytes()
        project.has_signature = True
        f = item.fields
        project.door_style = f["door_style"]
        project.corner_style = f["corner_style"] or "sharp"
        project.material_type = f["material_type"] or "wood"
        project.style_notes = f["style_notes"] or ""
        project.profile_spec = f["profile_spec"]
        project.profile_image_path = f["profile_image_path"]
        project.variant_hint_mode = f["variant_hint_mode"] or "styled"
        project.base_image_id = f["base_image_id"]
        if item.replica_verdict is not None and f["base_image_id"]:
            project.qa_verdicts[f["base_image_id"]] = item.replica_verdict
        store.save(item.library_id)
        if item.has_upload:
            store.save_upload(
                item.library_id,
                f["upload_filename"] or f"{item.source_name}.png",
                (src_dir / "upload.bin").read_bytes(),
            )


def verify(projects_dir: Path, items: list[PlanItem]) -> list[str]:
    """Reload everything through a fresh ProjectStore; return problems."""
    fresh = ProjectStore(projects_dir)
    problems: list[str] = []
    for item in items:
        p = fresh.get(item.library_id)
        if p is None:
            problems.append(f"{item.library_id}: missing after apply")
            continue
        if not p.has_signature or p.learned_signature is None:
            problems.append(f"{item.library_id}: no signature after apply")
        if p.base_door_image is None:
            problems.append(f"{item.library_id}: no replica after apply")
        if len(p.results) != item.result_count_before:
            problems.append(
                f"{item.library_id}: result count changed "
                f"{item.result_count_before} -> {len(p.results)}"
            )
    return problems


def server_running(port: int = 8000) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/test_backfill_library_signatures.py -v`
Expected: 4 PASSED

Also run the existing suite to prove nothing regressed:
Run: `uv run pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
npm run lint
git add scripts/backfill_library_signatures.py tests/test_backfill_library_signatures.py
git commit -m "feat(backfill): apply + backup + post-verify for library signature backfill"
```

---

### Task 3: CLI wiring + compare report

**Files:**
- Modify: `scripts/backfill_library_signatures.py` (append `compare_report` + `main`)

**Interfaces:**
- Consumes: everything from Tasks 1–2.
- Produces: CLI — `uv run python scripts/backfill_library_signatures.py` (dry run), `--apply`, `--compare-report`, `--port N`.

- [ ] **Step 1: Implement compare report + main**

Append to `scripts/backfill_library_signatures.py`:

```python
def _img_tag(path: Path, width: int = 220) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b64}" width="{width}" loading="lazy">'


def compare_report(projects_dir: Path, out_path: Path) -> None:
    """HTML side-by-side: each ambiguous library's variants vs candidate replicas."""
    rows = []
    for lib_id, cand_ids in CANDIDATES.items():
        lib = _read_manifest(projects_dir, lib_id)
        lib_dir = projects_dir / lib_id
        samples = [
            _img_tag(lib_dir / f"result_{i}.bin")
            for i in range(3)
            if (lib_dir / f"result_{i}.bin").exists()
        ]
        cands = []
        for cid in cand_ids:
            c = _read_manifest(projects_dir, cid)
            base = projects_dir / cid / "base_door.bin"
            img = _img_tag(base) if base.exists() else "(no replica)"
            cands.append(
                f"<figure><figcaption><b>{cid}</b> — {c['name']} "
                f"(style: {c.get('door_style')})</figcaption>{img}</figure>"
            )
        rows.append(
            f"<h2>{lib['name']} ({lib_id})</h2>"
            f"<h3>Library variants (first 3)</h3><div class=row>{''.join(samples)}</div>"
            f"<h3>Candidate replicas</h3><div class=row>{''.join(cands)}</div><hr>"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        "<meta charset=utf-8><title>Backfill: ambiguous door matching</title>"
        "<style>.row{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0}</style>"
        + "".join(rows)
    )
    print(f"Report written to {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument(
        "--compare-report", action="store_true",
        help="emit HTML report for ambiguous doors and exit",
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.compare_report:
        compare_report(PROJECTS_DIR, COMPARE_REPORT)
        return 0

    if server_running(args.port):
        print(f"ABORT: something is listening on port {args.port} — stop the dev "
              "server first (single-writer rule).")
        return 1

    items, skipped = build_plan(PROJECTS_DIR, APPROVALS_PATH, MAPPING)
    print(f"=== Plan: {len(items)} to backfill, {len(skipped)} skipped ===")
    for s in skipped:
        print(f"  SKIP {s}")
    for item in items:
        flags = " ".join(f"[WARN {w}]" for w in item.warnings)
        print(
            f"  {item.library_name:22} ({item.library_id}) <- "
            f"{item.source_name} ({item.source_id}) "
            f"style={item.fields['door_style']} "
            f"results={item.result_count_before} upload={item.has_upload} {flags}"
        )

    if not args.apply:
        print("\nDry run — nothing written. Re-run with --apply to write.")
        return 0

    apply_plan(PROJECTS_DIR, items, BACKUP_DIR)
    problems = verify(PROJECTS_DIR, items)
    if problems:
        print("=== VERIFY FAILED ===")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"=== Applied + verified {len(items)} projects. "
          f"Backups: {BACKUP_DIR} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the tests (regression) and a real dry run**

Run: `uv run pytest tests/test_backfill_library_signatures.py -v`
Expected: 4 PASSED

Real dry run (read-only, safe with server up or down — but stop it anyway to exercise the real path):
Run: `uv run python scripts/backfill_library_signatures.py`
Expected output shape: `=== Plan: 19 to backfill, 5 skipped ===`, the 5 skips all "pending visual confirmation", Indiana_new_wm carrying `[WARN source replica not in global approval store ...]`, every listed item showing the correct source name and a non-null `style=`.

If the dev server was running, expected instead: `ABORT: something is listening on port 8000` — stop it (`Ctrl-C` on `npm run dev`) and re-run.

- [ ] **Step 3: Lint and commit**

```bash
npm run lint
git add scripts/backfill_library_signatures.py
git commit -m "feat(backfill): CLI with dry-run default, server guard, ambiguity compare report"
```

---

### Task 4: Resolve the 5 ambiguous doors (operator-in-loop)

**Files:**
- Modify: `scripts/backfill_library_signatures.py` (fill the 5 `None` entries in `MAPPING`)

**Interfaces:**
- Consumes: `--compare-report` CLI from Task 3.
- Produces: a fully-resolved `MAPPING` (no `None` values, or documented leave-outs).

- [ ] **Step 1: Generate the comparison report**

Run: `uv run python scripts/backfill_library_signatures.py --compare-report`
Expected: `Report written to .../output/.onboard/backfill_compare.html`

- [ ] **Step 2: Visually match each door**

Read the report images (agent: `Read` the individual `result_*.bin` / `base_door.bin` files as images for each ambiguous door — they are PNG/JPEG bytes despite the `.bin` suffix; compare frame profile, panel type, arch vs square). Record a proposed source for each of: Shaker (42a5ceae), Highpointe (9d8a5618), Durango (c81e6ddf), Graham (dca2a561), Mission (e56a767d).

- [ ] **Step 3: Operator confirms**

Send the operator the report (`SendUserFile` on `output/.onboard/backfill_compare.html`) together with the proposed picks, and WAIT for explicit confirmation. Do not proceed on silence.

- [ ] **Step 4: Fill the mapping**

Edit `MAPPING` in `scripts/backfill_library_signatures.py`: replace each confirmed `None` with the confirmed source id and update the comment, e.g.:

```python
    "c81e6ddf": "92e60a19",  # Durango_new_wm       <- Durango (confirmed 2026-07-13)
```

If the operator rejects all candidates for a door, leave it `None` and note the reason in the comment — the script keeps skipping it safely.

- [ ] **Step 5: Re-run tests + dry run, commit**

Run: `uv run pytest tests/test_backfill_library_signatures.py -v` — Expected: 4 PASSED
Run: `uv run python scripts/backfill_library_signatures.py` (server stopped)
Expected: `=== Plan: 24 to backfill, 0 skipped ===` (or 19+confirmed count if any door stayed unresolved).

```bash
git add scripts/backfill_library_signatures.py
git commit -m "feat(backfill): resolve ambiguous door mappings (operator-confirmed)"
```

---

### Task 5: Real backfill run

**Files:** none (data-only; `output/` is gitignored)

**Interfaces:**
- Consumes: resolved `MAPPING`, CLI from Task 3.

- [ ] **Step 1: Ensure the dev server is stopped**

Run: `lsof -nP -iTCP:8000 -sTCP:LISTEN || echo "port 8000 free"`
Expected: `port 8000 free`. If a server is listed, ask the operator before killing anything they started.

- [ ] **Step 2: Final dry run**

Run: `uv run python scripts/backfill_library_signatures.py`
Expected: full plan, no unexpected skips, only the known Indiana warning.

- [ ] **Step 3: Apply**

Run: `uv run python scripts/backfill_library_signatures.py --apply`
Expected: `=== Applied + verified 24 projects. Backups: .../output/.onboard/backfill_backup ===` and exit code 0. If `VERIFY FAILED` prints, STOP — restore from the backup dir for the named projects and investigate; do not re-run blind.

- [ ] **Step 4: Spot-check Frontier on disk**

Run: `ls output/.projects/950e8411/ | grep -E "signature|base_door|upload" && python3 -c "import json; m=json.load(open('output/.projects/950e8411/manifest.json')); print(m['door_style'], m['base_image_id'], len(m['result_records']))"`
Expected: the three bins present; `recessed_panel <source base_image_id> 31`.

---

### Task 6: UI acceptance on Frontier_new_wm

**Files:** none

- [ ] **Step 1: Start the dev server**

Run: `npm run dev` (background). Wait for FastAPI on :8000 and Vite on :5173.

- [ ] **Step 2: Operator (or agent via browser tools) checks Frontier_new_wm**

Open the app, select the `Frontier_new_wm` project. Expected: the replica/base door displays, the project shows a learned signature (generate step available), and all 31 existing variants render untouched.

- [ ] **Step 3: Generate one test variation (~$0.134)**

Select exactly ONE swatch and trigger generation. Expected: GT-001 passes (replica already approved), generation runs, and the new variant APPENDS — result count goes 31 → 32 with the original 31 unchanged. Let the run drain fully before touching anything else (single-writer rule).

- [ ] **Step 4: Report the outcome to the operator**

State plainly: which projects were backfilled, the Indiana approval caveat (GT-001 gates it until its replica is approved in the UI), and the Frontier 31→32 acceptance result.
