"""Async QA lane: judge + geometry + policy for images as they are stored.

Owns the background executor that produces pipeline verdicts at generation
time (D-007). Generation status NEVER waits on this lane — verdicts land
asynchronously, keyed by stable image_id, with qa_status visible to the UI
(pending → judging → done). One ``_api_semaphore`` slot spans one entire
``judge()`` call (majority votes and retries included, D-010), so the global
Gemini concurrency cap holds. A failed judge gets exactly one automatic
re-judge; a persistent failure stores verdict ``error`` which gates as
``needs_human`` and never auto-regenerates.

Composition per image: VisionJudge → geometry (variant-vs-replica hard gate,
replica-vs-sample advisory, style-class routed) → ``policy.decide()`` fed
with the live approval state from the ApprovalStore.

Not responsible for: gate decisions on /generate (routers), approval writes
(approvals.py), spend accounting (runs.py), or auto-regeneration (wired here
later, but bounded and cap-checked by the run manifest).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from backend.qa.approvals import ApprovalStore, get_approval_store
from backend.qa.corpus import Candidate
from backend.qa.geometry import GeometryReport, measure_cached
from backend.qa.judge import VisionJudge
from backend.qa.policy import PolicyConfig, decide, load_policy
from backend.qa.styles_classes import style_class
from backend.state import new_image_id

if TYPE_CHECKING:
    from backend.runs import RunManifest
    from backend.state import ProjectStore


@dataclass
class RegenContext:
    """One wood slot's auto-regeneration chain (D-005/D-009/D-012).

    ``generate`` is a worker-built closure that produces one new attempt
    (it owns generator params and semaphore use). ``attempt_ids`` is the
    identity chain, index == attempt number, first entry = the initial image.
    """

    run: RunManifest
    generate: Callable[[], object]
    wood_name: str
    attempt_ids: list[str] = field(default_factory=list)

logger = logging.getLogger(__name__)

QA_DIR = Path("output/.qa")
GEOMETRY_CACHE = QA_DIR / "geometry"


def _default_measure(
    *,
    reference_path: Path,
    candidate_path: Path,
    key: str,
    geometry_config,
    style_cls: str,
    reference: str,
) -> GeometryReport | None:
    return measure_cached(
        reference_path, candidate_path, key, geometry_config, style_cls,
        reference=reference, cache_dir=GEOMETRY_CACHE,
    )


class _WorkerSemaphore:
    """Default semaphore: the worker's global Gemini cap (lazy import — the
    worker imports this module, so a top-level import would be circular)."""

    def __enter__(self):
        from backend.worker import _api_semaphore

        self._sem = _api_semaphore
        self._sem.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self._sem.release()


class QaLane:
    def __init__(
        self,
        *,
        max_workers: int = 2,
        judge_factory: Callable[[str], VisionJudge] | None = None,
        semaphore=None,
        approvals: ApprovalStore | None = None,
        measure_fn=None,
        policy: PolicyConfig | None = None,
    ) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._judge_factory = judge_factory or (
            lambda api_key: VisionJudge(api_key=api_key, cache_dir=QA_DIR / "verdicts")
        )
        self._semaphore = semaphore if semaphore is not None else _WorkerSemaphore()
        self._active = 0
        self._active_lock = threading.Lock()
        self._approvals = approvals
        self._measure_fn = measure_fn or _default_measure
        self._policy = policy

    def idle(self) -> bool:
        with self._active_lock:
            return self._active == 0

    def _get_approvals(self) -> ApprovalStore:
        return self._approvals if self._approvals is not None else get_approval_store()

    def _get_policy(self) -> PolicyConfig:
        # Re-read per task so policy_config.json edits apply without restart.
        return self._policy if self._policy is not None else load_policy()

    def enqueue(
        self,
        store: ProjectStore,
        project_id: str,
        image_id: str,
        api_key: str,
        *,
        kind: str,
        swatch_path: Path | None = None,
        regen: RegenContext | None = None,
    ) -> Future:
        """Queue one image for QA. Returns the Future (verdict dict or None)."""
        # Pending is visible immediately — the UI shows "judging…" states
        # without racing the executor.
        store.set_qa_verdict(
            project_id, image_id, {"qa_status": "pending", "verdict": None}
        )
        with self._active_lock:
            self._active += 1
        return self._executor.submit(
            self._run_task, store, project_id, image_id, api_key,
            kind=kind, swatch_path=swatch_path, regen=regen,
        )

    # ---- task ------------------------------------------------------------

    def _run_task(
        self,
        store: ProjectStore,
        project_id: str,
        image_id: str,
        api_key: str,
        *,
        kind: str,
        swatch_path: Path | None,
        regen: RegenContext | None = None,
    ) -> dict | None:
        try:
            verdict = self._judge_image(
                store, project_id, image_id, api_key, kind=kind, swatch_path=swatch_path
            )
            if verdict is not None and regen is not None:
                self._continue_chain(
                    store, project_id, api_key, regen, verdict, swatch_path=swatch_path
                )
            return verdict
        except Exception:
            # A lane bug must never take down the executor thread silently.
            logger.exception("QA task failed for %s:%s", project_id, image_id)
            verdict = _verdict_dict(
                verdict="error", gates_as="needs_human",
                reason="internal QA lane error (see server log)",
            )
            store.set_qa_verdict(project_id, image_id, verdict)
            return verdict
        finally:
            with self._active_lock:
                self._active -= 1

    def _judge_image(
        self,
        store: ProjectStore,
        project_id: str,
        image_id: str,
        api_key: str,
        *,
        kind: str,
        swatch_path: Path | None,
    ) -> dict | None:
        candidate = self._resolve_candidate(
            store, project_id, image_id, kind=kind, swatch_path=swatch_path
        )
        if candidate is None:
            # Image vanished (discarded / re-learned) — drop the pending marker.
            store.clear_qa_verdict(project_id, image_id)
            return None

        store.set_qa_verdict(
            project_id, image_id, {"qa_status": "judging", "verdict": None}
        )

        judge = self._judge_factory(api_key)
        # One semaphore slot spans the WHOLE judge() call — votes + retries.
        with self._semaphore:
            result = judge.judge(candidate)
        if result.verdict == "error":
            # Exactly one automatic re-judge (error verdicts are never cached).
            with self._semaphore:
                result = judge.judge(candidate)

        policy = self._get_policy()
        geometry = self._geometry_for(candidate, policy, store, project_id)

        approvals = self._get_approvals()
        approved_ids = approvals.approved_ids()
        project = store.get(project_id)
        replica_ok = (
            project is not None
            and project.base_image_id is not None
            and project.base_image_id in approved_ids
        )
        decision = decide(
            result,
            candidate,
            policy,
            geometry=geometry,
            approved_keys=(
                frozenset({candidate.key}) if image_id in approved_ids else frozenset()
            ),
            replica_approved=replica_ok,
        )

        verdict = _verdict_dict(
            verdict="error" if result.verdict == "error" else decision.verdict,
            gates_as=decision.verdict,
            reason=decision.reason,
            scores={
                "panel_layout_match": result.panel_layout_match,
                "proportions_match": result.proportions_match,
                "profile_character_match": result.profile_character_match,
                "material_realism": result.material_realism,
                "swatch_fidelity": result.swatch_fidelity,
            },
            geometry=geometry.status if geometry is not None else None,
        )
        store.set_qa_verdict(project_id, image_id, verdict)
        return verdict

    def _resolve_candidate(
        self,
        store: ProjectStore,
        project_id: str,
        image_id: str,
        *,
        kind: str,
        swatch_path: Path | None,
    ) -> Candidate | None:
        """Locate the image on disk by stable id, at task time (indices shift)."""
        project = store.get(project_id)
        if project is None:
            return None
        d = store.project_dir(project_id)
        sample = d / "upload.bin"
        sample_path = sample if sample.exists() else None

        if kind == "replica":
            if project.base_image_id != image_id:
                return None  # re-learned since enqueue — stale task
            image_path = d / "base_door.bin"
            index, wood_name = -1, None
        else:
            index = next(
                (i for i, r in enumerate(project.results) if r.image_id == image_id),
                None,
            )
            if index is None:
                return None
            image_path = d / f"result_{index}.bin"
            wood_name = project.results[index].wood_name
        if not image_path.exists():
            return None

        return Candidate(
            key=f"live:{image_id}",  # stable cache key for judge + geometry
            project_id=project_id,
            project_name=project.name,
            door_style=project.door_style,
            version=0,
            kind=kind,
            index=index,
            wood_name=wood_name,
            image_path=image_path,
            sample_path=sample_path,
            swatch_path=swatch_path if swatch_path and swatch_path.exists() else None,
            presumed="accept",
        )

    def _geometry_for(
        self,
        candidate: Candidate,
        policy: PolicyConfig,
        store: ProjectStore,
        project_id: str,
    ) -> GeometryReport | None:
        """Style routing + reference selection (mirrors the offline eval):
        variant -> current replica (hard gate), replica -> sample (advisory)."""
        if policy.geometry is None:
            return None
        cls = style_class(candidate.door_style)
        if cls not in policy.geometry.measurable_styles:
            return None
        if candidate.kind == "variant":
            replica_path = store.project_dir(project_id) / "base_door.bin"
            if replica_path.exists():
                reference_path, reference = replica_path, "replica"
            elif candidate.sample_path is not None:
                reference_path, reference = candidate.sample_path, "sample"
            else:
                return None
        else:
            if candidate.sample_path is None:
                return None
            reference_path, reference = candidate.sample_path, "sample"
        return self._measure_fn(
            reference_path=reference_path,
            candidate_path=candidate.image_path,
            key=candidate.key,
            geometry_config=policy.geometry,
            style_cls=cls,
            reference=reference,
        )

    # ---- auto-regeneration chain (D-005/D-009/D-012) -----------------------

    def _continue_chain(
        self,
        store: ProjectStore,
        project_id: str,
        api_key: str,
        regen: RegenContext,
        verdict: dict,
        *,
        swatch_path: Path | None,
    ) -> None:
        """Verdict landed for the chain's newest attempt — retry or finalize.

        Only ``regenerate`` retries (needs_human/error never do, D-007), each
        retry is counted as UNCONSENTED spend before submission and refused
        with GT-003 on the manifest when the cap would be exceeded (D-009).
        """
        config = regen.run.config_snapshot()
        max_retries = int(config.get("max_auto_retries", 2))
        image_cost = float(config.get("image_cost_usd", 0.134))
        cap = float(config.get("run_cost_cap_usd", 10.0))
        attempts_used = len(regen.attempt_ids) - 1

        if verdict.get("gates_as") == "regenerate" and attempts_used < max_retries:
            regen.run.submit(unconsented=True)  # increment-before-submit
            _, unconsented = regen.run.counters()
            if unconsented * image_cost > cap + 1e-9:
                regen.run.unsubmit(unconsented=True)  # rollback: no API call
                regen.run.record_event(
                    "GT-003",
                    f"unconsented-spend cap ${cap:.2f} reached; auto-retries "
                    f"cancelled for {regen.wood_name}",
                )
                self._finalize_best(store, project_id, regen)
                return
            result = regen.generate()
            image_data = getattr(result, "image_data", None)
            if getattr(result, "error", None) or image_data is None:
                logger.warning(
                    "auto-regen attempt failed for %s:%s", project_id, regen.wood_name
                )
                self._finalize_best(store, project_id, regen)
                return
            attempt_no = attempts_used + 1
            record = store.replace_result_attempt(
                project_id,
                regen.attempt_ids[-1],
                image_id=new_image_id(),
                wood_name=regen.wood_name,
                attempt=attempt_no,
                image_data=image_data,
            )
            if record is None:  # slot vanished (discard/re-learn) — stop
                return
            regen.run.record_attempt(
                image_id=record.image_id, wood_name=regen.wood_name,
                attempt=attempt_no, verdict=None,
            )
            regen.attempt_ids.append(record.image_id)
            self.enqueue(
                store, project_id, record.image_id, api_key,
                kind="variant", swatch_path=swatch_path, regen=regen,
            )
            return

        self._finalize_best(store, project_id, regen)

    def _finalize_best(
        self, store: ProjectStore, project_id: str, regen: RegenContext
    ) -> None:
        """Best attempt by judge score sum becomes active; ties break to the
        HIGHEST attempt number (deterministic, D-012)."""
        if len(regen.attempt_ids) < 2:
            return
        project = store.get(project_id)
        if project is None:
            return

        def score(image_id: str) -> int:
            v = project.qa_verdicts.get(image_id) or {}
            return sum((v.get("scores") or {}).values())

        best_attempt, best_id = max(
            enumerate(regen.attempt_ids), key=lambda t: (score(t[1]), t[0])
        )
        if best_id != regen.attempt_ids[-1]:
            store.promote_attempt(
                project_id,
                regen.attempt_ids[-1],
                promote_image_id=best_id,
                promote_attempt=best_attempt,
            )


def _verdict_dict(
    *,
    verdict: str,
    gates_as: str,
    reason: str,
    scores: dict[str, int] | None = None,
    geometry: str | None = None,
) -> dict:
    return {
        "verdict": verdict,  # "pass" | "regenerate" | "needs_human" | "error"
        "gates_as": gates_as,  # how the pipeline treats it (error -> needs_human)
        "reason": reason,
        "scores": scores or {},
        "geometry": geometry,  # "ok" | "drift" | "unmeasurable" | None
        "qa_status": "done",
        "judged_at": datetime.now(UTC).isoformat(),
    }


# Process-wide lane; tests build their own instances with fakes.
_default_lane: QaLane | None = None


def get_qa_lane() -> QaLane:
    global _default_lane
    if _default_lane is None:
        _default_lane = QaLane()
    return _default_lane
