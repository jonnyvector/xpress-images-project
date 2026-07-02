"""Export browser-viewable JPEG thumbnails for the .bin images."""

import hashlib
from pathlib import Path

from PIL import Image


def export_thumb(src: Path, out_dir: Path, max_px: int = 640) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(str(src).encode()).hexdigest()[:16]
    dest = out_dir / f"{digest}.jpg"
    if dest.exists():
        return dest
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(dest, "JPEG", quality=85)
    except OSError:
        return None
    return dest
