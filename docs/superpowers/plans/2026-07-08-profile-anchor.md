# Profile Anchor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the Decore catalog's per-door cross-section drawing (`profile/3d-profile.jpg`) as an image anchor — to the learn call on every retry after an identity disqualification, and to profile-spec extraction and the identity judge whenever it exists — so profile geometry that text cannot convey (El Dorado's sharp step, skinny-shaker frame width) arrives as unambiguous visual evidence.

**Architecture:** A `profile_bytes: bytes | None` parameter threads from the driver (`scripts/onboard_wood.py`, which resolves the drawing from the catalog) through `onboard_replica` into (a) the learn path (`start_learning` → `_run_learn` → `learn_door_style`, gated to retry attempts only) and (b) the QA path (`extract_profile_spec`, `judge_replica_identity`, always on when available). Every prompt gains a conditional framing block that appears ONLY when the drawing is attached; with no drawing, every code path and prompt is byte-identical to today.

**Tech Stack:** Python 3.12 + uv, pytest, google-genai SDK, existing FastAPI backend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-08-profile-anchor-design.md`

## Global Constraints

- Read the Gemini key ONLY via `read_api_key()` from `scripts/_onboard_common.py` (the `.env` key; a stale zshrc export shadows it).
- NEVER delete anything under `output/.projects/`; never rewrite stored signature bytes. `store.update` / `store.save_upload` are the only write paths.
- `output/.qa/labels.json` (frozen 179-label variant calibration) must not be touched.
- Geometry stays in the image: the ONLY new prompt text allowed is the exact framing blocks quoted in Tasks 2–3. No other geometry prose anywhere (verified backfire: prose cues the wrong prior).
- When no drawing is attached, every prompt must be byte-identical to today's and every code path must behave exactly as today.
- Stage-A replica approval stays human; nothing in this plan approves a replica.
- The variant path (`generate_variation`, `reference_image_path`) is out of scope — do not touch it.
- Run tests with `uv run pytest <file> -v` from the repo root. Lint with `npm run lint` before each commit.
- End every commit message with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_011fv8yWTXmebbUKX4yWjwA2`

---

### Task 1: `profile_image_path` field on ProjectState

