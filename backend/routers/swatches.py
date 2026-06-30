"""Swatches and styles API router."""

from fastapi import APIRouter, Query

from backend.materials import (
    get_reference_image_path,
    get_swatch_files,
    load_material_types,
    normalize_material_key,
    swatch_name_from_path,
)
from backend.models import StyleResponse, SwatchResponse
from backend.styles.catalog import STYLES

router = APIRouter()

# RTF only supports these style keys
RTF_STYLE_KEYS = {
    "rtf_minimal",
    "rtf_drawer_minimal",
    "rtf_drawer_shaker",
    "rtf_drawer_shaker_shallow",
    "rtf_drawer_shaker_skinny",
    "rtf_drawer_bevel",
    "recessed_panel",
    "raised_panel",
    "raised_panel_radius",
    "solid_plank",
    "drawer_recessed_panel",
    "drawer_raised_panel",
    "drawer_raised_panel_radius",
    "drawer_solid_plank",
}

# Styles that are exclusive to RTF and must not appear for wood
RTF_ONLY_STYLE_KEYS = {
    "rtf_minimal",
    "rtf_drawer_minimal",
    "rtf_drawer_shaker",
    "rtf_drawer_shaker_shallow",
    "rtf_drawer_shaker_skinny",
    "rtf_drawer_bevel",
}


def _get_reference_image_url(key: str, material: str = "wood") -> str | None:
    ref_path = get_reference_image_path(key, material)
    if ref_path is None:
        return None
    subdir = "rtf/references" if material == "rtf" else "references"
    return f"/files/swatches/{subdir}/{ref_path.name}"


@router.get("/swatches", response_model=list[SwatchResponse])
def list_swatches(
    material: str = Query("wood", pattern="^(wood|rtf)$"),
) -> list[SwatchResponse]:
    swatch_files = get_swatch_files(material)
    material_types = load_material_types(material)
    swatch_stems = {normalize_material_key(f.stem) for f in swatch_files}

    # URL path prefix differs by material
    url_prefix = "swatches/rtf" if material == "rtf" else "swatches/wood"

    result: list[SwatchResponse] = []

    # Physical swatches
    for f in swatch_files:
        key = normalize_material_key(f.stem)
        wt = material_types.get(key, {})
        result.append(
            SwatchResponse(
                key=key,
                name=wt.get("name", swatch_name_from_path(f)),
                description=wt.get("description"),
                swatch_image_url=f"/files/{url_prefix}/{f.name}",
                reference_image_url=_get_reference_image_url(key, material),
                is_virtual=False,
            )
        )

    # Virtual swatches (entries in material_types with no physical file)
    for key, data in material_types.items():
        if key in swatch_stems:
            continue
        borrowed_key = None
        borrowed_url = None
        if data.get("swatch_key"):
            borrowed_key = normalize_material_key(data["swatch_key"])
            for f in swatch_files:
                if normalize_material_key(f.stem) == borrowed_key:
                    borrowed_url = f"/files/{url_prefix}/{f.name}"
                    break
        ref_key = data.get("reference_key", key)
        result.append(
            SwatchResponse(
                key=key,
                name=data.get("name", key),
                description=data.get("description"),
                swatch_image_url=borrowed_url or "",
                reference_image_url=_get_reference_image_url(
                    ref_key, material
                ),
                is_virtual=True,
                swatch_key=borrowed_key,
            )
        )

    return result


@router.get("/styles", response_model=list[StyleResponse])
def list_styles(
    material: str = Query("wood", pattern="^(wood|rtf)$"),
) -> list[StyleResponse]:
    return [
        StyleResponse(key=key, name=style["name"], category=style["category"])
        for key, style in STYLES.items()
        if (material == "rtf" and key in RTF_STYLE_KEYS)
        or (material == "wood" and key not in RTF_ONLY_STYLE_KEYS)
    ]
