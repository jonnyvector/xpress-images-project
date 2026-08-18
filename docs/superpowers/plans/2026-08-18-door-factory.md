# Door Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `door-factory`, a fresh minimal web app (new repo at `/Users/jonathanhicks/dev/door-factory`) where an admin seeds cabinet doors and a VA generates swatch variations, judges them by eye, and exports passing images as zips — no AI judgment pipeline.

**Architecture:** FastAPI backend serving a built React frontend from one process; flat JSON-per-door store on a Railway volume at `/data`; in-memory generation queue; proven modules ported verbatim from `xpress-images-project` (`generator.py`, `styles/catalog.py`, `materials.py`, `selections.py`, swatch assets).

**Tech Stack:** Python 3.12 + uv + FastAPI + uvicorn + google-genai + Pillow + itsdangerous + pytest; React 19 + Vite + TypeScript; Docker on Railway.

**Spec:** `/Users/jonathanhicks/dev/xpress-images-project/docs/superpowers/specs/2026-08-18-va-generation-app-design.md` (in the OLD repo — read it before starting).

## Global Constraints

- New repo root: `/Users/jonathanhicks/dev/door-factory`. All Create/Modify paths below are relative to it unless absolute.
- Source repo for ported files: `/Users/jonathanhicks/dev/xpress-images-project` (call it `$SRC` below).
- Ported files are copied VERBATIM except where a task says otherwise. Do not refactor them.
- NO QA pipeline code: nothing from `$SRC/backend/qa/` is ever copied or imported.
- Data root: `Path(os.environ.get("DATA_DIR", "/data"))`. Tests always override via tmp_path — tests must never touch `/data`.
- Env vars (exact names): `GEMINI_API_KEY`, `ADMIN_PASSWORD`, `VA_PASSWORD`, `SESSION_SECRET`, `DAILY_IMAGE_CAP` (int, default 150), `DATA_DIR`.
- Roles are exactly the strings `"admin"` and `"va"`.
- Door status values exactly: `"seeding" | "ready" | "in_progress" | "complete" | "exported"`.
- Variant state values exactly: `"pending" | "passed" | "failed"`.
- All JSON writes are atomic: write `<file>.tmp`, then `os.replace`.
- Commits happen in the NEW repo. Conventional-commit style (`feat:`, `test:`, `chore:`).
- Python tests: `uv run pytest` from repo root. Frontend check: `npm run build` in `frontend/`.

---

### Task 1: Scaffold repo + port the jewels

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`
- Create (copy from $SRC): `backend/generator.py`, `backend/styles/__init__.py`, `backend/styles/catalog.py`, `backend/materials.py`, `backend/selections.py`, `swatches/` (entire directory), `tests/test_generator_retry.py`, plus whatever conftest fixtures that test needs (check its imports; copy only what it uses, never anything importing `backend.qa`)
- Create: `backend/__init__.py`, `tests/__init__.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `DoorGenerator(api_key, model=None)` with `.learn_door_style(door_image_path, door_style_name, door_style, aspect_ratio, corner_style, material_type, learn_in_maple, temperature, style_notes, profile_image_path, lean) -> GenerationResult`, `.generate_variation(swatch_image_path, wood_name, base_signature, wood_description, reference_image_path, door_style, text_prompt, aspect_ratio, style_notes, corner_style, material_type, hex_color, rtf_finish, lean) -> GenerationResult`; `GenerationResult(image_data: bytes|None, thought_signature: bytes|None, error: str|None, prompt: str)`; `backend.selections.build_selections(selected_swatches, door_style, material_type) -> list[dict]` where each dict has keys `wood_name`, `wood_description`, `swatch_path`, `reference_image`, `hex`, `rtf_finish`; `backend.styles.catalog.STYLES: dict`; `backend.materials.load_material_types(material)`, `get_swatch_files(material)`, `normalize_material_key(s)`.

- [ ] **Step 1: Create repo and git init**

```bash
mkdir -p /Users/jonathanhicks/dev/door-factory
cd /Users/jonathanhicks/dev/door-factory
git init
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "door-factory"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "google-genai>=1.0",
    "pillow>=10.0",
    "itsdangerous>=2.2",
    "python-multipart>=0.0.9",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = ["pytest>=8.0", "httpx>=0.27", "ruff>=0.6"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Write .gitignore**

```
.venv/
__pycache__/
node_modules/
frontend/dist/
.env
/data/
*.pyc
```

- [ ] **Step 4: Copy ported files from $SRC**

```bash
SRC=/Users/jonathanhicks/dev/xpress-images-project
mkdir -p backend/styles tests
touch backend/__init__.py tests/__init__.py
cp $SRC/backend/generator.py backend/
cp $SRC/backend/styles/__init__.py $SRC/backend/styles/catalog.py backend/styles/
cp $SRC/backend/materials.py $SRC/backend/selections.py backend/
cp -R $SRC/swatches swatches
cp $SRC/tests/test_generator_retry.py tests/
```

Then open `tests/test_generator_retry.py` and each copied backend file; check every `import`/`from` line resolves inside the new repo (they import only `backend.styles.catalog`, `backend.materials`, stdlib, `google.genai`, `PIL`). If `tests/test_generator_retry.py` imports fixtures from `$SRC/tests/conftest.py`, copy ONLY those fixture functions into a new `tests/conftest.py` — and if any needed fixture imports `backend.qa` or `backend.state`, inline a minimal replacement instead of copying the import.

- [ ] **Step 5: Install and run ported tests**

```bash
uv sync
uv run pytest tests/test_generator_retry.py -v
```

Expected: PASS (all). If a test fails on a missing module that lives only in the old app, delete that single test function and note it in the commit message.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: scaffold repo, port generator/styles/materials/selections + swatch assets from xpress-images-project"
```

---

### Task 2: DoorStore (flat JSON-per-door store)

