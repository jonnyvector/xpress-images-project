"""Best-seller coverage endpoint."""

from fastapi import APIRouter, Request

from backend.coverage import compute_coverage
from backend.models import CoverageResponse
from backend.routers.projects_common import get_store

router = APIRouter()


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    store = get_store(request)
    # Pydantic v2 coerces the list[dict] from compute_coverage into the models.
    return CoverageResponse(categories=compute_coverage(store.list_projects()))
