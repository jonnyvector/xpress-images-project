# Coverage: Approval & Shopify Status — Design

**Date:** 2026-07-13
**Status:** Approved (brainstorming) → ready for implementation plan

## Goal

The existing Coverage page (`docs/superpowers/specs/2026-06-30-coverage-checklist-design.md`)
shows, per best-seller product, whether images have been **generated**. It does
not show whether those images have been **approved by the operator** (every
variant reviewed and signed off) or **uploaded to Shopify** (every variant has
a product image set in the store). This design extends the same page with
those two additional statuses so the operator can see, at a glance, what's
generated-but-unapproved, approved-but-not-live, and fully shipped.

## Decisions (from brainstorming)

- **Scope:** extends the existing Coverage page — same rows, same categories,
  no new page.
- **Approval criterion:** a covered product's primary matched project counts
  as approved when every one of its generated results (one per selected wood
  variant) has an `approved` verdict on record for its current `image_id`.
  Shown as a progress count (`3/5 approved`), not just binary.
- **Shopify criterion:** the operator periodically exports a trimmed
  Matrixify-style product CSV from Shopify (Handle, Title, Variant SKU,
  Variant Image — one row per variant) and uploads it through the UI. A
  product is "on Shopify" when every variant row for its matched Shopify
  product has an image set.
- **Shopify matching:** reuse the *same* title-based fuzzy match already used
  to join sales-CSV products to projects (`extract_match_tokens` /
  `project_matches` in `backend/coverage.py`) — match the Shopify row's
  `Title` against the sales-CSV product `title` by token overlap. One
  matching system, no new mapping table.
- **Ingestion:** upload button in the UI (multipart), not a file dropped on
  disk by hand. Each upload overwrites the previous file — this is a single
  reference snapshot, not versioned history.
- **Display:** two new badges per row (approval progress, Shopify yes/no/—)
  plus header summary counts (e.g. `12/45 approved`, `8/45 on Shopify`)
  alongside the existing generated-count progress bar. No new filter controls
  in this iteration.

## Architecture

```
docs/sales/data/*.csv         ─┐
docs/sales/data/               │
  shopify_products.csv (new) ──┼─►  backend/coverage.py  ──►  GET /api/coverage  ──►  CoverageTable (+ badges)
ProjectStore (projects)        │        ▲
output/.qa/approvals.json ─────┘        │
                                 POST /api/coverage/shopify-csv (new, upload)
```

- **`backend/shopify_products.py`** (new, sibling to `coverage.py`) — owns
  parsing the Matrixify-style CSV: groups rows by `Handle`, returns per-product
  `{title, imaged_count, total_count, fully_imaged}`. Pure functions, same
  style as `coverage.py`'s CSV loader.
- **`backend/coverage.py`** — `compute_coverage()` gains two joins per
  product, computed alongside the existing project match:
  1. **Approval progress** — from the primary matched project (first
     results-bearing entry in `matched_project_ids`, same one the row already
     links to): for each `ResultRecord` in `project.results`, look up
     `ApprovalStore.get(record.image_id)`; count `verdict == "approved"`.
  2. **Shopify status** — token-match the product `title` against the parsed
     Shopify products; `on_shopify = True` if a match has `fully_imaged`,
     `False` if a match exists but isn't fully imaged, `None` if no Shopify
     data has ever been uploaded or no product matched.
