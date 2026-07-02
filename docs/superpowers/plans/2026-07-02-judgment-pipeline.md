# Judgment Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a calibrated QA judge that classifies generated cabinet-door images as pass / regenerate / needs-human, measured against Jonny's real accept/reject labels.

**Architecture:** A `backend/qa/` package with six small modules (labels, corpus, thumbs, sheet, judge, policy, eval, report) plus thin CLI scripts in `scripts/`. Ground truth is labeled first via a local contact-sheet web UI over the existing `output/.projects/` data; an eval harness then scores the LLM vision judge before it is trusted. Spec: `docs/superpowers/specs/2026-07-02-judgment-pipeline-design.md`.

**Tech Stack:** Python 3.12, google-genai (Gemini vision), Pillow, stdlib `http.server`, pytest, uv.

## Global Constraints

- Python ≥3.12; run everything with `uv run` (e.g. `uv run pytest`, `uv run python scripts/qa_label.py`).
- **No new dependencies.** Only stdlib + existing deps: `google-genai`, `pillow`, `numpy`, `python-dotenv`, `fastapi` (unused here), `pytest`.
- Ruff: line length 100, rules `E,F,I,UP,B,SIM`, py312 syntax (`X | None`, no `Optional`). Run `uv run ruff check backend/qa scripts tests/qa` before each commit.
- All QA state lives under `output/.qa/` (gitignored with the rest of `output/`): `labels.json`, `verdicts/`, `site/`, `eval_report.json`, `review.html`.
- **Never modify or delete anything inside `output/.projects/`** — projects and signatures are irreplaceable. All QA code treats it as read-only.
- Candidate key format everywhere: `"{project_id}:{version}:{kind}:{index}"` where version `0` = current, `kind` ∈ `replica|variant`, index `-1` for replicas.
- Reason vocabulary (fixed): `geometry_drift`, `profile_character`, `material_realism`, `artifacts`, `other`.
- Commit style: conventional commits ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Label store

**Files:**
- Create: `backend/qa/__init__.py` (empty)
- Create: `backend/qa/labels.py`
- Test: `tests/qa/test_labels.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Label(key: str, verdict: str, reasons: list[str], notes: str = "")`,
  `REASONS: list[str]`, and `LabelStore(path: Path)` with `.set(label) -> None` (upsert +
  save), `.get(key) -> Label | None`, `.all() -> list[Label]`. Persists to JSON at `path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_labels.py
from pathlib import Path

import pytest

from backend.qa.labels import Label, LabelStore


def test_label_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    store = LabelStore(path)
    store.set(Label(key="p1:0:variant:3", verdict="reject", reasons=["geometry_drift"]))
    store.set(Label(key="p1:0:replica:-1", verdict="accept"))

    reloaded = LabelStore(path)
    got = reloaded.get("p1:0:variant:3")
    assert got is not None
    assert got.verdict == "reject"
    assert got.reasons == ["geometry_drift"]
    assert len(reloaded.all()) == 2


def test_label_store_upsert_replaces(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels.json")
    store.set(Label(key="k1", verdict="reject", reasons=["artifacts"]))
    store.set(Label(key="k1", verdict="accept"))
    got = store.get("k1")
    assert got is not None
    assert got.verdict == "accept"
    assert got.reasons == []


def test_label_store_rejects_bad_input(tmp_path: Path) -> None:
    store = LabelStore(tmp_path / "labels.json")
    with pytest.raises(ValueError):
        store.set(Label(key="k", verdict="maybe"))
    with pytest.raises(ValueError):
        store.set(Label(key="k", verdict="reject", reasons=["too_ugly"]))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_labels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.qa'`

- [ ] **Step 3: Implement**

Create empty `backend/qa/__init__.py`, then:

```python
# backend/qa/labels.py
"""Accept/reject labels for generated images, persisted to JSON."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REASONS = ["geometry_drift", "profile_character", "material_realism", "artifacts", "other"]


@dataclass
class Label:
    key: str  # "{project_id}:{version}:{kind}:{index}"
    verdict: str  # "accept" | "reject"
    reasons: list[str] = field(default_factory=list)
    notes: str = ""


class LabelStore:
    """Load/save labels at ``path``; every ``set`` persists immediately."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._labels: dict[str, Label] = {}
        if path.exists():
            data = json.loads(path.read_text())
            for item in data.get("labels", []):
                label = Label(**item)
                self._labels[label.key] = label

    def set(self, label: Label) -> None:
        if label.verdict not in ("accept", "reject"):
            raise ValueError(f"Invalid verdict: {label.verdict!r}")
        unknown = [r for r in label.reasons if r not in REASONS]
        if unknown:
            raise ValueError(f"Unknown reasons: {unknown}")
        self._labels[label.key] = label
        self._save()

    def get(self, key: str) -> Label | None:
        return self._labels.get(key)

    def all(self) -> list[Label]:
        return list(self._labels.values())

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"labels": [asdict(label) for label in self._labels.values()]}
        self._path.write_text(json.dumps(payload, indent=1))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_labels.py -v`
Expected: 3 PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check backend/qa tests/qa
git add backend/qa tests/qa
git commit -m "feat(qa): label store for calibration accept/reject labels"
```

---

### Task 2: Corpus walker

**Files:**
- Create: `backend/qa/corpus.py`
- Create: `tests/qa/conftest.py`
- Test: `tests/qa/test_corpus.py`

**Interfaces:**
- Consumes: on-disk layout of `output/.projects/<id>/` (`manifest.json`, `upload.bin`,
  `base_door.bin`, `result_N.bin`, `versions/vN/` with `result_names.json` + `meta.json`)
  and `swatches/` (`wood_types.json`, `rtf_types.json`, `wood/`, `rtf/`).
- Produces: `Candidate` dataclass (fields: `key, project_id, project_name, door_style,
  version, kind, index, wood_name, image_path, sample_path, swatch_path, presumed`) and
  `walk_corpus(projects_dir: Path, swatches_dir: Path) -> list[Candidate]`.
  `presumed` is `"accept"` for current results, `"reject"` for archived versions.

- [ ] **Step 1: Write the shared fixtures**

```python
# tests/qa/conftest.py
import json
from pathlib import Path

import pytest

# Minimal JPEG header so magic-byte sniffing sees a JPEG.
JPEG = bytes.fromhex("ffd8ffe000104a46494600") + b"\x00" * 32


@pytest.fixture
def projects_dir(tmp_path: Path) -> Path:
    root = tmp_path / ".projects"
    d = root / "abc123"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "id": "abc123",
                "name": "Shaker Maple",
                "door_style": "shaker",
                "result_names": ["Cherry Natural", "Walnut Select"],
            }
        )
    )
    (d / "upload.bin").write_bytes(JPEG)
    (d / "base_door.bin").write_bytes(JPEG)
    (d / "result_0.bin").write_bytes(JPEG)
    (d / "result_1.bin").write_bytes(JPEG)
    v1 = d / "versions" / "v1"
    v1.mkdir(parents=True)
    (v1 / "base_door.bin").write_bytes(JPEG)
    (v1 / "result_0.bin").write_bytes(JPEG)
    (v1 / "result_names.json").write_text(json.dumps(["Cherry Natural"]))
    (v1 / "meta.json").write_text(
        json.dumps(
            {"version": 1, "created_at": "2026-01-01T00:00:00+00:00", "door_style": "shaker"}
        )
    )
    # A project with no upload.bin (real case: e.g. project c81e6ddf).
    d2 = root / "def456"
    d2.mkdir()
    (d2 / "manifest.json").write_text(
        json.dumps({"id": "def456", "name": "Durango", "result_names": ["Walnut Select"]})
    )
    (d2 / "result_0.bin").write_bytes(JPEG)
    return root


