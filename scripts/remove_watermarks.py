# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "opencv-python>=4.8.0",
#     "pillow>=12.0.0",
#     "numpy>=1.26.0",
# ]
# ///
"""Batch-remove 'Example' watermark and wood-name labels from door images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = 1000
FONT_SIZE = CANVAS_SIZE // 22  # 45 — matches add_watermark()
LABEL_AREA_H = CANVAS_SIZE // 13  # ~77px
MATCH_THRESHOLD = 0.35
INPAINT_RADIUS = 5
MASK_PAD = 4


def _load_font() -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, FONT_SIZE)
        except OSError:
            continue
    return ImageFont.load_default(size=FONT_SIZE)


def _render_text_template(text: str, font: ImageFont.FreeTypeFont) -> np.ndarray:
    """Render text as it appears in watermarked images: black text on white."""
    dummy = Image.new("L", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    img = Image.new("L", (w, h), 255)
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=0)
    return np.array(img)


def _template_to_mask(template: np.ndarray) -> np.ndarray:
    """Convert a visual template (black text on white) to a binary mask."""
    return (template < 128).astype(np.uint8) * 255


def _find_text(
    gray: np.ndarray, template: np.ndarray, template_inv: np.ndarray,
) -> tuple[int, int, float]:
    """Try normal template (light bg) then inverted (dark bg), return best match."""
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, val1, _, loc1 = cv2.minMaxLoc(result)

    result_inv = cv2.matchTemplate(gray, template_inv, cv2.TM_CCOEFF_NORMED)
    _, val2, _, loc2 = cv2.minMaxLoc(result_inv)

    if val1 >= val2:
        return loc1[0], loc1[1], val1
    return loc2[0], loc2[1], val2


def _is_white_background(img: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    pad = 10
    samples = []
    if x - pad >= 0:
        samples.append(img[y : y + h, max(0, x - pad - 20) : x - pad])
    if x + w + pad < img.shape[1]:
        samples.append(img[y : y + h, x + w + pad : min(img.shape[1], x + w + pad + 20)])
    if not samples:
        return False
    region = np.concatenate(samples, axis=1)
    return float(np.mean(region)) > 235


def _find_door_start_row(gray_top: np.ndarray) -> int:
    """Find the row where the door image begins (transition from white to content)."""
    for y in range(gray_top.shape[0]):
        row = gray_top[y, :]
        non_white = np.sum(row < 230) / len(row)
        if non_white > 0.15:
            return y
    return gray_top.shape[0]


def _remove_top_label(img: np.ndarray) -> bool:
    top = img[:LABEL_AREA_H, :]
    gray_top = cv2.cvtColor(top, cv2.COLOR_BGR2GRAY) if len(top.shape) == 3 else top
    if float(np.mean(gray_top)) < 220:
        return False

    door_row = _find_door_start_row(gray_top)
    if door_row <= 2:
        return False

    label_region = gray_top[:door_row, :]
    dark_mask = label_region < 140
    if np.sum(dark_mask) < 50:
        return False
    coords = np.argwhere(dark_mask)
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0)
    pad = 6
    y1 = max(0, y_min - pad)
    y2 = min(door_row, y_max + pad + 1)
    x1 = max(0, x_min - pad)
    x2 = min(img.shape[1], x_max + pad + 1)
    img[y1:y2, x1:x2] = 255
    return True


def process_image(
    path: Path,
    output_path: Path,
    font: ImageFont.FreeTypeFont,
    template: np.ndarray,
    template_inv: np.ndarray,
    text_mask: np.ndarray,
    dry_run: bool = False,
) -> str:
    pil_img = Image.open(path)
    if pil_img.size != (CANVAS_SIZE, CANVAS_SIZE):
        return f"SKIP (size {pil_img.size[0]}x{pil_img.size[1]})"

    img_rgb = np.array(pil_img.convert("RGB"))
    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    tx, ty, confidence = _find_text(gray, template, template_inv)
    th, tw = template.shape

    if confidence < MATCH_THRESHOLD:
        return f"SKIP (no watermark found, confidence={confidence:.2f})"

    if dry_run:
        return f"MATCH (confidence={confidence:.2f} at ({tx},{ty}))"

    mask = np.zeros(gray.shape, dtype=np.uint8)
    mask[ty : ty + th, tx : tx + tw] = text_mask
    mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    if _is_white_background(img_bgr, tx, ty, tw, th):
        img_bgr[mask > 0] = 255
    else:
        img_bgr = cv2.inpaint(img_bgr, mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)

    out_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out_rgb).save(output_path, format="PNG")

    return f"OK (confidence={confidence:.2f})"


def discover_images(folders: list[Path]) -> list[Path]:
    images: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            print(f"WARNING: {folder} is not a directory, skipping", file=sys.stderr)
            continue
        images.extend(sorted(folder.glob("*.png")))
    return images


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove 'Example' watermark from door images."
    )
    parser.add_argument("folders", nargs="+", type=Path, help="Folders with watermarked PNGs")
    parser.add_argument("--output", type=Path, default=None, help="Output directory (default: cleaned/ subfolder)")
    parser.add_argument("--inplace", action="store_true", help="Overwrite originals")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed")
    parser.add_argument("--skip-existing", action="store_true", help="Skip already-processed images")
    args = parser.parse_args()

    font = _load_font()
    template = _render_text_template("Example", font)
    template_inv = (255 - template).astype(np.uint8)
    text_mask = _template_to_mask(template)

    images = discover_images(args.folders)
    if not images:
        print("No PNG images found.")
        return

    print(f"Found {len(images)} PNG(s) to process.\n")

    ok = 0
    skipped = 0
    for i, img_path in enumerate(images, 1):
        if args.inplace:
            out_path = img_path
        elif args.output:
            out_path = args.output / img_path.name
        else:
            out_path = img_path.parent / "cleaned" / img_path.name

        if args.skip_existing and out_path.exists() and not args.inplace:
            skipped += 1
            continue

        status = process_image(
            img_path, out_path, font, template, template_inv, text_mask,
            dry_run=args.dry_run,
        )
        print(f"[{i}/{len(images)}] {img_path.name}: {status}")
        if status.startswith("OK"):
            ok += 1

    print(f"\nDone. {ok} processed, {skipped} skipped, {len(images) - ok - skipped} not matched.")


if __name__ == "__main__":
    main()
