"""Export browser-viewable JPEG thumbnails for the .bin images."""

import hashlib
import os
from pathlib import Path

from PIL import Image


def export_thumb(src: Path, out_dir: Path, max_px: int = 640) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{src}|{max_px}".encode()).hexdigest()[:16]
    dest = out_dir / f"{digest}.jpg"
    if dest.exists():
        return dest
    tmp = dest.with_suffix(".tmp")
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            im.save(tmp, "JPEG", quality=85)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return dest
