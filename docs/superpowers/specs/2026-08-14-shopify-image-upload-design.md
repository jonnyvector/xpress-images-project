# Shopify Image Upload — Design

**Date:** 2026-08-14
**Status:** Approved (brainstorming) → ready for implementation plan

## Goal

Push operator-approved generated door/drawer images from local disk directly
onto their matching Shopify product variants, without a CSV/URL detour.
Shopify's CSV import (native or Matrixify) requires `Image Src`/`Variant
Image` to resolve to a public URL — it cannot read a local file path, since
the import runs on Shopify's servers. The Admin API's media mutations accept
uploaded bytes directly (via a staged upload), so this goes straight from
disk to a specific variant in one script run.

## Decisions (from brainstorming)

- **Source of truth for "approved":** the operator's own curation. If an
  image has been written via "Save Watermarked/Plain to Folder", it's
  approved — no new approval-status check on the folder's contents. (Today
  Save-to-Folder writes every result regardless of QA/approval status; the
  operator is relied on to have already reviewed before saving. No code
  change to Save-to-Folder in this iteration.)
- **Product targeting:** explicit, operator-picked, durable — a new
  `shopify_product_id` field on the same per-title sign-off record that
  already carries `canonical_project_id` (`docs/sales/data/
  coverage_signoff.json`, owned by `backend/signoff.py`). No fuzzy title
  matching on this write path — that's for the read-only "On Shopify" badge
  only, never for deciding where an image gets pushed live.
- **Variant targeting:** normalized (case/whitespace-insensitive) match of
  the wood name (extracted from the image filename via the existing
  `extract_wood_name()` helper) against the product's variant `Option1`
  values, with a mandatory preview step before any write. Unmatched files
  are flagged, never guessed or silently skipped.
- **Interface:** a CLI script (`scripts/upload_to_shopify.py`), matching the
  existing `scripts/onboard_*.py` / `scripts/qa_*.py` pattern. Not a UI
  panel — this is a live-store write path, deliberately kept out of the
  React app's normal click-through flow.
- **Auth:** a custom Shopify app (operator creates once, manually, in
  Shopify Admin → Settings → Apps and sales channels → Develop apps) with
  `write_products`/`read_products` scopes. Token + store domain read from
  `.env` (`SHOPIFY_ADMIN_API_TOKEN`, `SHOPIFY_STORE_DOMAIN`).

## Architecture

```
docs/sales/data/coverage_signoff.json     (+shopify_product_id per title)
                    │
                    ▼
scripts/upload_to_shopify.py  ──reads──►  local folder (operator-approved images)
        │                                          │
        │                                   extract_wood_name() per file
        │                                          │
        ▼                                          ▼
  Shopify Admin GraphQL:                    normalized name match
  variants(product) ─────────────────────►  preview: file → variant | UNMATCHED
                                                     │
                                          --confirm ▼
                                   stagedUploadsCreate → upload bytes
                                        → productCreateMedia
                                        → productVariantAppendMedia
