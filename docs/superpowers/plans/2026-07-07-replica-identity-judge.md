# Replica Identity Judge (Profile-Spec Pipeline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the replica quality gate with an identity test: a per-door profile
spec (extracted once from the source photo) guides the learn prompt from attempt 1 and
powers a fact-by-fact + 7-region-sweep identity judge whose named defects feed the
next attempt.

**Architecture:** `backend/qa/profile_spec.py` (new) owns extraction prompt/parse;
`judge_replica_identity()` in `backend/qa/judge.py` (new function, old rubric
untouched) verifies facts and sweeps regions; `backend/onboarding.py`'s
`onboard_replica` orchestrates extract → condition → generate → verify → defect-guided
re-learn; `scripts/qa_replica_eval.py` (new) is the calibration gate against the
2026-07-06/07 operator verdicts.

**Tech Stack:** Python 3.12, google-genai SDK, pytest, uv.

## Global Constraints

- Vision model for extraction AND identity judging: `gemini-3.1-pro-preview` (same as `backend/qa/judge.py:15 DEFAULT_MODEL`).
- Disqualify bar: any nameable geometric difference. Grain figure, lighting, shadow, camera angle NEVER disqualify.
- Generated replicas are 9:16, usually taller than the sample: repeating elements continuing at the same pitch is CORRECT; a different pitch/spacing/profile IS a defect. Structural counts (panels, stiles, rails, center stile) are absolute; repeating-pattern facts are pitch/profile, never absolute counts.
- 7-region anatomy checklist (exact keys, used by extraction AND judge): `outside_edge`, `stiles_rails`, `joints_corners`, `inside_edge`, `panel`, `trim_molding`, `top_rail_arch`. No region may be skipped; unremarkable regions get a verifiable "plain/none" fact.
- Stage-A is human: `onboard_replica` NEVER approves a replica. Nothing under `output/.projects/` is ever deleted; signature bytes never rewritten.
- The variant judge (`RUBRIC_PROMPT`, `VisionJudge.judge`) and the frozen 179-label calibration (`output/.qa/labels.json`) are untouched.
- Fallbacks: extraction fails → onboard proceeds today's way (no facts, generic ladder), logged. Identity judge errors on an attempt → that attempt gates on the old `replica_queue_ready` instead.
- Calibration acceptance: catches ≥ 80% of operator rejects AND false-fails ≤ 20% of operator approves (verdicts in `output/.qa/approvals.json`, `kind=="replica"`, `decided_at >= "2026-07-06T10:00"`).
- Old min-score judge keeps running (it already runs in the QA lane); it is a secondary signal only — the identity verdict gates.

---

### Task 1: Profile spec extraction module

**Files:**
- Create: `backend/qa/profile_spec.py`
- Test: `tests/test_profile_spec.py`

**Interfaces:**
- Consumes: nothing project-internal (google-genai `client.models.generate_content`).
- Produces (later tasks rely on these exact names):
  - `REGIONS: tuple[str, ...]` — the 7 region keys from Global Constraints, in order.
  - `EXTRACT_PROMPT: str`
  - `parse_facts(text: str) -> list[str]` — raises `ValueError` on bad payloads.
  - `profile_facts_note(facts: list[str]) -> str` — one-line learn-prompt block; `""` for empty facts.
  - `extract_profile_spec(client, source_bytes: bytes, *, model: str = "gemini-3.1-pro-preview") -> list[str]` — raises `RuntimeError` after 3 failed attempts.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_profile_spec.py
import pytest

from backend.qa.profile_spec import (
    EXTRACT_PROMPT, REGIONS, parse_facts, profile_facts_note,
)


def test_regions_are_the_seven_anatomy_keys_in_order():
    assert REGIONS == (
        "outside_edge", "stiles_rails", "joints_corners", "inside_edge",
        "panel", "trim_molding", "top_rail_arch",
    )


def test_extract_prompt_names_every_region_and_scale_rule():
    for region in REGIONS:
        assert region in EXTRACT_PROMPT
    assert "9:16" in EXTRACT_PROMPT
    assert "never an absolute count" in EXTRACT_PROMPT


def test_parse_facts_accepts_fenced_json():
    text = '```json\n{"facts": ["outside_edge: square, eased", "panel: flat recess"]}\n```'
    assert parse_facts(text) == ["outside_edge: square, eased", "panel: flat recess"]


def test_parse_facts_rejects_empty_and_oversized():
    with pytest.raises(ValueError):
        parse_facts('{"facts": []}')
    with pytest.raises(ValueError):
        parse_facts('{"facts": [""]}')
    with pytest.raises(ValueError):
        parse_facts('{"facts": %s}' % (["f"] * 13))
    with pytest.raises(ValueError):
        parse_facts('{"nope": 1}')


def test_profile_facts_note_single_line_and_empty():
    note = profile_facts_note(["panel: flat recess", "frame: 2.25in flat"])
    assert "\n" not in note
    assert "panel: flat recess" in note and "frame: 2.25in flat" in note
    assert profile_facts_note([]) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_profile_spec.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.qa.profile_spec'`

- [ ] **Step 3: Write the module**

