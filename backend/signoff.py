"""Operator sign-off on coverage: the durable record of human judgment.

Coverage cannot be inferred. The set of colors a door needs varies by style,
so "all variations generated" is an operator judgment, as is "uploaded to
Shopify". This module owns that record and nothing else — it knows nothing
about sales CSVs, projects, or Shopify.

Keyed by the exact sales-CSV product title, the same key coverage_overrides.json
uses. Lives in docs/sales/data/ and is git-tracked: sign-off is a business
record that must survive a fresh clone and be reviewable in a diff.
"""

import json
import os
import tempfile
import threading
from pathlib import Path

SIGNOFF_FILENAME = "coverage_signoff.json"

# Public gate names -> record keys. Callers pass the short name.
GATE_KEYS = {"variations": "variations_complete", "shopify": "in_shopify"}

# Serialises the load -> mutate -> save sequence. Every writer loads the WHOLE
# record and saves the WHOLE record, so two overlapping writers would each
# save their own view and the loser's sign-off would vanish. FastAPI runs sync
# endpoints in a threadpool, so this is a real interleaving, not a hypothetical.
# Same pattern as ProjectStore's own lock.
SIGNOFF_LOCK = threading.Lock()


class SignoffRecordError(Exception):
    """The sign-off file exists but cannot be read as a record.

    Only writers care. A reader degrades to "nothing reviewed"; a writer must
    stop, because it would save its own one-entry view over the real file.
    """


def load_signoff(data_dir: Path) -> dict[str, dict]:
    """Read the sign-off record. Missing or malformed file means no sign-offs.

    Never raises: a broken file must degrade to "nothing reviewed", never to a
    crashed coverage page or a false green.
    """
    path = data_dir / SIGNOFF_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def load_signoff_strict(data_dir: Path) -> dict[str, dict]:
    """Read the sign-off record for a writer, refusing to guess.

    A missing file is the legitimate first-run path and returns {}. Anything
    else that cannot be read as a record raises, because the caller is about to
    save the whole record back: silently reading a corrupt file as "no
    sign-offs" turns one operator click into total, unrecoverable data loss.
    """
    path = data_dir / SIGNOFF_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        raise SignoffRecordError(f"{path} could not be read as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SignoffRecordError(
            f"{path} must hold a JSON object, found {type(data).__name__}"
        )
    bad = sorted(str(k) for k, v in data.items() if not isinstance(v, dict))
    if bad:
        raise SignoffRecordError(
            f"{path} has entries that are not objects: {', '.join(bad)}"
        )
    return {str(k): v for k, v in data.items()}


def save_signoff(data_dir: Path, record: dict[str, dict]) -> None:
    """Write the record atomically — a partial file would read as lost sign-offs."""
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, data_dir / SIGNOFF_FILENAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _entry(record: dict[str, dict], title: str) -> dict:
    return dict(record.get(title) or {})


def set_gate(
    record: dict[str, dict],
    title: str,
    gate: str,
    value: bool,
    *,
    by: str,
    at: str,
    result_count: int | None = None,
    acknowledged_gap: bool = False,
) -> dict[str, dict]:
    """Stamp or clear one gate. Returns a new record; does not mutate the input.

    Clearing deletes the key rather than storing False, so "never reviewed" and
    "revoked" both read as absent — a revoked gate is simply re-openable work.
    """
    if gate not in GATE_KEYS:
        raise ValueError(f"unknown gate {gate!r}; expected one of {sorted(GATE_KEYS)}")
    key = GATE_KEYS[gate]
    entry = _entry(record, title)
    if not value:
        entry.pop(key, None)
    else:
        stamp: dict = {"by": by, "at": at}
        if gate == "variations":
            stamp["result_count"] = result_count
            stamp["acknowledged_gap"] = acknowledged_gap
        entry[key] = stamp
    return {**record, title: entry}


def set_canonical(record: dict[str, dict], title: str, project_id: str) -> (
    dict[str, dict]
):
    """Designate the project the palette checklist reads from."""
    entry = _entry(record, title)
    entry["canonical_project_id"] = project_id
    return {**record, title: entry}


def set_exclusions(
    record: dict[str, dict], title: str, colors: list[str]
) -> dict[str, dict]:
    """Mark colors this product does not need. Stored sorted and deduped so the
    git diff stays stable when the operator re-clicks in a different order."""
    entry = _entry(record, title)
    entry["excluded_colors"] = sorted(set(colors))
    return {**record, title: entry}


def is_stale(entry: dict, distinct_colors: int) -> bool:
    """True when the canonical project's colour count moved since sign-off.

    This is what stops a signed-off row from silently rotting back into the
    state this whole feature exists to fix.
    """
    stamp = entry.get(GATE_KEYS["variations"])
    if not stamp:
        return False
    recorded = stamp.get("result_count")
    if recorded is None:
        return False
    return int(recorded) != int(distinct_colors)
