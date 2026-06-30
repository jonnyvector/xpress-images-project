"""Best-seller coverage endpoint."""

from fastapi import APIRouter, Request

from backend.coverage import compute_coverage
from backend.models import CoverageCategory, CoverageResponse
from backend.routers.projects_common import get_store

router = APIRouter()


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    store = get_store(request)
    categories = compute_coverage(store.list_projects())
    return CoverageResponse(
        categories=[CoverageCategory(**c) for c in categories]
    )