**Files:**
- Create: `backend/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces:
  - `slugify(name: str) -> str` (lowercase, alnum + hyphens)
  - `class DoorStore:`
    - `__init__(self, root: Path)` — `root` is the doors dir, e.g. `DATA_DIR/"doors"`; creates it
    - `create(self, name: str, door_type: str, style_notes: str, config: dict) -> dict` — makes `<root>/<slug>/`, writes `door.json` with `{"slug", "name", "type", "style_notes", "config", "swatches": [], "status": "seeding", "replica_approved": False, "variants": {}}`; raises `ValueError` if slug exists
    - `get(self, slug: str) -> dict | None`
    - `list_doors(self) -> list[dict]` — sorted by name
    - `save(self, door: dict) -> None` — atomic write of `door.json`
    - `door_dir(self, slug: str) -> Path`
    - `variant_dir(self, slug: str, swatch: str) -> Path` — creates it
    - `record_attempt(self, slug: str, swatch: str, image_bytes: bytes) -> str` — writes next `attempt-N.png`, returns filename
    - `list_attempts(self, slug: str, swatch: str) -> list[str]` — sorted by N
    - `recompute_status(self, door: dict) -> None` — mutates `door["status"]`: `seeding` if not `replica_approved` or no swatches; `complete` if every assigned swatch's variant state is `"passed"`; `in_progress` if any variant exists or any attempt made; else `ready`. Never demotes `"exported"` unless a swatch was added (then `in_progress`).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_store.py
from pathlib import Path
import pytest
from backend.store import DoorStore, slugify


@pytest.fixture
def store(tmp_path: Path) -> DoorStore:
    return DoorStore(tmp_path / "doors")


CONFIG = {"door_style": "recessed_panel", "corner_style": "sharp",
          "material_type": "wood", "aspect_ratio": "9:16"}


def test_slugify():
    assert slugify("Shaker 5pc!") == "shaker-5pc"


def test_create_and_get(store):
    door = store.create("Shaker 5pc", "door", "narrow frame", CONFIG)
    assert door["slug"] == "shaker-5pc"
    assert door["status"] == "seeding"
    assert store.get("shaker-5pc")["name"] == "Shaker 5pc"
    assert store.get("missing") is None


def test_create_duplicate_raises(store):
    store.create("Shaker", "door", "", CONFIG)
    with pytest.raises(ValueError):
        store.create("Shaker", "door", "", CONFIG)


def test_save_is_atomic_no_tmp_left(store):
    door = store.create("Shaker", "door", "", CONFIG)
    door["style_notes"] = "updated"
    store.save(door)
    assert store.get("shaker")["style_notes"] == "updated"
    assert not list(store.door_dir("shaker").glob("*.tmp"))


def test_record_and_list_attempts(store):
    store.create("Shaker", "door", "", CONFIG)
    assert store.record_attempt("shaker", "walnut-natural", b"png1") == "attempt-1.png"
    assert store.record_attempt("shaker", "walnut-natural", b"png2") == "attempt-2.png"
    assert store.list_attempts("shaker", "walnut-natural") == ["attempt-1.png", "attempt-2.png"]
    assert (store.variant_dir("shaker", "walnut-natural") / "attempt-1.png").read_bytes() == b"png1"


def test_recompute_status_lifecycle(store):
    door = store.create("Shaker", "door", "", CONFIG)
    store.recompute_status(door)
    assert door["status"] == "seeding"
    door["replica_approved"] = True
    door["swatches"] = ["walnut-natural", "maple-select"]
    store.recompute_status(door)
    assert door["status"] == "ready"
    door["variants"]["walnut-natural"] = {"chosen": "attempt-1.png", "state": "passed"}
    store.recompute_status(door)
    assert door["status"] == "in_progress"
    door["variants"]["maple-select"] = {"chosen": "attempt-1.png", "state": "passed"}
    store.recompute_status(door)
    assert door["status"] == "complete"


def test_exported_not_demoted(store):
    door = store.create("Shaker", "door", "", CONFIG)
    door.update(replica_approved=True, swatches=["walnut-natural"], status="exported",
                variants={"walnut-natural": {"chosen": "attempt-1.png", "state": "passed"}})
    store.recompute_status(door)
    assert door["status"] == "exported"
    door["swatches"].append("maple-select")
    store.recompute_status(door)
    assert door["status"] == "in_progress"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.store'`

- [ ] **Step 3: Implement backend/store.py**

```python
"""Flat JSON-per-door store. One process, one writer, atomic whole-file writes."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.lower()).strip("-")


class DoorStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def door_dir(self, slug: str) -> Path:
        return self.root / slug

    def variant_dir(self, slug: str, swatch: str) -> Path:
        d = self.door_dir(slug) / "variants" / swatch
        d.mkdir(parents=True, exist_ok=True)
        return d

    def create(self, name: str, door_type: str, style_notes: str, config: dict) -> dict:
        slug = slugify(name)
        if not slug:
            raise ValueError("name produces empty slug")
        if self.door_dir(slug).exists():
            raise ValueError(f"door {slug!r} already exists")
        self.door_dir(slug).mkdir(parents=True)
        door = {
            "slug": slug, "name": name, "type": door_type,
            "style_notes": style_notes, "config": config,
            "swatches": [], "status": "seeding",
            "replica_approved": False, "variants": {},
        }
        self.save(door)
        return door

    def get(self, slug: str) -> dict | None:
        path = self.door_dir(slug) / "door.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def list_doors(self) -> list[dict]:
        doors = []
        for d in self.root.iterdir():
            if (d / "door.json").exists():
                doors.append(json.loads((d / "door.json").read_text()))
        return sorted(doors, key=lambda x: x["name"])

    def save(self, door: dict) -> None:
        path = self.door_dir(door["slug"]) / "door.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(door, indent=2))
        os.replace(tmp, path)

    def record_attempt(self, slug: str, swatch: str, image_bytes: bytes) -> str:
        vdir = self.variant_dir(slug, swatch)
        n = len(self.list_attempts(slug, swatch)) + 1
        name = f"attempt-{n}.png"
        (vdir / name).write_bytes(image_bytes)
        return name

    def list_attempts(self, slug: str, swatch: str) -> list[str]:
        vdir = self.door_dir(slug) / "variants" / swatch
        if not vdir.exists():
            return []
        files = [p.name for p in vdir.glob("attempt-*.png")]
        return sorted(files, key=lambda f: int(f.split("-")[1].split(".")[0]))

    def recompute_status(self, door: dict) -> None:
        if not door["replica_approved"] or not door["swatches"]:
            door["status"] = "seeding"
            return
        states = [door["variants"].get(s, {}).get("state") for s in door["swatches"]]
        if all(s == "passed" for s in states):
            if door["status"] != "exported":
                door["status"] = "complete"
        elif any(s is not None for s in states) or any(
            self.list_attempts(door["slug"], s) for s in door["swatches"]
        ):
            door["status"] = "in_progress"
        else:
            door["status"] = "ready"
```

Note the `.with_suffix(".json.tmp")` trick: for `door.json` this yields `door.json.tmp`? No — `with_suffix` replaces the LAST suffix, giving `door.json.tmp` only if chained. Use `path.parent / (path.name + ".tmp")` instead. Implement it that way; the test `test_save_is_atomic_no_tmp_left` globs `*.tmp` and will catch leftovers either way.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/store.py tests/test_store.py
git commit -m "feat: DoorStore flat JSON-per-door store with atomic writes"
```

---

### Task 3: SpendLedger (daily image cap)

**Files:**
- Create: `backend/spend.py`
- Test: `tests/test_spend.py`

**Interfaces:**
- Consumes: nothing
- Produces: `class SpendLedger:` with `__init__(self, path: Path, daily_cap: int)`, `today_count(self) -> int`, `can_spend(self, n: int = 1) -> bool`, `record(self, n: int = 1) -> None`, `history(self) -> dict[str, int]` (date-string -> count), and property `daily_cap: int`. Ledger file is JSON `{"2026-08-18": 42, ...}`, atomic writes, missing file = empty.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_spend.py
from pathlib import Path
from backend.spend import SpendLedger


def test_empty_ledger(tmp_path: Path):
    led = SpendLedger(tmp_path / "spend.json", daily_cap=5)
    assert led.today_count() == 0
    assert led.can_spend()
    assert led.history() == {}


def test_record_and_cap(tmp_path: Path):
    led = SpendLedger(tmp_path / "spend.json", daily_cap=3)
    led.record(2)
    assert led.today_count() == 2
    assert led.can_spend(1)
    assert not led.can_spend(2)
    led.record()
    assert led.today_count() == 3
    assert not led.can_spend()


def test_persists_across_instances(tmp_path: Path):
    path = tmp_path / "spend.json"
    SpendLedger(path, daily_cap=10).record(4)
    assert SpendLedger(path, daily_cap=10).today_count() == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_spend.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.spend'`

- [ ] **Step 3: Implement backend/spend.py**

```python
"""Daily image-generation spend ledger with a hard cap."""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path


class SpendLedger:
    def __init__(self, path: Path, daily_cap: int) -> None:
        self.path = path
        self.daily_cap = daily_cap

    def _load(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def history(self) -> dict[str, int]:
        return self._load()

    def today_count(self) -> int:
        return self._load().get(datetime.date.today().isoformat(), 0)

    def can_spend(self, n: int = 1) -> bool:
        return self.today_count() + n <= self.daily_cap

    def record(self, n: int = 1) -> None:
        data = self._load()
        key = datetime.date.today().isoformat()
        data[key] = data.get(key, 0) + n
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.parent / (self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self.path)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_spend.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/spend.py tests/test_spend.py
git commit -m "feat: SpendLedger daily image cap"
```

---

### Task 4: Auth (login, signed sessions, roles)

