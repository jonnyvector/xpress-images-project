"""Projects API router."""

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response

from backend.generator import STYLES, DoorGenerator
from backend.models import (
    ErrorItem,
    GenerationStatusResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    ResultItem,
    SaveToFolderResponse,
    VersionSummary,
)
from backend.state import ProjectStore
from backend.worker import start_generation, start_retry

router = APIRouter()

OUTPUT_DIR = Path("output")


def _is_drawer_style(door_style: str | None) -> bool:
    """Return True if the given style key belongs to the drawer category."""
    if not door_style:
        return False
    return STYLES.get(door_style, {}).get("category") == "drawer"


def _get_store(request: Request) -> ProjectStore:
    return request.app.state.project_store


def _project_response(p) -> ProjectResponse:  # noqa: ANN001
    return ProjectResponse(
        id=p.id,
        name=p.name,
        product_type=p.product_type,
        material_type=p.material_type,
        door_style=p.door_style,
        corner_style=p.corner_style,
        style_notes=p.style_notes,
        gemini_model=p.gemini_model,
        selected_swatches=p.selected_swatches,
        upload_filename=p.upload_filename,
        has_signature=p.has_signature,
        has_base_image=p.base_door_image is not None,
        learning_status=p.learning_status,
        learning_error=p.learning_error,
        generation_status=p.generation_status,
        generation_completed=p.generation_completed,
        generation_total=p.generation_total,
        results=[
            ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(p.results)
        ],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in p.errors],
        retrying_indices=p.retrying_indices,
        signature_version=p.signature_version,
        version_count=p.version_count,
    )


