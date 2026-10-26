"""Command center endpoints: every active door/drawer front, per-variant cells."""

from fastapi import APIRouter, HTTPException, Request

from backend.catalog import build_catalog
from backend.coverage import DATA_DIR, load_shopify_source
from backend.models import CatalogProduct, CatalogResponse
from backend.qa.approvals import get_approval_store
from backend.routers.projects_common import get_store
from backend.shopify_live import ADMIN_PRODUCTS_URL, load_snapshot

router = APIRouter()

_NEEDS_REFRESH = "No per-variant Shopify data yet. Use Refresh from Shopify on the Coverage page."


def _catalog(request: Request, **build) -> CatalogResponse:
    snapshot = load_snapshot(DATA_DIR)
    error = load_shopify_source(DATA_DIR)[1].get("error")
    if snapshot is None or any("variants" not in p for p in snapshot["products"]):
        error = error or _NEEDS_REFRESH
    if error:
        return CatalogResponse(products=[], error=error, shopify_admin_url=ADMIN_PRODUCTS_URL)
    products = build_catalog(
        get_store(request).list_projects(), snapshot, get_approval_store(), DATA_DIR, **build
    )
    sales = snapshot.get("sales")
    return CatalogResponse(
        products=products,
        synced_at=snapshot.get("fetched_at"),
        sales_days=sales.get("days") if sales else None,
        sales_error=snapshot.get("sales_error"),
        shopify_admin_url=ADMIN_PRODUCTS_URL,
    )


@router.get("/catalog", response_model=CatalogResponse)
def get_catalog(request: Request) -> CatalogResponse:
    """All products without their variant cells (the list page)."""
    return _catalog(request, include_variants=False)


@router.get("/catalog/{handle}", response_model=CatalogProduct)
def get_catalog_product(handle: str, request: Request) -> CatalogProduct:
    response = _catalog(request, handle=handle)
    if response.error:
        raise HTTPException(status_code=409, detail=response.error)
    product = response.products[0] if response.products else None
    if product is None:
        raise HTTPException(status_code=404, detail=f"No active door or drawer front: {handle}")
    return product
