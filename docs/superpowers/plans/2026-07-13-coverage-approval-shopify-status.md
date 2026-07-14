# Coverage: Approval & Shopify Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing best-seller Coverage page so each product row also shows operator approval progress and whether it's live on Shopify with images for every variant.

**Architecture:** A new `backend/shopify_products.py` module parses an operator-uploaded Matrixify-style Shopify CSV into per-product image coverage; `backend/coverage.py`'s `compute_coverage()` joins that (via the existing title fuzzy-match) and the existing `ApprovalStore` into each `CoverageProduct` row; a new upload endpoint persists the CSV; the frontend renders two new badges and an upload button.

**Tech Stack:** FastAPI + Pydantic (backend), React 19 + TypeScript + Vite (frontend), pytest, stdlib `csv`.

## Global Constraints

- Design source of truth: `docs/superpowers/specs/2026-07-13-coverage-approval-shopify-status-design.md`.
- Extends the existing Coverage page — no new page, no new routes beyond one upload endpoint.
- Shopify CSV → product matching reuses the existing sales-CSV title fuzzy-match (`extract_match_tokens` / whole-word token overlap) — no new mapping table, no manual override file for Shopify this iteration.
- Each CSV upload overwrites `docs/sales/data/shopify_products.csv` in place — no versioning.
- `approved_total == 0` (not yet generated) renders as `—`, never `0/0`. `on_shopify == null` (no data uploaded, or no title match) renders as `—`, never a false "No".
- CSV parsing must tolerate missing files and malformed/short rows without raising — matches the existing `backend/coverage.py` loader convention.
- No new filter controls this iteration — badges + header summary counts only.
- Backend tests are pytest, run via `uv run pytest`. Frontend has no test framework — verify via `npm run build` (runs `tsc -b && vite build`) plus manual smoke.

---

### Task 1: Shopify CSV parsing module

**Files:**
- Create: `backend/shopify_products.py`
- Test: `tests/test_shopify_products.py`

**Interfaces:**
- Produces: `SHOPIFY_CSV_FILENAME: str` (constant, value `"shopify_products.csv"`); `has_recognizable_headers(header: list[str]) -> bool`; `load_shopify_products(csv_path: Path) -> list[dict]`, where each dict has keys `handle: str, title: str, total_count: int, imaged_count: int, fully_imaged: bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shopify_products.py`:

```python
"""Shopify product image coverage: parse a Matrixify-style variant CSV."""

from pathlib import Path

from backend.shopify_products import has_recognizable_headers, load_shopify_products


def test_missing_file_returns_empty(tmp_path: Path):
    assert load_shopify_products(tmp_path / "nope.csv") == []


def test_empty_file_returns_empty(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text("")
    assert load_shopify_products(csv_path) == []


def test_unrecognized_headers_returns_empty(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text("Foo,Bar\nx,y\n")
    assert load_shopify_products(csv_path) == []


def test_has_recognizable_headers_requires_handle_title_and_image_column():
    assert has_recognizable_headers(["Handle", "Title", "Variant Image"]) is True
    assert has_recognizable_headers(["Handle", "Title", "Image Src"]) is True
    assert has_recognizable_headers(["Handle", "Title"]) is False
    assert has_recognizable_headers(["Foo", "Bar"]) is False


def test_groups_variants_by_handle_fully_imaged(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,https://cdn/2.jpg\n"
        "shaker-cabinet-door,,SCD-CHERRY,https://cdn/3.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert len(products) == 1
    p = products[0]
    assert p["handle"] == "shaker-cabinet-door"
    assert p["title"] == "Shaker Cabinet Door"
    assert p["total_count"] == 3
    assert p["imaged_count"] == 3
    assert p["fully_imaged"] is True


def test_partially_imaged_product_is_not_fully_imaged(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
        "revere-cabinet-door,,RCD-OAK,\n"
    )
    products = load_shopify_products(csv_path)
    p = products[0]
    assert p["total_count"] == 2
    assert p["imaged_count"] == 1
    assert p["fully_imaged"] is False


def test_falls_back_to_image_src_column_when_variant_image_absent(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Image Src\n"
        "tacoma-cabinet-door,Tacoma Cabinet Door,TCD-MAPLE,https://cdn/1.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert products[0]["fully_imaged"] is True


def test_skips_rows_with_blank_handle(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        ",,,\n"
    )
    products = load_shopify_products(csv_path)
    assert len(products) == 1


def test_ragged_row_missing_trailing_columns_does_not_raise(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door\n"
    )
    products = load_shopify_products(csv_path)
    p = products[0]
    assert p["total_count"] == 2
    assert p["imaged_count"] == 1
    assert p["fully_imaged"] is False


def test_multiple_products_preserve_first_seen_order(tmp_path: Path):
    csv_path = tmp_path / "shopify_products.csv"
    csv_path.write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/2.jpg\n"
    )
    products = load_shopify_products(csv_path)
    assert [p["handle"] for p in products] == ["revere-cabinet-door", "shaker-cabinet-door"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_shopify_products.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.shopify_products'`

