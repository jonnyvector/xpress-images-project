# QA Judgment Pipeline — Operator Guide

The judgment pipeline automatically grades generated door images so you only
look at the ones that need a human. Validated 2026-07-02 on a held-out test
set: **100% of human-rejected images caught, 19.2% of good images flagged
unnecessarily**.

## The mental model

Every generated image gets a verdict:

| Verdict | Meaning | What happens |
|---|---|---|
| `pass` | Safe to use | Nothing — it ships |
| `regenerate` | Confidently bad | Goes back to generation (phase-2 orchestrator) |
| `needs_human` | Uncertain, or requires your approval | Lands in your review pile |

The pipeline is **fail-safe**: every error, ambiguity, or unmeasurable case
routes to `needs_human`. Nothing bad can silently pass; the worst failure
mode is you seeing an image you didn't need to see.

Three layers produce the verdict (in `backend/qa/policy.py`, 12 rules):

1. **Replica anchor (your approvals).** Every project's replica (base door)
   requires your accept before anything else counts — and variants of an
   unapproved replica never pass. This one rule does most of the work: one
   quick approval per project protects all of its variants.
2. **LLM vision judge** (`backend/qa/judge.py`, Gemini). Compares each image
   against the sample photo and swatch with a scoring rubric: layout,
   proportions, profile character, material realism, swatch fidelity.
   Catches semantic problems — wrong profile, fake grain, artifacts.
3. **Geometry measurement** (`backend/qa/geometry.py`, no API cost).
   Measures stile/rail widths, panel positions, and aspect as ratios.
   Variant-vs-replica drift at high confidence is a hard gate (regenerate);
   photo comparisons are advisory (route to you, never auto-regenerate).
   Only runs on framed rectangular styles; slab/louver/arched styles are
   judge-only by design.

## Running a QA cycle

```bash
uv run python scripts/qa_label.py            # labeling UI at http://127.0.0.1:8777
uv run python scripts/qa_label.py --sample 120   # curated calibration subset instead
uv run python scripts/qa_eval.py             # judge + score the train split
uv run python scripts/qa_eval.py --limit 30  # cap API spend while iterating
uv run python scripts/qa_report.py           # build output/.qa/review.html
```

- **Labeling** (`qa_label.py`): side-by-side sample | generated | swatch
  cards. Current results default to accept, archived versions to reject —
  flip the exceptions, tick a reason on rejects, click "Save all on page."
  Labels persist instantly to `output/.qa/labels.json`. **These labels are
  the pipeline's ground truth and your accumulated judgment — treat the file
  like the signatures: irreplaceable.**
- **Evaluating** (`qa_eval.py`): judges every labeled image and prints the
  scorecard — reject recall (must stay ≥95%), false-flag rate, per-reason
  and per-style breakdowns, replica-review load, geometry attribution.
  Verdicts are cached; re-runs only pay for new images or changed config.
  `--holdout` scores the reserved 20% split — run it rarely, only as a
  final check, never to tune against.
- **Reviewing** (`qa_report.py`): writes `output/.qa/review.html` — flagged
  images side-by-side with their sample, judge scores, and the reason.

## Configuration (`backend/qa/policy_config.json`)

Calibrated 2026-07-02; change values only with an eval run to justify it.

- `min_score: 3` — judge rubric floor; any score below it → regenerate
- `untrusted_styles: []` — styles routed straight to you
- `replica_review: true` / `transitive_replica_review: true` — the anchor rules
- `geometry.drift_thresholds` — per style class (`frame_standard` 0.03,
  `frame_narrow` 0.015); `aspect_threshold` 0.04

## Where state lives

Everything is under `output/.qa/` (gitignored):
`labels.json` (ground truth), `verdicts/<config-hash>/` (judge cache),
`geometry/<config-hash>/` (measurement cache), `eval_report.json`,
`review.html`, `site/` (labeling UI). Caches invalidate automatically when
the prompt/model/thresholds change. Errors are never cached, so transient
API failures retry on the next run.

