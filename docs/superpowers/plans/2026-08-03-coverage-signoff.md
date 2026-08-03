# Coverage Operator Sign-Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace inferred coverage (`any(p.results)`) with two recorded operator sign-offs per product, backed by an advisory palette-gap calculation.

**Architecture:** A new `backend/signoff.py` owns a git-tracked JSON record keyed by sales-CSV product title. `backend/coverage.py` stays the matcher and gains one job: attach that record plus a computed gap to each product row. Three endpoints on the existing coverage router write the record. The frontend adds an expandable per-row panel. Sign-off is never inferred; the gap is evidence only.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, React 19, TypeScript 5.7, Vite 6.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-coverage-signoff-design.md`. Read it before Task 1.
- Record file: `docs/sales/data/coverage_signoff.json`, git-tracked.
- Record key: the exact sales-CSV product title, same key `coverage_overrides.json` uses.
- Sign-off is never inferred. No code path may set `variations_complete` or `in_shopify` from generated results, verdicts, or Shopify data.
- Absent gate key = never reviewed. Revoking deletes the key; never store `false`.
- Writes are atomic: temp file in the same directory + `os.replace`.
- A missing or malformed record file loads as `{}` and never raises.
- Backend lint must pass: `npm run lint` (ruff, line length 100).
- Python: no `from __future__ import annotations` needed except where the existing file already has it (`coverage.py` does).
- Run backend tests as `uv run pytest tests/ -q --ignore=tests/qa` and `uv run pytest tests/qa -q` separately — the combined run OOMs on this machine.

---

### Task 0: Merge the advisory-signals branch

The spec builds on `feat/coverage-approval-shopify-status`, which adds `approved_count`, `approved_total`, and `on_shopify` to `CoverageProduct`. Every later task assumes those fields exist.

**Files:**
- Modify: repository state only (merge commit)

**Interfaces:**
- Consumes: nothing
- Produces: `CoverageProduct` with `approved_count: int`, `approved_total: int`, `on_shopify: bool | None`; `compute_coverage(projects, data_dir=DATA_DIR, approval_store=None)`; `backend/shopify_products.py`

- [ ] **Step 1: Merge the branch**

```bash
git checkout master
git merge --no-ff feat/coverage-approval-shopify-status \
  -m "Merge branch 'feat/coverage-approval-shopify-status'"
```

- [ ] **Step 2: Verify the merged tests pass**

Run: `uv run pytest tests/test_coverage.py tests/test_shopify_products.py -q`
Expected: PASS, no failures.

- [ ] **Step 3: Verify the frontend still builds**

Run: `cd frontend && npx tsc -b && cd .. && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit** (merge commit already created; nothing further if clean)

```bash
git status --short   # expect empty
```

---

### Task 1: Sign-off record store

**Files:**
- Create: `backend/signoff.py`
- Test: `tests/test_signoff.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `SIGNOFF_FILENAME = "coverage_signoff.json"`
  - `load_signoff(data_dir: Path) -> dict[str, dict]`
  - `save_signoff(data_dir: Path, record: dict[str, dict]) -> None`
  - `set_gate(record, title, gate, value, *, by, at, result_count=None, acknowledged_gap=False) -> dict[str, dict]`
  - `set_canonical(record, title, project_id) -> dict[str, dict]`
  - `set_exclusions(record, title, colors) -> dict[str, dict]`
  - `is_stale(entry: dict, distinct_colors: int) -> bool`
  - Gate names are the literals `"variations"` and `"shopify"`; they map to record keys `"variations_complete"` and `"in_shopify"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_signoff.py`:

```python
import json
from pathlib import Path

import pytest

from backend.signoff import (
    GATE_KEYS,
    SIGNOFF_FILENAME,
    is_stale,
    load_signoff,
    save_signoff,
    set_canonical,
    set_exclusions,
    set_gate,
)


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    assert load_signoff(tmp_path) == {}


def test_load_malformed_file_returns_empty(tmp_path: Path) -> None:
    (tmp_path / SIGNOFF_FILENAME).write_text("{not json")
    assert load_signoff(tmp_path) == {}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    record = {"Shaker Cabinet Door": {"canonical_project_id": "abc123"}}
    save_signoff(tmp_path, record)
    assert load_signoff(tmp_path) == record


def test_save_leaves_no_temp_file(tmp_path: Path) -> None:
    save_signoff(tmp_path, {"A": {}})
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [SIGNOFF_FILENAME]


def test_set_gate_stamps_who_and_when(tmp_path: Path) -> None:
    record = set_gate({}, "Shaker Cabinet Door", "variations", True,
                      by="jonny", at="2026-08-03T14:22:00Z", result_count=43)
    entry = record["Shaker Cabinet Door"]["variations_complete"]
    assert entry == {
        "by": "jonny",
        "at": "2026-08-03T14:22:00Z",
        "result_count": 43,
        "acknowledged_gap": False,
    }


def test_shopify_gate_omits_result_count() -> None:
    record = set_gate({}, "A", "shopify", True, by="jonny", at="2026-08-03T00:00:00Z")
    assert record["A"]["in_shopify"] == {"by": "jonny", "at": "2026-08-03T00:00:00Z"}


def test_clearing_gate_deletes_the_key() -> None:
    record = set_gate({}, "A", "variations", True, by="j", at="t", result_count=1)
    record = set_gate(record, "A", "variations", False, by="j", at="t2")
    assert "variations_complete" not in record["A"]


def test_unknown_gate_raises() -> None:
    with pytest.raises(ValueError):
        set_gate({}, "A", "bogus", True, by="j", at="t")


