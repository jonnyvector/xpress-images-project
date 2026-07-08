"""Project state management with disk persistence.

Identity model (graduated-trust pipeline, D-006): every generated image —
replica or variant attempt — carries a stable ``image_id`` assigned at
submission. Approvals, QA verdicts, and the reliability ledger key off image
IDs, never positional indices (which are completion-ordered and wiped on
re-learn). Old tuple-format projects migrate in place, non-destructively.
"""

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.runs import sweep_truncated


def new_image_id() -> str:
    """Stable identity for one generated image (uuid4 hex)."""
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ResultRecord:
    """One generated variant image: identity + metadata + bytes.

    ``image_id`` is the primary key for all trust state (approvals, verdicts,
    ledger). ``attempt`` is 0 for operator-initiated generations and 1..N for
    auto-regeneration attempts. Bytes live on disk as ``result_{idx}.bin``;
    the manifest stores only the metadata.
    """

    image_id: str
    wood_name: str
    attempt: int = 0
    created_at: str = ""
    image_data: bytes = b""


@dataclass
class ProjectState:
    id: str
    name: str
    product_type: str  # "Cabinet Door" | "Drawer Front"
    material_type: str = "wood"  # "wood" | "rtf"
    door_style: str | None = None
    corner_style: str = "sharp"  # "sharp" | "bullnose"
    style_notes: str = ""
    profile_spec: list[str] | None = None  # verifiable geometry facts (profile_spec.py)
    profile_image_path: str | None = None  # catalog 3d-profile cross-section (profile anchor)
    gemini_model: str = "gemini-3-pro-image-preview"
    selected_swatches: list[str] = field(default_factory=list)
    upload_filename: str | None = None
    has_signature: bool = False
    learned_signature: bytes | None = None  # NEVER sent to client
    base_door_image: bytes | None = None
    base_image_id: str | None = None  # stable identity of the current replica
    results: list[ResultRecord] = field(default_factory=list)
    qa_verdicts: dict[str, dict] = field(default_factory=dict)  # image_id -> verdict
    errors: list[tuple[str, str]] = field(default_factory=list)
    learning_status: str = "idle"  # "idle" | "running" | "done" | "error"
    learning_error: str | None = None
    generation_status: str = "idle"  # "idle" | "running" | "done"
    generation_completed: int = 0
    generation_total: int = 0
    retrying_indices: list[int] = field(default_factory=list)
    signature_version: int = 0
    version_count: int = 0
    truncated_runs: list[str] = field(default_factory=list)  # crash-orphaned run_ids
    project_dir: Path | None = None  # transient, stamped by the store (not persisted)


def _record_meta(record: ResultRecord) -> dict:
    """Manifest-serializable metadata for a record (bytes stay in .bin files)."""
    return {
        "image_id": record.image_id,
        "wood_name": record.wood_name,
        "attempt": record.attempt,
        "created_at": record.created_at,
    }


def _load_records(d: Path, data: dict) -> list[ResultRecord]:
    """Build ResultRecords from a project dir, migrating old manifests.

    New format: "result_records" metadata aligned by index with
    result_{idx}.bin. Old format (pre-migration): "result_names" only —
    generate fresh image_ids with attempt=0. Migration never touches files;
    the upgraded manifest is written on the next save.
    """
    metas = data.get("result_records")
    if metas is None:
        metas = [
            {"image_id": new_image_id(), "wood_name": wood_name, "attempt": 0,
             "created_at": ""}
            for wood_name in data.get("result_names", [])
        ]
    records: list[ResultRecord] = []
    for idx, meta in enumerate(metas):
        rpath = d / f"result_{idx}.bin"
        if not rpath.exists():
            continue
        records.append(
            ResultRecord(
                image_id=meta.get("image_id") or new_image_id(),
                wood_name=meta.get("wood_name", ""),
                attempt=int(meta.get("attempt", 0)),
                created_at=meta.get("created_at", ""),
                image_data=rpath.read_bytes(),
            )
        )
    return records


