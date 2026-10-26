"""Command center endpoints: every active door/drawer front, per-variant cells."""

from fastapi import APIRouter, HTTPException, Request

from backend.catalog import build_catalog, door_listings, listing_colors, match_swatches
from backend.coverage import DATA_DIR, load_shopify_source
from backend.models import CatalogProduct, CatalogResponse, DoorShopifyColors
from backend.qa.approvals import get_approval_store
from backend.routers.projects_common import get_project_or_404, get_store
from backend.routers.swatches import list_swatches
from backend.shopify_live import ADMIN_PRODUCTS_URL, load_snapshot

router = APIRouter()

_NEEDS_REFRESH = "No per-variant Shopify data yet. Use Refresh from Shopify on the Coverage page."


def _needs_refresh(snapshot: dict | None) -> bool:
    """Snapshots from before per-variant sync have products without "variants"."""
    return snapshot is None or any("variants" not in p for p in snapshot["products"])


def _catalog(request: Request, **build) -> CatalogResponse:
    snapshot = load_snapshot(DATA_DIR)
    error = load_shopify_source(DATA_DIR)[1].get("error")
    if _needs_refresh(snapshot):
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


@router.get("/projects/{project_id}/shopify-colors", response_model=DoorShopifyColors)
def get_door_shopify_colors(project_id: str, request: Request) -> DoorShopifyColors:
    """Which swatches this door's Shopify listing actually sells (for the picker)."""
    store = get_store(request)
    project = get_project_or_404(store, project_id)
    snapshot = load_snapshot(DATA_DIR)
    if _needs_refresh(snapshot):
        raise HTTPException(status_code=409, detail=_NEEDS_REFRESH)
    listings = door_listings(
        store.list_projects(), snapshot, get_approval_store(), DATA_DIR, project_id
    )
    colors = listing_colors(listings)
    swatches = list_swatches(project.material_type or "wood")
    keys, unmatched = match_swatches(colors, [(s.key, s.name) for s in swatches])
    return DoorShopifyColors(
        listings=[{"handle": p["handle"], "title": p["title"]} for p in listings],
        colors=colors,
        swatch_keys=keys,
        unmatched=unmatched,
    )