- **`backend/routers/coverage.py`** — adds `POST /coverage/shopify-csv`
  (`UploadFile`, following the existing multipart pattern in
  `projects_media.py`'s `upload_file`). Validates a non-empty file with a
  recognizable header (`Handle`/`Title`/`Variant Image` columns), writes it to
  `docs/sales/data/shopify_products.csv`, returns the refreshed
  `CoverageResponse`. On validation failure, returns 400 and leaves any
  existing file untouched.
- CSVs continue to be read fresh on every `GET /coverage` request — no
  background job, no caching, matching the existing sales-CSV convention.

### API contract additions

`CoverageProduct` gains three fields:

```json
{
  "title": "Shaker Cabinet Door",
  "net_sales": 234515.15,
  "quantity": 3997,
  "covered": true,
  "manual": false,
  "matched_project_ids": ["a1b2c3d4"],
  "approved_count": 3,
  "approved_total": 5,
  "on_shopify": true
}
```

- `approved_total == 0` means the product isn't covered yet (no results) —
  the frontend renders `—` for the approval badge in that case rather than a
  misleading `0/0`.
- `on_shopify: null` means no Shopify CSV has been uploaded yet, or nothing
  matched — rendered as a neutral `—`, never a false "No".

Pydantic models updated: `CoverageProduct` (`backend/models.py`). New request
handling only — no changes to `CoverageCategory` or `CoverageResponse`.

## Matching algorithm (Shopify)

1. Group Shopify CSV rows by `Handle`. For each group, `title` = the `Title`
   value from the first row that has one (Shopify repeats blank `Title` on
   variant continuation rows); `total_count` = row count; `imaged_count` =
   rows with a non-empty value in the image column. Image column detection:
   use `Variant Image` if that header is present in the CSV, otherwise fall
   back to `Image Src`. `fully_imaged = imaged_count == total_count and
   total_count > 0`.
2. For each sales-CSV product, reuse `extract_match_tokens(title)` (already
   computed for project matching) and test it against each Shopify product's
   `title` the same way `project_matches` tests against a project name — any
   token appearing as a whole word in the Shopify title counts as a match.
3. If multiple Shopify products match, prefer a `fully_imaged` one if any
   match is fully imaged (optimistic: the operator export is the source of
   truth per-product, ambiguity here just means the title match was coarse).
4. No manual override file for Shopify matching in this iteration (mirrors
   the "no manual override" limitation already accepted for project matching
   in the original coverage design) — a mismatch is visible as a wrong badge
   and can be corrected by tightening titles upstream if it becomes a
   recurring problem.

## Frontend

- **`CoverageTable.tsx`** — each row gains two cells:
  - **Approved**: `${approved_count}/${approved_total} approved`, styled
    green when `approved_count === approved_total && approved_total > 0`,
    neutral gray with `—` when `approved_total === 0`.
  - **On Shopify**: `✓` (green) when `true`, `✗` (muted) when `false`, `—`
    when `null`.
- **`CoveragePage.tsx`** — header gains summary counts (`X/Y approved`,
  `X/Y on Shopify`) computed client-side from the active category's products,
  plus an "Upload Shopify CSV" button: a hidden `<input type="file">` +
  `FormData` POST to `/api/coverage/shopify-csv` (same pattern as
  `UploadStep.tsx`'s file upload), re-fetching coverage on success and
  surfacing the 400 error message on failure.
- **`api.ts`** — `uploadShopifyCsv(file: File): Promise<CoverageResponse>`.
- **`types.ts`** — `CoverageProduct` gains `approved_count: number`,
  `approved_total: number`, `on_shopify: boolean | null`.

## Error handling

- Missing `shopify_products.csv` → `backend/shopify_products.py`'s loader
  returns `[]` (mirrors `coverage.py`'s existing `load_products` behavior for
  a missing sales CSV); every product's `on_shopify` resolves to `null`.
- Malformed/short rows in the Shopify CSV are skipped individually
  (`try/except ValueError: continue`), not treated as a fatal parse error —
  same tolerance as the sales-CSV loader.
- A product with `approved_total == 0` (not yet generated) never shows a
  misleading `0/0`; the badge is `—`.
- Upload endpoint rejects empty files and files missing all of
  `Handle`/`Title`/`Variant Image`-or-`Image Src` headers with a 400 and a
  clear message; a rejected upload does not touch the existing file on disk.

## Testing

- **`tests/test_shopify_products.py`** (new): well-formed multi-variant CSV
  groups correctly by Handle; a product missing one variant's image →
  `fully_imaged=False`; missing file → `[]`; malformed rows skipped without
  raising.
- **`tests/test_coverage.py`** (extended): `compute_coverage()` returns
  correct `approved_count`/`approved_total` given a fake `ApprovalStore` and a
  project with mixed-verdict results; a project with zero results yields
  `approved_total == 0`; `on_shopify` reflects a matched-and-fully-imaged,
  matched-but-partial, and no-Shopify-data-uploaded case.
- **Router test** for `POST /coverage/shopify-csv`: valid upload persists the
  file and a subsequent `GET /coverage` reflects it; invalid upload (empty or
  missing headers) returns 400 and leaves any existing file untouched.
- **Frontend:** build/typecheck (`tsc -b && vite build`); manual smoke —
  upload a real CSV export, confirm badges render correctly for
  approved/partial/unapproved and on/off/unknown Shopify states, confirm
  header summary counts match the visible rows.

## Out of scope (this iteration)

- Manual override/mapping file for Shopify title matching (mirrors the
  existing project-matching limitation — accepted for now).
- Filter controls for approval/Shopify status (e.g. "show only
  approved-not-shipped") — only badges + summary counts this round.
- Versioned history of Shopify CSV uploads — each upload replaces the last.
- Writing *back* to Shopify (this is read-only status display; no
  Matrixify export generation).
- Per-variant (per-wood) drill-down UI for approval/Shopify state — the badge
  is a project-level rollup only.

## Deliverables

1. `backend/shopify_products.py` (new) + extended `backend/coverage.py`.
2. `backend/routers/coverage.py`: new `POST /coverage/shopify-csv` endpoint.
3. `backend/models.py`: `CoverageProduct` gains `approved_count`,
   `approved_total`, `on_shopify`.
4. `tests/test_shopify_products.py` (new); `tests/test_coverage.py` extended;
   new router test for the upload endpoint.
5. `CoverageTable.tsx` + `CoveragePage.tsx` updated; `api.ts` + `types.ts`
   additions.
6. Coverage page shows accurate approval progress and Shopify status per
   product, with an upload control for refreshing Shopify data.
