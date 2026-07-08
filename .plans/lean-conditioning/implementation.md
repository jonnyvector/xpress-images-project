# lean-conditioning — Implementation Plan

## ⚠️ Execution Protocol

A progress report exists at `.plans/lean-conditioning/progress-report.md`.
It lists every feature for every milestone as a checkbox.

**Mandatory rules for all agents working on this plan:**

1. Before starting a milestone, run `plan-db check-progress --plan
   "lean-conditioning"` and read its section in the progress report —
   those current-cutoff checkboxes are your spec
2. Check each box as you complete the feature, not at the end
3. A milestone is NOT done until every current-cutoff checkbox under
   it is checked
4. If you find features missing from the report, add them first
5. Never declare a phase complete without updating the current focus
   marker and Summary
6. Deferred follow-up and superseded/obsolete checklist debt must not
   be counted as current blockers

## Context & Rationale (consolidated from RFC-01)

El Dorado failed 16 attempts across three conditioning strategies while
the operator's lean prompt fixed it in four re-rolls: the additive prose
stack (style prompt "bevel profile" + facts note + defect correctives)
CUES the priors it tries to forbid (white-RTF doctrine, 2026-07-03).
Temp-0 learning is non-deterministic (verified 2026-07-08), so re-rolls
sample the distribution without any variety knobs. An adaptive
de-escalation trigger was designed and killed in review: the identity
judge (52–62% catch / 10–19% false-fail, errors systematic per door)
cannot support a state machine — hence the deterministic fixed split
<!-- D-008 -->. The spike then fixed the lean tail's composition
empirically <!-- D-012 -->. Security posture: sidecar files contain only
prompt text under gitignored `output/`; no new trust boundaries; Stage-A
human review remains the sole replica gate. Rollback = revert the
branch; sidecars and audit doc are additive artifacts.

## Architecture

The replica-learn conditioning stack is restructured around a **fixed
prose/lean split** <!-- D-008 -->: attempts 0–1 keep today's conditioning
(style prompt + spec notes + facts note; maple rung at 1 for wood;
defect correctives; anchor-on-retry per the 2026-07-08 profile-anchor
build <!-- D-009 -->), and every attempt from index 2 onward is the
**lean tail** — the lean prompt ("Generate an exact replica of this
door.") with `style_notes` set to the spec-file width note ONLY
(`wood_specs.learn_notes` output; empty for doors without
`frame_width_in`) and NO profile anchor <!-- D-012 -->, re-rolled at
temperature 0 (temp-0 non-determinism supplies variety; the
rising-temperature schedule is removed <!-- D-006 -->). Lean is a
learn-call flag, never a `door_style` mutation <!-- D-003 -->. The tail
composition was fixed by the completed spike (A-001 pass, A-002 fail →
escape hatch 2). Every attempt's assembled prompt is returned on
`GenerationResult` and written by the worker to a timestamped sidecar
<!-- D-005, D-010 -->.

### Key Constraints

| Constraint | Impact |
|-----------|--------|
| Attempts 0–1 byte-compatible with today (incl. anchor-on-retry) | Existing prose-rung tests keep passing; no regression for door classes that work <!-- D-009 --> |
| QA side untouched: facts stay judge criteria on every attempt; drawing feeds extraction/judge unconditionally | Lean drops prose from the learn PROMPT only |
| `door_style` never mutated by the ladder | Variant hints stay truthful; El Dorado reverts to `raised_panel` <!-- D-003 --> |
| All rungs temperature 0 | `learn_conditioning`'s temp schedule deleted <!-- D-006 --> |
| Stage-A human approval remains the sole replica gate | Nothing here approves replicas; blast radius is re-roll spend |
| Nothing under `output/.projects/` deleted; signatures never rewritten | Standing project invariant |
| `output/.qa/labels.json` + frozen 97-verdict window untouched | Calibration integrity |
| GEMINI key via `read_api_key()` (.env) | zshrc shadows the env var |
| Style-prompt edits are surgical and failure-driven | Only `raised_panel`'s "bevel profile" phrase now <!-- D-004 --> |

### Boundaries

- `backend/generator.py::learn_door_style` owns prompt assembly: gains
  `lean` flag (swaps ONLY the style-prompt layer) and returns the
  assembled prompt on `GenerationResult`. No ladder knowledge.
- `backend/onboarding.py` owns policy: which attempt is prose vs lean,
  what notes each carries, attempt labels. No prompt-text knowledge.
- `backend/worker.py` owns I/O: threads `lean` + attempt label, writes
  the prompt sidecar, logs the layer summary.
- `backend/styles/catalog.py` remains the style-prompt source of truth;
  the audit doc (`docs/qa-style-prompt-audit.md`) is documentation, not
  code.
- QA modules (`backend/qa/*`) are out of bounds for this plan.

### Observability

Per learn attempt <!-- D-005, D-010 -->: full assembled prompt at
`output/.onboard/prompts/<project_id>/<label>-<utc-timestamp>.txt`
(labels: `attempt0`…`attemptN` from the ladder, `ui` for app-initiated
learns; timestamp prevents re-run overwrite) + one log line naming the
layers (`style=<key>|lean`, `notes=<present|empty>`, `anchor=<yes|no>`).
Sidecar write failure logs and continues — never fails the learn.

---

## Phases

### Phase 1: Spike — lean-tail composition ✅ COMPLETE (2026-07-08, pre-implementation)

**Outcome** (report: `artifacts/spike-report.md`; ~$2.01 spent,
operator-verdicted): A-001 PASS — the anchor is excluded from the lean
tail (it fattened Journey's frames, leaked the drawing's 3/4 viewpoint
into a render, and induced miters + a raised panel on Dylan). A-002
FAIL — bare lean fattened Dylan's 2.25 in frame 3/3 (the judge
false-matched `stiles_rails` on all six fat draws: confirmed blind
spot); the follow-up arm (lean + spec width note only) held the frame.
Tail composition recorded as <!-- D-012 -->: lean prompt + spec width
note only, no anchor, temp 0.

