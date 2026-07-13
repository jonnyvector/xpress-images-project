"""Autonomous onboarding policy — pure decisions for the replica/variant loops.

No I/O. These functions take stored ``qa_verdict`` dicts (the schema written by
``backend.qa.qa_lane._verdict_dict``) and return decisions; the driver
(``scripts/onboard_rtf.py``) and ``onboard_replica`` own all side effects.

Key fact (Explore, D-005): a replica's ``verdict``/``gates_as`` string is always
``needs_human`` by policy, so it carries no quality signal — quality is read off
the numeric ``scores`` dict plus the advisory ``geometry`` field.
"""

import time
from dataclasses import dataclass, field

# The five judge dimensions stored under qa_verdict["scores"].
SCORE_KEYS = (
    "panel_layout_match",
    "proportions_match",
    "profile_character_match",
    "material_realism",
    "swatch_fidelity",
)

# Variant-phase actions (D-003).
VARIANT_AUTO_ACCEPT = "auto_accept"
VARIANT_REGENERATE = "regenerate"
VARIANT_ESCALATE = "escalate"

# Corrective note per lowest-scoring dimension, appended to style_notes on a
# re-learn attempt (D-006). Empty string = no useful corrective for that dim.
_LOW_DIM_NOTE = {
    "profile_character_match": (
        "Match the sample's edge and frame profile EXACTLY — reproduce every "
        "step, cove and bevel of the profile shown in the sample photo."
    ),
    "panel_layout_match": (
        "Match the sample's panel layout EXACTLY — same recessed-vs-raised "
        "state and the same frame-to-panel proportions as the sample."
    ),
    "proportions_match": (
        "Match the sample's stile and rail widths and overall door proportions "
        "EXACTLY; do not stretch, compress or thin any member."
    ),
    "material_realism": (
        "Render a clean, realistic smooth thermofoil surface — no banding, "
        "seams or artifacts."
    ),
    "swatch_fidelity": "",
}


def _scores(verdict: dict) -> dict:
    return verdict.get("scores") or {}


def is_done(verdict: dict) -> bool:
    """A verdict is usable only once QA finished and wrote scores."""
    return bool(verdict) and verdict.get("qa_status") == "done" and bool(_scores(verdict))


def replica_queue_ready(verdict: dict, min_score: int) -> bool:
    """True when a judged replica is good enough to queue for operator approval.

    Every dimension must be >= ``min_score`` and geometry must not be measured
    as ``drift``. Unmeasurable / None geometry (raised, slab, arched styles)
    passes the geometry check — the gate is scores-only there.
    """
    if not is_done(verdict):
        return False
    if verdict.get("geometry") == "drift":
        return False
    scores = _scores(verdict)
    return min(scores.get(k, 0) for k in SCORE_KEYS) >= min_score


def score_sum(verdict: dict) -> int:
    scores = _scores(verdict)
    return sum(scores.get(k, 0) for k in SCORE_KEYS)


def best_attempt_index(verdicts: list[dict]) -> int:
    """Index of the strongest attempt by sum(scores); ties → latest attempt.

    Mirrors qa_lane._finalize_best. Returns -1 for an empty list.
    """
    best_i, best_s = -1, -1
    for i, v in enumerate(verdicts):
        s = score_sum(v)
        if s >= best_s:  # >= so a tie keeps the later attempt
            best_i, best_s = i, s
    return best_i


def lowest_dim(verdict: dict) -> str | None:
    """The lowest-scoring dimension, to target the next re-learn's corrective note."""
    scores = _scores(verdict)
    if not scores:
        return None
    return min(SCORE_KEYS, key=lambda k: scores.get(k, 0))


def variant_action(verdict: dict) -> str:
    """Map a variant verdict to an action (D-003).

    pass → auto-accept; regenerate → regenerate (under cap); anything unsure
    (needs_human, error, None) → escalate to the operator.
    """
    gate = verdict.get("gates_as") or verdict.get("verdict")
    if gate == "pass":
        return VARIANT_AUTO_ACCEPT
    if gate == "regenerate":
        return VARIANT_REGENERATE
    return VARIANT_ESCALATE


@dataclass
class LearnConditioning:
    """How to condition one learn attempt.

    Temp-0 generation is NOT deterministic across calls (verified 2026-07-08),
    so re-rolls vary on their own — every rung runs at temperature 0 and the
    old rising-temperature schedule is gone (lean-conditioning, D-006).
    """

    learn_in_maple: bool = False
    temperature: float = 0.0
    extra_note: str = ""
    lean: bool = False


