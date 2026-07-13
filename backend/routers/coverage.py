"""Best-seller coverage endpoint, plus the Shopify product-image upload."""

import csv
import io

from fastapi import APIRouter, HTTPException, Request, UploadFile

from backend.coverage import DATA_DIR, compute_coverage
from backend.models import CoverageResponse
from backend.routers.projects_common import get_store
from backend.shopify_products import SHOPIFY_CSV_FILENAME, has_recognizable_headers

router = APIRouter()


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    store = get_store(request)
    # Pydantic v2 coerces the list[dict] from compute_coverage into the models.
    return CoverageResponse(
        categories=compute_coverage(store.list_projects(), data_dir=DATA_DIR)
    )


@router.post("/coverage/shopify-csv", response_model=CoverageResponse)
async def upload_shopify_csv(file: UploadFile, request: Request) -> CoverageResponse:
    """Persist an operator-exported Shopify product CSV and refresh coverage."""
    store = get_store(request)
    data = await file.read()
    if not data.strip():
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    text = data.decode("utf-8-sig", errors="replace")
    header = next(csv.reader(io.StringIO(text)), None)
    if header is None or not has_recognizable_headers(header):
        raise HTTPException(
            status_code=400,
            detail=(
                "CSV must include Handle, Title, and a Variant Image or "
                "Image Src column"
            ),
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / SHOPIFY_CSV_FILENAME).write_bytes(data)
    return CoverageResponse(
        categories=compute_coverage(store.list_projects(), data_dir=DATA_DIR)
    )
