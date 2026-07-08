"""Per-door profile spec: verifiable geometric facts extracted from the source photo.

One extraction per door. The facts guide the learn prompt from attempt 1 AND power
judge_replica_identity's fact-by-fact verification. Facts must be individually
checkable; grain, color and lighting are never facts.
"""

import json
import re
import time

from google.genai import types

DEFAULT_MODEL = "gemini-3.1-pro-preview"

# The fixed door-anatomy checklist. Extraction emits one fact per region;
# the identity judge sweeps the same regions. Order matters for prompts.
REGIONS = (
    "outside_edge",   # door's outer edge profile (square, eased, roundover, bevel)
    "stiles_rails",   # frame member widths, equal or not, grain direction
    "joints_corners", # miter (45° lines) vs cope-and-stick vs butt
    "inside_edge",    # frame-to-panel transition (step, bevel, ogee, routed sticking)
    "panel",          # flat/raised/beadboard/plank/louver; raise profile / recess depth
    "trim_molding",   # applied molding present or absent; profile if present
    "top_rail_arch",  # square, cathedral, radius
)

EXTRACT_PROMPT = f"""You are a cabinet-door profile analyst. The image is a SAMPLE
photo of a real cabinet door. Extract its geometry as a short list of individually
VERIFIABLE facts, one per region, prefixed with the region name:

{chr(10).join(f"- {r}" for r in REGIONS)}

Rules:
- No region may be skipped. An unremarkable region gets an explicit plain/none fact
  (e.g. "trim_molding: none").
- EDGES FIRST. The outside_edge fact MUST name the precise profile: square, eased,
  chamfered, or BULLNOSE (fully rounded). The stiles_rails fact MUST state whether the
  door has left/right side stiles at all — some doors have only top/bottom rails and
  their planks/panels RUN OFF the left and right door edges, with the outermost
  elements cut by the edge. Say which construction this door is.
- Facts must be checkable by looking: structural counts, pitch/spacing ratios, widths
  (relative to a repeating element unless an absolute width is visually obvious),
  edge/bevel shapes, panel type and recess depth, joint type, arch geometry.
- Structural counts are absolute (panels, stiles, rails, center stile).
- The replica will be rendered at 9:16, likely taller than this sample. For repeating
  elements (louver slats, beadboard grooves, plank boards) state pitch/spacing/profile
  relative to the elements themselves, never an absolute count.
- State ONLY what is visually certain. Construction details that are hard to read at
  photo scale — joint type (miter vs cope-and-stick), a hairline edge roundover — go in
  a fact ONLY when unmistakable (e.g. clearly visible 45-degree corner lines); when in
  doubt, describe the region without that detail.
- Describe PROFILE GEOMETRY with its CHARACTER, not just its type: a raise is sharp/
  steep or gradual/shallow; molding is fat or fine, standing proud with a deep reveal
  or flat; grooves are deep chamfered V's or faint lines; reeds/flutes are half-round
  (state if their ends are rounded); state raise border width relative to the panel and
  arch curve shape (how far it drops, radius vs cathedral) — character carries the
  door's identity.
- Never mention wood species, color, grain figure, lighting, or photo quality.
- 7 to 12 facts total, each one line.

Reply with ONLY a JSON object, no markdown fences:
{{"facts": ["region: fact", ...]}}"""

# Appended ONLY when the catalog cross-section drawing is attached (profile anchor).
XSECTION_EXTRACT_BLOCK = (
    "A second image is attached: a line-drawing CROSS-SECTION of this same door's "
    "edge, frame, and panel profile viewed edge-on. It shows the true geometry a "
    "front-facing photo cannot — use it to state profile character precisely "
    "(raise shape: sharp vertical step vs gradual bevel; frame thickness; inside "
    "and outside edge profiles)."
)

_MAX_FACTS = 12


def parse_facts(text: str) -> list[str]:
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(),
                     flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    facts = data.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("facts must be a non-empty list")
    if len(facts) > _MAX_FACTS:
        raise ValueError(f"too many facts: {len(facts)}")
    out = [str(f).strip() for f in facts]
    if any(not f for f in out):
        raise ValueError("empty fact")
    return out


def profile_facts_note(facts: list[str]) -> str:
    """One-line learn-prompt block (minimal prose; the facts ARE the guidance)."""
    if not facts:
        return ""
    return "Match these geometric facts of the sample EXACTLY: " + " | ".join(
        facts)


def _mime(data: bytes) -> str:
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def extract_profile_spec(client, source_bytes: bytes, *,
                         model: str = DEFAULT_MODEL,
                         profile_bytes: bytes | None = None) -> list[str]:
    prompt = (EXTRACT_PROMPT if profile_bytes is None
              else EXTRACT_PROMPT + "\n\n" + XSECTION_EXTRACT_BLOCK)
    parts = [types.Part.from_bytes(data=source_bytes, mime_type=_mime(source_bytes))]
    if profile_bytes is not None:
        parts.append(types.Part.from_bytes(data=profile_bytes,
                                           mime_type=_mime(profile_bytes)))
    parts.append(types.Part.from_text(text=prompt))
    contents = [types.Content(role="user", parts=parts)]
    last = ""
    for attempt in range(3):
        try:
            resp = client.models.generate_content(model=model, contents=contents)
            return parse_facts(resp.text or "")
        except Exception as exc:  # noqa: BLE001 - retry then re-raise
            last = str(exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"profile spec extraction failed: {last}")
