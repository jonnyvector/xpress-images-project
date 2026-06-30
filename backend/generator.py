"""Gemini image generation with thought signature support."""

import io
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

from backend.materials import MIME_MAP
from backend.styles.catalog import STYLES

CANVAS_SIZE = 1000


def add_watermark(
    image_bytes: bytes,
    wood_name: str = "",
    y_offset: int = 0,
    force_dark_text: bool = False,
    image_scale: float = 1.0,
) -> bytes:
    """Place image on a 1000x1000 white canvas and add watermark text."""
    # Strip marketing suffixes from display name
    display_name = wood_name
    if display_name.lower().endswith("(new sample)"):
        display_name = display_name[: -len("(new sample)")].strip()

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Reserve strips at top (label) and bottom ("Example") so neither is ever clipped
    label_area_h = CANVAS_SIZE // 13 if display_name else 0  # ~77px
    example_area_h = CANVAS_SIZE // 13  # ~77px — always reserved for "Example" text
    available_h = CANVAS_SIZE - label_area_h - example_area_h

    # Watermark text sized to canvas
    font_size = CANVAS_SIZE // 22

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default(size=font_size)

    # Compute baseline (scale=1.0) image dimensions for fixed text anchors.
    # Text positions must not shift when image_scale changes.
    orig_w, orig_h = img.size
    base_ratio = min(CANVAS_SIZE / orig_w, available_h / orig_h)
    base_img_h = int(orig_h * base_ratio)
    base_offset_y = label_area_h + (available_h - base_img_h) // 2
    base_img_bottom = base_offset_y + base_img_h

    # Fit image to base size first, then apply scale
    img.thumbnail((CANVAS_SIZE, available_h), Image.LANCZOS)
    if image_scale != 1.0:
        new_w = int(img.width * image_scale)
        new_h = int(img.height * image_scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255, 255))
    offset_x = (CANVAS_SIZE - img.width) // 2
    offset_y = label_area_h + (available_h - img.height) // 2
    canvas.paste(img, (offset_x, offset_y), img)

    text_pad = CANVAS_SIZE // 40  # ~25px gap
    draw = ImageDraw.Draw(canvas)

    # Draw "Example" below the door — anchored to baseline geometry, not scaled size
    text = "Example"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = (CANVAS_SIZE - text_w) // 2
    text_y = base_img_bottom + text_pad - 4 + y_offset
    draw.text((text_x, text_y), text, font=font, fill=(0, 0, 0, 255))

    # Draw color/wood name above the door — anchored to baseline geometry
    if display_name:
        label_bbox = draw.textbbox((0, 0), display_name, font=font)
        label_w = label_bbox[2] - label_bbox[0]
        label_h = label_bbox[3] - label_bbox[1]
        label_x = (CANVAS_SIZE - label_w) // 2
        label_y = max(0, base_offset_y - text_pad - label_h)
        draw.text((label_x, label_y), display_name, font=font, fill=(0, 0, 0, 255))

    out = io.BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()


@dataclass
class GenerationResult:
    """Result from a single image generation."""

    image_data: bytes | None
    thought_signature: bytes | None
    error: str | None = None


def _corner_instruction(corner_style: str) -> str:
    if corner_style == "bullnose":
        return (
            "OUTER CORNERS: The four outer corners must be ROUNDED / BULLNOSE "
            "— smooth, convex radius corners, NOT sharp 90-degree edges. "
        )
    return "OUTER CORNERS: Sharp 90-degree square corners — NO rounding. "


