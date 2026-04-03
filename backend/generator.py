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


STYLES: dict[str, dict[str, str]] = {
    "davenport": {
        "name": "Davenport",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of this door. "
            "This door has TWO defining features you must get exactly right: "
            "1) The outer perimeter of the door has a BEADED EDGE — a small rounded bead/raised profile runs along the entire outside edge of the frame. "
            "2) The center panel is RECESSED and consists of FOUR vertical tongue-and-groove planks with V-groove lines between them — NOT a single flat panel. The planks sit BELOW the frame surface. "
            "All stiles and rails must be the same width."
        ),
        "variation_hint": (
            "Preserve the exact door structure. Change only the wood material. "
            "CRITICAL: The outer perimeter must have the BEADED EDGE profile. "
            "The center panel is RECESSED — THREE vertical tongue-and-groove/beadboard planks with V-groove lines sitting BELOW the frame surface — NOT a single flat panel. "
            "All stiles and rails must remain the same width."
        ),
    },
    "rtf_minimal": {
        "name": "Minimal RTF (Test)",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of this door."
        ),
        "variation_hint": (
            "Preserve the exact door structure. Change only the surface color/finish."
        ),
    },
    "rtf_drawer_minimal": {
        "name": "Minimal RTF (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of this drawer front."
        ),
        "variation_hint": (
            "Preserve the exact drawer front structure. Change only the surface color/finish."
        ),
    },
    "rtf_drawer_shaker_shallow": {
        "name": "Shaker Shallow RTF (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "STUDY THE REFERENCE IMAGE CAREFULLY before generating — every dimension must come from the image, not from standard cabinetry conventions. "
            "This is a SHALLOW SHAKER style RTF drawer front — flat recessed center panel, clean square-edge framing. "
            "PANEL DEPTH: The center panel steps down only 1/8\" below the frame surface — this is an extremely shallow recess. "
            "Because of this minimal depth, the shadow cast along the panel edges is very subtle and faint — NOT a deep or dramatic shadow. "
            "CRITICAL PROPORTIONS from the reference image: "
            "The vertical stiles (left and right frame members) are 1.75x wider than the horizontal rails (top and bottom frame members). "
            "The rails are intentionally NARROW — do NOT widen them to match standard 2-inch cabinet proportions. "
            "Measure the stile and rail widths directly from the reference image and replicate them exactly. "
            "The center panel occupies most of the visual width — the slim rails leave a large open panel area. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHALLOW SHAKER drawer front — flat recessed panel with only a 1/8\" step down from frame. "
            "The panel shadow is very faint due to the minimal recess depth — do NOT deepen it. "
            "PROPORTIONS MUST BE PRESERVED EXACTLY: stiles are 1.75x wider than rails. "
            "The rails are NARROW — do NOT use standard 2-inch rail width. "
            "The large open panel area is a defining visual characteristic. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact stile width, rail width, 1/8\" panel depth, and square-edge framing from before."
        ),
    },
    "rtf_drawer_shaker": {
        "name": "Shaker RTF (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SHAKER style RTF drawer front — it has a FLAT, RECESSED center panel "
            "with clean square-edge framing. "
            "The center panel is FLAT and sits BELOW the frame — it is NOT raised and has NO bevel. "
            "The frame has SQUARE, CLEAN inner edges — NO decorative routing, NO ogee, NO chamfer. "
            "The inner edge where frame meets panel is a simple sharp 90-degree step down. "
            "CRITICAL PROPORTIONS: The vertical stiles (left and right frame members) are TWICE as wide "
            "as the horizontal rails (top and bottom frame members). "
            "If the rails are 1 unit wide, the stiles must be 2 units wide. "
            "This wide-stile proportion is a defining feature — do NOT make stiles and rails the same width. "
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, and this exact 2:1 stile-to-rail proportion. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHAKER style drawer front — the center panel must be FLAT and RECESSED "
            "below the frame. Do NOT make a raised panel. The frame inner edges are SQUARE and CLEAN — "
            "no decorative routing. "
            "CRITICAL PROPORTIONS: The vertical stiles must be TWICE as wide as the horizontal rails — "
            "do NOT make them equal width. This 2:1 stile-to-rail ratio must be preserved exactly. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact stile width, rail width, panel depth, and square-edge framing from before."
        ),
    },
    "rtf_drawer_bevel": {
        "name": "Bevel RTF (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a BEVEL style RTF drawer front. Study the construction carefully — it is a SINGLE SOLID SLAB. "
            "THERE IS NO FRAME. THERE ARE NO RAILS. THERE ARE NO STILES. THERE IS NO RAISED OR RECESSED PANEL. "
            "Do NOT construct a frame-and-panel door. Do NOT add rails or stiles around a center panel. "
            "The face is ONE continuous surface — a single flat slab of RTF thermofoil material. "
            "THE DEFINING FEATURE — THE BEVEL: A wide angled bevel wraps ALL FOUR SIDES of the face (top, bottom, left, right). "
            "The bevel is an angled surface — it slopes from the outer perimeter edge INWARD and DOWNWARD "
            "to meet the flat center field. The outer rim of the slab is the HIGHEST point; "
            "the bevel surface descends at an angle toward the center. "
            "The bevel width is substantial — roughly 15–20% of the total face width on each edge. "
            "The bevel angle is approximately 45 degrees. "
            "The four bevel planes meet at the four corners — they do NOT leave a square outer rim. "
            "CENTER FIELD: The center of the face is completely FLAT, SMOOTH, and UNIFORM — "
            "it is NOT raised, NOT recessed (relative to the bevel's lower edge), NOT textured. "
            "The flat center field sits at the lowest point of the face, below the outer rim. "
            "MATERIAL: RTF thermofoil — solid uniform color, smooth finish, NO wood grain, "
            "no texture variation across the surface. "
            "The lighting should show the bevel clearly: the top and left bevel faces catch light "
            "(brighter), the bottom and right bevel faces are in shadow (darker). "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). "
            "Absolutely no shadows, no gradients, no grey tones — the background must be perfectly "
            "uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a BEVEL style RTF drawer front — a SINGLE SOLID SLAB with NO frame, "
            "NO rails, NO stiles, NO raised or recessed panel construction of any kind. "
            "DO NOT add a frame. DO NOT add a panel inside a frame. "
            "THE BEVEL IS THE ONLY FEATURE: A wide angled bevel (approximately 45 degrees, ~15–20% of face width) "
            "wraps ALL FOUR sides of the face, sloping from the outer rim DOWNWARD to the flat center field. "
            "The four bevel planes meet at the corners. The center is completely FLAT and SMOOTH. "
            "Change ONLY the RTF surface color/finish. Preserve the exact bevel angle, bevel width, "
            "flat center field, and single-slab construction from before."
        ),
    },
    # Test style - minimal prompting
    "minimal": {
        "name": "Minimal (Test)",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of this door. "
            "All stiles and rails must be the same width — do not make any frame member wider than the others."
        ),
        "variation_hint": (
            "Preserve the exact door structure. Change only the wood material. "
            "All stiles and rails must remain the same width."
        ),
    },
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
    "vienna": {
        "name": "Vienna",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a VIENNA style cabinet door — a SLAB VENEER door with APPLIED BEAD MOLDING on the outside edge. "
            "CRITICAL CONSTRUCTION: This is a SLAB door — the panel is ONE continuous flat surface of veneer. "
            "There is NO separate frame and panel construction. There are NO rails or stiles. "
            "The entire face is a single flat veneered surface. "
            "BEAD MOLDING DETAIL: A small beaded molding strip (approximately 3/8\" wide) is applied around "
            "the OUTSIDE perimeter edge of the door face. This solid wood molding sits slightly RAISED above "
            "the flat veneer surface, creating a subtle frame-like border. The molding raises the outside edge "
            "to approximately 15/16\" total thickness while the center panel is 3/4\" thick. "
            "The bead detail is a small rounded/semi-circular profile — subtle and refined, NOT a large "
            "decorative molding. It creates a very thin raised border around the flat slab. "
            "IMPORTANT: Do NOT interpret this as a traditional frame-and-panel door. There are NO cope-and-stick "
            "joints, NO separate rails and stiles, NO recessed or raised panel. It is a flat slab with a thin "
            "beaded molding applied to the perimeter. "
            "Use the reference image to match the exact design details: "
            "the flat slab construction, bead molding width and profile, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a VIENNA style SLAB VENEER door — NOT a frame-and-panel door. "
            "The entire face is ONE continuous flat veneered surface. There are NO rails, NO stiles, "
            "NO separate frame-and-panel construction. Do NOT add frame-and-panel details. "
            "A small BEAD MOLDING (3/8\" wide, rounded profile) is applied around the OUTSIDE perimeter, "
            "sitting slightly raised above the flat surface. This is the ONLY raised detail on the door. "
            "Preserve the exact flat slab construction, thin bead molding border, and overall simplicity. "
            "Do NOT convert this into a shaker, recessed panel, or raised panel door."
        ),
    },
    "terracina": {
        "name": "Terracina",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a TERRACINA style cabinet door — a RECESSED FLAT PANEL door with a distinctive "
            "OGEE/STEPPED inner edge profile. "
            "CRITICAL PANEL TYPE: The center panel is completely FLAT and RECESSED — it sits BELOW the "
            "frame surface. This is NOT a raised panel door. The panel does NOT have a raised bevel, "
            "convex surface, or any elevation above the frame. The panel is flat and inset. "
            "INNER EDGE PROFILE: The transition from the frame to the recessed panel features a decorative "
            "ogee or stepped profile — a curved/stepped molding detail cut into the inner edge of the frame. "
            "This creates visual depth and elegance but the panel itself remains completely flat and recessed. "
            "Do NOT confuse this decorative edge profile with a raised panel — the ogee is on the FRAME edge, "
            "not on the panel surface. "
            "JOINERY: The frame uses COPE-AND-STICK joints — stiles run full length top to bottom, "
            "rails butt into them at right angles. NOT mitered corners. "
            "FRAME: Wide stiles and rails with generous proportions. "
            "Use the reference image to match the exact design details: "
            "the ogee/stepped inner edge profile, flat recessed panel, cope-and-stick joints, "
            "frame width, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a TERRACINA style door — a RECESSED FLAT PANEL door with an OGEE/STEPPED "
            "inner edge profile on the frame. "
            "The center panel is FLAT and RECESSED — it sits BELOW the frame. Do NOT make a raised panel. "
            "The panel must NOT have a raised bevel, convex surface, or any elevation. It is completely flat. "
            "The decorative ogee/stepped profile is on the FRAME'S inner edge, NOT on the panel surface. "
            "Do NOT interpret the edge detail as a raised panel — the panel stays flat and inset. "
            "COPE-AND-STICK joints — stiles run full length, rails butt in at right angles, NOT mitered. "
            "Preserve the exact ogee/stepped edge profile, flat recessed panel, frame width, "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
    "shaker_flat_step": {
        "name": "Shaker Flat Step",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SHAKER FLAT STEP door — it has an inner trim/step detail between the frame and panel. "
            "CRITICAL INNER TRIM PROFILE: The inner trim has a FLAT VERTICAL STEP — a clean right-angle drop "
            "straight down from the frame surface to the panel. The step is a simple flat ledge, "
            "NOT angled, NOT beveled, NOT chamfered. There must be NO slope or diagonal surface on the "
            "inner profile. It must look like a tiny square shelf, not a ramp. Do NOT add shadow or depth "
            "that makes it look beveled — keep it flat and square. "
            "JOINT DETAIL: The outer frame uses COPE-AND-STICK joints (butt joints) — stiles run full "
            "length top to bottom, rails butt into them. But the INNER TRIM is MITERED at 45 degrees "
            "at the corners. So the outer frame has butt joints while the inner trim has mitered corners. "
            "The center panel is FLAT and RECESSED — it sits BELOW the frame, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the flat step profile, mitered inner trim, butt-joint frame, frame width, "
            "rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHAKER FLAT STEP door. "
            "The inner trim has a FLAT VERTICAL STEP — a simple right-angle drop, NOT beveled, "
            "NOT chamfered, NOT angled. No slope or diagonal surface. It must be a flat square ledge. "
            "Do NOT add shadow or depth that makes the step look beveled or ramped. "
            "The outer frame has COPE-AND-STICK BUTT JOINTS (stiles run full length, rails butt in). "
            "The INNER TRIM corners are MITERED at 45 degrees. "
            "The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "Preserve the exact flat step profile, mitered inner trim, butt-joint frame, "
            "frame width, and proportions from before."
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
            "CRITICAL FRAME MEMBER WIDTHS: ALL frame members (left stile, right stile, center stile, top rail, bottom rail) "
            "must be EXACTLY THE SAME WIDTH. Do NOT make the bottom rail wider than the stiles. Do NOT make any rail "
            "wider or narrower than the stiles. ALL frame members must have uniform, matching widths. "
            "Use the reference image to match the exact design details: "
            "the center stile width and position, panel depth, edge profile, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL STRUCTURAL REQUIREMENT: This door has a VERTICAL CENTER STILE dividing it into "
            "TWO side-by-side recessed panels. The center stile MUST be present — it is the defining feature "
            "of this door. Do NOT simplify to a single panel. Preserve the exact double-panel layout: "
            "outer frame (top rail, bottom rail, left stile, right stile) plus the vertical center stile "
            "creating two tall narrow recessed panels. "
            "CRITICAL FRAME MEMBER WIDTHS: ALL frame members (left stile, right stile, center stile, top rail, bottom rail) "
            "must be EXACTLY THE SAME WIDTH. Do NOT make the bottom rail wider than the stiles. Do NOT make any rail "
            "wider or narrower than the stiles. ALL frame members must have uniform, matching widths. "
            "Maintain uniform width across all stiles and rails from before."
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
    "mission": {
        "name": "Mission",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a MISSION style cathedral arch FLAT PANEL door. "
            "CRITICAL PANEL TYPE: The center panel is completely FLAT — it is NOT a raised panel. "
            "There is NO bevel, NO convex surface, NO raised center on the panel whatsoever. "
            "The panel is a single flat plane that sits FLUSH or slightly RECESSED within the frame. "
            "ARCH SHAPE: The top edge of the panel forms a cathedral curve shaped like a wide shallow 'M' "
            "or mustache. There is a modest rounded rise at center, but the DEFINING feature is the two "
            "DEEP CONCAVE SWOOPS on either side. These concave dips curve well below the center peak "
            "before sweeping back up to meet the top corners of the frame. "
            "The concave dips are the dominant visual — they should be deep and dramatic, dropping roughly "
            "20-25% of the panel height below the center peak. The center rise is gentle and secondary. "
            "This is NOT a simple arch, NOT a semicircle, NOT a pointed Gothic peak. "
            "The silhouette reads as: high corners → deep swoop down → moderate rise at center → "
            "deep swoop down → high corners. "
            "FRAME PROFILE: The frame's INNER EDGE has a decorative routed profile (ogee or similar) "
            "that creates shadow lines where the frame meets the panel. These shadow lines come from "
            "the FRAME molding profile, NOT from the panel being raised. Do NOT misinterpret these "
            "shadows as a raised panel bevel. "
            "FRAME PROPORTIONS: The bottom rail is noticeably wider than the stiles (approximately 1.5x). "
            "The stiles are uniform width. The top rail follows the arch contour. "
            "Use the reference image to match the exact arch curve, frame molding profile, "
            "rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a MISSION style cathedral arch FLAT PANEL door. "
            "The center panel is completely FLAT — it is NOT raised. There is NO bevel, NO convex "
            "surface, NO raised center. The panel is a single flat plane. "
            "The shadow lines at the frame-panel junction come from the FRAME's decorative inner "
            "edge profile, NOT from the panel being raised. Do NOT add any raised panel bevel. "
            "Preserve the exact cathedral arch — shaped like a wide 'M' with deep concave swoops "
            "on each side of a modest center rise. The dips are the dominant feature, NOT the peak. "
            "Preserve the flat panel, decorative frame profile, "
            "wide bottom rail, and rail/stile proportions from before."
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
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": ("Preserve the exact raised-panel cabinet door design from before."),
    },
    "raised_panel_radius": {
        "name": "Raised Panel Radius",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a raised-panel cabinet door with RADIUS INNER CORNERS. "
            "CRITICAL PROFILE DETAIL: The center panel is RAISED — it sits ABOVE the surrounding routed "
            "channel/groove. The frame (rails and stiles) surrounds a routed channel that steps DOWN from "
            "the frame, then the center panel RISES back up above the channel. "
            "INNER CORNER RADIUS: The four inner corners where the routed channel changes direction have "
            "a visible ROUNDED RADIUS — a smooth curved arc, NOT a sharp 90-degree turn. This radius is "
            "approximately 3/8 to 1/2 inch. The inner corners must be clearly rounded and soft. "
            "Do NOT make the inner profile corners sharp or square. "
            "Use the reference image to match the exact design details: "
            "the panel raise height, bevel profile, rail/stile proportions, inner corner radius, "
            "and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a RAISED PANEL door with RADIUS INNER CORNERS. "
            "The center panel is RAISED above the surrounding routed channel. "
            "The four inner corners where the routed channel turns must have a visible ROUNDED RADIUS "
            "— a smooth curved arc approximately 3/8 to 1/2 inch, NOT a sharp 90-degree corner. "
            "Preserve the exact raised panel height, bevel profile, frame proportions, "
            "and rounded inner corner radius from before."
        ),
    },
    "solid_plank": {
        "name": "Solid / Plank",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a SOLID SLAB cabinet door — "
            "this is a single flat piece of material with NO frame, NO panel, NO rails, NO stiles, "
            "NO raised or recessed sections, NO routed channels, NO profiles, NO inset details. "
            "It is simply a plain, flat rectangle. "
            "Use the reference image to match the exact proportions, edge profile, and wood grain direction. "
            "CRITICAL: Do NOT add any frame-and-panel construction. There are NO separate components — "
            "just one solid flat slab. If you see rails, stiles, or any panel detail, you have it WRONG. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SOLID SLAB door — a single flat rectangle with NO frame, "
            "NO panel, NO rails, NO stiles, NO routed profiles, NO raised or recessed areas. "
            "Do NOT add any frame-and-panel details. Keep it as a plain flat slab. "
            "Preserve the exact proportions and edge profile from before."
        ),
    },
    "louver": {
        "name": "Louver",
        "category": "door",
        "learn_prompt": (
            "Generate a photorealistic product image of a louvered cabinet door. "
            "Use the reference image to match the exact design details: "
            "the slat spacing, angle, frame proportions, and edge profile. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
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
            "Match the wood type, panel depth, edge profile, and rail/stile proportions exactly. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a RECESSED/INSET panel drawer front — the center panel must be FLAT and sit "
            "BELOW the surrounding frame. Do NOT make a raised panel. The panel must NOT have a raised bevel "
            "or convex surface. Wood grain runs HORIZONTALLY. Preserve the exact flat recessed panel design from before."
        ),
    },
    "drawer_raised_panel": {
        "name": "Raised Panel (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate a photorealistic product image of a raised-panel cabinet drawer front. "
            "Use the reference image to match the exact design details: "
            "the panel raise height, bevel profile, and rail/stile proportions. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": ("Preserve the exact raised-panel drawer front design from before. Wood grain runs HORIZONTALLY."),
    },
    "drawer_raised_panel_radius": {
        "name": "Raised Panel Radius (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate a photorealistic product image of a raised-panel cabinet drawer front with RADIUS INNER CORNERS. "
            "CRITICAL PROFILE DETAIL: The center panel is RAISED — it sits ABOVE the surrounding routed "
            "channel/groove. The frame surrounds a routed channel that steps DOWN from the frame, then "
            "the center panel RISES back up above the channel. "
            "INNER CORNER RADIUS: The four inner corners where the routed channel changes direction have "
            "a visible ROUNDED RADIUS — a smooth curved arc, NOT a sharp 90-degree turn. This radius is "
            "approximately 3/8 to 1/2 inch. The inner corners must be clearly rounded and soft. "
            "Do NOT make the inner profile corners sharp or square. "
            "Use the reference image to match the exact design details: "
            "the panel raise height, bevel profile, rail/stile proportions, and inner corner radius. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a RAISED PANEL drawer front with RADIUS INNER CORNERS. "
            "The center panel is RAISED above the surrounding routed channel. "
            "The four inner corners where the routed channel turns must have a visible ROUNDED RADIUS "
            "— a smooth curved arc approximately 3/8 to 1/2 inch, NOT a sharp 90-degree corner. "
            "Preserve the exact raised panel height, bevel profile, frame proportions, "
            "and rounded inner corner radius from before. Wood grain runs HORIZONTALLY."
        ),
    },
    "drawer_solid_plank": {
        "name": "Solid / Slab (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate a photorealistic product image of a SOLID SLAB cabinet drawer front — "
            "this is a single flat piece of material with NO frame, NO panel, NO rails, NO stiles, "
            "NO raised or recessed sections, NO routed channels, NO inset details. "
            "The face is a single flat surface. "
            "EDGE PROFILE: Study the reference image carefully and replicate the exact outer edge profile — "
            "this may be a simple square edge, a subtle bevel, an ogee, a cove, or another decorative profile. "
            "The edge detail is a defining characteristic of this drawer front and must be preserved exactly. "
            "Use the reference image to match the exact proportions and edge profile. "
            "CRITICAL: Do NOT add any frame-and-panel construction. There are NO separate components — "
            "just one solid flat slab with its specific edge treatment. "
            "If you see rails, stiles, or any panel detail on the face, you have it WRONG. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a SOLID SLAB drawer front — a single flat face with NO frame, "
            "NO panel, NO rails, NO stiles, NO routed profiles, NO raised or recessed areas on the face. "
            "Do NOT add any frame-and-panel details. "
            "Preserve the exact flat face, outer edge profile (bevel, ogee, square, or other detail), "
            "and proportions from before. "
            "Wood grain runs HORIZONTALLY."
        ),
    },
    "drawer_alpine": {
        "name": "Alpine (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is an ALPINE style drawer front with a FLAT RECTANGULAR TRIM STRIP framing a recessed panel. "
            "CRITICAL INNER TRIM PROFILE: The inner trim is a FLAT, RECTANGULAR cross-section strip of wood — "
            "like a thin, flat picture-frame molding. The trim surface is completely FLAT and LEVEL — it has "
            "NO bevel, NO angle, NO chamfer, NO slope, NO rounded edge. The cross-section of the trim is a "
            "simple RECTANGLE — flat on top, square edges on both sides, like a small flat board laid on its side. "
            "If you imagine cutting through the trim, you would see a plain rectangle, NOT a triangle, NOT a "
            "trapezoid, NOT a parallelogram. The top face of the trim is PARALLEL to the door face. "
            "Do NOT make the trim look beveled, angled, sloped, or chamfered in ANY way. "
            "TRIM CORNERS: The trim strips meet at 45-DEGREE MITER JOINTS at all four corners — "
            "the trim forms a picture-frame pattern with clean diagonal miter cuts where each strip meets. "
            "CONSTRUCTION: The outer frame uses standard rail-and-stile construction. The flat rectangular "
            "trim strip is applied INSIDE the frame, sitting slightly RAISED above the recessed panel surface "
            "but BELOW the outer frame surface. The trim creates a distinct border between the frame and panel. "
            "The center panel is FLAT and RECESSED — it sits BELOW the trim, NOT raised. "
            "Use the reference image to match the exact design details: "
            "the flat rectangular trim profile, mitered corners, trim width and height, "
            "frame proportions, and panel depth. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is an ALPINE style drawer front. The defining feature is the FLAT RECTANGULAR "
            "TRIM STRIP framing the recessed panel. "
            "The trim has a FLAT, RECTANGULAR cross-section — the top surface is completely FLAT and LEVEL, "
            "PARALLEL to the door face. There is NO bevel, NO angle, NO chamfer, NO slope on the trim. "
            "If you cut through the trim, the cross-section is a plain RECTANGLE — NOT a triangle, "
            "NOT a trapezoid. Do NOT make the trim look beveled, angled, or sloped in any way. "
            "The trim corners are MITERED at 45 degrees — a clean picture-frame pattern. "
            "The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact flat rectangular trim profile, mitered corners, trim dimensions, "
            "frame proportions, and panel depth from before."
        ),
    },
    "drawer_shaker": {
        "name": "Shaker (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a SHAKER style drawer front — it has a FLAT, RECESSED center panel "
            "with clean square-edge framing. "
            "The center panel is FLAT and sits BELOW the frame — it is NOT raised and has NO bevel. "
            "The frame has SQUARE, CLEAN inner edges — NO decorative routing, NO ogee, NO chamfer. "
            "The inner edge where frame meets panel is a simple sharp 90-degree step down. "
            "Use the reference image to match the exact design details: "
            "the panel depth, edge profile, and rail/stile proportions. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a SHAKER style drawer front — the center panel must be FLAT and RECESSED "
            "below the frame. Do NOT make a raised panel. The panel must NOT have a raised bevel or "
            "convex surface. The frame inner edges are SQUARE and CLEAN — no decorative routing. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact Shaker flat recessed panel design and square-edge framing from before."
        ),
    },
    "drawer_harmony": {
        "name": "Harmony (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "Match every detail precisely — do NOT simplify the construction. "
            "CRITICAL OUTER EDGE: The outer frame edge is RAISED and ROUNDED — it curves UP, "
            "not down. Do NOT make it a flat step-down or a square edge. The outer edge has a "
            "smooth convex profile that rises above the surrounding surface. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "Preserve the exact drawer front construction from before. "
            "CRITICAL: The outer frame edge is RAISED and ROUNDED — it curves UP, not down. "
            "Do NOT flatten it into a step-down or square edge. "
            "Wood grain runs HORIZONTALLY. Change ONLY the wood material."
        ),
    },
    "drawer_journey": {
        "name": "Journey (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a JOURNEY style drawer front — a SHALLOW, SKINNY SHAKER drawer front with MITERED CORNERS. "
            "CRITICAL FRAME WIDTH: The rails and stiles are VERY NARROW — approximately 1 INCH wide. "
            "This is roughly HALF the width of a standard shaker frame. The narrow frame makes the flat "
            "center panel appear proportionally much larger than a normal shaker. Do NOT widen the frame — "
            "if the frame looks like a standard shaker width, it is WRONG. The frame must look noticeably "
            "skinny and slim. The 1-inch face detail is the defining proportion of this style. "
            "MITERED CORNERS: The frame corners are joined at 45-DEGREE MITER JOINTS — the grain runs "
            "at 45 degrees at each corner where rails meet stiles. Do NOT use cope-and-stick or square "
            "butt joints. Every corner must show a clean diagonal miter seam. "
            "INNER EDGE PROFILE: The inner edge where frame meets panel is a simple, clean SQUARE profile — "
            "a sharp 90-degree step down from the frame to the recessed panel. There is NO decorative "
            "routing, NO ogee, NO chamfer, NO applied molding. Just a clean square shaker edge. "
            "CENTER PANEL: The center panel is completely FLAT and RECESSED — it sits BELOW the frame "
            "surface. It is NOT raised, has NO bevel, NO convex surface. "
            "SHALLOW PROPORTIONS: This is a drawer front, NOT a door — it has a shallow/short height "
            "relative to its width, creating a wide landscape orientation typical of drawer fronts. "
            "Use the reference image to match the exact design details: "
            "the very narrow ~1-inch frame width, mitered corner joints, square inner edge, "
            "flat recessed panel, shallow drawer proportions, and wood grain direction. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The drawer front must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire drawer front must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "CRITICAL: This is a JOURNEY style drawer front — a SKINNY SHAKER with MITERED CORNERS. "
            "The frame (rails and stiles) must be VERY NARROW — approximately 1 INCH wide, roughly HALF "
            "the width of a standard shaker. Do NOT widen the frame to standard shaker proportions — "
            "the skinny 1-inch frame is the defining feature. If the frame looks like a normal shaker "
            "width, it is WRONG. "
            "The frame corners are 45-degree MITER JOINTS — NOT cope-and-stick, NOT butt joints. "
            "Every corner must show a clean diagonal miter seam where the grain meets at 45 degrees. "
            "Simple SQUARE inner edge — a clean 90-degree step down, NO routed profile, NO applied molding. "
            "The center panel is FLAT and RECESSED — do NOT make a raised panel. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact skinny ~1-inch frame width, miter geometry, square inner edge, "
            "flat recessed panel, and shallow drawer proportions from before."
        ),
    },
}


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
