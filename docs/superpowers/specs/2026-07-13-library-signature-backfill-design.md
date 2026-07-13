# Library Signature Backfill — Design

**Date:** 2026-07-13
**Status:** Approved by operator (approach A)

## Problem

The 24 `*_new_wm` library projects (e.g. `Frontier_new_wm`, id `950e8411`) hold the
finished watermark-cleaned variant sets but were created by copying variant images
only. They have no `signature.bin` (thought signature), no `base_door.bin` (approved
replica), and no `upload.bin`, and their manifests lack `door_style` /
`base_image_id`. Result: the UI cannot generate additional variations from any
library project. The originals still exist in each door's lowercase working project
(e.g. `frontier`, id `a9f04868`).

## Goal

Every `*_new_wm` project becomes fully generation-capable in the existing UI:
replica visible, signature attached, "generate variations" passes the graduated-
trust gates and appends new results alongside the curated variants. No backend or
frontend code changes — a data backfill via a reusable script,
`scripts/backfill_library_signatures.py`.

## Non-goals

- No UI "import signature from another project" feature (YAGNI).
- No merging of library variants back into source projects.
- No re-learning in library projects — re-learn wipes results (`worker.py:342`).

## Key mechanics this relies on (verified)

- `has_signature` is derived at load from `signature.bin` presence
  (`state.py:167-170`); `base_image_id` and `qa_verdicts` persist in the manifest.
- Variation generation appends to existing results (`worker.py:625`) and requires
  `learned_signature`, `door_style`, `corner_style`, `material_type`.
- GT-001 (replica approved) checks the **global** approval store by `base_image_id`
  (`projects_common.py:33-38`). Copying the source's `base_image_id` verbatim
  carries the existing approval — same image bytes, same identity, no re-approval.

## 1. Matching (source → library)

Map each library project to its source by case-insensitive name stem
(`Frontier_new_wm` → `frontier`), requiring the source to have both
`signature.bin` and `base_door.bin`.

- 18 doors match one source exactly; Hamilton matches via the looser
  `Hamilton Cabinet Door` form. Total unambiguous: 19.
- 5 ambiguous doors — Durango, Graham, Highpointe, Mission, Shaker — each have
  multiple signature-bearing candidates. Resolution: visually compare each
  library's variants against each candidate's replica, pick the match, and produce
  a side-by-side HTML confirmation report. The operator confirms those five before
  they are written.
- The final mapping ships in the script as an explicit, reviewable table
  (library id → source id), not re-derived at run time.

## 2. What gets copied per project

Files (source → library dir):
- `signature.bin`
- `base_door.bin`
- `upload.bin` (if present)

Manifest fields (from source manifest):
- `base_image_id` (verbatim — carries global replica approval)
- `door_style`, `corner_style`, `material_type`, `style_notes`
- `profile_spec`, `profile_image_path`, `variant_hint_mode`
- `upload_filename`
- the replica's entry from the source's `qa_verdicts` (keyed by `base_image_id`)

Never touched:
- `result_*.bin`, `result_records` / `result_names`
- variant QA verdicts already in the library project
- project `name`, `id`, `selected_swatches` (operator selects at generation time)
- source projects are strictly read-only throughout

## 3. Safety

- Single-writer rule: abort if the dev server is listening on port 8000.
- `--dry-run` is the default and prints the full plan; `--apply` writes.
- Before writing, snapshot each library project's `manifest.json` and record which
  files are being added, under `output/.onboard/backfill_backup/<library_id>/`.
  Rollback = delete the three copied files and restore the manifest snapshot (the
  backfill only adds files and fills empty fields).
- Idempotent: skip any library project that already has `signature.bin`.

## 4. Verification

- Script post-check (`--apply`): re-load every touched project through
  `ProjectStore`; assert `has_signature` is true, replica bytes present, and the
  result count is unchanged from before the write.
- Acceptance: start the server, open `Frontier_new_wm` in the UI, confirm the
  replica displays, select one swatch, generate one variation (~$0.134), and
  confirm it appends alongside the 31 existing variants.

## Inventory (as of 2026-07-13)

24 library projects, all missing signature/replica/upload. Unambiguous source
matches include: Adobe→`adobe` (2564359f), Alpine→`alpine` (c9ff205d),
Arcadia→`arcadia` (a2c466f8), Artesia→`artesia` (b48dfef2), Campbell→`campbell`
(9f98e1fa), Cascade→`cascade` (35113f5a), Connecticut→`connecticut` (02afd676),
Cougar→`Cougar` (1de2743f), Eldridge→`Eldridge` (9e726e6c), Estrella→`estrella`
(ec593b7e), Frontier→`frontier` (a9f04868), Hamilton→`Hamilton Cabinet Door`
(a3453f05), Hayes→`hayes` (b558a816), Indiana→`indiana` (5357bc46),
Isabella→`isabella` (6d2bb325), Jasper→`jasper` (7ef841e3), Josephine→`Josephine`
(ca7c7f92), Kennedy→`Kennedy` (dcf543e4), Laguna→`Laguna` (5875fc02).
Pending visual confirmation: Durango, Graham, Highpointe, Mission, Shaker.
