"""Generation-run manifests: persisted records of planned work, attempts, spend.

Owns ``output/.projects/<id>/runs/<run_id>.json``. Each generation run writes
one manifest holding the planned selections (with image_ids pre-assigned at
submission time, D-006), the per-attempt history, an immutable snapshot of the
trust config taken at run start (D-009), and two spend counters. The counters
are the cost-cap authority: they increment under this manifest's lock BEFORE
each API submission, so concurrent worker threads can never overshoot a cap by
racing the check. ``unconsented_images`` counts only auto-retry submissions —
the spend the operator did not explicitly confirm.

A manifest still ``running`` when the store loads means the process died
mid-run: it flips to ``truncated`` and is surfaced on the project, never
silently reported done.

Not responsible for: gate decisions (routers), verdict production (QA lane),
or result storage (ProjectStore).
"""

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path


class RunManifest:
    """One generation run's persisted state. All mutations lock + save."""

    def __init__(self, path: Path, data: dict) -> None:
        self.path = path
        self._data = data
        self._lock = threading.Lock()

    @property
    def run_id(self) -> str:
        return self._data["run_id"]

    @classmethod
    def create(
        cls,
        project_dir: Path,
        planned: list[tuple[str, str]],
        config: dict,
    ) -> "RunManifest":
        """Start a new run: manifest written immediately with status=running.

        ``planned`` is (wood_name, image_id) pairs — identity is assigned at
        submission time, before any API call. ``config`` is deep-copied via
        JSON round-trip so later edits to the source never leak into the run.
        """
        run_id = uuid.uuid4().hex[:12]
        runs_dir = project_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "config_snapshot": json.loads(json.dumps(config)),
            "planned": [
                {"wood_name": wood_name, "image_id": image_id}
                for wood_name, image_id in planned
            ],
            "attempts": [],
            "images_submitted": 0,
            "unconsented_images": 0,
        }
        manifest = cls(runs_dir / f"{run_id}.json", data)
        manifest._save()
        return manifest

    @classmethod
    def load(cls, path: Path) -> "RunManifest":
        return cls(path, json.loads(path.read_text()))

    def submit(self, *, unconsented: bool = False) -> int:
        """Count one image submission, atomically, BEFORE the API call.

        Returns the new images_submitted total. Callers enforcing a cost cap
        check the counters and roll back via ``unsubmit`` when over.
        """
        with self._lock:
            self._data["images_submitted"] += 1
            if unconsented:
                self._data["unconsented_images"] += 1
            self._save()
            return self._data["images_submitted"]

    def unsubmit(self, *, unconsented: bool = False) -> None:
        """Roll back one ``submit`` (cap breach: increment happened, call won't)."""
        with self._lock:
            self._data["images_submitted"] -= 1
            if unconsented:
                self._data["unconsented_images"] -= 1
            self._save()

    def record_attempt(
        self,
        *,
        image_id: str,
        wood_name: str,
        attempt: int,
        verdict: str | None = None,
        active: bool = True,
    ) -> None:
        with self._lock:
            self._data["attempts"].append(
                {
                    "image_id": image_id,
                    "wood_name": wood_name,
                    "attempt": attempt,
                    "verdict": verdict,
                    "active": active,
                }
            )
            self._save()

    def counters(self) -> tuple[int, int]:
        """(images_submitted, unconsented_images) — consistent snapshot."""
        with self._lock:
            return self._data["images_submitted"], self._data["unconsented_images"]

    def config_snapshot(self) -> dict:
        return json.loads(json.dumps(self._data["config_snapshot"]))

    def finish(self, status: str = "done") -> None:
        with self._lock:
            self._data["status"] = status
            self._save()

    def _save(self) -> None:
        """Persist. Must be called with the lock held (or from create)."""
        self.path.write_text(json.dumps(self._data, indent=1))


def sweep_truncated(project_dir: Path) -> list[str]:
    """Flip crash-orphaned ``running`` manifests to ``truncated``.

    Called at store load; returns run_ids that are (now) truncated so the
    project can surface them. Finished runs are left untouched.
    """
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return []
    truncated: list[str] = []
    for path in sorted(runs_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") == "running":
            data["status"] = "truncated"
            path.write_text(json.dumps(data, indent=1))
        if data.get("status") == "truncated":
            truncated.append(data.get("run_id", path.stem))
    return truncated


def latest_run_summary(project_dir: Path) -> dict | None:
    """Newest run's manifest summary for the UI (status, counters)."""
    runs_dir = project_dir / "runs"
    if not runs_dir.exists():
        return None
    newest: dict | None = None
    newest_key = ""
    for path in runs_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        key = str(data.get("started_at", ""))
        if key >= newest_key:
            newest_key, newest = key, data
    if newest is None:
        return None
    return {
        "run_id": newest.get("run_id"),
        "status": newest.get("status"),
        "started_at": newest.get("started_at"),
        "images_submitted": newest.get("images_submitted", 0),
        "unconsented_images": newest.get("unconsented_images", 0),
        "planned": len(newest.get("planned", [])),
    }
