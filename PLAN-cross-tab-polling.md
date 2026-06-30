# Fix: Cross-tab generation interference — COMPLETED

When two doors are generating simultaneously, one finishing killed the other's polling/generation state.

## Steps

1. ✅ Memoize `ProjectTab` with `React.memo`
2. ✅ Make polling resilient in `GenerateStep` — uses `useRef` for poll callback so `setInterval` always calls latest version without recreating interval
3. ✅ Replace `listProjects()` with `getProject()` in poll completion — avoids broad re-renders
4. ✅ Add `React.memo` to `UploadStep`

## Additional fixes
- Added `POST /api/projects/{id}/generate/reset` endpoint to unstick projects
- Added `GET /api/projects/{id}` single-project endpoint
- Wrapped `_run_generation` in try/finally so `generation_status` always gets set to `done`