@pytest.fixture
def swatches_dir(tmp_path: Path) -> Path:
    root = tmp_path / "swatches"
    (root / "wood").mkdir(parents=True)
    (root / "wood_types.json").write_text(
        json.dumps(
            {
                "cherry-natural": {"name": "Cherry Natural", "description": ""},
                "walnut-select": {"name": "Walnut Select", "description": ""},
            }
        )
    )
    (root / "rtf_types.json").write_text("{}")
    # Note: underscore filename while slug uses hyphens — mirrors the real swatches/ dir.
    (root / "wood" / "cherry_natural.jpg").write_bytes(JPEG)
    return root
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/qa/test_corpus.py
from pathlib import Path

from backend.qa.corpus import walk_corpus


def test_walk_corpus_enumerates_current_and_versions(
    projects_dir: Path, swatches_dir: Path
) -> None:
    candidates = walk_corpus(projects_dir, swatches_dir)
    by_key = {c.key for c in candidates}
    # abc123 current: replica + 2 variants; v1: replica + 1 variant; def456: 1 variant.
    assert by_key == {
        "abc123:0:replica:-1",
        "abc123:0:variant:0",
        "abc123:0:variant:1",
        "abc123:1:replica:-1",
        "abc123:1:variant:0",
        "def456:0:variant:0",
    }