**Files:**
- Create: `backend/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `router` (APIRouter) with `POST /auth/login` (JSON `{"password": str}` → matches `ADMIN_PASSWORD` → role admin, matches `VA_PASSWORD` → role va, else 401 after `time.sleep(1)`; sets cookie `session` httponly, max_age 7 days, returns `{"role": ...}`), `POST /auth/logout` (clears cookie), `GET /auth/me` (returns `{"role": ...}` or 401)
  - `require_user(request: Request) -> str` — FastAPI dependency, returns role or raises 401
  - `require_admin(request: Request) -> str` — returns `"admin"` or raises 403 (401 if no session)
  - Token = `itsdangerous.URLSafeTimedSerializer(SESSION_SECRET).dumps({"role": role})`, verified with `max_age=604800`.
  - Config read lazily from env INSIDE functions (so tests can monkeypatch env), via helper `_settings() -> dict` returning `{"admin_password", "va_password", "secret"}`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from backend.auth import require_admin, require_user, router


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.setenv("VA_PASSWORD", "vapw")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    app = FastAPI()
    app.include_router(router, prefix="/api")

    @app.get("/api/protected")
    def protected(role: str = Depends(require_user)):
        return {"role": role}

    @app.get("/api/admin-only")
    def admin_only(role: str = Depends(require_admin)):
        return {"role": role}

    return TestClient(app)


def test_login_admin(client):
    r = client.post("/api/auth/login", json={"password": "adminpw"})
    assert r.status_code == 200 and r.json() == {"role": "admin"}
    assert client.get("/api/protected").json() == {"role": "admin"}
    assert client.get("/api/admin-only").status_code == 200


def test_login_va_blocked_from_admin(client):
    client.post("/api/auth/login", json={"password": "vapw"})
    assert client.get("/api/protected").json() == {"role": "va"}
    assert client.get("/api/admin-only").status_code == 403


def test_bad_password(client):
    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401


def test_no_session(client):
    assert client.get("/api/protected").status_code == 401


def test_logout(client):
    client.post("/api/auth/login", json={"password": "vapw"})
    client.post("/api/auth/logout")
    assert client.get("/api/protected").status_code == 401


def test_tampered_cookie(client):
    client.cookies.set("session", "garbage")
    assert client.get("/api/protected").status_code == 401
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.auth'`

- [ ] **Step 3: Implement backend/auth.py**

```python
"""Password login, signed session cookie, admin/va roles."""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

SESSION_MAX_AGE = 7 * 24 * 3600
router = APIRouter()


def _settings() -> dict:
    return {
        "admin_password": os.environ.get("ADMIN_PASSWORD", ""),
        "va_password": os.environ.get("VA_PASSWORD", ""),
        "secret": os.environ.get("SESSION_SECRET", ""),
    }


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_settings()["secret"], salt="session")


def _role_from_request(request: Request) -> str | None:
    token = request.cookies.get("session")
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    role = data.get("role")
    return role if role in ("admin", "va") else None


def require_user(request: Request) -> str:
    role = _role_from_request(request)
    if role is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return role


def require_admin(request: Request) -> str:
    role = require_user(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return role


class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
def login(body: LoginRequest, response: Response) -> dict:
    s = _settings()
    if s["admin_password"] and body.password == s["admin_password"]:
        role = "admin"
    elif s["va_password"] and body.password == s["va_password"]:
        role = "va"
    else:
        time.sleep(1)  # crude brute-force brake
        raise HTTPException(status_code=401, detail="Wrong password")
    token = _serializer().dumps({"role": role})
    response.set_cookie("session", token, max_age=SESSION_MAX_AGE,
                        httponly=True, samesite="lax")
    return {"role": role}


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> dict:
    return {"role": require_user(request)}
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: password auth with signed sessions and admin/va roles"
```

---

### Task 5: GenerationWorker (queue + generator dispatch)

**Files:**
- Create: `backend/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `DoorStore` (Task 2), `SpendLedger` (Task 3), `build_selections` + `DoorGenerator`/`GenerationResult` (Task 1)
- Produces:
  - `class GenerationWorker:`
    - `__init__(self, store: DoorStore, ledger: SpendLedger, generator_factory: Callable[[], object])` — `generator_factory` returns an object with the `generate_variation(...)` signature from Task 1 (tests inject a fake; app injects `lambda: DoorGenerator(os.environ["GEMINI_API_KEY"])`). Starts one daemon worker thread over a `queue.Queue`.
    - `enqueue(self, slug: str, swatch: str) -> str` — returns `"queued"`, or `"cap"` if `not ledger.can_spend()`, or `"busy"` if that (slug, swatch) is already pending/running
    - `enqueue_all(self, slug: str) -> dict` — enqueues every assigned swatch whose variant state != "passed"; returns `{"queued": [...], "skipped_cap": [...]}` (stops queueing at cap)
    - `status(self, slug: str) -> dict[str, str]` — `{swatch: "pending"|"running"}` for in-flight only
    - `last_error(self, slug: str, swatch: str) -> str | None`
  - Job behavior: `ledger.record(1)` when job STARTS; build selection via `build_selections([swatch], door_style=cfg["door_style"], material_type=cfg["material_type"])`; read signature from `store.door_dir(slug)/"signature.bin"`; call `generate_variation(swatch_image_path=sel["swatch_path"], wood_name=sel["wood_name"], base_signature=sig, wood_description=sel["wood_description"], reference_image_path=None, door_style=cfg["door_style"], aspect_ratio=cfg["aspect_ratio"], style_notes=door["style_notes"], corner_style=cfg["corner_style"], material_type=cfg["material_type"], hex_color=sel.get("hex"), rtf_finish=sel.get("rtf_finish"))`. On success: `store.record_attempt`, set variant `{"chosen": <new attempt>, "state": "pending"}` (only overwrite `chosen` if current state != "passed"), `store.recompute_status`, `store.save`. On error result or exception: store message in `last_error`, leave door.json untouched.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_worker.py
import time
from pathlib import Path
import pytest
from backend.spend import SpendLedger
from backend.store import DoorStore
from backend.worker import GenerationWorker
from backend.generator import GenerationResult

CONFIG = {"door_style": "recessed_panel", "corner_style": "sharp",
          "material_type": "wood", "aspect_ratio": "9:16"}


class FakeGenerator:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = []

    def generate_variation(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            return GenerationResult(image_data=None, thought_signature=None, error="boom")
        return GenerationResult(image_data=b"fakepng", thought_signature=b"sig2", error=None)


@pytest.fixture
def store(tmp_path: Path) -> DoorStore:
    s = DoorStore(tmp_path / "doors")
    door = s.create("Shaker", "door", "", CONFIG)
    door["replica_approved"] = True
    door["swatches"] = ["alder-select", "alder-natural"]
    s.save(door)
    (s.door_dir("shaker") / "signature.bin").write_bytes(b"learned-sig")
    return s


def make_worker(store, tmp_path, gen, cap=100):
    ledger = SpendLedger(tmp_path / "spend.json", daily_cap=cap)
    return GenerationWorker(store, ledger, lambda: gen), ledger


def wait_idle(worker, slug, timeout=5.0):
    deadline = time.time() + timeout
    while worker.status(slug) and time.time() < deadline:
        time.sleep(0.02)
    assert not worker.status(slug), "worker did not drain"


def test_enqueue_generates_and_records(store, tmp_path):
    gen = FakeGenerator()
    worker, ledger = make_worker(store, tmp_path, gen)
    assert worker.enqueue("shaker", "alder-select") == "queued"
    wait_idle(worker, "shaker")
    door = store.get("shaker")
    assert door["variants"]["alder-select"] == {"chosen": "attempt-1.png", "state": "pending"}
    assert store.list_attempts("shaker", "alder-select") == ["attempt-1.png"]
    assert ledger.today_count() == 1
    call = gen.calls[0]
    assert call["base_signature"] == b"learned-sig"
    assert call["wood_name"] == "Alder Select"
    assert call["door_style"] == "recessed_panel"


def test_cap_blocks(store, tmp_path):
    worker, _ = make_worker(store, tmp_path, FakeGenerator(), cap=0)
    assert worker.enqueue("shaker", "alder-select") == "cap"


def test_duplicate_enqueue_busy(store, tmp_path):
    class SlowGen(FakeGenerator):
        def generate_variation(self, **kwargs):
            time.sleep(0.3)
            return super().generate_variation(**kwargs)
    worker, _ = make_worker(store, tmp_path, SlowGen())
    assert worker.enqueue("shaker", "alder-select") == "queued"
    assert worker.enqueue("shaker", "alder-select") == "busy"
    wait_idle(worker, "shaker")


def test_error_recorded_not_written(store, tmp_path):
    worker, _ = make_worker(store, tmp_path, FakeGenerator(fail=True))
    worker.enqueue("shaker", "alder-select")
    wait_idle(worker, "shaker")
    assert worker.last_error("shaker", "alder-select") == "boom"
    assert store.get("shaker")["variants"] == {}
    assert store.list_attempts("shaker", "alder-select") == []


def test_enqueue_all_skips_passed(store, tmp_path):
    door = store.get("shaker")
    door["variants"]["alder-select"] = {"chosen": "attempt-1.png", "state": "passed"}
    store.save(door)
    worker, _ = make_worker(store, tmp_path, FakeGenerator())
    result = worker.enqueue_all("shaker")
    assert result["queued"] == ["alder-natural"]
    wait_idle(worker, "shaker")


def test_passed_chosen_not_overwritten(store, tmp_path):
    gen = FakeGenerator()
    worker, _ = make_worker(store, tmp_path, gen)
    store.record_attempt("shaker", "alder-select", b"old")
    door = store.get("shaker")
    door["variants"]["alder-select"] = {"chosen": "attempt-1.png", "state": "passed"}
    store.save(door)
    worker.enqueue("shaker", "alder-select")
    wait_idle(worker, "shaker")
    door = store.get("shaker")
    assert door["variants"]["alder-select"]["chosen"] == "attempt-1.png"
    assert store.list_attempts("shaker", "alder-select") == ["attempt-1.png", "attempt-2.png"]
```

