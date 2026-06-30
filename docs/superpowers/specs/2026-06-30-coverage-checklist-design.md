# Best-Seller Coverage Checklist — Design

**Date:** 2026-06-30
**Status:** Approved (brainstorming) → ready for implementation plan

## Goal

A new UI view that shows, for each best-selling product, whether the user has
**already generated images for it** — "almost like a checklist." It doubles as a
prioritization list (what's worth generating next) by surfacing each product's
sales figures alongside its coverage status.

## Decisions (from brainstorming)

- **Match logic:** auto-match by name (no manual linking/tagging).
- **Granularity:** four tabs, one per source category — Wood Cabinet Doors,
  Wood Drawer Fronts, Thermofoil Cabinet Doors, Thermofoil Drawer Fronts. Each
  CSV row is its own checklist item within its tab.
- **"Done" criterion:** a product is covered only when a name-matched project of
  the right material + form has **≥1 generated result**.
- **Sales figures:** shown per row; default sort by net sales (descending).
- **Filter:** a "show only not-yet-generated" toggle.

## Architecture

A backend coverage module + endpoint, consumed by a new frontend view. No
changes to generation, signatures, or project storage.

```
docs/sales/data/*.csv  ─┐
                        ├─►  backend/coverage.py  ──►  GET /api/coverage  ──►  CoveragePage (4 sub-tabs)
ProjectStore (projects) ┘
```

### Backend

- **`backend/coverage.py`** — owns CSV loading, style-token extraction, and the
  match/coverage computation. Pure functions where possible so the matching is
  unit-testable.
- **`backend/routers/coverage.py`** — `GET /api/coverage`, mounted under `/api`
  like the other routers. Reads the `ProjectStore` from `request.app.state`.
- CSVs are read from `docs/sales/data/` at the existing relative-path convention
  (the backend already reads `swatches/` relatively from the project root).

### Category configuration

| key | label | material | product_type | csv |
|-----|-------|----------|--------------|-----|
| `wood_cabinet_doors` | Wood Cabinet Doors | `wood` | `Cabinet Door` | `wood_cabinet_doors.csv` |
| `wood_drawer_fronts` | Wood Drawer Fronts | `wood` | `Drawer Front` | `wood_drawer_fronts.csv` |
| `thermofoil_cabinet_doors` | Thermofoil Cabinet Doors | `rtf` | `Cabinet Door` | `thermofoil_cabinet_doors.csv` |
| `thermofoil_drawer_fronts` | Thermofoil Drawer Fronts | `rtf` | `Drawer Front` | `thermofoil_drawer_fronts.csv` |

### API contract

`GET /api/coverage` →

```json
{
  "categories": [
    {
      "key": "wood_cabinet_doors",
      "label": "Wood Cabinet Doors",
      "covered": 12,
      "total": 79,
      "products": [
        {
          "title": "Shaker Cabinet Door",
          "net_sales": 234515.15,
          "quantity": 3997,
          "covered": true,
          "matched_project_ids": ["a1b2c3d4"]
        }
      ]
    }
  ]
}
```

Products are returned in CSV order (already sales-descending). Pydantic models:
`CoverageProduct`, `CoverageCategory`, `CoverageResponse`.

## Matching algorithm

For a given category, candidate projects are those with
`material_type == material` and `product_type == product_type`.

**Token extraction** from a product title produces a set of lowercase match
tokens:

1. Strip the trailing `Cabinet Door` / `Drawer Front` (and the `Thermofoil`
   word) from the title.
2. Strip size prefixes like `3/4"`, `7/8"`.
3. Capture any parenthetical style word(s) — e.g. `(Plank Style)` → `plank`,
   `(Shaker Style)` → `shaker`.
4. Wood titles → the remaining style word(s) become tokens
   (`Shaker` → `shaker`, `Tacoma` + `plank`).
5. Thermofoil titles → the leading **SKU** token (`AR756`, `DRS131`) **plus**
   any parenthetical style word.

**Coverage test:** a product is `covered` when at least one of its tokens
matches — whole-word, case-insensitive — against a candidate project's
**`name`** or its **`door_style`** key, **and** that project has
`len(results) >= 1`. `matched_project_ids` lists the projects that matched (any
result count); `covered` additionally requires results.

> Distinction: a project can match a product by name but contribute to
> `matched_project_ids` without making it `covered` if it has no results. The
> row is checked only when a *matched project with results* exists.

**Known limitation:** projects named after raw filenames (e.g. `door1.jpg`)
won't auto-match. This is the accepted cost of name-based matching (the chosen
approach); no manual override in this iteration.

## Frontend

- **`CoveragePage.tsx`** — orchestrator. Fetches `/api/coverage` once, holds the
  active sub-tab and the "only uncovered" toggle, renders the 4 sub-tabs.
- **`CoverageTable.tsx`** — renders one category: header summary
  (`12 / 79 generated` + a `.progress-bar`), then the product rows. Each row:
  a ✓/○ status indicator, the product title, net-sales and units columns, and —
  for covered rows — a link that opens the matched project (dispatch
  `OPEN_TAB` with the first `matched_project_ids` entry, switch to project view).
- Entry point: a **"Coverage"** button added to `TabBar` next to "Library";
  `Layout` gains a third `activeView` value (`'library' | 'project' | 'coverage'`).
- Reuses existing CSS (`status-*`, `.progress-bar`, tab/toggle classes).
- API client: `getCoverage()` in `api.ts` returning a typed `CoverageResponse`;
  types added to `types.ts`.

### Default behavior

- Sort: net sales descending (CSV order, no client re-sort needed).
- "Show only not-yet-generated" toggle filters to `covered === false`.
- Opening a covered row's link navigates to the matched project tab.

## Testing

- **Backend `tests/test_coverage.py`:**
  - token extraction: plain wood name, size-prefixed (`3/4" Heritage`),
    parenthetical (`Tacoma … (Plank Style)`), thermofoil SKU + parenthetical
    (`DRS131 … (Shaker Style)`), bare thermofoil SKU (`AR756 …`).
  - coverage: a matched project with results → covered; matched project with no
    results → not covered but listed in `matched_project_ids`; wrong
    material/form project → not matched; filename-only project → not matched.
  - category counts (`covered` / `total`) correct against synthetic projects.
- **Frontend:** build/typecheck (`tsc -b && vite build`); manual smoke of the
  4 tabs, the toggle, and the open-project link.

## Out of scope (this iteration)

- Manual linking / tagging or override of matches.
- Editing the product lists from the UI (the CSVs are the source of truth).
- Per-style sub-checks across materials (the four-tab split replaces that).
- Margin/date/region weighting — coverage uses net sales + units only.

## Deliverables

1. `backend/coverage.py` + `backend/routers/coverage.py` + models, mounted route.
2. `tests/test_coverage.py`.
3. `CoveragePage.tsx` + `CoverageTable.tsx`, `TabBar`/`Layout` wiring, `api.ts`
   + `types.ts` additions.
4. App shows a Coverage view with 4 tabs, accurate checked/unchecked status,
   sales figures, and an uncovered-only filter.
