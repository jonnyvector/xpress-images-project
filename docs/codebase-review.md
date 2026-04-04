# Codebase Review (Risk-ranked)

## Critical

1. Large generator module (`backend/generator.py`) historically mixed style catalog and service logic.
   - Mitigation implemented: style catalog extracted to `backend/styles/catalog.py`.

## High

1. Duplicated swatch/material logic across router and worker.
   - Mitigation implemented: shared helpers in `backend/materials.py` and both modules now use it.
2. Monolithic projects router.
   - Mitigation implemented: router split into `projects_crud.py`, `projects_media.py`, `projects_versions.py`, `projects_generation.py` with shared `projects_common.py`.
3. Duplicated polling logic in frontend.
   - Mitigation implemented: shared `usePollingTask` hook used by Upload and Generate flows.

## Medium

1. Reducer side-effects in `ProjectsContext`.
   - Mitigation implemented: localStorage writes moved to `useEffect`; reducer now pure.
2. Thin test coverage.
   - Mitigation implemented: added tests for materials helpers and project store basics.

## Low

1. Missing/empty top-level docs.
   - Mitigation implemented: `README.md` now documents architecture, commands, and checks.