Note: swatch keys `alder-select` / `alder-natural` exist in the ported `swatches/wood_types.json` with physical files, so `build_selections` resolves them for real — no mocking of selections.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.worker'`

- [ ] **Step 3: Implement backend/worker.py**

```python
"""Single-thread generation queue. In-memory by design — deploys kill in-flight
jobs; affected swatches just show non-passed and get regenerated."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from backend.selections import build_selections
from backend.spend import SpendLedger
from backend.store import DoorStore

log = logging.getLogger(__name__)


class GenerationWorker:
    def __init__(self, store: DoorStore, ledger: SpendLedger,
                 generator_factory: Callable[[], object]) -> None:
        self.store = store
        self.ledger = ledger
        self.generator_factory = generator_factory
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._lock = threading.Lock()
        self._inflight: dict[tuple[str, str], str] = {}  # (slug, swatch) -> pending|running
        self._errors: dict[tuple[str, str], str] = {}
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # -- public API -----------------------------------------------------
    def enqueue(self, slug: str, swatch: str) -> str:
        with self._lock:
            if (slug, swatch) in self._inflight:
                return "busy"
            if not self.ledger.can_spend(1 + sum(
                1 for s in self._inflight.values() if s == "pending"
            )):
                return "cap"
            self._inflight[(slug, swatch)] = "pending"
            self._errors.pop((slug, swatch), None)
        self._queue.put((slug, swatch))
        return "queued"

    def enqueue_all(self, slug: str) -> dict:
        door = self.store.get(slug)
        queued, skipped_cap = [], []
        for swatch in door["swatches"]:
            if door["variants"].get(swatch, {}).get("state") == "passed":
                continue
            result = self.enqueue(slug, swatch)
            if result == "queued":
                queued.append(swatch)
            elif result == "cap":
                skipped_cap.append(swatch)
        return {"queued": queued, "skipped_cap": skipped_cap}

    def status(self, slug: str) -> dict[str, str]:
        with self._lock:
            return {sw: st for (s, sw), st in self._inflight.items() if s == slug}

    def last_error(self, slug: str, swatch: str) -> str | None:
        with self._lock:
            return self._errors.get((slug, swatch))

    # -- worker loop ----------------------------------------------------
    def _run(self) -> None:
        while True:
            slug, swatch = self._queue.get()
            with self._lock:
                self._inflight[(slug, swatch)] = "running"
            try:
                self._generate(slug, swatch)
            except Exception as exc:  # noqa: BLE001 — worker thread must survive
                log.exception("generation failed for %s/%s", slug, swatch)
                with self._lock:
                    self._errors[(slug, swatch)] = str(exc)
            finally:
                with self._lock:
                    self._inflight.pop((slug, swatch), None)
                self._queue.task_done()

    def _generate(self, slug: str, swatch: str) -> None:
        door = self.store.get(slug)
        cfg = door["config"]
        sig_path = self.store.door_dir(slug) / "signature.bin"
        signature = sig_path.read_bytes() if sig_path.exists() else b""
        sels = build_selections([swatch], door_style=cfg["door_style"],
                                material_type=cfg["material_type"])
        if not sels:
            with self._lock:
                self._errors[(slug, swatch)] = f"swatch {swatch!r} did not resolve"
            return
        sel = sels[0]
        self.ledger.record(1)
        gen = self.generator_factory()
        result = gen.generate_variation(
            swatch_image_path=sel["swatch_path"],
            wood_name=sel["wood_name"],
            base_signature=signature,
            wood_description=sel["wood_description"],
            reference_image_path=None,
            door_style=cfg["door_style"],
            aspect_ratio=cfg["aspect_ratio"],
            style_notes=door["style_notes"],
            corner_style=cfg["corner_style"],
            material_type=cfg["material_type"],
            hex_color=sel.get("hex"),
            rtf_finish=sel.get("rtf_finish"),
        )
        if result.error or not result.image_data:
            with self._lock:
                self._errors[(slug, swatch)] = result.error or "no image returned"
            return
        attempt = self.store.record_attempt(slug, swatch, result.image_data)
        door = self.store.get(slug)  # re-read: avoid clobbering review actions
        variant = door["variants"].get(swatch, {"chosen": None, "state": "pending"})
        if variant.get("state") != "passed":
            variant["chosen"] = attempt
            variant["state"] = "pending"
        door["variants"][swatch] = variant
        self.store.recompute_status(door)
        self.store.save(door)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_worker.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run full suite (regression)**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/worker.py tests/test_worker.py
git commit -m "feat: GenerationWorker queue with spend cap and injectable generator"
```

---

### Task 6: API routers + app wiring (doors, seeding, review, export)

