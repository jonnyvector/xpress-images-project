# VA Generation App — Design

**Date:** 2026-08-18
**Status:** Approved design, pre-implementation
**Working name:** `door-factory` (final name TBD by Jonathan at repo creation)

## Purpose

A fresh, minimal web app deployed on Railway that lets a hired VA generate
cabinet door swatch variations and judge them manually. It replaces the AI
judgment pipeline with human review. Jonathan (admin) seeds doors; the VA
generates, reviews, and exports passing images as zips that they drop into
Google Drive.

This is a **new repository** with **fresh data** — it does not share code,
projects, or signatures with `xpress-images-project`. The existing app remains
Jonathan's local lab, unchanged.

## Decisions (settled during brainstorming)

| Decision | Choice |
| --- | --- |
| Relationship to existing app | New repo; port proven modules (approach B). No shared package (YAGNI). |
| Data | Fresh. No migration of existing library projects or signatures. |
| Door seeding | Admin only. Jonathan uploads doors, approves replicas, assigns swatches. |
| Swatch scope | Per-door swatch list curated by admin at seeding (deliberate departure, for this app only, from the "always full palette" rule used in the lab app). |
| QA pipeline | Absent entirely. No judge, no geometry checks, no QA lane. Human review only. |
| Export | VA downloads a zip per door and manually uploads to Google Drive. No Drive API. |
| Hosting | Railway: one service, one volume at `/data`, GitHub push-to-deploy. |
| Auth | Password login, two users (admin / va) via env vars. Signed session cookie. |
| Spend control | Daily image-count cap (env var). Cap hit → generation blocked with a friendly message. |
| Support model | VA reports problems to Jonathan; he fixes and pushes; Railway redeploys. |

## Architecture

Stack: FastAPI backend, React + Vite + TypeScript frontend, uv + npm.
One Railway service; backend serves the built frontend and the API.

```
door-factory/
├── backend/
│   ├── app.py          # FastAPI entry, serves API + built frontend
│   ├── auth.py         # login, sessions, roles: admin / va
│   ├── generator.py    # PORTED: DoorGenerator, prompt ladder, signatures, retry
│   ├── store.py        # flat JSON-per-door store, single process, atomic writes
│   ├── worker.py       # small generation queue + spend counter
│   └── routers/        # doors, generate, review, export, auth
├── frontend/src/       # Login, DoorList, DoorDetail (generate + review), AdminSeed
├── swatches/           # copied swatch images + wood_types.json
├── Dockerfile          # build frontend → uvicorn
└── /data (Railway volume)  # doors/, generated images, spend ledger
```

### Ported from xpress-images-project (the jewels)

- `generator.py` — DoorGenerator, prompt ladder, thought-signature handling,
  retry logic. Ported mostly intact with its relevant tests.
- Filename/swatch conventions and `wood_types.json`.
- Image resize/upload handling, including the recent resize fix.

Everything else is written fresh and small. No QA imports anywhere.
Fork-drift risk is accepted and confined to `generator.py`.

## Data model

One folder per door under `/data/doors/<slug>/`:

```
/data/doors/shaker-5pc/
├── door.json           # state file
├── source.png          # admin-uploaded door / drawer front
├── replica.png         # approved replica from learn step
├── signature.bin       # thought signature — irreplaceable
└── variants/
    └── <swatch-slug>/
        ├── attempt-1.png
        └── attempt-2.png
```

`door.json`:

```json
{
  "name": "Shaker 5pc",
  "type": "door | drawer_front",
  "style_notes": "narrow frame, flat panel",
  "swatches": ["walnut-natural", "maple-select"],
  "status": "seeding | ready | in_progress | complete | exported",
  "variants": {
    "walnut-natural": { "chosen": "attempt-2.png", "state": "pending | passed | failed" }
  }
}
```

Rules:

- Whole-file JSON writes, atomic (write tmp file, rename). One process, one
  writer. No locking machinery.