**Files:**
- Modify: `backend/state.py` (field after `profile_spec` at line 56; manifest save around line 244; manifest load around line 175)
- Test: `tests/test_state_profile_spec.py` (extend — follow the file's existing save/load-roundtrip pattern)

**Interfaces:**
- Consumes: existing `ProjectState` dataclass, `ProjectStore.save/get/update`.
- Produces: `ProjectState.profile_image_path: str | None = None`, persisted in `manifest.json` under key `"profile_image_path"`, updatable via `store.update(project_id, profile_image_path=...)`. Tasks 5–6 rely on this exact field/key name.

- [ ] **Step 1: Write the failing test**

Open `tests/test_state_profile_spec.py`, read its existing tests, and append (adapting the store-construction idiom already used in that file):

```python
def test_profile_image_path_roundtrips_and_defaults_none(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="El Dorado", product_type="Cabinet Door", material_type="wood")
    assert p.profile_image_path is None

    store.update(p.id, profile_image_path="/catalog/El Dorado/profile/3d-profile.jpg")
    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.profile_image_path == "/catalog/El Dorado/profile/3d-profile.jpg"
```

If the file's existing tests build the store differently (e.g. a helper), use that idiom instead — the assertions stay the same.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state_profile_spec.py -v`
Expected: new test FAILS (`AttributeError: ... 'profile_image_path'` or reloaded value is `None`).

- [ ] **Step 3: Implement**

In `backend/state.py`:

1. In the `ProjectState` dataclass, directly under `profile_spec` (line 56), add:

```python
    profile_image_path: str | None = None  # catalog 3d-profile cross-section (profile anchor)
```

2. In the manifest **save** dict (near line 244, next to `"profile_spec": project.profile_spec,`), add:

```python
            "profile_image_path": project.profile_image_path,
```

3. In the manifest **load** (near line 175, next to `project.profile_spec = data.get("profile_spec")`), add:

```python
                project.profile_image_path = data.get("profile_image_path")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_state_profile_spec.py tests/test_project_store.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
npm run lint && git add backend/state.py tests/test_state_profile_spec.py
git commit -m "feat(state): profile_image_path field for the catalog cross-section anchor"
```

---

### Task 2: Anchor slot on the learn path (generator + worker)

**Files:**
- Modify: `backend/generator.py` (`learn_door_style`, lines 396–553)
- Modify: `backend/worker.py` (`_run_learn` lines 239–317, `start_learning` lines 320–362)
- Test: Create `tests/test_learn_profile_anchor.py`

**Interfaces:**
- Consumes: `DoorGenerator.learn_door_style`, `DoorGenerator._call_with_retry(contents, config, label=...) -> (response, GenerationResult|None)`, `MIME_MAP`, `types.Part`, `OUTPUT_DIR` in worker.
- Produces: `learn_door_style(..., profile_image_path: Path | None = None)`; `_run_learn(..., profile_bytes: bytes | None = None)` (new last parameter); `start_learning(store, project, api_key, upload_bytes, *, learn_in_maple=False, aspect_ratio=None, temperature=0.0, style_notes="", profile_bytes: bytes | None = None)`. Task 4 calls `learn_fn(..., profile_bytes=...)` as a keyword argument.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_learn_profile_anchor.py`:

```python
"""learn_door_style profile anchor: parts assembly + framing line, no live API."""
from backend.generator import DoorGenerator, GenerationResult


def _capture_generator(monkeypatch):
    gen = DoorGenerator(api_key="test-key")
    captured = {}

    def fake_call(contents, config, label=""):
        captured["contents"] = contents
        return None, GenerationResult(image_data=None, thought_signature=None, error="stub")

    monkeypatch.setattr(gen, "_call_with_retry", fake_call)
    return gen, captured


def _image_parts(captured):
    return [p for p in captured["contents"][0].parts if p.inline_data is not None]


def _prompt_text(captured):
    return captured["contents"][0].parts[0].text


def test_learn_without_profile_is_unchanged(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    gen.learn_door_style(door_image_path=door)
    assert len(_image_parts(cap)) == 1
    assert "CROSS-SECTION" not in _prompt_text(cap)


def test_learn_with_profile_attaches_drawing_and_framing_line(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    drawing = tmp_path / "3d-profile.jpg"
    drawing.write_bytes(b"\xff\xd8xsec")
    gen.learn_door_style(door_image_path=door, profile_image_path=drawing)
    imgs = _image_parts(cap)
    assert len(imgs) == 2
    assert imgs[1].inline_data.data == b"\xff\xd8xsec"
    text = _prompt_text(cap)
    assert "CROSS-SECTION" in text and "line-art" in text


def test_learn_with_missing_profile_path_behaves_as_none(tmp_path, monkeypatch):
    gen, cap = _capture_generator(monkeypatch)
    door = tmp_path / "door.jpg"
    door.write_bytes(b"\xff\xd8hero")
    gen.learn_door_style(door_image_path=door,
                         profile_image_path=tmp_path / "missing.jpg")
    assert len(_image_parts(cap)) == 1
    assert "CROSS-SECTION" not in _prompt_text(cap)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_learn_profile_anchor.py -v`
Expected: FAIL — `learn_door_style() got an unexpected keyword argument 'profile_image_path'`.

- [ ] **Step 3: Implement the generator change**

In `backend/generator.py`:

1. Add the parameter to `learn_door_style` (after `style_notes: str = ""`, line ~406):

```python
        style_notes: str = "",
        profile_image_path: Path | None = None,
```

2. Directly AFTER the `if style_notes:` block (line ~481–482) and BEFORE the "Load the reference image" comment, add:

```python
        # Profile anchor (see docs/superpowers/specs/2026-07-08-profile-anchor-design.md):
        # the catalog cross-section carries profile geometry a front-facing photo
        # underdetermines. Geometry stays in the image — this framing line is the
        # only prose allowed about it.
        has_profile = profile_image_path is not None and profile_image_path.exists()
        if has_profile:
            prompt += (
                " PROFILE CROSS-SECTION: an additional small line drawing is "
                "attached — a cross-section of this exact door's edge, frame, and "
                "panel profile viewed edge-on. Reproduce this exact profile "
                "geometry. Do not copy the drawing's line-art rendering style."
            )
```

3. Directly AFTER the existing `parts: list[types.Part] = [...]` literal (lines 496–499) and BEFORE the maple-swatch block, add:

```python
        if has_profile:
            parts.append(
                types.Part.from_bytes(
                    data=profile_image_path.read_bytes(),
                    mime_type=MIME_MAP.get(profile_image_path.suffix.lower(), "image/jpeg"),
                    # The drawings are tiny (130-185px); HIGH resolution gives the
                    # model enough tokens to read the profile shape.
                    media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
                )
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_learn_profile_anchor.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Implement the worker pass-through**

In `backend/worker.py`:

1. `_run_learn` (line 239): add final parameter `profile_bytes: bytes | None = None`. Inside, write the drawing to a temp file beside the existing one and pass its path. The function becomes (only the changed lines shown — keep everything else exactly as is):

```python
def _run_learn(
    ...
    style_notes: str = "",
    profile_bytes: bytes | None = None,
) -> None:
    """Run learn_door_style in background thread."""
    temp_path = OUTPUT_DIR / f"temp_learn_{project_id}.png"
    profile_path = OUTPUT_DIR / f"temp_profile_{project_id}.jpg"
    try:
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(upload_bytes)
        if profile_bytes:
            profile_path.write_bytes(profile_bytes)

        generator = DoorGenerator(api_key=api_key, model=gemini_model)
        with _api_semaphore:
            result = generator.learn_door_style(
                door_image_path=temp_path,
                ...
                style_notes=style_notes,
                profile_image_path=profile_path if profile_bytes else None,
            )
```

and in the `finally:` block:

```python
    finally:
        temp_path.unlink(missing_ok=True)
        profile_path.unlink(missing_ok=True)
```

2. `start_learning` (line 320): add keyword parameter `profile_bytes: bytes | None = None` after `style_notes`, and append `profile_bytes` as the last argument of the `_executor.submit(_run_learn, ...)` call (after `style_notes`).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS (worker signature change is backward-compatible; nothing else calls it with positional trailing args).

- [ ] **Step 7: Commit**

```bash
npm run lint && git add backend/generator.py backend/worker.py tests/test_learn_profile_anchor.py
git commit -m "feat(learn): profile cross-section anchor slot on the learn path"
```

---

### Task 3: Cross-section witness for extraction and the identity judge

**Files:**
- Modify: `backend/qa/profile_spec.py` (`extract_profile_spec`, lines 95–111; new module constant)
- Modify: `backend/qa/judge.py` (`IDENTITY_PROMPT` lines 166–220, `judge_replica_identity` lines 263–285; new module constant)
- Test: `tests/test_profile_spec.py` and `tests/test_identity_judge.py` (extend)

**Interfaces:**
- Consumes: existing `EXTRACT_PROMPT`, `parse_facts`, `IDENTITY_PROMPT` (currently formatted with `facts=` only), `parse_identity`, `_mime`.
- Produces: `extract_profile_spec(client, source_bytes, *, model=DEFAULT_MODEL, profile_bytes: bytes | None = None)`; `judge_replica_identity(client, source_bytes, replica_bytes, facts, *, model=DEFAULT_MODEL, key="", profile_bytes: bytes | None = None)`. Task 4's closures pass `profile_bytes=` to both. `IDENTITY_PROMPT` gains an `{xsection}` placeholder — any other caller formatting it must now pass `xsection=""`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_profile_spec.py`:

```python
from types import SimpleNamespace

from backend.qa.profile_spec import extract_profile_spec


class FakeClient:
    """Captures generate_content calls; returns canned text."""
    def __init__(self, text):
        self.calls, self._text = [], text
        self.models = self

    def generate_content(self, *, model, contents):
        self.calls.append(contents)
        return SimpleNamespace(text=self._text)


FACTS_JSON = '{"facts": ["panel: raised, sharp vertical step", "trim_molding: none"]}'


def test_extract_without_drawing_is_unchanged():
    fake = FakeClient(FACTS_JSON)
    extract_profile_spec(fake, b"\xff\xd8src")
    parts = fake.calls[0][0].parts
    assert sum(1 for p in parts if p.inline_data is not None) == 1
    assert "CROSS-SECTION" not in parts[-1].text


def test_extract_with_drawing_attaches_second_image_and_block():
    fake = FakeClient(FACTS_JSON)
    extract_profile_spec(fake, b"\xff\xd8src", profile_bytes=b"\x89PNGxsec")
    parts = fake.calls[0][0].parts
    imgs = [p for p in parts if p.inline_data is not None]
    assert len(imgs) == 2 and imgs[1].inline_data.data == b"\x89PNGxsec"
    assert "CROSS-SECTION" in parts[-1].text
```

Append to `tests/test_identity_judge.py` (it already defines `_payload()`):

```python
from types import SimpleNamespace

from backend.qa.judge import judge_replica_identity


class FakeClient:
    def __init__(self, text):
        self.calls, self._text = [], text
        self.models = self

    def generate_content(self, *, model, contents):
        self.calls.append(contents)
        return SimpleNamespace(text=self._text)


def test_judge_without_drawing_prompt_and_parts_unchanged():
    fake = FakeClient(_payload())
    judge_replica_identity(fake, b"\xff\xd8src", b"\xff\xd8rep", ["panel: flat"])
    parts = fake.calls[0][0].parts
    assert sum(1 for p in parts if p.inline_data is not None) == 2
    assert "CROSS-SECTION" not in parts[-1].text


def test_judge_with_drawing_inserts_it_between_sample_and_replica():
    fake = FakeClient(_payload())
    judge_replica_identity(fake, b"\xff\xd8src", b"\xff\xd8rep", [],
                           profile_bytes=b"\x89PNGxsec")
    parts = fake.calls[0][0].parts
    imgs = [p for p in parts if p.inline_data is not None]
    assert len(imgs) == 3
    assert imgs[0].inline_data.data == b"\xff\xd8src"      # sample stays FIRST
    assert imgs[1].inline_data.data == b"\x89PNGxsec"      # drawing in the middle
    assert imgs[2].inline_data.data == b"\xff\xd8rep"      # replica stays LAST image
    assert "CROSS-SECTION" in parts[-1].text


def test_xsection_placeholder_collapses_cleanly_when_empty():
    p = IDENTITY_PROMPT.format(facts="- f", xsection="")
    # Original paragraph spacing must survive an empty block (byte-identical rule).
    assert "bullnose (fully rounded).\n\nProfile geometry is where" in p
    assert "CROSS-SECTION" not in p
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_profile_spec.py tests/test_identity_judge.py -v`
Expected: new tests FAIL (unexpected keyword `profile_bytes`; `KeyError: 'xsection'`).

- [ ] **Step 3: Implement `profile_spec.py`**

1. Below `EXTRACT_PROMPT`, add:

```python
# Appended ONLY when the catalog cross-section drawing is attached (profile anchor).
XSECTION_EXTRACT_BLOCK = (
    "A second image is attached: a line-drawing CROSS-SECTION of this same door's "
    "edge, frame, and panel profile viewed edge-on. It shows the true geometry a "
    "front-facing photo cannot — use it to state profile character precisely "
    "(raise shape: sharp vertical step vs gradual bevel; frame thickness; inside "
    "and outside edge profiles)."
)
```

2. Replace the body of `extract_profile_spec` (lines 95–111) with:

```python
def extract_profile_spec(client, source_bytes: bytes, *,
                         model: str = DEFAULT_MODEL,
                         profile_bytes: bytes | None = None) -> list[str]:
    prompt = (EXTRACT_PROMPT if profile_bytes is None
              else EXTRACT_PROMPT + "\n\n" + XSECTION_EXTRACT_BLOCK)
    parts = [types.Part.from_bytes(data=source_bytes, mime_type=_mime(source_bytes))]
    if profile_bytes is not None:
        parts.append(types.Part.from_bytes(data=profile_bytes,
                                           mime_type=_mime(profile_bytes)))
    parts.append(types.Part.from_text(text=prompt))
    contents = [types.Content(role="user", parts=parts)]
    last = ""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=model, contents=contents)
            return parse_facts(resp.text or "")
        except Exception as exc:  # noqa: BLE001 - retry then re-raise
            last = str(exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"profile spec extraction failed: {last}")
```

(The only changes vs today: the `profile_bytes` keyword, the conditional prompt, and the conditional second image part.)

- [ ] **Step 4: Implement `judge.py`**

1. In `IDENTITY_PROMPT`, change the seam between the edges-first paragraph and the characterize-then-compare paragraph. Today it reads:

```
...square vs eased
vs chamfered vs bullnose (fully rounded).

Profile geometry is where the remaining near-misses fail...
```

Change to (inserting the placeholder line between the paragraphs):

```
...square vs eased
vs chamfered vs bullnose (fully rounded).
{xsection}
Profile geometry is where the remaining near-misses fail...
```

2. Below `IDENTITY_PROMPT`, add:

```python
# Formatted into {xsection} ONLY when the catalog cross-section is attached;
# an empty string restores the original paragraph spacing exactly.
XSECTION_JUDGE_BLOCK = (
    "\nA line-drawing CROSS-SECTION of the SAMPLE door's edge, frame, and panel "
    "profile (viewed edge-on) is attached between the sample photo and the "
    "replica. It shows the sample's TRUE profile geometry — use it to resolve "
    "profile-character questions: raise shape (sharp vertical step vs gradual "
    "bevel), frame thickness, inside and outside edge profiles. The REPLICA must "
    "match the drawing's geometry; the drawing's line-art rendering style is "
    "irrelevant.\n"
)
```

3. Update `judge_replica_identity` (lines 263–275) to:

```python
def judge_replica_identity(
    client, source_bytes: bytes, replica_bytes: bytes, facts: list[str],
    *, model: str = DEFAULT_MODEL, key: str = "",
    profile_bytes: bytes | None = None,
) -> IdentityResult:
    fallback = "- (no stated facts; rely on the region sweep)"
    fact_lines = "\n".join(f"- {f}" for f in facts) if facts else fallback
    prompt = IDENTITY_PROMPT.format(
        facts=fact_lines,
        xsection=XSECTION_JUDGE_BLOCK if profile_bytes is not None else "",
    )
    parts = [types.Part.from_bytes(data=source_bytes, mime_type=_mime(source_bytes))]
    if profile_bytes is not None:
        parts.append(types.Part.from_bytes(data=profile_bytes,
                                           mime_type=_mime(profile_bytes)))
    parts.append(types.Part.from_bytes(data=replica_bytes, mime_type=_mime(replica_bytes)))
    parts.append(types.Part.from_text(text=prompt))
    contents = [types.Content(role="user", parts=parts)]
```

(The retry loop below the `contents` line is unchanged.) The drawing goes BETWEEN sample and replica because the prompt's first paragraph promises "The FIRST image is the SAMPLE… The LAST image is an AI-generated replica" — the replica must stay the last image.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_profile_spec.py tests/test_identity_judge.py -v`
Expected: all PASS (old and new).

- [ ] **Step 6: Commit**

```bash
npm run lint && git add backend/qa/profile_spec.py backend/qa/judge.py tests/test_profile_spec.py tests/test_identity_judge.py
git commit -m "feat(qa): cross-section witness for profile extraction and the identity judge"
```

---

### Task 4: Escalation gating in `onboard_replica`

**Files:**
- Modify: `backend/onboarding.py` (`onboard_replica`, lines 274–390)
- Test: `tests/test_onboard_identity.py` (extend)

**Interfaces:**
- Consumes: Task 2's `learn_fn(..., profile_bytes=...)` keyword; Task 3's `extract_profile_spec(..., profile_bytes=...)` and `judge_replica_identity(..., profile_bytes=...)`.
- Produces: `onboard_replica(..., profile_bytes: bytes | None = None)`. Injected `identity_fn(src, rep, facts)` and `extract_fn(src)` keep their 3-arg/1-arg signatures — the default closures capture `profile_bytes`. Task 5 passes `profile_bytes=` from the driver.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_onboard_identity.py`:

```python
def test_profile_anchor_attaches_only_after_first_disqualification(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_profiles = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_profiles.append(kw.get("profile_bytes"))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["raise too gradual"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
        profile_bytes=b"xsec",
    )
    assert res.status == QUEUED_READY and res.attempts == 2
    assert seen_profiles == [None, b"xsec"]   # attempt 1 native, retries anchored


def test_no_profile_bytes_means_none_on_every_attempt(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_profiles = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_profiles.append(kw.get("profile_bytes"))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["d"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_READY
    assert seen_profiles == [None, None]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_onboard_identity.py -v`
Expected: first new test FAILS — `onboard_replica() got an unexpected keyword argument 'profile_bytes'`.

- [ ] **Step 3: Implement**

In `backend/onboarding.py`, `onboard_replica`:

1. Add the parameter after `extract_fn=None`:

```python
    extract_fn=None,
    profile_bytes: bytes | None = None,
) -> OnboardResult:
```

2. Extend the docstring's final paragraph with:

```
    ``profile_bytes`` (the catalog cross-section drawing, when the driver found
    one) always reaches extraction and the identity judge; the LEARN call gets it
    only on retries — the first attempt is exactly today's path, and the anchor
    joins after the first disqualification.
```

3. Update the default closures (the `if identity_fn is None:` / `if extract_fn is None:` block) so both pass the drawing through:

```python
        if identity_fn is None:
            def identity_fn(src, rep, facts):  # closure mirrors learn_fn's lazy import
                return judge_replica_identity(_client, src, rep, facts,
                                              key=f"{project_id}:identity",
                                              profile_bytes=profile_bytes)
        if extract_fn is None:
            def extract_fn(src):
                return extract_profile_spec(_client, src, profile_bytes=profile_bytes)
```

4. In the loop's `learn_fn(...)` call, add the gated keyword:

```python
        learn_fn(
            store, store.get(project_id), api_key, upload_bytes,
            learn_in_maple=cond.learn_in_maple,
            aspect_ratio=aspect_ratio,
            temperature=cond.temperature,
            style_notes=notes,
            profile_bytes=profile_bytes if attempt >= 1 else None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_onboard_identity.py tests/test_onboarding_core.py tests/test_onboard_replica.py -v`
Expected: all PASS (existing stub `learn_fn`s take `**kw`, so the new keyword is absorbed).

- [ ] **Step 5: Commit**

```bash
npm run lint && git add backend/onboarding.py tests/test_onboard_identity.py
git commit -m "feat(onboard): profile anchor joins learn retries after the first disqualification"
```

---

### Task 5: Driver resolves the drawing (`onboard_wood.py`)

**Files:**
- Modify: `scripts/onboard_wood.py` (refactor `resolve` lines 75–89; new `resolve_profile`; wire `main` lines 125–169)
- Test: `tests/test_onboard_wood_spec.py` (extend — it loads the script via `importlib`, module name `onboard_wood`)

**Interfaces:**
- Consumes: Task 1's `profile_image_path` store field; Task 4's `onboard_replica(..., profile_bytes=...)`.
- Produces: `resolve(name, catalog=CATALOG) -> Path | None` (unchanged behavior, now testable), `resolve_profile(name, catalog=CATALOG) -> Path | None`. Task 6 imports `resolve_profile` from this module.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_onboard_wood_spec.py`:

```python
def _fake_catalog(tmp_path, with_profile=True):
    d = tmp_path / "raised-panel" / "El Dorado"
    (d / "hero").mkdir(parents=True)
    (d / "hero" / "door.jpg").write_bytes(b"hero")
    if with_profile:
        (d / "profile").mkdir()
        (d / "profile" / "3d-profile.jpg").write_bytes(b"xsec")
    return tmp_path


def test_resolve_profile_finds_drawing(tmp_path):
    cat = _fake_catalog(tmp_path)
    p = onboard_wood.resolve_profile("El Dorado", catalog=cat)
    assert p is not None and p.read_bytes() == b"xsec"


def test_resolve_profile_missing_returns_none(tmp_path):
    cat = _fake_catalog(tmp_path, with_profile=False)
    assert onboard_wood.resolve_profile("El Dorado", catalog=cat) is None


def test_resolve_profile_prefix_match_like_dylan_7_8(tmp_path):
    d = tmp_path / "raised-panel" / "Dylan-7-8"
    (d / "profile").mkdir(parents=True)
    (d / "profile" / "3d-profile.jpg").write_bytes(b"xsec")
    assert onboard_wood.resolve_profile("Dylan", catalog=tmp_path) is not None


def test_resolve_hero_still_works_with_catalog_override(tmp_path):
    cat = _fake_catalog(tmp_path)
    p = onboard_wood.resolve("El Dorado", catalog=cat)
    assert p is not None and p.read_bytes() == b"hero"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_onboard_wood_spec.py -v`
Expected: FAIL — `module 'onboard_wood' has no attribute 'resolve_profile'`.

- [ ] **Step 3: Implement the resolver refactor**

In `scripts/onboard_wood.py`, replace `resolve` (lines 75–89) with a shared matcher plus two thin lookups:

```python
def _door_dirs(name: str, catalog: Path = CATALOG):
    """Catalog folders matching a door name, across both profile folders."""
    lname = name.lower()
    for sub, _ in _PROFILE_STYLE:
        base = catalog / sub
        if not base.exists():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir():
                dn = d.name.lower()
                if dn == lname or dn.startswith(lname + "-") or dn.startswith(lname + " "):
                    yield d


def resolve(name: str, catalog: Path = CATALOG) -> Path | None:
    """Locate a wood door's hero image in the catalog (either profile folder)."""
    for d in _door_dirs(name, catalog):
        door = d / "hero" / "door.jpg"
        if door.exists():
            return door
    return None


def resolve_profile(name: str, catalog: Path = CATALOG) -> Path | None:
    """Locate a door's cross-section drawing (the profile anchor), if any."""
    for d in _door_dirs(name, catalog):
        drawing = d / "profile" / "3d-profile.jpg"
        if drawing.exists():
            return drawing
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_onboard_wood_spec.py -v`
Expected: all PASS.

- [ ] **Step 5: Wire `main()`**

In `main()`:

1. After the `style is None` skip block (line ~136), add:

```python
        profile = resolve_profile(name)
        profile_bytes = profile.read_bytes() if profile else None
        if profile_bytes is None:
            print(f"[{name}] note — no 3d-profile cross-section in catalog; "
                  "onboarding without anchor")
```

2. Extend the existing `store.update(...)` call (line 152) with the path:

```python
        store.update(proj.id, door_style=style, corner_style="sharp",
                     style_notes=notes, selected_swatches=palette,
                     profile_image_path=str(profile) if profile else None)
```

3. Pass the bytes to `onboard_replica` (line 159):

```python
        res = onboard_replica(store, proj.id, key, upload, attempt_cap=args.cap,
                              min_score=3, spend=spend, allow_maple=True,
                              profile_bytes=profile_bytes)
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
npm run lint && git add scripts/onboard_wood.py tests/test_onboard_wood_spec.py
git commit -m "feat(onboard): driver resolves the catalog cross-section and threads it through"
```

---

### Task 6: Re-calibration support in `qa_replica_eval.py`

**Files:**
- Modify: `scripts/qa_replica_eval.py`
- Test: `tests/test_qa_replica_eval.py` (extend — follow that file's existing import idiom for the script module)

**Interfaces:**
- Consumes: Task 5's `resolve_profile` (import: `from onboard_wood import resolve_profile` — the scripts dir is already on `sys.path` in this script); Task 3's `profile_bytes=` keywords; Task 1's manifest key `"profile_image_path"`.
- Produces: `door_code(project_name) -> str`, `_cache_path(project_id, anchored) -> Path`; eval rows gain `"anchored": bool`. This is the LAST code task; the eval RUN itself (live spend) happens in Task 7.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_qa_replica_eval.py` (using however that file already imports the script module — keep its idiom; the names below assume the module is available as `qa_replica_eval`):

```python
def test_door_code_strips_product_suffixes():
    assert qa_replica_eval.door_code("El Dorado Cabinet Door") == "El Dorado"
    assert qa_replica_eval.door_code("Apache Drawer Front") == "Apache"
    assert qa_replica_eval.door_code("Laredo") == "Laredo"


def test_cache_path_separates_anchored_from_plain():
    plain = qa_replica_eval._cache_path("p1", anchored=False)
    anchored = qa_replica_eval._cache_path("p1", anchored=True)
    assert plain.name == "p1.json"
    assert anchored.name == "p1__anchored.json"
    assert plain != anchored
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_qa_replica_eval.py -v`
Expected: new tests FAIL (missing attributes).

- [ ] **Step 3: Implement**

In `scripts/qa_replica_eval.py`:

1. Add the import next to the other script-local import (after `from _onboard_common import read_api_key`):

```python
from onboard_wood import resolve_profile  # noqa: E402
```

2. Add the helpers below `session_replica_decisions`:

```python
def door_code(project_name: str) -> str:
    """Catalog door name from a project name ('El Dorado Cabinet Door' -> 'El Dorado')."""
    for suffix in (" Cabinet Door", " Drawer Front"):
        if project_name.endswith(suffix):
            return project_name[: -len(suffix)]
    return project_name


def _cache_path(project_id: str, anchored: bool) -> Path:
    """Anchored extractions cache separately — the drawing changes the facts."""
    name = f"{project_id}__anchored.json" if anchored else f"{project_id}.json"
    return SPEC_CACHE / name


def _profile_bytes(manifest_data: dict, name: str) -> bytes | None:
    """The door's cross-section: stored manifest path first, catalog lookup second."""
    stored = manifest_data.get("profile_image_path")
    if stored and Path(stored).exists():
        return Path(stored).read_bytes()
    p = resolve_profile(door_code(name))
    return p.read_bytes() if p else None
```

3. Update `_cached_facts` to accept and forward the drawing:

```python
def _cached_facts(client, project_id: str, source: Path,
                  profile_bytes: bytes | None = None) -> list[str]:
    SPEC_CACHE.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(project_id, anchored=profile_bytes is not None)
    if cache.exists():
        return json.loads(cache.read_text())
    facts = extract_profile_spec(client, source.read_bytes(), profile_bytes=profile_bytes)
    cache.write_text(json.dumps(facts))
    return facts
```

4. In `main()`'s row loop:
   - Load the manifest ONCE into a dict: replace the `name = ...` line with

```python
        manifest_data = json.loads(manifest.read_text()) if manifest.exists() else {}
        name = manifest_data.get("name", pid)
```

   - After the source/replica existence check, add:

```python
        profile_bytes = _profile_bytes(manifest_data, name)
```

   - Pass it to both calls:

```python
            facts = _cached_facts(client, pid, source, profile_bytes=profile_bytes)
        ...
        result = judge_replica_identity(client, source.read_bytes(), replica.read_bytes(),
                                        facts, key=f"{pid}:{dec['image_id']}",
                                        profile_bytes=profile_bytes)
```

   - Record it in the row dict:

```python
        rows.append({"name": name, "project_id": pid, "operator": dec["verdict"],
                     "disqualified": result.disqualified, "defects": result.defects,
                     "anchored": profile_bytes is not None})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_qa_replica_eval.py -v`
Expected: all PASS.

- [ ] **Step 5: Full suite + commit**

```bash
uv run pytest -q && npm run lint
git add scripts/qa_replica_eval.py tests/test_qa_replica_eval.py
git commit -m "feat(qa): eval passes the cross-section anchor; anchored spec cache"
```

---

### Task 7: Live acceptance — OPERATOR-GATED (main session, not a subagent)

**Files:** none (runs only). Every live step costs real money (~$0.134/image); get the operator's go-ahead before each numbered run and report results between them.

- [ ] **Step 1: Full suite green**

Run: `uv run pytest -q` and `npm run lint`
Expected: all PASS, no lint errors.

- [ ] **Step 2: El Dorado (the known 10-attempt failure)**

`--force` without `--respec` reuses the operator-corrected `profile_spec` — do NOT pass `--respec`.

Run: `uv run python scripts/onboard_wood.py --only "El Dorado" --force --cap 5 --ceiling 3`

Expected: attempt 1 fails identity as before (sharp step vs bevel); retries carry the anchor. Success = a `READY` (identity-clean) replica. Check the replica image for line-art style leak before calling it a win, then have the operator review it in the app's Review tab.

- [ ] **Step 3: Journey and Dylan (worst skinny shakers)**

Run: `uv run python scripts/onboard_wood.py --doors "Journey,Dylan" --force --cap 5 --ceiling 5`

Expected: anchored retries beat the frame-fattening prior. Operator reviews.

- [ ] **Step 4: Re-calibration (honest before/after)**

Run: `uv run python scripts/qa_replica_eval.py`

Expected: a fresh catch/false-fail table against the frozen 97-verdict window (anchored extractions cache under `output/.qa/profile_specs/*__anchored.json`; the old cache is untouched). Report the before (52–62% catch / 10–19% false-fail) vs after numbers to the operator. The judge stays a re-roll assist regardless.

- [ ] **Step 5: Record the outcome**

Update `docs/superpowers/specs/2026-07-08-profile-anchor-design.md` Status line with the live results and re-calibration table; commit:

```bash
git add docs/superpowers/specs/2026-07-08-profile-anchor-design.md
git commit -m "docs(spec): profile anchor live-test + re-calibration outcome"
```
