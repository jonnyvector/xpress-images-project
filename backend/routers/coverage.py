"""Best-seller coverage endpoints: read model, operator sign-off, Shopify upload."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, UploadFile

from backend.coverage import CATEGORIES, DATA_DIR, compute_coverage, load_products
from backend.models import (
    CanonicalRequest,
    CoverageResponse,
    ExclusionsRequest,
    SignoffRequest,
)
from backend.palette import compute_gap, distinct_generated
from backend.routers.projects_common import get_store
from backend.shopify_products import SHOPIFY_CSV_FILENAME, has_recognizable_headers
from backend.signoff import load_signoff, save_signoff, set_canonical, set_exclusions, set_gate

router = APIRouter()


def _known_titles() -> dict[str, str]:
    """Map every sales-CSV product title to its material, for validation."""
    titles: dict[str, str] = {}
    for cat in CATEGORIES:
        for title, _, _ in load_products(DATA_DIR / cat["csv"]):
            titles[title] = cat["material"]
    return titles


def _require_title(title: str) -> str:
    known = _known_titles()
    if title not in known:
        raise HTTPException(status_code=404, detail=f"Unknown product title: {title}")
    return known[title]


def _response(request: Request) -> CoverageResponse:
    store = get_store(request)
    # Pydantic v2 coerces the list[dict] from compute_coverage into the models.
    return CoverageResponse(categories=compute_coverage(store.list_projects(), DATA_DIR))


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    return _response(request)


@router.put("/coverage/{title}/canonical", response_model=CoverageResponse)
def put_canonical(title: str, body: CanonicalRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    store = get_store(request)
    if store.get(body.project_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown project: {body.project_id}")
    save_signoff(DATA_DIR, set_canonical(load_signoff(DATA_DIR), title, body.project_id))
    return _response(request)


@router.put("/coverage/{title}/exclusions", response_model=CoverageResponse)
def put_exclusions(title: str, body: ExclusionsRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    save_signoff(DATA_DIR, set_exclusions(load_signoff(DATA_DIR), title, body.colors))
    return _response(request)


@router.post("/coverage/{title}/signoff", response_model=CoverageResponse)
def post_signoff(title: str, body: SignoffRequest, request: Request) -> CoverageResponse:
    material = _require_title(title)
    store = get_store(request)
    record = load_signoff(DATA_DIR)
    entry = record.get(title) or {}
    canonical = store.get(entry.get("canonical_project_id") or "")

    result_count = len(distinct_generated(canonical)) if canonical else 0

    # The operator may always override, but never by accident, and the override
    # is recorded on the stamp.
    if body.gate == "variations" and body.value and not body.acknowledge_gap:
        gap = compute_gap(material, list(entry.get("excluded_colors") or []), canonical)
        if gap["missing"]:
            preview = ", ".join(gap["missing"][:5])
            more = "" if len(gap["missing"]) <= 5 else f" (+{len(gap['missing']) - 5} more)"
            raise HTTPException(
                status_code=409,
                detail=f"{len(gap['missing'])} colours still missing: {preview}{more}. "
                "Re-send with acknowledge_gap to sign off anyway.",
            )

    record = set_gate(
        record, title, body.gate, body.value,
        by=body.by,
        at=datetime.now(UTC).isoformat(),
        result_count=result_count,
        acknowledged_gap=body.acknowledge_gap,
    )
    save_signoff(DATA_DIR, record)
    return _response(request)


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
