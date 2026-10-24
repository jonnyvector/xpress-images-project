"""Best-seller coverage endpoints: read model, operator sign-off, Shopify sync."""

import threading
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

from backend.coverage import (
    CATEGORIES,
    DATA_DIR,
    compute_coverage,
    extract_match_tokens,
    listings_fully_imaged,
    load_products,
    load_shopify_source,
    match_shopify_listings,
)
from backend.models import (
    CanonicalRequest,
    CoverageResponse,
    ExclusionsRequest,
    SignoffRequest,
)
from backend.palette import compute_gap, distinct_generated
from backend.routers.projects_common import get_store
from backend.shopify_live import (
    ADMIN_PRODUCTS_URL,
    ShopifyCliError,
    drop_archived,
    fetch_products,
    save_snapshot,
)
from backend.signoff import (
    GATE_KEYS,
    SIGNOFF_FILENAME,
    SIGNOFF_LOCK,
    SignoffRecordError,
    load_signoff_strict,
    save_signoff,
    set_canonical,
    set_exclusions,
    set_gate,
)

router = APIRouter()
# One Shopify refresh at a time: an older, slower read must not overwrite a newer one.
_REFRESH_LOCK = threading.Lock()


def _load_for_write() -> dict[str, dict]:
    """Load the record on a write path, or refuse to write at all.

    Writers save the whole record back, so a corrupt file must stop the write
    rather than be quietly replaced by a one-entry file. Readers keep the
    lenient load_signoff — a broken file degrades the page, not the record.
    """
    try:
        return load_signoff_strict(DATA_DIR)
    except SignoffRecordError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Refusing to write: {exc}. Fix or restore "
                f"{DATA_DIR / SIGNOFF_FILENAME} (it is git-tracked) and try again. "
                "Nothing was written."
            ),
        ) from exc


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
    shopify = load_shopify_source(DATA_DIR)
    meta = shopify[1]
    # Pydantic v2 coerces the list[dict] from compute_coverage into the models.
    return CoverageResponse(
        categories=compute_coverage(store.list_projects(), DATA_DIR, shopify=shopify),
        shopify_source=meta["source"],
        shopify_synced_at=meta["synced_at"],
        shopify_admin_url=ADMIN_PRODUCTS_URL,
        shopify_error=meta.get("error"),
    )


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage(request: Request) -> CoverageResponse:
    return _response(request)


@router.put("/coverage/{title}/canonical", response_model=CoverageResponse)
def put_canonical(title: str, body: CanonicalRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    store = get_store(request)
    if store.get(body.project_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown project: {body.project_id}")
    with SIGNOFF_LOCK:
        record = _load_for_write()
        save_signoff(DATA_DIR, set_canonical(record, title, body.project_id))
    return _response(request)


@router.put("/coverage/{title}/exclusions", response_model=CoverageResponse)
def put_exclusions(title: str, body: ExclusionsRequest, request: Request) -> CoverageResponse:
    _require_title(title)
    with SIGNOFF_LOCK:
        record = _load_for_write()
        save_signoff(DATA_DIR, set_exclusions(record, title, body.colors))
    return _response(request)


@router.post("/coverage/{title}/signoff", response_model=CoverageResponse)
def post_signoff(title: str, body: SignoffRequest, request: Request) -> CoverageResponse:
    material = _require_title(title)
    store = get_store(request)
    with SIGNOFF_LOCK:
        record = _load_for_write()
        entry = record.get(title) or {}
        canonical = store.get(entry.get("canonical_project_id") or "")

        # No canonical project means no evidence, not zero colours. Stamping 0
        # would make is_stale() fire the moment a canonical project is picked;
        # None records "not measured" and is_stale ignores it.
        result_count = len(distinct_generated(canonical)) if canonical else None

        # Likewise there is no gap to guard against or acknowledge — comparing
        # the palette to nothing would report the whole palette as missing and
        # record an acknowledgement the operator never actually made.
        acknowledged_gap = bool(body.acknowledge_gap) and canonical is not None

        # The operator may always override a real gap, but never by accident,
        # and the override is recorded on the stamp.
        if (
            canonical is not None
            and body.gate == "variations"
            and body.value
            and not body.acknowledge_gap
        ):
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
            record,
            title,
            body.gate,
            body.value,
            by=body.by,
            at=datetime.now(UTC).isoformat(),
            result_count=result_count,
            acknowledged_gap=acknowledged_gap,
        )
        save_signoff(DATA_DIR, record)
    return _response(request)


@router.post("/coverage/shopify-refresh", response_model=CoverageResponse)
def refresh_from_shopify(request: Request) -> CoverageResponse:
    """Read every product's variant images live from Shopify (read-only).

    Sync handler on purpose: FastAPI runs it in a worker thread, so the ~15s of
    CLI calls don't block the event loop.
    """
    if not _REFRESH_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A Shopify refresh is already running.")
    try:
        return _refresh(request)
    finally:
        _REFRESH_LOCK.release()


def _refresh(request: Request) -> CoverageResponse:
    try:
        products = fetch_products()
    except ShopifyCliError as exc:
        if exc.needs_auth:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Shopify login needed ({exc}). Run scripts/shopauth.sh "
                    "in a terminal, then refresh again."
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"Shopify CLI failed: {exc}") from exc
    if not products:
        # Never replace good data with an empty store read (wrong store, scope, outage).
        raise HTTPException(
            status_code=502, detail="Shopify returned no products; kept the previous data."
        )
    products = drop_archived(products)
    # Stamp first: if the sign-off file can't be written, the refresh fails as a
    # whole instead of half-applying (new snapshot, no stamps).
    _stamp_shopify_signoffs(products, by="shopify-live")
    save_snapshot(DATA_DIR, products)
    return _response(request)


def _stamp_shopify_signoffs(products: list[dict], by: str) -> None:
    """Record an in_shopify sign-off for every fully-imaged Shopify product.

    A sync is a bulk way for the operator to record a decision they would
    otherwise tick by hand, so it only ever ADDS stamps. It never revokes a
    sign-off and never overwrites one already on the record: a human's judgment
    (or an earlier sync's) outranks a later one. That also means a product
    dropping off the store does not silently un-ship it.

    Only the shopify gate is touched. variations_complete stays a human call —
    nothing here can infer whether every needed colour was generated.
    """
    if not any(p["fully_imaged"] for p in products):
        return

    now = datetime.now(UTC).isoformat()
    with SIGNOFF_LOCK:
        try:
            record = load_signoff_strict(DATA_DIR)
        except SignoffRecordError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        for cat in CATEGORIES:
            for title, _, _ in load_products(DATA_DIR / cat["csv"]):
                if GATE_KEYS["shopify"] in (record.get(title) or {}):
                    continue  # already signed off — never overwrite provenance
                tokens = extract_match_tokens(title)
                if listings_fully_imaged(match_shopify_listings(cat, tokens, products)):
                    record = set_gate(record, title, "shopify", True, by=by, at=now)
        save_signoff(DATA_DIR, record)
