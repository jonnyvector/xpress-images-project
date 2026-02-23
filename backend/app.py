"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routers import projects, swatches
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

# Static file mounts
Path("swatches").mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/files/swatches", StaticFiles(directory="swatches"), name="swatches")

# Serve frontend build in production (if it exists)
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
