# lean-variants — Progress Report

> Auto-generated from implementation plan. Canonical source of truth
> for what is done and what remains. Check each box as the feature
> completes — never mark a milestone complete until every current-cutoff
> checkbox under it is checked.

> Current focus: COMPLETE — deferred follow-ups remain

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

- [x] Prep one-off (server down): lean set on ten doors, table acked; RI later reverted to styled (D-010)
- [x] Width backfill impossible (no measurements exist, D-009); flat-panel GUARD fact added instead (D-011); Mitchell's guard removed after it flattened his bevel (D-012)
- [x] OQ-2: Fallbrook classification verified CORRECT (mitered flat panel + decorative inner profile)
- [x] Stage 1 probes ×2 rounds (~$2.40): verdict-widget page; RI collapse caught ($0.40 vs $5); flat guard invented+validated; per-door recipes fixed
- [x] Stage 2 gate: Windsor 32/38 (84%) through the full pipeline
- [x] Stage 3 waves A/B/C complete; --topup protection fired correctly for Dylan/Baldwin; single-writer held
- [x] Per-door scorecard appended below


## Stage-3 scorecard (approved variants per door)

| Door | Library variants | Styled baseline | Recipe |
|---|---|---|---|
| Fallbrook | 36/38 | 0/38 | lean + flat guard |
| Baldwin | 34 (33 new) | 1/38 | lean + width + guard |
| Windsor | 32/38 | — (parked) | lean + flat guard |
| Mitchell | 31/38 | 0/38 | bare lean |
| Finley | 28/38 | — | lean + width + guard |
| Melbourne | 20/38 | — | lean + flat guard |
| Rhode Island | 13 (styled top-up 0/25 accepted, drift-flags to operator) | 13/37 | styled (lean collapses it) |
| Dylan | 7 | 1/38 | lean + width + guard (2.25" hardest class) |
| Journey | 4/37 | — | lean + width + guard (2" hardest) |
| Hamilton | 3/38 | — | lean + width + guard (drift-flagged, 32 clean-scored queued) |

TOTAL: 208 library variants across the ten rollout doors (~$62 spend incl. probes/regens).
The skinniest doors (Journey/Hamilton/Dylan) remain hard; their queued clean-scored
drift flags await operator verdicts.

## Deferred follow-up

- [ ] El Dorado variant batch watch item (lean-learned replica under `raised_panel` hint) — carried from lean-conditioning
- [ ] RTF lean-mode wording (`rtf_minimal`-style hint) if lean mode ever expands past wood doors

## Superseded/obsolete checklist debt

(none)

## Summary
- Total features: 27
- Completed: 27
- Remaining: 0
- Current cutoff blockers: 0
- Accepted/deferred follow-up: 2
- Superseded/obsolete checklist debt: 0