```

### `backend/signoff.py` additions

- `set_shopify_product(record, title, product_id) -> dict[str, dict]` — same
  shape/pattern as `set_canonical`: stores `entry["shopify_product_id"] =
  product_id`, returns a new record, does not mutate the input.
- No gate semantics (not a boolean like `variations`/`shopify` sign-off
  gates) — just a durable pointer, read directly by the script via
  `load_signoff()` / written via `save_signoff()` under `SIGNOFF_LOCK`
  exactly like the existing writers in `backend/routers/coverage.py`.
- No new HTTP endpoint — the script is a standalone process, not a request
  handler, and imports `backend.signoff` directly.

### `scripts/upload_to_shopify.py`

```
uv run python scripts/upload_to_shopify.py \
  --title "AR756 Thermofoil Cabinet Door" \
  --folder "~/Desktop/Xpress/Images/AI Images/RTF Doors/AR756.../Watermarked" \
  [--product gid://shopify/Product/123 | a-product-handle] \
  [--confirm]
```

1. **Resolve product ID.** If `--product` is passed, use it, and persist it
   to the sign-off record for `--title` (via `set_shopify_product`) so
   future runs for the same title don't need it again. Otherwise read
   `shopify_product_id` from the existing sign-off entry for `--title`; if
   absent, exit with an error telling the operator to supply `--product`
   once.
2. **Fetch variants.** GraphQL query for the product's variants: `id` and
   `selectedOptions` (to read the `Option1`-equivalent value — the wood/color
   name). Requires `SHOPIFY_STORE_DOMAIN` + `SHOPIFY_ADMIN_API_TOKEN` from
   `.env`.
3. **List local files.** Every image file (`IMAGE_EXTENSIONS`, same set
   `projects_media.py` already uses) directly under `--folder` (non-recursive
   — mirrors the existing folder-import endpoint's behavior).
4. **Extract wood name per file** via `backend.filename_parsing
   .extract_wood_name(path.stem, wood_types)` — the same helper
   `import_results_from_folder` already uses, so this can't disagree with
   how the app already parses its own saved filenames. `wood_types` loaded
   via `load_material_types(material_type)`, where `material_type` comes
   from the title's category in `backend.coverage.CATEGORIES` (wood vs rtf).
5. **Match.** Normalize both sides (`.strip().casefold()`) and compare wood
   name to each variant's option value. Build a preview list: `(filename,
   wood_name, matched_variant_id | None)`.
6. **Always print the preview**, grouped as Matched / Unmatched. Without
   `--confirm`, stop here — pure dry run, zero API writes beyond the
   read-only variant fetch (and the sign-off persist in step 1, which is
   local-file-only, not a Shopify write).
7. **With `--confirm`**, for each matched file only:
   a. `stagedUploadsCreate` (filename, mimeType, resource: `IMAGE`,
      httpMethod: `POST`) → get the staged target URL + params.
   b. `POST` the file bytes to that URL with the returned params.
   c. `productCreateMedia(productId, media: [{originalSource:
      <resourceUrl>, mediaContentType: IMAGE, alt: wood_name}])` → get the
      new `MediaImage` id back (poll/check `status` if needed — Shopify
      processes media asynchronously; short-poll with a small retry loop
      since this is a low-volume interactive script, not a bulk job).
   d. `productVariantAppendMedia(productId, variantMedia: [{variantId,
      mediaIds: [<new media id>]}])`.
   Print per-file success/failure. A failure on one file doesn't stop the
   rest — collect and report errors at the end.

## Error handling

- Missing `SHOPIFY_ADMIN_API_TOKEN`/`SHOPIFY_STORE_DOMAIN` → exit before any
  work, clear message pointing at `.env`.
- `--title` not in the sign-off record and no `shopify_product_id`, and no
  `--product` supplied → exit with a clear message, no partial state
  written.
- `--folder` doesn't exist or has no image files → exit, same pattern as
  `import_results_from_folder`'s existing validation.
- A filename `extract_wood_name` can't parse → included in the Unmatched
  list with a reason, never guessed.
- Any GraphQL `userErrors`/`mediaUserErrors` on a given file → reported per
  file, script continues with the remaining matched files.
- Media stuck in a non-`READY`/`UPLOADED` status after the short poll
  window → reported as a failure for that file, not silently treated as
  success.

## Testing

- **`tests/test_signoff.py`** (extend, or new if none exists): `
  set_shopify_product` stores the id, doesn't clobber other fields on the
  entry, round-trips through `save_signoff`/`load_signoff`.
- **`tests/test_upload_to_shopify.py`** (new): the matching function
  (normalize + compare wood name to variant options) is a pure function —
  unit test matched, unmatched, and case/whitespace-drift cases directly,
  no network. The three-mutation Shopify call sequence is exercised with a
  mocked HTTP layer (matches how other network-touching code in this repo
  is tested) covering: happy path, a `mediaUserErrors` response, and a
  stuck-processing media status.
- **Manual**: one real dry run (`--confirm` omitted) against a real product
  to confirm the preview reads correctly before ever running with
  `--confirm` for the first time.

## Out of scope (this iteration)

- Bulk/all-products run — one `--title` per invocation only.
- UI panel — CLI only.
- Idempotency / dedup against images already on the variant — re-running
  `--confirm` will add a duplicate image each time; the operator is
  responsible for not double-running.
- Replacing or deleting existing variant images.
- Fixing Save-to-Folder to filter to approved-only (operator's own curation
  is the trust boundary here, per brainstorming decision).

## Deliverables

1. `backend/signoff.py`: `set_shopify_product()`.
2. `scripts/upload_to_shopify.py` (new): full flow above.
3. `tests/test_signoff.py` (extend) + `tests/test_upload_to_shopify.py`
   (new).
4. One documented dry run against a real Shopify product before first live
   `--confirm` use.