def _build_rtf_prompt(
    wood_name: str,
    hex_color: str | None,
    wood_description: str | None,
    rtf_finish: str | None,
    variation_hint: str,
    corner_style: str,
    is_rtf_drawer: bool,
) -> str:
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
        hex_clause = f"The EXACT color is #{hex_color} — match this hex value precisely. " if hex_color else ""
        source_instruction = (
            "Use the swatch image as the definitive color reference. "
            f"{hex_clause}"
            "Match the swatch EXACTLY: same color, sheen, and finish. "
            "This is a SOLID, UNIFORM color — there is NO wood grain, NO texture variation, "
            "NO streaks, NO mottling. The surface must be perfectly smooth and consistent "
            "with a single flat color across the entire door face. "
        )

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

    return (
        f"{grain_override}"
        f"CRITICAL STYLE PRESERVATION: {variation_hint} "
        f"Keep identical: door shape, frame proportions, edge profiles, and joint types. "
        f"Change ONLY the surface color/finish — everything else must stay exactly the same. "
        f"MATERIAL: This is RTF (Rigid Thermofoil) — a smooth vinyl wrap over MDF. "
        f"There is NO natural wood grain. The surface is uniform and consistent. "
        f"{_corner_instruction(corner_style)}"
        f"{rtf_identity} "
        f"{source_instruction}"
        f"Output: front-facing orthographic view, STARK PURE WHITE background (#FFFFFF), "
        f"absolutely no shadows, no gradients, no grey tones in the background — "
        f"the background must be perfectly uniform bright white. Professional lighting."
    )


def _build_wood_prompt(
    wood_name: str,
    wood_description: str | None,
    reference_image_path: Path | None,
    door_style: str,
    variation_hint: str,
    corner_style: str,
    is_rtf_drawer: bool,
) -> str:
    is_grainless = wood_description and "grainless" in wood_description.lower()

    if is_grainless:
        wood_identity = f"The target material is {wood_name}."
        if wood_description:
            wood_identity += (
                f" KEY REQUIREMENTS for this material — follow these strictly: {wood_description}"
            )
    else:
        wood_identity = f"The target wood type is {wood_name}."
        if wood_description:
            wood_identity += (
                f" KEY REQUIREMENTS for this wood — follow these strictly: {wood_description}"
            )

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
    elif is_grainless:
        source_instruction = (
            "Use the swatch image as the definitive color and texture reference. "
            "Match the swatch EXACTLY: same color intensity, saturation, and uniformity. "
            "The surface has NO wood grain — it must be smooth and uniform. "
        )
    else:
        source_instruction = (
            "Use the swatch image as the definitive color and grain reference. "
            "Match the swatch EXACTLY: same color intensity, saturation, and richness. "
            "Do NOT lighten or desaturate the wood color — preserve the exact tones from the swatch. "
        )

    drawer_instruction = ""
    if is_rtf_drawer:
        drawer_instruction = (
            "Replace the wood grain pattern entirely — use the grain texture "
            "and character from the swatch, NOT from the previous image. "
            "GRAIN DIRECTION: The center panel grain must run HORIZONTALLY (left to right). "
            "Do NOT use vertical grain on the center panel. "
        )

    material_word = "material" if is_grainless else "wood material"
    color_source = "material color" if is_grainless else "wood color"

    return (
        f"CRITICAL STYLE PRESERVATION: {variation_hint} "
        f"Keep identical: door shape, frame proportions, edge profiles, and joint types. "
        f"Change ONLY the {material_word} — everything else must stay exactly the same. "
        f"{_corner_instruction(corner_style)}"
        f"{wood_identity} "
        f"{source_instruction}"
        f"{drawer_instruction}"
        f"COLOR NEUTRALIZATION: The reference door image (from the learned style) is for "
        f"SHAPE and STRUCTURE only — do NOT inherit any color cast, tint, or warmth bias "
        f"from the reference door. If the reference door appears reddish, warm, or cool-tinted, "
        f"IGNORE that bias entirely. The {color_source} must come purely from the swatch image "
        f"and the description above — render the color neutrally and accurately based on "
        f"those sources, not on any cast from the reference door. "
        f"Output: front-facing orthographic view, STARK PURE WHITE background (#FFFFFF), "
        f"absolutely no shadows, no gradients, no grey tones in the background — "
        f"the background must be perfectly uniform bright white. Professional lighting."
    )



