"""Swatches and styles API router."""

import json
from pathlib import Path

from fastapi import APIRouter

from backend.generator import STYLES
from backend.models import StyleResponse, SwatchResponse

router = APIRouter()

SWATCHES_DIR = Path("swatches")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _get_swatch_files() -> list[Path]:
    if not SWATCHES_DIR.exists():
        return []
    return sorted([f for f in SWATCHES_DIR.iterdir() if f.suffix.lower() in EXTENSIONS])


def _load_wood_types() -> dict[str, dict]:
    json_path = SWATCHES_DIR / "wood_types.json"
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def _get_reference_image_url(key: str) -> str | None:
    key_underscore = key.replace("-", "_")
    ref_dir = Path("swatches/references")
    if not ref_dir.exists():
        return None
    for prefix in ("door-", "door_"):
        for k in (key, key_underscore):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                ref_path = ref_dir / f"{prefix}{k}{ext}"
                if ref_path.exists():
                    return f"/files/swatches/references/{ref_path.name}"
    return None


def _swatch_name_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


@router.get("/swatches", response_model=list[SwatchResponse])
def list_swatches() -> list[SwatchResponse]:
    swatch_files = _get_swatch_files()
    wood_types = _load_wood_types()
    swatch_stems = {f.stem.lower().replace("_", "-") for f in swatch_files}

    result: list[SwatchResponse] = []

    # Physical swatches
    for f in swatch_files:
        key = f.stem.lower().replace("_", "-")
        wt = wood_types.get(key, {})
        result.append(
            SwatchResponse(
                key=key,
                name=wt.get("name", _swatch_name_from_path(f)),
                description=wt.get("description"),
                swatch_image_url=f"/files/swatches/{f.name}",
                reference_image_url=_get_reference_image_url(key),
                is_virtual=False,
            )
        )

    # Virtual swatches (have swatch_key but no physical file)
    for key, data in wood_types.items():
        if data.get("swatch_key") and key not in swatch_stems:
            borrowed_key = data["swatch_key"]
            # Find the borrowed swatch file URL
            borrowed_url = None
            for f in swatch_files:
                if f.stem.lower().replace("_", "-") == borrowed_key:
                    borrowed_url = f"/files/swatches/{f.name}"
                    break
            ref_key = data.get("reference_key", key)
            result.append(
                SwatchResponse(
                    key=key,
                    name=data.get("name", key),
                    description=data.get("description"),
                    swatch_image_url=borrowed_url or "",
                    reference_image_url=_get_reference_image_url(ref_key),
                    is_virtual=True,
                    swatch_key=borrowed_key,
                )
            )

    return result


@router.get("/styles", response_model=list[StyleResponse])
def list_styles() -> list[StyleResponse]:
    return [
        StyleResponse(key=key, name=style["name"], category=style["category"])
        for key, style in STYLES.items()
    ]