- [ ] **Step 3: Write the implementation**

Create `backend/shopify_products.py`:

```python
"""Shopify product image coverage: parse a Matrixify-style variant CSV.

Owns detecting, per product (grouped by Handle), whether every variant row
has an image set. Mirrors coverage.py's tolerant CSV-loading conventions so
a partial/malformed store export never blocks the coverage page from
loading.
"""

from __future__ import annotations

import csv
from pathlib import Path

SHOPIFY_CSV_FILENAME = "shopify_products.csv"

REQUIRED_HEADERS = {"Handle", "Title"}
IMAGE_HEADER_CANDIDATES = ("Variant Image", "Image Src")


def has_recognizable_headers(header: list[str]) -> bool:
    """True if header has Handle, Title, and one of the known image columns."""
    fields = set(header)
    if not REQUIRED_HEADERS <= fields:
        return False
    return any(h in fields for h in IMAGE_HEADER_CANDIDATES)


def load_shopify_products(csv_path: Path) -> list[dict]:
    """Read Shopify variant rows and group into per-product image coverage.

    Returns [] if the file is missing, empty, or lacks recognizable
    Handle/Title/image-column headers. Rows with a blank Handle are
    skipped. Products are returned in first-seen Handle order.
    """
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not has_recognizable_headers(list(reader.fieldnames)):
            return []
        image_header = next(
            (h for h in IMAGE_HEADER_CANDIDATES if h in reader.fieldnames), None
        )
        groups: dict[str, dict] = {}
        order: list[str] = []
        for row in reader:
            handle = (row.get("Handle") or "").strip()
            if not handle:
                continue
            if handle not in groups:
                groups[handle] = {"title": "", "total_count": 0, "imaged_count": 0}
                order.append(handle)
            group = groups[handle]
            group["total_count"] += 1
            title = (row.get("Title") or "").strip()
            if title and not group["title"]:
                group["title"] = title
            if image_header and (row.get(image_header) or "").strip():
                group["imaged_count"] += 1

    products: list[dict] = []
    for handle in order:
        g = groups[handle]
        products.append(
            {
                "handle": handle,
                "title": g["title"] or handle,
                "total_count": g["total_count"],
                "imaged_count": g["imaged_count"],
                "fully_imaged": g["total_count"] > 0 and g["imaged_count"] == g["total_count"],
            }
        )
    return products
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_shopify_products.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/shopify_products.py tests/test_shopify_products.py
git commit -m "feat: add Shopify Matrixify CSV parser for coverage page"
```

---

### Task 2: Approval progress + Shopify join in `compute_coverage`

**Files:**
- Modify: `backend/coverage.py`
- Modify: `backend/models.py` (`CoverageProduct` class, currently lines 129-135)
- Test: `tests/test_coverage.py` (extend)

