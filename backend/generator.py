"""Gemini image generation with thought signature support."""

import io
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = 1000


def add_watermark(image_bytes: bytes, wood_name: str = "") -> bytes:
    """Place image on a 1000x1000 white canvas and add watermark text."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Fit image within canvas while preserving aspect ratio
    img.thumbnail((CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))
    offset_x = (CANVAS_SIZE - img.width) // 2
    offset_y = (CANVAS_SIZE - img.height) // 2
    canvas.paste(img, (offset_x, offset_y), img)

    # Watermark text sized to canvas
    font_size = CANVAS_SIZE // 22

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default(size=font_size)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    text = "Example"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (CANVAS_SIZE - text_w) // 2
    margin = int(CANVAS_SIZE * 0.05)
    text_y = CANVAS_SIZE - margin // 2 - text_h // 2 - 86

    if "walnut" in wood_name.lower():
        outline_color = (220, 220, 220, 180)
        text_color = (240, 240, 240, 210)
    else:
        outline_color = (40, 40, 40, 180)
        text_color = (50, 50, 50, 210)
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        draw.text((text_x + dx, text_y + dy), text, font=font, fill=outline_color)
    draw.text((text_x, text_y), text, font=font, fill=text_color)

    canvas = Image.alpha_composite(canvas, overlay)

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()


@dataclass
class GenerationResult:
    """Result from a single image generation."""

    image_data: bytes | None
    thought_signature: bytes | None
    error: str | None = None


STYLES: dict[str, dict[str, str]] = {
    # Door styles
    "recessed_panel": {
        "name": "Recessed Panel",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a RECESSED (INSET) panel door — the center panel sits BELOW the frame, NOT raised above it. "
            "The center panel is FLAT and RECESSED — it does NOT have a raised bevel or convex surface. "
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, rail/stile proportions, molding profile, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a RECESSED/INSET panel door — the center panel must be FLAT and sit BELOW "
            "the surrounding frame. Do NOT make a raised panel door. The panel must NOT have a raised bevel "
            "or convex surface. Preserve the exact flat recessed panel design, frame molding profile, "
            "and rail/stile proportions from before."
        ),
    },
    "shaker_cope_stick": {
        "name": "Shaker Cope & Stick",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SHAKER door with COPE-AND-STICK joinery. "
            "The frame has a plain SQUARE inner edge — no routed step profile, no applied molding. "
            "CRITICAL JOINT DETAIL: The frame uses traditional COPE-AND-STICK joints, NOT mitered. "
            "The vertical stiles run FULL LENGTH top to bottom. The horizontal rails are cope-cut "
            "to fit over the stile's stick profile, creating a visible SEAM LINE where rail meets stile. "
            "This seam is a thin horizontal line across each stile at the joint — it should be subtly "
            "visible, especially on lighter woods. The inner corners are RIGHT-ANGLE BUTT JOINTS, "
            "NOT 45-degree miters. Do NOT make mitered corners. "
            "The center panel is FLAT and RECESSED — it sits BELOW the frame, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the square inner edge, cope-and-stick joint seams, frame width, rail/stile proportions, "
            "and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHAKER door with COPE-AND-STICK joints — NOT mitered. "
            "Plain SQUARE inner edge — no routed profile, no applied molding. "
            "The stile profiles run full length top to bottom; the cope-cut rails butt into them "
            "at right angles, leaving a visible seam line at each joint. "
            "Do NOT make mitered corners — NO 45-degree angles. Each inner corner is a right-angle "
            "butt joint with a subtle visible seam where the cope meets the stick. "
            "The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "Preserve the exact square edge, cope-and-stick joint seams, frame width, "
            "and proportions from before."
        ),
    },
    "recessed_panel_center_stile": {
        "name": "Recessed Panel (Center Stile)",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This door has a VERTICAL CENTER STILE that divides the door into TWO side-by-side recessed panels. "
            "The center stile is a critical structural element — it runs vertically through the middle of the door, "
            "creating two tall narrow recessed panels instead of one wide panel. "
            "Use the reference image to match the exact design details: "
            "the center stile width and position, panel depth, edge profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL STRUCTURAL REQUIREMENT: This door has a VERTICAL CENTER STILE dividing it into "
            "TWO side-by-side recessed panels. The center stile MUST be present — it is the defining feature "
            "of this door. Do NOT simplify to a single panel. Preserve the exact double-panel layout: "
            "outer frame (top rail, bottom rail, left stile, right stile) plus the vertical center stile "
            "creating two tall narrow recessed panels."
        ),
    },
    "recessed_panel_applied_molding": {
        "name": "Recessed Panel (Applied Molding)",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a RECESSED PANEL door with APPLIED MOLDING — it has a flat, recessed center panel "
            "surrounded by a separate decorative molding strip that creates a frame-within-a-frame appearance. "
            "There are TWO distinct borders visible: the outer frame (rails and stiles) and then an inner "
            "applied molding trim piece with a multi-step profile that frames the recessed panel. "
            "The center panel is FLAT and sits BELOW the frame — it is NOT raised. "
            "The applied molding creates a stepped-down transition from the outer frame to the panel. "
            "Use the reference image to match the exact design details: "
            "the applied molding profile, the step-down depth, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This door has APPLIED MOLDING — a decorative trim strip creating a visible "
            "frame-within-a-frame around the flat recessed panel. There must be TWO distinct borders: "
            "the outer frame and the inner applied molding piece. The center panel is FLAT and RECESSED — "
            "do NOT make a raised panel. Do NOT simplify to a plain shaker edge — the applied molding "
            "with its multi-step profile is the defining feature. Preserve the exact applied molding profile, "
            "step-down geometry, and rail/stile proportions from before."
        ),
    },
    "graham": {
        "name": "Graham",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a recessed panel door with a subtle ROUTED STEP PROFILE on the inner frame edge. "
            "The frame uses traditional COPE-AND-STICK joints — NOT mitered. "
            "CRITICAL JOINT DETAIL: The inner routed profile follows cope-and-stick joinery, just like "
            "a shaker door. The vertical stile profiles run FULL LENGTH top to bottom uninterrupted. "
            "The horizontal rail profiles BUTT INTO the stiles and terminate there. "
            "The inner corners are RIGHT-ANGLE BUTT JOINTS, NOT 45-degree miters. "
            "Do NOT make the inner profile look like a picture frame with mitered corners. "
            "The inner edge of the frame has a small, clean stepped/routed detail — more refined than "
            "a plain square shaker edge, but NOT a separate applied molding piece. The step is integral "
            "to the frame, creating a thin recessed line between the frame and the panel. "
            "The center panel is FLAT and RECESSED — it sits BELOW the frame, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the routed step profile, frame width, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a recessed panel door with a subtle ROUTED STEP PROFILE on the inner frame edge. "
            "The step detail is integral to the frame — NOT a separate applied molding piece, and NOT a plain "
            "square shaker edge. The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "CRITICAL JOINT DETAIL: The inner profile corners are COPE-AND-STICK BUTT JOINTS, NOT miters. "
            "The stile profiles run full length top to bottom; the rail profiles butt into them at right angles. "
            "Do NOT make the inner trim look like a mitered picture frame — NO 45-degree corners. "
            "Preserve the exact routed step profile, butt-joint corners, frame width, and proportions from before."
        ),
    },
    "hayes": {
        "name": "Hayes",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is the HAYES style cabinet door with these specific construction details: "
            "1) WIDE FRAME (rails and stiles) with a SQUARE outer edge profile — the outside "
            "perimeter of the door has clean, sharp, square-cut edges, NOT rounded or bullnosed. "
            "2) APPLIED MOLDING — a separate decorative molding strip with a COVE/OGEE stepped profile "
            "surrounds the center panel, creating a distinct frame-within-a-frame appearance with TWO "
            "visible borders: the outer frame and the inner applied molding trim. "
            "3) The APPLIED MOLDING CORNERS are MITERED at 45 degrees — the molding strips meet with "
            "precise diagonal miter cuts at each corner. "
            "4) The OUTER FRAME uses traditional COPE-AND-STICK joints at the corners — the rails and "
            "stiles join with square cope-and-stick joinery, NOT mitered. "
            "5) The center panel is FLAT and RECESSED — it sits BELOW the applied molding, NOT raised. "
            "6) There is a clear STEPPED TRANSITION from the outer frame down to the applied molding "
            "and then down again to the recessed panel — creating visible depth and shadow lines. "
            "Use the reference image to match the exact design details: "
            "the square outer edge, applied molding profile, miter joints on molding, "
            "cope-and-stick joints on frame, frame width, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL STYLE PRESERVATION — this is the HAYES door with ALL of these features: "
            "1) WIDE FRAME with a SQUARE outer edge — clean sharp square-cut perimeter, NOT rounded or bullnosed. "
            "2) APPLIED MOLDING with a COVE/OGEE stepped profile creating a frame-within-a-frame look. "
            "3) Applied molding corners are MITERED at 45 degrees. "
            "4) Outer frame corners use COPE-AND-STICK joints (NOT mitered). "
            "5) FLAT RECESSED center panel — do NOT make a raised panel. "
            "6) Clear stepped depth transitions: outer frame → applied molding → recessed panel. "
            "Preserve the exact square edge, applied molding profile, miter geometry on molding, "
            "cope-and-stick joints on frame, and all proportions from before."
        ),
    },
    "mitered_recessed_panel_applied_molding": {
        "name": "Mitered Recessed Panel (Applied Molding)",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a MITERED RECESSED PANEL door with APPLIED MOLDING. It combines three key features: "
            "1) The frame corners are joined at 45-DEGREE MITER JOINTS, NOT cope-and-stick — the grain "
            "runs at 45 degrees at each corner where rails meet stiles. "
            "2) A decorative APPLIED MOLDING strip with a stepped profile surrounds the panel, creating "
            "a frame-within-a-frame appearance with TWO distinct borders. "
            "3) The center panel is FLAT and RECESSED — it sits BELOW the frame, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the miter joint angles, applied molding profile, step-down depth, rail/stile proportions, "
            "and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This door has THREE defining features that must ALL be preserved: "
            "1) 45-degree MITER JOINTS at the frame corners — NOT cope-and-stick or square butt joints. "
            "2) APPLIED MOLDING — a decorative trim strip creating a frame-within-a-frame with a stepped profile. "
            "3) FLAT RECESSED center panel — do NOT make a raised panel. "
            "Preserve the exact miter geometry, applied molding profile, and proportions from before."
        ),
    },
    "mitered_flat_panel": {
        "name": "Skinny Shaker Mitered",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SKINNY SHAKER MITERED door — the defining feature is its EXTREMELY NARROW frame. "
            "The rails and stiles are VERY THIN — roughly HALF the width of a standard shaker door frame. "
            "The frame width is approximately 1 to 1.25 inches, making the center panel appear much larger "
            "relative to the frame than a normal shaker. Do NOT widen the frame — if the frame looks like "
            "a standard shaker width, it is WRONG. The frame must look noticeably skinny/slim. "
            "The frame corners are joined at 45-DEGREE MITER JOINTS, NOT cope-and-stick — the grain "
            "runs at 45 degrees at each corner where rails meet stiles. "
            "The inner edge is a simple clean square shaker profile — no routed detail, no applied molding. "
            "The center panel is FLAT and RECESSED — it sits BELOW the frame, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the very narrow frame width, miter joint angles, panel depth, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SKINNY SHAKER MITERED door. The frame (rails and stiles) must be "
            "EXTREMELY NARROW — roughly HALF the width of a standard shaker, approximately 1 to 1.25 inches. "
            "Do NOT widen the frame to standard shaker proportions — the skinny frame is the defining feature. "
            "If the frame looks like a normal shaker width, it is WRONG. "
            "The frame corners are 45-degree MITER JOINTS, NOT cope-and-stick or butt joints. "
            "Simple square shaker inner edge — no routed profile, no applied molding. "
            "The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "Preserve the exact skinny frame width, miter geometry, and proportions from before."
        ),
    },
    "shaker": {
        "name": "Shaker",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SHAKER style door — it has a FLAT, RECESSED center panel with clean square-edge framing. "
            "The center panel is FLAT and sits BELOW the frame — it is NOT raised and has NO bevel. "
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHAKER door — the center panel must be FLAT and RECESSED below the frame. "
            "Do NOT make a raised panel door. The panel must NOT have a raised bevel or convex surface. "
            "Preserve the exact Shaker flat recessed panel design and square-edge framing from before."
        ),
    },
    "raised_panel": {
        "name": "Raised Panel",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a raised-panel cabinet door. "
            "Use the reference image to match the exact design details: "
            "the panel raise height, bevel profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact raised-panel cabinet door design from before."),
    },
    "solid_plank": {
        "name": "Solid / Plank",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a solid plank cabinet door. "
            "Use the reference image to match the exact design details: "
            "the overall proportions, edge profile, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact solid plank door design from before."),
    },
    "louver": {
        "name": "Louver",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a louvered cabinet door. "
            "Use the reference image to match the exact design details: "
            "the slat spacing, angle, frame proportions, and edge profile. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact louvered door design from before."),
    },
    # Drawer front styles
    "drawer_recessed_panel": {
        "name": "Recessed Panel (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a RECESSED (INSET) panel drawer front — the center panel sits BELOW the frame, NOT raised above it. "
            "The center panel is FLAT and RECESSED — it does NOT have a raised bevel or convex surface. "
            "Use the reference image to match the exact design details: "
            "Match the wood type, panel depth, edge profile, rail/stile proportions, and wood grain direction exactly. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a RECESSED/INSET panel drawer front — the center panel must be FLAT and sit "
            "BELOW the surrounding frame. Do NOT make a raised panel. The panel must NOT have a raised bevel "
            "or convex surface. Preserve the exact flat recessed panel design from before."
        ),
    },
    "drawer_raised_panel": {
        "name": "Raised Panel (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate a photorealistic product image of a raised-panel cabinet drawer front. "
            "Use the reference image to match the exact design details: "
            "the panel raise height, bevel profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact raised-panel drawer front design from before."),
    },
    "drawer_solid_plank": {
        "name": "Solid / Slab (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate a photorealistic product image of a solid slab cabinet drawer front. "
            "Use the reference image to match the exact design details: "
            "the overall proportions, edge profile, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact solid slab drawer front design from before."),
    },
}


class DoorGenerator:
    """Generate door style variations using Gemini 3 with thought signatures."""

    MODEL = "gemini-3-pro-image-preview"
    MAX_RETRIES = 5
    RETRY_DELAY = 15  # seconds (exponential backoff: 15, 30, 60, 120, 240)

    def __init__(self, api_key: str) -> None:
        """Initialize the generator with API key."""
        self.client = genai.Client(api_key=api_key)

    def _load_image_as_part(self, image_path: Path) -> types.Part:
        """Load an image file as a Gemini Part."""
        image_bytes = image_path.read_bytes()

        # Determine mime type from extension
        suffix = image_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        mime_type = mime_types.get(suffix, "image/jpeg")

        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    def _extract_image_and_signature(self, response: Any) -> tuple[bytes | None, bytes | None, int]:
        """Extract image data and thought signature from response.

        Checks ALL candidates, not just the first one.
        Returns (image_data, thought_signature, candidate_index).
        """
        if not response.candidates:
            return None, None, -1

        # Check all candidates for valid image data
        for idx, candidate in enumerate(response.candidates):
            content = candidate.content
            if content is None or content.parts is None:
                continue

            image_data: bytes | None = None
            thought_signature: bytes | None = None

            for part in content.parts:
                if hasattr(part, "thought_signature") and part.thought_signature:
                    thought_signature = part.thought_signature
                if hasattr(part, "inline_data") and part.inline_data:
                    image_data = part.inline_data.data

            if image_data is not None:
                return image_data, thought_signature, idx

        return None, None, -1

    def learn_door_style(
        self,
        door_image_path: Path,
        door_style_name: str = "cabinet door",
        door_style: str = "recessed_panel",
        aspect_ratio: str = "9:16",
    ) -> GenerationResult:
        """
        Have Gemini generate its own version of the door to capture its understanding.

        This creates a thought signature that locks in the door's shape/style
        for consistent variations.

        Args:
            door_image_path: Path to the door style reference image
            door_style_name: Name of the door style (e.g., "Adobe Cabinet Door")
            door_style: Key from STYLES dict

        Returns:
            GenerationResult with Gemini's door image and thought signature
        """
        style = STYLES.get(door_style, STYLES["recessed_panel"])
        prompt = style["learn_prompt"]

        parts: list[types.Part] = [
            types.Part.from_text(text=prompt),
            self._load_image_as_part(door_image_path),
        ]

        contents = [types.Content(role="user", parts=parts)]

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["image", "text"],
                        temperature=0.0,  # Deterministic for style consistency
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio,
                        ),
                    ),
                )

                image_data, signature, candidate_idx = self._extract_image_and_signature(response)

                if image_data is None:
                    return GenerationResult(
                        image_data=None,
                        thought_signature=signature,
                        error="No image returned from API",
                    )

                return GenerationResult(
                    image_data=image_data,
                    thought_signature=signature,
                )

            except Exception as e:
                error_str = str(e).lower()
                print(f"[learn_door_style] Attempt {attempt + 1} error: {e}", file=sys.stderr)

                if "429" in str(e) or "rate" in error_str or "quota" in error_str:
                    if attempt < self.MAX_RETRIES - 1:
                        wait_time = self.RETRY_DELAY * (2**attempt)
                        print(
                            f"[learn_door_style] Rate limited, waiting {wait_time}s...",
                            file=sys.stderr,
                        )
                        time.sleep(wait_time)
                        continue
                    return GenerationResult(
                        image_data=None,
                        thought_signature=None,
                        error=f"Rate limited after {self.MAX_RETRIES} retries: {e}",
                    )

                return GenerationResult(
                    image_data=None,
                    thought_signature=None,
                    error=str(e),
                )

        return GenerationResult(
            image_data=None,
            thought_signature=None,
            error="Max retries exceeded",
        )

    def generate_variation(
        self,
        swatch_image_path: Path | None,
        wood_name: str,
        base_signature: bytes,
        wood_description: str | None = None,
        reference_image_path: Path | None = None,
        door_style: str = "recessed_panel",
        text_prompt: str | None = None,
        aspect_ratio: str = "9:16",
        style_notes: str = "",
    ) -> GenerationResult:
        """
        Generate a door variation with a specific wood type.

        Uses the base signature from learn_door_style to maintain door shape.

        Args:
            swatch_image_path: Path to the wood swatch reference image (None for text-only)
            wood_name: Name of the wood type (for the prompt)
            base_signature: Thought signature from learn_door_style
            wood_description: Optional description of wood characteristics
            reference_image_path: Optional path to a real door photo in this wood type
            door_style: Key from STYLES dict
            text_prompt: Optional text-only prompt (replaces swatch-based prompt)

        Returns:
            GenerationResult with image data, new signature, or error
        """
        style = STYLES.get(door_style, STYLES["recessed_panel"])
        variation_hint = style["variation_hint"]

        # Combine variation hint with user-provided structural notes
        if style_notes:
            variation_hint = f"{variation_hint} STRUCTURAL DETAILS: {style_notes}"

        if text_prompt:
            # Text-only variation — inject variation hint to preserve geometry
            prompt = f"CRITICAL: {variation_hint} {text_prompt}"
        else:
            # Build wood identity block — this is the primary directive
            wood_identity = f"The target wood type is {wood_name}."
            if wood_description:
                wood_identity += (
                    f" KEY REQUIREMENTS for this wood — follow these strictly: {wood_description}"
                )

            # Reinforce Graham joint detail in wood description (esp. for complex
            # material swaps like MDF that can cause Gemini to reinterpret joints)
            if door_style == "graham":
                wood_identity += (
                    " JOINT REMINDER: The inner frame profile uses cope-and-stick BUTT JOINTS, "
                    "NOT miters. Stile profiles run full length top to bottom; rail profiles "
                    "butt into them at right angles. NO 45-degree corners on the inner trim."
                )

            if reference_image_path:
                source_instruction = (
                    "Use the reference door photo for color, grain pattern, and texture guidance. "
                    "Use the swatch image for exact color matching. "
                )
            else:
                source_instruction = (
                    "Use the swatch image as the definitive color and grain reference. "
                    "Match the swatch EXACTLY: same color intensity, saturation, and richness. "
                    "Do NOT lighten or desaturate the wood color — preserve the exact tones from the swatch. "
                )

            drawer_instruction = ""
            if style.get("category") == "drawer":
                drawer_instruction = (
                    "Replace the wood grain pattern entirely — use the grain texture, direction, "
                    "and character from the swatch, NOT from the previous image. "
                )

            prompt = (
                f"CRITICAL STYLE PRESERVATION: {variation_hint} "
                f"Keep identical: door shape, frame proportions, edge profiles, and joint types. "
                f"Change ONLY the wood material — everything else must stay exactly the same. "
                f"{wood_identity} "
                f"{source_instruction}"
                f"{drawer_instruction}"
                f"Output: front-facing orthographic view, clean white background, "
                f"no shadows, professional lighting."
            )

        # Build content parts - signature first to reference the learned door
        parts: list[types.Part] = [
            types.Part(thought_signature=base_signature),
            types.Part.from_text(text=prompt),
        ]
        if swatch_image_path:
            parts.append(self._load_image_as_part(swatch_image_path))
        if reference_image_path:
            parts.append(self._load_image_as_part(reference_image_path))

        contents = [types.Content(role="user", parts=parts)]

        # Retry loop for rate limiting and transient errors
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["image", "text"],
                        temperature=0.3,  # Slight randomness so retries produce different results
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio,
                        ),
                    ),
                )

                image_data, new_signature, _ = self._extract_image_and_signature(response)

                if image_data is None:
                    return GenerationResult(
                        image_data=None,
                        thought_signature=new_signature,
                        error="No image returned from API",
                    )

                return GenerationResult(
                    image_data=image_data,
                    thought_signature=new_signature,
                )

            except Exception as e:
                error_str = str(e).lower()

                # Handle rate limiting
                if "429" in str(e) or "rate" in error_str or "quota" in error_str:
                    if attempt < self.MAX_RETRIES - 1:
                        wait_time = self.RETRY_DELAY * (2**attempt)
                        time.sleep(wait_time)
                        continue
                    return GenerationResult(
                        image_data=None,
                        thought_signature=None,
                        error=f"Rate limited after {self.MAX_RETRIES} retries",
                    )

                # Handle expired/invalid signature
                if "400" in str(e) or "signature" in error_str or "expired" in error_str:
                    return GenerationResult(
                        image_data=None,
                        thought_signature=None,
                        error=f"Signature error: {e}",
                    )

                # Other errors
                return GenerationResult(
                    image_data=None,
                    thought_signature=None,
                    error=str(e),
                )

        return GenerationResult(
            image_data=None,
            thought_signature=None,
            error="Max retries exceeded",
        )

    def generate_batch(
        self,
        door_image_path: Path,
        swatch_paths: list[tuple[Path, str]],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> tuple[GenerationResult | None, list[tuple[str, GenerationResult]]]:
        """
        Generate multiple variations for a door style.

        First learns the door style, then generates variations using that signature.

        Args:
            door_image_path: Path to the door style reference image
            swatch_paths: List of (swatch_path, wood_name) tuples
            progress_callback: Optional callback(current, total, wood_name)

        Returns:
            Tuple of (base_door_result, list of (wood_name, GenerationResult) tuples)
        """
        results: list[tuple[str, GenerationResult]] = []
        total = len(swatch_paths) + 1  # +1 for the initial learning step

        # Step 1: Learn the door style
        if progress_callback:
            progress_callback(0, total, "Learning door style...")

        base_result = self.learn_door_style(door_image_path)

        if base_result.error or base_result.thought_signature is None:
            # Failed to learn door style
            return base_result, []

        base_signature = base_result.thought_signature

        # Step 2: Generate variations using the learned signature
        for i, (swatch_path, wood_name) in enumerate(swatch_paths):
            if progress_callback:
                progress_callback(i + 1, total, wood_name)

            result = self.generate_variation(
                swatch_image_path=swatch_path,
                wood_name=wood_name,
                base_signature=base_signature,
            )

            results.append((wood_name, result))

        if progress_callback:
            progress_callback(total, total, "Complete")

        return base_result, results
