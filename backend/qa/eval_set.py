"""Frozen answer key for comparing vision judges.

Sources, best first:
- hand labels (output/.qa/labels.json), all of them;
- the operator's in-app rejections;
- in-app approvals clicked one at a time. "Approve All" bursts are left out:
  nobody inspected those images individually, so they aren't trustworthy accepts.

Each door contributes a few images per answer, so one big door can't dominate
the score. The set is written once and reused, so every model is judged on the
same images.
"""

import json
import random
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from backend.qa.corpus import Candidate

# An approval with this many others from the same door within the window was
# an "Approve All" click, not an individual inspection.
BULK_MIN_COUNT = 5
BULK_WINDOW_S = 90


@dataclass
class EvalItem:
    key: str  # corpus candidate key
    truth: str  # "accept" | "reject"
    source: str  # "label" | "rejected" | "approved"
    project_id: str
    reasons: list[str]


def bulk_approval_ids(approvals: list[dict]) -> set[str]:
    """Image ids approved as part of a burst (Approve All)."""
    by_project: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for a in approvals:
        if a["verdict"] == "approved":
            ts = datetime.fromisoformat(a["decided_at"]).timestamp()
            by_project[a["project_id"]].append((ts, a["image_id"]))
    bulk: set[str] = set()
    for stamps in by_project.values():
        stamps.sort()
        times = [t for t, _ in stamps]
        lo = 0
        for hi, (t, _) in enumerate(stamps):
            while times[lo] < t - BULK_WINDOW_S:
                lo += 1
            if hi - lo + 1 >= BULK_MIN_COUNT:
                bulk.update(image_id for _, image_id in stamps[lo : hi + 1])
    return bulk


def image_id_to_key(projects_dir: Path) -> dict[str, str]:
    """Current-version image id -> corpus key ("pid:0:variant:idx" / "pid:0:replica:-1")."""
    out: dict[str, str] = {}
    for manifest_path in projects_dir.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        pid = manifest.get("id", manifest_path.parent.name)
        for idx, record in enumerate(manifest.get("result_records") or []):
            out[record["image_id"]] = f"{pid}:0:variant:{idx}"
        if manifest.get("base_image_id"):
            out.setdefault(manifest["base_image_id"], f"{pid}:0:replica:-1")
    return out


def build_eval_set(
    candidates: dict[str, Candidate],
    labels: list[dict],
    approvals: list[dict],
    id_to_key: dict[str, str],
    *,
    per_project: int = 10,
    max_per_class: int = 200,
    seed: int = 7,
) -> list[EvalItem]:
    items: dict[str, EvalItem] = {}
    for label in labels:
        cand = candidates.get(label["key"])
        if cand is not None and cand.image_path.exists():
            items[label["key"]] = EvalItem(
                label["key"], label["verdict"], "label", cand.project_id, list(label["reasons"])
            )

    bulk = bulk_approval_ids(approvals)
    pool: dict[tuple[str, str], list[EvalItem]] = defaultdict(list)
    for a in approvals:
        key = id_to_key.get(a["image_id"])
        cand = candidates.get(key) if key else None
        if cand is None or key in items or not cand.image_path.exists():
            continue
        if a["verdict"] == "approved" and a["image_id"] in bulk:
            continue
        truth = "accept" if a["verdict"] == "approved" else "reject"
        source = "approved" if truth == "accept" else "rejected"
        pool[(cand.project_id, truth)].append(
            EvalItem(key, truth, source, cand.project_id, list(a.get("reasons") or []))
        )

    rng = random.Random(seed)
    for truth in ("reject", "accept"):
        picked: list[EvalItem] = []
        for (_, t), group in sorted(pool.items()):
            if t == truth:
                group = sorted(group, key=lambda item: item.key)
                rng.shuffle(group)
                picked.extend(group[:per_project])
        rng.shuffle(picked)
        for item in picked[:max_per_class]:
            items[item.key] = item
    return sorted(items.values(), key=lambda item: item.key)


def save_eval_set(path: Path, items: list[EvalItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(item) for item in items], indent=1))


def load_eval_set(path: Path) -> list[EvalItem]:
    return [EvalItem(**row) for row in json.loads(path.read_text())]