def test_set_canonical_and_exclusions_preserve_other_fields() -> None:
    record = set_gate({}, "A", "shopify", True, by="j", at="t")
    record = set_canonical(record, "A", "proj1")
    record = set_exclusions(record, "A", ["Black Oak"])
    assert record["A"]["canonical_project_id"] == "proj1"
    assert record["A"]["excluded_colors"] == ["Black Oak"]
    assert record["A"]["in_shopify"]["by"] == "j"


def test_exclusions_are_deduped_and_sorted() -> None:
    record = set_exclusions({}, "A", ["Niagara", "Black Oak", "Niagara"])
    assert record["A"]["excluded_colors"] == ["Black Oak", "Niagara"]


def test_is_stale_true_when_count_moved() -> None:
    entry = {"variations_complete": {"by": "j", "at": "t", "result_count": 43,
                                     "acknowledged_gap": False}}
    assert is_stale(entry, 44) is True
    assert is_stale(entry, 43) is False


def test_is_stale_false_when_never_signed_off() -> None:
    assert is_stale({}, 12) is False


def test_gate_keys_mapping_is_exact() -> None:
    assert GATE_KEYS == {"variations": "variations_complete", "shopify": "in_shopify"}


def test_saved_file_is_readable_json(tmp_path: Path) -> None:
    save_signoff(tmp_path, {"A": {"excluded_colors": []}})
    data = json.loads((tmp_path / SIGNOFF_FILENAME).read_text())
    assert data == {"A": {"excluded_colors": []}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signoff.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.signoff'`

- [ ] **Step 3: Write the implementation**

Create `backend/signoff.py`:

```python
"""Operator sign-off on coverage: the durable record of human judgment.

Coverage cannot be inferred. The set of colors a door needs varies by style,
so "all variations generated" is an operator judgment, as is "uploaded to
Shopify". This module owns that record and nothing else — it knows nothing
about sales CSVs, projects, or Shopify.

Keyed by the exact sales-CSV product title, the same key coverage_overrides.json
uses. Lives in docs/sales/data/ and is git-tracked: sign-off is a business
record that must survive a fresh clone and be reviewable in a diff.
"""

import json
import os
import tempfile
from pathlib import Path

SIGNOFF_FILENAME = "coverage_signoff.json"

# Public gate names -> record keys. Callers pass the short name.
GATE_KEYS = {"variations": "variations_complete", "shopify": "in_shopify"}


def load_signoff(data_dir: Path) -> dict[str, dict]:
    """Read the sign-off record. Missing or malformed file means no sign-offs.

    Never raises: a broken file must degrade to "nothing reviewed", never to a
    crashed coverage page or a false green.
    """
    path = data_dir / SIGNOFF_FILENAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def save_signoff(data_dir: Path, record: dict[str, dict]) -> None:
    """Write the record atomically — a partial file would read as lost sign-offs."""
    data_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=data_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(record, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, data_dir / SIGNOFF_FILENAME)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _entry(record: dict[str, dict], title: str) -> dict:
    return dict(record.get(title) or {})


def set_gate(
    record: dict[str, dict],
    title: str,
    gate: str,
    value: bool,
    *,
    by: str,
    at: str,
    result_count: int | None = None,
    acknowledged_gap: bool = False,
) -> dict[str, dict]:
    """Stamp or clear one gate. Returns a new record; does not mutate the input.

    Clearing deletes the key rather than storing False, so "never reviewed" and
    "revoked" both read as absent — a revoked gate is simply re-openable work.
    """
    if gate not in GATE_KEYS:
        raise ValueError(f"unknown gate {gate!r}; expected one of {sorted(GATE_KEYS)}")
    key = GATE_KEYS[gate]
    entry = _entry(record, title)
    if not value:
        entry.pop(key, None)
    else:
        stamp: dict = {"by": by, "at": at}
        if gate == "variations":
            stamp["result_count"] = result_count
            stamp["acknowledged_gap"] = acknowledged_gap
        entry[key] = stamp
    return {**record, title: entry}


def set_canonical(record: dict[str, dict], title: str, project_id: str) -> dict[str, dict]:
    """Designate the project the palette checklist reads from."""
    entry = _entry(record, title)
    entry["canonical_project_id"] = project_id
    return {**record, title: entry}


def set_exclusions(
    record: dict[str, dict], title: str, colors: list[str]
) -> dict[str, dict]:
    """Mark colors this product does not need. Stored sorted and deduped so the
    git diff stays stable when the operator re-clicks in a different order."""
    entry = _entry(record, title)
    entry["excluded_colors"] = sorted(set(colors))
    return {**record, title: entry}


def is_stale(entry: dict, distinct_colors: int) -> bool:
    """True when the canonical project's colour count moved since sign-off.

    This is what stops a signed-off row from silently rotting back into the
    state this whole feature exists to fix.
    """
    stamp = entry.get(GATE_KEYS["variations"])
    if not stamp:
        return False
    recorded = stamp.get("result_count")
    if recorded is None:
        return False
    return int(recorded) != int(distinct_colors)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signoff.py -q`
Expected: PASS, 14 tests.

- [ ] **Step 5: Lint**

Run: `npm run lint`
Expected: "All checks passed!"

- [ ] **Step 6: Commit**

```bash
git add backend/signoff.py tests/test_signoff.py
git commit -m "feat: add coverage sign-off record store"
```

---

### Task 2: Palette gap calculation

**Files:**
- Create: `backend/palette.py`
- Test: `tests/test_palette.py`

**Interfaces:**
- Consumes: `backend.materials.load_material_types(material) -> dict[str, dict]`
- Produces:
  - `full_palette(material: str) -> list[str]` — every colour name for the material, sorted
  - `distinct_generated(project) -> set[str]` — distinct `wood_name` across `project.results`
  - `compute_gap(material, excluded, project) -> dict` returning
    `{"expected": int, "generated": int, "missing": list[str], "excluded": list[str]}`

Separate from `coverage.py` because it is pure palette arithmetic with no CSV or matching concerns, and `coverage.py` is already the largest surface in this feature.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_palette.py`:

```python
from dataclasses import dataclass, field

from backend.palette import compute_gap, distinct_generated, full_palette


@dataclass
class FakeRecord:
    wood_name: str


@dataclass
class FakeProject:
    results: list = field(default_factory=list)


def test_full_palette_is_sorted_and_nonempty():
    palette = full_palette("rtf")
    assert palette == sorted(palette)
    assert len(palette) > 30


def test_distinct_generated_collapses_duplicate_attempts():
    project = FakeProject(results=[
        FakeRecord("Bisque"), FakeRecord("Bisque"), FakeRecord("Niagara"),
    ])
    assert distinct_generated(project) == {"Bisque", "Niagara"}


def test_distinct_generated_empty_project():
    assert distinct_generated(FakeProject()) == set()


def test_compute_gap_lists_missing_colours():
    project = FakeProject(results=[FakeRecord("Bisque")])
    gap = compute_gap("rtf", excluded=[], project=project)
    assert gap["generated"] == 1
    assert gap["expected"] == len(full_palette("rtf"))
    assert "Bisque" not in gap["missing"]
    assert len(gap["missing"]) == gap["expected"] - 1


def test_excluded_colours_shrink_expected_and_never_appear_missing():
    palette = full_palette("rtf")
    excluded = palette[:2]
    project = FakeProject(results=[])
    gap = compute_gap("rtf", excluded=excluded, project=project)
    assert gap["expected"] == len(palette) - 2
    assert all(c not in gap["missing"] for c in excluded)
    assert gap["excluded"] == sorted(excluded)


def test_generated_colour_outside_palette_is_ignored_not_counted_twice():
    project = FakeProject(results=[FakeRecord("Not A Real Colour")])
    gap = compute_gap("rtf", excluded=[], project=project)
    assert gap["generated"] == 0
    assert len(gap["missing"]) == gap["expected"]


def test_no_project_yields_everything_missing():
    gap = compute_gap("rtf", excluded=[], project=None)
    assert gap["generated"] == 0
    assert len(gap["missing"]) == gap["expected"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_palette.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.palette'`

- [ ] **Step 3: Write the implementation**

Create `backend/palette.py`:

```python
"""Palette arithmetic for coverage: expected colours vs. generated colours.

Advisory only. The result is evidence shown to the operator at sign-off; it
never decides coverage. "Expected" is a starting set to subtract from, not a
completion target — some styles legitimately skip colours.
"""

from backend.materials import load_material_types


def full_palette(material: str) -> list[str]:
    """Every colour name defined for a material, sorted.

    Includes description-only entries that have no swatch file, because those
    still generate.
    """
    types = load_material_types(material)
    return sorted({(wt.get("name") or key) for key, wt in types.items()})


def distinct_generated(project) -> set[str]:
    """Distinct colour names present in a project's results.

    Distinct, not len(results): re-attempts leave duplicates behind, so a raw
    count reads complete while colours are missing (AP768: 45 results, 43
    colours).
    """
    if project is None:
        return set()
    return {r.wood_name for r in project.results}


def compute_gap(material: str, excluded: list[str], project) -> dict:
    """Expected minus generated, with excluded colours removed from expected."""
    excluded_set = set(excluded or [])
    expected = [c for c in full_palette(material) if c not in excluded_set]
    generated = distinct_generated(project) & set(expected)
    return {
        "expected": len(expected),
        "generated": len(generated),
        "missing": sorted(set(expected) - generated),
        "excluded": sorted(excluded_set),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_palette.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Lint and commit**

```bash
npm run lint
git add backend/palette.py tests/test_palette.py
git commit -m "feat: add palette gap calculation for coverage"
```

---

### Task 3: Join sign-off into coverage rows

**Files:**
- Modify: `backend/coverage.py` (`compute_coverage`, and delete `load_overrides`)
- Modify: `backend/models.py:129-135` (`CoverageProduct`), `backend/models.py:138-143` (`CoverageCategory`)
- Test: `tests/test_coverage.py` (extend)

**Interfaces:**
- Consumes: `load_signoff`, `is_stale`, `GATE_KEYS` (Task 1); `compute_gap` (Task 2)
- Produces: `compute_coverage(projects, data_dir=DATA_DIR, approval_store=None, signoff=None) -> list[dict]`, where each product dict gains `variations_complete: bool`, `in_shopify: bool`, `canonical_project_id: str | None`, `excluded_colors: list[str]`, `gap: dict | None`, `stale: bool`, and each category gains `variations_complete: int` and `in_shopify_count: int`.

The `covered` field is retained on the model but now means `variations_complete` — the frontend's existing filter keeps working without a rename. The `manual` field and `load_overrides` are removed; Task 5 migrates the five titles.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_coverage.py`:

```python
from backend.state import ResultRecord


def _project(pid: str, name: str, colours: list[str], material: str = "rtf") -> ProjectState:
    p = ProjectState(id=pid, name=name, product_type="Cabinet Door", material_type=material)
    p.results = [ResultRecord(image_id=f"{pid}-{i}", wood_name=c)
                 for i, c in enumerate(colours)]
    return p


def test_results_alone_no_longer_mark_covered(tmp_path: Path):
    project = _project("p1", "AR756", ["Bisque"])
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff={})
    rows = [r for c in cats for r in c["products"] if "AR756" in r["title"]]
    assert rows, "expected an AR756 row in the fixtures"
    assert all(r["variations_complete"] is False for r in rows)
    assert all(r["in_shopify"] is False for r in rows)


def test_signoff_drives_the_two_gates():
    project = _project("p1", "AR756", ["Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {
        "variations_complete": {"by": "j", "at": "t", "result_count": 1,
                                "acknowledged_gap": True},
        "in_shopify": {"by": "j", "at": "t"},
    }}
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["variations_complete"] is True
    assert row["in_shopify"] is True


def test_gap_reads_canonical_project_only_not_the_union():
    # Two projects match the same product; only the canonical one counts.
    canonical = _project("good", "AR756", ["Bisque"])
    decoy = _project("decoy", "AR756-test", ["Niagara", "Snow White", "Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {"canonical_project_id": "good"}}
    cats = compute_coverage([canonical, decoy], data_dir=Path("docs/sales/data"),
                            signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"]["generated"] == 1
    assert "Niagara" in row["gap"]["missing"]


def test_excluded_colours_shrink_expected():
    project = _project("p1", "AR756", [])
    title = "AR756 Thermofoil Cabinet Door"
    base = compute_coverage([project], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "p1"}})
    base_row = next(r for c in base for r in c["products"] if r["title"] == title)
    with_excl = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff={
        title: {"canonical_project_id": "p1", "excluded_colors": ["Bisque"]}})
    excl_row = next(r for c in with_excl for r in c["products"] if r["title"] == title)
    assert excl_row["gap"]["expected"] == base_row["gap"]["expected"] - 1
    assert "Bisque" not in excl_row["gap"]["missing"]


def test_duplicate_attempts_count_once():
    project = _project("p1", "AR756", ["Bisque", "Bisque"])
    title = "AR756 Thermofoil Cabinet Door"
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "p1"}})
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"]["generated"] == 1


def test_stale_flag_when_colour_count_moved():
    project = _project("p1", "AR756", ["Bisque", "Niagara"])
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {
        "canonical_project_id": "p1",
        "variations_complete": {"by": "j", "at": "t", "result_count": 1,
                                "acknowledged_gap": True},
    }}
    cats = compute_coverage([project], data_dir=Path("docs/sales/data"), signoff=signoff)
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["stale"] is True


def test_category_counts_both_gates():
    title = "AR756 Thermofoil Cabinet Door"
    signoff = {title: {"variations_complete": {"by": "j", "at": "t", "result_count": 0,
                                               "acknowledged_gap": True}}}
    cats = compute_coverage([], data_dir=Path("docs/sales/data"), signoff=signoff)
    cat = next(c for c in cats if c["key"] == "thermofoil_cabinet_doors")
    assert cat["variations_complete"] == 1
    assert cat["in_shopify_count"] == 0


def test_missing_canonical_project_yields_null_gap():
    title = "AR756 Thermofoil Cabinet Door"
    cats = compute_coverage([], data_dir=Path("docs/sales/data"),
                            signoff={title: {"canonical_project_id": "gone"}})
    row = next(r for c in cats for r in c["products"] if r["title"] == title)
    assert row["gap"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coverage.py -q -k "signoff or gap or gates or stale or duplicate or canonical or excluded or both_gates"`
Expected: FAIL — `compute_coverage() got an unexpected keyword argument 'signoff'`

- [ ] **Step 3: Update the Pydantic models**

In `backend/models.py`, replace `CoverageProduct` and `CoverageCategory`:

```python
class CoverageProduct(BaseModel):
    title: str
    net_sales: float
    quantity: int
    covered: bool  # mirrors variations_complete; kept for the existing filter
    matched_project_ids: list[str]
    approved_count: int = 0
    approved_total: int = 0
    on_shopify: bool | None = None  # None = no Shopify CSV uploaded, or no title match
    variations_complete: bool = False
    in_shopify: bool = False
    canonical_project_id: str | None = None
    excluded_colors: list[str] = []
    gap: dict | None = None  # None = no canonical project resolved
    stale: bool = False


class CoverageCategory(BaseModel):
    key: str
    label: str
    covered: int  # mirrors variations_complete count
    total: int
    variations_complete: int = 0
    in_shopify_count: int = 0
    products: list[CoverageProduct]
```

- [ ] **Step 4: Rewrite the join in `backend/coverage.py`**

Delete `load_overrides` entirely. Replace the body of the per-product loop and the category assembly in `compute_coverage`:

```python
def compute_coverage(
    projects: list[ProjectState],
    data_dir: Path = DATA_DIR,
    approval_store: ApprovalStore | None = None,
    signoff: dict[str, dict] | None = None,
) -> list[dict]:
    """Build per-category coverage data joining the CSVs with projects.

    Coverage is decided ONLY by the sign-off record. The palette gap and the
    approval/Shopify signals are advisory evidence for the operator.
    """
    record = load_signoff(data_dir) if signoff is None else signoff
    shopify_products = load_shopify_products(data_dir / SHOPIFY_CSV_FILENAME)
    store = approval_store if approval_store is not None else get_approval_store()
    by_id = {p.id: p for p in projects}
    categories: list[dict] = []
    for cat in CATEGORIES:
        candidates = [
            p
            for p in projects
            if p.material_type == cat["material"]
            and p.product_type == cat["product_type"]
        ]
        products: list[dict] = []
        n_variations = 0
        n_shopify = 0
        for title, net_sales, quantity in load_products(data_dir / cat["csv"]):
            tokens = extract_match_tokens(title)
            matched = [p for p in candidates if project_matches(p, tokens)]
            matched.sort(key=lambda p: 0 if p.results else 1)
            entry = record.get(title) or {}

            canonical_id = entry.get("canonical_project_id")
            canonical = by_id.get(canonical_id) if canonical_id else None
            excluded = list(entry.get("excluded_colors") or [])
            gap = (
                compute_gap(cat["material"], excluded, canonical)
                if canonical is not None
                else None
            )

            variations_done = GATE_KEYS["variations"] in entry
            shopify_done = GATE_KEYS["shopify"] in entry
            n_variations += int(variations_done)
            n_shopify += int(shopify_done)

            products.append(
                {
                    "title": title,
                    "net_sales": net_sales,
                    "quantity": quantity,
                    "covered": variations_done,
                    "matched_project_ids": [p.id for p in matched],
                    "approved_count": _approval_count(matched, store),
                    "approved_total": _approval_total(matched),
                    "on_shopify": _shopify_status(title, tokens, shopify_products),
                    "variations_complete": variations_done,
                    "in_shopify": shopify_done,
                    "canonical_project_id": canonical_id,
                    "excluded_colors": excluded,
                    "gap": gap,
                    "stale": is_stale(entry, len(distinct_generated(canonical)))
                    if canonical is not None
                    else False,
                }
            )
        categories.append(
            {
                "key": cat["key"],
                "label": cat["label"],
                "covered": n_variations,
                "total": len(products),
                "variations_complete": n_variations,
                "in_shopify_count": n_shopify,
                "products": products,
            }
        )
    return categories
```

Add the imports at the top of `backend/coverage.py`:

```python
from backend.palette import compute_gap, distinct_generated
from backend.signoff import GATE_KEYS, is_stale, load_signoff
```

Keep the branch's existing approval and Shopify helpers. If they are inline in the loop rather than named helpers, extract them to `_approval_count(matched, store) -> int`, `_approval_total(matched) -> int`, and `_shopify_status(title, tokens, shopify_products) -> bool | None` so the loop above compiles as written.

- [ ] **Step 5: Run the full coverage test file**

Run: `uv run pytest tests/test_coverage.py -q`
Expected: PASS. Any pre-existing test asserting `manual` or `covered` from results must be updated to the new rule — that behaviour change is the point of this task.

- [ ] **Step 6: Lint and commit**

```bash
npm run lint
git add backend/coverage.py backend/models.py tests/test_coverage.py
git commit -m "feat: decide coverage from operator sign-off, not generated results"
```

---

### Task 4: Sign-off API endpoints

**Files:**
- Modify: `backend/routers/coverage.py`
- Modify: `backend/models.py` (request bodies)
- Test: `tests/test_coverage_signoff_api.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1–3
- Produces:
  - `PUT /api/coverage/{title}/canonical` body `{"project_id": str}`
  - `PUT /api/coverage/{title}/exclusions` body `{"colors": list[str]}`
  - `POST /api/coverage/{title}/signoff` body `{"gate": str, "value": bool, "acknowledge_gap": bool = False, "by": str = "operator"}`
  - All three return `CoverageResponse`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_coverage_signoff_api.py`:

```python
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from backend.app import app

TITLE = "AR756 Thermofoil Cabinet Door"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Point the router at a scratch data dir seeded with the real CSVs."""
    import shutil

    import backend.routers.coverage as cov_router

    src = Path("docs/sales/data")
    for name in ("thermofoil_cabinet_doors.csv",):
        shutil.copy(src / name, tmp_path / name)
    monkeypatch.setattr(cov_router, "DATA_DIR", tmp_path)
    return TestClient(app)


def test_canonical_rejects_unknown_project(client):
    r = client.put(f"/api/coverage/{quote(TITLE)}/canonical", json={"project_id": "nope"})
    assert r.status_code == 422


def test_signoff_shopify_gate_succeeds(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": True})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["in_shopify"] is True


def test_variations_signoff_blocked_by_gap(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True})
    assert r.status_code == 409
    assert "missing" in r.json()["detail"].lower()


def test_variations_signoff_with_acknowledge_succeeds(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "variations", "value": True, "acknowledge_gap": True})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["variations_complete"] is True


def test_unknown_title_404(client):
    r = client.post(f"/api/coverage/{quote('No Such Door')}/signoff",
                    json={"gate": "shopify", "value": True})
    assert r.status_code == 404


def test_unknown_gate_422(client):
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "bogus", "value": True})
    assert r.status_code == 422


def test_exclusions_round_trip(client):
    r = client.put(f"/api/coverage/{quote(TITLE)}/exclusions",
                   json={"colors": ["Bisque", "Bisque"]})
    assert r.status_code == 200
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["excluded_colors"] == ["Bisque"]


def test_revoking_gate_clears_it(client):
    client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                json={"gate": "shopify", "value": True})
    r = client.post(f"/api/coverage/{quote(TITLE)}/signoff",
                    json={"gate": "shopify", "value": False})
    row = next(p for c in r.json()["categories"] for p in c["products"]
               if p["title"] == TITLE)
    assert row["in_shopify"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_coverage_signoff_api.py -q`
Expected: FAIL with 404/405 — routes not defined.

- [ ] **Step 3: Add request models**

Append to `backend/models.py`:

```python
class CanonicalRequest(BaseModel):
    project_id: str


class ExclusionsRequest(BaseModel):
    colors: list[str]


class SignoffRequest(BaseModel):
    gate: Literal["variations", "shopify"]
    value: bool
    acknowledge_gap: bool = False
    by: str = "operator"
```

Add `Literal` to the `typing` import at the top of `backend/models.py` if absent.

- [ ] **Step 4: Implement the endpoints**

Rewrite `backend/routers/coverage.py`:

```python
"""Best-seller coverage endpoints, including operator sign-off."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from backend.coverage import DATA_DIR, compute_coverage, load_products, CATEGORIES
from backend.models import (
    CanonicalRequest,
    CoverageResponse,
    ExclusionsRequest,
    SignoffRequest,
)
from backend.palette import compute_gap, distinct_generated
from backend.routers.projects_common import get_store
from backend.signoff import load_signoff, save_signoff, set_canonical, set_exclusions, set_gate

router = APIRouter()


def _known_titles() -> dict[str, str]:
    """Map every sales-CSV product title to its material, for validation."""
    titles: dict[str, str] = {}
    for cat in CATEGORIES:
        for title, _, _ in load_products(DATA_DIR / cat["csv"]):
            titles[title] = cat["material"]
    return titles


def _require_title(title: str) -> str:
    known = _known_titles()
    if title not in known:
        raise HTTPException(status_code=404, detail=f"Unknown product title: {title}")
    return known[title]


def _response(request: Request) -> CoverageResponse:
    store = get_store(request)
    return CoverageResponse(categories=compute_coverage(store.list_projects(), DATA_DIR))


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    return _response(request)


@router.put("/coverage/{title}/canonical", response_model=CoverageResponse)
def put_canonical(title: str, body: CanonicalRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    store = get_store(request)
    if store.get(body.project_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown project: {body.project_id}")
    save_signoff(DATA_DIR, set_canonical(load_signoff(DATA_DIR), title, body.project_id))
    return _response(request)


@router.put("/coverage/{title}/exclusions", response_model=CoverageResponse)
def put_exclusions(title: str, body: ExclusionsRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    save_signoff(DATA_DIR, set_exclusions(load_signoff(DATA_DIR), title, body.colors))
    return _response(request)


@router.post("/coverage/{title}/signoff", response_model=CoverageResponse)
def post_signoff(title: str, body: SignoffRequest, request: Request) -> CoverageResponse:
    material = _require_title(title)
    store = get_store(request)
    record = load_signoff(DATA_DIR)
    entry = record.get(title) or {}
    canonical = store.get(entry.get("canonical_project_id") or "")

    result_count = len(distinct_generated(canonical)) if canonical else 0

    # The operator may always override, but never by accident, and the override
    # is recorded on the stamp.
    if body.gate == "variations" and body.value and not body.acknowledge_gap:
        gap = compute_gap(material, list(entry.get("excluded_colors") or []), canonical)
        if gap["missing"]:
            preview = ", ".join(gap["missing"][:5])
            more = "" if len(gap["missing"]) <= 5 else f" (+{len(gap['missing']) - 5} more)"
            raise HTTPException(
                status_code=409,
                detail=f"{len(gap['missing'])} colours still missing: {preview}{more}. "
                "Re-send with acknowledge_gap to sign off anyway.",
            )

    record = set_gate(
        record, title, body.gate, body.value,
        by=body.by,
        at=datetime.now(UTC).isoformat(),
        result_count=result_count,
        acknowledged_gap=body.acknowledge_gap,
    )
    save_signoff(DATA_DIR, record)
    return _response(request)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_coverage_signoff_api.py -q`
Expected: PASS, 8 tests.

- [ ] **Step 6: Run the whole backend suite**

Run: `uv run pytest tests/ -q --ignore=tests/qa` then `uv run pytest tests/qa -q`
Expected: PASS both.

- [ ] **Step 7: Lint and commit**

```bash
npm run lint
git add backend/routers/coverage.py backend/models.py tests/test_coverage_signoff_api.py
git commit -m "feat: add coverage sign-off endpoints"
```

---

### Task 5: Migrate the existing overrides

**Files:**
- Create: `scripts/migrate_coverage_overrides.py`
- Create: `docs/sales/data/coverage_signoff.json` (output, committed)
- Delete: `docs/sales/data/coverage_overrides.json`
- Test: `tests/test_migrate_coverage_overrides.py`

**Interfaces:**
- Consumes: `load_signoff`, `save_signoff`, `set_gate` (Task 1)
- Produces: `migrate(data_dir: Path, *, now: str) -> int` returning the number of titles migrated

The five titles in `coverage_overrides.json` were claims that the work was done outside the app, so both gates are already true for them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrate_coverage_overrides.py`:

```python
import json
from pathlib import Path

from backend.signoff import load_signoff
from scripts.migrate_coverage_overrides import migrate


def test_migrates_both_gates(tmp_path: Path):
    (tmp_path / "coverage_overrides.json").write_text(
        json.dumps({"covered": ["FS842 Thermofoil Cabinet Door"]})
    )
    n = migrate(tmp_path, now="2026-08-03T00:00:00Z")
    assert n == 1
    record = load_signoff(tmp_path)
    entry = record["FS842 Thermofoil Cabinet Door"]
    assert entry["variations_complete"]["by"] == "migrated"
    assert entry["in_shopify"]["by"] == "migrated"
    assert entry["variations_complete"]["acknowledged_gap"] is True


def test_missing_overrides_file_is_a_noop(tmp_path: Path):
    assert migrate(tmp_path, now="2026-08-03T00:00:00Z") == 0
    assert load_signoff(tmp_path) == {}


def test_does_not_clobber_existing_signoff(tmp_path: Path):
    (tmp_path / "coverage_overrides.json").write_text(json.dumps({"covered": ["A"]}))
    (tmp_path / "coverage_signoff.json").write_text(
        json.dumps({"B": {"canonical_project_id": "keep"}})
    )
    migrate(tmp_path, now="2026-08-03T00:00:00Z")
    record = load_signoff(tmp_path)
    assert record["B"]["canonical_project_id"] == "keep"
    assert "A" in record
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_migrate_coverage_overrides.py -q`
Expected: FAIL — `No module named 'scripts.migrate_coverage_overrides'`

- [ ] **Step 3: Write the script**

Create `scripts/migrate_coverage_overrides.py`:

```python
"""One-shot: turn coverage_overrides.json into coverage_signoff.json entries.

The override list recorded products whose images were produced outside the app.
Both gates are therefore already true for them, stamped `migrated` so the
provenance stays visible in the record.

Run once:  uv run python scripts/migrate_coverage_overrides.py
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.signoff import load_signoff, save_signoff, set_gate

DATA_DIR = Path("docs/sales/data")


def migrate(data_dir: Path, *, now: str) -> int:
    path = data_dir / "coverage_overrides.json"
    if not path.exists():
        return 0
    try:
        titles = json.loads(path.read_text()).get("covered", [])
    except (ValueError, OSError):
        return 0

    record = load_signoff(data_dir)
    for title in titles:
        for gate in ("variations", "shopify"):
            record = set_gate(
                record, str(title), gate, True,
                by="migrated", at=now, result_count=None, acknowledged_gap=True,
            )
    save_signoff(data_dir, record)
    return len(titles)


if __name__ == "__main__":
    n = migrate(DATA_DIR, now=datetime.now(UTC).isoformat())
    print(f"Migrated {n} override title(s) into coverage_signoff.json")
    sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_migrate_coverage_overrides.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Run the migration for real, then remove the legacy file**

```bash
uv run python scripts/migrate_coverage_overrides.py
cat docs/sales/data/coverage_signoff.json
git rm docs/sales/data/coverage_overrides.json
```

- [ ] **Step 6: Confirm no references to the removed file remain**

Run: `grep -rn "coverage_overrides\|load_overrides" backend/ tests/ frontend/src/`
Expected: no matches outside `scripts/migrate_coverage_overrides.py`.

- [ ] **Step 7: Lint, test, commit**

```bash
npm run lint
uv run pytest tests/ -q --ignore=tests/qa
git add scripts/migrate_coverage_overrides.py tests/test_migrate_coverage_overrides.py \
        docs/sales/data/coverage_signoff.json
git commit -m "feat: migrate coverage overrides into the sign-off record"
```

---

### Task 6: Frontend types and API client

**Files:**
- Modify: `frontend/src/types.ts:118-132`
- Modify: `frontend/src/api.ts`

**Interfaces:**
- Consumes: the API from Task 4
- Produces: `setCanonicalProject`, `setExclusions`, `setSignoff` in `api.ts`; `CoverageGap` and extended `CoverageProduct`/`CoverageCategory` in `types.ts`

- [ ] **Step 1: Extend the types**

In `frontend/src/types.ts`, replace `CoverageProduct` and `CoverageCategory`:

```ts
export interface CoverageGap {
  expected: number;
  generated: number;
  missing: string[];
  excluded: string[];
}

export interface CoverageProduct {
  title: string;
  net_sales: number;
  quantity: number;
  covered: boolean;
  matched_project_ids: string[];
  approved_count: number;
  approved_total: number;
  on_shopify: boolean | null;
  variations_complete: boolean;
  in_shopify: boolean;
  canonical_project_id: string | null;
  excluded_colors: string[];
  gap: CoverageGap | null;
  stale: boolean;
}

export interface CoverageCategory {
  key: string;
  label: string;
  covered: number;
  total: number;
  variations_complete: number;
  in_shopify_count: number;
  products: CoverageProduct[];
}
```

- [ ] **Step 2: Add the API calls**

Append to `frontend/src/api.ts`, following the existing fetch/error pattern in that file:

```ts
export async function setCanonicalProject(
  title: string,
  projectId: string,
): Promise<CoverageResponse> {
  return request<CoverageResponse>(
    `/api/coverage/${encodeURIComponent(title)}/canonical`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId }) },
  );
}

export async function setExclusions(
  title: string,
  colors: string[],
): Promise<CoverageResponse> {
  return request<CoverageResponse>(
    `/api/coverage/${encodeURIComponent(title)}/exclusions`,
    { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ colors }) },
  );
}

export async function setSignoff(
  title: string,
  gate: 'variations' | 'shopify',
  value: boolean,
  acknowledgeGap = false,
): Promise<CoverageResponse> {
  return request<CoverageResponse>(
    `/api/coverage/${encodeURIComponent(title)}/signoff`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gate, value, acknowledge_gap: acknowledgeGap }) },
  );
}
```

If `api.ts` has no shared `request` helper, copy the exact fetch-and-throw shape used by the neighbouring functions in that file instead of inventing one.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: PASS. Errors here mean a field name drifted from Task 3 — fix to match the backend, not the other way round.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: add coverage sign-off types and API client"
```

---

### Task 7: Sign-off panel UI

**Files:**
- Create: `frontend/src/components/ProductSignoffPanel.tsx`
- Modify: `frontend/src/components/CoverageTable.tsx`
- Modify: `frontend/src/components/CoveragePage.tsx`

**Interfaces:**
- Consumes: Task 6's `api.setCanonicalProject`, `api.setExclusions`, `api.setSignoff`; `CoverageProduct`, `CoverageGap`
- Produces: `<ProductSignoffPanel product={...} projects={...} palette={...} onChanged={(r: CoverageResponse) => void} />`

- [ ] **Step 1: Create the panel**

Create `frontend/src/components/ProductSignoffPanel.tsx`:

```tsx
// Per-product sign-off: canonical project, palette checklist, two gates.
// Coverage is decided ONLY by the two gates here — the palette grid is
// evidence to make that judgment fast, never an input to it.
import { useState } from 'react';
import type { CoverageProduct, CoverageResponse, Project } from '../types';
import * as api from '../api';

interface Props {
  product: CoverageProduct;
  projects: Project[];
  onChanged: (r: CoverageResponse) => void;
}

export default function ProductSignoffPanel({ product, projects, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const candidates = projects.filter((p) => product.matched_project_ids.includes(p.id));

  const run = async (fn: () => Promise<CoverageResponse>) => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await fn());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setBusy(false);
    }
  };

  const signoff = (gate: 'variations' | 'shopify', value: boolean) =>
    run(async () => {
      try {
        return await api.setSignoff(product.title, gate, value);
      } catch (err) {
        // 409 = colours still missing. Confirm, then re-send acknowledged.
        const msg = err instanceof Error ? err.message : '';
        if (gate === 'variations' && value && msg && window.confirm(`${msg}\n\nSign off anyway?`)) {
          return api.setSignoff(product.title, gate, value, true);
        }
        throw err;
      }
    });

  const toggleColor = (color: string) => {
    const next = product.excluded_colors.includes(color)
      ? product.excluded_colors.filter((c) => c !== color)
      : [...product.excluded_colors, color];
    return run(() => api.setExclusions(product.title, next));
  };

  return (
    <div style={{ padding: '0.75rem', background: 'rgba(0,0,0,0.03)' }}>
      {error && <div className="status-error">{error}</div>}
      {product.stale && (
        <div className="status-info">
          The canonical project changed since sign-off. Re-check and sign off again.
        </div>
      )}

      <label style={{ display: 'block', marginBottom: '0.5rem' }}>
        Canonical project:{' '}
        <select
          value={product.canonical_project_id ?? ''}
          disabled={busy}
          onChange={(e) => run(() => api.setCanonicalProject(product.title, e.target.value))}
        >
          <option value="" disabled>Pick one…</option>
          {candidates.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({new Set(p.results.map((r) => r.wood_name)).size} colors)
            </option>
          ))}
        </select>
      </label>

      {product.gap ? (
        <>
          <div style={{ fontSize: '0.85rem', marginBottom: '0.35rem' }}>
            {product.gap.generated}/{product.gap.expected} generated
            {product.gap.missing.length > 0 && (
              <> — missing: {product.gap.missing.join(', ')}</>
            )}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.25rem' }}>
            {[...product.gap.missing, ...product.gap.excluded].sort().map((color) => {
              const excluded = product.excluded_colors.includes(color);
              return (
                <button
                  key={color}
                  disabled={busy}
                  onClick={() => toggleColor(color)}
                  title={excluded ? 'Marked not needed — click to require' : 'Click to mark not needed'}
                  style={{
                    fontSize: '0.75rem',
                    padding: '0.1rem 0.4rem',
                    opacity: excluded ? 0.45 : 1,
                    textDecoration: excluded ? 'line-through' : 'none',
                  }}
                >
                  {color}
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <div className="status-info">
          Pick a canonical project to see which colors are missing.
        </div>
      )}

      <div style={{ marginTop: '0.6rem', display: 'flex', gap: '1rem' }}>
        <label>
          <input
            type="checkbox"
            checked={product.variations_complete}
            disabled={busy}
            onChange={(e) => signoff('variations', e.target.checked)}
          />{' '}
          All variations generated
        </label>
        <label>
          <input
            type="checkbox"
            checked={product.in_shopify}
            disabled={busy}
            onChange={(e) => signoff('shopify', e.target.checked)}
          />{' '}
          Uploaded to Shopify
        </label>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Make rows expandable in `CoverageTable.tsx`**

Add local expansion state and a disclosure cell. Keep the component presentational otherwise — it receives `projects` and `onChanged` as props and passes them straight through:

```tsx
const [expanded, setExpanded] = useState<string | null>(null);
```

In the row body, add a leading cell `<td><button onClick={() => setExpanded(expanded === product.title ? null : product.title)}>{expanded === product.title ? '▾' : '▸'}</button></td>`, and after each `<tr>` render:

```tsx
{expanded === product.title && (
  <tr>
    <td colSpan={6}>
      <ProductSignoffPanel product={product} projects={projects} onChanged={onChanged} />
    </td>
  </tr>
)}
```

Change the header summary from one count to two:

```tsx
<h3 style={{ margin: 0 }}>
  {category.variations_complete} / {category.total} variations complete
  {' · '}
  {category.in_shopify_count} / {category.total} in Shopify
</h3>
```

Set the progress bar `pct` from `category.variations_complete`. Update `onlyUncovered` to filter on `!p.variations_complete`.

- [ ] **Step 3: Pass projects through from `CoveragePage.tsx`**

`CoveragePage` already fetches coverage; give it the project list from `ProjectsContext` (the same source `DoorLibrary` uses) and pass both `projects` and an `onChanged` callback that replaces coverage state with the response, into each `CoverageTable`.

- [ ] **Step 4: Typecheck and build**

Run: `cd frontend && npx tsc -b && cd .. && npm run build`
Expected: both succeed.

- [ ] **Step 5: Lint**

Run: `cd frontend && npx eslint src/components/ProductSignoffPanel.tsx src/components/CoverageTable.tsx src/components/CoveragePage.tsx`
Expected: clean.

- [ ] **Step 6: Manual smoke test**

Run `npm run dev`, open the Coverage page, and confirm:
1. Every row starts unsigned except the five migrated titles.
2. Expanding a row shows the canonical picker with per-project colour counts.
3. Picking a canonical renders the palette grid and a missing-colour list.
4. Ticking "All variations generated" with colours missing prompts to confirm, and signs off after confirming.
5. Header shows both counts, and they change as you tick.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ProductSignoffPanel.tsx \
        frontend/src/components/CoverageTable.tsx \
        frontend/src/components/CoveragePage.tsx
git commit -m "feat: add per-product sign-off panel to the coverage page"
```

---

## Self-Review Notes

**Spec coverage:** data model → Task 1; computed gap → Task 2; coverage rule and two headline numbers → Task 3; three endpoints and the 409 gap guard → Task 4; migration and `load_overrides` removal → Task 5; frontend contract → Task 6; panel, palette grid, staleness banner, canonical picker → Task 7. Merging the advisory branch → Task 0.

**Deliberately deferred to execution:** the exact `request` helper name in `api.ts` and the exact shape of the branch's approval/Shopify helpers in `coverage.py` — both are read from the merged code in Task 0 rather than guessed here. Task 3 Step 4 and Task 6 Step 2 each say what to do if the shape differs.

**Known gap:** no automated frontend test exists in this repo (no vitest), so Task 7 verifies via typecheck, build, lint, and the explicit manual checklist in Step 6.
