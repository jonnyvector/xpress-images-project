# Cabinet Door Generator

## Project Overview
FastAPI + React app that generates cabinet door image variations across different wood types using Google Gemini 3's image generation with "thought signatures" for style consistency.

## Architecture

### Backend (FastAPI)
- `backend/app.py` - FastAPI entry point with CORS, static files, router mounts
- `backend/generator.py` - Core `DoorGenerator` class wrapping Gemini 3 Pro Image API
- `backend/routers/projects.py` - Project CRUD & generation endpoints
- `backend/routers/swatches.py` - Wood swatch listing endpoints
- `backend/models.py` - Pydantic models
- `backend/state.py` - `ProjectStore` for persistent project state
- `backend/worker.py` - Background generation worker

### Frontend (React + Vite + TypeScript)
- `frontend/src/App.tsx` - Root app component
- `frontend/src/api.ts` - API client functions
- `frontend/src/types.ts` - TypeScript type definitions
- `frontend/src/context/ProjectsContext.tsx` - Projects state context
- `frontend/src/components/` - UI components:
  - `Layout.tsx` - App layout shell
  - `TabBar.tsx` - Project tab navigation
  - `ProjectTab.tsx` - Individual project view
  - `UploadStep.tsx` - Door image upload
  - `SwatchGrid.tsx` - Wood type swatch selection
  - `GenerateStep.tsx` - Generation trigger & progress
  - `ResultsGrid.tsx` - Generated image results
  - `DoorLibrary.tsx` - Door library browser
  - `SignatureHistory.tsx` - Thought signature history

### Shared
- `swatches/` - Wood swatch reference images + `wood_types.json`
- `output/` - Generated images & project data (gitignored)

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
```

## Environment
- Requires `GEMINI_API_KEY` env var (in `.env`)
- Python 3.12+ with uv for backend dependencies
- Node.js for frontend (React 19, Vite 6, TypeScript 5.7)
- `concurrently` for running both servers in dev

## Cost
~$0.134 per image generated (Gemini 3 Pro Image, 1K-2K resolution)