**Interfaces:**
- Consumes: `SHOPIFY_CSV_FILENAME: str`, `load_shopify_products(csv_path: Path) -> list[dict]` from Task 1's `backend/shopify_products.py`; `ApprovalStore` (`get(image_id) -> Approval | None`, `.verdict: str`) and `get_approval_store() -> ApprovalStore` from `backend/qa/approvals.py`; `ResultRecord.image_id: str` and `ProjectState.results: list[ResultRecord]` from `backend/state.py`.
- Produces: `title_matches(tokens: set[str], candidate_title: str) -> bool`; `compute_coverage(projects: list[ProjectState], data_dir: Path = DATA_DIR, approval_store: ApprovalStore | None = None) -> list[dict]` where each product dict gains `approved_count: int`, `approved_total: int`, `on_shopify: bool | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_coverage.py`, add `title_matches` to the existing `backend.coverage` import block so it reads:

```python
from backend.coverage import (
    CATEGORIES,
    compute_coverage,
    extract_match_tokens,
    load_products,
    project_matches,
    title_matches,
)
```

Add two new imports below it:

```python
from backend.qa.approvals import Approval, ApprovalStore
from backend.state import ResultRecord
```

Then append these test functions at the end of the file:

```python
def test_title_matches_checks_whole_word_overlap():
    assert title_matches({"shaker"}, "My Shaker Upload") is True
    assert title_matches({"shaker"}, "door1.jpg") is False


def test_compute_coverage_reports_approval_progress(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    records = [
        ResultRecord(image_id="img1", wood_name="Maple"),
        ResultRecord(image_id="img2", wood_name="Oak"),
    ]
    project = _project(id="s1", name="Shaker", results=records)
    store = ApprovalStore(path=tmp_path / "approvals.json")
    store.set(Approval(image_id="img1", project_id="s1", kind="variant", verdict="approved"))

    cats = compute_coverage([project], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["approved_count"] == 1
    assert row["approved_total"] == 2


def test_compute_coverage_approval_zero_total_when_no_results(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    project = _project(id="s1", name="Shaker", results=[])
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([project], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["approved_count"] == 0
    assert row["approved_total"] == 0


def test_compute_coverage_on_shopify_true_when_fully_imaged(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,https://cdn/2.jpg\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is True


def test_compute_coverage_on_shopify_false_when_partially_imaged(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
        "shaker-cabinet-door,,SCD-OAK,\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is False


def test_compute_coverage_on_shopify_none_when_no_csv_uploaded(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is None


def test_compute_coverage_on_shopify_none_when_no_title_match(tmp_path: Path):
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    (tmp_path / "shopify_products.csv").write_text(
        "Handle,Title,Variant SKU,Variant Image\n"
        "revere-cabinet-door,Revere Cabinet Door,RCD-MAPLE,https://cdn/1.jpg\n"
    )
    store = ApprovalStore(path=tmp_path / "approvals.json")

    cats = compute_coverage([], data_dir=tmp_path, approval_store=store)
    row = next(c for c in cats if c["key"] == "wood_cabinet_doors")["products"][0]
    assert row["on_shopify"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: FAIL — `title_matches` doesn't exist yet, `compute_coverage()` raises `TypeError: compute_coverage() got an unexpected keyword argument 'approval_store'`, and product dicts lack `approved_count`/`approved_total`/`on_shopify`.

- [ ] **Step 3: Implement**

In `backend/models.py`, replace the `CoverageProduct` class (currently lines 129-135):

```python
class CoverageProduct(BaseModel):
    title: str
    net_sales: float
    quantity: int
    covered: bool
    manual: bool = False  # covered by operator override, not a project match
    matched_project_ids: list[str]
    approved_count: int = 0
    approved_total: int = 0
    on_shopify: bool | None = None  # None = no Shopify CSV uploaded, or no title match
