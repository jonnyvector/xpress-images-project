"""One-shot: turn coverage_overrides.json into coverage_signoff.json entries.

The override list recorded products whose images were produced outside the app.
Both gates are therefore already true for them, stamped `migrated` so the
provenance stays visible in the record.

Run once:  uv run python scripts/migrate_coverage_overrides.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.signoff import load_signoff, save_signoff, set_gate

DATA_DIR = Path("docs/sales/data")


def migrate(data_dir: Path, *, now: str) -> int:
    path = data_dir / "coverage_overrides.json"
    if not path.exists():
        return 0
    try:
        titles = json.loads(path.read_text()).get("covered", [])
    except (ValueError, OSError):
        return 0

    record = load_signoff(data_dir)
    for title in titles:
        for gate in ("variations", "shopify"):
            record = set_gate(
                record, str(title), gate, True,
                by="migrated", at=now, result_count=None, acknowledged_gap=True,
            )
    save_signoff(data_dir, record)
    return len(titles)


if __name__ == "__main__":
    n = migrate(DATA_DIR, now=datetime.now(UTC).isoformat())
    print(f"Migrated {n} override title(s) into coverage_signoff.json")
    sys.exit(0)
