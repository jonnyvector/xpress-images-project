"""Project CRUD endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.models import ProjectCreate, ProjectResponse, ProjectUpdate
from backend.routers.projects_common import get_project_or_404, get_store, to_project_response

router = APIRouter()


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(request: Request) -> list[ProjectResponse]:
    store = get_store(request)
    return [to_project_response(p) for p in store.list_projects()]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, request: Request) -> ProjectResponse:
    store = get_store(request)
    return to_project_response(get_project_or_404(store, project_id))


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, request: Request) -> ProjectResponse:
    store = get_store(request)
    project = store.create(
        name=body.name,
        product_type=body.product_type,
        material_type=body.material_type,
    )
    return to_project_response(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request) -> None:
    store = get_store(request)
    if not store.delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, body: ProjectUpdate, request: Request) -> ProjectResponse:
    store = get_store(request)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return to_project_response(get_project_or_404(store, project_id))
    project = store.update(project_id, **updates)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return to_project_response(project)
