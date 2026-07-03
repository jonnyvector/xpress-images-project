"""Production approval store: the operator's verdicts on generated images.

Owns ``output/.qa/approvals.json``. Keyed by stable image_id (D-006): a
re-learned replica is a new image and therefore starts unapproved — stale
approvals can never gate variants of an image nobody reviewed. Completely
separate from the frozen calibration labels in ``labels.json`` (D-011);
nothing may write across that boundary in either direction.

Thread-safety: ``approved_ids()`` feeds ``policy.decide()`` from concurrent
worker threads while the API writes approvals, so every read and write holds
the internal lock (D-010).

Not responsible for: gate decisions (routers), reliability accounting
(reliability.py), or calibration ground truth (labels.py).
"""

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.qa.labels import REASONS

VERDICTS = ("approved", "rejected")
KINDS = ("replica", "variant")

DEFAULT_APPROVALS_PATH = Path("output/.qa/approvals.json")


@dataclass
class Approval:
    image_id: str
    project_id: str
    kind: str  # "replica" | "variant"
    verdict: str  # "approved" | "rejected"
    reasons: list[str] = field(default_factory=list)  # REASONS vocabulary, rejects only
    note: str = ""
    decided_at: str = ""  # ISO 8601, set by the store


# Process-wide store at the default path; tests swap it for a tmp instance.
_default_store: "ApprovalStore | None" = None


def get_approval_store() -> "ApprovalStore":
    global _default_store
    if _default_store is None:
        _default_store = ApprovalStore()
    return _default_store


class ApprovalStore:
    """Load/save approvals at ``path``; every ``set`` validates and persists."""

    def __init__(self, path: Path = DEFAULT_APPROVALS_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._approvals: dict[str, Approval] = {}
        if path.exists():
            data = json.loads(path.read_text())
            for item in data.get("approvals", []):
                approval = Approval(**item)
                self._approvals[approval.image_id] = approval

    def set(self, approval: Approval) -> None:
        if approval.verdict not in VERDICTS:
            raise ValueError(f"Invalid verdict: {approval.verdict!r}")
        if approval.kind not in KINDS:
            raise ValueError(f"Invalid kind: {approval.kind!r}")
        unknown = [r for r in approval.reasons if r not in REASONS]
        if unknown:
            raise ValueError(f"Unknown reasons: {unknown}")
        approval.decided_at = datetime.now(UTC).isoformat()
        with self._lock:
            self._approvals[approval.image_id] = approval
            self._save()

    def get(self, image_id: str) -> Approval | None:
        with self._lock:
            return self._approvals.get(image_id)

    def for_project(self, project_id: str) -> list[Approval]:
        with self._lock:
            return [
                a for a in self._approvals.values() if a.project_id == project_id
            ]

    def approved_ids(self) -> frozenset[str]:
        """Image ids with an ``approved`` verdict — feeds policy.decide()."""
        with self._lock:
            return frozenset(
                a.image_id for a in self._approvals.values() if a.verdict == "approved"
            )

    def _save(self) -> None:
        """Persist. Must be called with the lock held."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"approvals": [asdict(a) for a in self._approvals.values()]}
        self._path.write_text(json.dumps(payload, indent=1))


def approved_candidate_keys(
    store: ApprovalStore, projects_dir: Path = Path("output/.projects")
) -> frozenset[str]:
    """Map approved image_ids to offline candidate keys (D-006 boundary).

    The eval/report scripts reason in ``{pid}:{version}:{kind}:{index}`` keys;
    production trust state keys off image_ids. This adapter is the ONLY place
    the two key spaces meet: current-version replicas and variants whose
    image_id carries an ``approved`` verdict become candidate keys.
    """
    approved = store.approved_ids()
    keys: set[str] = set()
    if not projects_dir.exists():
        return frozenset()
    for d in projects_dir.iterdir():
        manifest = d / "manifest.json"
        if not d.is_dir() or not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        pid = data.get("id", d.name)
        if data.get("base_image_id") in approved:
            keys.add(f"{pid}:0:replica:-1")
        for idx, meta in enumerate(data.get("result_records", [])):
            if meta.get("image_id") in approved:
                keys.add(f"{pid}:0:variant:{idx}")
    return frozenset(keys)
