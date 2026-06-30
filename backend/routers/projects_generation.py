"""Project learning/generation endpoints."""

from fastapi import APIRouter, Header, HTTPException, Request

from backend.models import GenerationStatusResponse, ProjectResponse
from backend.routers.projects_common import (
    get_project_or_404,
    get_store,
    to_generation_status,
    to_project_response,
)
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

    start_generation(store, project, x_api_key)
    return to_generation_status(get_project_or_404(store, project_id))


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
    if not project.has_signature or project.learned_signature is None:
        raise HTTPException(status_code=400, detail="No learned signature")
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    if idx in project.retrying_indices:
        raise HTTPException(status_code=409, detail="Already retrying this result")

    start_retry(store, project, idx, x_api_key)
    return to_generation_status(get_project_or_404(store, project_id))
