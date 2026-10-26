"""Export browser-viewable JPEG thumbnails for the .bin images."""

import base64
import hashlib
import io
import os
from pathlib import Path

from PIL import Image


def thumbnail_jpeg(src: Path | bytes, max_px: int, quality: int = 85) -> bytes:
    """A JPEG no larger than max_px on its long edge."""
    with Image.open(io.BytesIO(src) if isinstance(src, bytes) else src) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=quality)
    return out.getvalue()


def jpeg_data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def export_thumb(src: Path, out_dir: Path, max_px: int = 640) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(f"{src}|{max_px}".encode()).hexdigest()[:16]
    dest = out_dir / f"{digest}.jpg"
    if dest.exists():
        return dest
    tmp = dest.with_suffix(".tmp")
    try:
        tmp.write_bytes(thumbnail_jpeg(src, max_px))
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        return None
    return dest