## Troubleshooting

- **Every verdict is `needs_human` / errors mention API key:** three known
  traps. (1) `~/.zshrc` exports an old `GEMINI_API_KEY` — the QA scripts use
  `load_dotenv(override=True)` so `.env` wins, but new scripts must do the
  same. (2) The web app does NOT read `.env` — its key lives in the browser
  (sidebar field), so "app works but eval fails" means the `.env` key is
  bad, and vice versa. (3) Newer Google keys start with `AQ.` (~53 chars),
  not just `AIzaSy` (39) — don't reject on format.
- **"model ... is no longer available":** Google retired the judge model.
  Update `DEFAULT_MODEL` in `backend/qa/judge.py` (or pass `--model`) —
  remember `qa_report.py` needs the same `--model` to find the verdicts.
- **Recall drops after a change:** the eval is the gate. Revert or fix;
  never re-run `--holdout` to make a number look better.

## Known limits & queued follow-ups

- False flags (~19-30% depending on split) are dominated by judge-rubric
  disagreement with your accepts — a judge prompt-iteration round is the
  queued fix, measured against the existing labels.
- ~1,650 older images have no sample photo on file; they route to
  `needs_human` unjudged. Pairing original photos back in would unlock them.
- The in-app graduated-trust workflow (below) now covers generation-time
  judging and the regenerate loop; the Shopify Matrixify export is still
  designed but not built.


## The in-app workflow (graduated trust)

Since 2026-07-03 the pipeline runs **inside the app** — you don't need the
offline scripts for day-to-day work. Trust is graduated:

1. **Stage A — approve the replica.** After Learn, the base door shows an
   Approve/Reject control. Variants are locked (server-enforced, GT-001)
   until you approve. A re-learned replica is a new image and starts
   unapproved again — old approvals never carry over.
2. **Stage B — small batches (≤5).** Generate is capped at 5 resolved
   selections while bulk is locked (GT-002). Every image is judged seconds
   after it lands: badges show pass / regenerate / needs-human / error with
   the judge's reasoning on hover. `regenerate` verdicts retry automatically
   (max 2 attempts per wood, best attempt kept; retries are capped by
   `run_cost_cap_usd` — a breach shows GT-003 on the run record).
   Review the batch and Approve/Reject each variant — every click is scored
   against the pipeline's verdict in the **reliability ledger**
   (`output/.qa/reliability.jsonl`; sidebar panel shows agreement/deferral).
3. **Stage C — bulk (35–50).** When the ledger convinces you, edit
   `backend/qa/trust_config.json`: set `"bulk_unlocked": true` (global) or
   add style-classes to `"bulk_unlocked_style_classes"` (e.g.
   `["frame_standard"]`). Applies to the next generate — no restart. Revoke
   the same way, any time. In-flight runs keep the config they started with.

Cost consent: every Generate first shows "Stage X — N images ≈ $Y (worst
case $Z with auto-retries)". The worst case includes the full unconsented
retry cap, so the dialog never under-quotes.

Files that matter: approvals in `output/.qa/approvals.json`, run records in
`output/.projects/<id>/runs/`, knobs in `backend/qa/trust_config.json`
(parse errors fall back to bulk-locked, $10 cap). A run cut short by a crash
shows a truncation banner — never a silent "done".

## Deeper reading

- Spec: `docs/superpowers/specs/2026-07-02-judgment-pipeline-design.md`
- Build plan: `docs/superpowers/plans/2026-07-02-judgment-pipeline.md`
- Geometry module RFC + evidence: `.plans/geometry-checks/` (RFC v2,
  `phase0-mechanisms.md`, `phase2-spike.md`, `phase4-calibration.md`)
- Graduated-trust pipeline RFC + plan: `.plans/graduated-trust-pipeline/`
