"""Swatches and styles API router."""

import json
from pathlib import Path

from fastapi import APIRouter, Query

from backend.generator import STYLES
from backend.models import StyleResponse, SwatchResponse

router = APIRouter()

SWATCHES_BASE = Path("swatches")
WOOD_SWATCHES_DIR = Path("swatches/wood")
RTF_SWATCHES_DIR = Path("swatches/rtf")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

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


def _get_swatch_dir(material: str) -> Path:
    return RTF_SWATCHES_DIR if material == "rtf" else WOOD_SWATCHES_DIR


def _get_swatch_files(material: str = "wood") -> list[Path]:
    d = _get_swatch_dir(material)
    if not d.exists():
        return []
    return sorted([f for f in d.iterdir() if f.suffix.lower() in EXTENSIONS])


def _load_material_types(material: str = "wood") -> dict[str, dict]:
    if material == "rtf":
        json_path = SWATCHES_BASE / "rtf_types.json"
    else:
        json_path = SWATCHES_BASE / "wood_types.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def _get_reference_image_url(key: str, material: str = "wood") -> str | None:
    key_underscore = key.replace("-", "_")
    ref_dir = Path("swatches/rtf/references") if material == "rtf" else Path("swatches/references")
    if not ref_dir.exists():
        return None
    subdir = "rtf/references" if material == "rtf" else "references"
    for prefix in ("door-", "door_"):
        for k in (key, key_underscore):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                ref_path = ref_dir / f"{prefix}{k}{ext}"
                if ref_path.exists():
                    return f"/files/swatches/{subdir}/{ref_path.name}"
    return None


def _swatch_name_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


@router.get("/swatches", response_model=list[SwatchResponse])
def list_swatches(
    material: str = Query("wood", pattern="^(wood|rtf)$"),
) -> list[SwatchResponse]:
    swatch_files = _get_swatch_files(material)
    material_types = _load_material_types(material)
    swatch_stems = {f.stem.lower().replace("_", "-") for f in swatch_files}

    # URL path prefix differs by material
    url_prefix = "swatches/rtf" if material == "rtf" else "swatches/wood"

    result: list[SwatchResponse] = []

    # Physical swatches
    for f in swatch_files:
        key = f.stem.lower().replace("_", "-")
        wt = material_types.get(key, {})
        result.append(
            SwatchResponse(
                key=key,
                name=wt.get("name", _swatch_name_from_path(f)),
                description=wt.get("description"),
                swatch_image_url=f"/files/{url_prefix}/{f.name}",
                reference_image_url=_get_reference_image_url(key, material),
                is_virtual=False,
            )
        )

    # Virtual swatches (have swatch_key but no physical file)
    for key, data in material_types.items():
        if data.get("swatch_key") and key not in swatch_stems:
            borrowed_key = data["swatch_key"]
            borrowed_url = None
            for f in swatch_files:
                if f.stem.lower().replace("_", "-") == borrowed_key:
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
