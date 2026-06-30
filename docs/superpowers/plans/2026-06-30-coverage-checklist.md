# Best-Seller Coverage Checklist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Coverage" view that shows, per best-seller category, which products already have generated images — auto-matched by name, checked only when a matched project has ≥1 result.

**Architecture:** A backend `coverage` module (pure CSV-load + token-extraction + match functions) behind a `GET /api/coverage` endpoint that joins the four sales CSVs with the `ProjectStore`. A new frontend "Coverage" top-level view with 4 sub-tabs renders the response.

**Tech Stack:** FastAPI + Pydantic (backend), Python 3.12 / `uv` / `pytest` / `ruff`, React 19 + TypeScript + Vite (frontend).

**Spec:** `docs/superpowers/specs/2026-06-30-coverage-checklist-design.md`

## Global Constraints

- Backend reads CSVs from `docs/sales/data/` using project-root-relative paths (same convention as `swatches/`).
- Matching is **auto by name** only — no manual linking this iteration.
- A product is **covered** only when a name-matched project of the right `material_type` + `product_type` has `len(results) >= 1`.
- Behavior-preserving for everything else: no changes to generation, signatures, or `ProjectStore` persistence.
- Backend must keep `ruff check backend/` clean and all `pytest` green.
- Frontend must keep `tsc -b && vite build` clean.
- Commit after each task.

## File Structure

- Create `backend/coverage.py` — category config, CSV loading, token extraction, match logic, `compute_coverage`.
- Modify `backend/models.py` — add `CoverageProduct`, `CoverageCategory`, `CoverageResponse`.
- Create `backend/routers/coverage.py` — `GET /api/coverage`.
- Modify `backend/app.py` — mount the coverage router.
- Create `tests/test_coverage.py` — token extraction + coverage logic.
- Modify `frontend/src/types.ts` — coverage types.
- Modify `frontend/src/api.ts` — `getCoverage()`.
- Create `frontend/src/components/CoverageTable.tsx` — one category's rows.
- Create `frontend/src/components/CoveragePage.tsx` — fetch + 4 sub-tabs + filter.
- Modify `frontend/src/components/TabBar.tsx` — "Coverage" button + view type.
- Modify `frontend/src/components/Layout.tsx` — third view, render `CoveragePage`.

---

## Task 1: Coverage token extraction (backend, pure function)

**Files:**
- Create: `backend/coverage.py`
- Test: `tests/test_coverage.py`

**Interfaces:**
- Produces: `extract_match_tokens(title: str) -> set[str]` — lowercase match tokens for a product title (material-agnostic).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_coverage.py
from backend.coverage import extract_match_tokens


def test_extract_tokens_plain_wood_name():
    assert extract_match_tokens("Shaker Cabinet Door") == {"shaker"}


def test_extract_tokens_strips_size_prefix():
    assert extract_match_tokens('3/4" Heritage Cabinet Door') == {"heritage"}


def test_extract_tokens_includes_parenthetical_style():
    assert extract_match_tokens("Tacoma Cabinet Door (Plank Style)") == {"tacoma", "plank"}


def test_extract_tokens_thermofoil_sku_only():
    assert extract_match_tokens("AR756 Thermofoil Cabinet Door") == {"ar756"}


def test_extract_tokens_thermofoil_sku_plus_parenthetical():
    assert extract_match_tokens(
        "DRS131 Thermofoil Cabinet Door (Shaker Style)"
    ) == {"drs131", "shaker"}