### Gate 1→2

- [x] A-001 and A-002 resolved with evidence in plan-db (pass / fail)
- [x] Tail-mix decision recorded (D-012) and reflected in M3 tasks

### Phase 2: Lean plumbing + observability (code, no ladder change)

**Goal:** `lean=True` reaches the generator; every learn writes its
assembled prompt sidecar; El Dorado's `door_style` is truthful again.

**Gate from previous:** none (independent of spike outcome).

#### M2: Lean flag + prompt return (generator/worker)

- **Dependencies:** none
- **Effort:** S
- **Tasks:**
  1. RED: test `learn_door_style(lean=True)` uses the lean prompt text,
     keeps corner/dimensions/material blocks and image parts, ignores
     `STYLES[door_style]` prose (capture via stubbed `_call_with_retry`,
     pattern: `tests/test_learn_profile_anchor.py`).
  2. RED: test `GenerationResult` carries the assembled prompt for both
     lean and styled calls.
  3. GREEN: implement `lean` flag + prompt field in
     `backend/generator.py`.
  4. RED: test `start_learning`/`_run_learn` pass `lean` and
     `attempt_label` through; worker writes
     `output/.onboard/prompts/<pid>/<label>-<ts>.txt` and the
     layer-summary line; write failure doesn't fail the learn
     (monkeypatched write).
  5. GREEN: implement worker threading + sidecar + log line.
  6. GREEN: `store.update` El Dorado (`141216d1`) `door_style` →
     `raised_panel` (one-off script or driver flag; replica/signature
     untouched; note the `variation_hint` watch item in the run log).
  7. REFACTOR: lint, full suite, commit.

### Gate 2→3

- [ ] Full suite green; sidecar files appear for a stubbed learn
- [ ] El Dorado manifest shows `door_style=raised_panel`, same
      `base_image_id`

### Phase 3: Ladder redesign (fixed split)

**Goal:** `onboard_replica` runs prose rungs 0–1 exactly as today and
the lean tail from attempt 2, per the spike-decided mix.

**Gate from previous:** Gate 1→2 passed (tail mix known); Gate 2→3
passed (lean flag exists).

#### M3: Fixed split in `learn_conditioning`/`onboard_replica`

- **Dependencies:** Phase 1 outcome (D-012), M2
- **Effort:** M
- **Tasks:**
  1. RED: tests — attempts 0–1 conditioning unchanged (style notes carry
     facts+spec notes; maple at 1; defect corrective on 1; anchor at
     retry 1 per existing test); attempts ≥ 2 call `learn_fn` with
     `lean=True`, `style_notes` = spec width note only (empty for doors
     without `frame_width_in`) and `profile_bytes=None` (NO anchor in
     the tail <!-- D-012 -->), temp 0; temperature schedule gone (no
     rung requests temp > 0); `attempt_cap=1` never reaches lean.
  2. GREEN: rewrite `learn_conditioning` (drop temp schedule, add lean
     rungs) and the `onboard_replica` loop (facts+defect notes only on
     prose rungs; the tail's width-note needs the spec note passed
     separately from the facts note — split the current single
     `base_notes` string into spec-note and facts-note inputs; label
     threading `attempt{i}`).
  3. Update the tests that asserted the old temp schedule (updated, not
     silently deleted).
  4. REFACTOR: docstrings state the split doctrine; lint; full suite;
     commit.

### Gate 3→4

- [ ] Full suite green; ladder tests lock the split
- [ ] El Dorado dry-run through the new ladder (operator-gated ~$0.80):
      reaches lean tail at attempt 2, judge-clean draw within the tail
      (subject to draw luck — a cap-hit with correct labeling/sidecars
      still passes the MECHANICS check; the operator judges the door)

