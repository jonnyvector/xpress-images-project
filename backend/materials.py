"""Shared helpers for swatch/material metadata and file resolution."""

from __future__ import annotations

import json
from pathlib import Path

SWATCHES_BASE = Path("swatches")
WOOD_SWATCHES_DIR = Path("swatches/wood")
RTF_SWATCHES_DIR = Path("swatches/rtf")
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MIME_MAP: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def normalize_material_key(value: str) -> str:
    return value.lower().replace("_", "-")


def get_swatch_dir(material: str = "wood") -> Path:
    return RTF_SWATCHES_DIR if material == "rtf" else WOOD_SWATCHES_DIR


def get_swatch_files(material: str = "wood") -> list[Path]:
    d = get_swatch_dir(material)
    if not d.exists():
        return []
    return sorted([f for f in d.iterdir() if f.suffix.lower() in EXTENSIONS])


def load_material_types(material: str = "wood") -> dict[str, dict]:
    json_path = SWATCHES_BASE / ("rtf_types.json" if material == "rtf" else "wood_types.json")
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    return {}


def swatch_name_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()


def resolve_swatch_path(swatch_key: str, swatch_files: list[Path]) -> Path | None:
    normalized = normalize_material_key(swatch_key)
    for f in swatch_files:
        if normalize_material_key(f.stem) == normalized:
            return f
    return None


def get_reference_image_path(key: str, material: str = "wood") -> Path | None:
    key_underscore = key.replace("-", "_")
    ref_dir = Path("swatches/rtf/references") if material == "rtf" else Path("swatches/references")
    if not ref_dir.exists():
        return None
    for prefix in ("door-", "door_"):
        for k in (key, key_underscore):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                ref_path = ref_dir / f"{prefix}{k}{ext}"
                if ref_path.exists():
                    return ref_path
    return None