```

In `backend/coverage.py`, update the imports at the top (after the existing `if TYPE_CHECKING:` block):

```python
from backend.qa.approvals import get_approval_store
from backend.shopify_products import SHOPIFY_CSV_FILENAME, load_shopify_products

if TYPE_CHECKING:
    from backend.qa.approvals import ApprovalStore
    from backend.state import ProjectState
```

Replace `project_matches` (and add `title_matches` right before it):

```python
def title_matches(tokens: set[str], candidate_title: str) -> bool:
    """True if any token is a whole word in candidate_title."""
    return bool(tokens & set(_words(candidate_title)))


def project_matches(project: ProjectState, tokens: set[str]) -> bool:
    """True if any token is a whole word in the project's name."""
    return title_matches(tokens, project.name)
```

Add a new helper after `load_overrides`:

```python
def _approval_progress(project: ProjectState, approval_store: ApprovalStore) -> tuple[int, int]:
    """(approved_count, total) for a project's current result records."""
    total = len(project.results)
    approved = sum(
        1
        for record in project.results
        if (a := approval_store.get(record.image_id)) is not None and a.verdict == "approved"
    )
    return approved, total
```

Replace `compute_coverage` in full:

```python
def compute_coverage(
    projects: list[ProjectState],
    data_dir: Path = DATA_DIR,
    approval_store: ApprovalStore | None = None,
) -> list[dict]:
    """Build per-category coverage data joining the CSVs with projects."""
    overrides = load_overrides(data_dir)
    shopify_products = load_shopify_products(data_dir / SHOPIFY_CSV_FILENAME)
    store = approval_store if approval_store is not None else get_approval_store()
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
            matched.sort(key=lambda p: 0 if p.results else 1)  # results-bearing first
            manual = title in overrides
            is_covered = manual or any(p.results for p in matched)
            if is_covered:
                covered_count += 1

            primary = next((p for p in matched if p.results), None)
            approved_count, approved_total = (
                _approval_progress(primary, store) if primary is not None else (0, 0)
            )

            shopify_matches = [
                sp for sp in shopify_products if title_matches(tokens, sp["title"])
            ]
            on_shopify = (
                any(sp["fully_imaged"] for sp in shopify_matches) if shopify_matches else None
            )

            products.append(
                {
                    "title": title,
                    "net_sales": net_sales,
                    "quantity": quantity,
                    "covered": is_covered,
                    "manual": manual,
                    "matched_project_ids": [p.id for p in matched],
                    "approved_count": approved_count,
                    "approved_total": approved_total,
                    "on_shopify": on_shopify,
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

Run: `uv run pytest tests/test_coverage.py tests/test_coverage_overrides.py -v`
Expected: PASS (all tests, old and new)

- [ ] **Step 5: Commit**

```bash
git add backend/coverage.py backend/models.py tests/test_coverage.py
git commit -m "feat: join approval progress and Shopify status into coverage rows"
```

---

### Task 3: Shopify CSV upload endpoint

**Files:**
- Modify: `backend/routers/coverage.py`
- Test: `tests/test_coverage.py` (extend)

**Interfaces:**
- Consumes: `DATA_DIR: Path` and `compute_coverage(...)` from `backend/coverage.py` (Task 2); `SHOPIFY_CSV_FILENAME: str`, `has_recognizable_headers(header: list[str]) -> bool` from `backend/shopify_products.py` (Task 1); `get_store(request) -> ProjectStore` from `backend/routers/projects_common.py`.
- Produces: `POST /api/coverage/shopify-csv` (multipart `file` field) → `CoverageResponse`, 400 on empty/unrecognized-header uploads.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_coverage.py` (add `import backend.routers.coverage as coverage_router` near the top imports, alongside the existing `from backend.app import app`):

```python
import backend.routers.coverage as coverage_router
```

Append these test functions:

```python
def test_upload_shopify_csv_persists_and_refreshes_coverage(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    (tmp_path / "wood_cabinet_doors.csv").write_text(
        '"Product title","Net sales","Quantity ordered"\n'
        '"Shaker Cabinet Door",100.0,5\n'
    )
    csv_bytes = (
        b"Handle,Title,Variant SKU,Variant Image\n"
        b"shaker-cabinet-door,Shaker Cabinet Door,SCD-MAPLE,https://cdn/1.jpg\n"
    )
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", csv_bytes, "text/csv")},
        )
    assert resp.status_code == 200
    assert (tmp_path / "shopify_products.csv").exists()
    data = resp.json()
    wood_cd = next(c for c in data["categories"] if c["key"] == "wood_cabinet_doors")
    row = next(p for p in wood_cd["products"] if p["title"] == "Shaker Cabinet Door")
    assert row["on_shopify"] is True


def test_upload_shopify_csv_rejects_empty_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", b"", "text/csv")},
        )
    assert resp.status_code == 400
    assert not (tmp_path / "shopify_products.csv").exists()


def test_upload_shopify_csv_rejects_unrecognized_headers(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(coverage_router, "DATA_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/coverage/shopify-csv",
            files={"file": ("shopify_products.csv", b"Foo,Bar\nx,y\n", "text/csv")},
        )
    assert resp.status_code == 400
    assert not (tmp_path / "shopify_products.csv").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coverage.py -k upload_shopify_csv -v`
Expected: FAIL with 404 (route doesn't exist yet) on all three tests.

- [ ] **Step 3: Implement**

Replace the full contents of `backend/routers/coverage.py`:

```python
"""Best-seller coverage endpoint, plus the Shopify product-image upload."""

import csv
import io

from fastapi import APIRouter, HTTPException, Request, UploadFile

from backend.coverage import DATA_DIR, compute_coverage
from backend.models import CoverageResponse
from backend.routers.projects_common import get_store
from backend.shopify_products import SHOPIFY_CSV_FILENAME, has_recognizable_headers

router = APIRouter()


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    store = get_store(request)
    # Pydantic v2 coerces the list[dict] from compute_coverage into the models.
    return CoverageResponse(
        categories=compute_coverage(store.list_projects(), data_dir=DATA_DIR)
    )


@router.post("/coverage/shopify-csv", response_model=CoverageResponse)
async def upload_shopify_csv(file: UploadFile, request: Request) -> CoverageResponse:
    """Persist an operator-exported Shopify product CSV and refresh coverage."""
    store = get_store(request)
    data = await file.read()
    if not data.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    text = data.decode("utf-8-sig", errors="replace")
    header = next(csv.reader(io.StringIO(text)), None)
    if header is None or not has_recognizable_headers(header):
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV must include Handle, Title, and a Variant Image or "
                "Image Src column"
            ),
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / SHOPIFY_CSV_FILENAME).write_bytes(data)
    return CoverageResponse(
        categories=compute_coverage(store.list_projects(), data_dir=DATA_DIR)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_coverage.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones)