```python
# backend/qa/profile_spec.py
"""Per-door profile spec: verifiable geometric facts extracted from the source photo.

One extraction per door. The facts guide the learn prompt from attempt 1 AND power
judge_replica_identity's fact-by-fact verification. Facts must be individually
checkable; grain, color and lighting are never facts.
"""

import json
import re
import time

from google.genai import types

DEFAULT_MODEL = "gemini-3.1-pro-preview"

# The fixed door-anatomy checklist. Extraction emits one fact per region;
# the identity judge sweeps the same regions. Order matters for prompts.
REGIONS = (
    "outside_edge",   # door's outer edge profile (square, eased, roundover, bevel)
    "stiles_rails",   # frame member widths, equal or not, grain direction
    "joints_corners", # miter (45° lines) vs cope-and-stick vs butt
    "inside_edge",    # frame-to-panel transition (step, bevel, ogee, routed sticking)
    "panel",          # flat/raised/beadboard/plank/louver; raise profile / recess depth
    "trim_molding",   # applied molding present or absent; profile if present
    "top_rail_arch",  # square, cathedral, radius
)

EXTRACT_PROMPT = f"""You are a cabinet-door profile analyst. The image is a SAMPLE
photo of a real cabinet door. Extract its geometry as a short list of individually
VERIFIABLE facts, one per region, prefixed with the region name:

{chr(10).join(f"- {r}" for r in REGIONS)}

Rules:
- No region may be skipped. An unremarkable region gets an explicit plain/none fact
  (e.g. "trim_molding: none").
- Facts must be checkable by looking: structural counts, pitch/spacing ratios, widths
  (relative to a repeating element unless an absolute width is visually obvious),
  edge/bevel shapes, panel type and recess depth, joint type, arch geometry.
- Structural counts are absolute (panels, stiles, rails, center stile).
- The replica will be rendered at 9:16, likely taller than this sample. For repeating
  elements (louver slats, beadboard grooves, plank boards) state pitch/spacing/profile
  relative to the elements themselves, never an absolute count.
- Never mention wood species, color, grain figure, lighting, or photo quality.
- 7 to 12 facts total, each one line.

Reply with ONLY a JSON object, no markdown fences:
{{"facts": ["region: fact", ...]}}"""

_MAX_FACTS = 12


def parse_facts(text: str) -> list[str]:
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    facts = data.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("facts must be a non-empty list")
    if len(facts) > _MAX_FACTS:
        raise ValueError(f"too many facts: {len(facts)}")
    out = [str(f).strip() for f in facts]
    if any(not f for f in out):
        raise ValueError("empty fact")
    return out


def profile_facts_note(facts: list[str]) -> str:
    """One-line learn-prompt block (minimal prose; the facts ARE the guidance)."""
    if not facts:
        return ""
    return "Match these geometric facts of the sample EXACTLY: " + " | ".join(facts)


def _mime(data: bytes) -> str:
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def extract_profile_spec(client, source_bytes: bytes, *, model: str = DEFAULT_MODEL) -> list[str]:
    parts = [
        types.Part.from_bytes(data=source_bytes, mime_type=_mime(source_bytes)),
        types.Part.from_text(text=EXTRACT_PROMPT),
    ]
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_profile_spec.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/qa/profile_spec.py tests/test_profile_spec.py
git commit -m "feat(qa): profile spec extraction — verifiable per-region geometry facts"
```

---

### Task 2: Persist `profile_spec` on the project

**Files:**
- Modify: `backend/state.py` (ProjectState fields ~line 48; `_save_project` manifest dict ~line 234; load path ~line 148)
- Test: `tests/test_state_profile_spec.py`

**Interfaces:**
- Produces: `ProjectState.profile_spec: list[str] | None = None`, round-tripped through `manifest.json`, settable via `store.update(project_id, profile_spec=[...])` (update() already accepts any dataclass field).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_profile_spec.py
from pathlib import Path

from backend.state import ProjectStore