def test_extract_tokens_drops_pure_digits_and_generic_words():
    # "Drawer Front", "Style", and bare size digits must not become tokens
    assert extract_match_tokens("Revere Drawer Front") == {"revere"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.coverage'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/coverage.py
"""Best-seller coverage: join the sales CSVs with generated projects.

Owns the CSV product lists, the fuzzy style/SKU token extraction, and the
name-based match logic that decides whether a project covers a product. Pure
functions are kept side-effect-free so the matching is unit-testable.
"""

from __future__ import annotations

import re

# Words that carry no style meaning and must never become match tokens.
_GENERIC_WORDS = {
    "thermofoil",
    "cabinet",
    "door",
    "drawer",
    "front",
    "style",
    "dbq",
}


def _words(text: str) -> list[str]:
    """Split into lowercase alphanumeric words."""
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def extract_match_tokens(title: str) -> set[str]:
    """Extract lowercase match tokens (style words and/or SKUs) from a title."""
    parentheticals = re.findall(r"\(([^)]*)\)", title)
    base = re.sub(r"\([^)]*\)", " ", title)
    base = re.sub(r'\d+/\d+"?', " ", base)  # strip size fractions like 3/4"

    candidates = _words(base)
    for chunk in parentheticals:
        candidates.extend(_words(chunk))

    tokens: set[str] = set()
    for word in candidates:
        if word in _GENERIC_WORDS:
            continue
        if word.isdigit():
            continue
        if len(word) < 2:
            continue
        tokens.add(word)
    return tokens
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_coverage.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/coverage.py tests/test_coverage.py
git commit -m "feat(coverage): style/SKU token extraction from product titles"
```

---

## Task 2: Project-match + coverage computation (backend, pure functions)

**Files:**
- Modify: `backend/coverage.py`
- Test: `tests/test_coverage.py`

**Interfaces:**
- Consumes: `extract_match_tokens(title)` from Task 1; `ProjectState` from `backend.state`.
- Produces:
  - `CATEGORIES: list[dict]` — each `{key, label, material, product_type, csv}`.
  - `load_products(csv_path: Path) -> list[tuple[str, float, int]]` — `(title, net_sales, quantity)` rows; `[]` if the file is missing.
  - `project_matches(project: ProjectState, tokens: set[str]) -> bool` — whole-word match against `name` or `door_style`.
  - `compute_coverage(projects: list[ProjectState], data_dir: Path = DATA_DIR) -> list[dict]` — per-category dicts `{key, label, covered, total, products}` where each product is `{title, net_sales, quantity, covered, matched_project_ids}`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_coverage.py
from pathlib import Path

from backend.coverage import (
    CATEGORIES,
    compute_coverage,
    load_products,
    project_matches,
)
from backend.state import ProjectState


def _project(**kw) -> ProjectState:
    base = dict(id="p1", name="x", product_type="Cabinet Door", material_type="wood")
    base.update(kw)
    return ProjectState(**base)


def test_categories_cover_all_four_lists():
    keys = {c["key"] for c in CATEGORIES}
    assert keys == {
        "wood_cabinet_doors",
        "wood_drawer_fronts",
        "thermofoil_cabinet_doors",
        "thermofoil_drawer_fronts",
    }


def test_load_products_missing_file_returns_empty(tmp_path: Path):
    assert load_products(tmp_path / "nope.csv") == []


def test_project_matches_on_name_word():
    assert project_matches(_project(name="My Shaker upload"), {"shaker"}) is True
    assert project_matches(_project(name="door1.jpg"), {"shaker"}) is False


def test_project_matches_on_door_style_key():
    assert project_matches(_project(name="door1", door_style="solid_plank"), {"plank"}) is True


def test_compute_coverage_marks_covered_only_with_results(tmp_path: Path):
    csv = tmp_path / "wood_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
        '"Revere Cabinet Door",50.0,2\n'
    )
    # Shaker project WITH a result -> covered; Revere project WITHOUT results -> matched-not-covered
    shaker = _project(id="s1", name="Shaker", results=[("Maple", b"img")])
    revere = _project(id="r1", name="Revere", results=[])
    cats = compute_coverage([shaker, revere], data_dir=tmp_path)
    wood_cd = next(c for c in cats if c["key"] == "wood_cabinet_doors")

    assert wood_cd["total"] == 2
    assert wood_cd["covered"] == 1
    shaker_row = next(p for p in wood_cd["products"] if p["title"] == "Shaker Cabinet Door")
    revere_row = next(p for p in wood_cd["products"] if p["title"] == "Revere Cabinet Door")
    assert shaker_row["covered"] is True
    assert shaker_row["matched_project_ids"] == ["s1"]
    assert revere_row["covered"] is False
    assert revere_row["matched_project_ids"] == ["r1"]


def test_compute_coverage_filters_by_material_and_form(tmp_path: Path):
    csv = tmp_path / "thermofoil_cabinet_doors.csv"
    csv.write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"DRS131 Thermofoil Cabinet Door (Shaker Style)",10.0,1\n'
    )
    # A wood project named "Shaker" must NOT cover an rtf product.
    wood_shaker = _project(id="w1", name="Shaker", material_type="wood", results=[("M", b"x")])
    cats = compute_coverage([wood_shaker], data_dir=tmp_path)
    tf_cd = next(c for c in cats if c["key"] == "thermofoil_cabinet_doors")
    assert tf_cd["covered"] == 0
    assert tf_cd["products"][0]["matched_project_ids"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage.py -q`
Expected: FAIL with `ImportError: cannot import name 'CATEGORIES'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/coverage.py`:

```python
import csv
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.state import ProjectState

DATA_DIR = Path("docs/sales/data")

CATEGORIES: list[dict] = [
    {
        "key": "wood_cabinet_doors",
        "label": "Wood Cabinet Doors",
        "material": "wood",
        "product_type": "Cabinet Door",
        "csv": "wood_cabinet_doors.csv",
    },
    {
        "key": "wood_drawer_fronts",
        "label": "Wood Drawer Fronts",
        "material": "wood",
        "product_type": "Drawer Front",
        "csv": "wood_drawer_fronts.csv",
    },
    {
        "key": "thermofoil_cabinet_doors",
        "label": "Thermofoil Cabinet Doors",
        "material": "rtf",
        "product_type": "Cabinet Door",
        "csv": "thermofoil_cabinet_doors.csv",
    },
    {
        "key": "thermofoil_drawer_fronts",
        "label": "Thermofoil Drawer Fronts",
        "material": "rtf",
        "product_type": "Drawer Front",
        "csv": "thermofoil_drawer_fronts.csv",
    },
]


def load_products(csv_path: Path) -> list[tuple[str, float, int]]:
    """Read (title, net_sales, quantity) rows from a sales CSV; [] if missing."""
    if not csv_path.exists():
        return []
    rows: list[tuple[str, float, int]] = []
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # header
        for row in reader:
            if len(row) < 3:
                continue
            try:
                rows.append((row[0], float(row[1]), int(row[2])))
            except ValueError:
                continue
    return rows


def project_matches(project: "ProjectState", tokens: set[str]) -> bool:
    """True if any token is a whole word in the project's name or door_style."""
    haystack = set(_words(project.name))
    if project.door_style:
        haystack |= set(_words(project.door_style))
    return bool(tokens & haystack)


def compute_coverage(
    projects: list["ProjectState"], data_dir: Path = DATA_DIR
) -> list[dict]:
    """Build per-category coverage data joining the CSVs with projects."""
    categories: list[dict] = []
    for cat in CATEGORIES:
        candidates = [
            p
            for p in projects
            if p.material_type == cat["material"]
            and p.product_type == cat["product_type"]
        ]
        products: list[dict] = []
        covered_count = 0
        for title, net_sales, quantity in load_products(data_dir / cat["csv"]):
            tokens = extract_match_tokens(title)
            matched = [p for p in candidates if project_matches(p, tokens)]
            is_covered = any(p.results for p in matched)
            if is_covered:
                covered_count += 1
            products.append(
                {
                    "title": title,
                    "net_sales": net_sales,
                    "quantity": quantity,
                    "covered": is_covered,
                    "matched_project_ids": [p.id for p in matched],
                }
            )
        categories.append(
            {
                "key": cat["key"],
                "label": cat["label"],
                "covered": covered_count,
                "total": len(products),
                "products": products,
            }
        )
    return categories
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coverage.py -q && npm run lint`
Expected: PASS (all tests), `ruff` "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add backend/coverage.py tests/test_coverage.py
git commit -m "feat(coverage): category config + project match + compute_coverage"
```

---

## Task 3: Coverage models + endpoint + mount

**Files:**
- Modify: `backend/models.py`
- Create: `backend/routers/coverage.py`
- Modify: `backend/app.py:10` (import) and `backend/app.py:35-36` (mount)
- Test: `tests/test_coverage.py`

**Interfaces:**
- Consumes: `compute_coverage(...)` from Task 2; `get_store(request)` from `backend.routers.projects_common`.
- Produces: `GET /api/coverage` returning `CoverageResponse` (`{categories: [...]}`).

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_coverage.py
from fastapi.testclient import TestClient

from backend.app import app


def test_coverage_endpoint_returns_four_categories():
    with TestClient(app) as client:
        resp = client.get("/api/coverage")
    assert resp.status_code == 200
    data = resp.json()
    keys = {c["key"] for c in data["categories"]}
    assert keys == {
        "wood_cabinet_doors",
        "wood_drawer_fronts",
        "thermofoil_cabinet_doors",
        "thermofoil_drawer_fronts",
    }
    wood_cd = next(c for c in data["categories"] if c["key"] == "wood_cabinet_doors")
    assert wood_cd["total"] >= 1
    assert "covered" in wood_cd
    assert {"title", "net_sales", "quantity", "covered", "matched_project_ids"} <= set(
        wood_cd["products"][0].keys()
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_coverage.py::test_coverage_endpoint_returns_four_categories -q`
Expected: FAIL with 404 (route not mounted)

- [ ] **Step 3a: Add models to `backend/models.py`**

Append at end of `backend/models.py`:

```python
class CoverageProduct(BaseModel):
    title: str
    net_sales: float
    quantity: int
    covered: bool
    matched_project_ids: list[str]


class CoverageCategory(BaseModel):
    key: str
    label: str
    covered: int
    total: int
    products: list[CoverageProduct]


class CoverageResponse(BaseModel):
    categories: list[CoverageCategory]
```

- [ ] **Step 3b: Create `backend/routers/coverage.py`**

```python
"""Best-seller coverage endpoint."""

from fastapi import APIRouter, Request

from backend.coverage import compute_coverage
from backend.models import CoverageCategory, CoverageResponse
from backend.routers.projects_common import get_store

router = APIRouter()


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    store = get_store(request)
    categories = compute_coverage(store.list_projects())
    return CoverageResponse(
        categories=[CoverageCategory(**c) for c in categories]
    )
```

- [ ] **Step 3c: Mount the router in `backend/app.py`**

Change the import on line 10 from:

```python
from backend.routers import projects, swatches
```

to:

```python
from backend.routers import coverage, projects, swatches
```

And after the existing `app.include_router(projects.router, prefix="/api")` line, add:

```python
app.include_router(coverage.router, prefix="/api")
```

- [ ] **Step 4: Run tests + lint to verify they pass**

Run: `uv run pytest tests/test_coverage.py -q && npm run lint`
Expected: PASS (all coverage tests), `ruff` "All checks passed!"

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/routers/coverage.py backend/app.py tests/test_coverage.py
git commit -m "feat(coverage): add GET /api/coverage endpoint"
```

---

## Task 4: Frontend types + API client

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Produces: `CoverageProduct`, `CoverageCategory`, `CoverageResponse` types; `getCoverage(): Promise<CoverageResponse>`.

- [ ] **Step 1: Add types to `frontend/src/types.ts`**

Append at end of `frontend/src/types.ts`:

```typescript
export interface CoverageProduct {
  title: string;
  net_sales: number;
  quantity: number;
  covered: boolean;
  matched_project_ids: string[];
}

export interface CoverageCategory {
  key: string;
  label: string;
  covered: number;
  total: number;
  products: CoverageProduct[];
}

export interface CoverageResponse {
  categories: CoverageCategory[];
}
```

- [ ] **Step 2: Add the API client to `frontend/src/api.ts`**

At the top of `frontend/src/api.ts`, add `CoverageResponse` to the existing type import from `./types`:

```typescript
import type { Project, Swatch, Style, GenerationStatus, SignatureVersion, CoverageResponse } from './types';
```

Then append at the end of the file:

```typescript
// Coverage
export function getCoverage(): Promise<CoverageResponse> {
  return request<CoverageResponse>('/api/coverage');
}
```

- [ ] **Step 3: Verify the build/typecheck passes**

Run: `cd frontend && npm run build`
Expected: `✓ built` with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat(coverage): frontend coverage types + getCoverage client"
```

---

## Task 5: CoverageTable component (one category)

**Files:**
- Create: `frontend/src/components/CoverageTable.tsx`

**Interfaces:**
- Consumes: `CoverageCategory` type from Task 4.
- Produces: `CoverageTable` default export with props
  `{ category: CoverageCategory; onlyUncovered: boolean; onOpenProject: (id: string) => void }`.

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/CoverageTable.tsx
// Renders one best-seller category as a coverage checklist: a header summary
// with a progress bar, then one row per product showing covered status, sales
// figures, and a link to the matched project. Presentational only.
import type { CoverageCategory } from '../types';

interface Props {
  category: CoverageCategory;
  onlyUncovered: boolean;
  onOpenProject: (id: string) => void;
}

export default function CoverageTable({ category, onlyUncovered, onOpenProject }: Props) {
  const products = onlyUncovered
    ? category.products.filter((p) => !p.covered)
    : category.products;

  const pct = category.total > 0 ? Math.round((category.covered / category.total) * 100) : 0;

  return (
    <section>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <h3 style={{ margin: 0 }}>
          {category.covered} / {category.total} generated
        </h3>
        <div className="progress-bar" style={{ flex: 1, maxWidth: 240 }}>
          <div className="fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {products.length === 0 ? (
        <div className="status-info">
          {onlyUncovered ? 'Everything in this category has been generated.' : 'No products.'}
        </div>
      ) : (
        <table className="coverage-table">
          <thead>
            <tr>
              <th style={{ width: '2rem' }} />
              <th>Product</th>
              <th style={{ textAlign: 'right' }}>Net sales</th>
              <th style={{ textAlign: 'right' }}>Units</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.title} className={p.covered ? 'covered' : ''}>
                <td style={{ textAlign: 'center' }}>{p.covered ? '✓' : '○'}</td>
                <td>
                  {p.covered && p.matched_project_ids.length > 0 ? (
                    <button
                      className="link-button"
                      onClick={() => onOpenProject(p.matched_project_ids[0])}
                    >
                      {p.title}
                    </button>
                  ) : (
                    p.title
                  )}
                </td>
                <td style={{ textAlign: 'right' }}>
                  ${p.net_sales.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </td>
                <td style={{ textAlign: 'right' }}>{p.quantity.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Add minimal CSS to `frontend/src/index.css`**

Append at the end of `frontend/src/index.css`:

```css
/* Coverage checklist */
.coverage-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}
.coverage-table th,
.coverage-table td {
  padding: 0.4rem 0.6rem;
  border-bottom: 1px solid var(--color-border);
  text-align: left;
}
.coverage-table tr.covered {
  color: var(--color-text-muted);
}
.coverage-table .link-button {
  background: none;
  border: none;
  padding: 0;
  color: inherit;
  text-decoration: underline;
  cursor: pointer;
  font: inherit;
}
```

- [ ] **Step 3: Verify the build/typecheck passes**

Run: `cd frontend && npm run build`
Expected: `✓ built` with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CoverageTable.tsx frontend/src/index.css
git commit -m "feat(coverage): CoverageTable component + table styles"
```

---

## Task 6: CoveragePage + TabBar + Layout wiring

**Files:**
- Create: `frontend/src/components/CoveragePage.tsx`
- Modify: `frontend/src/components/TabBar.tsx`
- Modify: `frontend/src/components/Layout.tsx`

**Interfaces:**
- Consumes: `getCoverage()` from Task 4; `CoverageTable` from Task 5; `CoverageResponse` type.
- Produces: `CoveragePage` default export with props `{ onOpenProject: (id: string) => void }`.

- [ ] **Step 1: Create `frontend/src/components/CoveragePage.tsx`**

```tsx
// frontend/src/components/CoveragePage.tsx
// Top-level Coverage view: fetches /api/coverage once, holds the active
// sub-tab (one per best-seller category) and the "only uncovered" filter,
// and renders the selected category via CoverageTable.
import { useState, useEffect } from 'react';
import type { CoverageResponse } from '../types';
import * as api from '../api';
import CoverageTable from './CoverageTable';

interface Props {
  onOpenProject: (id: string) => void;
}

export default function CoveragePage({ onOpenProject }: Props) {
  const [data, setData] = useState<CoverageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [onlyUncovered, setOnlyUncovered] = useState(false);

  useEffect(() => {
    api
      .getCoverage()
      .then((resp) => {
        setData(resp);
        setActiveKey((prev) => prev ?? resp.categories[0]?.key ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load coverage'));
  }, []);

  if (error) return <div className="status-error">{error}</div>;
  if (!data) return <div className="status-info">Loading coverage…</div>;

  const active = data.categories.find((c) => c.key === activeKey) ?? data.categories[0];

  return (
    <div>
      <div className="tab-bar" style={{ marginBottom: '1rem' }}>
        {data.categories.map((c) => (
          <button
            key={c.key}
            className={`tab-item ${c.key === active?.key ? 'active' : ''}`}
            onClick={() => setActiveKey(c.key)}
          >
            {c.label} ({c.covered}/{c.total})
          </button>
        ))}
      </div>

      <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.75rem', fontSize: '0.875rem' }}>
        <input
          type="checkbox"
          checked={onlyUncovered}
          onChange={(e) => setOnlyUncovered(e.target.checked)}
        />
        Show only not-yet-generated
      </label>

      {active && (
        <CoverageTable
          category={active}
          onlyUncovered={onlyUncovered}
          onOpenProject={onOpenProject}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Update `frontend/src/components/TabBar.tsx`**

Replace the entire contents of `frontend/src/components/TabBar.tsx` with:

```tsx
import type { Project } from '../types';

interface Props {
  projects: Project[];
  activeId: string | null;
  activeView: 'library' | 'project' | 'coverage';
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onSelectLibrary: () => void;
  onSelectCoverage: () => void;
}

export default function TabBar({
  projects,
  activeId,
  activeView,
  onSelect,
  onClose,
  onSelectLibrary,
  onSelectCoverage,
}: Props) {
  return (
    <div className="tab-bar">
      <button
        className={`tab-item ${activeView === 'library' ? 'active' : ''}`}
        onClick={onSelectLibrary}
      >
        Library
      </button>
      <button
        className={`tab-item ${activeView === 'coverage' ? 'active' : ''}`}
        onClick={onSelectCoverage}
      >
        Coverage
      </button>
      {projects.map((p) => (
        <button
          key={p.id}
          className={`tab-item ${p.id === activeId && activeView === 'project' ? 'active' : ''}`}
          onClick={() => onSelect(p.id)}
        >
          {p.name}
          <span
            className="close-btn"
            onClick={(e) => {
              e.stopPropagation();
              onClose(p.id);
            }}
          >
            x
          </span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Update `frontend/src/components/Layout.tsx`**

Make three edits in `frontend/src/components/Layout.tsx`:

(a) Add the import near the other component imports (after the `DoorLibrary` import):

```tsx
import CoveragePage from './CoveragePage';
```

(b) Change the `activeView` state type (currently `useState<'library' | 'project'>('project')`) to:

```tsx
  const [activeView, setActiveView] = useState<'library' | 'project' | 'coverage'>('project');
```

(c) In the `<TabBar ... />` usage, add the `onSelectCoverage` prop next to `onSelectLibrary`:

```tsx
            onSelectLibrary={() => setActiveView('library')}
            onSelectCoverage={() => setActiveView('coverage')}
```

(d) In the content area, replace the existing view branch:

```tsx
          {activeView === 'library' ? (
```

with a coverage branch first, keeping the rest of the existing ternary intact:

```tsx
          {activeView === 'coverage' ? (
            <CoveragePage
              onOpenProject={(id) => {
                dispatch({ type: 'OPEN_TAB', id });
                setActiveView('project');
              }}
            />
          ) : activeView === 'library' ? (
```

- [ ] **Step 4: Verify the build/typecheck passes**

Run: `cd frontend && npm run build`
Expected: `✓ built` with no TypeScript errors

- [ ] **Step 5: Manual smoke test**

Run the app (`npm run dev`), open the Coverage tab, confirm: 4 sub-tabs each show `covered/total`, rows show ✓/○ + sales + units, the "only not-yet-generated" toggle filters rows, and clicking a covered product opens its project tab.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/CoveragePage.tsx frontend/src/components/TabBar.tsx frontend/src/components/Layout.tsx
git commit -m "feat(coverage): Coverage view with 4 category tabs + filter"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** architecture (Tasks 1–3 backend, 4–6 frontend), category config (Task 2), API contract (Task 3 models), matching algorithm incl. tokens + name/door_style + results-gated coverage (Tasks 1–2), 4-tab UI + summary + progress bar + sales columns + open-project link + uncovered filter (Tasks 5–6), tests (Tasks 1–3). All spec sections map to a task.
- **Known-limitation note:** filename-only projects not matching is exercised by `test_project_matches_on_name_word` (the `door1.jpg` case).
- **Type consistency:** `compute_coverage` dict keys (`title, net_sales, quantity, covered, matched_project_ids` / `key, label, covered, total, products`) match the Pydantic models in Task 3 and the TS types in Task 4. `getCoverage` return type, `CoverageTable` props, and `CoveragePage` props are consistent across Tasks 4–6. `TabBar` gains `onSelectCoverage` (Task 6 Step 2) consumed in Layout (Step 3c).
- **Placeholder scan:** no TBD/TODO; every code step shows complete code.
```
