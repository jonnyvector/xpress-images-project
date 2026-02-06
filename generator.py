"""Gemini image generation with thought signature support."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image


@dataclass
class GenerationResult:
    """Result from a single image generation."""

    image_data: bytes | None
    thought_signature: bytes | None
    error: str | None = None
    aspect_ratio: str | None = None


class DoorGenerator:
    """Generate door style variations using Gemini 3 with thought signatures."""

    MODEL = "gemini-3-pro-image-preview"
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

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

    def _extract_image_and_signature(self, response: Any) -> tuple[bytes | None, bytes | None]:
        """Extract image data and thought signature from response."""
        image_data: bytes | None = None
        thought_signature: bytes | None = None

        if not response.candidates:
            return None, None

        content = response.candidates[0].content
        if content is None or content.parts is None:
            return None, None

        for part in content.parts:
            if hasattr(part, "thought_signature") and part.thought_signature:
                thought_signature = part.thought_signature
            if hasattr(part, "inline_data") and part.inline_data:
                image_data = part.inline_data.data

        return image_data, thought_signature

    def _get_aspect_ratio(self, image_path: Path) -> str:
        """Calculate aspect ratio string from image dimensions."""
        with Image.open(image_path) as img:
            width, height = img.size

        ratio = width / height

        # Map to closest supported Gemini aspect ratio
        if ratio > 1.6:
            return "16:9"
        elif ratio > 1.2:
            return "4:3"
        elif ratio > 0.9:
            return "1:1"
        elif ratio > 0.7:
            return "3:4"
        else:
            return "9:16"

    def learn_door_style(
        self, door_image_path: Path, aspect_ratio: str = "3:4", door_style_name: str = "cabinet door"
    ) -> GenerationResult:
        """
        Have Gemini generate its own version of the door to capture its understanding.

        This creates a thought signature that locks in the door's shape/style
        for consistent variations.

        Args:
            door_image_path: Path to the door style reference image
            aspect_ratio: Desired aspect ratio for the output (e.g., "3:4", "9:16")
            door_style_name: Name of the door style (e.g., "Adobe Cabinet Door")

        Returns:
            GenerationResult with Gemini's door image and thought signature
        """

        prompt = (
            "Generate a photorealistic product image of a Shaker-style cabinet door. "
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo, white background, professional lighting."
        )

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
                        imageConfig=types.ImageConfig(
                            aspectRatio=aspect_ratio,
                        ),
                    ),
                )

                image_data, signature = self._extract_image_and_signature(response)

                if image_data is None:
                    return GenerationResult(
                        image_data=None,
                        thought_signature=signature,
                        error="No image returned from API",
                        aspect_ratio=aspect_ratio,
                    )

                return GenerationResult(
                    image_data=image_data,
                    thought_signature=signature,
                    aspect_ratio=aspect_ratio,
                )

            except Exception as e:
                error_str = str(e).lower()

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
        swatch_image_path: Path,
        wood_name: str,
        base_signature: bytes,
        aspect_ratio: str = "3:4",
        wood_description: str | None = None,
    ) -> GenerationResult:
        """
        Generate a door variation with a specific wood type.

        Uses the base signature from learn_door_style to maintain door shape.

        Args:
            swatch_image_path: Path to the wood swatch reference image
            wood_name: Name of the wood type (for the prompt)
            base_signature: Thought signature from learn_door_style
            aspect_ratio: Desired aspect ratio for the output
            wood_description: Optional description of wood characteristics

        Returns:
            GenerationResult with image data, new signature, or error
        """
        # Build prompt with optional wood description
        base_prompt = (
            f"Using the same door style and shape from before, change the wood "
            f"to match this swatch image. The wood type is {wood_name}. "
            f"Keep the exact same door style, shape, and panel design. "
            f"Only change the wood grain, color, and texture to match the swatch. "
        )
        if wood_description:
            base_prompt += f"Wood characteristics: {wood_description} "
        base_prompt += "Produce a photorealistic product image suitable for e-commerce."
        prompt = base_prompt

        # Build content parts - signature first to reference the learned door
        parts: list[types.Part] = [
            types.Part(thought_signature=base_signature),
            types.Part.from_text(text=prompt),
            self._load_image_as_part(swatch_image_path),
        ]

        contents = [types.Content(role="user", parts=parts)]

        # Retry loop for rate limiting and transient errors
        for attempt in range(self.MAX_RETRIES):
            try:
                response = self.client.models.generate_content(
                    model=self.MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_modalities=["image", "text"],
                        imageConfig=types.ImageConfig(
                            aspectRatio=aspect_ratio,
                        ),
                    ),
                )

                image_data, new_signature = self._extract_image_and_signature(response)

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
