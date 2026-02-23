"""Project state management with disk persistence."""

import json
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class ProjectState:
    id: str
    name: str
    product_type: str  # "Cabinet Door" | "Drawer Front"
    door_style: str | None = None
    style_notes: str = ""
    selected_swatches: list[str] = field(default_factory=list)
    upload_filename: str | None = None
    has_signature: bool = False
    learned_signature: bytes | None = None  # NEVER sent to client
    base_door_image: bytes | None = None
    results: list[tuple[str, bytes]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    learning_status: str = "idle"  # "idle" | "running" | "done" | "error"
    learning_error: str | None = None
    generation_status: str = "idle"  # "idle" | "running" | "done"
    generation_completed: int = 0
    generation_total: int = 0
    retrying_indices: list[int] = field(default_factory=list)
    signature_version: int = 0
    version_count: int = 0


class ProjectStore:
    """Thread-safe project store with disk persistence."""

    def __init__(self, persist_dir: Path) -> None:
        self._persist_dir = persist_dir
        self._lock = threading.Lock()
        self._projects: dict[str, ProjectState] = {}
        self._load_all()

    def _project_dir(self, project_id: str) -> Path:
        return self._persist_dir / project_id

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
                    door_style=data.get("door_style"),
                    style_notes=data.get("style_notes", ""),
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

                upload_path = d / "upload.bin"
                if upload_path.exists() and not project.upload_filename:
                    # upload exists on disk but filename wasn't recorded
                    pass

                # Load results
                results: list[tuple[str, bytes]] = []
                result_names = data.get("result_names", [])
                for idx, wood_name in enumerate(result_names):
                    rpath = d / f"result_{idx}.bin"
                    if rpath.exists():
                        results.append((wood_name, rpath.read_bytes()))
                project.results = results

                # Load errors
                project.errors = [
                    (e["wood_name"], e["error"]) for e in data.get("errors", [])
                ]

                if results or project.errors:
                    project.generation_status = "done"
                    project.generation_completed = len(results)
                    project.generation_total = len(results) + len(project.errors)

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
        for idx, (wood_name, image_data) in enumerate(project.results):
            (d / f"result_{idx}.bin").write_bytes(image_data)
            result_names.append(wood_name)
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
            "door_style": project.door_style,
            "style_notes": project.style_notes,
            "selected_swatches": project.selected_swatches,
            "upload_filename": project.upload_filename,
            "result_names": result_names,
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

    def create(self, name: str, product_type: str) -> ProjectState:
        project = ProjectState(
            id=uuid.uuid4().hex[:8],
            name=name,
            product_type=product_type,
        )
        with self._lock:
            self._projects[project.id] = project
            self._save_project(project)
        return project

    def update(self, project_id: str, **kwargs: object) -> ProjectState | None:
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return None
            for key, value in kwargs.items():
                if hasattr(project, key):
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
            for idx, (wood_name, image_data) in enumerate(project.results):
                (vdir / f"result_{idx}.bin").write_bytes(image_data)
                result_names.append(wood_name)

            (vdir / "result_names.json").write_text(json.dumps(result_names))

            # Write version metadata
            meta = {
                "version": version,
                "created_at": datetime.now(UTC).isoformat(),
                "door_style": project.door_style,
                "style_notes": project.style_notes,
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

            # Restore results
            names_path = vdir / "result_names.json"
            results: list[tuple[str, bytes]] = []
            if names_path.exists():
                names = json.loads(names_path.read_text())
                for idx, wood_name in enumerate(names):
                    rpath = vdir / f"result_{idx}.bin"
                    if rpath.exists():
                        results.append((wood_name, rpath.read_bytes()))
            project.results = results
            project.errors = []
            project.generation_status = "done" if results else "idle"
            project.generation_completed = len(results)
            project.generation_total = len(results)
            project.signature_version = version

            # Restore metadata from version
            meta_path = vdir / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text())
                project.door_style = meta.get("door_style", project.door_style)
                project.style_notes = meta.get("style_notes", project.style_notes)

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

    def save(self, project_id: str) -> None:
        """Explicitly persist a project (call after mutation outside the store)."""
        with self._lock:
            project = self._projects.get(project_id)
            if project:
                self._save_project(project)