**Files:**
- Create: `backend/app.py`, `backend/deps.py`, `backend/routers/__init__.py`, `backend/routers/doors.py`, `backend/routers/swatches.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1-5
- Produces (all under `/api`, media under `/media`):
  - `backend/deps.py`: `get_store(request) -> DoorStore`, `get_worker(request) -> GenerationWorker`, `get_ledger(request) -> SpendLedger` — read from `request.app.state`
  - `backend/app.py`: `create_app(data_dir: Path | None = None, generator_factory=None) -> FastAPI`. Builds store (`data_dir/"doors"`), ledger (`data_dir/"spend.json"`, cap from `DAILY_IMAGE_CAP` env, default 150), worker; stores on `app.state`; includes auth router + doors router + swatches router under `/api`; mounts `StaticFiles(directory=data_dir, ...)` at `/media` **behind auth** (see below); mounts `swatches/` at `/media-swatches`; serves `frontend/dist` at `/` if it exists. Module-level `app = create_app()` guarded so tests never hit `/data`: only build when `DATA_DIR` env or `/data` exists.
  - Auth on media: implement `/media` as a normal GET route `GET /media/{path:path}` that calls `require_user` then `FileResponse`, rejecting any path containing `..` and resolving strictly inside `data_dir`.
  - Doors router endpoints:
    - `GET /api/doors` (user) — list; VA role gets doors with status != "seeding" only; each item: slug, name, type, status, swatch count, passed count, thumbnail url `/media/doors/<slug>/source.png`
    - `POST /api/doors` (admin, multipart) — fields: `name`, `door_type` ("door"|"drawer_front"), `style_notes`, `door_style`, `corner_style`, `material_type`, `aspect_ratio`, file `image`. Validates `door_style in STYLES`. Saves `source.png` (converted to PNG via Pillow), creates door.
    - `POST /api/doors/{slug}/learn` (admin) — runs `generator_factory().learn_door_style(door_image_path=<source.png>, door_style_name=door["name"], door_style=cfg["door_style"], aspect_ratio=cfg["aspect_ratio"], corner_style=cfg["corner_style"], material_type=cfg["material_type"], style_notes=door["style_notes"])` SYNCHRONOUSLY; records 1 spend; on success writes `replica-candidate.png` + `signature-candidate.bin`; returns `{"replica_url": ...}`; 502 with the error string on failure; 429 if cap hit.
    - `POST /api/doors/{slug}/approve-replica` (admin) — renames candidates to `replica.png` / `signature.bin`, sets `replica_approved=True`, recomputes status, saves.
    - `PUT /api/doors/{slug}/swatches` (admin, JSON `{"swatches": [...]}`) — validates each key resolves via `build_selections`; sets list; recompute; save.
    - `GET /api/doors/{slug}` (user; VA blocked from `seeding` doors with 404) — full door dict + `attempts` map `{swatch: [filenames]}` + `inflight` from `worker.status(slug)` + `errors` map + image URL templates
    - `POST /api/doors/{slug}/generate` (user, JSON `{"swatch": str}`) — `worker.enqueue`; maps `"cap"` → 429 `{"detail": "Daily limit reached — message Jonathan."}`, `"busy"` → 409, `"queued"` → 200
    - `POST /api/doors/{slug}/generate-all` (user) — `worker.enqueue_all`, 200 with its dict
    - `POST /api/doors/{slug}/variants/{swatch}/review` (user, JSON `{"action": "pass"|"fail", "chosen": str|None}`) — pass: set state passed (+ optional chosen override, must be an existing attempt else 400); fail: set state failed AND `worker.enqueue` (ignore cap result, still mark failed); recompute; save; returns updated door
    - `GET /api/doors/{slug}/export` (user) — 409 unless status in ("complete", "exported"); streams zip named `<Name>.zip` containing `<slug>-<swatch>.png` for each chosen image, plus `door.json` and `signature.bin`; sets status "exported", saves
    - `POST /api/doors/{slug}/reopen` (admin) — status `exported` → recompute (back to complete/in_progress)
    - `GET /api/spend` (admin) — `{"today": n, "cap": n, "history": {...}}`
  - Swatches router: `GET /api/swatches?material=wood|rtf` (user) — trimmed port of old `list_swatches` returning `[{key, name, description, swatch_image_url}]` with urls under `/media-swatches/...`; skip virtual-swatch and reference-image handling ONLY if it breaks — otherwise port as-is with rewritten URL prefix.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_api.py
import io
import zipfile
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.generator import GenerationResult


class FakeGen:
    def learn_door_style(self, **kwargs):
        return GenerationResult(image_data=b"replica-png", thought_signature=b"sig", error=None)

    def generate_variation(self, **kwargs):
        return GenerationResult(image_data=b"variant-png", thought_signature=b"sig2", error=None)


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.setenv("VA_PASSWORD", "vapw")
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    monkeypatch.setenv("DAILY_IMAGE_CAP", "100")
    app = create_app(data_dir=tmp_path, generator_factory=lambda: FakeGen())
    return TestClient(app)


def login(client, pw):
    assert client.post("/api/auth/login", json={"password": pw}).status_code == 200


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 20), "white").save(buf, format="PNG")
    return buf.getvalue()


def seed_door(client) -> str:
    login(client, "adminpw")
    r = client.post("/api/doors", data={
        "name": "Shaker 5pc", "door_type": "door", "style_notes": "narrow frame",
        "door_style": "recessed_panel", "corner_style": "sharp",
        "material_type": "wood", "aspect_ratio": "9:16",
    }, files={"image": ("door.png", _png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    slug = r.json()["slug"]
    assert client.post(f"/api/doors/{slug}/learn").status_code == 200
    assert client.post(f"/api/doors/{slug}/approve-replica").status_code == 200
    r = client.put(f"/api/doors/{slug}/swatches",
                   json={"swatches": ["alder-select", "alder-natural"]})
    assert r.status_code == 200, r.text
    return slug


def test_full_seed_flow(client):
    slug = seed_door(client)
    door = client.get(f"/api/doors/{slug}").json()
    assert door["status"] == "ready"
    assert door["replica_approved"] is True
    assert door["swatches"] == ["alder-select", "alder-natural"]


def test_va_cannot_seed(client):
    login(client, "vapw")
    assert client.post("/api/doors", data={"name": "X"}).status_code == 403


def test_va_hidden_seeding_doors(client):
    login(client, "adminpw")
    client.post("/api/doors", data={
        "name": "Half Done", "door_type": "door", "style_notes": "",
        "door_style": "recessed_panel", "corner_style": "sharp",
        "material_type": "wood", "aspect_ratio": "9:16",
    }, files={"image": ("d.png", _png_bytes(), "image/png")})
    login(client, "vapw")
    assert client.get("/api/doors").json() == []
    assert client.get("/api/doors/half-done").status_code == 404


def test_generate_review_export(client):
    slug = seed_door(client)
    login(client, "vapw")
    assert client.post(f"/api/doors/{slug}/generate-all").status_code == 200
    # worker is async; poll until both attempts exist
    import time
    deadline = time.time() + 5
    while time.time() < deadline:
        door = client.get(f"/api/doors/{slug}").json()
        if all(door["attempts"].get(s) for s in door["swatches"]) and not door["inflight"]:
            break
        time.sleep(0.05)
    for s in ["alder-select", "alder-natural"]:
        r = client.post(f"/api/doors/{slug}/variants/{s}/review",
                        json={"action": "pass", "chosen": None})
        assert r.status_code == 200
    assert client.get(f"/api/doors/{slug}").json()["status"] == "complete"
    r = client.get(f"/api/doors/{slug}/export")
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert f"{slug}-alder-select.png" in names
    assert "door.json" in names and "signature.bin" in names
    assert client.get(f"/api/doors/{slug}").json()["status"] == "exported"


def test_export_blocked_when_incomplete(client):
    slug = seed_door(client)
    login(client, "vapw")
    assert client.get(f"/api/doors/{slug}/export").status_code == 409


def test_fail_marks_and_requeues(client):
    slug = seed_door(client)
    login(client, "vapw")
    client.post(f"/api/doors/{slug}/generate", json={"swatch": "alder-select"})
    import time
    time.sleep(0.3)
    r = client.post(f"/api/doors/{slug}/variants/alder-select/review",
                    json={"action": "fail", "chosen": None})
    assert r.status_code == 200
    assert r.json()["variants"]["alder-select"]["state"] == "failed"


def test_cap_returns_429(client, monkeypatch):
    slug = seed_door(client)
    monkeypatch.setenv("DAILY_IMAGE_CAP", "0")
    # cap read at app creation; simulate exhaustion instead
    from backend.deps import _  # noqa: F401  (placeholder guard — see note)


def test_media_requires_auth(client):
    slug = seed_door(client)
    fresh = TestClient(client.app)
    assert fresh.get(f"/media/doors/{slug}/source.png").status_code == 401
    login(fresh, "vapw")
    assert fresh.get(f"/media/doors/{slug}/source.png").status_code == 200
    assert fresh.get("/media/../pyproject.toml").status_code in (400, 404)


def test_spend_endpoint_admin_only(client):
    seed_door(client)  # logs in as admin, learn spent 1
    r = client.get("/api/spend")
    assert r.status_code == 200 and r.json()["today"] >= 1
    login(client, "vapw")
    assert client.get("/api/spend").status_code == 403


def test_swatches_list(client):
    login(client, "vapw")
    r = client.get("/api/swatches?material=wood")
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert "alder-select" in keys
```

