"""Project version endpoints."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from backend.models import ProjectResponse, VersionSummary
from backend.routers.projects_common import get_project_or_404, get_store, to_project_response

router = APIRouter()


@router.get("/projects/{project_id}/versions", response_model=list[VersionSummary])
def list_versions(project_id: str, request: Request) -> list[VersionSummary]:
    store = get_store(request)
    get_project_or_404(store, project_id)
    versions = store.list_versions(project_id)
    return [VersionSummary(**v) for v in versions]


@router.get("/projects/{project_id}/versions/{version}/base-image")
def get_version_base_image(project_id: str, version: int, request: Request) -> Response:
    store = get_store(request)
    get_project_or_404(store, project_id)
    data = store.get_version_base_image(project_id, version)
    if data is None:
        raise HTTPException(status_code=404, detail="Version base image not found")
    return Response(content=data, media_type="image/png")


@router.get("/projects/{project_id}/versions/{version}/results/{idx}/image")
def get_version_result_image(project_id: str, version: int, idx: int, request: Request) -> Response:
    store = get_store(request)
    get_project_or_404(store, project_id)
    data = store.get_version_result_image(project_id, version, idx)
    if data is None:
        raise HTTPException(status_code=404, detail="Version result image not found")
    return Response(content=data, media_type="image/png")


@router.post("/projects/{project_id}/versions/{version}/restore", response_model=ProjectResponse)
def restore_version(project_id: str, version: int, request: Request) -> ProjectResponse:
    store = get_store(request)
    get_project_or_404(store, project_id)
    if not store.restore_version(project_id, version):
        raise HTTPException(status_code=404, detail="Version not found")
    return to_project_response(get_project_or_404(store, project_id))