- [ ] **Step 5: Run the full backend test suite**

Run: `uv run pytest tests/ -v`
Expected: PASS — confirms the `DATA_DIR` explicit pass-through on `GET /coverage` didn't change any existing behavior.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/coverage.py tests/test_coverage.py
git commit -m "feat: add Shopify CSV upload endpoint to coverage router"
```

---

### Task 4: Frontend types and API client

**Files:**
- Modify: `frontend/src/types.ts` (`CoverageProduct` interface, currently lines 118-124)
- Modify: `frontend/src/api.ts` (Coverage section, currently lines 186-189)

**Interfaces:**
- Consumes: backend `CoverageProduct` shape from Task 2/3 (`approved_count`, `approved_total`, `on_shopify`); backend `POST /api/coverage/shopify-csv` endpoint from Task 3.
- Produces: `CoverageProduct` TS type with the three new fields; `uploadShopifyCsv(file: File): Promise<CoverageResponse>` for Task 5 to call.

- [ ] **Step 1: Update the `CoverageProduct` interface**

In `frontend/src/types.ts`, replace:

```ts
export interface CoverageProduct {
  title: string;
  net_sales: number;
  quantity: number;
  covered: boolean;
  matched_project_ids: string[];
}
```

with:

```ts
export interface CoverageProduct {
  title: string;
  net_sales: number;
  quantity: number;
  covered: boolean;
  matched_project_ids: string[];
  approved_count: number;
  approved_total: number;
  on_shopify: boolean | null;
}
```

- [ ] **Step 2: Add the upload function to the API client**

In `frontend/src/api.ts`, replace the `// Coverage` section:

```ts
// Coverage
export function getCoverage(): Promise<CoverageResponse> {
  return request<CoverageResponse>('/api/coverage');
}
```

with:

```ts
// Coverage
export function getCoverage(): Promise<CoverageResponse> {
  return request<CoverageResponse>('/api/coverage');
}

export function uploadShopifyCsv(file: File): Promise<CoverageResponse> {
  const form = new FormData();
  form.append('file', file);
  return request<CoverageResponse>('/api/coverage/shopify-csv', {
    method: 'POST',
    body: form,
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit 2>&1 | grep -i coverage || echo "no coverage-related errors"`
Expected: `no coverage-related errors` (other pre-existing errors, if any, are out of scope — only confirm nothing coverage-related broke)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add approval/Shopify fields and upload client for coverage"
```

---

### Task 5: Coverage UI — badges and upload button

**Files:**
- Modify: `frontend/src/components/CoverageTable.tsx`
- Modify: `frontend/src/components/CoveragePage.tsx`
- Modify: `frontend/src/index.css` (add badge modifiers near the existing `.badge-material` rule, currently around line 749)

**Interfaces:**
- Consumes: `CoverageProduct.approved_count/approved_total/on_shopify` (Task 4 types); `api.uploadShopifyCsv(file: File): Promise<CoverageResponse>` (Task 4).
- Produces: rendered "Approved" and "On Shopify" badges per row; an "Upload Shopify CSV" button with header summary counts on the Coverage page.

- [ ] **Step 1: Add badge CSS modifiers**

In `frontend/src/index.css`, after the existing `.badge-material` rule (around line 752), add:

```css
.badge-approved {
  background: #d1fae5;
  color: #065f46;
}

.badge-partial {
  background: #fef3c7;
  color: #92400e;
}