class DoorGenerator:
    """Generate door style variations using Gemini 3 with thought signatures."""

    DEFAULT_MODEL = "gemini-3-pro-image-preview"
    MAX_RETRIES = 5
    RETRY_DELAY = 15  # seconds (exponential backoff: 15, 30, 60, 120, 240)

    def __init__(self, api_key: str, model: str | None = None) -> None:
        """Initialize the generator with API key and optional model override."""
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=600_000),  # 10 min in ms
        )
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
        mime_type = MIME_MAP.get(suffix, "image/jpeg")

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

    def _call_with_retry(
        self, contents: list[Any], config: Any, *, label: str
    ) -> tuple[Any | None, "GenerationResult | None"]:
        """Call generate_content with retry/backoff for transient errors.

        Returns (response, None) on success, or (None, GenerationResult) when a
        terminal error occurs. Handles rate-limit backoff (429/quota), invalid
        signature (400), and generic errors uniformly — callers map the
        response to their own GenerationResult.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                return response, None
            except Exception as e:
                error_str = str(e).lower()
                print(f"[{label}] Attempt {attempt + 1} error: {e}", file=sys.stderr)

                if "429" in str(e) or "rate" in error_str or "quota" in error_str:
                    if attempt < self.MAX_RETRIES - 1:
                        wait_time = self.RETRY_DELAY * (2**attempt)
                        print(
                            f"[{label}] Rate limited, waiting {wait_time}s...",
                            file=sys.stderr,
                        )
                        time.sleep(wait_time)
                        continue
                    return None, GenerationResult(
                        image_data=None,
                        thought_signature=None,
                        error=f"Rate limited after {self.MAX_RETRIES} retries: {e}",
                    )

                if "400" in str(e) or "signature" in error_str or "expired" in error_str:
                    return None, GenerationResult(
                        image_data=None,
                        thought_signature=None,
                        error=f"Signature error: {e}",
                    )

                return None, GenerationResult(
                    image_data=None,
                    thought_signature=None,
                    error=str(e),
                )

        return None, GenerationResult(
            image_data=None,
            thought_signature=None,
            error="Max retries exceeded",
        )

    def learn_door_style(
        self,
        door_image_path: Path,
        door_style_name: str = "cabinet door",
        door_style: str = "recessed_panel",
        aspect_ratio: str = "9:16",
        corner_style: str = "sharp",
        material_type: str = "wood",
        learn_in_maple: bool = False,
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
            learn_in_maple: If True, ask Gemini to recreate the door in maple
                select instead of exact replica, forcing a new generation.

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

        # "Learn in Maple Select" mode: force Gemini to generate a truly new
        # image (in maple select wood) instead of replicating the original
        # material, which can produce a stronger thought signature.
        maple_swatch_path: Path | None = None
        if learn_in_maple:
            prompt += (
                " MATERIAL OVERRIDE: Instead of replicating the exact wood material "
                "shown in the reference, recreate this door in MAPLE SELECT wood. "
                "Maple Select has the least amount of color and grain variation — "
                "consistent light cream with a subtle golden warmth, like pale straw "
                "or light honey-cream. The entire door must be one uniform color — "
                "the frame and panel should look like they came from the same board. "
                "A swatch of the target maple select wood is provided below. "
                "You MUST generate a brand new image — do NOT return the reference image."
            )
            maple_swatch_path = Path("swatches/wood/maple_select.jpg")

        # Load the reference image with HIGH media resolution so Gemini uses
        # ~1120 tokens to analyze it (vs default 256) — critical for reading
        # fine details like exact stile/rail widths from the input image.
        ref_image_bytes = door_image_path.read_bytes()
        suffix = door_image_path.suffix.lower()
        ref_mime = MIME_MAP.get(suffix, "image/jpeg")
        ref_part = types.Part.from_bytes(
            data=ref_image_bytes,
            mime_type=ref_mime,
            media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )

        parts: list[types.Part] = [
            types.Part.from_text(text=prompt),
            ref_part,
        ]

        if maple_swatch_path and maple_swatch_path.exists():
            swatch_bytes = maple_swatch_path.read_bytes()
            swatch_suffix = maple_swatch_path.suffix.lower()
            parts.append(
                types.Part.from_bytes(
                    data=swatch_bytes,
                    mime_type=MIME_MAP.get(swatch_suffix, "image/jpeg"),
                )
            )

        contents = [types.Content(role="user", parts=parts)]

        config = types.GenerateContentConfig(
            response_modalities=["image", "text"],
            temperature=0.0,  # Deterministic for style consistency
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        )
        response, error_result = self._call_with_retry(
            contents, config, label="learn_door_style"
        )
        if error_result is not None:
            return error_result

        image_data, signature, _ = self._extract_image_and_signature(response)

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
        is_rtf_drawer = style.get("category") == "drawer"
        variation_hint = style["variation_hint"]

        # Combine variation hint with user-provided structural notes
        if style_notes:
            variation_hint = f"{variation_hint} STRUCTURAL DETAILS: {style_notes}"

        if text_prompt:
            prompt = f"CRITICAL: {variation_hint} {text_prompt}"
        elif material_type == "rtf":
            prompt = _build_rtf_prompt(
                wood_name, hex_color, wood_description, rtf_finish,
                variation_hint, corner_style, is_rtf_drawer,
            )
        else:
            prompt = _build_wood_prompt(
                wood_name, wood_description, reference_image_path,
                door_style, variation_hint, corner_style, is_rtf_drawer,
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

        config = types.GenerateContentConfig(
            response_modalities=["image", "text"],
            temperature=0.3,
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        )
        response, error_result = self._call_with_retry(
            contents, config, label="generate_variation"
        )
        if error_result is not None:
            return error_result

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

    def generate_variation_from_reference(
        self,
        reference_image_path: Path,
        swatch_image_path: Path | None,
        wood_name: str,
        variation_hint: str,
        wood_description: str | None = None,
        aspect_ratio: str = "16:9",
        corner_style: str = "sharp",
    ) -> GenerationResult:
        """Generate a variation using a reference image as the geometric anchor.

        Mirrors the learn_in_maple flow exactly: minimal prompt, high-res
        reference image, temperature 0.0, and a swatch for the target wood.
        """
        prompt = (
            "Generate an exact replica of this drawer front. "
            f"MATERIAL OVERRIDE: Instead of replicating the exact wood material "
            f"shown in the reference, recreate this door in {wood_name} wood. "
        )
        if wood_description:
            prompt += f"{wood_description} "
        prompt += (
            "A swatch of the target wood is provided below. "
            "GRAIN DIRECTION: The wood grain on the center panel must run HORIZONTALLY (left to right). Do NOT use vertical grain on the panel. "
            "You MUST generate a brand new image — do NOT return the reference image."
        )

        ref_bytes = reference_image_path.read_bytes()
        ref_part = types.Part.from_bytes(
            data=ref_bytes,
            mime_type="image/png",
            media_resolution=types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )

        parts: list[types.Part] = [
            types.Part.from_text(text=prompt),
            ref_part,
        ]
        if swatch_image_path:
            parts.append(self._load_image_as_part(swatch_image_path))

        contents = [types.Content(role="user", parts=parts)]

        config = types.GenerateContentConfig(
            response_modalities=["image", "text"],
            temperature=0.0,
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        )
        response, error_result = self._call_with_retry(
            contents, config, label="generate_variation_from_reference"
        )
        if error_result is not None:
            return error_result

        image_data, _, _ = self._extract_image_and_signature(response)

        if image_data is None:
            return GenerationResult(
                image_data=None,
                thought_signature=None,
                error="No image returned from API",
            )

        return GenerationResult(
            image_data=image_data,
            thought_signature=None,
        )
