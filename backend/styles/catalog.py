"""Door and drawer style catalog."""

from typing import Any

STYLES: dict[str, dict[str, Any]] = {
    "davenport": {
        "name": "Davenport",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of this door. "
            "This door has TWO defining features you must get exactly right: "
            "1) The center panel is RECESSED and consists of exactly THREE vertical tongue-and-groove planks with V-groove lines between them — NOT a single flat panel, NOT four planks. The planks sit BELOW the frame surface. "
            "2) BEADS run along ALL FOUR SIDES of the recessed panel where it meets the frame — TWO parallel beads sit close to the frame on every side. "
            "All stiles and rails must be the same width."
        ),
        "variation_hint": (
            "Preserve the exact door structure. Change only the wood material. "
            "CRITICAL: The center panel is RECESSED — exactly THREE vertical tongue-and-groove/beadboard planks with V-groove lines sitting BELOW the frame surface — NOT a single flat panel, NOT four planks. "
            "BEADS run along ALL FOUR SIDES of the panel, with TWO parallel beads close to the frame on every side. "
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
    "rtf_drawer_shaker_skinny": {
        "name": "Skinny Shaker RTF (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "STUDY THE REFERENCE IMAGE CAREFULLY before generating — every dimension must come from the image, not from standard cabinetry conventions. "
            "This is a SKINNY SHAKER style RTF drawer front — it has a FLAT, RECESSED center panel with clean square-edge framing. "
            "CRITICAL PROPORTIONS: The vertical stiles (left and right) and horizontal rails (top and bottom) are EXACTLY 7/8 INCH wide (0.875 inches). "
            "This is less than HALF the width of a standard shaker door frame. "
            "Do NOT widen the frame to standard 2-inch proportions — the 7/8 inch frame width is the defining feature of this style. "
            "If the frame looks like a normal shaker width, it is WRONG. "
            "The center panel is FLAT and RECESSED below the frame — it is NOT raised and has NO bevel. "
            "The frame has SQUARE, CLEAN inner edges — NO decorative routing, NO ogee, NO chamfer. "
            "The inner edge where frame meets panel is a simple sharp 90-degree step down. "
            "The very narrow 7/8 inch frame leaves a LARGE open panel area — the center panel occupies most of the visual width. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a SKINNY SHAKER style drawer front — the defining feature is the EXTREMELY NARROW 7/8 INCH frame. "
            "The stiles and rails must be exactly 7/8 inch (0.875 inches) wide — less than half the width of a standard shaker. "
            "Do NOT widen the frame to normal shaker proportions — the 7/8 inch width is what makes this style unique. "
            "The center panel must be FLAT and RECESSED below the frame. Do NOT make a raised panel. "
            "The frame inner edges are SQUARE and CLEAN — no decorative routing. "
            "The narrow 7/8 inch frame creates a LARGE open panel area that dominates the visual. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact 7/8 inch stile/rail width, panel depth, and square-edge framing from before."
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
            "the surrounding frame. Do NOT make a raised panel door. The panel must NOT have a raised bevel, "
            "convex surface, or any outward curvature whatsoever — it is completely FLAT and RECESSED. "
            "Even though the frame may have ornate or decorative molding profiles, the CENTER PANEL is "
            "still FLAT and RECESSED — do NOT assume an ornate frame means a raised panel. "
            "The panel surface must be a flat plane sitting in a recess below the frame surface. "
            "Preserve the exact flat recessed panel design, frame molding profile, "
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
    "shaker_bevel": {
        "name": "Shaker Bevel",
        "category": "door",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is essentially a standard Shaker door. The frame, panel, and proportions are "
            "all standard Shaker construction. The center panel is FLAT and RECESSED below the frame. "
            "The ONLY difference from a plain Shaker is that the inner edge of the frame where it "
            "meets the panel is very slightly eased — the tiniest hint of an angle instead of a "
            "perfectly sharp 90-degree corner. This is just a router pass on the frame edge, "
            "NOT a separate trim piece, NOT an applied molding, NOT a visible chamfer. "
            "There is NO separate inner trim or border of any kind. The frame is ONE piece of wood. "
            "At a glance this should look like a normal Shaker door. "
            "Use the reference image to match the exact design details: "
            "the panel depth, frame width, rail/stile proportions, and wood grain direction. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). Absolutely no shadows, no gradients, no grey tones — the background must be perfectly uniform bright white. Professional lighting. "
            "CRITICAL: The door must NOT touch or bleed to the edges of the image. "
            "Leave at least 5% whitespace margin on ALL four sides (top, bottom, left, right). "
            "The entire door must be fully visible and centered with clear white space surrounding it."
        ),
        "variation_hint": (
            "This is essentially a standard Shaker door. The center panel is FLAT and RECESSED. "
            "The inner frame edge has the tiniest eased bevel — barely visible, just a softened corner. "
            "There is NO separate trim piece, NO applied molding, NO visible inner border. "
            "The frame is ONE solid piece of wood. At a glance this should look like a normal Shaker. "
            "Preserve the exact frame proportions and flat recessed panel from before."
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
            "The wood grain must be continuous across the face — NO visible stave joints, "
            "NO glue lines, NO seams between separate boards. "
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
            "The wood grain must be continuous — NO visible stave joints, NO glue lines, NO seams. "
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
    "drawer_durango": {
        "name": "Durango (Drawer)",
        "category": "drawer",
        "use_base_door_reference": True,
        "learn_prompt": (
            "Generate an exact replica of this drawer front."
        ),
        "variation_hint": (
            "Preserve the exact drawer front structure. Change only the wood material."
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
            "CRITICAL PROPORTIONS: Measure the stile and rail widths in the reference image and "
            "replicate them EXACTLY. The vertical stiles (left and right) are typically WIDER than "
            "the horizontal rails (top and bottom) — do NOT make them equal width. "
            "Study the reference image carefully for the exact stile-to-rail ratio and match it precisely. "
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
            "CRITICAL PROPORTIONS: The stiles (left and right) are WIDER than the rails (top and bottom) — "
            "do NOT make them equal width. Preserve the exact stile-to-rail ratio from before. "
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
    "drawer_minimal": {
        "name": "Minimal (Drawer Test)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of this drawer front."
        ),
        "variation_hint": (
            "Preserve the exact drawer front structure. Change only the wood material."
        ),
    },
    "drawer_durango_minimal": {
        "name": "Durango Minimal (Drawer)",
        "category": "drawer",
        "use_base_door_reference": True,
        "learn_prompt": (
            "Replicate this drawer front exactly. Pay strict attention to the structural "
            "proportions: notice that the vertical side stiles are significantly wider than "
            "the top and bottom horizontal rails. Explicitly break down these exact geometric "
            "proportions in your internal reasoning before generating the image."
        ),
        "variation_hint": (
            "Maintain the exact structural dimensions from the previous turn: the vertical "
            "stiles must remain visibly wider than the horizontal top and bottom rails. "
            "Do not make the borders symmetrical."
        ),
    },
    "drawer_routed": {
        "name": "Routed (Drawer)",
        "category": "drawer",
        "learn_prompt": (
            "Generate an exact replica of the reference image. "
            "This is a ROUTED drawer front — a SINGLE SOLID PIECE of wood with a routed channel "
            "cut into the face to create a frame-and-panel appearance. "
            "This is NOT 5-piece construction. There are NO separate rails, stiles, or panel — "
            "it is ONE continuous piece of wood with a CNC-routed groove. "
            "Use the reference image to match the exact routed profile, channel depth and width, "
            "and proportions. "
            "GRAIN DIRECTION: The wood grain must run HORIZONTALLY (left to right) across the "
            "drawer front. Do NOT use vertical grain. "
            "Create a brand new render - do NOT return the reference image. "
            "Output: clean studio product photo on a STARK PURE WHITE background (#FFFFFF). "
            "Absolutely no shadows, no gradients, no grey tones — the background must be "
            "perfectly uniform bright white. Professional lighting."
        ),
        "variation_hint": (
            "CRITICAL: This is a ROUTED drawer front — a SINGLE SOLID PIECE of wood, NOT 5-piece "
            "construction. The routed channel is cut into one continuous piece. "
            "Do NOT convert to separate rails and stiles. "
            "Wood grain runs HORIZONTALLY. "
            "Preserve the exact routed profile, channel depth, and proportions from before."
        ),
    },
}
