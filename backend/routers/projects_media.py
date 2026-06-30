"""Project media/result endpoints."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from backend.generator import add_watermark
from backend.materials import load_material_types, normalize_material_key
from backend.models import ImportResultsResponse, ProjectResponse, SaveToFolderResponse
from backend.routers.projects_common import (
    SAVE_DIR_DOORS,
    SAVE_DIR_DRAWERS,
    SAVE_DIR_RTF_DOORS,
    SAVE_DIR_RTF_DRAWERS,
    get_project_or_404,
    get_store,
    guess_mime,
    is_drawer_style,
    to_project_response,
)

router = APIRouter()


@router.get("/projects/{project_id}/upload")
def get_upload_image(project_id: str, request: Request) -> Response:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    data = store.get_upload_bytes(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No uploaded image")
    return Response(content=data, media_type=guess_mime(project.upload_filename))


@router.get("/projects/{project_id}/base-image")
def get_base_image(project_id: str, request: Request) -> Response:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if project.base_door_image is None:
        raise HTTPException(status_code=404, detail="No base image")
    return Response(
        content=project.base_door_image,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.get("/projects/{project_id}/results/{idx}/image")
def get_result_image(
    project_id: str,
    idx: int,
    request: Request,
    watermark: bool = True,
    watermark_offset: int = Query(0, ge=-600, le=600),
    image_scale: float = Query(1.0, ge=0.5, le=2.0),
) -> Response:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if idx < 0 or idx >= len(project.results):
        raise HTTPException(status_code=404, detail="Result not found")
    wood_name, image_data = project.results[idx]

    if watermark:
        image_data = add_watermark(
            image_data,
            wood_name,
            watermark_offset,
            force_dark_text=is_drawer_style(project.door_style),
            image_scale=image_scale,
        )

    return Response(
        content=image_data,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@router.post("/projects/{project_id}/upload", response_model=ProjectResponse)
async def upload_file(project_id: str, file: UploadFile, request: Request) -> ProjectResponse:
    store = get_store(request)
    get_project_or_404(store, project_id)
    data = await file.read()
    store.save_upload(project_id, file.filename or "upload.png", data)
    return to_project_response(get_project_or_404(store, project_id))


@router.post("/projects/{project_id}/results/save", response_model=SaveToFolderResponse)
def save_results_to_folder(
    project_id: str,
    request: Request,
    watermark: bool = True,
    watermark_offset: int = Query(0, ge=-600, le=600),
    image_scale: float = Query(1.0, ge=0.5, le=2.0),
) -> SaveToFolderResponse:
    """Save all result images directly to the configured folder on disk."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if not project.results:
        raise HTTPException(status_code=404, detail="No results to save")

    is_drawer = project.product_type == "Drawer Front" or is_drawer_style(project.door_style)
    is_rtf = project.material_type == "rtf"
    if is_rtf:
        save_dir = SAVE_DIR_RTF_DRAWERS if is_drawer else SAVE_DIR_RTF_DOORS
    else:
        save_dir = SAVE_DIR_DRAWERS if is_drawer else SAVE_DIR_DOORS

    suffix = "Watermarked" if watermark else "Plain"
    folder = save_dir / Path(project.name).name / suffix
    folder.mkdir(parents=True, exist_ok=True)
    saved_files: list[str] = []

    for wood_name, image_data in project.results:
        safe_wood = wood_name.lower().replace(" ", "_").replace("/", "_")
        base = f"{project.name}_{safe_wood}"
        dest = folder / f"{base}.png"
        n = 2
        while dest.exists():
            dest = folder / f"{base} ({n}).png"
            n += 1

        out_data = (
            add_watermark(
                image_data, wood_name, watermark_offset,
                force_dark_text=is_drawer, image_scale=image_scale,
            )
            if watermark
            else image_data
        )
        dest.write_bytes(out_data)
        saved_files.append(dest.name)

    return SaveToFolderResponse(saved_to=str(folder), files=saved_files)


