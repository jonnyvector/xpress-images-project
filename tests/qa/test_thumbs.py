from pathlib import Path

from PIL import Image

from backend.qa.thumbs import export_thumb


def _make_png(path: Path, size: tuple[int, int] = (800, 1400)) -> None:
    Image.new("RGB", size, color=(120, 80, 40)).save(path, "PNG")


def test_export_thumb_resizes_and_caches(tmp_path: Path) -> None:
    src = tmp_path / "door.bin"
    _make_png(src)
    out = tmp_path / "thumbs"

    thumb = export_thumb(src, out, max_px=400)
    assert thumb is not None and thumb.exists() and thumb.suffix == ".jpg"
    with Image.open(thumb) as im:
        assert max(im.size) <= 400

    mtime = thumb.stat().st_mtime_ns
    again = export_thumb(src, out, max_px=400)
    assert again == thumb
    assert again.stat().st_mtime_ns == mtime  # cache hit, not rewritten


def test_export_thumb_cache_is_keyed_by_max_px(tmp_path: Path) -> None:
    src = tmp_path / "door.bin"
    _make_png(src)
    out = tmp_path / "thumbs"

    big = export_thumb(src, out, max_px=400)
    small = export_thumb(src, out, max_px=100)
    assert big is not None and small is not None
    assert big != small  # different sizes must not share a cache entry
    with Image.open(small) as im:
        assert max(im.size) <= 100


def test_export_thumb_unreadable_returns_none(tmp_path: Path) -> None:
    src = tmp_path / "junk.bin"
    src.write_bytes(b"not an image")
    assert export_thumb(src, tmp_path / "thumbs") is None
