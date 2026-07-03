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
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from backend.qa.approvals import ApprovalStore, get_approval_store
from backend.qa.corpus import Candidate
from backend.qa.geometry import GeometryReport, measure_cached
from backend.qa.judge import VisionJudge
from backend.qa.policy import PolicyConfig, decide, load_policy
from backend.qa.styles_classes import style_class

if TYPE_CHECKING:
    from backend.state import ProjectStore

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
        self._approvals = approvals
        self._measure_fn = measure_fn or _default_measure
        self._policy = policy

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
    ) -> Future:
        """Queue one image for QA. Returns the Future (verdict dict or None)."""
        # Pending is visible immediately — the UI shows "judging…" states
        # without racing the executor.
        store.set_qa_verdict(
            project_id, image_id, {"qa_status": "pending", "verdict": None}
        )
        return self._executor.submit(
            self._run_task, store, project_id, image_id, api_key,
            kind=kind, swatch_path=swatch_path,
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
    ) -> dict | None:
        try:
            return self._judge_image(
                store, project_id, image_id, api_key, kind=kind, swatch_path=swatch_path
            )
        except Exception:
            # A lane bug must never take down the executor thread silently.
            logger.exception("QA task failed for %s:%s", project_id, image_id)
            verdict = _verdict_dict(
                verdict="error", gates_as="needs_human",
                reason="internal QA lane error (see server log)",
            )
            store.set_qa_verdict(project_id, image_id, verdict)
            return verdict

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
