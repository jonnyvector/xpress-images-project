# lean-variants — Progress Report

> Auto-generated from implementation plan. Canonical source of truth
> for what is done and what remains. Check each box as the feature
> completes — never mark a milestone complete until every current-cutoff
> checkbox under it is checked.

> Current focus: Phase 3 — Prep + staged rollout (M3, operator-gated)

## Phase 1: Core mode

### M1: `variant_hint_mode` + `generate_variation(lean=…)`
Source: `backend/state.py`, `backend/generator.py`, implementation.md M1

- [x] `variant_hint_mode` field on `ProjectState` (default `"styled"`), manifest key saved
- [x] Old manifest WITHOUT the key loads `"styled"` (explicit `data.get(..., "styled")`, test-locked)
- [x] Roundtrip test: set `"lean"`, reload fresh store, still `"lean"`
- [x] `LEAN_VARIATION_HINT` constant: "Preserve the exact door structure from before. Change only the wood material." — no geometry claims
- [x] `generate_variation(lean=True)` prompt uses the bare hint, not the styled hint
- [x] `generate_variation(lean=True)` still appends `style_notes` as STRUCTURAL DETAILS
- [x] `generate_variation(lean=False)` prompt byte-identical to today (locked)
- [x] Swatch part / signature-first order / temp 0.3 unchanged under lean
- [x] Full suite green + lint after M1

## Phase 2: Plumbing + rollout ergonomics

### M2: worker plumbing + `--topup`
Source: `backend/worker.py`, `scripts/variant_wave.py`, implementation.md M2

- [x] `_run_generation` resolves `lean` from `project.variant_hint_mode` and passes it through (lean-mode test)
- [x] Styled-mode project passes `lean=False` (locked)
- [x] `_run_retry` resolves the mode the same way
- [x] RegenContext closure regenerates with the SAME resolved mode — lean door → lean regen (test)
- [x] Styled door → styled regen (test, no cross-mode de-escalation)
- [x] Reference-image branch (`generate_variation_from_reference`) unaffected by the flag
- [x] Mode log line emitted per run: `[variants <pid>] hint=lean|styled notes=<present|empty>`
- [x] `variant_wave.py --topup`: selects only palette woods lacking an approved variant; `reset_existing=False`
- [x] Wave refuses a non-topup run on a door WITH approved variants (protection test)
- [x] Wave prints each door's resolved mode before generating
- [x] Full suite green + lint (backend, scripts, tests) after M2

## Phase 3: Prep + staged rollout (operator-gated)

### M3: prep + stages
Source: implementation.md M3

- [ ] Prep one-off (dev server DOWN): lean mode set on all ten doors; prints id+name+mode+notes; operator eyeball ack
- [ ] Width notes backfilled from spec for Melbourne, Windsor, Fallbrook
- [ ] OQ-2: Fallbrook classification verified against catalog hero before any draw
- [ ] Stage 1 probe (operator go, ~$1.21): Baldwin/Windsor/Rhode Island × 3 swatches, artifact page, operator verdicts recorded (resolves OQ-1)
- [ ] Stage 2 gate door (operator go): one full lean palette, wave rhythm review
- [ ] Stage 3 waves (operator go): remaining doors; Rhode Island via `--topup`; single-writer discipline
- [ ] Per-door scorecard appended to this report

## Deferred follow-up

- [ ] El Dorado variant batch watch item (lean-learned replica under `raised_panel` hint) — carried from lean-conditioning
- [ ] RTF lean-mode wording (`rtf_minimal`-style hint) if lean mode ever expands past wood doors

## Superseded/obsolete checklist debt

(none)

## Summary
- Total features: 27
- Completed: 20
- Remaining: 7
- Current cutoff blockers: 7
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 0