Delete `test_cap_returns_429` as written above — it is unfinishable as sketched. Replace it with this real version: create the app with `monkeypatch.setenv("DAILY_IMAGE_CAP", "1")` in a SEPARATE fixture-less test that builds its own client, seed a door (learn consumes the 1), then `POST .../generate` and assert 429 with detail `"Daily limit reached — message Jonathan."`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app'`

- [ ] **Step 3: Implement backend/deps.py**

```python
"""App-state accessors used as FastAPI dependencies."""
from __future__ import annotations

from fastapi import Request

from backend.spend import SpendLedger
from backend.store import DoorStore
from backend.worker import GenerationWorker


def get_store(request: Request) -> DoorStore:
    return request.app.state.store


def get_worker(request: Request) -> GenerationWorker:
    return request.app.state.worker


def get_ledger(request: Request) -> SpendLedger:
    return request.app.state.ledger
```

- [ ] **Step 4: Implement backend/routers/swatches.py**

Port `$SRC/backend/routers/swatches.py`'s `list_swatches` body, with changes: drop `StyleResponse`/`/styles` endpoint and pydantic response models (return plain dicts); URL prefix becomes `/media-swatches/wood/...` or `/media-swatches/rtf/...`; add `Depends(require_user)`. Keep virtual-swatch handling as-is.

- [ ] **Step 5: Implement backend/routers/doors.py**

Implement every endpoint from the Interfaces block. Skeleton with the non-obvious parts spelled out:

```python
"""Doors API: seeding (admin), generation + review + export (va & admin)."""
from __future__ import annotations

import io
import json
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from backend.auth import require_admin, require_user
from backend.deps import get_ledger, get_store, get_worker
from backend.selections import build_selections
from backend.styles.catalog import STYLES

router = APIRouter()


def _door_or_404(store, slug: str, role: str) -> dict:
    door = store.get(slug)
    if door is None or (role == "va" and door["status"] == "seeding"):
        raise HTTPException(status_code=404, detail="Door not found")
    return door


def _detail(store, worker, door: dict) -> dict:
    slug = door["slug"]
    attempts = {s: store.list_attempts(slug, s) for s in door["swatches"]}
    errors = {s: worker.last_error(slug, s) for s in door["swatches"]
              if worker.last_error(slug, s)}
    return {**door, "attempts": attempts, "inflight": worker.status(slug),
            "errors": errors,
            "source_url": f"/media/doors/{slug}/source.png",
            "replica_url": f"/media/doors/{slug}/replica.png" if door["replica_approved"] else None}


@router.get("/doors")
def list_doors(role: str = Depends(require_user), store=Depends(get_store)) -> list[dict]:
    doors = store.list_doors()
    if role == "va":
        doors = [d for d in doors if d["status"] != "seeding"]
    return [{
        "slug": d["slug"], "name": d["name"], "type": d["type"], "status": d["status"],
        "swatch_count": len(d["swatches"]),
        "passed_count": sum(1 for s in d["swatches"]
                            if d["variants"].get(s, {}).get("state") == "passed"),
        "thumbnail_url": f"/media/doors/{d['slug']}/source.png",
    } for d in doors]


@router.post("/doors")
def create_door(
    name: str = Form(...), door_type: str = Form(...), style_notes: str = Form(""),
    door_style: str = Form(...), corner_style: str = Form("sharp"),
    material_type: str = Form("wood"), aspect_ratio: str = Form("9:16"),
    image: UploadFile = File(...),
    _: str = Depends(require_admin), store=Depends(get_store),
) -> dict:
    if door_style not in STYLES:
        raise HTTPException(status_code=400, detail=f"Unknown door_style {door_style!r}")
    if door_type not in ("door", "drawer_front"):
        raise HTTPException(status_code=400, detail="door_type must be door|drawer_front")
    config = {"door_style": door_style, "corner_style": corner_style,
              "material_type": material_type, "aspect_ratio": aspect_ratio}
    try:
        door = store.create(name, door_type, style_notes, config)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    img = Image.open(io.BytesIO(image.file.read()))
    img.save(store.door_dir(door["slug"]) / "source.png", format="PNG")
    return door
```

Learn endpoint (synchronous, admin waits — this is deliberate):

```python
@router.post("/doors/{slug}/learn")
def learn(slug: str, request: Request, _: str = Depends(require_admin),
          store=Depends(get_store), ledger=Depends(get_ledger)) -> dict:
    door = store.get(slug)
    if door is None:
        raise HTTPException(status_code=404, detail="Door not found")
    if not ledger.can_spend():
        raise HTTPException(status_code=429, detail="Daily limit reached")
    cfg = door["config"]
    ledger.record(1)
    gen = request.app.state.generator_factory()
    result = gen.learn_door_style(
        door_image_path=store.door_dir(slug) / "source.png",
        door_style_name=door["name"], door_style=cfg["door_style"],
        aspect_ratio=cfg["aspect_ratio"], corner_style=cfg["corner_style"],
        material_type=cfg["material_type"], style_notes=door["style_notes"],
    )
    if result.error or not result.image_data or not result.thought_signature:
        raise HTTPException(status_code=502, detail=result.error or "no image/signature")
    (store.door_dir(slug) / "replica-candidate.png").write_bytes(result.image_data)
    (store.door_dir(slug) / "signature-candidate.bin").write_bytes(result.thought_signature)
    return {"replica_url": f"/media/doors/{slug}/replica-candidate.png"}
```

Approve, swatches, detail, generate, generate-all, review, export, reopen, spend — follow the Interfaces block exactly. Export zip:

```python
@router.get("/doors/{slug}/export")
def export_zip(slug: str, role: str = Depends(require_user),
               store=Depends(get_store)) -> Response:
    door = _door_or_404(store, slug, role)
    if door["status"] not in ("complete", "exported"):
        raise HTTPException(status_code=409, detail="Door is not complete")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for swatch in door["swatches"]:
            chosen = door["variants"][swatch]["chosen"]
            path = store.door_dir(slug) / "variants" / swatch / chosen
            zf.write(path, f"{slug}-{swatch}.png")
        zf.write(store.door_dir(slug) / "door.json", "door.json")
        sig = store.door_dir(slug) / "signature.bin"
        if sig.exists():
            zf.write(sig, "signature.bin")
    door["status"] = "exported"
    store.save(door)
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="{door["name"]}.zip"'})
```

Review endpoint:

