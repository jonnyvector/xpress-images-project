#!/usr/bin/env python
"""Calibration gate for the replica identity judge.

Replays the 2026-07-06/07 operator review session (approvals.json, kind=replica)
through extraction + identity judging and reports catch/false-fail rates against
the acceptance bar (catch >= 80% of rejects, false-fail <= 20% of approves).

Profile specs are cached per project under output/.qa/profile_specs/ so prompt
iterations re-run cheaply. Rows whose images can't be resolved are listed, never
silently dropped.

Usage:
    uv run python scripts/qa_replica_eval.py [--limit N] [--since 2026-07-06T10:00]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402
from google import genai  # noqa: E402
from onboard_wood import resolve_profile  # noqa: E402

from backend.qa.judge import judge_replica_identity  # noqa: E402
from backend.qa.profile_spec import extract_profile_spec  # noqa: E402

PROJECTS = Path("output/.projects")
APPROVALS = Path("output/.qa/approvals.json")
SPEC_CACHE = Path("output/.qa/profile_specs")
REPORT = Path("output/.qa/replica_eval.json")
DEFAULT_SINCE = "2026-07-06T10:00"
CATCH_BAR, FALSE_FAIL_BAR = 0.80, 0.20


def session_replica_decisions(approvals: list[dict], since: str) -> list[dict]:
    """Operator replica verdicts in the calibration window, oldest first."""
    rows = [r for r in approvals
            if r.get("kind") == "replica" and r.get("decided_at", "") >= since]
    rows.sort(key=lambda r: r.get("decided_at", ""))
    return rows


def door_code(project_name: str) -> str:
    """Catalog door name from a project name ('El Dorado Cabinet Door' -> 'El Dorado')."""
    for suffix in (" Cabinet Door", " Drawer Front"):
        if project_name.endswith(suffix):
            return project_name[: -len(suffix)]
    return project_name


def _cache_path(project_id: str, anchored: bool) -> Path:
    """Anchored extractions cache separately — the drawing changes the facts."""
    name = f"{project_id}__anchored.json" if anchored else f"{project_id}.json"
    return SPEC_CACHE / name


def _profile_bytes(manifest_data: dict, name: str) -> bytes | None:
    """The door's cross-section: stored manifest path first, catalog lookup second."""
    stored = manifest_data.get("profile_image_path")
    if stored and Path(stored).exists():
        return Path(stored).read_bytes()
    p = resolve_profile(door_code(name))
    return p.read_bytes() if p else None


def resolve_replica_image(project_dir: Path, image_id: str) -> Path | None:
    """Find the exact replica image an approval refers to: the active base door
    if ids match, else the archived version with that base_image_id."""
    manifest = project_dir / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text()).get("base_image_id") == image_id:
        p = project_dir / "base_door.bin"
        return p if p.exists() else None
    versions = project_dir / "versions"
    if versions.exists():
        for v in sorted(versions.iterdir()):
            meta = v / "meta.json"
            if meta.exists() and json.loads(meta.read_text()).get("base_image_id") == image_id:
                p = v / "base_door.bin"
                return p if p.exists() else None
    return None


def rates(rows: list[dict]) -> dict:
    rejects = [r for r in rows if r["operator"] == "rejected"]
    approves = [r for r in rows if r["operator"] == "approved"]
    catch = (sum(1 for r in rejects if r["disqualified"]) / len(rejects)) if rejects else 0.0
    false_fail = ((sum(1 for r in approves if r["disqualified"]) / len(approves))
                  if approves else 0.0)
    return {"catch_rate": catch, "false_fail_rate": false_fail,
            "rejects": len(rejects), "approves": len(approves),
            "accepted": catch >= CATCH_BAR and false_fail <= FALSE_FAIL_BAR}


def _cached_facts(client, project_id: str, source: Path,
                  profile_bytes: bytes | None = None) -> list[str]:
    SPEC_CACHE.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(project_id, anchored=profile_bytes is not None)
    if cache.exists():
        return json.loads(cache.read_text())
    facts = extract_profile_spec(client, source.read_bytes(), profile_bytes=profile_bytes)
    cache.write_text(json.dumps(facts))
    return facts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N rows")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    args = ap.parse_args()

    client = genai.Client(api_key=read_api_key())
    approvals = json.loads(APPROVALS.read_text())["approvals"]
    decisions = session_replica_decisions(approvals, args.since)
    if args.limit:
        decisions = decisions[: args.limit]

    rows, skipped = [], []
    for dec in decisions:
        pid = dec["project_id"]
        pdir = PROJECTS / pid
        manifest = pdir / "manifest.json"
        manifest_data = json.loads(manifest.read_text()) if manifest.exists() else {}
        name = manifest_data.get("name", pid)
        source = pdir / "upload.bin"
        replica = resolve_replica_image(pdir, dec["image_id"])
        if not source.exists() or replica is None:
            skipped.append((name, "missing source" if not source.exists() else "image not found"))
            continue
        profile_bytes = _profile_bytes(manifest_data, name)
        try:
            facts = _cached_facts(client, pid, source, profile_bytes=profile_bytes)
        except RuntimeError as exc:
            skipped.append((name, f"extraction failed: {exc}"))
            continue
        result = judge_replica_identity(client, source.read_bytes(), replica.read_bytes(),
                                        facts, key=f"{pid}:{dec['image_id']}",
                                        profile_bytes=profile_bytes)
        if result.verdict == "error":
            skipped.append((name, f"judge error: {result.reason}"))
            continue
        rows.append({"name": name, "project_id": pid, "operator": dec["verdict"],
                     "disqualified": result.disqualified, "defects": result.defects,
                     "anchored": profile_bytes is not None})
        mark = "✓" if (dec["verdict"] == "rejected") == result.disqualified else "✗"
        print(f"{mark} {name:30s} operator={dec['verdict']:9s} judge_disq={result.disqualified}"
              f"  {('; '.join(result.defects[:2]))[:80]}")

    summary = rates(rows)
    # Anchored runs use a different QA path (drawing-aware judging) than the
    # pre-anchor baseline — clobbering REPORT would erase the number we
    # compare anchored results against.
    report_path = (REPORT.with_name("replica_eval_anchored.json")
                   if any(r["anchored"] for r in rows) else REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({"rows": rows, "summary": summary,
                                       "skipped": skipped}, indent=2))
    print(f"\ncatch_rate={summary['catch_rate']:.0%} (bar >= {CATCH_BAR:.0%})"
          f"   false_fail_rate={summary['false_fail_rate']:.0%} (bar <= {FALSE_FAIL_BAR:.0%})"
          f"   -> {'ACCEPTED' if summary['accepted'] else 'NOT ACCEPTED'}")
    if skipped:
        print(f"skipped {len(skipped)} rows (not silently dropped):")
        for name, why in skipped:
            print(f"  - {name}: {why}")
    print(f"report -> {report_path}")


if __name__ == "__main__":
    main()