def test_presumed_verdicts(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    assert candidates["abc123:0:variant:0"].presumed == "accept"
    assert candidates["abc123:1:variant:0"].presumed == "reject"


def test_sample_and_swatch_resolution(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    cherry = candidates["abc123:0:variant:0"]
    assert cherry.wood_name == "Cherry Natural"
    assert cherry.sample_path is not None and cherry.sample_path.name == "upload.bin"
    assert cherry.swatch_path is not None and cherry.swatch_path.name == "cherry_natural.jpg"
    # Walnut Select has no swatch image on disk -> None, not an error.
    walnut = candidates["abc123:0:variant:1"]
    assert walnut.swatch_path is None
    # def456 has no upload.bin -> sample_path None, still enumerated.
    assert candidates["def456:0:variant:0"].sample_path is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_corpus.py -v`
Expected: FAIL with `ModuleNotFoundError` (no `backend.qa.corpus`)

- [ ] **Step 4: Implement**

```python
# backend/qa/corpus.py
"""Read-only walker over output/.projects: enumerate generated images + references."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Candidate:
    key: str  # "{project_id}:{version}:{kind}:{index}"
    project_id: str
    project_name: str
    door_style: str | None
    version: int  # 0 = current, N = versions/vN
    kind: str  # "replica" | "variant"
    index: int  # -1 for replica
    wood_name: str | None
    image_path: Path
    sample_path: Path | None  # upload.bin, may be missing
    swatch_path: Path | None
    presumed: str  # "accept" (current) | "reject" (archived version)


def _swatch_index(swatches_dir: Path) -> dict[str, Path]:
    """Map lowercased display name -> swatch image path, tolerant of filename drift."""
    index: dict[str, Path] = {}
    for json_name, img_subdir in (("wood_types.json", "wood"), ("rtf_types.json", "rtf")):
        types_path = swatches_dir / json_name
        if not types_path.exists():
            continue
        try:
            types = json.loads(types_path.read_text())
        except json.JSONDecodeError:
            continue
        for slug, info in types.items():
            name = str(info.get("name", slug)).lower()
            for filename in (
                f"{slug.replace('-', '_')}.jpg",
                f"{slug}.jpg",
                f"{slug}-new.png",
                f"{slug.replace('-', '_')}.png",
                f"{slug}.png",
            ):
                path = swatches_dir / img_subdir / filename
                if path.exists():
                    index[name] = path
                    break
    return index


def walk_corpus(projects_dir: Path, swatches_dir: Path) -> list[Candidate]:
    swatch_by_name = _swatch_index(swatches_dir)
    candidates: list[Candidate] = []
    if not projects_dir.exists():
        return candidates
    for d in sorted(projects_dir.iterdir()):
        manifest_path = d / "manifest.json"
        if not d.is_dir() or not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError:
            continue
        pid = manifest.get("id", d.name)
        name = manifest.get("name", d.name)
        style = manifest.get("door_style")
        upload = d / "upload.bin"
        sample = upload if upload.exists() else None
        candidates.extend(
            _version_candidates(
                d,
                version=0,
                presumed="accept",
                pid=pid,
                name=name,
                style=style,
                sample=sample,
                result_names=manifest.get("result_names", []),
                swatch_by_name=swatch_by_name,
            )
        )
        versions_dir = d / "versions"
        if not versions_dir.exists():
            continue
        for vdir in sorted(versions_dir.iterdir()):
            if not vdir.is_dir() or not vdir.name.startswith("v") or not vdir.name[1:].isdigit():
                continue
            names_path = vdir / "result_names.json"
            result_names = json.loads(names_path.read_text()) if names_path.exists() else []
            vstyle = style
            meta_path = vdir / "meta.json"
            if meta_path.exists():
                try:
                    vstyle = json.loads(meta_path.read_text()).get("door_style", style)
                except json.JSONDecodeError:
                    pass
            candidates.extend(
                _version_candidates(
                    vdir,
                    version=int(vdir.name[1:]),
                    presumed="reject",
                    pid=pid,
                    name=name,
                    style=vstyle,
                    sample=sample,
                    result_names=result_names,
                    swatch_by_name=swatch_by_name,
                )
            )
    return candidates


def _version_candidates(
    base: Path,
    *,
    version: int,
    presumed: str,
    pid: str,
    name: str,
    style: str | None,
    sample: Path | None,
    result_names: list[str],
    swatch_by_name: dict[str, Path],
) -> list[Candidate]:
    out: list[Candidate] = []
    replica = base / "base_door.bin"
    if replica.exists():
        out.append(
            Candidate(
                key=f"{pid}:{version}:replica:-1",
                project_id=pid,
                project_name=name,
                door_style=style,
                version=version,
                kind="replica",
                index=-1,
                wood_name=None,
                image_path=replica,
                sample_path=sample,
                swatch_path=None,
                presumed=presumed,
            )
        )
    for idx, wood_name in enumerate(result_names):
        rpath = base / f"result_{idx}.bin"
        if not rpath.exists():
            continue
        out.append(
            Candidate(
                key=f"{pid}:{version}:variant:{idx}",
                project_id=pid,
                project_name=name,
                door_style=style,
                version=version,
                kind="variant",
                index=idx,
                wood_name=wood_name,
                image_path=rpath,
                sample_path=sample,
                swatch_path=swatch_by_name.get(wood_name.lower()),
                presumed=presumed,
            )
        )
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_corpus.py -v`
Expected: 3 PASS

- [ ] **Step 6: Sanity-check against the real corpus**

Run: `uv run python -c "from pathlib import Path; from backend.qa.corpus import walk_corpus; cs = walk_corpus(Path('output/.projects'), Path('swatches')); print(len(cs), 'candidates'); print(sum(1 for c in cs if c.presumed=='reject'), 'presumed rejects'); print(sum(1 for c in cs if c.sample_path is None), 'missing samples')"`
Expected: thousands of candidates, nonzero presumed rejects, nonzero missing samples. Record the numbers in the commit message.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check backend/qa tests/qa
git add backend/qa/corpus.py tests/qa
git commit -m "feat(qa): corpus walker over projects + version archives"
```

---

### Task 3: Thumbnail export

**Files:**
- Create: `backend/qa/thumbs.py`
- Test: `tests/qa/test_thumbs.py`

**Interfaces:**
- Consumes: any image `Path` (the `.bin` files are plain JPEGs/PNGs).
- Produces: `export_thumb(src: Path, out_dir: Path, max_px: int = 640) -> Path | None` —
  writes a browser-viewable `<sha1-16>.jpg` into `out_dir`, returns its path; returns the
  cached file on repeat calls; returns `None` for unreadable images. Browsers won't render
  `.bin` files from disk, which is why thumbs exist at all.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_thumbs.py
from pathlib import Path

from PIL import Image

from backend.qa.thumbs import export_thumb


def _make_png(path: Path, size: tuple[int, int] = (800, 1400)) -> None:
    Image.new("RGB", size, color=(120, 80, 40)).save(path, "PNG")


def test_export_thumb_resizes_and_caches(tmp_path: Path) -> None:
    src = tmp_path / "door.bin"
    _make_png(src)
    out = tmp_path / "thumbs"

    thumb = export_thumb(src, out, max_px=400)
    assert thumb is not None and thumb.exists() and thumb.suffix == ".jpg"
    with Image.open(thumb) as im:
        assert max(im.size) <= 400

    mtime = thumb.stat().st_mtime_ns
    again = export_thumb(src, out, max_px=400)
    assert again == thumb
    assert again.stat().st_mtime_ns == mtime  # cache hit, not rewritten


def test_export_thumb_unreadable_returns_none(tmp_path: Path) -> None:
    src = tmp_path / "junk.bin"
    src.write_bytes(b"not an image")
    assert export_thumb(src, tmp_path / "thumbs") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_thumbs.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/qa/thumbs.py
"""Export browser-viewable JPEG thumbnails for the .bin images."""

import hashlib
from pathlib import Path

from PIL import Image


def export_thumb(src: Path, out_dir: Path, max_px: int = 640) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(src).encode()).hexdigest()[:16]
    dest = out_dir / f"{digest}.jpg"
    if dest.exists():
        return dest
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(dest, "JPEG", quality=85)
    except OSError:
        return None
    return dest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_thumbs.py -v`
Expected: 2 PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check backend/qa tests/qa
git add backend/qa/thumbs.py tests/qa/test_thumbs.py
git commit -m "feat(qa): thumbnail export for labeling/review UIs"
```

---

### Task 4: Labeling contact sheet + local server

**Files:**
- Create: `backend/qa/sheet.py`
- Create: `scripts/qa_label.py`
- Test: `tests/qa/test_sheet.py`

**Interfaces:**
- Consumes: `Candidate` (Task 2), `LabelStore`/`Label`/`REASONS` (Task 1),
  `export_thumb` (Task 3).
- Produces: `render_index(projects: list[tuple[str, str, int, int]]) -> str` (rows of
  `(project_id, project_name, labeled_count, total_count)`) and
  `render_project_sheet(project_name: str, candidates: list[Candidate],
  labels: LabelStore, thumb_urls: dict[str, dict[str, str]]) -> str` where
  `thumb_urls[key]` maps roles `"img" | "sample" | "swatch"` to relative URLs.
  The server posts `{"key", "verdict", "reasons"}` JSON to `POST /label`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_sheet.py
from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.labels import Label, LabelStore
from backend.qa.sheet import render_index, render_project_sheet


def test_render_project_sheet_contains_cards(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    candidates = [c for c in walk_corpus(projects_dir, swatches_dir) if c.project_id == "abc123"]
    labels = LabelStore(tmp_path / "labels.json")
    labels.set(Label(key="abc123:0:variant:0", verdict="reject", reasons=["artifacts"]))
    thumb_urls = {
        c.key: {"img": f"thumbs/{c.key.replace(':', '_')}.jpg", "sample": "thumbs/s.jpg"}
        for c in candidates
    }
    html_out = render_project_sheet("Shaker Maple", candidates, labels, thumb_urls)
    assert 'data-key="abc123:0:variant:0"' in html_out
    assert 'class="card reject"' in html_out  # explicit label wins over presumed
    assert 'class="card accept"' in html_out  # presumed accept for unlabeled current
    assert "geometry_drift" in html_out  # reason checkboxes present
    assert "Cherry Natural" in html_out


def test_render_index_lists_projects() -> None:
    html_out = render_index([("abc123", "Shaker Maple", 2, 5), ("def456", "Durango", 0, 1)])
    assert "Shaker Maple" in html_out
    assert "2 / 5" in html_out
    assert 'href="project_abc123.html"' in html_out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_sheet.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the renderer**

```python
# backend/qa/sheet.py
"""Render the calibration labeling contact sheets (static HTML + tiny JS)."""

import html

from backend.qa.corpus import Candidate
from backend.qa.labels import REASONS, LabelStore

_CSS = """
body{font-family:system-ui;background:#141414;color:#eee;margin:0;padding:16px}
a{color:#8ab4f8}
.card{display:flex;gap:12px;border:3px solid #444;border-radius:8px;padding:10px;margin:12px 0}
.card.accept{border-color:#2e7d32}
.card.reject{border-color:#c62828}
.card img{max-height:360px;border-radius:4px;background:#000}
.imgs{display:flex;gap:8px;align-items:flex-start}
.imgs figure{margin:0;text-align:center;font-size:12px;color:#aaa}
.meta{min-width:240px}
.reasons label{display:block;font-size:13px;margin:2px 0}
button{padding:6px 14px;margin:4px 6px 4px 0;cursor:pointer;border-radius:4px;border:0}
.b-accept{background:#2e7d32;color:#fff}
.b-reject{background:#c62828;color:#fff}
.savebar{position:sticky;top:0;background:#141414;padding:8px 0;z-index:2}
"""

_JS = """
async function post(key, verdict, reasons){
  await fetch('/label', {method:'POST',
    body: JSON.stringify({key: key, verdict: verdict, reasons: reasons})});
}
function reasonsOf(card){
  return Array.from(card.querySelectorAll('input:checked')).map(i => i.value);
}
async function setLabel(btn, verdict){
  const card = btn.closest('.card');
  card.classList.remove('accept', 'reject');
  card.classList.add(verdict);
  card.dataset.explicit = '1';
  await post(card.dataset.key, verdict, verdict === 'reject' ? reasonsOf(card) : []);
}
async function saveAll(){
  for (const card of document.querySelectorAll('.card')){
    const verdict = card.classList.contains('reject') ? 'reject' : 'accept';
    await post(card.dataset.key, verdict, verdict === 'reject' ? reasonsOf(card) : []);
    card.dataset.explicit = '1';
  }
  document.getElementById('savemsg').textContent = 'All cards on page saved.';
}
"""


def _figure(url: str, caption: str) -> str:
    return f'<figure><img src="{html.escape(url)}" loading="lazy"><figcaption>{html.escape(caption)}</figcaption></figure>'


def render_project_sheet(
    project_name: str,
    candidates: list[Candidate],
    labels: LabelStore,
    thumb_urls: dict[str, dict[str, str]],
) -> str:
    cards: list[str] = []
    for c in candidates:
        label = labels.get(c.key)
        state = label.verdict if label else c.presumed
        checked = set(label.reasons) if label else set()
        urls = thumb_urls.get(c.key, {})
        figs: list[str] = []
        if "sample" in urls:
            figs.append(_figure(urls["sample"], "sample"))
        if "img" in urls:
            figs.append(_figure(urls["img"], c.kind))
        if "swatch" in urls:
            figs.append(_figure(urls["swatch"], "swatch"))
        reason_boxes = "".join(
            f'<label><input type="checkbox" value="{r}"'
            f'{" checked" if r in checked else ""}> {r}</label>'
            for r in REASONS
        )
        title = f"{c.kind} · {c.wood_name or 'base door'}"
        if c.version:
            title += f" · archived v{c.version}"
        no_sample = "" if c.sample_path else "<div>⚠ no sample photo on file</div>"
        cards.append(
            f'<div class="card {state}" data-key="{html.escape(c.key)}">'
            f'<div class="imgs">{"".join(figs)}</div>'
            f'<div class="meta"><h3>{html.escape(title)}</h3>{no_sample}'
            f'<button class="b-accept" onclick="setLabel(this, \'accept\')">Accept</button>'
            f'<button class="b-reject" onclick="setLabel(this, \'reject\')">Reject</button>'
            f'<div class="reasons">{reason_boxes}</div></div></div>'
        )
    return (
        f"<!doctype html><meta charset=utf-8><title>{html.escape(project_name)}</title>"
        f"<style>{_CSS}</style><script>{_JS}</script>"
        f'<div class="savebar"><a href="index.html">← index</a> '
        f"<h2 style=\"display:inline\">{html.escape(project_name)}</h2> "
        f'<button onclick="saveAll()">Save all on page</button> <span id="savemsg"></span></div>'
        f'{"".join(cards)}'
    )


def render_index(projects: list[tuple[str, str, int, int]]) -> str:
    rows = "".join(
        f'<li><a href="project_{html.escape(pid)}.html">{html.escape(name)}</a>'
        f" — {labeled} / {total} labeled</li>"
        for pid, name, labeled, total in projects
    )
    return (
        "<!doctype html><meta charset=utf-8><title>QA labeling</title>"
        f"<style>{_CSS}</style><h1>Calibration labeling</h1>"
        "<p>Current results default to <b>accept</b>, archived versions to <b>reject</b>. "
        "Flip the exceptions, tick reasons on rejects, then “Save all on page”.</p>"
        f"<ul>{rows}</ul>"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_sheet.py -v`
Expected: 2 PASS

- [ ] **Step 5: Write the server script**

```python
# scripts/qa_label.py
"""Serve the calibration labeling UI.

Usage:
    uv run python scripts/qa_label.py [--port 8777] [--project PROJECT_ID]

Builds a static site under output/.qa/site/ (thumbnails cached across runs), then serves
it locally. Accept/Reject clicks persist immediately to output/.qa/labels.json.
"""

import argparse
import json
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from backend.qa.corpus import Candidate, walk_corpus
from backend.qa.labels import Label, LabelStore
from backend.qa.sheet import render_index, render_project_sheet
from backend.qa.thumbs import export_thumb

QA_DIR = Path("output/.qa")
SITE_DIR = QA_DIR / "site"
THUMBS_DIR = SITE_DIR / "thumbs"


def build_site(candidates: list[Candidate], labels: LabelStore) -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    by_project: dict[str, list[Candidate]] = {}
    names: dict[str, str] = {}
    for c in candidates:
        by_project.setdefault(c.project_id, []).append(c)
        names[c.project_id] = c.project_name

    index_rows: list[tuple[str, str, int, int]] = []
    for pid, cands in sorted(by_project.items(), key=lambda kv: names[kv[0]].lower()):
        thumb_urls: dict[str, dict[str, str]] = {}
        for c in cands:
            urls: dict[str, str] = {}
            for role, src in (("img", c.image_path), ("sample", c.sample_path),
                              ("swatch", c.swatch_path)):
                if src is None:
                    continue
                thumb = export_thumb(src, THUMBS_DIR)
                if thumb is not None:
                    urls[role] = f"thumbs/{thumb.name}"
            thumb_urls[c.key] = urls
        page = render_project_sheet(names[pid], cands, labels, thumb_urls)
        (SITE_DIR / f"project_{pid}.html").write_text(page)
        labeled = sum(1 for c in cands if labels.get(c.key) is not None)
        index_rows.append((pid, names[pid], labeled, len(cands)))
    (SITE_DIR / "index.html").write_text(render_index(index_rows))


class LabelHandler(SimpleHTTPRequestHandler):
    store: LabelStore  # set on the class before serving

    def do_POST(self) -> None:  # noqa: N802 (stdlib API name)
        if self.path != "/label":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length))
        self.store.set(
            Label(key=data["key"], verdict=data["verdict"], reasons=data.get("reasons", []))
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: object) -> None:  # keep the terminal quiet
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--project", help="rebuild/serve only this project id")
    args = parser.parse_args()

    labels = LabelStore(QA_DIR / "labels.json")
    candidates = walk_corpus(Path("output/.projects"), Path("swatches"))
    if args.project:
        candidates = [c for c in candidates if c.project_id == args.project]
    print(f"Building site for {len(candidates)} images (thumbnails cached across runs)...")
    build_site(candidates, labels)

    LabelHandler.store = labels
    handler = partial(LabelHandler, directory=str(SITE_DIR))
    server = HTTPServer(("127.0.0.1", args.port), handler)
    print(f"Labeling UI: http://127.0.0.1:{args.port}/index.html  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Smoke-test the server manually**

Run: `uv run python scripts/qa_label.py --port 8777 --project <any real project id from output/.projects>` then in another shell:
`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8777/index.html` → expect `200`;
`curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8777/label -d '{"key":"smoke:0:variant:0","verdict":"accept","reasons":[]}'` → expect `204`;
`grep -c smoke output/.qa/labels.json` → expect `1`. Stop the server. Remove the smoke label: edit `output/.qa/labels.json` and delete the `smoke:0:variant:0` entry.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check backend/qa scripts tests/qa
git add backend/qa/sheet.py scripts/qa_label.py tests/qa/test_sheet.py
git commit -m "feat(qa): side-by-side labeling UI with local save server"
```

---

### Task 5: LLM vision judge

**Files:**
- Create: `backend/qa/judge.py`
- Test: `tests/qa/test_judge.py`

**Interfaces:**
- Consumes: `Candidate` (Task 2); `google.genai` client (same library `generator.py` uses).
- Produces: `JudgeResult(key, panel_layout_match, proportions_match,
  profile_character_match, material_realism, swatch_fidelity, artifacts: list[str],
  verdict: str, confidence: str, reason: str, votes: int = 1)` where `verdict` ∈
  `pass|fail|error`, `confidence` ∈ `high|low`; and
  `VisionJudge(api_key, model=DEFAULT_MODEL, cache_dir=..., client=None)` with
  `.judge(candidate) -> JudgeResult` (disk-cached by key + config hash) and
  `.config_hash() -> str`. Pass `client=` to inject a fake in tests.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_judge.py
import json
from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.judge import VisionJudge


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)
        self.calls = 0

    def generate_content(self, *, model: str, contents: object, config: object = None):
        self.calls += 1
        return FakeResponse(self.texts.pop(0))


class FakeClient:
    def __init__(self, texts: list[str]) -> None:
        self.models = FakeModels(texts)


GOOD = json.dumps(
    {
        "panel_layout_match": 5, "proportions_match": 5, "profile_character_match": 4,
        "material_realism": 5, "swatch_fidelity": 5, "artifacts": [],
        "verdict": "pass", "confidence": "high", "reason": "matches sample",
    }
)
LOW_FAIL = GOOD.replace('"high"', '"low"').replace('"pass"', '"fail"')


def _candidate(projects_dir: Path, swatches_dir: Path):
    return next(
        c for c in walk_corpus(projects_dir, swatches_dir) if c.key == "abc123:0:variant:0"
    )


def test_judge_parses_and_caches(projects_dir: Path, swatches_dir: Path, tmp_path: Path) -> None:
    client = FakeClient([GOOD])
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    c = _candidate(projects_dir, swatches_dir)

    result = judge.judge(c)
    assert result.verdict == "pass" and result.confidence == "high"
    assert result.panel_layout_match == 5

    again = judge.judge(c)  # would raise IndexError if it hit the fake again
    assert again.verdict == "pass"
    assert client.models.calls == 1


def test_low_confidence_triggers_majority_vote(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    client = FakeClient([LOW_FAIL, LOW_FAIL, GOOD])  # 2 fail votes of 3 -> fail
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    result = judge.judge(_candidate(projects_dir, swatches_dir))
    assert client.models.calls == 3
    assert result.verdict == "fail"
    assert result.votes == 3


def test_unparseable_response_yields_error_verdict(
    projects_dir: Path, swatches_dir: Path, tmp_path: Path
) -> None:
    client = FakeClient(["not json at all"] * 3)
    judge = VisionJudge(api_key="x", cache_dir=tmp_path / "verdicts", client=client)
    result = judge.judge(_candidate(projects_dir, swatches_dir))
    assert result.verdict == "error"
    assert result.confidence == "low"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_judge.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/qa/judge.py
"""LLM vision judge: compare a generated image against its sample photo and swatch."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from google import genai
from google.genai import types

from backend.qa.corpus import Candidate

DEFAULT_MODEL = "gemini-3-pro-preview"

RUBRIC_PROMPT = """You are a strict quality inspector for AI-generated cabinet door product images.
The first image is the customer's SAMPLE photo of the real door.{swatch_line}
The LAST image is the AI-GENERATED {kind} being judged.

Decide whether the generated image is usable as a product photo of the SAME door design{material_line}.
Be strict: subtle geometry or profile changes make an image unusable.

Score each criterion 1-5 (5 = indistinguishable from the sample, 1 = clearly wrong):
- panel_layout_match: same count and arrangement of panels, stiles, rails
- proportions_match: stile/rail widths and panel proportions match the sample
- profile_character_match: edge profile, bevels, routing detail read as the same product
- material_realism: wood grain and finish look photographically real, plausible grain direction
- swatch_fidelity: color and species match the swatch image (score 5 if no swatch was provided)

Also list artifacts you see: warping, added or removed hardware, changed corners, blur,
text or watermark remnants, inconsistent lighting or shadows.

Reply with ONLY a JSON object, no markdown fences:
{{"panel_layout_match": n, "proportions_match": n, "profile_character_match": n,
"material_realism": n, "swatch_fidelity": n, "artifacts": ["..."],
"verdict": "pass" or "fail", "confidence": "high" or "low", "reason": "one sentence"}}"""


@dataclass
class JudgeResult:
    key: str
    panel_layout_match: int = 0
    proportions_match: int = 0
    profile_character_match: int = 0
    material_realism: int = 0
    swatch_fidelity: int = 0
    artifacts: list[str] = field(default_factory=list)
    verdict: str = "error"  # "pass" | "fail" | "error"
    confidence: str = "low"  # "high" | "low"
    reason: str = ""
    votes: int = 1


def _mime(data: bytes) -> str:
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def _image_part(path: Path) -> types.Part:
    data = path.read_bytes()
    return types.Part.from_bytes(data=data, mime_type=_mime(data))


class VisionJudge:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        cache_dir: Path = Path("output/.qa/verdicts"),
        client: object | None = None,
    ) -> None:
        self.client = client or genai.Client(api_key=api_key)
        self.model = model
        self.cache_dir = cache_dir

    def config_hash(self) -> str:
        return hashlib.sha256(f"{self.model}|{RUBRIC_PROMPT}".encode()).hexdigest()[:12]

    def _cache_path(self, key: str) -> Path:
        safe = key.replace(":", "_")
        return self.cache_dir / self.config_hash() / f"{safe}.json"

    def judge(self, candidate: Candidate) -> JudgeResult:
        cache = self._cache_path(candidate.key)
        if cache.exists():
            return JudgeResult(**json.loads(cache.read_text()))

        result = self._judge_once(candidate)
        if result.verdict != "error" and result.confidence == "low":
            votes = [result, self._judge_once(candidate), self._judge_once(candidate)]
            fails = sum(1 for v in votes if v.verdict in ("fail", "error"))
            result.verdict = "fail" if fails >= 2 else "pass"
            result.confidence = "high" if fails in (0, 3) else "low"
            result.votes = 3

        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(asdict(result)))
        return result

    def _judge_once(self, candidate: Candidate) -> JudgeResult:
        prompt = RUBRIC_PROMPT.format(
            swatch_line=(
                "\nThe middle image is the target WOOD SWATCH for this variant."
                if candidate.swatch_path
                else ""
            ),
            kind=candidate.kind,
            material_line=(
                f" rendered in {candidate.wood_name}" if candidate.wood_name else ""
            ),
        )
        parts: list[types.Part] = []
        if candidate.sample_path is not None:
            parts.append(_image_part(candidate.sample_path))
        if candidate.swatch_path is not None:
            parts.append(_image_part(candidate.swatch_path))
        parts.append(_image_part(candidate.image_path))
        parts.append(types.Part.from_text(text=prompt))
        contents = [types.Content(role="user", parts=parts)]

        last_error = ""
        for _ in range(3):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=contents
                )
                return self._parse(candidate.key, response.text or "")
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = f"unparseable response: {exc}"
            except Exception as exc:  # network/API errors -> retry then error verdict
                last_error = f"api error: {exc}"
        return JudgeResult(key=candidate.key, verdict="error", reason=last_error)

    def _parse(self, key: str, text: str) -> JudgeResult:
        cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        data = json.loads(cleaned)
        if data.get("verdict") not in ("pass", "fail"):
            raise ValueError(f"bad verdict: {data.get('verdict')!r}")
        return JudgeResult(
            key=key,
            panel_layout_match=int(data["panel_layout_match"]),
            proportions_match=int(data["proportions_match"]),
            profile_character_match=int(data["profile_character_match"]),
            material_realism=int(data["material_realism"]),
            swatch_fidelity=int(data["swatch_fidelity"]),
            artifacts=[str(a) for a in data.get("artifacts", [])],
            verdict=data["verdict"],
            confidence=data.get("confidence", "low"),
            reason=str(data.get("reason", "")),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_judge.py -v`
Expected: 3 PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check backend/qa tests/qa
git add backend/qa/judge.py tests/qa/test_judge.py
git commit -m "feat(qa): LLM vision judge with rubric, majority vote, disk cache"
```

---

### Task 6: Decision policy

**Files:**
- Create: `backend/qa/policy.py`
- Create: `backend/qa/policy_config.json`
- Test: `tests/qa/test_policy.py`

**Interfaces:**
- Consumes: `JudgeResult` (Task 5), `Candidate` (Task 2).
- Produces: `Decision(key: str, verdict: str, reason: str)` with `verdict` ∈
  `pass|regenerate|needs_human`; `PolicyConfig(min_score: int, untrusted_styles:
  list[str])`; `load_policy(path: Path) -> PolicyConfig`;
  `decide(result: JudgeResult, candidate: Candidate, config: PolicyConfig) -> Decision`.
  Default config file: `backend/qa/policy_config.json`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_policy.py
from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult
from backend.qa.policy import PolicyConfig, decide, load_policy


def _candidate(style: str | None = "shaker") -> Candidate:
    return Candidate(
        key="p:0:variant:0", project_id="p", project_name="P", door_style=style,
        version=0, kind="variant", index=0, wood_name="Cherry Natural",
        image_path=Path("x.bin"), sample_path=None, swatch_path=None, presumed="accept",
    )


def _result(**overrides: object) -> JudgeResult:
    base = dict(
        key="p:0:variant:0", panel_layout_match=5, proportions_match=5,
        profile_character_match=5, material_realism=5, swatch_fidelity=5,
        artifacts=[], verdict="pass", confidence="high", reason="ok",
    )
    base.update(overrides)
    return JudgeResult(**base)  # type: ignore[arg-type]


CONFIG = PolicyConfig(min_score=4, untrusted_styles=["applied_molding"])


def test_high_confidence_pass() -> None:
    assert decide(_result(), _candidate(), CONFIG).verdict == "pass"


def test_fail_verdict_regenerates() -> None:
    d = decide(_result(verdict="fail", reason="stiles wider"), _candidate(), CONFIG)
    assert d.verdict == "regenerate"
    assert "stiles wider" in d.reason


def test_low_score_regenerates_even_if_judge_said_pass() -> None:
    d = decide(_result(proportions_match=3), _candidate(), CONFIG)
    assert d.verdict == "regenerate"


def test_low_confidence_pass_needs_human() -> None:
    d = decide(_result(confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_error_needs_human() -> None:
    d = decide(_result(verdict="error", confidence="low"), _candidate(), CONFIG)
    assert d.verdict == "needs_human"


def test_untrusted_style_needs_human_regardless() -> None:
    d = decide(_result(), _candidate(style="applied_molding"), CONFIG)
    assert d.verdict == "needs_human"


def test_load_policy_default_file() -> None:
    config = load_policy(Path("backend/qa/policy_config.json"))
    assert config.min_score >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_policy.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/qa/policy.py
"""Turn a JudgeResult into pass / regenerate / needs_human. Fail-safe: doubt -> human."""

import json
from dataclasses import dataclass, field
from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult

DEFAULT_POLICY_PATH = Path("backend/qa/policy_config.json")


@dataclass
class PolicyConfig:
    min_score: int = 4
    untrusted_styles: list[str] = field(default_factory=list)


@dataclass
class Decision:
    key: str
    verdict: str  # "pass" | "regenerate" | "needs_human"
    reason: str


def load_policy(path: Path = DEFAULT_POLICY_PATH) -> PolicyConfig:
    data = json.loads(path.read_text())
    return PolicyConfig(
        min_score=int(data.get("min_score", 4)),
        untrusted_styles=list(data.get("untrusted_styles", [])),
    )


def decide(result: JudgeResult, candidate: Candidate, config: PolicyConfig) -> Decision:
    if candidate.door_style in config.untrusted_styles:
        return Decision(result.key, "needs_human", f"untrusted style: {candidate.door_style}")
    if result.verdict == "error":
        return Decision(result.key, "needs_human", f"judge error: {result.reason}")
    scores = {
        "panel_layout_match": result.panel_layout_match,
        "proportions_match": result.proportions_match,
        "profile_character_match": result.profile_character_match,
        "material_realism": result.material_realism,
        "swatch_fidelity": result.swatch_fidelity,
    }
    low = [f"{name}={value}" for name, value in scores.items() if value < config.min_score]
    if result.verdict == "fail" or low:
        detail = result.reason or "judge fail"
        if low:
            detail += f" (low scores: {', '.join(low)})"
        return Decision(result.key, "regenerate", detail)
    if result.confidence == "low":
        return Decision(result.key, "needs_human", "low judge confidence")
    return Decision(result.key, "pass", result.reason)
```

Create `backend/qa/policy_config.json` with exactly:

```json
{
  "min_score": 4,
  "untrusted_styles": []
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_policy.py -v`
Expected: 7 PASS

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check backend/qa tests/qa
git add backend/qa/policy.py backend/qa/policy_config.json tests/qa/test_policy.py
git commit -m "feat(qa): decision policy with untrusted-style routing"
```

---

### Task 7: Eval harness + CLI

**Files:**
- Create: `backend/qa/eval.py`
- Create: `scripts/qa_eval.py`
- Test: `tests/qa/test_eval.py`

**Interfaces:**
- Consumes: `Label`/`LabelStore` (Task 1), `Candidate` (Task 2), `VisionJudge` (Task 5),
  `decide`/`load_policy` (Task 6).
- Produces: `is_holdout(project_id: str) -> bool` (deterministic ~20% split by project);
  `EvalMetrics(n, n_rejects, n_accepts, reject_recall, false_flag_rate,
  recall_by_reason: dict[str, tuple[int, int]], by_style: dict[str, dict[str, float]])`;
  `evaluate(labels: list[Label], decisions: dict[str, Decision],
  candidates: dict[str, Candidate], holdout_only: bool = False) -> EvalMetrics`.
  "Flagged" = decision verdict != "pass". A true reject is *caught* iff flagged.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_eval.py
from pathlib import Path

from backend.qa.corpus import Candidate
from backend.qa.eval import evaluate, is_holdout
from backend.qa.labels import Label
from backend.qa.policy import Decision


def _candidate(key: str, style: str = "shaker") -> Candidate:
    pid = key.split(":")[0]
    return Candidate(
        key=key, project_id=pid, project_name=pid, door_style=style, version=0,
        kind="variant", index=0, wood_name="Cherry Natural", image_path=Path("x.bin"),
        sample_path=None, swatch_path=None, presumed="accept",
    )


def test_is_holdout_deterministic_and_partial() -> None:
    ids = [f"proj{i}" for i in range(200)]
    first = [is_holdout(i) for i in ids]
    assert first == [is_holdout(i) for i in ids]  # stable
    frac = sum(first) / len(first)
    assert 0.05 < frac < 0.4  # roughly a fifth


def test_evaluate_recall_and_false_flags() -> None:
    labels = [
        Label(key="a:0:variant:0", verdict="reject", reasons=["geometry_drift"]),
        Label(key="a:0:variant:1", verdict="reject", reasons=["artifacts"]),
        Label(key="a:0:variant:2", verdict="accept"),
        Label(key="a:0:variant:3", verdict="accept"),
    ]
    decisions = {
        "a:0:variant:0": Decision("a:0:variant:0", "regenerate", "bad geometry"),  # caught
        "a:0:variant:1": Decision("a:0:variant:1", "pass", "looks fine"),  # MISSED reject
        "a:0:variant:2": Decision("a:0:variant:2", "pass", "ok"),  # correct pass
        "a:0:variant:3": Decision("a:0:variant:3", "needs_human", "low conf"),  # false flag
    }
    candidates = {label.key: _candidate(label.key) for label in labels}
    m = evaluate(labels, decisions, candidates)
    assert m.n == 4 and m.n_rejects == 2 and m.n_accepts == 2
    assert m.reject_recall == 0.5
    assert m.false_flag_rate == 0.5
    assert m.recall_by_reason["geometry_drift"] == (1, 1)
    assert m.recall_by_reason["artifacts"] == (0, 1)
    assert "shaker" in m.by_style
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/qa/test_eval.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the metrics module**

```python
# backend/qa/eval.py
"""Score a judge+policy configuration against human labels."""

import hashlib
from dataclasses import dataclass, field

from backend.qa.corpus import Candidate
from backend.qa.labels import Label
from backend.qa.policy import Decision


def is_holdout(project_id: str) -> bool:
    """Deterministic ~20% holdout split, by project so tuning can't leak."""
    return int(hashlib.sha1(project_id.encode()).hexdigest(), 16) % 5 == 0


@dataclass
class EvalMetrics:
    n: int = 0
    n_rejects: int = 0
    n_accepts: int = 0
    reject_recall: float = 0.0
    false_flag_rate: float = 0.0
    recall_by_reason: dict[str, tuple[int, int]] = field(default_factory=dict)
    by_style: dict[str, dict[str, float]] = field(default_factory=dict)


def evaluate(
    labels: list[Label],
    decisions: dict[str, Decision],
    candidates: dict[str, Candidate],
    holdout_only: bool = False,
) -> EvalMetrics:
    caught = missed = false_flags = accepts = 0
    reason_caught: dict[str, int] = {}
    reason_total: dict[str, int] = {}
    style_stats: dict[str, dict[str, int]] = {}
    n = 0
    for label in labels:
        candidate = candidates.get(label.key)
        decision = decisions.get(label.key)
        if candidate is None or decision is None:
            continue
        if holdout_only and not is_holdout(candidate.project_id):
            continue
        n += 1
        flagged = decision.verdict != "pass"
        style = candidate.door_style or "unknown"
        stats = style_stats.setdefault(style, {"caught": 0, "rejects": 0, "flags": 0, "accepts": 0})
        if label.verdict == "reject":
            stats["rejects"] += 1
            for reason in label.reasons or ["other"]:
                reason_total[reason] = reason_total.get(reason, 0) + 1
                if flagged:
                    reason_caught[reason] = reason_caught.get(reason, 0) + 1
            if flagged:
                caught += 1
                stats["caught"] += 1
            else:
                missed += 1
        else:
            accepts += 1
            stats["accepts"] += 1
            if flagged:
                false_flags += 1
                stats["flags"] += 1

    rejects = caught + missed
    return EvalMetrics(
        n=n,
        n_rejects=rejects,
        n_accepts=accepts,
        reject_recall=caught / rejects if rejects else 0.0,
        false_flag_rate=false_flags / accepts if accepts else 0.0,
        recall_by_reason={
            r: (reason_caught.get(r, 0), t) for r, t in sorted(reason_total.items())
        },
        by_style={
            s: {
                "reject_recall": v["caught"] / v["rejects"] if v["rejects"] else 1.0,
                "false_flag_rate": v["flags"] / v["accepts"] if v["accepts"] else 0.0,
                "n_rejects": float(v["rejects"]),
                "n_accepts": float(v["accepts"]),
            }
            for s, v in sorted(style_stats.items())
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa/test_eval.py -v`
Expected: 2 PASS

- [ ] **Step 5: Write the CLI**

```python
# scripts/qa_eval.py
"""Run the vision judge over labeled images and score it against the labels.

Usage:
    uv run python scripts/qa_eval.py            # train split (non-holdout)
    uv run python scripts/qa_eval.py --holdout  # final check, run sparingly
    uv run python scripts/qa_eval.py --limit 20 # cap API spend while iterating

Judge verdicts are cached in output/.qa/verdicts/<config-hash>/, so re-runs only pay for
new images or a changed prompt/model.
"""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

from backend.qa.corpus import walk_corpus
from backend.qa.eval import evaluate, is_holdout
from backend.qa.judge import VisionJudge
from backend.qa.labels import LabelStore
from backend.qa.policy import decide, load_policy

QA_DIR = Path("output/.qa")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", action="store_true", help="score the holdout split")
    parser.add_argument("--limit", type=int, default=0, help="max images to judge (0 = all)")
    parser.add_argument("--model", default=None, help="override judge model")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set (see .env)")

    labels = LabelStore(QA_DIR / "labels.json").all()
    candidates = {
        c.key: c for c in walk_corpus(Path("output/.projects"), Path("swatches"))
    }
    judged_labels = [
        label
        for label in labels
        if label.key in candidates
        and is_holdout(candidates[label.key].project_id) == args.holdout
    ]
    if args.limit:
        judged_labels = judged_labels[: args.limit]
    split = "holdout" if args.holdout else "train"
    print(f"{len(judged_labels)} labeled images in {split} split")

    kwargs = {"model": args.model} if args.model else {}
    judge = VisionJudge(api_key=api_key, cache_dir=QA_DIR / "verdicts", **kwargs)
    policy = load_policy()
    decisions = {}
    for i, label in enumerate(judged_labels, 1):
        candidate = candidates[label.key]
        result = judge.judge(candidate)
        decisions[label.key] = decide(result, candidate, policy)
        print(f"[{i}/{len(judged_labels)}] {label.key}: {decisions[label.key].verdict}")

    metrics = evaluate(judged_labels, decisions, candidates)
    print(f"\n== {split} metrics (judge config {judge.config_hash()}) ==")
    print(f"n={metrics.n}  rejects={metrics.n_rejects}  accepts={metrics.n_accepts}")
    print(f"reject recall:   {metrics.reject_recall:.1%}  (target >= 95%)")
    print(f"false-flag rate: {metrics.false_flag_rate:.1%}  (target <= 20%)")
    print("recall by reason:")
    for reason, (caught, total) in metrics.recall_by_reason.items():
        print(f"  {reason}: {caught}/{total}")
    print("by door style:")
    for style, stats in metrics.by_style.items():
        print(
            f"  {style}: recall {stats['reject_recall']:.0%} "
            f"({stats['n_rejects']:.0f} rejects), "
            f"false flags {stats['false_flag_rate']:.0%} ({stats['n_accepts']:.0f} accepts)"
        )
    report_path = QA_DIR / "eval_report.json"
    report_path.write_text(json.dumps({"split": split, **asdict(metrics)}, indent=1))
    print(f"\nwritten: {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Verify CLI wiring without labels**

Run: `uv run python scripts/qa_eval.py --limit 1`
Expected: either `0 labeled images in train split` (labels not created yet) followed by the metrics block with `n=0`, or a clean judged run if smoke labels exist. It must not traceback. (If `GEMINI_API_KEY` is missing it should exit with the friendly message.)

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check backend/qa scripts tests/qa
git add backend/qa/eval.py scripts/qa_eval.py tests/qa/test_eval.py
git commit -m "feat(qa): eval harness with holdout split + qa_eval CLI"
```

---

### Task 8: Review report

**Files:**
- Create: `backend/qa/report.py`
- Create: `scripts/qa_report.py`
- Test: `tests/qa/test_report.py`

**Interfaces:**
- Consumes: `Candidate` (Task 2), `Decision` (Task 6), `JudgeResult` (Task 5),
  `export_thumb` (Task 3), sheet CSS (Task 4).
- Produces: `render_review_report(items: list[tuple[Candidate, JudgeResult, Decision]],
  thumb_urls: dict[str, dict[str, str]]) -> str` — flagged images (verdict != pass)
  side-by-side with sample + swatch, judge scores and reason, grouped needs_human first
  then regenerate, then by door style; passes appear only as a summary count.
  CLI `scripts/qa_report.py` writes `output/.qa/review.html`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/qa/test_report.py
from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.judge import JudgeResult
from backend.qa.policy import Decision
from backend.qa.report import render_review_report


def test_report_shows_flagged_hides_passed(projects_dir: Path, swatches_dir: Path) -> None:
    candidates = {c.key: c for c in walk_corpus(projects_dir, swatches_dir)}
    flagged = candidates["abc123:0:variant:0"]
    passed = candidates["abc123:0:variant:1"]
    items = [
        (
            flagged,
            JudgeResult(key=flagged.key, verdict="fail", reason="stiles 10% wider"),
            Decision(flagged.key, "regenerate", "stiles 10% wider"),
        ),
        (
            passed,
            JudgeResult(key=passed.key, verdict="pass", confidence="high", reason="ok"),
            Decision(passed.key, "pass", "ok"),
        ),
    ]
    thumb_urls = {flagged.key: {"img": "thumbs/a.jpg", "sample": "thumbs/s.jpg"}}
    html_out = render_review_report(items, thumb_urls)
    assert "stiles 10% wider" in html_out
    assert flagged.key in html_out
    assert passed.key not in html_out  # passes summarized, not carded
    assert "1 passed" in html_out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/qa/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
# backend/qa/report.py
"""Render the flagged-images review report."""

import html

from backend.qa.corpus import Candidate
from backend.qa.judge import JudgeResult
from backend.qa.policy import Decision
from backend.qa.sheet import _CSS, _figure

_ORDER = {"needs_human": 0, "regenerate": 1}


def render_review_report(
    items: list[tuple[Candidate, JudgeResult, Decision]],
    thumb_urls: dict[str, dict[str, str]],
) -> str:
    flagged = [it for it in items if it[2].verdict != "pass"]
    passed = len(items) - len(flagged)
    flagged.sort(
        key=lambda it: (_ORDER.get(it[2].verdict, 9), it[0].door_style or "", it[0].key)
    )
    cards: list[str] = []
    for candidate, result, decision in flagged:
        urls = thumb_urls.get(candidate.key, {})
        figs = "".join(
            _figure(urls[role], role)
            for role in ("sample", "img", "swatch")
            if role in urls
        )
        scores = (
            f"layout {result.panel_layout_match} · proportions {result.proportions_match} · "
            f"profile {result.profile_character_match} · realism {result.material_realism} · "
            f"swatch {result.swatch_fidelity}"
        )
        cards.append(
            f'<div class="card reject" data-key="{html.escape(candidate.key)}">'
            f'<div class="imgs">{figs}</div><div class="meta">'
            f"<h3>{html.escape(decision.verdict)} · {html.escape(candidate.project_name)} · "
            f"{html.escape(candidate.wood_name or 'base door')}</h3>"
            f"<div>{html.escape(candidate.door_style or 'unknown style')} · "
            f"{html.escape(candidate.key)}</div>"
            f"<div>{html.escape(scores)}</div>"
            f"<p>{html.escape(decision.reason)}</p></div></div>"
        )
    return (
        "<!doctype html><meta charset=utf-8><title>QA review</title>"
        f"<style>{_CSS}</style><h1>Flagged images</h1>"
        f"<p>{len(flagged)} flagged · {passed} passed (not shown)</p>"
        f'{"".join(cards)}'
    )
```

```python
# scripts/qa_report.py
"""Build output/.qa/review.html from cached judge verdicts + policy.

Usage: uv run python scripts/qa_report.py
Only images with a cached verdict appear (run scripts/qa_eval.py first).
"""

import json
from pathlib import Path

from backend.qa.corpus import walk_corpus
from backend.qa.judge import JudgeResult, VisionJudge
from backend.qa.policy import decide, load_policy
from backend.qa.report import render_review_report
from backend.qa.thumbs import export_thumb

QA_DIR = Path("output/.qa")


def main() -> None:
    candidates = {c.key: c for c in walk_corpus(Path("output/.projects"), Path("swatches"))}
    judge = VisionJudge(api_key="unused-cache-only", client=object(), cache_dir=QA_DIR / "verdicts")
    verdict_dir = QA_DIR / "verdicts" / judge.config_hash()
    policy = load_policy()
    items = []
    thumb_urls: dict[str, dict[str, str]] = {}
    if verdict_dir.exists():
        for path in sorted(verdict_dir.glob("*.json")):
            result = JudgeResult(**json.loads(path.read_text()))
            candidate = candidates.get(result.key)
            if candidate is None:
                continue
            decision = decide(result, candidate, policy)
            items.append((candidate, result, decision))
            if decision.verdict != "pass":
                urls: dict[str, str] = {}
                for role, src in (("img", candidate.image_path),
                                  ("sample", candidate.sample_path),
                                  ("swatch", candidate.swatch_path)):
                    if src is None:
                        continue
                    thumb = export_thumb(src, QA_DIR / "site" / "thumbs")
                    if thumb is not None:
                        urls[role] = f"site/thumbs/{thumb.name}"
                thumb_urls[candidate.key] = urls
    out = QA_DIR / "review.html"
    out.write_text(render_review_report(items, thumb_urls))
    flagged = sum(1 for it in items if it[2].verdict != "pass")
    print(f"{len(items)} judged, {flagged} flagged -> {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/qa -v`
Expected: all QA tests PASS (this catches regressions across tasks too)

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check backend/qa scripts tests/qa
git add backend/qa/report.py scripts/qa_report.py tests/qa/test_report.py
git commit -m "feat(qa): flagged-images review report"
```

---

### Task 9: Docs + calibration run (manual gate with Jonny)

**Files:**
- Modify: `CLAUDE.md` (Commands section)

This task has no code. It is the operational gate that decides whether the judge is
trustworthy and whether the conditional geometry module is needed.

- [ ] **Step 1: Document the QA commands in CLAUDE.md**

Append to the `## Commands` code block in `CLAUDE.md`:

```bash
uv run python scripts/qa_label.py    # labeling UI on :8777 (calibration ground truth)
uv run python scripts/qa_eval.py     # judge labeled images + score vs labels (train split)
uv run python scripts/qa_report.py   # build output/.qa/review.html of flagged images
```

Commit: `git add CLAUDE.md && git commit -m "docs: QA judgment pipeline commands"`

- [ ] **Step 2: Labeling session (Jonny)**

Start `uv run python scripts/qa_label.py` and have Jonny label until `labels.json` has
**≥100 labels including ≥30 rejects with reasons**, deliberately covering the door styles
he considers difficult. Confirm the reason vocabulary covers reality — if he keeps
reaching for "other", add the missing reason to `REASONS` (Task 1) and the spec.

- [ ] **Step 3: First eval on the train split**

Run: `uv run python scripts/qa_eval.py --limit 30` first (spend check: ~30 vision calls),
then without `--limit`. Record reject recall and false-flag rate.

- [ ] **Step 4: Iterate prompt/policy on train split only**

Adjust `RUBRIC_PROMPT`, `min_score`, or `--model` and re-run `qa_eval.py` (changed config
hash ⇒ fresh verdicts). Populate `untrusted_styles` in `backend/qa/policy_config.json`
from the by-style table (any style with recall < 100% on rejects or chronic low
confidence). Commit each meaningful iteration.

- [ ] **Step 5: Decision gate — geometry module**

Look at `recall_by_reason` for `geometry_drift` and `profile_character`:
- **≥95% caught** → geometry module not needed; skip to Step 6.
- **<95% caught** → the conditional geometry module (spec §4: alignment + edge-map +
  stile/rail measurement) is justified. STOP and write a separate implementation plan
  for `backend/qa/geometry.py` before continuing — it is deliberately not specced in
  this plan so its design can use the actual observed misses as test fixtures.

- [ ] **Step 6: Final holdout check**

Run: `uv run python scripts/qa_eval.py --holdout` **once**. Success = reject recall ≥95%
and false-flag rate ≤~20% (spec targets). If it fails on holdout after passing train,
the judge is overfit — report the numbers honestly to Jonny and iterate with fresh labels
rather than re-running holdout repeatedly.

- [ ] **Step 7: Review with Jonny**

Run `uv run python scripts/qa_report.py`, open `output/.qa/review.html` together, and ask:
does the flagged pile look like the images he'd actually want to see? His answer, plus the
holdout numbers, is the acceptance criterion for this whole phase — and the go/no-go for
phase 2 (bulk orchestration + regeneration loop).

---

## Self-Review Notes

- **Spec coverage:** calibration builder → Tasks 1–4; eval harness → Task 7; LLM judge
  (rubric, multi-vote, cache, fail-safe errors) → Task 5; decision policy + untrusted
  styles + config file → Task 6; review report → Task 8; geometry module → explicitly
  conditional, gated at Task 9 Step 5 per spec ("added only if the eval shows misses");
  missing `upload.bin` handling → Task 2 (None sample) + Task 4 (warning badge);
  held-out split by project → Task 7; success criteria + honest-fallback reporting →
  Task 9 Steps 6–7. Verdict persistence/resumability → Task 5 cache keyed by config hash.
- **Known simplification:** `qa_report.py` constructs `VisionJudge` with a dummy client
  only to reuse `config_hash()`; acceptable because the constructor never calls the API.
- **Cost control:** judging is disk-cached; eval CLI has `--limit`; holdout run happens once.
