# lean-conditioning — Progress Report

> Auto-generated from implementation plan. This is the canonical
> source of truth for what is done and what remains. Update this
> file as features are implemented — never mark a milestone complete
> until every current-cutoff checkbox under it is checked.

> Current focus: Phase 2 — Lean plumbing + observability

## Phase 1: Spike — lean-tail composition (COMPLETE 2026-07-08)

### M1: Probe matrix
Source: `.plans/lean-conditioning/artifacts/spike-report.md`

- [x] Journey/Dylan probe matrix run (bare ×3 + anchored ×3 each, + Dylan width-note arm ×3)
- [x] A-001 validated (pass) and A-002 validated (fail) in plan-db with evidence
- [x] Tail-mix decision D-012 recorded and mirrored into M3 tasks

## Phase 2: Lean plumbing + observability

### M2: Lean flag + prompt return (generator/worker)
Source: `backend/generator.py::learn_door_style`, `backend/worker.py`,
`.plans/lean-conditioning/implementation.md` M2

- [ ] `learn_door_style(lean=True)` uses the lean prompt text in place of `STYLES[door_style]["learn_prompt"]`
- [ ] lean=True retains the corner-style block (sharp and bullnose)
- [ ] lean=True retains the CRITICAL DIMENSIONS block
- [ ] lean=True retains the RTF material block when `material_type="rtf"`
- [ ] lean=True retains image parts, including optional `profile_image_path`
- [ ] `GenerationResult` carries the assembled prompt for a styled call
- [ ] `GenerationResult` carries the assembled prompt for a lean call
- [ ] `start_learning` accepts and forwards `lean` and `attempt_label` keywords
- [ ] `_run_learn` forwards `lean`/label to `learn_door_style` and receives the prompt
- [ ] Sidecar written to `output/.onboard/prompts/<pid>/<label>-<utc-ts>.txt`
- [ ] Layer-summary log line emitted (`style=<key>|lean`, notes present/empty, anchor yes/no)
- [ ] Sidecar write failure is logged and the learn still succeeds
- [ ] UI-initiated learns get label `ui`
- [ ] El Dorado (`141216d1`) `door_style` reverted to `raised_panel` with `base_image_id` unchanged
- [ ] Full suite green + lint (backend, scripts, tests) after M2

## Phase 3: Ladder redesign (fixed split)

### M3: Fixed split in `learn_conditioning`/`onboard_replica`
Source: `backend/onboarding.py`, `.plans/lean-conditioning/implementation.md` M3

- [ ] Attempt 0 conditioning unchanged (style prompt + spec notes + facts note)
- [ ] Attempt 1 maple rung unchanged (wood, `allow_maple=True`)
- [ ] Attempt 1 native+corrective unchanged (RTF, `allow_maple=False`)
- [ ] Defect corrective from attempt 0 still feeds attempt 1
- [ ] Anchor still attaches at attempt 1 (existing anchor-gating test passes)
- [ ] Attempts ≥ 2 call `learn_fn` with `lean=True`
- [ ] Attempts ≥ 2 `style_notes` == spec width note for doors with `frame_width_in`
- [ ] Attempts ≥ 2 `style_notes` == "" for doors without `frame_width_in`
- [ ] Attempts ≥ 2 pass `profile_bytes=None` (no anchor in the tail)
- [ ] Every rung runs temperature 0; rising-temperature schedule removed
- [ ] `attempt_cap=1` never reaches the lean tail
- [ ] Attempt labels `attempt{i}` threaded through to the worker
- [ ] `base_notes` split into separable spec-note and facts-note inputs
- [ ] Old temperature-schedule tests updated (not silently deleted)
- [ ] Full suite green + lint after M3

## Phase 4: Style-prompt audit

### M4: Audit table + surgical edit
Source: `backend/styles/catalog.py`, `docs/qa-style-prompt-audit.md`

- [ ] Audit table covers all 38 `learn_prompt`s with flagged prior-cueing vocabulary
- [ ] Table lists the 3 sibling styles duplicating "bevel profile" as flagged-not-edited
- [ ] `raised_panel`'s `learn_prompt` contains no "bevel" token (test-locked)
- [ ] `raised_panel`'s prompt still names the panel raise
- [ ] Operator has reviewed the audit table

## Phase 5: Rollout (operator-gated)

### M5: Resistant-class batches
Source: `scripts/onboard_wood.py`, spike-report roster

- [ ] Gate 3→4: El Dorado dry-run through the new ladder (mechanics verified: lean tail at attempt 2, labels + sidecars correct)
- [ ] Batch 1: Journey re-onboarded via driver, replica in Stage-A review
- [ ] Batch 1: Dylan re-onboarded via driver, replica in Stage-A review
- [ ] Batch 2+: remaining mitered skinny shakers (~18) under operator-approved ceiling
- [ ] Batch 2+: remaining rejected doors under operator-approved ceiling
- [ ] Per-door outcome table (attempts, winning rung, spend) appended to this report

## Deferred follow-up

- [ ] Watch item: El Dorado's first variant batch reviewed for `variation_hint` mismatch (lean-learned replica under `raised_panel` hint)
- [ ] The 3 sibling styles' "bevel profile" phrasing — edit only when their door class shows failures (D-004)

## Superseded/obsolete checklist debt

(none)

## Summary
- Total features: 44 (3 complete + 41 remaining)
- Completed: 3
- Remaining: 41
- Current cutoff blockers: 41
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 0
