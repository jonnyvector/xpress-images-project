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
    text_y = CANVAS_SIZE - margin // 2 - text_h // 2 - 60

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
            "Generate an exact replica of the reference image."
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "Preserve the exact flat recessed panel design from before."
        ),
    },
    "shaker": {
        "name": "Shaker",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image."
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "Preserve the exact Shaker-style flat recessed panel design from before."
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
            "Use the reference image to match the exact design details: "
            "Match the wood type, panel depth, edge profile, rail/stile proportions, and wood grain direction exactly. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, clean white background, no shadows, professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "Preserve the exact Shaker-style flat recessed panel drawer front design from before."
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

        if text_prompt:
            # Text-only variation — inject variation hint to preserve geometry
            prompt = f"CRITICAL: {variation_hint} {text_prompt}"
        elif reference_image_path:
            # Build prompt with optional wood description and reference image
            base_prompt = (
                f"Using the EXACT same door style from before, change ONLY the wood material "
                f"to match the reference door photo and swatch image provided. The wood type is {wood_name}. "
                f"Use the reference door photo for color, grain pattern, and texture guidance. "
                f"Use the swatch for exact color matching. "
                f"CRITICAL: {variation_hint} "
                f"Keep identical: door shape, frame proportions, edge profiles. "
                f"Match the wood appearance EXACTLY: same color intensity, saturation, and richness. "
                f"Do NOT lighten or desaturate the wood color. "
            )
            if wood_description:
                base_prompt += f"Wood characteristics: {wood_description} "
            if style.get("category") == "drawer":
                base_prompt += (
                    "Replace the wood grain pattern entirely — use the grain texture, direction, "
                    "and character from the swatch, NOT from the previous image. "
                )
            base_prompt += (
                "Output: front-facing orthographic view, clean white background, "
                "no shadows, professional lighting."
            )
            prompt = base_prompt
        else:
            base_prompt = (
                f"Using the EXACT same door style from before, change ONLY the wood material "
                f"to match this swatch image. The wood type is {wood_name}. "
                f"CRITICAL: {variation_hint} "
                f"Keep identical: door shape, frame proportions, edge profiles. "
                f"Match the swatch EXACTLY: same color intensity, saturation, and richness. "
                f"Do NOT lighten or desaturate the wood color - preserve the exact tones from the swatch. "
            )
            if wood_description:
                base_prompt += f"Wood characteristics: {wood_description} "
            if style.get("category") == "drawer":
                base_prompt += (
                    "Replace the wood grain pattern entirely — use the grain texture, direction, "
                    "and character from the swatch, NOT from the previous image. "
                )
            base_prompt += (
                "Output: front-facing orthographic view, clean white background, "
                "no shadows, professional lighting."
            )
            prompt = base_prompt

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
                        temperature=0.0,  # Deterministic for consistency
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
