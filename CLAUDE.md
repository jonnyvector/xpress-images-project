# Cabinet Door Generator

## Project Overview
FastAPI + React app that generates cabinet door image variations across different wood types using Google Gemini 3's image generation with "thought signatures" for style consistency.

## Architecture

### Backend (FastAPI)
- `backend/app.py` - FastAPI entry point with CORS, static files, router mounts
- `backend/generator.py` - Core `DoorGenerator` class wrapping Gemini 3 Pro Image API
- `backend/routers/projects*.py` - Project endpoints, split by area (crud, generation, media, versions)
- `backend/routers/coverage.py` - Coverage + live Shopify sync (`backend/shopify_live.py`, via Shopify CLI: products, variant images, 12-month sales)
- `backend/routers/catalog.py` + `backend/catalog.py` - Products command center: every active door/drawer front, per-variant image cells (live / generated here / missing) and sales
- `backend/routers/qa.py` - QA review queue & approvals
- `backend/qa/` - QA judgment pipeline (judge, geometry, policy, approvals)
- `backend/routers/swatches.py` - Wood swatch listing endpoints
- `backend/models.py` - Pydantic models
- `backend/state.py` - `ProjectStore` for persistent project state
- `backend/worker.py` - Background generation worker

### Frontend (React + Vite + TypeScript)
- `frontend/src/App.tsx` - Routes (react-router): `/library`, `/review`, `/products`, `/products/:handle`, `/coverage`, `/doors/:id?step=style|replica|variants`
- `frontend/src/api.ts` - API client functions
- `frontend/src/types.ts` - TypeScript type definitions
- `frontend/src/context/ProjectsContext.tsx` - Projects state context
- `frontend/src/components/` - UI components:
  - `AppShell.tsx` - Left nav (views, recent doors, settings) + routed page
  - `DoorPage.tsx` - `/doors/:id` loader; renders `ProjectTab`
  - `ProjectTab.tsx` - Door workspace: Style / Replica / Variants steps
  - `Segmented.tsx` - Shared filter buttons
  - `ProductsPage.tsx` / `ProductPage.tsx` - Command center list (by sales) and per-variant image grid
  - `ImageViewer.tsx` - Full-screen zoom viewer
  - `CoveragePage.tsx` / `CoverageTable.tsx` - Coverage by category
  - `ReviewQueue.tsx` - Pending verdicts
  - `UploadStep.tsx` - Door image upload
  - `SwatchGrid.tsx` - Wood type swatch selection
  - `GenerateStep.tsx` - Generation trigger & progress
  - `ResultsGrid.tsx` - Generated image results
  - `DoorLibrary.tsx` - Door library browser
  - `SignatureHistory.tsx` - Thought signature history

### Shared
- `swatches/` - Wood swatch reference images + `wood_types.json`
- `output/` - Generated images & project data (gitignored)

## QA Judgment Pipeline
Generated images are auto-graded (pass / regenerate / needs_human) by a three-layer
pipeline: replica approvals, LLM vision judge, deterministic geometry checks.
Operator guide: `docs/qa-pipeline.md`.
Automatic judging is OFF (`auto_judge: false` in `backend/qa/trust_config.json`): new images
go straight to the Review queue for the operator; no Gemini judge spend, no auto-regeneration.
Candidate judge models are compared offline with `scripts/judgeeval.sh` (OpenRouter, company key)
against a frozen answer key of the operator's verdicts.

## Key Concept: Thought Signatures
Gemini returns a binary "thought signature" when generating images. This signature encodes the model's understanding of the door style and can be passed back in subsequent requests to maintain geometric consistency while changing materials.

## Commands
```bash
npm run dev              # Run both backend & frontend concurrently
npm run dev:backend      # FastAPI on :8000 (uv run uvicorn)
npm run dev:frontend     # Vite dev server on :5173
npm run build            # Build frontend for production
npm run lint             # Ruff lint backend
npm run format           # Ruff format backend
uv run python scripts/qa_label.py    # labeling UI on :8777 (calibration ground truth)
uv run python scripts/qa_eval.py     # judge labeled images + score vs labels (train split)
uv run python scripts/qa_report.py   # build output/.qa/review.html of flagged images
scripts/judgeeval.sh build|opus|sonnet|gemini|report   # compare judge models on the answer key
```

## Environment
- Requires `GEMINI_API_KEY` env var (in `.env`)
- Python 3.12+ with uv for backend dependencies
- Node.js for frontend (React 19, Vite 6, TypeScript 5.7)
- `concurrently` for running both servers in dev

## Cost
~$0.134 per image generated (Gemini 3 Pro Image, 1K-2K resolution)
