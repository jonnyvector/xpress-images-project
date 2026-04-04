# Cabinet Door Generator

FastAPI + React application for generating cabinet door and drawer-front material variations using Gemini image generation with thought signatures.

## Stack

- **Backend:** FastAPI (`backend/`)
- **Frontend:** React + Vite + TypeScript (`frontend/`)
- **Model:** Gemini image generation (API key via `X-API-Key`)

## Run locally

```bash
npm run dev            # backend + frontend
npm run dev:backend    # FastAPI on :8000
npm run dev:frontend   # Vite on :5173
```

## Quality checks

```bash
npm run build
npm run lint
npm --prefix frontend run lint
uv run pytest -q
```

## Repo structure

- `backend/app.py` – FastAPI entrypoint
- `backend/routers/` – API endpoints (projects/swatches)
- `backend/worker.py` – background generation/retry/learn workers
- `backend/state.py` – persistent project store
- `backend/materials.py` – shared swatch/material helpers
- `backend/generator.py` – Gemini generation service
- `backend/styles/catalog.py` – style catalog
- `frontend/src/components/` – UI components
- `frontend/src/context/ProjectsContext.tsx` – project state
- `frontend/src/hooks/usePollingTask.ts` – shared polling hook

## Notes

- Generated artifacts are stored under `output/.projects/`.
- Swatches live in `swatches/wood` and `swatches/rtf`.
- Environment variables should go in `.env` (ignored by git).