```python
class ReviewRequest(BaseModel):
    action: str  # "pass" | "fail"
    chosen: str | None = None


@router.post("/doors/{slug}/variants/{swatch}/review")
def review(slug: str, swatch: str, body: ReviewRequest,
           role: str = Depends(require_user), store=Depends(get_store),
           worker=Depends(get_worker)) -> dict:
    door = _door_or_404(store, slug, role)
    if swatch not in door["swatches"]:
        raise HTTPException(status_code=404, detail="Swatch not assigned")
    attempts = store.list_attempts(slug, swatch)
    variant = door["variants"].get(swatch, {"chosen": None, "state": "pending"})
    if body.action == "pass":
        chosen = body.chosen or variant.get("chosen") or (attempts[-1] if attempts else None)
        if chosen not in attempts:
            raise HTTPException(status_code=400, detail="No such attempt")
        door["variants"][swatch] = {"chosen": chosen, "state": "passed"}
    elif body.action == "fail":
        variant["state"] = "failed"
        door["variants"][swatch] = variant
        worker.enqueue(slug, swatch)  # best-effort regen; cap just skips
    else:
        raise HTTPException(status_code=400, detail="action must be pass|fail")
    store.recompute_status(door)
    store.save(door)
    return _detail(store, worker, door)
```

- [ ] **Step 6: Implement backend/app.py**

```python
"""FastAPI entry: wires store/ledger/worker, mounts API + media + frontend."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import auth
from backend.auth import require_user
from backend.routers import doors, swatches
from backend.spend import SpendLedger
from backend.store import DoorStore
from backend.worker import GenerationWorker

load_dotenv()


def _default_generator_factory():
    from backend.generator import DoorGenerator
    return DoorGenerator(os.environ["GEMINI_API_KEY"])


def create_app(data_dir: Path | None = None, generator_factory=None) -> FastAPI:
    data_dir = data_dir or Path(os.environ.get("DATA_DIR", "/data"))
    generator_factory = generator_factory or _default_generator_factory
    app = FastAPI(title="Door Factory")
    app.state.data_dir = data_dir
    app.state.store = DoorStore(data_dir / "doors")
    app.state.ledger = SpendLedger(
        data_dir / "spend.json",
        daily_cap=int(os.environ.get("DAILY_IMAGE_CAP", "150")))
    app.state.worker = GenerationWorker(app.state.store, app.state.ledger,
                                        generator_factory)
    app.state.generator_factory = generator_factory

    app.include_router(auth.router, prefix="/api")
    app.include_router(doors.router, prefix="/api")
    app.include_router(swatches.router, prefix="/api")

    @app.get("/media/{path:path}")
    def media(path: str, _: str = Depends(require_user)) -> FileResponse:
        full = (data_dir / path).resolve()
        if not str(full).startswith(str(data_dir.resolve())) or not full.is_file():
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(full)

    app.mount("/media-swatches", StaticFiles(directory="swatches"), name="swatches")

    dist = Path("frontend/dist")
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


# Only build the real app when a data dir is actually configured (uvicorn entry).
if os.environ.get("DATA_DIR") or Path("/data").exists():
    app = create_app()
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_api.py -v` then `uv run pytest`
Expected: all PASS. Note: `/media/../pyproject.toml` — TestClient/httpx may normalize `..` before the route sees it; if that assertion fails with a 200, tighten the check to reject any `path` containing `".."` explicitly and re-run.

- [ ] **Step 8: Commit**

```bash
git add backend/ tests/test_api.py
git commit -m "feat: doors/swatches/review/export API with role gating and app wiring"
```

---

### Task 7: Frontend scaffold, login, API client

**Files:**
- Create: `frontend/` (Vite scaffold), `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/App.tsx`, `frontend/src/Login.tsx`, `frontend/vite.config.ts`

**Interfaces:**
- Consumes: API from Task 6
- Produces: `api.ts` exports used by Tasks 8-9: `login(password): Promise<{role: Role}>`, `me()`, `listDoors(): Promise<DoorSummary[]>`, `getDoor(slug): Promise<DoorDetail>`, `createDoor(form: FormData)`, `learnDoor(slug)`, `approveReplica(slug)`, `setSwatches(slug, swatches: string[])`, `listSwatches(material): Promise<Swatch[]>`, `generate(slug, swatch)`, `generateAll(slug)`, `review(slug, swatch, action, chosen?)`, `exportUrl(slug): string`, `reopenDoor(slug)`, `getSpend()`. Types: `Role = 'admin' | 'va'`; `DoorSummary {slug, name, type, status, swatch_count, passed_count, thumbnail_url}`; `DoorDetail = DoorSummary-ish & {style_notes, config, swatches: string[], replica_approved, variants: Record<string, {chosen: string|null, state: VariantState}>, attempts: Record<string, string[]>, inflight: Record<string, string>, errors: Record<string, string>, source_url, replica_url}`; `VariantState = 'pending'|'passed'|'failed'`; `Swatch {key, name, description, swatch_image_url}`.

- [ ] **Step 1: Scaffold Vite app**

```bash
cd /Users/jonathanhicks/dev/door-factory
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```

- [ ] **Step 2: vite.config.ts with dev proxy**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
      '/media-swatches': 'http://localhost:8000',
    },
  },
});
```

- [ ] **Step 3: Write types.ts and api.ts**

`api.ts` pattern — one helper, thin wrappers:

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', ...init });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? 'Request failed');
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export const login = (password: string) =>
  request<{ role: Role }>('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
// ... every function from the Interfaces block, same pattern.
// createDoor posts FormData with NO Content-Type header (browser sets it).
export const exportUrl = (slug: string) => `/api/doors/${slug}/export`;
```

- [ ] **Step 4: App.tsx — session gate + view switch**

```tsx
import { useEffect, useState } from 'react';
import { me } from './api';
import type { Role } from './types';
import Login from './Login';
import DoorList from './DoorList';

export default function App() {
  const [role, setRole] = useState<Role | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    me().then((r) => setRole(r.role)).catch(() => {}).finally(() => setChecked(true));
  }, []);

  if (!checked) return null;
  if (!role) return <Login onLogin={setRole} />;
  return <DoorList role={role} />;
}
```

`Login.tsx`: single password field + submit; on `ApiError` show "Wrong password"; calls `onLogin(role)`. Create a stub `DoorList.tsx` that renders `<p>doors</p>` so the build passes (Task 8 replaces it).

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: exits 0, `frontend/dist/` created

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat: frontend scaffold with login and typed API client"
```

---

### Task 8: DoorList + DoorDetail + Lightbox (the VA product)

**Files:**
- Create: `frontend/src/DoorList.tsx`, `frontend/src/DoorDetail.tsx`, `frontend/src/Lightbox.tsx`, `frontend/src/index.css` (replace scaffold css)
- Modify: `frontend/src/App.tsx` (route between list and detail via `useState<string | null>` selected slug — no router library)

**Interfaces:**
- Consumes: `api.ts` from Task 7
- Produces: `DoorList({role, onOpen, onOpenAdmin?})`, `DoorDetail({slug, role, onBack})`, `Lightbox({images: {url, label}[], startIndex, compareUrl, onClose})`

- [ ] **Step 1: DoorList.tsx**

Cards grid from `listDoors()`: source thumbnail (`<img src={thumbnail_url}>`), name, status badge, `passed_count/swatch_count passed`. Click card → `onOpen(slug)`. Admin additionally sees a "+ New Door" button (wired in Task 9) and `seeding` doors marked with a badge. Poll `listDoors()` every 10s while mounted.

- [ ] **Step 2: DoorDetail.tsx**

Layout: header (back button, door name, `N/M passed`, "Generate all remaining", "Export zip" enabled when `status === 'complete' || status === 'exported'`, as `<a href={exportUrl(slug)}>`). Left column: sticky `<img src={door.source_url}>`. Main: tile grid, one per `door.swatches`:

- Tile top: swatch name.
- Tile image: `variants[s]?.chosen` attempt or empty-state box; spinner overlay when `inflight[s]`; red error strip when `errors[s]` ("Generation failed — try again").
- Attempts strip under image when `attempts[s].length > 1`: small thumbnails, click sets that attempt as candidate `chosen` (call `review(slug, s, 'pass', attempt)` only on explicit Pass — strip click just changes which image displays locally via `useState`).
- Buttons: **Generate/Regenerate** → `generate(slug, s)`; on 429 show the cap message in a banner and disable all generate buttons; on 409 ignore (already queued). **Pass** → `review(slug, s, 'pass', displayedAttempt)`, tile border green. **Fail** → `review(slug, s, 'fail')`, tile border red (regen auto-queued by backend).
- Click main image → `<Lightbox>`.

Poll `getDoor(slug)` every 2s while any `inflight` key exists, else every 10s. Image URLs: attempt image = `/media/doors/${slug}/variants/${swatch}/${attempt}`.

- [ ] **Step 3: Lightbox.tsx**

Fixed full-screen overlay, dark backdrop. Shows current image at native resolution inside a pan/zoom container: wheel = zoom (scale 1-6, transform-origin at cursor), drag = pan, double-click = reset. Keyboard: `ArrowLeft`/`ArrowRight` step through `images` (all attempts of current swatch, then across swatches), `c` toggles to `compareUrl` (the source door), `Escape` closes. Implement zoom/pan by tracking `{scale, tx, ty}` in state and applying `transform: translate(tx,ty) scale(s)`; no library.

- [ ] **Step 4: index.css**

Minimal clean styling: system font stack, neutral grays, green/red/amber status colors, responsive tile grid (`grid-template-columns: repeat(auto-fill, minmax(240px, 1fr))`). No CSS framework.

- [ ] **Step 5: Verify build + manual check**

Run: `cd frontend && npm run build` — exits 0.
Then manual: `DATA_DIR=/tmp/df-manual ADMIN_PASSWORD=a VA_PASSWORD=v SESSION_SECRET=s GEMINI_API_KEY=x uv run uvicorn backend.app:app --port 8000` + `npm run dev`; log in as `v`; verify empty door list renders. (Real generation not needed — FakeGen only exists in tests, so just verify UI renders and login works.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat: VA door list, door detail with generate/pass/fail tiles, zoom lightbox"
```

