"""Shared helpers for projects routers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, Request

from backend.models import ErrorItem, GenerationStatusResponse, ProjectResponse, ResultItem
from backend.state import ProjectState, ProjectStore
from backend.styles.catalog import STYLES

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

SAVE_DIR_DOORS = Path.home() / "Desktop/xpress-images/AI Images/Inset Panel Doors"
SAVE_DIR_DRAWERS = Path.home() / "Desktop/xpress-images/AI Images/Drawer Fronts"
SAVE_DIR_RTF_DOORS = Path.home() / "Desktop/xpress-images/AI Images/RTF Doors"
SAVE_DIR_RTF_DRAWERS = Path.home() / "Desktop/xpress-images/AI Images/RTF Drawer Fronts"


def get_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


def get_project_or_404(store: ProjectStore, project_id: str) -> ProjectState:
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def to_project_response(project: ProjectState) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        product_type=project.product_type,
        material_type=project.material_type,
        door_style=project.door_style,
        corner_style=project.corner_style,
        style_notes=project.style_notes,
        gemini_model=project.gemini_model,
        selected_swatches=project.selected_swatches,
        upload_filename=project.upload_filename,
        has_signature=project.has_signature,
        has_base_image=project.base_door_image is not None,
        learning_status=project.learning_status,
        learning_error=project.learning_error,
        generation_status=project.generation_status,
        generation_completed=project.generation_completed,
        generation_total=project.generation_total,
        results=[ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
        signature_version=project.signature_version,
        version_count=project.version_count,
    )


def to_generation_status(project: ProjectState) -> GenerationStatusResponse:
    return GenerationStatusResponse(
        status=project.generation_status,
        completed=project.generation_completed,
        total=project.generation_total,
        results=[ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
    )


def is_drawer_style(door_style: str | None) -> bool:
    if not door_style:
        return False
    return STYLES.get(door_style, {}).get("category") == "drawer"


def guess_mime(filename: str | None) -> str:
    if filename:
        return MIME_TYPES.get(Path(filename).suffix.lower(), "image/png")
    return "image/png"