def learn_conditioning(
    attempt: int, low_dim: str | None = None, *, allow_maple: bool = True
) -> LearnConditioning:
    """The fixed prose/lean split (lean-conditioning, D-008/D-012).

    Prose rungs — attempt 0 native (style prompt + notes), attempt 1 maple
    (wood) or native+corrective (RTF) — keep today's conditioning. Every
    attempt from index 2 on is the LEAN TAIL: the bare lean prompt, with
    ``onboard_replica`` supplying only the spec-file width note as notes
    (prose actively cues the priors it tries to forbid — El Dorado burned 16
    prose attempts; the lean prompt fixed it in 4 re-rolls).
    """
    if attempt <= 0:
        return LearnConditioning()
    if attempt == 1:
        if allow_maple:
            return LearnConditioning(learn_in_maple=True)
        return LearnConditioning(extra_note=_LOW_DIM_NOTE.get(low_dim or "", ""))
    return LearnConditioning(lean=True)


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


# ---------------------------------------------------------------------------
# Replica onboarding loop (side-effecting: learns, judges, re-learns ≤ cap)
# ---------------------------------------------------------------------------

# Status values for OnboardResult.
QUEUED_READY = "queued_ready"          # judge-clean replica queued for approval
QUEUED_NEEDS_HUMAN = "queued_needs_human"  # best attempt queued, flagged for a look
ONBOARD_ERROR = "error"                # learn/judge failed or timed out
CEILING_HIT = "ceiling"               # run spend ceiling reached first


def _default_image_cost() -> float:
    from backend.qa.trust_config import load_trust_config

    return load_trust_config().image_cost_usd


@dataclass
class Spend:
    """Per-run spend guard (increment-before-submit, like the QA lane)."""

    ceiling_usd: float
    image_cost_usd: float = field(default_factory=_default_image_cost)
    spent_usd: float = 0.0

    def can_charge(self) -> bool:
        return self.spent_usd + self.image_cost_usd <= self.ceiling_usd + 1e-9

    def charge(self) -> None:
        self.spent_usd += self.image_cost_usd


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


