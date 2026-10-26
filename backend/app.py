"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.routers import catalog, coverage, projects, qa, swatches
from backend.state import ProjectStore

PROJECTS_DIR = Path("output/.projects")


@asynccontextmanager
async def lifespan(app: FastAPI):
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    app.state.project_store = ProjectStore(persist_dir=PROJECTS_DIR)
    yield


app = FastAPI(title="Cabinet Door Generator API", lifespan=lifespan)

# CORS for Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(swatches.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(coverage.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")

# Static file mounts
Path("swatches").mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files/swatches", StaticFiles(directory="swatches"), name="swatches")


class SPAStaticFiles(StaticFiles):
    """Serve index.html for app links (/doors/abc) so a refresh loads the app.

    Only extension-less, non-API paths fall back; a missing asset still 404s.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            is_api = path == "api" or path.startswith("api/")
            is_page = "." not in path.rsplit("/", 1)[-1] and not is_api
            if exc.status_code == 404 and is_page:
                return await super().get_response("index.html", scope)
            raise


# Serve frontend build in production (if it exists)
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
