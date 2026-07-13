# Style-Prompt Audit — prior-cueing profile-character vocabulary

Generated 2026-07-08 (lean-conditioning plan, D-004). Sweep of all 39
`learn_prompt`s in `backend/styles/catalog.py` for words that describe 3D
relief character (bevel, sloped, chamfer, ogee, cove, pillowy, raised,
gradual…). Doctrine: words describing relief CUE the prior they name —
even as negations (verified white-RTF 2026-07-03; El Dorado 2026-07-08,
16 failed attempts under a prompt saying "bevel profile").

**Policy (D-004): audit broadly, edit surgically.** Only prompts
implicated in actual door failures are edited. Everything else stays —
most negation-style prose below is operator-calibrated fixes with wins
on record.

## Category 1 — AFFIRMATIVE prior-cueing (the dangerous kind)

The prompt tells the model to render the named relief as part of "match
the design":

| Style | Phrase | Status |
|---|---|---|
| `raised_panel` | "match … the panel raise height, ~~bevel profile~~, rail/stile proportions" | **EDITED 2026-07-08** → "raise profile" (El Dorado failure class) |
| `raised_panel_radius` | same "bevel profile" phrase | flagged, NOT edited (no failures attributed yet) |
| `drawer_raised_panel` | same "bevel profile" phrase | flagged, NOT edited |
| `drawer_raised_panel_radius` | same "bevel profile" phrase | flagged, NOT edited |

Also affirmative but INTENDED (the door class genuinely is a bevel):
`rtf_drawer_bevel` ("THE DEFINING FEATURE — THE BEVEL…") — correct as is.

## Category 2 — Negation prose (defensive, double-edged)

"NO bevel / NOT raised / NO ogee" phrasing. These are deliberate past
fixes that demonstrably work for their classes; they remain risk-flagged
because negated relief vocabulary can still cue the prior. Edit ONLY if
the class starts failing on the negated feature.

`mission`, `shaker`, `shaker_flat_step`, `shaker_cope_stick`,
`recessed_panel`, `recessed_panel_arched`, `recessed_panel_applied_molding`,
`mitered_flat_panel`, `mitered_recessed_panel_applied_molding`, `graham`,
`terracina` (mixed: affirmative OGEE is the door's real feature),
`hayes` (affirmative COVE/OGEE is real), `vienna`, `solid_plank`,
`drawer_alpine`, `drawer_journey`, `drawer_recessed_panel`,
`drawer_shaker`, `drawer_solid_plank`, `drawer_harmony`,
`rtf_drawer_shaker`, `rtf_drawer_shaker_skinny`, `shaker_bevel`
(chamfer negation).

## Category 3 — Benign

"raised-panel cabinet door/drawer front" as the style NAME in the
opening sentence (`raised_panel*`, `drawer_raised_panel*`) — names the
category, not the transition character. No action.

## Escalation path

A door failing on profile character under any Category-1/2 prompt:
first check this table for the style's vocabulary; consider the lean
tail (which bypasses the style prompt entirely) before editing the
prompt — the ladder now does this automatically from attempt 2.