.badge-muted {
  background: var(--color-border);
  color: var(--color-text-muted);
}
```

- [ ] **Step 2: Add the two badge columns to `CoverageTable.tsx`**

Replace the full contents of `frontend/src/components/CoverageTable.tsx`:

```tsx
// Renders one best-seller category as a coverage checklist: a header summary
// with a progress bar, then one row per product showing covered status, sales
// figures, approval progress, Shopify status, and a link to the matched
// project. Presentational only.
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
              <th>Approved</th>
              <th>On Shopify</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => (
              <tr key={p.title} className={p.covered ? 'covered' : ''}>
                <td style={{ textAlign: 'center' }}>{p.covered ? '✓' : '○'}</td>
                <td>
                  {p.covered && p.matched_project_ids.length > 0 ? (
                    <button
                      type="button"
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
                <td>
                  {p.approved_total > 0 ? (
                    <span
                      className={`badge ${p.approved_count === p.approved_total ? 'badge-approved' : 'badge-partial'}`}
                    >
                      {p.approved_count}/{p.approved_total} approved
                    </span>
                  ) : (
                    <span className="badge badge-muted">—</span>
                  )}
                </td>
                <td>
                  {p.on_shopify === true ? (
                    <span className="badge badge-approved">On Shopify</span>
                  ) : p.on_shopify === false ? (
                    <span className="badge badge-muted">Missing images</span>
                  ) : (
                    <span className="badge badge-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
```

- [ ] **Step 3: Add the upload button and summary counts to `CoveragePage.tsx`**

Replace the full contents of `frontend/src/components/CoveragePage.tsx`:

```tsx
// Top-level Coverage view: fetches /api/coverage once, holds the active
// sub-tab and the "only uncovered" filter, renders the active category, and
// hosts the Shopify CSV upload control.
import { useState, useEffect, useRef, useCallback } from 'react';
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
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .getCoverage()
      .then((resp) => {
        setData(resp);
        setActiveKey((prev) => prev ?? resp.categories[0]?.key ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load coverage'));
  }, []);

  const handleUploadClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileSelected = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-uploading a file with the same name
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    api
      .uploadShopifyCsv(file)
      .then(setData)
      .catch((err) => setUploadError(err instanceof Error ? err.message : 'Upload failed'))
      .finally(() => setUploading(false));
  }, []);

  if (error) return <div className="status-error">{error}</div>;
  if (!data) return <div className="status-info">Loading coverage…</div>;

  const active = data.categories.find((c) => c.key === activeKey) ?? data.categories[0];
  const approvedCount = active
    ? active.products.filter((p) => p.approved_total > 0 && p.approved_count === p.approved_total).length
    : 0;
  const onShopifyCount = active ? active.products.filter((p) => p.on_shopify === true).length : 0;

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

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.875rem' }}>
          <input
            type="checkbox"
            checked={onlyUncovered}
            onChange={(e) => setOnlyUncovered(e.target.checked)}
          />
          Show only not-yet-generated
        </label>

        {active && (
          <span style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>
            {approvedCount}/{active.total} approved · {onShopifyCount}/{active.total} on Shopify
          </span>
        )}

        <div style={{ marginLeft: 'auto' }}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={handleFileSelected}
          />
          <button type="button" onClick={handleUploadClick} disabled={uploading}>
            {uploading ? 'Uploading…' : 'Upload Shopify CSV'}
          </button>
        </div>
      </div>

      {uploadError && (
        <div className="status-error" style={{ marginBottom: '0.75rem' }}>
          {uploadError}
        </div>
      )}

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

- [ ] **Step 4: Build and typecheck**

Run: `npm run build`
Expected: builds successfully with no TypeScript errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/CoverageTable.tsx frontend/src/components/CoveragePage.tsx frontend/src/index.css
git commit -m "feat: render approval/Shopify badges and CSV upload on coverage page"
```

---

### Task 6: End-to-end verification

**Files:** none (verification only)

**Interfaces:**
- Consumes: the running app (Tasks 1-5 complete).

- [ ] **Step 1: Run the full backend test suite**

Run: `uv run pytest tests/ -v`
Expected: PASS, no regressions

- [ ] **Step 2: Run the full frontend build**

Run: `npm run build`
Expected: builds successfully

- [ ] **Step 3: Manual smoke test**

Run: `npm run dev` (starts backend on :8000 and frontend on :5173)

In the browser:
1. Open the Coverage tab. Confirm existing rows still show ✓/○ and sales figures as before.
2. Confirm every row now also shows an "Approved" badge (either `X/Y approved` or `—`) and an "On Shopify" badge (`—` before any CSV is uploaded).
3. Click "Upload Shopify CSV" and select a real Shopify/Matrixify product export (Handle, Title, Variant SKU, Variant Image/Image Src columns). Confirm the page refreshes and at least one row's "On Shopify" badge changes to "On Shopify" or "Missing images".
4. Confirm the header summary counts (`X/Y approved · X/Y on Shopify`) match what's visible in the table for the active category tab.
5. Try uploading a non-CSV or empty file; confirm a red error message appears and the table doesn't lose its previous state.

- [ ] **Step 4: Stop the dev servers**

Press Ctrl+C in the terminal running `npm run dev`.