@router.get("/projects", response_model=list[ProjectResponse])
def list_projects(request: Request) -> list[ProjectResponse]:
    store = _get_store(request)
    return [_project_response(p) for p in store.list_projects()]


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, request: Request) -> ProjectResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(project)


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(body: ProjectCreate, request: Request) -> ProjectResponse:
    store = _get_store(request)
    project = store.create(
        name=body.name,
        product_type=body.product_type,
        material_type=body.material_type,
    )
    return _project_response(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, request: Request) -> None:
    store = _get_store(request)
    if not store.delete(project_id):
        raise HTTPException(status_code=404, detail="Project not found")


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str, body: ProjectUpdate, request: Request
) -> ProjectResponse:
    store = _get_store(request)
    updates = body.model_dump(exclude_none=True)
    if not updates:
        project = store.get(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return _project_response(project)
    project = store.update(project_id, **updates)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_response(project)


MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _guess_mime(filename: str | None) -> str:
    if filename:
        suffix = Path(filename).suffix.lower()
        return MIME_TYPES.get(suffix, "image/png")
    return "image/png"


@router.get("/projects/{project_id}/upload")
def get_upload_image(project_id: str, request: Request) -> Response:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = store.get_upload_bytes(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No uploaded image")
    return Response(content=data, media_type=_guess_mime(project.upload_filename))


@router.get("/projects/{project_id}/base-image")
def get_base_image(project_id: str, request: Request) -> Response:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.base_door_image is None:
        raise HTTPException(status_code=404, detail="No base image")
    return Response(
        content=project.base_door_image,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get(
    "/projects/{project_id}/versions",
    response_model=list[VersionSummary],
)
def list_versions(project_id: str, request: Request) -> list[VersionSummary]:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    versions = store.list_versions(project_id)
    return [VersionSummary(**v) for v in versions]


@router.get("/projects/{project_id}/versions/{version}/base-image")
def get_version_base_image(
    project_id: str, version: int, request: Request
) -> Response:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = store.get_version_base_image(project_id, version)
    if data is None:
        raise HTTPException(status_code=404, detail="Version base image not found")
    return Response(content=data, media_type="image/png")


@router.get("/projects/{project_id}/versions/{version}/results/{idx}/image")
def get_version_result_image(
    project_id: str, version: int, idx: int, request: Request
) -> Response:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = store.get_version_result_image(project_id, version, idx)
    if data is None:
        raise HTTPException(status_code=404, detail="Version result image not found")
    return Response(content=data, media_type="image/png")


@router.post("/projects/{project_id}/versions/{version}/restore")
def restore_version(
    project_id: str, version: int, request: Request
) -> ProjectResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not store.restore_version(project_id, version):
        raise HTTPException(status_code=404, detail="Version not found")
    project = store.get(project_id)
    return _project_response(project)


@router.get("/projects/{project_id}/results/{idx}/image")
def get_result_image(
    project_id: str,
    idx: int,
    request: Request,
    watermark: bool = True,
    watermark_offset: int = Query(0, ge=-600, le=600),
) -> Response:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    wood_name, image_data = project.results[idx]

    if watermark:
        from backend.generator import add_watermark

        image_data = add_watermark(
            image_data, wood_name, watermark_offset,
            force_dark_text=_is_drawer_style(project.door_style),
        )
    return Response(
        content=image_data,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/projects/{project_id}/upload", response_model=ProjectResponse)
async def upload_file(
    project_id: str, file: UploadFile, request: Request
) -> ProjectResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    data = await file.read()
    store.save_upload(project_id, file.filename or "upload.png", data)
    project = store.get(project_id)
    return _project_response(project)


@router.post("/projects/{project_id}/learn", response_model=ProjectResponse)
def learn_style(
    project_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ProjectResponse:
    from backend.worker import start_learning

    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.learning_status == "running":
        raise HTTPException(status_code=409, detail="Learning already in progress")

    upload_bytes = store.get_upload_bytes(project_id)
    if upload_bytes is None:
        raise HTTPException(status_code=400, detail="No uploaded image")

    start_learning(store, project, x_api_key, upload_bytes)

    project = store.get(project_id)
    return _project_response(project)


# --- Generation endpoints ---


@router.post("/projects/{project_id}/generate", response_model=GenerationStatusResponse)
def trigger_generation(
    project_id: str,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> GenerationStatusResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.has_signature or project.learned_signature is None:
        raise HTTPException(status_code=400, detail="Learn style first")
    if not project.selected_swatches:
        raise HTTPException(status_code=400, detail="No swatches selected")
    if project.generation_status == "running":
        raise HTTPException(status_code=409, detail="Generation already running")

    start_generation(store, project, x_api_key)

    project = store.get(project_id)
    return GenerationStatusResponse(
        status=project.generation_status,
        completed=project.generation_completed,
        total=project.generation_total,
        results=[
            ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)
        ],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
    )


@router.get(
    "/projects/{project_id}/generate/status",
    response_model=GenerationStatusResponse,
)
def generation_status(project_id: str, request: Request) -> GenerationStatusResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return GenerationStatusResponse(
        status=project.generation_status,
        completed=project.generation_completed,
        total=project.generation_total,
        results=[
            ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)
        ],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
    )


@router.post("/projects/{project_id}/generate/reset", response_model=GenerationStatusResponse)
def reset_generation(project_id: str, request: Request) -> GenerationStatusResponse:
    """Force-reset a stuck generation back to done/idle."""
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.generation_status = "done" if project.results else "idle"
    project.generation_completed = len(project.results)
    project.generation_total = len(project.results) + len(project.errors)
    store.save(project_id)
    return GenerationStatusResponse(
        status=project.generation_status,
        completed=project.generation_completed,
        total=project.generation_total,
        results=[
            ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)
        ],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
    )


@router.post(
    "/projects/{project_id}/results/{idx}/retry",
    response_model=GenerationStatusResponse,
)
def retry_result(
    project_id: str,
    idx: int,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> GenerationStatusResponse:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.has_signature or project.learned_signature is None:
        raise HTTPException(status_code=400, detail="No learned signature")
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    if idx in project.retrying_indices:
        raise HTTPException(status_code=409, detail="Already retrying this result")

    start_retry(store, project, idx, x_api_key)

    project = store.get(project_id)
    return GenerationStatusResponse(
        status=project.generation_status,
        completed=project.generation_completed,
        total=project.generation_total,
        results=[
            ResultItem(index=i, wood_name=wn) for i, (wn, _) in enumerate(project.results)
        ],
        errors=[ErrorItem(wood_name=wn, error=err) for wn, err in project.errors],
        retrying_indices=project.retrying_indices,
    )


SAVE_DIR_DOORS = Path.home() / "Desktop/xpress-images/AI Images/Inset Panel Doors"
SAVE_DIR_DRAWERS = Path.home() / "Desktop/xpress-images/AI Images/Drawer Fronts"
SAVE_DIR_RTF_DOORS = Path.home() / "Desktop/xpress-images/AI Images/RTF Doors"
SAVE_DIR_RTF_DRAWERS = Path.home() / "Desktop/xpress-images/AI Images/RTF Drawer Fronts"


@router.post(
    "/projects/{project_id}/results/save",
    response_model=SaveToFolderResponse,
)
def save_results_to_folder(
    project_id: str,
    request: Request,
    watermark: bool = True,
    watermark_offset: int = Query(0, ge=-600, le=600),
) -> SaveToFolderResponse:
    """Save all result images directly to the configured folder on disk."""
    from backend.generator import add_watermark

    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.results:
        raise HTTPException(status_code=404, detail="No results to save")

    # Route to the correct folder based on material type and category
    style_info = STYLES.get(project.door_style or "") if project.door_style else None
    is_drawer = style_info is not None and style_info.get("category") == "drawer"
    is_rtf = project.material_type == "rtf"
    if is_rtf:
        save_dir = SAVE_DIR_RTF_DRAWERS if is_drawer else SAVE_DIR_RTF_DOORS
    else:
        save_dir = SAVE_DIR_DRAWERS if is_drawer else SAVE_DIR_DOORS

    suffix = "Watermarked" if watermark else "Plain"
    folder = save_dir / project.name / suffix
    folder.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []

    for wood_name, image_data in project.results:
        safe_wood = wood_name.lower().replace(' ', '_').replace('/', '_')
        base = f"{project.name}_{safe_wood}"
        dest = folder / f"{base}.png"
        n = 2
        while dest.exists():
            dest = folder / f"{base} ({n}).png"
            n += 1
        out_data = (
            add_watermark(image_data, wood_name, watermark_offset, force_dark_text=is_drawer)
            if watermark
            else image_data
        )
        dest.write_bytes(out_data)
        saved_files.append(dest.name)

    return SaveToFolderResponse(saved_to=str(folder), files=saved_files)


@router.delete("/projects/{project_id}/results/{idx}", status_code=204)
def discard_result(project_id: str, idx: int, request: Request) -> None:
    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    project.results.pop(idx)
    store.save(project_id)


@router.get("/projects/{project_id}/results/zip")
def download_results_zip(
    project_id: str,
    request: Request,
    watermark: bool = True,
    watermark_offset: int = Query(0, ge=-600, le=600),
):  # noqa: ANN201
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    from backend.generator import add_watermark

    store = _get_store(request)
    project = store.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if not project.results:
        raise HTTPException(status_code=404, detail="No results")

    suffix = "watermarked" if watermark else "plain"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        is_drawer = _is_drawer_style(project.door_style)
        for wood_name, image_data in project.results:
            filename = f"{project.name}_{wood_name.lower().replace(' ', '_')}.png"
            zf.writestr(
                filename,
                add_watermark(image_data, wood_name, watermark_offset, force_dark_text=is_drawer)
                if watermark
                else image_data,
            )
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{project.name}_variations_{suffix}.zip"'
        },
    )
