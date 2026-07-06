# Autonomous RTF Door Onboarding — Implementation Plan

Source of truth: `plan.db` (decisions D-001..D-008, assumptions A-001..A-002).
Structure: TDD ordering (test spec first, then implementation) per milestone.

## Overview

Build a reusable, tested onboarding core (`backend/onboarding.py`) plus a thin
CLI driver (`scripts/onboard_rtf.py`). The immediate run onboards the next 5
RTF cabinet doors to **queued, judge-clean replicas** and stops for operator
approval (D-001). The variant auto-run phase (M6) is part of the system but
activates only after the operator approves replicas.

---

## M1 — Onboarding core: policy + quality gate + best-of

New module `backend/onboarding.py` with pure, unit-tested functions.

- [ ] **RED** `tests/test_onboarding_core.py`: `replica_queue_ready(verdict, min_score)` — True when all `scores >= min_score` and `geometry != "drift"`; False on a low dim, on `geometry=="drift"`, and when scores missing (not done).
- [ ] **RED** best-of: `best_attempt_index(verdicts)` picks max `sum(scores)`, ties → latest.
- [ ] **RED** verdict→action: `variant_action(verdict)` → `auto_accept` (pass), `regenerate` (regenerate under cap), `escalate` (needs_human/error). (D-003)
- [ ] **RED** ladder: `learn_conditioning(attempt, low_dim)` → dataclass `{learn_in_maple: bool, temperature: float, extra_note: str}` per D-006 table.
- [ ] **GREEN** implement the four functions + `LearnConditioning` dataclass.
- [ ] **REFACTOR** module docstring stating responsibility (policy only; no I/O).

## M2 — Optional temperature knob on learn (driver-only variety)

- [ ] **RED** `tests/test_learn_temperature.py`: `learn_door_style` default `temperature=0.0` preserved; passing `temperature=0.4` reaches the `GenerateContentConfig` (assert via a fake client capturing config). App/HTTP path unchanged.
- [ ] **GREEN** add `temperature: float = 0.0` param to `DoorGenerator.learn_door_style`, thread into config. `start_learning`/`_run_learn` accept + pass an optional `temperature` (default 0.0).
- [ ] **REFACTOR** confirm no existing caller changes behavior (grep call sites).

## M3 — Replica onboarding loop (learn → judge → re-learn ≤cap)

- [ ] **RED** `tests/test_onboard_replica.py` with a fake generator + in-memory store: a weak first replica (low score) triggers a re-learn; a queue-ready replica stops the loop; cap reached → returns best attempt flagged needs_human. Assert spend counter increments and the ceiling halts further learns.
- [ ] **RED** poll: `wait_for_verdict(store, pid, image_id, timeout)` returns the verdict once `qa_status=="done"`; raises on timeout.
- [ ] **GREEN** `onboard_replica(store, project, api_key, *, attempt_cap=5, min_score, spend)` in `backend/onboarding.py`: loop `start_learning`(conditioning per ladder) → `wait_for_verdict` → `replica_queue_ready`? stop : re-learn; track best-of via `qa_verdicts`; return `OnboardResult(status, attempts, best_scores, base_image_id)`.
- [ ] **GREEN** cost guard: increment a `Spend` counter before each learn; stop at run ceiling, return partial.
- [ ] **REFACTOR** ensure the loop never approves a replica (Stage-A preserved) and never deletes prior versions (re-learn archives, per existing `_run_learn`).

## M4 — Batch driver CLI

- [ ] **RED** `tests/test_onboard_driver.py`: door-spec table resolves each code to `~/Desktop/Xpress/Decore Catalog/rtf/<CODE>-3-4/hero/door.jpg`; missing source → skip+record, not crash. Idempotent: a door whose project already exists with a signature is skipped.
- [ ] **GREEN** `scripts/onboard_rtf.py`: the 5-door spec (code, door_style, style_notes); for each — `create`/`update`(full RTF palette via `/api/swatches`)/`save_upload` → `onboard_replica`; print a per-door summary (status, attempts, best min-score) and a run total.
- [ ] **GREEN** reads `GEMINI_API_KEY` from `.env`; run ceiling default (replica-only ≈ $8 headroom).
- [ ] **REFACTOR** summary distinguishes queued-ready vs queued-needs-human vs skipped.

## M5 — Run the 5 doors (replica phase)

- [ ] Run `scripts/onboard_rtf.py` for FR556, KB732, DT223, DP8, AP768.
- [ ] Verify each replica is in `GET /qa/review-queue` with `replica.pending==true`.
- [ ] Build an operator preview (before/after style images + status) and hand off for approval.
- [ ] Record actual attempts/scores per door; validate A-001 (≤5 reaches queue-ready).

## M6 — Variant auto-run phase (DEFERRED: activates after operator approves replicas)

Not run this turn (no approved replicas yet). Part of the system for the next
invocation.

- [ ] **RED** `tests/test_variant_autoaccept.py`: after replica approval, generating the palette with onboarding settings — a `pass` variant gets an auto `approved` record (D-003); `needs_human`/`error` stay queued; `regenerate` loops up to cap=5.
- [ ] **GREEN** variant phase: reuse existing QA-lane variant auto-regen with `max_auto_retries=5` (onboarding override), plus an auto-accept sweep that writes an `approved` ApprovalStore record for `pass` variants.
- [ ] **GREEN** driver subcommand `onboard_rtf.py --variants <project_id>` gated on `replica_approved`.
- [ ] **REFACTOR** confirm auto-accept only fires for judge `pass`, never for unsure verdicts.

---

## Gates

- After M1–M4: full `uv run pytest` green before the M5 run.
- M5 spends real tokens — respect run ceiling; stop and report if hit.
- M6 must not fire without `replica_approved==true` on the project.
