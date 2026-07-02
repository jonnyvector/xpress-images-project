# Judgment Pipeline — Design

**Date:** 2026-07-02
**Status:** Draft for review

## Purpose

Automated quality judgment for generated cabinet door images. Given a sample
photo and its generated replica/variants, produce a verdict per image —
**pass / regenerate / needs-human** — with a stated reason. The judge is
calibrated against Jonny's real accept/reject history and measured before it
is trusted.

This is phase 1 of automating bulk variant generation for hundreds of
products. The judge is the risky, load-bearing piece, so it is built and
proven first.

**Out of scope for this phase:** bulk orchestration/queueing, the
regeneration loop, Shopify/Matrixify CSV export, app UI integration.

## Why this shape

- The differences that make a door image unusable are subtle (a stile a few
  percent too wide, an edge profile that reads as a different product). An
  uncalibrated LLM rubric will confidently pass images Jonny would reject,
  so ground truth comes first and every judge change is measured against it.
- LLM vision and deterministic CV have complementary blind spots: the LLM
  catches semantic problems (profile character, fake-looking grain,
  hallucinated details); aligned geometric comparison catches dimensional
  drift the LLM eyeballs past.
- Some door styles are genuinely hard to generate. The pipeline must learn
  which styles it is not trusted on and route those to human review rather
  than pretend.

## Existing data (calibration source)

Generated history lives in `output/.projects/<id>/` (~246 projects):

| File | Content |
|------|---------|
| `manifest.json` | name, door/corner style, `result_names` (index → wood name) |
| `upload.bin` | original sample photo (missing in some projects) |
| `base_door.bin` | learned replica |
| `result_N.bin` | generated variants (plain JPEGs) |
| `versions/vN/` | archived pre-re-learn signature/base door/results |

Key insight: current results are mostly accepts; `versions/` archives likely
hold the generations that were rejected and redone. The labeling tool
pre-sorts accordingly so Jonny confirms rather than judges cold.

## Components

Code lives in `backend/qa/` (importable later by the worker), with CLI entry
points in `scripts/`.

### 1. Calibration set builder (`scripts/qa_label.py`)

Walks `output/.projects/` (including `versions/`), pairs each generated image
with its sample (`upload.bin`), replica (`base_door.bin`), wood name, and
swatch image, and emits a contact-sheet HTML labeling page:

- Side-by-side card per image: sample photo (left), generated image (right),
  swatch thumbnail for variants.
- One-click **Accept / Reject**; on reject, a quick reason picker:
  `geometry_drift`, `profile_character`, `material_realism`, `artifacts`,
  `other`.
- Labels persist to `output/.qa/labels.json` keyed by
  `(project_id, version, result_index)`. Relabeling is idempotent.
- Pre-sorted: current results shown as presumed-accept, archived versions as
  presumed-reject; Jonny flips the exceptions.
- Projects missing `upload.bin` are labeled against `base_door.bin` and
  flagged so original photos can be paired in later if found.

Target: 100+ labeled images spanning door styles, deliberately including the
known-difficult styles, with both accepts and rejects per style where
possible.

### 2. Eval harness (`scripts/qa_eval.py`)

Runs any judge configuration over the labeled set and reports:

- **Reject recall** — % of true rejects caught. Primary metric; a miss means
  a bad image reaches the store.
- **False-flag rate** — % of true accepts flagged anyway. This is Jonny's
  residual review workload.
- Per-failure-mode and per-door-style breakdowns, so weaknesses are
  attributable ("misses 40% of profile_character rejects on applied-molding
  styles").

A held-out split (by project, not by image, to avoid leakage) guards against
tuning to the calibration set.

### 3. LLM vision judge (`backend/qa/judge.py`)

Structured-rubric comparison of candidate vs sample (and swatch for
variants). Returns JSON:

```json
{
  "panel_layout_match": 1-5,
  "proportions_match": 1-5,
  "profile_character_match": 1-5,
  "material_realism": 1-5,
  "swatch_fidelity": 1-5,
  "artifacts": ["list of observed defects"],
  "verdict": "pass | fail",
  "confidence": "high | low",
  "reason": "one sentence"
}
```

- Model: start with Gemini (key already provisioned); the eval harness makes
  model choice an empirical question, not a debate.
- Low-confidence or near-threshold results trigger 2 additional independent
  votes; majority wins, disagreement escalates to needs-human.
- Prompt includes door-style-specific guidance where the eval shows it helps.

### 4. Deterministic geometry checks (`backend/qa/geometry.py`) — conditional

Added **only if** the eval shows the LLM judge missing geometry rejects
(expected, but the eval decides):

- Align candidate to sample (feature match / homography).
- Compare edge maps; measure stile/rail widths and panel bounding boxes;
  report numeric deltas.
- Thresholds calibrated from the labeled set.

### 5. Decision policy (`backend/qa/policy.py`)

Combines judge output (and geometry metrics when present) into
**pass / regenerate / needs-human**:

- Tuned to **over-flag**: uncertainty routes to Jonny, not to pass.
- Per-door-style trust: styles whose labeled pass rate or judge accuracy is
  poor are auto-routed to needs-human entirely.
- All thresholds live in one config file; retuning is an eval run, not a
  code change.

### 6. Review report (`scripts/qa_report.py`)

HTML report of flagged images: side-by-side with sample and swatch, judge
scores and reason attached, grouped by verdict then door style. App-integrated
review queue is deferred until the report proves clunky in practice.

## Data flow

```
output/.projects/**  ──►  qa_label.py  ──►  output/.qa/labels.json
                                                    │
                              ┌─────────────────────┘
                              ▼
judge.py (+ geometry.py)  ◄── qa_eval.py ──► metrics (recall / false-flag)
       │                                          (tune until targets met)
       ▼
policy.py ──► verdicts ──► qa_report.py ──► HTML review sheet
```

## Success criteria

Measured on the held-out split:

1. Reject recall ≥ 95% (target ~100%; every miss is examined individually).
2. False-flag rate ≤ ~20% of accepts.
3. Per-style trust map exists: every door style is either "judge trusted" or
   "needs-human", with data behind the assignment.

If the eval cannot reach these numbers after adding geometry checks and
prompt iteration, that is a real finding — the honest fallback is a judge
that pre-sorts and prioritizes rather than gates, and we report that
explicitly rather than shipping false confidence.

## Error handling

- Unreadable/missing images: skipped and listed in the report, never
  silently dropped.
- Judge API failures: retried with backoff; persistent failure marks the
  image needs-human (fail-safe direction).
- All verdicts + raw judge JSON persist to `output/.qa/verdicts/` so runs are
  resumable and auditable; images already judged are not re-judged unless
  the judge config hash changes.

## Testing

- Unit tests for label store, policy thresholds, and manifest walking
  (fixtures with synthetic project folders).
- The eval harness itself is the integration test for the judge; its metrics
  gate any prompt/model/threshold change.
- Geometry checks (if built) get fixture pairs with known synthetic
  distortions (scaled stiles, shifted panels).

## Open items

1. Failure-mode list assumed as: geometry drift, profile character, material
   realism, artifacts. Confirm/extend during first labeling session.
2. Original sample photos for projects missing `upload.bin` — pair in if
   they still exist elsewhere.
3. Judge model/version choice — decided by eval numbers, not upfront.

## Cost note

Judging is cheap relative to generation (vision-input calls, fractions of a
cent per image vs ~$0.134 to generate). Multi-vote on borderline cases only.
Never re-judge unchanged images; never regenerate passed images (enforced in
phase 2's orchestrator).
