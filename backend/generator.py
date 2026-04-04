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

from backend.styles.catalog import STYLES

CANVAS_SIZE = 1000


def add_watermark(image_bytes: bytes, wood_name: str = "", y_offset: int = 0, force_dark_text: bool = False) -> bytes:
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
    # Base position: vertically centered; y_offset moves up (negative) or down (positive)
    text_y = (CANVAS_SIZE - text_h) // 2 + y_offset

    # Dark colors that need white/light watermark text
    LIGHT_TEXT_NAMES = {
        "moonlight",
        "chocolate pear",
        "cherry blossom",
        "cherry blossom rtf",
        "gibraltar taction oak",
        "gibraltar taction rtf",
        "dark italian rtf",
        "gauntlet grey supermatte",
        "grenada",
        "mysterious supermatte",
        "siena supermatte",
    }
    name_lower = wood_name.lower()
    use_light_text = not force_dark_text and (
        "walnut" in name_lower
        or "black" in name_lower
        or name_lower in LIGHT_TEXT_NAMES
    )
    if use_light_text:
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



class DoorGenerator:
    """Generate door style variations using Gemini 3 with thought signatures."""

    DEFAULT_MODEL = "gemini-3-pro-image-preview"
    MAX_RETRIES = 5
    RETRY_DELAY = 15  # seconds (exponential backoff: 15, 30, 60, 120, 240)

    def __init__(self, api_key: str, model: str | None = None) -> None:
        """Initialize the generator with API key and optional model override."""
        self.client = genai.Client(api_key=api_key)
        self.model = model or self.DEFAULT_MODEL

    def _load_image_as_part(
        self, image_path: Path, rotate_90: bool = False
    ) -> types.Part:
        """Load an image file as a Gemini Part.

        Args:
            image_path: Path to the image file.
            rotate_90: If True, rotate the image 90° counter-clockwise before
                sending.  Used for RTF woodgrain swatches on drawer fronts so
                the grain direction in the reference image matches the desired
                horizontal output.
        """
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

        if rotate_90:
            img = Image.open(io.BytesIO(image_bytes))
            img = img.rotate(90, expand=True)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_bytes = buf.getvalue()
            mime_type = "image/png"

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
        corner_style: str = "sharp",
        material_type: str = "wood",
    ) -> GenerationResult:
        """
        Have Gemini generate its own version of the door to capture its understanding.

        This creates a thought signature that locks in the door's shape/style
        for consistent variations.

        Args:
            door_image_path: Path to the door style reference image
            door_style_name: Name of the door style (e.g., "Adobe Cabinet Door")
            door_style: Key from STYLES dict
            corner_style: "sharp" or "bullnose"

        Returns:
            GenerationResult with Gemini's door image and thought signature
        """
        style = STYLES.get(door_style, STYLES["recessed_panel"])
        prompt = style["learn_prompt"]

        # Inject corner style instruction
        if corner_style == "bullnose":
            prompt += (
                " OUTER CORNERS: The four outer corners of the door must be "
                "ROUNDED / BULLNOSE — smooth, convex radius corners, NOT sharp "
                "90-degree edges. The bullnose radius should be clearly visible."
            )
        else:
            prompt += (
                " OUTER CORNERS: The four outer corners of the door must be "
                "SHARP 90-degree square corners — NO rounding, NO radius, "
                "NO bullnose. Crisp, clean square edges."
            )

        # Inject material type instruction
        if material_type == "rtf":
            prompt += (
                " MATERIAL: This is an RTF (Rigid Thermofoil) door — the surface "
                "is a smooth, uniform vinyl/thermofoil wrap over MDF substrate. "
                "The finish is NOT natural wood. It has a consistent, uniform color "
                "with no natural wood grain variation. The surface may be matte, "
                "satin, or have a subtle embossed texture pattern."
            )

        # Inject dimension preservation instruction
        prompt += (
            " CRITICAL DIMENSIONS: Match the exact aspect ratio, height-to-width proportions, "
            "and overall dimensions of the reference image precisely. Do NOT stretch or compress "
            "the door. Each stile and rail must match its own width exactly as shown in the reference — "
            "stiles and rails may differ from each other, reproduce whatever ratio the reference shows."
        )

        # Load the reference image with HIGH media resolution so Gemini uses
        # ~1120 tokens to analyze it (vs default 256) — critical for reading
        # fine details like exact stile/rail widths from the input image.
        ref_image_bytes = door_image_path.read_bytes()
        suffix = door_image_path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        ref_mime = mime_map.get(suffix, "image/jpeg")
        ref_part = types.Part.from_bytes(
            data=ref_image_bytes,
            mime_type=ref_mime,
            media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )

        parts: list[types.Part] = [
            types.Part.from_text(text=prompt),
            ref_part,
        ]

        contents = [types.Content(role="user", parts=parts)]

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
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

                if not signature:
                    print(
                        "[learn_door_style] WARNING: Image returned but no thought signature. "
                        "Variations will not maintain style consistency.",
                        file=sys.stderr,
                    )
                    return GenerationResult(
                        image_data=image_data,
                        thought_signature=None,
                        error="No thought signature returned — cannot generate consistent variations. "
                        "Please retry learning.",
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
        corner_style: str = "sharp",
        material_type: str = "wood",
        hex_color: str | None = None,
        rtf_finish: str | None = None,
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
        # Validate thought signature before proceeding
        if not base_signature:
            return GenerationResult(
                image_data=None,
                thought_signature=None,
                error="No thought signature provided — cannot generate variation without a "
                "learned style signature. Please re-learn the door style first.",
            )

        style = STYLES.get(door_style, STYLES["recessed_panel"])
        variation_hint = style["variation_hint"]

        # Combine variation hint with user-provided structural notes
        if style_notes:
            variation_hint = f"{variation_hint} STRUCTURAL DETAILS: {style_notes}"

        if text_prompt:
            # Text-only variation — inject variation hint to preserve geometry
            prompt = f"CRITICAL: {variation_hint} {text_prompt}"
        elif material_type == "rtf":
            # RTF (Rigid Thermofoil) variation
            rtf_identity = f"The target RTF color/finish is {wood_name}."
            if hex_color:
                rtf_identity += f" The EXACT target color is #{hex_color}."
            if wood_description:
                rtf_identity += (
                    f" KEY REQUIREMENTS for this finish — follow these strictly: {wood_description}"
                )

            if rtf_finish == "woodgrain":
                source_instruction = (
                    "Use the swatch image as the definitive color and grain pattern reference. "
                    "Match the swatch EXACTLY: same color tones and printed/embossed wood grain texture. "
                )
            else:
                # Solid color RTF
                hex_clause = ""
                if hex_color:
                    hex_clause = (
                        f"The EXACT color is #{hex_color} — match this hex value precisely. "
                    )
                source_instruction = (
                    "Use the swatch image as the definitive color reference. "
                    f"{hex_clause}"
                    "Match the swatch EXACTLY: same color, sheen, and finish. "
                    "This is a SOLID, UNIFORM color — there is NO wood grain, NO texture variation, "
                    "NO streaks, NO mottling. The surface must be perfectly smooth and consistent "
                    "with a single flat color across the entire door face. "
                )

            # Corner style instruction
            if corner_style == "bullnose":
                corner_instruction = (
                    "OUTER CORNERS: The four outer corners must be ROUNDED / BULLNOSE "
                    "— smooth, convex radius corners, NOT sharp 90-degree edges. "
                )
            else:
                corner_instruction = (
                    "OUTER CORNERS: Sharp 90-degree square corners — NO rounding. "
                )

            is_rtf_drawer = style.get("category") == "drawer"
            if rtf_finish == "woodgrain":
                if is_rtf_drawer:
                    grain_override = (
                        "HORIZONTAL GRAIN ONLY. "
                        "This door is covered in a single seamless sheet of horizontal woodgrain vinyl. "
                        "The grain flows continuously from the very left edge to the very right edge "
                        "without interruption across the entire surface. "
                        "Monolithic horizontal wood texture — do NOT break the grain direction for any part of the door. "
                    )
                else:
                    grain_override = (
                        "VERTICAL GRAIN ONLY. "
                        "This door is covered in a single seamless sheet of vertical woodgrain vinyl. "
                        "The grain flows continuously from the very top edge to the very bottom edge "
                        "without interruption across the entire surface. "
                        "Monolithic vertical wood texture — do NOT break the grain direction for any part of the door. "
                    )
            else:
                grain_override = ""

            prompt = (
                f"{grain_override}"
                f"CRITICAL STYLE PRESERVATION: {variation_hint} "
                f"Keep identical: door shape, frame proportions, edge profiles, and joint types. "
                f"Change ONLY the surface color/finish — everything else must stay exactly the same. "
                f"MATERIAL: This is RTF (Rigid Thermofoil) — a smooth vinyl wrap over MDF. "
                f"There is NO natural wood grain. The surface is uniform and consistent. "
                f"{corner_instruction}"
                f"{rtf_identity} "
                f"{source_instruction}"
                f"Output: front-facing orthographic view, STARK PURE WHITE background (#FFFFFF), "
                f"absolutely no shadows, no gradients, no grey tones in the background — "
                f"the background must be perfectly uniform bright white. Professional lighting."
            )
        else:
            # Wood variation — full grain/material handling
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
                    "Replace the wood grain pattern entirely — use the grain texture "
                    "and character from the swatch, NOT from the previous image. "
                    "GRAIN DIRECTION: The center panel grain must run HORIZONTALLY (left to right). "
                    "Do NOT use vertical grain on the center panel. "
                )

            # Corner style instruction
            if corner_style == "bullnose":
                corner_instruction = (
                    "OUTER CORNERS: The four outer corners must be ROUNDED / BULLNOSE "
                    "— smooth, convex radius corners, NOT sharp 90-degree edges. "
                )
            else:
                corner_instruction = (
                    "OUTER CORNERS: Sharp 90-degree square corners — NO rounding. "
                )

            prompt = (
                f"CRITICAL STYLE PRESERVATION: {variation_hint} "
                f"Keep identical: door shape, frame proportions, edge profiles, and joint types. "
                f"Change ONLY the wood material — everything else must stay exactly the same. "
                f"{corner_instruction}"
                f"{wood_identity} "
                f"{source_instruction}"
                f"{drawer_instruction}"
                f"Output: front-facing orthographic view, STARK PURE WHITE background (#FFFFFF), "
                f"absolutely no shadows, no gradients, no grey tones in the background — "
                f"the background must be perfectly uniform bright white. Professional lighting."
            )

        # Build content parts - signature first to reference the learned door
        sig_size = len(base_signature) if base_signature else 0
        print(
            f"[generate_variation] Using thought signature ({sig_size} bytes) for {wood_name}",
            file=sys.stderr,
        )
        parts: list[types.Part] = [
            types.Part(thought_signature=base_signature),
            types.Part.from_text(text=prompt),
        ]
        if swatch_image_path:
            rotate_swatch = rtf_finish == "woodgrain" and is_rtf_drawer
            parts.append(self._load_image_as_part(swatch_image_path, rotate_90=rotate_swatch))
        if reference_image_path:
            parts.append(self._load_image_as_part(reference_image_path))

        contents = [types.Content(role="user", parts=parts)]

        # Retry loop for rate limiting and transient errors
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
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