def test_profile_spec_round_trips_through_manifest(tmp_path: Path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Talbot", product_type="Cabinet Door", material_type="wood")
    assert store.get(p.id).profile_spec is None

    facts = ["panel: louver slats, tight pitch", "trim_molding: none"]
    store.update(p.id, profile_spec=facts)

    reloaded = ProjectStore(persist_dir=tmp_path).get(p.id)
    assert reloaded.profile_spec == facts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state_profile_spec.py -q`
Expected: FAIL — `update()` raises `ValueError: Unknown ProjectState fields: ['profile_spec']`

- [ ] **Step 3: Implement**

In `backend/state.py`:

1. Add to the `ProjectState` dataclass, right after `style_notes: str = ""`:

```python
    profile_spec: list[str] | None = None  # verifiable geometry facts (profile_spec.py)
```

2. In `_save_project`'s manifest dict, after `"style_notes": project.style_notes,`:

```python
            "profile_spec": project.profile_spec,
```

3. In the load path, after `project.base_image_id = data.get("base_image_id")` (keep the migration comment block intact):

```python
                project.profile_spec = data.get("profile_spec")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_state_profile_spec.py -q && uv run pytest tests/ -q`
Expected: PASS, full suite green (no other test asserts the manifest key set)

- [ ] **Step 5: Commit**

```bash
git add backend/state.py tests/test_state_profile_spec.py
git commit -m "feat(state): persist profile_spec facts on the project manifest"
```

---

### Task 3: Identity judge

**Files:**
- Modify: `backend/qa/judge.py` (append below `VisionJudge`; do NOT touch `RUBRIC_PROMPT`, `JudgeResult`, or `VisionJudge`)
- Test: `tests/test_identity_judge.py`

**Interfaces:**
- Consumes: `from backend.qa.profile_spec import REGIONS` (Task 1).
- Produces:
  - `IdentityResult` dataclass: `key: str`, `fact_checks: list[dict]`, `region_sweep: dict`, `defects: list[str]`, `disqualified: bool = True`, `verdict: str = "ok"` ("ok" | "error"), `reason: str = ""`.
  - `IDENTITY_PROMPT: str` (has `{facts}` placeholder).
  - `parse_identity(key: str, text: str) -> IdentityResult` — raises on malformed payloads.
  - `judge_replica_identity(client, source_bytes: bytes, replica_bytes: bytes, facts: list[str], *, model: str = DEFAULT_MODEL, key: str = "") -> IdentityResult` — returns `verdict="error"` after 3 failed attempts (never raises).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_identity_judge.py
import json

import pytest

from backend.qa.judge import IDENTITY_PROMPT, IdentityResult, parse_identity
from backend.qa.profile_spec import REGIONS


def _payload(**overrides):
    base = {
        "fact_checks": [{"fact": "panel: flat recess", "holds": True, "observed": "flat recess"}],
        "region_sweep": {r: "matches" for r in REGIONS},
        "defects": [],
        "disqualified": False,
    }
    base.update(overrides)
    return json.dumps(base)


def test_prompt_names_regions_916_and_carveouts():
    for region in REGIONS:
        assert region in IDENTITY_PROMPT
    assert "9:16" in IDENTITY_PROMPT
    assert "grain" in IDENTITY_PROMPT.lower() and "lighting" in IDENTITY_PROMPT.lower()


def test_clean_replica_not_disqualified():
    r = parse_identity("k", _payload())
    assert isinstance(r, IdentityResult)
    assert r.disqualified is False and r.defects == [] and r.verdict == "ok"


def test_failed_fact_disqualifies_even_if_model_says_ok():
    r = parse_identity("k", _payload(
        fact_checks=[{"fact": "panel: flat", "holds": False, "observed": "raised"}],
        disqualified=False,
    ))
    assert r.disqualified is True
    assert any("panel: flat" in d for d in r.defects)


def test_region_difference_disqualifies_and_becomes_defect():
    sweep = {r: "matches" for r in REGIONS}
    sweep["trim_molding"] = "replica adds applied molding; sample has none"
    r = parse_identity("k", _payload(region_sweep=sweep, disqualified=False))
    assert r.disqualified is True
    assert any("applied molding" in d for d in r.defects)


def test_missing_region_is_malformed():
    sweep = {r: "matches" for r in REGIONS[:-1]}  # drop one region
    with pytest.raises(ValueError):
        parse_identity("k", _payload(region_sweep=sweep))


def test_fenced_reply_is_parsed():
    r = parse_identity("k", "```json\n" + _payload() + "\n```")
    assert r.verdict == "ok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_identity_judge.py -q`
Expected: FAIL with `ImportError: cannot import name 'IDENTITY_PROMPT'`

- [ ] **Step 3: Implement (append to `backend/qa/judge.py`)**

```python
# --- Replica identity judging (profile-spec pipeline) -----------------------
# The similarity rubric above still governs variants; replicas gate on THIS.

from backend.qa.profile_spec import REGIONS  # noqa: E402  (grouped with its feature)

IDENTITY_PROMPT = """You are comparing two cabinet door photos for GEOMETRIC IDENTITY.
The FIRST image is the SAMPLE photo of the real door. The LAST image is an
AI-generated replica rendered at 9:16 — it may be TALLER than the sample. Repeating
elements (louver slats, grooves, planks) continuing at the same pitch on a taller door
is CORRECT; a different pitch, spacing ratio, or element profile IS a defect.

The replica must be the IDENTICAL door design. Wood grain figure, color, lighting,
shadows and camera angle are NEVER defects. Any nameable geometric difference IS.

Step 1 — verify each stated fact against the replica:
{facts}

Step 2 — region sweep. For EACH region below, compare sample vs replica and answer
"matches" or state the difference in one sentence:
- outside_edge: the door's outer edge profile
- stiles_rails: frame member widths and proportions
- joints_corners: miter 45-degree lines vs cope-and-stick vs butt
- inside_edge: the frame-to-panel transition profile (step, bevel, ogee, routing)
- panel: type, raise profile or recess depth, surface texture geometry
- trim_molding: applied molding present/absent and its profile
- top_rail_arch: square vs cathedral vs radius geometry

Reply with ONLY a JSON object, no markdown fences:
{{"fact_checks": [{{"fact": "...", "holds": true, "observed": "..."}}, ...],
"region_sweep": {{"outside_edge": "matches", "stiles_rails": "...", "joints_corners": "...",
"inside_edge": "...", "panel": "...", "trim_molding": "...", "top_rail_arch": "..."}},
"defects": ["one-line geometric difference", ...],
"disqualified": true/false}}"""


@dataclass
class IdentityResult:
    key: str
    fact_checks: list[dict] = field(default_factory=list)
    region_sweep: dict = field(default_factory=dict)
    defects: list[str] = field(default_factory=list)
    disqualified: bool = True
    verdict: str = "ok"  # "ok" | "error"
    reason: str = ""


def parse_identity(key: str, text: str) -> IdentityResult:
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    sweep = data.get("region_sweep") or {}
    missing = [r for r in REGIONS if r not in sweep]
    if missing:
        raise ValueError(f"region_sweep missing regions: {missing}")
    checks = [
        {"fact": str(c.get("fact", "")), "holds": bool(c.get("holds")),
         "observed": str(c.get("observed", ""))}
        for c in data.get("fact_checks") or []
    ]
    defects = [str(d) for d in data.get("defects") or []]
    # Derive disqualification — the model's flag alone is not trusted. A failed
    # fact or a non-matching region always disqualifies and always yields a defect.
    for c in checks:
        if not c["holds"]:
            line = f"fact failed — {c['fact']} (observed: {c['observed']})"
            if not any(c["fact"] in d for d in defects):
                defects.append(line)
    for region in REGIONS:
        answer = str(sweep[region]).strip()
        if answer.lower() != "matches":
            if not any(answer in d for d in defects):
                defects.append(f"{region}: {answer}")
    disqualified = bool(data.get("disqualified")) or bool(defects)
    return IdentityResult(key=key, fact_checks=checks, region_sweep=sweep,
                          defects=defects, disqualified=disqualified)


def judge_replica_identity(
    client, source_bytes: bytes, replica_bytes: bytes, facts: list[str],
    *, model: str = DEFAULT_MODEL, key: str = "",
) -> IdentityResult:
    fact_lines = "\n".join(f"- {f}" for f in facts) if facts else "- (no stated facts; rely on the region sweep)"
    prompt = IDENTITY_PROMPT.format(facts=fact_lines)
    parts = [
        types.Part.from_bytes(data=source_bytes, mime_type=_mime(source_bytes)),
        types.Part.from_bytes(data=replica_bytes, mime_type=_mime(replica_bytes)),
        types.Part.from_text(text=prompt),
    ]
    contents = [types.Content(role="user", parts=parts)]
    last = ""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=model, contents=contents)
            return parse_identity(key, resp.text or "")
        except Exception as exc:  # noqa: BLE001 - retry then error result
            last = str(exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return IdentityResult(key=key, verdict="error", reason=last)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_identity_judge.py tests/test_profile_spec.py -q && uv run pytest tests/ -q`
Expected: PASS; full suite green (existing judge tests unaffected — `RUBRIC_PROMPT` untouched, so `config_hash` and verdict caches are stable)

- [ ] **Step 5: Commit**

```bash
git add backend/qa/judge.py tests/test_identity_judge.py
git commit -m "feat(qa): replica identity judge — fact verification + 7-region sweep"
```

---

### Task 4: Wire identity gate + defect-guided re-learn into `onboard_replica`

**Files:**
- Modify: `backend/onboarding.py` (`_Attempt`, `OnboardResult`, `onboard_replica`, `_finalize`; add `defect_note`)
- Modify: `scripts/onboard_wood.py` (add `--respec` flag)
- Test: `tests/test_onboard_identity.py`

**Interfaces:**
- Consumes: `extract_profile_spec`, `profile_facts_note` (Task 1); `judge_replica_identity`, `IdentityResult` (Task 3); `ProjectState.profile_spec` (Task 2).
- Produces:
  - `defect_note(defects: list[str]) -> str` — corrective block, ≤5 defects, `""` for empty.
  - `onboard_replica(..., identity_fn=None, extract_fn=None)` — injectable for tests; `None` → real implementations. `identity_fn(source_bytes, replica_bytes, facts) -> IdentityResult`; `extract_fn(source_bytes) -> list[str]`.
  - `OnboardResult.defects: list[str] = field(default_factory=list)` — the returned attempt's defects (drivers log them).
  - Gate: an attempt is queue-ready when `identity.verdict == "ok" and not identity.disqualified and verdict.get("geometry") != "drift"`. Identity `verdict == "error"` → that attempt falls back to `replica_queue_ready(verdict, min_score)`.
  - Best-of at cap: fewest defects among identity-ok attempts; ties → higher `score_sum`; ties → later attempt. Attempts whose identity errored count as 99 defects.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_onboard_identity.py
"""onboard_replica with identity gate: stubbed learn/extract/identity, real store."""
from pathlib import Path

from backend.onboarding import (
    QUEUED_NEEDS_HUMAN, QUEUED_READY, defect_note, onboard_replica,
)
from backend.qa.judge import IdentityResult
from backend.state import ProjectStore

GOOD_SCORES = {k: 4 for k in (
    "panel_layout_match", "proportions_match", "profile_character_match",
    "material_realism", "swatch_fidelity")}


def _verdict():
    return {"qa_status": "done", "scores": dict(GOOD_SCORES), "geometry": None}


def make_learn_fn(counter):
    """Synchronous stub: each call installs a new 'replica' and a done verdict."""
    def learn_fn(store, project, api_key, upload_bytes, **kw):
        counter["n"] += 1
        bid = f"img{counter['n']}"
        store.update(project.id, learning_status="done", base_image_id=bid,
                     base_door_image=f"replica{counter['n']}".encode(),
                     qa_verdicts={bid: _verdict()})
    return learn_fn


def _store(tmp_path):
    store = ProjectStore(persist_dir=tmp_path)
    p = store.create(name="Talbot", product_type="Cabinet Door", material_type="wood")
    return store, p.id


def test_defect_note_lists_defects_and_caps_at_five():
    note = defect_note(["a", "b", "c", "d", "e", "f"])
    assert "a" in note and "e" in note and "f" not in note
    assert defect_note([]) == ""


def test_clean_identity_queues_ready_and_stores_facts(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    facts = ["panel: louver, tight pitch"]
    calls = []

    def identity_fn(src, rep, f):
        calls.append(f)
        return IdentityResult(key="k", disqualified=False, defects=[])

    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None,
        learn_fn=make_learn_fn(counter),
        extract_fn=lambda src: facts, identity_fn=identity_fn,
    )
    assert res.status == QUEUED_READY and res.attempts == 1
    assert store.get(pid).profile_spec == facts   # extracted once, persisted
    assert calls == [facts]                       # judge saw the facts


def test_defects_feed_next_attempt_conditioning(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    seen_notes = []
    inner = make_learn_fn(counter)

    def learn_fn(store_, project, api_key, upload, **kw):
        seen_notes.append(kw.get("style_notes", ""))
        inner(store_, project, api_key, upload, **kw)

    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["slats too widely spaced"]),
        IdentityResult(key="k", disqualified=False, defects=[]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=3, spend=None, learn_fn=learn_fn,
        extract_fn=lambda src: ["panel: louver"], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_READY and res.attempts == 2
    assert "slats too widely spaced" in seen_notes[1]   # defect-guided re-learn
    assert "panel: louver" in seen_notes[0]             # facts guide attempt 1


def test_cap_hit_finalizes_fewest_defects(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}
    verdicts = [
        IdentityResult(key="k", disqualified=True, defects=["d1", "d2"]),
        IdentityResult(key="k", disqualified=True, defects=["d1"]),        # best
        IdentityResult(key="k", disqualified=True, defects=["d1", "d2", "d3"]),
    ]
    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=2, spend=None,
        learn_fn=make_learn_fn(counter),
        extract_fn=lambda src: [], identity_fn=lambda *a: verdicts.pop(0),
    )
    assert res.status == QUEUED_NEEDS_HUMAN and res.attempts == 3
    assert res.defects == ["d1"]
    assert store.get(pid).base_image_id == "img2"       # best attempt restored


def test_extraction_failure_falls_back_to_old_gate(tmp_path):
    store, pid = _store(tmp_path)
    counter = {"n": 0}

    def broken_extract(src):
        raise RuntimeError("boom")

    res = onboard_replica(
        store, pid, "key", b"src", attempt_cap=1, spend=None,
        learn_fn=make_learn_fn(counter), extract_fn=broken_extract,
        identity_fn=lambda *a: IdentityResult(key="k", verdict="error", reason="api"),
    )
    # identity errored -> old min-score gate; GOOD_SCORES pass min 3
    assert res.status == QUEUED_READY
    assert store.get(pid).profile_spec is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_onboard_identity.py -q`
Expected: FAIL with `ImportError: cannot import name 'defect_note'`

- [ ] **Step 3: Implement in `backend/onboarding.py`**

Add near `_LOW_DIM_NOTE`:

```python
_MAX_DEFECT_LINES = 5


def defect_note(defects: list[str]) -> str:
    """Corrective block for the next learn attempt, built from named defects.

    One line per defect (cap 5), minimal prose — specific facts beat verbose notes.
    """
    if not defects:
        return ""
    lines = "; ".join(f"({i + 1}) {d}" for i, d in enumerate(defects[:_MAX_DEFECT_LINES]))
    return ("Your previous attempt differed from the sample. Fix each of these "
            f"EXACTLY: {lines}.")
```

Extend `_Attempt` and `OnboardResult`:

```python
@dataclass
class OnboardResult:
    code: str
    status: str
    attempts: int = 0
    best_min_score: int = 0
    best_sum: int = 0
    base_image_id: str | None = None
    reason: str = ""
    defects: list[str] = field(default_factory=list)


@dataclass
class _Attempt:
    verdict: dict
    base_id: str
    image: bytes | None
    signature: bytes | None
    identity: object | None = None  # IdentityResult | None
```

Rewrite `onboard_replica` (same signature plus the two new kwargs; docstring updated):

```python
def onboard_replica(
    store,
    project_id: str,
    api_key: str,
    upload_bytes: bytes,
    *,
    attempt_cap: int = 5,
    min_score: int = 3,
    aspect_ratio: str = "9:16",
    allow_maple: bool = True,
    spend: Spend | None = None,
    timeout: float = 240.0,
    learn_fn=None,
    identity_fn=None,
    extract_fn=None,
) -> OnboardResult:
    """Learn → identity-judge → defect-guided re-learn until no disqualifier or the
    attempt cap. Never approves the replica (Stage-A stays human, D-001).

    The profile spec (verifiable geometry facts) is extracted once per project and
    guides every attempt's conditioning; the identity judge verifies the replica
    against it fact-by-fact plus a 7-region sweep. Named defects become the next
    attempt's corrective. The old min-score judge still runs in the QA lane; an
    attempt gates on it only when the identity judge errors.
    """
    if learn_fn is None:
        from backend.worker import start_learning as learn_fn  # lazy: avoid import cycle
    if identity_fn is None or extract_fn is None:
        from google import genai

        from backend.qa.judge import judge_replica_identity
        from backend.qa.profile_spec import extract_profile_spec

        _client = genai.Client(api_key=api_key)
        if identity_fn is None:
            def identity_fn(src, rep, facts):  # noqa: E731-style closure, mirrors learn_fn
                return judge_replica_identity(_client, src, rep, facts,
                                              key=f"{project_id}:identity")
        if extract_fn is None:
            def extract_fn(src):
                return extract_profile_spec(_client, src)

    from backend.qa.profile_spec import profile_facts_note

    project = store.get(project_id)
    code = getattr(project, "name", project_id)
    base_notes = getattr(project, "style_notes", "") or ""

    # Profile spec: reuse a stored one; extract once otherwise. Extraction failure
    # falls back to today's behavior (no facts) — logged, never fatal.
    facts = getattr(project, "profile_spec", None)
    if facts is None:
        try:
            facts = extract_fn(upload_bytes)
            store.update(project_id, profile_spec=facts)
        except Exception as exc:  # noqa: BLE001
            print(f"[{code}] profile spec extraction failed ({exc}) — proceeding without")
            facts = None
    facts_note = profile_facts_note(facts or [])
    if facts_note:
        base_notes = f"{base_notes} {facts_note}".strip()

    low_dim: str | None = None
    defects: list[str] = []
    attempts: list[_Attempt] = []

    for attempt in range(attempt_cap + 1):
        if spend is not None and not spend.can_charge():
            best = _finalize(store, project_id, attempts, min_score)
            if best.status != ONBOARD_ERROR:
                best.status = CEILING_HIT
                best.reason = "run spend ceiling reached"
            return best

        cond = learn_conditioning(attempt, low_dim, allow_maple=allow_maple)
        corrective = defect_note(defects) or cond.extra_note
        notes = f"{base_notes} {corrective}".strip() if corrective else base_notes

        learn_fn(
            store, store.get(project_id), api_key, upload_bytes,
            learn_in_maple=cond.learn_in_maple,
            aspect_ratio=aspect_ratio,
            temperature=cond.temperature,
            style_notes=notes,
        )
        if spend is not None:
            spend.charge()

        base_id, verdict = wait_for_replica_verdict(store, project_id, timeout)
        if verdict is None:
            return OnboardResult(code=code, status=ONBOARD_ERROR, attempts=attempt + 1,
                                 reason="learn or judge failed/timed out")

        p = store.get(project_id)
        identity = identity_fn(upload_bytes, p.base_door_image, facts or [])
        attempts.append(_Attempt(verdict=verdict, base_id=base_id,
                                 image=p.base_door_image, signature=p.learned_signature,
                                 identity=identity))

        identity_ok = getattr(identity, "verdict", "error") == "ok"
        if identity_ok:
            clean = (not identity.disqualified) and verdict.get("geometry") != "drift"
        else:
            clean = replica_queue_ready(verdict, min_score)  # identity errored: old gate

        if clean:
            s = _scores(verdict)
            return OnboardResult(
                code=code, status=QUEUED_READY, attempts=attempt + 1,
                best_min_score=min((s.get(k, 0) for k in SCORE_KEYS), default=0),
                best_sum=score_sum(verdict), base_image_id=base_id,
                defects=list(getattr(identity, "defects", []) or []),
            )
        defects = list(getattr(identity, "defects", []) or []) if identity_ok else []
        low_dim = lowest_dim(verdict)

    return _finalize(store, project_id, attempts, min_score)
```

Update `_finalize`'s best-of (replace the `best_i` line and result):

```python
def _attempt_rank(a: "_Attempt") -> tuple:
    """Sort key: fewest defects (identity-ok), then highest score sum. Attempts
    whose identity errored rank as 99 defects."""
    ident = a.identity
    n_def = (len(getattr(ident, "defects", []) or [])
             if getattr(ident, "verdict", "error") == "ok" else 99)
    return (n_def, -score_sum(a.verdict))


def _finalize(store, project_id: str, attempts: list[_Attempt], min_score: int) -> OnboardResult:
    """Cap reached without a clean replica: make the best attempt active and flag it."""
    code = getattr(store.get(project_id), "name", project_id)
    if not attempts:
        return OnboardResult(code=code, status=ONBOARD_ERROR, reason="no attempts produced")

    best_i = min(range(len(attempts)),
                 key=lambda i: (_attempt_rank(attempts[i]), -i))  # ties → later attempt
    best = attempts[best_i]
    if best_i != len(attempts) - 1 and best.image is not None:
        store.set_active_replica(
            project_id, image=best.image, signature=best.signature,
            base_image_id=best.base_id, verdict=best.verdict,
        )

    s = best.verdict.get("scores", {})
    return OnboardResult(
        code=code, status=QUEUED_NEEDS_HUMAN, attempts=len(attempts),
        best_min_score=min((s.get(k, 0) for k in SCORE_KEYS), default=0),
        best_sum=score_sum(best.verdict), base_image_id=best.base_id,
        reason="no attempt reached the quality bar within the cap",
        defects=list(getattr(best.identity, "defects", []) or []),
    )
```

(Note: `-i` inside the min key inverts tie order so the LATER attempt wins, matching
the old `>=` behavior. `_attempt_rank` already negates score_sum.)

In `scripts/onboard_wood.py`, add after the `--force` argument:

```python
    ap.add_argument("--respec", action="store_true",
                    help="re-extract the profile spec even if one is stored")
```

and in the per-door loop, right before `res = onboard_replica(...)`:

```python
        if args.respec:
            store.update(proj.id, profile_spec=None)
```

Also print defects on non-ready results, after the existing status print:

```python
        if res.defects:
            print(f"[{name}]   defects: {'; '.join(res.defects[:5])}", flush=True)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_onboard_identity.py tests/test_onboard_driver.py -q && uv run pytest tests/ -q`
Expected: PASS. If `tests/test_onboard_driver.py` asserts the old queue-ready gate on
`onboard_replica`, inject `identity_fn=lambda *a: IdentityResult(key="k", verdict="error")`
is NOT the fix — those tests exercise policy functions (`replica_queue_ready` etc.)
which are unchanged; only fix a test if it calls `onboard_replica` without stubs and
now hits the real network path (then inject a stub `identity_fn`/`extract_fn`).

- [ ] **Step 5: Commit**

```bash
git add backend/onboarding.py scripts/onboard_wood.py tests/test_onboard_identity.py
git commit -m "feat(onboard): identity gate + defect-guided re-learn in the replica loop"
```

---

### Task 5: Calibration eval gate

**Files:**
- Create: `scripts/qa_replica_eval.py`
- Test: `tests/test_qa_replica_eval.py`

**Interfaces:**
- Consumes: `extract_profile_spec`, `parse_facts` (Task 1); `judge_replica_identity` (Task 3); `read_api_key` from `scripts/_onboard_common.py`.
- Produces (pure, unit-tested): `session_replica_decisions(approvals: list[dict], since: str) -> list[dict]`, `resolve_replica_image(project_dir: Path, image_id: str) -> Path | None`, `rates(rows: list[dict]) -> dict`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_qa_replica_eval.py
import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "qa_replica_eval", Path(__file__).resolve().parents[1] / "scripts" / "qa_replica_eval.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)

SINCE = "2026-07-06T10:00"


def test_session_replica_decisions_filters_kind_and_date():
    rows = [
        {"kind": "replica", "verdict": "rejected", "decided_at": "2026-07-06T10:22", "project_id": "a", "image_id": "i1"},
        {"kind": "variant", "verdict": "rejected", "decided_at": "2026-07-06T10:22", "project_id": "b", "image_id": "i2"},
        {"kind": "replica", "verdict": "approved", "decided_at": "2026-07-03T09:00", "project_id": "c", "image_id": "i3"},
        {"kind": "replica", "verdict": "approved", "decided_at": "2026-07-07T02:26", "project_id": "d", "image_id": "i4"},
    ]
    got = ev.session_replica_decisions(rows, SINCE)
    assert [r["project_id"] for r in got] == ["a", "d"]


def test_resolve_replica_image_active_then_versions(tmp_path: Path):
    d = tmp_path / "proj"
    (d / "versions" / "v1").mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"base_image_id": "cur"}))
    (d / "base_door.bin").write_bytes(b"current")
    (d / "versions" / "v1" / "meta.json").write_text(json.dumps({"base_image_id": "old"}))
    (d / "versions" / "v1" / "base_door.bin").write_bytes(b"old")

    assert ev.resolve_replica_image(d, "cur") == d / "base_door.bin"
    assert ev.resolve_replica_image(d, "old") == d / "versions" / "v1" / "base_door.bin"
    assert ev.resolve_replica_image(d, "gone") is None


def test_rates():
    rows = [
        {"operator": "rejected", "disqualified": True},
        {"operator": "rejected", "disqualified": False},
        {"operator": "approved", "disqualified": False},
        {"operator": "approved", "disqualified": True},
        {"operator": "approved", "disqualified": False},
    ]
    r = ev.rates(rows)
    assert r["catch_rate"] == 0.5          # 1 of 2 rejects caught
    assert r["false_fail_rate"] == 1 / 3   # 1 of 3 approves failed
    assert r["accepted"] is False          # gate: >=0.80 and <=0.20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_qa_replica_eval.py -q`
Expected: FAIL — `FileNotFoundError` / `AttributeError` (script doesn't exist)

- [ ] **Step 3: Write the script**

```python
#!/usr/bin/env python
"""Calibration gate for the replica identity judge.

Replays the 2026-07-06/07 operator review session (approvals.json, kind=replica)
through extraction + identity judging and reports catch/false-fail rates against
the acceptance bar (catch >= 80% of rejects, false-fail <= 20% of approves).

Profile specs are cached per project under output/.qa/profile_specs/ so prompt
iterations re-run cheaply. Rows whose images can't be resolved are listed, never
silently dropped.

Usage:
    uv run python scripts/qa_replica_eval.py [--limit N] [--since 2026-07-06T10:00]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _onboard_common import read_api_key  # noqa: E402
from google import genai  # noqa: E402

from backend.qa.judge import judge_replica_identity  # noqa: E402
from backend.qa.profile_spec import extract_profile_spec  # noqa: E402

PROJECTS = Path("output/.projects")
APPROVALS = Path("output/.qa/approvals.json")
SPEC_CACHE = Path("output/.qa/profile_specs")
REPORT = Path("output/.qa/replica_eval.json")
DEFAULT_SINCE = "2026-07-06T10:00"
CATCH_BAR, FALSE_FAIL_BAR = 0.80, 0.20


def session_replica_decisions(approvals: list[dict], since: str) -> list[dict]:
    """Operator replica verdicts in the calibration window, oldest first."""
    rows = [r for r in approvals
            if r.get("kind") == "replica" and r.get("decided_at", "") >= since]
    rows.sort(key=lambda r: r.get("decided_at", ""))
    return rows


def resolve_replica_image(project_dir: Path, image_id: str) -> Path | None:
    """Find the exact replica image an approval refers to: the active base door
    if ids match, else the archived version with that base_image_id."""
    manifest = project_dir / "manifest.json"
    if manifest.exists():
        if json.loads(manifest.read_text()).get("base_image_id") == image_id:
            p = project_dir / "base_door.bin"
            return p if p.exists() else None
    versions = project_dir / "versions"
    if versions.exists():
        for v in sorted(versions.iterdir()):
            meta = v / "meta.json"
            if meta.exists() and json.loads(meta.read_text()).get("base_image_id") == image_id:
                p = v / "base_door.bin"
                return p if p.exists() else None
    return None


def rates(rows: list[dict]) -> dict:
    rejects = [r for r in rows if r["operator"] == "rejected"]
    approves = [r for r in rows if r["operator"] == "approved"]
    catch = (sum(1 for r in rejects if r["disqualified"]) / len(rejects)) if rejects else 0.0
    false_fail = (sum(1 for r in approves if r["disqualified"]) / len(approves)) if approves else 0.0
    return {"catch_rate": catch, "false_fail_rate": false_fail,
            "rejects": len(rejects), "approves": len(approves),
            "accepted": catch >= CATCH_BAR and false_fail <= FALSE_FAIL_BAR}


def _cached_facts(client, project_id: str, source: Path) -> list[str]:
    SPEC_CACHE.mkdir(parents=True, exist_ok=True)
    cache = SPEC_CACHE / f"{project_id}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    facts = extract_profile_spec(client, source.read_bytes())
    cache.write_text(json.dumps(facts))
    return facts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N rows")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    args = ap.parse_args()

    client = genai.Client(api_key=read_api_key())
    approvals = json.loads(APPROVALS.read_text())["approvals"]
    decisions = session_replica_decisions(approvals, args.since)
    if args.limit:
        decisions = decisions[: args.limit]

    rows, skipped = [], []
    for dec in decisions:
        pid = dec["project_id"]
        pdir = PROJECTS / pid
        manifest = pdir / "manifest.json"
        name = json.loads(manifest.read_text()).get("name", pid) if manifest.exists() else pid
        source = pdir / "upload.bin"
        replica = resolve_replica_image(pdir, dec["image_id"])
        if not source.exists() or replica is None:
            skipped.append((name, "missing source" if not source.exists() else "image not found"))
            continue
        try:
            facts = _cached_facts(client, pid, source)
        except RuntimeError as exc:
            skipped.append((name, f"extraction failed: {exc}"))
            continue
        result = judge_replica_identity(client, source.read_bytes(), replica.read_bytes(),
                                        facts, key=f"{pid}:{dec['image_id']}")
        if result.verdict == "error":
            skipped.append((name, f"judge error: {result.reason}"))
            continue
        rows.append({"name": name, "project_id": pid, "operator": dec["verdict"],
                     "disqualified": result.disqualified, "defects": result.defects})
        mark = "✓" if (dec["verdict"] == "rejected") == result.disqualified else "✗"
        print(f"{mark} {name:30s} operator={dec['verdict']:9s} judge_disq={result.disqualified}"
              f"  {('; '.join(result.defects[:2]))[:80]}")

    summary = rates(rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"rows": rows, "summary": summary,
                                  "skipped": skipped}, indent=2))
    print(f"\ncatch_rate={summary['catch_rate']:.0%} (bar >= {CATCH_BAR:.0%})"
          f"   false_fail_rate={summary['false_fail_rate']:.0%} (bar <= {FALSE_FAIL_BAR:.0%})"
          f"   -> {'ACCEPTED' if summary['accepted'] else 'NOT ACCEPTED'}")
    if skipped:
        print(f"skipped {len(skipped)} rows (not silently dropped):")
        for name, why in skipped:
            print(f"  - {name}: {why}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests, then a 4-row smoke of the real eval**

Run: `uv run pytest tests/test_qa_replica_eval.py -q`
Expected: PASS

Run: `uv run python scripts/qa_replica_eval.py --limit 4`
Expected: 4 printed rows with ✓/✗ marks, a rates line, report written. (Spends ~8
vision calls; this is the cheap smoke, not the gate.)

- [ ] **Step 5: Commit**

```bash
git add scripts/qa_replica_eval.py tests/test_qa_replica_eval.py
git commit -m "feat(qa): replica identity calibration eval against operator verdicts"
```

---

### Task 6: Run the calibration gate and iterate (OPERATOR-GATED)

This task spends vision calls (~60 extractions + ~62 identity judgments per full
pass; extractions cache) and its outcome is a ship/no-ship decision the operator
signs off on.

- [ ] **Step 1: Full suite green first**

Run: `uv run pytest -q && uv run ruff check backend/ scripts/ tests/`
Expected: PASS / All checks passed

- [ ] **Step 2: Full eval pass**

Run: `uv run python scripts/qa_replica_eval.py`
Expected: per-row table + `catch_rate` / `false_fail_rate` + ACCEPTED or NOT ACCEPTED.

- [ ] **Step 3: If NOT ACCEPTED — iterate on prompts, not thresholds**

Diagnose from `output/.qa/replica_eval.json`:
- Missed rejects (operator rejected, judge passed): the region sweep or facts were too
  coarse — sharpen `EXTRACT_PROMPT` region wording or add sweep emphasis in
  `IDENTITY_PROMPT` for the regions that missed (read the rejected doors' defect lists
  to see which region should have caught it).
- False-failed approves (operator approved, judge disqualified): usually grain/lighting
  leakage or 9:16 count complaints — strengthen the carve-out / pitch wording.
After each prompt change: `rm -rf output/.qa/profile_specs` only if `EXTRACT_PROMPT`
changed (judge-only changes reuse cached facts), re-run Step 2. Each full pass costs
roughly a dollar-scale amount of vision calls; do not loop more than ~4 times without
presenting findings to the operator.

- [ ] **Step 4: Present results to the operator for sign-off**

Show the rates, the per-door table, and 2–3 example defect lists. The operator decides
ship (identity gate stays default in `onboard_replica`) or hold.

- [ ] **Step 5: Commit any prompt iterations**

```bash
git add backend/qa/profile_spec.py backend/qa/judge.py
git commit -m "tune(qa): identity/extraction prompt iteration from calibration eval"
```

---

## Self-Review

- **Spec coverage:** extraction module + region checklist (Task 1), manifest
  persistence + `--respec` (Tasks 2, 4), identity judge + region sweep + 9:16 rule +
  carve-outs (Task 3), generation guidance + defect-guided re-learn + fewest-defects
  best-of + fallbacks (Task 4), calibration gate + acceptance bar (Tasks 5–6). Old
  rubric, variant path, frozen labels untouched (all tasks).
- **Placeholder scan:** none — every code step has complete code; Task 5's Step 1
  includes its own corrected assertion.
- **Type consistency:** `REGIONS` defined in `profile_spec.py`, imported by judge and
  tests; `IdentityResult` fields consistent across Tasks 3–5; `identity_fn(src, rep,
  facts) -> IdentityResult` and `extract_fn(src) -> list[str]` match between Task 4's
  implementation and tests; `OnboardResult.defects` consumed by the driver print and
  `_finalize`.