- All attempts kept on disk; only the `chosen` passing image per swatch goes
  into the export zip.
- Spend ledger at `/data/spend.json`: per-date counts; cap read from env.
- The Railway volume is the only live copy of signatures. Mitigation: each
  export zip also contains `signature.bin` + `door.json`, so every Drive drop
  doubles as a per-door backup.

## VA flow

Login → **Door list**: cards with source thumbnail, progress ("7/12 swatches
passed"), status badge. Doors in `seeding` are hidden from the VA.

**Door detail** (the whole VA job on one screen):

- Source door image large on the left — the judging reference.
- Grid of tiles, one per assigned swatch: swatch chip + latest attempt.
- Tile actions: **Generate** / **Regenerate**, **Pass**, **Fail**.
  - Regenerate keeps prior attempts in a strip; VA picks the best attempt as
    `chosen`, not necessarily the latest.
  - Fail = mark failed + regenerate in one click.
- **Generate all remaining** — batches every non-passed swatch through the
  worker queue (sequential or 2-wide; decided at build).
- **Zoom / lightbox**: click any variation → full-screen lightbox with
  scroll/pinch zoom and pan at native resolution; arrow keys flip between
  attempts and swatches; one keypress toggles to the source door for
  comparison. No watermarks in this app.
- Header progress counter. At all-passed the door flips `complete` and
  **Export zip** activates: downloads `<Door-Name>.zip` containing chosen
  images named `<door>-<swatch>.png` plus the signature backup. Door marked
  `exported`; VA drags the zip into the shared Drive folder.

Guardrails:

- Spend cap hit → generate buttons disabled: "Daily limit reached — message
  Jonathan."
- No delete action exists anywhere in the VA view.
- Hover-zoom + side-by-side comparison to support edge-first judging.

## Admin flow

Admin sees everything the VA sees, plus:

- **New Door**: upload source image → name, type, optional style notes (fed
  into the learn prompt) → **Learn** runs signature acquisition and shows the
  replica beside the source → approve or re-roll → **Assign swatches** via a
  checkbox grid of the full swatch library → door flips `ready`.
- Edit swatch list on an existing door.
- Re-open an `exported` door.
- Spend dashboard: today's count, cap, history.
- Raw `door.json` download per door for debugging.

All seeding happens through the web UI — no SSH, no scripts.

## Deploy & ops

- Dockerfile: build frontend, copy into image, run uvicorn.
- Railway: connect GitHub repo, attach volume at `/data`, set env vars:
  `GEMINI_API_KEY`, `ADMIN_PASSWORD`, `VA_PASSWORD`, `DAILY_IMAGE_CAP`,
  `SESSION_SECRET`. Push = deploy. Railway-provided HTTPS URL; custom domain
  optional later.
- Expected cost ≈ $10–15/mo (service + volume) plus Gemini usage
  (~$0.134/image).

## Error handling

- Gemini failures: ported retry logic. Terminal failure → tile shows
  "Generation failed — try again"; never a stack trace. Full errors go to
  server logs (read via Railway dashboard).
- Deploy mid-generation: in-flight jobs die; affected swatches simply show as
  non-passed on next load and the VA regenerates. Queue is in-memory by
  design — no job-persistence machinery.
- Sessions: signed cookie, 7-day expiry. Failed logins crudely rate-limited
  (sleep on failure).

## Testing

- Ported generator keeps its relevant tests (retry, prompt ladder), minus
  QA-coupled ones.
- New tests: store atomic-write behavior, spend-cap boundary, auth/role
  gating (VA cannot reach admin routes), export zip contents.
- Real-API smoke test is manual: seed one door, generate one swatch,
  before the VA ever logs in.

## Out of scope (v1)

- Google Drive API integration (manual zip upload instead).
- Any AI judging (judge, geometry, QA lane, calibration tooling).
- Multi-VA accounts, per-user audit trails.
- Data migration from the existing app.
- Shared core package between the two apps (revisit if generator bugs get
  fixed twice).
