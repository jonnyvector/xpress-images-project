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

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.qa.approvals import ApprovalStore  # noqa: E402

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
                "source replica not approved in global approval store — GT-001 will gate "
                "generation until approved in the UI"
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