@router.delete("/projects/{project_id}/results/{idx}", status_code=204)
def discard_result(project_id: str, idx: int, request: Request) -> None:
    store = get_store(request)
    project = get_project_or_404(store, project_id)
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
    image_scale: float = Query(1.0, ge=0.5, le=2.0),
):
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    if not project.results:
        raise HTTPException(status_code=404, detail="No results")

    suffix = "watermarked" if watermark else "plain"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        use_dark = is_drawer_style(project.door_style)
        for wood_name, image_data in project.results:
            filename = f"{project.name}_{wood_name.lower().replace(' ', '_')}.png"
            zf.writestr(
                filename,
                add_watermark(
                    image_data, wood_name, watermark_offset,
                    force_dark_text=use_dark, image_scale=image_scale,
                )
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


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

_TRAILING_VERSION_RE = re.compile(r"\s*\(?(\d+)\)?\s*$")

# Matches a leading product/model+style prefix like "DR1-df-slab_", "DN917 Slab Plain_".
# We find potential split points (underscores) and try each from left to right,
# accepting the first one whose remainder resolves to a known material.
_MODEL_CODE_RE = re.compile(r"^[A-Za-z]+\d+", re.IGNORECASE)

_TRAILING_RTF_RE = re.compile(r"[-_]rtf$", re.IGNORECASE)


def _match_color_key(color_part: str, wood_types: dict[str, dict]) -> str | None:
    """Try exact then prefix match against wood_types, return name or None."""
    color_part = _TRAILING_RTF_RE.sub("", color_part)
    key = normalize_material_key(color_part)
    if not key:
        return None
    wt = wood_types.get(key)
    if wt:
        return wt["name"]
    prefix = key + "-"
    matches = [k for k in wood_types if k.startswith(prefix)]
    if len(matches) == 1:
        return wood_types[matches[0]]["name"]
    if len(matches) > 1:
        matches.sort(key=len)
        return wood_types[matches[0]]["name"]
    return None


def _extract_wood_name(stem: str, wood_types: dict[str, dict]) -> str:
    """Best-effort extraction of wood name from a filename stem."""
    clean = _TRAILING_VERSION_RE.sub("", stem).strip()

    # Try progressively shorter suffixes against wood_types keys (exact match).
    tokens = re.split(r"[_\-]+", clean)
    for start in range(len(tokens)):
        candidate = "-".join(tokens[start:])
        key = normalize_material_key(candidate)
        wt = wood_types.get(key)
        if wt:
            return wt["name"]

    # Try splitting at each underscore position after a model code prefix.
    # e.g. "DR1-df-slab_black_rtf" -> try "black_rtf", then "rtf"
    #      "KB732_alabaster_taction_rtf" -> try "alabaster_taction_rtf", then "taction_rtf"
    # Accept the first (longest) remainder that resolves to a known material.
    underscore_positions = [i for i, c in enumerate(clean) if c == "_"]
    for pos in underscore_positions:
        remainder = clean[pos + 1:]
        name = _match_color_key(remainder, wood_types)
        if name:
            return name

    # Final fallback: strip model code and trailing _rtf, title-case
    m = _MODEL_CODE_RE.match(clean)
    if m:
        rest = clean[m.end():].lstrip(" _-")
        rest = _TRAILING_RTF_RE.sub("", rest)
        if rest:
            return rest.replace("_", " ").replace("-", " ").title()

    clean = _TRAILING_RTF_RE.sub("", clean)
    return clean.replace("_", " ").replace("-", " ").title()


@router.post("/projects/{project_id}/results/import", response_model=ImportResultsResponse)
def import_results_from_folder(
    project_id: str,
    request: Request,
    folder: str = Query(..., description="Path to folder containing door images"),
) -> ImportResultsResponse:
    """Import door images from a local folder as project results."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)

    folder_path = Path(folder).expanduser()
    if not folder_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {folder}")

    wood_types = load_material_types(project.material_type)

    images = sorted(
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not images:
        raise HTTPException(status_code=400, detail="No images found in folder")

    wood_names: list[str] = []
    for img_path in images:
        image_data = img_path.read_bytes()
        wood_name = _extract_wood_name(img_path.stem, wood_types)
        project.results.append((wood_name, image_data))
        wood_names.append(wood_name)

    project.generation_status = "done"
    project.generation_completed = len(project.results)
    project.generation_total = len(project.results)
    store.save(project_id)

    return ImportResultsResponse(imported=len(wood_names), wood_names=wood_names)
