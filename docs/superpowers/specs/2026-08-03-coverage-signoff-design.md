# Coverage: Operator Sign-Off — Design

**Date:** 2026-08-03
**Status:** Approved (brainstorming) → ready for implementation plan
**Supersedes the coverage *rule* in:** `2026-06-30-coverage-checklist-design.md`
**Builds on:** `2026-07-13-coverage-approval-shopify-status-design.md`
(implemented on the unmerged branch `feat/coverage-approval-shopify-status`)

## Problem

`compute_coverage()` decides coverage with:

```python
is_covered = manual or any(p.results for p in matched)
```

A single generated image marks a product covered. The page then reports
progress the operator does not trust, and cannot act on.

Two measurements taken against live data on 2026-08-03:

- **AP768 Thermofoil Cabinet Door** holds 45 results but only **43 distinct
  colors** — two results are duplicate re-attempts, so two palette colors are
  missing while the raw count looks complete.
- **45 of 191 products match two or more projects.** Matches include test and
  variant projects: `Adobe Cabinet Door` matches `Adobe_new_wm`, `adobe`,
  `Mitered-Adobe`, and `adobe_maple_select`. Any rollup that unions results
  across matches hides gaps behind unrelated projects.

Neither problem is fixable by a better threshold. The set of colors a door
*needs* varies by style — some styles legitimately skip colors — so there is
no computable denominator. Completeness is an operator judgment.

## Decisions (from brainstorming)

- **Both gates are manual.** "All variations generated" and "uploaded to
  Shopify" are recorded operator sign-offs. Nothing infers either one.
- **The app computes evidence, not verdicts.** It shows which palette colors
  are generated, missing, or marked not-needed, so the judgment is fast.
- **Exclusions are per product row**, not per door style. A style-level rule
  would propagate one wrong guess across many rows, and products map to styles
  only fuzzily by name token.
- **Each product designates one canonical project.** The checklist reads that
  project only — never a union across matches.
- **Two headline numbers**, not one: `variations complete: N/total` and
  `in Shopify: M/total`, where M is a subset of N.
- **Everything starts unreviewed.** No seeding from current auto-coverage; the
  existing numbers are the thing being replaced.
- **State is git-tracked** at `docs/sales/data/coverage_signoff.json`. Sign-off
  is a business record: it must survive a fresh clone and be reviewable in a
  diff.
- **The prior branch merges first.** Its approval-progress and Shopify-CSV
  signals become advisory evidence displayed in the sign-off panel; they never
  set `covered`.

## Data model

One record per sales-CSV product title (the same key
`coverage_overrides.json` already uses):

```jsonc
{
  "FS842 Thermofoil Cabinet Door": {
    "canonical_project_id": "abdf99a1",
    "excluded_colors": ["Black Oak", "Chocolate Pear"],
    "variations_complete": { "by": "jonny", "at": "2026-08-03T14:22:00Z",
                             "result_count": 43, "acknowledged_gap": false },
    "in_shopify":          { "by": "jonny", "at": "2026-08-04T09:10:00Z" }
  }
}
```

Sign-offs are stamped records, not booleans, so a claim carries when it was
made. Absent key = never signed off. Clearing a gate deletes the key rather
than storing `false`, so "never reviewed" and "reviewed and revoked" are not
confused — a revoked gate is simply re-openable work.

`result_count` is the canonical project's distinct-color count at the moment
of sign-off. It is what makes staleness detectable.

## Modules

**`backend/signoff.py`** (new) — owns the record and nothing else. No
knowledge of CSVs, projects, or Shopify.

```python
load_signoff(data_dir: Path) -> dict[str, ProductSignoff]
save_signoff(data_dir: Path, record: dict[str, ProductSignoff]) -> None
is_stale(signoff: ProductSignoff, distinct_colors: int) -> bool
```

Writes are atomic (temp file + `os.replace`), matching `ProjectStore`'s
discipline. A missing or malformed file loads as `{}`, mirroring
`load_overrides`.

**`backend/coverage.py`** — keeps its role as the matcher. It gains one job:
attach sign-off state and the computed palette gap to each product dict.
`compute_coverage()` stays pure with the record injected, so matching tests
stay disk-free.

A separate file rather than an extension because the two have different
lifetimes: coverage is derived and recomputed from CSVs on every request;
sign-off is durable operator input that a recompute must never overwrite.

### Computed gap (advisory)

For a product with a canonical project:

```
expected  = full palette for the material − excluded_colors
generated = distinct wood_names present in the canonical project's results
gap       = expected − generated
```

"Full palette" is every entry in `wood_types.json` for that material — 44 wood,
45 RTF — including the six wood entries that are description-only with no
swatch file, since those still generate. It is a starting set for the operator
to subtract from via `excluded_colors`, never a completion target in itself.

`generated` counts *distinct* names, not `len(project.results)`: re-attempts
replace a slot but duplicates exist in the data (AP768: 45 results, 43 colors).
Failed generations live in `project.errors`, not `project.results`, so every
result record already represents a success — no verdict filtering is applied
here. Judge verdicts and approvals are shown as separate advisory badges and
deliberately do not shrink `generated`; whether a mediocre image counts is the
operator's call at sign-off.

Rendered as `41/43 — missing: Bisque, Niagara`. It never sets `covered`.