### Phase 4: Style-prompt audit

**Goal:** `docs/qa-style-prompt-audit.md` exists, operator-reviewed;
`raised_panel` no longer says "bevel profile".

**Gate from previous:** none (parallel-safe with Phase 3; sequenced
after to keep one change in flight).

#### M4: Audit table + surgical edit

- **Dependencies:** none
- **Effort:** S
- **Tasks:**
  1. Audit sweep of all 38 `learn_prompt`s for prior-cueing
     profile-character vocabulary; write the findings table (style key,
     phrase, risk note), explicitly listing the three sibling styles
     duplicating "bevel profile" (`raised_panel_radius`, both drawer
     raised-panel styles) as flagged-not-edited <!-- D-004, D-011 -->.
  2. RED: test asserting `raised_panel`'s `learn_prompt` contains no
     "bevel" token (and still names the raise).
  3. GREEN: replace "bevel profile" with "raise profile" in
     `raised_panel` only.
  4. Operator reviews the table; commit.

### Gate 4→5

- [ ] Operator has reviewed the audit table
- [ ] Full suite green

### Phase 5: Rollout (operator-gated)

**Goal:** The resistant class is re-onboarded through the new ladder.

**Gate from previous:** Gates 1→2 … 4→5 all passed.

#### M5: Resistant-class batches

- **Dependencies:** M3, M4
- **Effort:** M (spend-dominated)
- **Tasks:**
  1. Batch 1: the two spike doors (Journey, Dylan) re-onboarded
     properly through the driver (`--force`, keeps operator-corrected
     facts where stored) so signatures land in projects.
  2. Batch 2+: remaining mitered skinny shakers (~18) and remaining
     rejects, batched under an operator-approved ceiling per batch;
     defects + sidecar prompts reviewed between batches.
  3. Stage-A operator review of every replica (unchanged).
  4. Summary: per-door outcome table (attempts, rung that won, spend)
     appended to the plan's progress report.

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation | Owner |
|------|----------|------------|------------|-------|
| ~~Prose-saved doors lose the width note in the tail~~ CLOSED: the tail keeps the width note (D-012, spike evidence) | — | — | resolved by spike | done |
| Lean tail exhausts cap on some doors (n small evidence) | medium | medium | Cap-hit unchanged (best-of + needs_human); Dylan's inside-edge miss shows residual profile-character risk; batches reviewed between runs | Phase 5 batching |
| Judge false-matches frame width (6/6 on Dylan's fat draws) | medium | high | Operator eye is the width verdict in Stage-A and batch reviews; never trust stiles_rails "matches" alone on skinny doors | standing |
| `raised_panel` prompt edit shifts a working distribution | low | low | Single-phrase edit; judge + Stage-A gate everything downstream | M4 |
| Best-of prefers judge-missed draws (more tail re-rolls = more lottery) | low | medium | Pre-existing; Stage-A reviews winner; noted in RFC | accepted |
| El Dorado variant hint mismatch (lean-learned replica, raised_panel hint) | low | low | Watch item on first variant batch | Phase 5 notes |

---

## Escape Hatches

1. ~~If A-001 fails~~ RESOLVED: A-001 passed — anchor excluded from the
   tail (spike, D-012).
2. ~~If A-002 fails~~ TAKEN: A-002 failed — the tail carries exactly the
   spec-file width note (`wood_specs.learn_notes` output) and nothing
   else (spike, D-012).
3. **If the El Dorado dry-run (Gate 3→4) cap-hits on mechanics that are
   correct:** accept the mechanics gate, re-roll El Dorado in Phase 5
   with operator spend approval — draw luck is not a code defect.
4. **If lean-tail rollout underperforms prose baselines broadly
   (Phase 5 batch 1):** stop batches, `regress-stage` to decompose,
   revisit the split boundary (e.g., 3 prose rungs) with the batch
   evidence.

---

## Progress Report Accounting

The progress report is the implementation resume state. Normalized
accounting per the planner invariants: current cutoff blockers vs
accepted/deferred follow-up vs superseded debt vs completed work.
Before resuming implementation or declaring convergence:

```bash
npx tsx <skill-dir>/scripts/plan-db.ts check-progress --plan "lean-conditioning"
```

---

## Validation Commands

```bash
uv run pytest -q                        # full suite (fast, stubbed API)
npm run lint                            # ruff over backend/
uv run ruff check scripts/ tests/      # lint scope not covered by npm script
uv run python scripts/onboard_wood.py --only "El Dorado" --force --cap 5 --ceiling 3   # operator-gated live
```

---

## Decisions

Canonical decisions live in `.plans/lean-conditioning/plan.db`
(D-001…D-012; D-008 supersedes D-001, D-009 amends D-002, D-012 fixes
the lean tail). Query:

```bash
npx tsx <skill-dir>/scripts/plan-db.ts query-decisions --plan "lean-conditioning"
```
