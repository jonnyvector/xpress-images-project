"""Project learning/generation endpoints.

Owns the graduated-trust gates on POST /generate (D-004): Stage A — the
current replica MUST be operator-approved (GT-001, 409); Stage B — resolved
selections MUST fit the small-batch limit while bulk is locked (GT-002, 422);
empty resolution is rejected (GT-006, 400). Gates count RESOLVED selections
via the same resolver the worker uses, so the gate can never disagree with
what would actually be generated.
"""

from fastapi import APIRouter, Header, HTTPException, Request

from backend.models import GenerationStatusResponse, ProjectResponse
from backend.qa.trust_config import bulk_unlocked_for, load_trust_config
from backend.routers.projects_common import (
    get_project_or_404,
    get_store,
    replica_approved,
    to_generation_status,
    to_project_response,
)
from backend.selections import build_selections
from backend.styles.catalog import STYLES
from backend.worker import start_generation, start_learning, start_retry

router = APIRouter()


@router.post("/projects/{project_id}/learn", response_model=ProjectResponse)
def learn_style(
    project_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    learn_in_maple: bool = False,
) -> ProjectResponse:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if project.learning_status == "running":
        raise HTTPException(status_code=409, detail="Learning already in progress")

    upload_bytes = store.get_upload_bytes(project_id)
    if upload_bytes is None:
        raise HTTPException(status_code=400, detail="No uploaded image")

    start_learning(store, project, x_api_key, upload_bytes, learn_in_maple=learn_in_maple)
    return to_project_response(get_project_or_404(store, project_id))


@router.post("/projects/{project_id}/generate", response_model=GenerationStatusResponse)
def trigger_generation(
    project_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> GenerationStatusResponse:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if not project.has_signature or project.learned_signature is None:
        raise HTTPException(status_code=400, detail="Learn style first")
    if not project.selected_swatches:
        raise HTTPException(status_code=400, detail="No swatches selected")
    if project.generation_status == "running":
        raise HTTPException(status_code=409, detail="Generation already running")

    # Stage A: variants of an unreviewed replica never generate (GT-001).
    if not replica_approved(project):
        raise HTTPException(
            status_code=409,
            detail="GT-001: replica not approved — approve the replica before "
            "generating variants",
        )

    # Stage B: gate on RESOLVED selections, same resolver the worker uses.
    config = load_trust_config()
    resolved = build_selections(
        project.selected_swatches,
        door_style=project.door_style,
        material_type=project.material_type,
    )
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="GT-006: no selections resolve to generatable materials",
        )
    if (
        len(resolved) > config.small_batch_limit
        and not bulk_unlocked_for(config, project.door_style)
    ):
        raise HTTPException(
            status_code=422,
            detail=f"GT-002: {len(resolved)} resolved selections exceed the "
            f"small-batch limit of {config.small_batch_limit} while bulk is locked",
        )

    start_generation(store, project, x_api_key)
    return to_generation_status(get_project_or_404(store, project_id))


@router.get("/projects/{project_id}/generate/estimate")
def generation_estimate(project_id: str, request: Request) -> dict:
    """Pre-spend consent numbers + gate state — mirrors the /generate gates
    without side effects, so the confirm dialog can never under-quote (D-009)."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    config = load_trust_config()
    resolved = build_selections(
        project.selected_swatches,
        door_style=project.door_style,
        material_type=project.material_type,
    )
    n = len(resolved)
    bulk = bulk_unlocked_for(config, project.door_style)
    approved = replica_approved(project)

    gate_ok, gate_reason = True, None
    if not approved:
        gate_ok, gate_reason = False, "GT-001: replica not approved"
    elif n == 0:
        gate_ok, gate_reason = False, "GT-006: no selections resolve"
    elif n > config.small_batch_limit and not bulk:
        gate_ok, gate_reason = (
            False,
            f"GT-002: {n} resolved selections exceed the small-batch limit "
            f"of {config.small_batch_limit} while bulk is locked",
        )

    return {
        "images": n,
        "est_cost_usd": round(n * config.image_cost_usd, 4),
        # Consented spend plus the full unconsented cap — never under-quotes.
        "worst_case_usd": round(n * config.image_cost_usd + config.run_cost_cap_usd, 4),
        "stage": "A" if not approved else ("C" if bulk else "B"),
        "gate_ok": gate_ok,
        "gate_reason": gate_reason,
    }


@router.get("/projects/{project_id}/generate/status", response_model=GenerationStatusResponse)
def generation_status(project_id: str, request: Request) -> GenerationStatusResponse:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    return to_generation_status(project)


@router.post("/projects/{project_id}/generate/reset", response_model=GenerationStatusResponse)
def reset_generation(project_id: str, request: Request) -> GenerationStatusResponse:
    """Force-reset a stuck generation back to done/idle."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    project.generation_status = "done" if project.results else "idle"
    project.generation_completed = len(project.results)
    project.generation_total = len(project.results) + len(project.errors)
    store.save(project_id)
    return to_generation_status(project)


@router.post("/projects/{project_id}/results/{idx}/retry", response_model=GenerationStatusResponse)
def retry_result(
    project_id: str,
    idx: int,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> GenerationStatusResponse:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    # Reference-based styles retry from base_door.bin rather than a signature,
    # so only require a signature for the non-reference path (start_retry does
    # its own base-image validation for the reference case).
    style = STYLES.get(project.door_style or "", {})
    use_ref = bool(style.get("use_base_door_reference"))
    if not use_ref and (not project.has_signature or project.learned_signature is None):
        raise HTTPException(status_code=400, detail="No learned signature")
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    if idx in project.retrying_indices:
        raise HTTPException(status_code=409, detail="Already retrying this result")

    start_retry(store, project, idx, x_api_key)
    return to_generation_status(get_project_or_404(store, project_id))