### Coverage rule

`covered` is replaced by two independent booleans derived only from the
record: `variations_complete` present, and `in_shopify` present. The existing
`manual` override list is migrated (below) and the field retired.

## API

Three endpoints on the existing coverage router. Title is URL-encoded.

```
PUT  /coverage/{title}/canonical    { "project_id": "abdf99a1" }
PUT  /coverage/{title}/exclusions   { "colors": ["Black Oak"] }
POST /coverage/{title}/signoff      { "gate": "variations"|"shopify",
                                      "value": true,
                                      "acknowledge_gap": false }
```

`PUT` for idempotent state, `POST` for the stamped human act. All three return
the refreshed `CoverageResponse` so the page updates in one round trip.

**Gap guard:** signing off `variations` while `gap` is non-empty returns `409`
listing the missing colors, unless `acknowledge_gap: true` — which is then
persisted on the record. The operator can always override; not by accident,
and never silently.

`404` for a title absent from every sales CSV; `422` for an unknown
`project_id` or a `gate` outside the two values.

## Frontend

`CoverageTable.tsx` stays presentational. Expanding a row reveals a new
`ProductSignoffPanel.tsx`:

- **Canonical project picker** — defaults to the matched project with the most
  distinct colors, preferring a `*_new_wm` name; shows each candidate's
  distinct-color count so test projects are obvious.
- **Palette grid** — every color for the material as generated / missing /
  excluded. Click toggles excluded.
- **Two sign-off checkboxes** with who and when, plus the advisory approval
  and Shopify badges from the merged branch.
- **Staleness banner** when the canonical project's distinct-color count no
  longer matches `result_count`, with a one-click re-affirm.

Category header shows both counters. Existing `onlyUncovered` filter switches
to filtering on `variations_complete`.

`types.ts` and `api.ts` gain the record shape and the three calls.

## Error handling

- Missing or malformed `coverage_signoff.json` → `{}`; every product reads
  unreviewed. Never a crash, never a false green.
- A `canonical_project_id` pointing at a deleted project → the panel shows
  "canonical project missing, pick another"; sign-off state is retained, and
  the row is flagged stale rather than silently reverting to unreviewed.
- A product with no matched project can still be signed off — work done
  entirely outside the app is exactly what the current override list is for.
  The panel shows no palette grid in that case.
- Concurrent writes: the record is small and rewritten whole under an atomic
  replace. Reads happen per request; last write wins. This is a single-operator
  tool, consistent with the existing single-writer constraint on `ProjectStore`.

## Testing

**`tests/test_signoff.py`** (new): round-trip load/save; missing file → `{}`;
malformed JSON → `{}`; atomic write leaves no partial file on failure;
staleness true when the count moved and false when it did not; clearing a gate
removes the key.

**`tests/test_coverage.py`** (extended): sign-off drives the two booleans and
`any(p.results)` no longer does; excluded colors shrink the expected set; the
gap reads from the canonical project only, not the union of matches (regression
test built on the real `Adobe Cabinet Door` four-way match); a duplicate-attempt
project reports distinct colors, not raw result count (the AP768 case).

**Router tests:** each endpoint's happy path; `409` on signing off with a
non-empty gap; `acknowledge_gap: true` persists and succeeds; `404` unknown
title; `422` unknown project.

**Frontend:** `tsc -b && vite build`, plus a manual pass signing off one real
product end to end.

## Migration

The 5 titles in `coverage_overrides.json` become records with both gates
stamped `by: "migrated"` and no `canonical_project_id` — they were claims that
the work was done outside the app, so both gates are already true. A one-shot
script writes them into the new file. `coverage_overrides.json` then becomes
read-only legacy, and `load_overrides` is deleted once the migration lands.

Every other product starts unreviewed.

## Accepted costs

- **A review backlog of roughly 105 products.** The panel makes each row fast,
  but this is an afternoon of work, not a minute. It is the deliberate price of
  not carrying forward numbers that were never verified.
- **Test and variant projects keep appearing** in the canonical picker
  (`arcadia-no-ar-test`, `Arcadia-Test`, `adobe_maple_select`). Choosing a
  canonical neutralizes them per row; cleaning them up is out of scope.
- **Shopify status stays a manual tick.** The merged branch's CSV badge is
  advisory only, and goes stale unless exports are refreshed. No API
  integration.

## Out of scope

- Writing to Shopify, or any Shopify API integration.
- Per-style reusable exclusion rules, and an "apply to similar rows" action.
- Multi-operator attribution beyond a name string; no auth.
- Reworking the fuzzy title matcher itself.
- Cleaning up stale test projects.

## Deliverables

1. Merge `feat/coverage-approval-shopify-status` (advisory signals).
2. `backend/signoff.py` (new) + `backend/coverage.py` extended to attach
   sign-off state and the computed gap.
3. Three endpoints on `backend/routers/coverage.py`; `backend/models.py`
   updated.
4. `ProductSignoffPanel.tsx` (new); `CoverageTable.tsx`, `CoveragePage.tsx`,
   `api.ts`, `types.ts` updated.
5. `tests/test_signoff.py` (new); `tests/test_coverage.py` and router tests
   extended.
6. Migration script for the 5 override titles; `load_overrides` removed.
