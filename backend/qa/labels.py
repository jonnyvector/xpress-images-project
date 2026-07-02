"""Accept/reject labels for generated images, persisted to JSON."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REASONS = ["geometry_drift", "profile_character", "material_realism", "artifacts", "other"]


@dataclass
class Label:
    key: str  # "{project_id}:{version}:{kind}:{index}"
    verdict: str  # "accept" | "reject"
    reasons: list[str] = field(default_factory=list)
    notes: str = ""


class LabelStore:
    """Load/save labels at ``path``; every ``set`` persists immediately."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._labels: dict[str, Label] = {}
        if path.exists():
            data = json.loads(path.read_text())
            for item in data.get("labels", []):
                label = Label(**item)
                self._labels[label.key] = label

    def set(self, label: Label) -> None:
        if label.verdict not in ("accept", "reject"):
            raise ValueError(f"Invalid verdict: {label.verdict!r}")
        unknown = [r for r in label.reasons if r not in REASONS]
        if unknown:
            raise ValueError(f"Unknown reasons: {unknown}")
        self._labels[label.key] = label
        self._save()

    def get(self, key: str) -> Label | None:
        return self._labels.get(key)

    def all(self) -> list[Label]:
        return list(self._labels.values())

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"labels": [asdict(label) for label in self._labels.values()]}
        self._path.write_text(json.dumps(payload, indent=1))
