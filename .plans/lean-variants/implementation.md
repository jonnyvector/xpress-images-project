# lean-variants — Implementation Plan

## ⚠️ Execution Protocol

A progress report exists at `.plans/lean-variants/progress-report.md`.
Mandatory for all agents: run `plan-db check-progress --plan
"lean-variants"` before starting a milestone; its current-cutoff
checkboxes are the spec; check each box as the feature completes; a
milestone is not done until every box under it is checked; deferred/
superseded items never count as current blockers.

## Architecture

Variant generation gains a per-project conditioning mode
<!-- D-001 -->: `variant_hint_mode="styled"` (default — today's
behavior, byte-identical) or `"lean"`, which swaps the style's
`variation_hint` for the new bare constant `LEAN_VARIATION_HINT`
("Preserve the exact door structure from before. Change only the wood
material.") <!-- D-005 --> while `style_notes` (spec width facts) still
appends. The mode is resolved once per generation run in the worker and
captured by the QA-lane regen closure — lean doors regen lean, styled
doors regen styled, no cross-mode de-escalation <!-- D-006 -->. Every
run logs its resolved mode <!-- D-008 -->. Rollout is staged with
probes before palettes, and top-ups protect operator-approved variants
<!-- D-007 -->.

### Key Constraints

| Constraint | Impact |
|-----------|--------|
| Styled doors byte-identical on every path (batch/retry/regen) | Locked by tests; 87% pass rate preserved <!-- D-006 --> |
| Judge, drift check, auto-accept, Stage-A untouched | Drift check operator-vindicated 2026-07-11 <!-- D-003 --> |
| Bare hint makes NO geometry claims | `STYLES["minimal"]`'s width sentence explicitly rejected <!-- D-005 --> |
| No RTF project gets lean mode | Wood-only wording; white-RTF anchor recipe untouched <!-- D-005 --> |
| Approved variants never destroyed | Top-up (`reset_existing=False`, unapproved woods only) <!-- D-007 --> |
| Single-writer: one mutating process, full drain; approvals via API when server up | ops_single_writer memory; mode-setting runs server-DOWN <!-- D-008 --> |
| Manifest load: `data.get("variant_hint_mode", "styled")` | Old manifests must not load None <!-- D-008 --> |
| GEMINI key via `read_api_key()`; nothing under output/.projects deleted; signatures never rewritten | Standing invariants |

### Boundaries

- `backend/generator.py` owns the hint swap: `LEAN_VARIATION_HINT`
  constant + `generate_variation(lean=False)`. No mode knowledge.
- `backend/state.py` owns persistence: field + manifest save/load.
- `backend/worker.py` owns resolution: mode → `lean` flag per run,
  threading through batch/retry/regen closures, and the mode log line.
- `scripts/variant_wave.py` owns rollout ergonomics: `--topup`, per-door
  mode print.
- QA modules untouched.

### Observability

Per generation run <!-- D-008 -->: one line
`[variants <project_id>] hint=lean|styled notes=<present|empty>`
emitted where the mode is resolved (batch start, retry, regen), so run
logs prove which conditioning every draw carried.

---

## Phases

### Phase 1: Core mode (M1)

**Goal:** the mode exists end-to-end in one process: persisted field +
generator flag, styled path provably unchanged.

#### M1: `variant_hint_mode` + `generate_variation(lean=…)`

- **Dependencies:** none
- **Effort:** S
- **Tasks (TDD):**
  1. RED: `variant_hint_mode` roundtrips the manifest; an old manifest
     without the key loads `"styled"` (write manifest json without key,
     reload store).
  2. GREEN: field after `profile_image_path` in `ProjectState`; save
     `"variant_hint_mode"`; load with explicit `"styled"` default.
  3. RED (fake-client capture, pattern `tests/test_learn_temperature.py`):
     `generate_variation(lean=True)` prompt contains
     `LEAN_VARIATION_HINT` and NOT the styled hint; still appends
     STRUCTURAL DETAILS from style_notes; `lean=False` prompt
     byte-identical to today for the same inputs; swatch part intact.
  4. GREEN: `LEAN_VARIATION_HINT` constant + `lean` param swapping only
     the hint source.
  5. REFACTOR: lint, full suite, commit.

### Gate 1→2

- [ ] Full suite green; styled-path byte-identity test locked

### Phase 2: Plumbing + rollout ergonomics (M2)

**Goal:** the persisted mode drives every generation path with logged
resolution; the wave script can top up.

#### M2: worker plumbing + `--topup`

- **Dependencies:** M1
- **Effort:** M
- **Tasks (TDD):**
  1. RED: `_run_generation` with a lean-mode project passes `lean=True`
     to `generate_variation` (stub generator capture); styled-mode
     passes `lean=False`; `_run_retry` same; the RegenContext closure
     regenerates with the SAME resolved mode (lean door → lean regen;
     styled door → styled regen — both directions locked).
  2. RED: the reference-image branch
     (`generate_variation_from_reference`) is unaffected by lean mode.
  3. RED: mode log line emitted (`hint=lean`/`hint=styled`).
  4. GREEN: resolve `lean = project.variant_hint_mode == "lean"` in
     `start_generation`/`_run_generation` and `start_retry`/`_run_retry`;
     thread through `_generate_for_selection`; capture in the
     `_attempt` regen closure; emit the log line.
  5. RED: `variant_wave.py --topup` computes only palette woods lacking
     an approved variant for the door and calls `onboard_variants` with
     `reset_existing=False` and that subset; without `--topup`, a door
     that HAS approved variants is refused (protection, not silent
     reset).
  6. GREEN: implement `--topup` + per-door resolved-mode print in the
     wave script.
  7. REFACTOR: lint (backend/scripts/tests), full suite, commit.

### Gate 2→3

- [ ] Full suite green; regen-mode-capture test locked both directions
- [ ] Wave script refuses `reset_existing` over approved variants

### Phase 3: Prep + staged rollout (M3, operator-gated)

**Goal:** ten doors set lean, notes backfilled, and the staged spend
resolves OQ-1/OQ-2 before the tail is committed.

#### M3: prep + stages

- **Dependencies:** M2
- **Effort:** M (spend-dominated)
- **Tasks:**
  1. Prep (dev server DOWN): one-off sets `variant_hint_mode="lean"`
     for Mitchell, Fallbrook, Baldwin, Dylan, Rhode Island, Journey,
     Hamilton, Melbourne, Windsor, Finley; backfills
     `wood_specs.learn_notes` width notes into empty `style_notes` for
     Melbourne, Windsor, Fallbrook; prints `project_id + name + mode +
     notes` for all ten → operator eyeball ack <!-- D-008 -->.
  2. Prep: verify Fallbrook's classification against its catalog hero
     (OQ-2); correct `door_style`/spec if wrong before any draw.
  3. Stage 1 (~$1.21, operator go): 3×3 probe — Baldwin, Windsor,
     Rhode Island × maple/cherry/white-oak; artifact page; operator
     verdicts resolve OQ-1.
  4. Stage 2 (operator go): one full lean palette on the strongest
     probe door via the wave; review between.
  5. Stage 3 (operator go): remaining doors in waves; Rhode Island via
     `--topup`; single-writer discipline; per-door scorecard appended
     to this plan's progress report. Honest budget ~$70-85 incl.
     auto-regens <!-- D-007 -->.

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation | Owner |
|------|----------|------------|------------|-------|
| frame_narrow lean pass rate low (8/10 doors, untested) | high | medium | Stages 1-2 measure for ~$6 before ~$60 tail | operator gates |
| Mode clobbered by stale server save → silent styled re-run | medium | low | server-down prep, eyeball ack, per-run mode log | D-008 |
| Lean per-draw variance floods queue | medium | medium | unchanged gates + caps; wave rhythm reviews | stages |
| Fallbrook misclassified (style drives geometry routing) | medium | medium | OQ-2 prep verification before draws | M3.2 |
| Best-of mixes regimes on width-blind judge | low | low | noted in RFC; within-door conditioning is uniform | accepted |

---

## Escape Hatches

1. **If Stage 1 probes fail on frame_narrow** (fattening without the
   note, or with it): stop; the skinny class needs a facts-style
   variant conditioning instead — regress to decompose with the probe
   evidence.
2. **If the gate door (Stage 2) lands < ~60% operator-clean**: hold
   Stage 3; review defects; consider per-door notes before more spend.
3. **If Fallbrook is misclassified (OQ-2)**: fix spec + door_style and
   route it through re-onboarding, not this rollout.

---

## Progress Report Accounting

Normalized accounting per planner invariants; before resuming
implementation or declaring convergence run
`plan-db check-progress --plan "lean-variants"`.

---

## Validation Commands

```bash
uv run pytest -q
npm run lint && uv run ruff check scripts/ tests/
ps aux | grep -E "variant_|onboard_" | grep -v grep   # single-writer precheck
```

---

## Decisions

Canonical in `.plans/lean-variants/plan.db` (D-001…D-008; D-005 amends
D-001, D-006 supersedes D-002's global de-escalation, D-007 amends
D-004). Query:

```bash
npx tsx <skill-dir>/scripts/plan-db.ts query-decisions --plan "lean-variants"
```
