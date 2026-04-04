"""Projects API router (aggregated sub-routers)."""

from fastapi import APIRouter

from backend.routers import (
    projects_crud,
    projects_generation,
    projects_media,
    projects_versions,
)

router = APIRouter()
router.include_router(projects_crud.router)
router.include_router(projects_media.router)
router.include_router(projects_versions.router)
router.include_router(projects_generation.router)
