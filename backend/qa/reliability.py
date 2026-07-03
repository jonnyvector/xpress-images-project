"""Reliability ledger: pipeline-vs-operator agreement, honestly measured.

Owns ``output/.qa/reliability.jsonl`` (append-only) and its aggregation.
One record per human verdict event, capturing the pipeline's verdict for the
same image at decision time. This file is the evidence base for the bulk
unlock decision (D-003) — so the math must not flatter the pipeline:

- **Agreement** counts only DECISIVE pipeline verdicts (D-008):
  ``pass``+approved or ``regenerate``+rejected agree; the inverses disagree.
- ``needs_human``/``error`` are the **deferral** bucket — a pipeline that
  declines to decide demonstrates no discriminative skill.
- ``null`` pipeline verdicts (QA hadn't finished at decision time) are
  excluded from every rate.
- No data reports ``agreement_rate: None``, never a fake 100%.

Not responsible for: approval storage (approvals.py) or verdict production
(qa_lane.py). Ledger-append failures are the caller's to log — they MUST
never block the approval write.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_LEDGER_PATH = Path("output/.qa/reliability.jsonl")

_append_lock = threading.Lock()

DECISIVE = ("pass", "regenerate")
DEFERRAL = ("needs_human", "error")


def append_record(
    path: Path | None = None,
    *,
    image_id: str,
    project_id: str,
    kind: str,
    style_class: str,
    pipeline_verdict: str | None,
    human_verdict: str,
    reasons: list[str],
) -> None:
    if path is None:
        path = DEFAULT_LEDGER_PATH  # resolved at call time — tests repoint it
    record = {
        "image_id": image_id,
        "project_id": project_id,
        "kind": kind,
        "style_class": style_class,
        "pipeline_verdict": pipeline_verdict,
        "human_verdict": human_verdict,
        "reasons": reasons,
        "at": datetime.now(UTC).isoformat(),
    }
    line = json.dumps(record) + "\n"
    with _append_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(line)


def _bucket() -> dict:
    return {"agree": 0, "disagreements": 0, "deferral_n": 0, "null_n": 0}


def _rates(b: dict) -> dict:
    decisive = b["agree"] + b["disagreements"]
    verdict_bearing = decisive + b["deferral_n"]
    return {
        "decisive_n": decisive,
        "agreement_rate": (b["agree"] / decisive) if decisive else None,
        "deferral_n": b["deferral_n"],
        "deferral_rate": (
            b["deferral_n"] / verdict_bearing if verdict_bearing else None
        ),
        "null_n": b["null_n"],
        "disagreements": b["disagreements"],
    }


def aggregate(path: Path | None = None) -> dict:
    """Recompute agreement stats from the JSONL file (no hidden state)."""
    if path is None:
        path = DEFAULT_LEDGER_PATH  # resolved at call time — tests repoint it
    total = _bucket()
    by_kind: dict[str, dict] = {}
    by_style: dict[str, dict] = {}

    if path.exists():
        for line in path.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            buckets = [
                total,
                by_kind.setdefault(r.get("kind", "unknown"), _bucket()),
                by_style.setdefault(r.get("style_class", "unknown"), _bucket()),
            ]
            pipeline = r.get("pipeline_verdict")
            human = r.get("human_verdict")
            for b in buckets:
                if pipeline is None:
                    b["null_n"] += 1
                elif pipeline in DEFERRAL:
                    b["deferral_n"] += 1
                elif pipeline in DECISIVE:
                    agree = (pipeline == "pass") == (human == "approved")
                    b["agree" if agree else "disagreements"] += 1

    return {
        "total": _rates(total),
        "by_kind": {k: _rates(b) for k, b in by_kind.items()},
        "by_style_class": {k: _rates(b) for k, b in by_style.items()},
    }