def _wait_until(predicate, timeout: float, poll: float = 0.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value is not None:
            return value
        time.sleep(poll)
    return None


def wait_for_replica_verdict(store, project_id: str, timeout: float = 240.0):
    """Wait for learning then the replica judge to finish.

    Returns (base_image_id, verdict) once ``qa_status=="done"``, or (None, None)
    on learn error or timeout.
    """

    def learn_done():
        p = store.get(project_id)
        if p is None:
            return None
        if p.learning_status == "error":
            return ("error", None)
        if p.learning_status == "done" and p.base_image_id:
            return ("done", p.base_image_id)
        return None

    got = _wait_until(learn_done, timeout)
    if got is None or got[0] == "error":
        return (None, None)
    base_id = got[1]

    def verdict_done():
        p = store.get(project_id)
        if p is None:
            return None
        v = p.qa_verdicts.get(base_id)
        if v and v.get("qa_status") == "done":
            return v
        return None

    return (base_id, _wait_until(verdict_done, timeout))


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
    profile_bytes: bytes | None = None,
    lean_notes: str = "",
) -> OnboardResult:
    """Learn → identity-judge → re-learn until no disqualifier or the attempt
    cap, on the fixed prose/lean split (lean-conditioning, D-008/D-012). Never
    approves the replica (Stage-A stays human, D-001).

    Prose rungs (attempts 0–1): the profile spec's facts and the project's
    stored notes condition the learn prompt, and named defects become the next
    attempt's corrective. The lean tail (attempts ≥ 2) drops ALL of that: the
    bare lean prompt plus ``lean_notes`` — the driver passes the spec-file
    width note there (one measured fact, no character prose) — re-rolled at
    temp 0. ``profile_bytes`` (the catalog cross-section drawing) feeds
    EXTRACTION ONLY: as an image it hurt both generation (lean-spike viewpoint
    leak, 2026-07-08) and the judge (false-fails doubled, re-cal 2026-07-10);
    as extraction input it sharpens the facts. Facts remain the identity
    judge's acceptance criteria on EVERY attempt. The old min-score judge
    still runs in the QA lane; an attempt gates on it only when the identity
    judge errors.
    """
    if learn_fn is None:
        from backend.worker import start_learning as learn_fn  # lazy: avoid import cycle
    if identity_fn is None or extract_fn is None:
        from google import genai

        from backend.qa.judge import judge_replica_identity
        from backend.qa.profile_spec import extract_profile_spec

        _client = genai.Client(api_key=api_key)
        if identity_fn is None:
            def identity_fn(src, rep, facts):  # closure mirrors learn_fn's lazy import
                # No cross-section: the 2026-07-10 re-calibration showed the
                # drawing DOUBLES the judge's false-fails (10%->21%) for flat
                # catch — it stays extraction-only.
                return judge_replica_identity(_client, src, rep, facts,
                                              key=f"{project_id}:identity")
        if extract_fn is None:
            def extract_fn(src):
                return extract_profile_spec(_client, src, profile_bytes=profile_bytes)

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
        if cond.lean:
            # Lean tail (D-012): width note only — no facts, defects, or anchor.
            notes = lean_notes
        else:
            corrective = defect_note(defects) or cond.extra_note
            notes = f"{base_notes} {corrective}".strip() if corrective else base_notes

        learn_fn(
            store, store.get(project_id), api_key, upload_bytes,
            learn_in_maple=cond.learn_in_maple,
            aspect_ratio=aspect_ratio,
            temperature=cond.temperature,
            style_notes=notes,
            lean=cond.lean,
            attempt_label=f"attempt{attempt}",
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


# ---------------------------------------------------------------------------
# Variant phase (post-approval): generate a batch, auto-accept judge passes
# ---------------------------------------------------------------------------


def _variant_signature(project) -> tuple:
    """Stable snapshot of (image_id, terminal-gate) for settle detection."""
    return tuple(sorted(
        (r.image_id, (project.qa_verdicts.get(r.image_id) or {}).get("gates_as"))
        for r in project.results
    ))


def onboard_variants(
    store,
    project_id: str,
    api_key: str,
    swatch_paths: list,
    *,
    timeout: float = 300.0,
    poll: float = 3.0,
    stable_polls: int = 2,
    reset_existing: bool = True,
    auto_accept: bool = True,
    generate_fn=None,
) -> dict:
    """Generate a variant batch for an APPROVED replica, let the QA lane judge
    and auto-regenerate, then (if ``auto_accept``) approve judge passes (D-003).
    Unsure variants (needs_human / regenerate-at-cap / error / still-judging at
    timeout) always stay queued for the operator.

    With ``auto_accept=False`` nothing is approved automatically — every variant
    lands in the operator Review tab (the "show me all" mode for the reliability
    phase). The returned ``accepted`` list then reflects what *would* auto-accept.

    The replica must already be operator-approved — this never approves a
    replica, only variants the judge passed. ``reset_existing`` clears prior
    variant results first so a re-run replaces rather than appends. The wait is
    bounded by ``timeout``; a variant whose judge never finishes is queued, not
    waited on forever.
    """
    if generate_fn is None:
        from backend.worker import start_generation as generate_fn  # lazy

    if reset_existing:
        store.reset_variant_results(project_id)

    store.update(project_id, selected_swatches=[str(p) for p in swatch_paths])
    generate_fn(store, store.get(project_id), api_key)

    deadline = time.monotonic() + timeout
    last_sig, stable = None, 0
    while time.monotonic() < deadline:
        p = store.get(project_id)
        gen_done = p is not None and p.generation_status == "done"
        results = p.results if p else []
        all_judged = bool(results) and all(
            (p.qa_verdicts.get(r.image_id) or {}).get("qa_status") == "done"
            for r in results
        )
        if gen_done and all_judged:
            sig = _variant_signature(p)
            stable = stable + 1 if sig == last_sig else 0
            last_sig = sig
            if stable >= stable_polls:
                break
        else:
            stable = 0
        time.sleep(poll)

    from backend.qa.approvals import Approval, get_approval_store

    approvals = get_approval_store()
    p = store.get(project_id)
    accepted, queued = [], []
    for r in p.results:
        verdict = p.qa_verdicts.get(r.image_id) or {}
        if variant_action(verdict) == VARIANT_AUTO_ACCEPT:
            if auto_accept:
                approvals.set(Approval(
                    image_id=r.image_id, project_id=project_id, kind="variant",
                    verdict="approved", note="onboarding auto-accept (judge pass)",
                ))
            accepted.append(r.wood_name)
        else:
            queued.append((r.wood_name, verdict.get("gates_as") or verdict.get("verdict")))
    return {"total": len(p.results), "accepted": accepted, "queued": queued,
            "auto_accepted": auto_accept}