class ProjectStore:
    """Thread-safe project store with disk persistence."""

    def __init__(self, persist_dir: Path) -> None:
        self._persist_dir = persist_dir
        self._lock = threading.Lock()
        self._projects: dict[str, ProjectState] = {}
        self._load_all()

    def _project_dir(self, project_id: str) -> Path:
        return self._persist_dir / project_id

    def project_dir(self, project_id: str) -> Path:
        """Public path accessor (read-only use: QA lane resolves images by id)."""
        return self._project_dir(project_id)

    def _load_all(self) -> None:
        """Load all projects from disk on startup."""
        if not self._persist_dir.exists():
            return
        for d in self._persist_dir.iterdir():
            if not d.is_dir():
                continue
            manifest = d / "manifest.json"
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text())
                project = ProjectState(
                    id=data["id"],
                    name=data["name"],
                    product_type=data.get("product_type", "Cabinet Door"),
                    material_type=data.get("material_type", "wood"),
                    door_style=data.get("door_style"),
                    corner_style=data.get("corner_style", "sharp"),
                    style_notes=data.get("style_notes", ""),
                    gemini_model=data.get("gemini_model", "gemini-3-pro-image-preview"),
                    selected_swatches=data.get("selected_swatches", []),
                    upload_filename=data.get("upload_filename"),
                    signature_version=data.get("signature_version", 0),
                    version_count=data.get("version_count", 0),
                )

                # Load binary blobs
                sig_path = d / "signature.bin"
                if sig_path.exists():
                    project.learned_signature = sig_path.read_bytes()
                    project.has_signature = True

                base_path = d / "base_door.bin"
                if base_path.exists():
                    project.base_door_image = base_path.read_bytes()

                project.base_image_id = data.get("base_image_id")
                project.profile_spec = data.get("profile_spec")
                project.profile_image_path = data.get("profile_image_path")
                # Migration: a replica without an identity can't be approved —
                # assign one at load (persisted on the next save).
                if project.base_image_id is None and project.base_door_image is not None:
                    project.base_image_id = new_image_id()
                project.qa_verdicts = data.get("qa_verdicts", {})

                # Load results. New format: "result_records" metadata aligned
                # with result_{idx}.bin. Old format: "result_names" only —
                # migrate by generating stable ids (persisted on next save).
                project.results = _load_records(d, data)

                # Load errors
                project.errors = [
                    (e["wood_name"], e["error"]) for e in data.get("errors", [])
                ]

                if project.results or project.errors:
                    project.generation_status = "done"
                    project.generation_completed = len(project.results)
                    project.generation_total = len(project.results) + len(project.errors)

                # A run manifest still "running" at load means the process
                # died mid-run — flip to truncated and surface it (D-009).
                project.truncated_runs = sweep_truncated(d)
                project.project_dir = d

                self._projects[project.id] = project
            except (json.JSONDecodeError, KeyError, OSError):
                continue

    def _save_project(self, project: ProjectState) -> None:
        """Persist a single project to disk. Must be called with lock held."""
        d = self._project_dir(project.id)
        d.mkdir(parents=True, exist_ok=True)

        # Write binary blobs
        for blob, filename in [
            (project.learned_signature, "signature.bin"),
            (project.base_door_image, "base_door.bin"),
        ]:
            path = d / filename
            if blob is not None:
                path.write_bytes(blob)
            elif path.exists():
                path.unlink()

        # Upload is written separately via save_upload

        # Write result images
        result_names: list[str] = []
        for idx, record in enumerate(project.results):
            (d / f"result_{idx}.bin").write_bytes(record.image_data)
            result_names.append(record.wood_name)
        # Clean stale results
        stale_idx = len(project.results)
        while (d / f"result_{stale_idx}.bin").exists():
            (d / f"result_{stale_idx}.bin").unlink()
            stale_idx += 1

        # Write manifest
        manifest = {
            "id": project.id,
            "name": project.name,
            "product_type": project.product_type,
            "material_type": project.material_type,
            "door_style": project.door_style,
            "corner_style": project.corner_style,
            "style_notes": project.style_notes,
            "profile_spec": project.profile_spec,
            "profile_image_path": project.profile_image_path,
            "gemini_model": project.gemini_model,
            "selected_swatches": project.selected_swatches,
            "upload_filename": project.upload_filename,
            # result_names stays for older readers (corpus walker, offline eval).
            "result_names": result_names,
            "result_records": [_record_meta(r) for r in project.results],
            "base_image_id": project.base_image_id,
            "qa_verdicts": project.qa_verdicts,
            "errors": [
                {"wood_name": wn, "error": err} for wn, err in project.errors
            ],
            "signature_version": project.signature_version,
            "version_count": project.version_count,
        }
        (d / "manifest.json").write_text(json.dumps(manifest))

    def list_projects(self) -> list[ProjectState]:
        with self._lock:
            return list(self._projects.values())

    def get(self, project_id: str) -> ProjectState | None:
        with self._lock:
            return self._projects.get(project_id)

    def create(
        self, name: str, product_type: str, material_type: str = "wood"
    ) -> ProjectState:
        project = ProjectState(
            id=uuid.uuid4().hex[:8],
            name=name,
            product_type=product_type,
            material_type=material_type,
        )
        project.project_dir = self._project_dir(project.id)
        with self._lock:
            self._projects[project.id] = project
            self._save_project(project)
        return project

    def update(self, project_id: str, **kwargs: object) -> ProjectState | None:
        unknown = [k for k in kwargs if k not in ProjectState.__dataclass_fields__]
        if unknown:
            raise ValueError(f"Unknown ProjectState fields: {unknown}")
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            for key, value in kwargs.items():
                setattr(project, key, value)
            self._save_project(project)
            return project

    def delete(self, project_id: str) -> bool:
        with self._lock:
            project = self._projects.pop(project_id, None)
            if project is None:
                return False
            d = self._project_dir(project_id)
            if d.exists():
                shutil.rmtree(d)
            return True

    def archive_current_version(self, project_id: str) -> int | None:
        """Archive the current signature/base_door/results into versions/v{N}/.

        Returns the version number, or None if nothing to archive.
        Must be called with lock NOT held (acquires it internally).
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None or not project.has_signature:
                return None

            project.version_count += 1
            version = project.version_count
            d = self._project_dir(project_id)
            vdir = d / "versions" / f"v{version}"
            vdir.mkdir(parents=True, exist_ok=True)

            # Copy signature and base door image
            sig_path = d / "signature.bin"
            if sig_path.exists():
                shutil.copy2(sig_path, vdir / "signature.bin")

            base_path = d / "base_door.bin"
            if base_path.exists():
                shutil.copy2(base_path, vdir / "base_door.bin")

            # Copy result images and build names list
            result_names: list[str] = []
            for idx, record in enumerate(project.results):
                (vdir / f"result_{idx}.bin").write_bytes(record.image_data)
                result_names.append(record.wood_name)

            (vdir / "result_names.json").write_text(json.dumps(result_names))
            # Identity + verdict history travel with the archive (D-006):
            # approvals/ledger reference these image_ids forever.
            (vdir / "result_records.json").write_text(
                json.dumps([_record_meta(r) for r in project.results])
            )
            (vdir / "qa_verdicts.json").write_text(json.dumps(project.qa_verdicts))

            # Write version metadata
            meta = {
                "version": version,
                "created_at": _now(),
                "material_type": project.material_type,
                "door_style": project.door_style,
                "corner_style": project.corner_style,
                "style_notes": project.style_notes,
                "base_image_id": project.base_image_id,
            }
            (vdir / "meta.json").write_text(json.dumps(meta))

            self._save_project(project)
            return version

    def list_versions(self, project_id: str) -> list[dict]:
        """Return list of version summaries for a project."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return []

        d = self._project_dir(project_id)
        versions_dir = d / "versions"
        if not versions_dir.exists():
            return []

        summaries: list[dict] = []
        for vdir in sorted(versions_dir.iterdir()):
            if not vdir.is_dir() or not vdir.name.startswith("v"):
                continue
            meta_path = vdir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                meta = json.loads(meta_path.read_text())
                names_path = vdir / "result_names.json"
                result_count = 0
                if names_path.exists():
                    result_count = len(json.loads(names_path.read_text()))
                summaries.append(
                    {
                        "version": meta["version"],
                        "created_at": meta["created_at"],
                        "door_style": meta.get("door_style"),
                        "style_notes": meta.get("style_notes", ""),
                        "result_count": result_count,
                    }
                )
            except (json.JSONDecodeError, KeyError, OSError):
                continue
        return summaries

    def restore_version(self, project_id: str, version: int) -> bool:
        """Archive current state, then restore the given version to active slot.

        Returns True on success, False if version not found.
        """
        d = self._project_dir(project_id)
        vdir = d / "versions" / f"v{version}"
        if not vdir.exists():
            return False

        # Archive current first (if there's a signature to archive)
        project = self.get(project_id)
        if project is not None and project.has_signature:
            self.archive_current_version(project_id)

        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False

            # Read version files
            sig_path = vdir / "signature.bin"
            if sig_path.exists():
                sig_data = sig_path.read_bytes()
                project.learned_signature = sig_data
                project.has_signature = True
                (d / "signature.bin").write_bytes(sig_data)

            base_path = vdir / "base_door.bin"
            if base_path.exists():
                base_data = base_path.read_bytes()
                project.base_door_image = base_data
                (d / "base_door.bin").write_bytes(base_data)

            # Restore results (records preserve identity; old archives without
            # result_records.json migrate like old manifests do).
            names_path = vdir / "result_names.json"
            names = json.loads(names_path.read_text()) if names_path.exists() else []
            records_path = vdir / "result_records.json"
            version_data = {"result_names": names}
            if records_path.exists():
                version_data["result_records"] = json.loads(records_path.read_text())
            project.results = _load_records(vdir, version_data)
            verdicts_path = vdir / "qa_verdicts.json"
            project.qa_verdicts = (
                json.loads(verdicts_path.read_text()) if verdicts_path.exists() else {}
            )
            project.errors = []
            project.generation_status = "done" if project.results else "idle"
            project.generation_completed = len(project.results)
            project.generation_total = len(project.results)
            project.signature_version = version

            # Restore metadata from version
            meta_path = vdir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                project.material_type = meta.get("material_type", project.material_type)
                project.door_style = meta.get("door_style", project.door_style)
                project.corner_style = meta.get("corner_style", project.corner_style)
                project.style_notes = meta.get("style_notes", project.style_notes)
                # The restored replica is the archived image — same identity.
                project.base_image_id = meta.get("base_image_id")

            self._save_project(project)
            return True

    def set_qa_verdict(self, project_id: str, image_id: str, verdict: dict) -> bool:
        """Attach a QA verdict to an image by stable id and persist, atomically.

        Verdicts are stored as plain dicts (schema owned by the QA lane).
        Returns False if the project is gone.
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            project.qa_verdicts[image_id] = verdict
            self._save_project(project)
            return True

    def replace_result_attempt(
        self,
        project_id: str,
        active_image_id: str,
        *,
        image_id: str,
        wood_name: str,
        attempt: int,
        image_data: bytes,
    ) -> ResultRecord | None:
        """Swap in a new auto-regen attempt for a wood slot, atomically.

        The current active bytes are demoted to ``result_{idx}_attempt_{K}.bin``
        (attempts are retained for audit, D-012 — an image is never lost).
        Slot located by the ACTIVE image_id, never by index (indices shift).
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            idx = next(
                (i for i, r in enumerate(project.results)
                 if r.image_id == active_image_id),
                None,
            )
            if idx is None:
                return None
            current = project.results[idx]
            d = self._project_dir(project_id)
            (d / f"result_{idx}_attempt_{current.attempt}.bin").write_bytes(
                current.image_data
            )
            record = ResultRecord(
                image_id=image_id,
                wood_name=wood_name,
                attempt=attempt,
                created_at=_now(),
                image_data=image_data,
            )
            project.results[idx] = record
            self._save_project(project)
            return record

    def promote_attempt(
        self,
        project_id: str,
        active_image_id: str,
        *,
        promote_image_id: str,
        promote_attempt: int,
    ) -> bool:
        """Make a previously demoted attempt the active record (best-attempt
        selection, D-012). The displaced active bytes are demoted to their own
        attempt file; the promoted bytes move into ``result_{idx}.bin``."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            idx = next(
                (i for i, r in enumerate(project.results)
                 if r.image_id == active_image_id),
                None,
            )
            if idx is None:
                return False
            d = self._project_dir(project_id)
            src = d / f"result_{idx}_attempt_{promote_attempt}.bin"
            if not src.exists():
                return False
            current = project.results[idx]
            (d / f"result_{idx}_attempt_{current.attempt}.bin").write_bytes(
                current.image_data
            )
            promoted_bytes = src.read_bytes()
            project.results[idx] = ResultRecord(
                image_id=promote_image_id,
                wood_name=current.wood_name,
                attempt=promote_attempt,
                created_at=_now(),
                image_data=promoted_bytes,
            )
            # Bytes now live in result_{idx}.bin — drop the duplicate file.
            src.unlink()
            self._save_project(project)
            return True

    def clear_qa_verdict(self, project_id: str, image_id: str) -> None:
        """Drop a verdict entry (stale QA task for a vanished image)."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return
            if project.qa_verdicts.pop(image_id, None) is not None:
                self._save_project(project)

    def set_active_replica(
        self,
        project_id: str,
        *,
        image: bytes | None,
        signature: bytes | None,
        base_image_id: str,
        verdict: dict | None,
    ) -> bool:
        """Make a specific replica (bytes + signature + identity + verdict) the
        active one, atomically. Used by the onboarding loop to restore its
        best-scoring attempt after later attempts overwrote it.
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            project.base_door_image = image
            project.learned_signature = signature
            project.has_signature = bool(signature)
            project.base_image_id = base_image_id
            project.qa_verdicts = {base_image_id: verdict} if verdict else {}
            self._save_project(project)
            return True

    def reset_variant_results(
        self, project_id: str, *, keep_replica_verdict: bool = True
    ) -> bool:
        """Clear all variant results (and their verdicts), atomically, so a
        re-run replaces rather than appends. The replica verdict is preserved by
        default."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            replica_v = (
                project.qa_verdicts.get(project.base_image_id)
                if keep_replica_verdict and project.base_image_id
                else None
            )
            project.results = []
            project.qa_verdicts = (
                {project.base_image_id: replica_v} if replica_v else {}
            )
            self._save_project(project)
            return True

    def get_version_base_image(self, project_id: str, version: int) -> bytes | None:
        """Read base_door.bin from a specific version."""
        vdir = self._project_dir(project_id) / "versions" / f"v{version}"
        path = vdir / "base_door.bin"
        if path.exists():
            return path.read_bytes()
        return None

    def get_version_result_image(
        self, project_id: str, version: int, idx: int
    ) -> bytes | None:
        """Read a specific result image from a version."""
        vdir = self._project_dir(project_id) / "versions" / f"v{version}"
        path = vdir / f"result_{idx}.bin"
        if path.exists():
            return path.read_bytes()
        return None

    def save_upload(self, project_id: str, filename: str, data: bytes) -> bool:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            project.upload_filename = filename
            d = self._project_dir(project_id)
            d.mkdir(parents=True, exist_ok=True)
            (d / "upload.bin").write_bytes(data)
            self._save_project(project)
            return True

    def get_upload_bytes(self, project_id: str) -> bytes | None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            path = self._project_dir(project_id) / "upload.bin"
            if path.exists():
                return path.read_bytes()
            return None

    def record_result(
        self,
        project_id: str,
        wood_name: str,
        *,
        image_data: bytes | None = None,
        error: str | None = None,
        advance: bool = True,
        attempt: int = 0,
        image_id: str | None = None,
    ) -> ResultRecord | bool:
        """Append a generation result or error and persist, atomically.

        Called concurrently by generation worker threads, so the whole
        read-modify-write (append + counter bump + save) happens under the
        store lock to avoid lost updates.

        Returns the created ResultRecord when an image was stored — callers
        bind QA verdicts to its image_id, never to a positional index (which
        is assigned in completion order under the lock). Returns True when
        only an error was recorded, False if the project is gone.
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            record: ResultRecord | bool = True
            if image_data is not None:
                record = ResultRecord(
                    # Prefer the submission-time id (from the run manifest's
                    # planned entries) so identity binds before the API call.
                    image_id=image_id or new_image_id(),
                    wood_name=wood_name,
                    attempt=attempt,
                    created_at=_now(),
                    image_data=image_data,
                )
                project.results.append(record)
            else:
                project.errors.append((wood_name, error or "Unknown error"))
            if advance:
                project.generation_completed += 1
            self._save_project(project)
            return record

    def record_retry_result(
        self,
        project_id: str,
        idx: int,
        wood_name: str,
        *,
        image_data: bytes | None = None,
        error: str | None = None,
    ) -> bool:
        """Record the outcome of a single-result retry, atomically.

        Clears any prior error entries for the same wood name first, so
        repeated retries don't accumulate stale errors. On success the result
        is replaced in place; on failure an error is recorded and the existing
        result (if any) is left untouched.

        Returns the fresh ResultRecord on success (a new image is a new
        identity — verdicts of the replaced image do not carry over), True
        when only an error was recorded, False if the project is gone.
        """
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return False
            project.errors = [
                (wn, err) for wn, err in project.errors if wn != wood_name
            ]
            record: ResultRecord | bool = True
            if image_data is not None:
                record = ResultRecord(
                    image_id=new_image_id(),
                    wood_name=wood_name,
                    attempt=0,
                    created_at=_now(),
                    image_data=image_data,
                )
                if 0 <= idx < len(project.results):
                    project.results[idx] = record
                else:
                    project.results.append(record)
            else:
                project.errors.append((wood_name, error or "Retry failed"))
            self._save_project(project)
            return record

    def finish_retry(self, project_id: str, idx: int) -> None:
        """Clear a result index from retrying_indices and persist, atomically."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return
            if idx in project.retrying_indices:
                project.retrying_indices.remove(idx)
            self._save_project(project)

    def save(self, project_id: str) -> None:
        """Explicitly persist a project (call after mutation outside the store)."""
        with self._lock:
            project = self._projects.get(project_id)
            if project:
                self._save_project(project)