---

### Task 9: Admin seed view + spend dashboard

**Files:**
- Create: `frontend/src/AdminSeed.tsx`, `frontend/src/AdminSpend.tsx`
- Modify: `frontend/src/DoorList.tsx` (wire "+ New Door" and spend link for admin), `frontend/src/DoorDetail.tsx` (admin extras: edit swatches, reopen exported)

**Interfaces:**
- Consumes: `api.ts` (`createDoor`, `learnDoor`, `approveReplica`, `setSwatches`, `listSwatches`, `getSpend`, `reopenDoor`)
- Produces: `AdminSeed({onDone})` — 3-step wizard; `AdminSpend({onBack})`

- [ ] **Step 1: AdminSeed.tsx — 3-step wizard in one component**

Step state machine `useState<'form' | 'replica' | 'swatches'>`:
1. **form**: name, type select (door/drawer_front), style notes textarea, door_style `<select>` (fetch keys: add `getStyles()` to api.ts hitting a new tiny `GET /api/styles` — add that endpoint to `backend/routers/swatches.py` returning `[{key, name, category}]` from `STYLES`, `require_admin`), corner_style select (sharp/bullnose), material_type select (wood/rtf), aspect_ratio select (9:16, 16:9, 1:1, 3:4, 4:3), file input. Submit → `createDoor(formData)` → step replica.
2. **replica**: call `learnDoor(slug)` (show "Learning… ~1 min" spinner — it is synchronous and slow); on success show source and replica-candidate side by side; buttons **Approve** (`approveReplica` → step swatches) and **Re-roll** (`learnDoor` again); on 502 show error + retry; on 429 show cap message.
3. **swatches**: checkbox grid from `listSwatches(material_type)` showing swatch chip images; Save → `setSwatches` → `onDone()`.

- [ ] **Step 2: AdminSpend.tsx**

Table from `getSpend()`: today's count vs cap prominent, then history rows (date, count) sorted descending.

- [ ] **Step 3: Admin extras in DoorDetail**

If `role === 'admin'`: "Edit swatches" button opening the same checkbox grid (pre-checked from `door.swatches`, saves via `setSwatches`); if `status === 'exported'` a "Reopen" button calling `reopenDoor`.

- [ ] **Step 4: Backend `GET /api/styles` + test**

Add to `backend/routers/swatches.py`:

```python
@router.get("/styles")
def list_styles(_: str = Depends(require_admin)) -> list[dict]:
    return [{"key": k, "name": s["name"], "category": s["category"]}
            for k, s in STYLES.items()]
```

Add to `tests/test_api.py`:

```python
def test_styles_admin_only(client):
    login(client, "adminpw")
    r = client.get("/api/styles")
    assert r.status_code == 200 and any(s["key"] == "recessed_panel" for s in r.json())
    login(client, "vapw")
    assert client.get("/api/styles").status_code == 403
```

Run: `uv run pytest tests/test_api.py -v` — PASS.

- [ ] **Step 5: Build + commit**

```bash
cd frontend && npm run build && cd ..
git add backend/routers/swatches.py tests/test_api.py frontend/src
git commit -m "feat: admin seeding wizard, spend dashboard, styles endpoint"
```

---

### Task 10: Dockerfile + Railway deploy

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `railway.json`, `docs/deploy.md`

**Interfaces:**
- Consumes: whole app
- Produces: running Railway service

- [ ] **Step 1: Dockerfile**

```dockerfile
# --- frontend build ---
FROM node:22-slim AS fe
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend .
RUN npm run build

# --- backend ---
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY backend backend
COPY swatches swatches
COPY --from=fe /fe/dist frontend/dist
ENV DATA_DIR=/data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`: `.venv`, `node_modules`, `frontend/dist`, `.git`, `/data`, `tests`, `docs`.

- [ ] **Step 2: Local Docker smoke**

```bash
docker build -t door-factory .
docker run -p 8000:8000 -v /tmp/df-data:/data \
  -e ADMIN_PASSWORD=a -e VA_PASSWORD=v -e SESSION_SECRET=s -e GEMINI_API_KEY=x \
  door-factory
```

Expected: `curl -s localhost:8000/api/auth/me` → 401 JSON; `curl -s localhost:8000/` → HTML.

- [ ] **Step 3: railway.json + deploy doc**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "DOCKERFILE" },
  "deploy": { "restartPolicyType": "ON_FAILURE" }
}
```

`docs/deploy.md` — exact click-path: create Railway project from GitHub repo; add volume mounted at `/data`; set env vars `GEMINI_API_KEY`, `ADMIN_PASSWORD`, `VA_PASSWORD`, `SESSION_SECRET` (long random), `DAILY_IMAGE_CAP=150`; generate domain; note "deploys kill in-flight generations — deploy while VA idle".

- [ ] **Step 4: Push + deploy (with Jonathan)**

Create GitHub repo (`gh repo create door-factory --private --source . --push`), connect in Railway, verify env + volume, open the URL, log in as admin. THIS STEP NEEDS JONATHAN — Railway account + real secrets.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore railway.json docs/deploy.md
git commit -m "chore: Dockerfile and Railway deploy config"
```

---

### Task 11: Real-API smoke test (manual, with Jonathan)

**Files:** none (checklist)

- [ ] **Step 1:** On the deployed URL as admin: seed one real door (real image, real `GEMINI_API_KEY`), learn, approve replica, assign 2 swatches.
- [ ] **Step 2:** Log in as VA (separate browser): generate both swatches, verify images appear, lightbox zoom works, pass both, export zip, open zip — 2 named pngs + door.json + signature.bin.
- [ ] **Step 3:** Verify spend dashboard shows the ~3 images spent; set `DAILY_IMAGE_CAP=1` temporarily, confirm generate blocks with the cap message, restore cap.
- [ ] **Step 4:** Redeploy (empty commit push) and confirm the door, images, and signature survive (volume persistence).
- [ ] **Step 5:** Tag `v0.1.0`: `git tag v0.1.0 && git push --tags`.
