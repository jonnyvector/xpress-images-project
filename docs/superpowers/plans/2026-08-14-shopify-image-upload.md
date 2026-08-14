# Shopify Image Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI script that pushes operator-approved local images straight onto a Shopify product's variants (no CSV/URL detour), matching filenames to variants by wood/color name.

**Architecture:** A durable `shopify_product_id` field added to the existing per-title sign-off record (`backend/signoff.py`), a small pure Shopify Admin GraphQL client module (`backend/shopify_admin.py`) built around an injectable `httpx.Client` for testability, and a CLI script (`scripts/upload_to_shopify.py`) that resolves the product, fetches its variants, matches local files to them, always prints a preview, and only writes to Shopify when `--confirm` is passed.

**Tech Stack:** Python 3.12, `httpx` (Shopify Admin GraphQL + staged file upload), `python-dotenv` (credentials), Shopify Admin API 2026-07 (`stagedUploadsCreate` → `productCreateMedia` → `productVariantAppendMedia`).

**Spec:** `docs/superpowers/specs/2026-08-14-shopify-image-upload-design.md`

## Global Constraints

- Product targeting is explicit only — never fuzzy-matched. A write path must never guess which live product an image goes to.
- The preview (matched/unmatched files) is always printed before any Shopify write, with or without `--confirm`.
- CLI only — no new HTTP endpoint in `backend/routers/`.
- Credentials: `SHOPIFY_STORE_DOMAIN` and `SHOPIFY_ADMIN_API_TOKEN` read from `.env` via `python-dotenv`, same pattern as `scripts/_onboard_common.py`'s `GEMINI_API_KEY` handling.
- Local file listing is non-recursive, same `IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}` set already used by `backend/routers/projects_media.py`'s folder-import endpoint.
- Wood-name extraction from filenames reuses the existing `backend.filename_parsing.extract_wood_name()` — never reimplemented.
- No dedup/idempotency check against existing variant media in this iteration — re-running `--confirm` adds a duplicate each time (documented in the script's `--confirm` help text).

---

## File Structure

- **Modify** `backend/signoff.py` — add `set_shopify_product()`, same shape as the existing `set_canonical()`.
- **Modify** `pyproject.toml` — add `httpx` as an explicit dependency (already present transitively via FastAPI, but the script imports it directly so it must be declared).
- **Create** `backend/shopify_admin.py` — pure Shopify Admin GraphQL client functions (fetch variants, staged upload, create media, poll status, append media to variant). Each function takes an `httpx.Client` so tests inject a mock transport.
- **Create** `tests/test_shopify_admin.py` — one test per `shopify_admin.py` function, using `httpx.MockTransport`.
- **Create** `scripts/upload_to_shopify.py` — matching logic + `main()` CLI entrypoint, wiring `shopify_admin.py` + `signoff.py` + `filename_parsing.py` together.
- **Create** `tests/test_upload_to_shopify.py` — pure-function tests (matching, material-type resolution, preview printing) with no network calls.
- **Modify** `tests/test_signoff.py` — add coverage for `set_shopify_product()`.

---

### Task 1: `set_shopify_product` on the sign-off record

**Files:**
- Modify: `backend/signoff.py`
- Test: `tests/test_signoff.py`

**Interfaces:**
- Produces: `set_shopify_product(record: dict[str, dict], title: str, product_id: str) -> dict[str, dict]` — pure, returns a new record, does not mutate the input. Stores `entry["shopify_product_id"] = product_id`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_signoff.py`:

```python
def test_set_shopify_product_stores_the_id() -> None:
    record = set_shopify_product({}, "A", "gid://shopify/Product/123")
    assert record["A"]["shopify_product_id"] == "gid://shopify/Product/123"


def test_set_shopify_product_preserves_other_fields() -> None:
    record = set_gate({}, "A", "shopify", True, by="j", at="t")
    record = set_canonical(record, "A", "proj1")
    record = set_shopify_product(record, "A", "gid://shopify/Product/123")
    assert record["A"]["canonical_project_id"] == "proj1"
    assert record["A"]["in_shopify"]["by"] == "j"
    assert record["A"]["shopify_product_id"] == "gid://shopify/Product/123"


def test_set_shopify_product_round_trips(tmp_path) -> None:
    record = set_shopify_product({}, "A", "gid://shopify/Product/123")
    save_signoff(tmp_path, record)
    assert load_signoff(tmp_path) == record


def test_set_shopify_product_does_not_mutate_input() -> None:
    original = {}
    set_shopify_product(original, "A", "gid://shopify/Product/123")
    assert original == {}
```

Add `set_shopify_product` to the existing import block at the top of `tests/test_signoff.py`:

```python
from backend.signoff import (
    GATE_KEYS,
    SIGNOFF_FILENAME,
    SignoffRecordError,
    is_stale,
    load_signoff,
    load_signoff_strict,
    save_signoff,
    set_canonical,
    set_exclusions,
    set_gate,
    set_shopify_product,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_signoff.py -k shopify_product -v`
Expected: FAIL with `ImportError: cannot import name 'set_shopify_product'`

- [ ] **Step 3: Implement `set_shopify_product`**

Add to `backend/signoff.py`, right after `set_canonical`:

```python
def set_shopify_product(
    record: dict[str, dict], title: str, product_id: str
) -> dict[str, dict]:
    """Link this product title to the Shopify product its images upload to.

    Durable, operator-picked, never inferred — this is the write-path
    counterpart to the read-only fuzzy title matching used elsewhere; a wrong
    guess here would push an image to the wrong live product.
    """
    entry = _entry(record, title)
    entry["shopify_product_id"] = product_id
    return {**record, title: entry}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_signoff.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/signoff.py tests/test_signoff.py
git commit -m "feat: add set_shopify_product to the coverage sign-off record"
```

---

### Task 2: Shopify Admin API client module

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/shopify_admin.py`
- Test: `tests/test_shopify_admin.py`

**Interfaces:**
- Produces:
  - `class ShopifyApiError(Exception)`
  - `@dataclass class Variant: id: str; option_value: str`
  - `fetch_variants(client: httpx.Client, store_domain: str, token: str, product_id: str) -> list[Variant]`
  - `create_staged_upload(client: httpx.Client, store_domain: str, token: str, filename: str, mime_type: str, file_size: int) -> dict` (keys: `url`, `resourceUrl`, `parameters`)
  - `upload_staged_file(client: httpx.Client, staged_target: dict, filename: str, mime_type: str, content: bytes) -> None`
  - `create_product_media(client: httpx.Client, store_domain: str, token: str, product_id: str, resource_url: str, alt: str) -> str` (returns media id)
  - `wait_for_media_ready(client: httpx.Client, store_domain: str, token: str, media_id: str, attempts: int = 5, delay_seconds: float = 1.0) -> None`
  - `append_media_to_variant(client: httpx.Client, store_domain: str, token: str, product_id: str, variant_id: str, media_id: str) -> None`

- [ ] **Step 1: Add the `httpx` dependency**

```bash
uv add httpx
```

Verify `pyproject.toml`'s `dependencies` list now includes an `httpx>=...` line.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_shopify_admin.py`:

```python
import httpx
import pytest

from backend.shopify_admin import (
    ShopifyApiError,
    Variant,
    append_media_to_variant,
    create_product_media,
    create_staged_upload,
    fetch_variants,
    upload_staged_file,
    wait_for_media_ready,
)

STORE = "test-store.myshopify.com"
TOKEN = "shpat_test"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_variants_returns_id_and_option_value():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "product": {
                        "variants": {
                            "nodes": [
                                {
                                    "id": "gid://shopify/ProductVariant/1",
                                    "selectedOptions": [{"name": "Color", "value": "949T White"}],
                                },
                                {
                                    "id": "gid://shopify/ProductVariant/2",
                                    "selectedOptions": [{"name": "Color", "value": "Bisque"}],
                                },
                            ]
                        }
                    }
                }
            },
        )

    client = _client(handler)
    variants = fetch_variants(client, STORE, TOKEN, "gid://shopify/Product/1")
    assert variants == [
        Variant(id="gid://shopify/ProductVariant/1", option_value="949T White"),
        Variant(id="gid://shopify/ProductVariant/2", option_value="Bisque"),
    ]


def test_fetch_variants_raises_when_product_missing():
    def handler(request):
        return httpx.Response(200, json={"data": {"product": None}})

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        fetch_variants(client, STORE, TOKEN, "gid://shopify/Product/999")


def test_create_staged_upload_returns_target():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "stagedUploadsCreate": {
                        "stagedTargets": [
                            {
                                "url": "https://upload.example/target",
                                "resourceUrl": "https://upload.example/resource/1",
                                "parameters": [{"name": "key", "value": "abc"}],
                            }
                        ],
                        "userErrors": [],
                    }
                }
            },
        )

    client = _client(handler)
    target = create_staged_upload(client, STORE, TOKEN, "bisque.png", "image/png", 1234)
    assert target["resourceUrl"] == "https://upload.example/resource/1"


def test_create_staged_upload_raises_on_user_errors():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "stagedUploadsCreate": {
                        "stagedTargets": [],
                        "userErrors": [{"field": ["input"], "message": "bad size"}],
                    }
                }
            },
        )

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        create_staged_upload(client, STORE, TOKEN, "bisque.png", "image/png", 1234)


def test_upload_staged_file_posts_to_target_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(201)

    client = _client(handler)
    target = {
        "url": "https://upload.example/target",
        "parameters": [{"name": "key", "value": "abc"}],
    }
    upload_staged_file(client, target, "bisque.png", "image/png", b"fake-bytes")
    assert seen["url"] == "https://upload.example/target"


def test_create_product_media_returns_media_id():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "productCreateMedia": {
                        "media": [{"id": "gid://shopify/MediaImage/1", "status": "PROCESSING"}],
                        "mediaUserErrors": [],
                    }
                }
            },
        )

    client = _client(handler)
    media_id = create_product_media(
        client, STORE, TOKEN, "gid://shopify/Product/1",
        "https://upload.example/resource/1", "Bisque",
    )
    assert media_id == "gid://shopify/MediaImage/1"


def test_create_product_media_raises_on_media_user_errors():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "productCreateMedia": {
                        "media": [],
                        "mediaUserErrors": [
                            {"field": ["media", "0", "originalSource"], "message": "Image URL is invalid"}
                        ],
                    }
                }
            },
        )

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        create_product_media(client, STORE, TOKEN, "gid://shopify/Product/1", "bad", "Bisque")


def test_wait_for_media_ready_returns_when_ready():
    def handler(request):
        return httpx.Response(200, json={"data": {"node": {"status": "READY"}}})

    client = _client(handler)
    wait_for_media_ready(client, STORE, TOKEN, "gid://shopify/MediaImage/1", attempts=3, delay_seconds=0)


def test_wait_for_media_ready_raises_on_failed_status():
    def handler(request):
        return httpx.Response(200, json={"data": {"node": {"status": "FAILED"}}})

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        wait_for_media_ready(client, STORE, TOKEN, "gid://shopify/MediaImage/1", attempts=3, delay_seconds=0)


def test_wait_for_media_ready_raises_after_exhausting_attempts():
    def handler(request):
        return httpx.Response(200, json={"data": {"node": {"status": "PROCESSING"}}})

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        wait_for_media_ready(client, STORE, TOKEN, "gid://shopify/MediaImage/1", attempts=2, delay_seconds=0)


def test_append_media_to_variant_raises_on_user_errors():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "productVariantAppendMedia": {
                        "productVariants": [],
                        "userErrors": [{"field": ["variantId"], "message": "not found"}],
                    }
                }
            },
        )

    client = _client(handler)
    with pytest.raises(ShopifyApiError):
        append_media_to_variant(
            client, STORE, TOKEN, "gid://shopify/Product/1",
            "gid://shopify/ProductVariant/1", "gid://shopify/MediaImage/1",
        )


def test_append_media_to_variant_succeeds_without_errors():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "data": {
                    "productVariantAppendMedia": {
                        "productVariants": [{"id": "gid://shopify/ProductVariant/1"}],
                        "userErrors": [],
                    }
                }
            },
        )

    client = _client(handler)
    append_media_to_variant(
        client, STORE, TOKEN, "gid://shopify/Product/1",
        "gid://shopify/ProductVariant/1", "gid://shopify/MediaImage/1",
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_shopify_admin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.shopify_admin'`

- [ ] **Step 4: Implement `backend/shopify_admin.py`**

```python
"""Shopify Admin API client: variant fetch + staged-upload-to-variant-media flow.

Thin wrapper around the GraphQL calls scripts/upload_to_shopify.py needs. Each
function takes an httpx.Client so tests can inject a mock transport instead of
hitting the network.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

API_VERSION = "2026-07"


class ShopifyApiError(Exception):
    """A Shopify GraphQL call returned userErrors, or a lookup found nothing."""


def _graphql_url(store_domain: str) -> str:
    return f"https://{store_domain}/admin/api/{API_VERSION}/graphql.json"


def _post_graphql(
    client: httpx.Client, store_domain: str, token: str, query: str, variables: dict
) -> dict:
    resp = client.post(
        _graphql_url(store_domain),
        json={"query": query, "variables": variables},
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    body = resp.json()
    if "errors" in body:
        raise ShopifyApiError(str(body["errors"]))
    return body["data"]


@dataclass
class Variant:
    id: str
    option_value: str


_VARIANTS_QUERY = """
query ProductVariants($id: ID!) {
  product(id: $id) {
    variants(first: 100) {
      nodes {
        id
        selectedOptions { name value }
      }
    }
  }
}
"""


def fetch_variants(
    client: httpx.Client, store_domain: str, token: str, product_id: str
) -> list[Variant]:
    """Fetch up to 100 variants for a product, with the first selected option
    value (the wood/color name — Option1 in this store)."""
    data = _post_graphql(client, store_domain, token, _VARIANTS_QUERY, {"id": product_id})
    product = data.get("product")
    if product is None:
        raise ShopifyApiError(f"Product not found: {product_id}")
    variants = []
    for node in product["variants"]["nodes"]:
        options = node.get("selectedOptions") or []
        value = options[0]["value"] if options else ""
        variants.append(Variant(id=node["id"], option_value=value))
    return variants


_STAGED_UPLOADS_CREATE = """
mutation StagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters { name value }
    }
    userErrors { field message }
  }
}
"""


def create_staged_upload(
    client: httpx.Client,
    store_domain: str,
    token: str,
    filename: str,
    mime_type: str,
    file_size: int,
) -> dict:
    """Returns {"url", "resourceUrl", "parameters": [{"name", "value"}, ...]}."""
    data = _post_graphql(
        client,
        store_domain,
        token,
        _STAGED_UPLOADS_CREATE,
        {
            "input": [
                {
                    "filename": filename,
                    "mimeType": mime_type,
                    "httpMethod": "POST",
                    "resource": "IMAGE",
                    "fileSize": str(file_size),
                }
            ]
        },
    )
    payload = data["stagedUploadsCreate"]
    if payload["userErrors"]:
        raise ShopifyApiError(str(payload["userErrors"]))
    return payload["stagedTargets"][0]


def upload_staged_file(
    client: httpx.Client,
    staged_target: dict,
    filename: str,
    mime_type: str,
    content: bytes,
) -> None:
    """POST the file bytes to the staged target URL with its required form fields."""
    form = {p["name"]: p["value"] for p in staged_target["parameters"]}
    resp = client.post(
        staged_target["url"],
        data=form,
        files={"file": (filename, content, mime_type)},
    )
    resp.raise_for_status()


_PRODUCT_CREATE_MEDIA = """
mutation ProductCreateMedia($productId: ID!, $media: [CreateMediaInput!]!) {
  productCreateMedia(productId: $productId, media: $media) {
    media {
      id
      status
    }
    mediaUserErrors { field message }
  }
}
"""


def create_product_media(
    client: httpx.Client,
    store_domain: str,
    token: str,
    product_id: str,
    resource_url: str,
    alt: str,
) -> str:
    """Registers the staged upload as product media; returns the new media id."""
    data = _post_graphql(
        client,
        store_domain,
        token,
        _PRODUCT_CREATE_MEDIA,
        {
            "productId": product_id,
            "media": [
                {"originalSource": resource_url, "mediaContentType": "IMAGE", "alt": alt}
            ],
        },
    )
    payload = data["productCreateMedia"]
    if payload["mediaUserErrors"]:
        raise ShopifyApiError(str(payload["mediaUserErrors"]))
    media = payload["media"]
    if not media:
        raise ShopifyApiError("productCreateMedia returned no media")
    return media[0]["id"]


_MEDIA_STATUS_QUERY = """
query MediaStatus($id: ID!) {
  node(id: $id) {
    ... on MediaImage { status }
  }
}
"""

_READY_STATUSES = {"READY", "UPLOADED"}


def wait_for_media_ready(
    client: httpx.Client,
    store_domain: str,
    token: str,
    media_id: str,
    attempts: int = 5,
    delay_seconds: float = 1.0,
) -> None:
    """Short-poll until the media leaves PROCESSING, or raise if it never does."""
    for _ in range(attempts):
        data = _post_graphql(client, store_domain, token, _MEDIA_STATUS_QUERY, {"id": media_id})
        status = (data.get("node") or {}).get("status")
        if status in _READY_STATUSES:
            return
        if status == "FAILED":
            raise ShopifyApiError(f"Media {media_id} failed processing")
        if delay_seconds:
            time.sleep(delay_seconds)
    raise ShopifyApiError(f"Media {media_id} did not finish processing in time")


_APPEND_MEDIA = """
mutation ProductVariantAppendMedia($productId: ID!, $variantMedia: [ProductVariantAppendMediaInput!]!) {
  productVariantAppendMedia(productId: $productId, variantMedia: $variantMedia) {
    productVariants { id }
    userErrors { field message }
  }
}
"""


def append_media_to_variant(
    client: httpx.Client,
    store_domain: str,
    token: str,
    product_id: str,
    variant_id: str,
    media_id: str,
) -> None:
    data = _post_graphql(
        client,
        store_domain,
        token,
        _APPEND_MEDIA,
        {
            "productId": product_id,
            "variantMedia": [{"variantId": variant_id, "mediaIds": [media_id]}],
        },
    )
    if data["productVariantAppendMedia"]["userErrors"]:
        raise ShopifyApiError(str(data["productVariantAppendMedia"]["userErrors"]))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_shopify_admin.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock backend/shopify_admin.py tests/test_shopify_admin.py
git commit -m "feat: add Shopify Admin API client for the staged-upload-to-variant flow"
```

---

### Task 3: Matching, material-type resolution, and preview printing

**Files:**
- Create: `scripts/upload_to_shopify.py` (matching/printing portion only — `main()` comes in Task 4)
- Test: `tests/test_upload_to_shopify.py`

**Interfaces:**
- Consumes: `backend.filename_parsing.extract_wood_name(stem: str, wood_types: dict) -> str`; `backend.coverage.CATEGORIES`, `backend.coverage.load_products(csv_path: Path) -> list[tuple[str, float, int]]`; `backend.shopify_admin.Variant`.
- Produces:
  - `normalize_name(value: str) -> str`
  - `@dataclass class MatchResult: path: Path; wood_name: str; variant_id: str | None`
  - `match_files_to_variants(files: list[Path], wood_types: dict[str, dict], variants: list["Variant"]) -> list[MatchResult]`
  - `resolve_material_type(title: str, data_dir: Path = DATA_DIR) -> str` (raises `SystemExit` if the title isn't in any sales CSV)
  - `print_preview(matches: list[MatchResult]) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_upload_to_shopify.py`:

```python
from pathlib import Path

import pytest

from backend.shopify_admin import Variant
from scripts.upload_to_shopify import (
    MatchResult,
    match_files_to_variants,
    normalize_name,
    print_preview,
    resolve_material_type,
)


def test_normalize_name_strips_and_casefolds():
    assert normalize_name("  Bisque ") == normalize_name("bisque")


def test_match_files_to_variants_matches_case_and_whitespace_insensitively():
    wood_types = {"bisque": {"name": "Bisque"}}
    files = [Path("proj_bisque.png")]
    variants = [Variant(id="gid://shopify/ProductVariant/1", option_value="  bisque ")]
    results = match_files_to_variants(files, wood_types, variants)
    assert results == [
        MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id="gid://shopify/ProductVariant/1")
    ]


def test_match_files_to_variants_flags_unmatched():
    wood_types = {"bisque": {"name": "Bisque"}}
    files = [Path("proj_bisque.png")]
    variants = [Variant(id="gid://shopify/ProductVariant/1", option_value="Frosty White")]
    results = match_files_to_variants(files, wood_types, variants)
    assert results == [MatchResult(path=Path("proj_bisque.png"), wood_name="Bisque", variant_id=None)]


def test_resolve_material_type_finds_category(tmp_path):
    (tmp_path / "thermofoil_cabinet_doors.csv").write_text(
        "Title,Net Sales,Qty\nAR756 Thermofoil Cabinet Door,1000,10\n"
    )
    assert resolve_material_type("AR756 Thermofoil Cabinet Door", data_dir=tmp_path) == "rtf"


def test_resolve_material_type_raises_when_not_found(tmp_path):
    with pytest.raises(SystemExit):
        resolve_material_type("Nonexistent Product", data_dir=tmp_path)


def test_print_preview_lists_matched_and_unmatched(capsys):
    matches = [
        MatchResult(path=Path("a.png"), wood_name="Bisque", variant_id="gid://shopify/ProductVariant/1"),
        MatchResult(path=Path("b.png"), wood_name="Unknown", variant_id=None),
    ]
    print_preview(matches)
    out = capsys.readouterr().out
    assert "Matched (1)" in out
    assert "a.png -> Bisque" in out
    assert "Unmatched (1)" in out
    assert "b.png -> Unknown" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upload_to_shopify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.upload_to_shopify'`

- [ ] **Step 3: Implement the matching/printing portion of `scripts/upload_to_shopify.py`**

Create `scripts/upload_to_shopify.py` with this content (the CLI `main()` is appended in Task 4 — write the file exactly as below for now):

```python
"""Push operator-approved local images onto a Shopify product's variants.

Reads image files from a local folder, matches each to a variant by wood/color
name, always prints a preview, and only writes to Shopify when --confirm is
passed. See docs/superpowers/specs/2026-08-14-shopify-image-upload-design.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.coverage import CATEGORIES, DATA_DIR, load_products
from backend.filename_parsing import extract_wood_name
from backend.shopify_admin import Variant


def normalize_name(value: str) -> str:
    return value.strip().casefold()


@dataclass
class MatchResult:
    path: Path
    wood_name: str
    variant_id: str | None


def match_files_to_variants(
    files: list[Path], wood_types: dict[str, dict], variants: list[Variant]
) -> list[MatchResult]:
    by_normalized = {normalize_name(v.option_value): v.id for v in variants}
    results = []
    for path in files:
        wood_name = extract_wood_name(path.stem, wood_types)
        variant_id = by_normalized.get(normalize_name(wood_name))
        results.append(MatchResult(path=path, wood_name=wood_name, variant_id=variant_id))
    return results


def resolve_material_type(title: str, data_dir: Path = DATA_DIR) -> str:
    """Find which sales-CSV category (and therefore material_type) a product
    title belongs to, the same way backend/routers/coverage.py validates
    titles for sign-off writes."""
    for cat in CATEGORIES:
        titles = {t for t, _, _ in load_products(data_dir / cat["csv"])}
        if title in titles:
            return cat["material"]
    raise SystemExit(f"Unknown product title: {title!r} (not found in any sales CSV)")


def print_preview(matches: list[MatchResult]) -> None:
    matched = [m for m in matches if m.variant_id is not None]
    unmatched = [m for m in matches if m.variant_id is None]
    print(f"Matched ({len(matched)}):")
    for m in matched:
        print(f"  {m.path.name} -> {m.wood_name}")
    print(f"Unmatched ({len(unmatched)}):")
    for m in unmatched:
        print(f"  {m.path.name} -> {m.wood_name} (no variant match)")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_upload_to_shopify.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/upload_to_shopify.py tests/test_upload_to_shopify.py
git commit -m "feat: add wood-name-to-variant matching for the Shopify uploader"
```

---

### Task 4: CLI entrypoint (`main()`)

**Files:**
- Modify: `scripts/upload_to_shopify.py` (append `main()` and credential loading)
- Test: `tests/test_upload_to_shopify.py` (extend)

**Interfaces:**
- Consumes: everything from Task 3, plus `backend.signoff.{load_signoff, load_signoff_strict, save_signoff, set_shopify_product, SIGNOFF_LOCK}`, `backend.materials.{load_material_types, MIME_MAP}`, `backend.routers.projects_media.IMAGE_EXTENSIONS`, `backend.shopify_admin.{ShopifyApiError, fetch_variants, create_staged_upload, upload_staged_file, create_product_media, wait_for_media_ready, append_media_to_variant}`.
- Produces: `read_shopify_credentials() -> tuple[str, str]`; `main() -> None` (argparse entrypoint, guarded by `if __name__ == "__main__"`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_upload_to_shopify.py`:

```python
import os

from scripts.upload_to_shopify import read_shopify_credentials


def test_read_shopify_credentials_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOPIFY_STORE_DOMAIN", raising=False)
    monkeypatch.delenv("SHOPIFY_ADMIN_API_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here to load
    with pytest.raises(SystemExit):
        read_shopify_credentials()


def test_read_shopify_credentials_returns_env_values(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "test-store.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_API_TOKEN", "shpat_test")
    monkeypatch.chdir(tmp_path)
    domain, token = read_shopify_credentials()
    assert domain == "test-store.myshopify.com"
    assert token == "shpat_test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_upload_to_shopify.py -k credentials -v`
Expected: FAIL with `ImportError: cannot import name 'read_shopify_credentials'`

- [ ] **Step 3: Append credentials + `main()` to `scripts/upload_to_shopify.py`**

Add these imports to the top of `scripts/upload_to_shopify.py` (alongside the existing ones from Task 3):

```python
import argparse
import os

from dotenv import load_dotenv

from backend.materials import MIME_MAP, load_material_types
from backend.routers.projects_media import IMAGE_EXTENSIONS
from backend.shopify_admin import (
    ShopifyApiError,
    append_media_to_variant,
    create_product_media,
    create_staged_upload,
    fetch_variants,
    upload_staged_file,
    wait_for_media_ready,
)
from backend.signoff import (
    SIGNOFF_LOCK,
    load_signoff,
    load_signoff_strict,
    save_signoff,
    set_shopify_product,
)
import httpx
```

Append this to the end of the file:

```python
def read_shopify_credentials() -> tuple[str, str]:
    """SHOPIFY_STORE_DOMAIN + SHOPIFY_ADMIN_API_TOKEN from the project .env,
    overriding any stale shell export (same pattern as
    scripts/_onboard_common.py's GEMINI_API_KEY handling)."""
    load_dotenv(override=True)
    domain = os.environ.get("SHOPIFY_STORE_DOMAIN", "")
    token = os.environ.get("SHOPIFY_ADMIN_API_TOKEN", "")
    if not domain or not token:
        raise SystemExit(
            "SHOPIFY_STORE_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must be set in .env"
        )
    return domain, token


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload approved local images to a Shopify product's variants."
    )
    parser.add_argument(
        "--title", required=True,
        help="Sales-CSV product title (matches the coverage sign-off record)",
    )
    parser.add_argument(
        "--folder", required=True, help="Local folder of approved images to upload"
    )
    parser.add_argument(
        "--product",
        help="Shopify product id/gid, e.g. gid://shopify/Product/123. "
        "Persisted to the sign-off record for future runs.",
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Actually write to Shopify. Without this flag, only a preview is "
        "printed. Re-running with --confirm does not check for images already "
        "on the variant and will add a duplicate.",
    )
    args = parser.parse_args()

    store_domain, token = read_shopify_credentials()
    material_type = resolve_material_type(args.title)

    record = load_signoff(DATA_DIR)
    entry = record.get(args.title) or {}
    product_id = args.product or entry.get("shopify_product_id")
    if not product_id:
        raise SystemExit(
            f"No Shopify product linked to {args.title!r} yet. Pass --product once to link it."
        )
    if args.product:
        with SIGNOFF_LOCK:
            record = load_signoff_strict(DATA_DIR)
            record = set_shopify_product(record, args.title, args.product)
            save_signoff(DATA_DIR, record)

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        raise SystemExit(f"Not a directory: {args.folder}")
    files = sorted(
        f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not files:
        raise SystemExit(f"No image files found in {args.folder}")

    wood_types = load_material_types(material_type)

    with httpx.Client(timeout=30.0) as client:
        variants = fetch_variants(client, store_domain, token, product_id)
        matches = match_files_to_variants(files, wood_types, variants)
        print_preview(matches)

        if not args.confirm:
            print("\nDry run only — pass --confirm to upload the matched files.")
            return

        matched = [m for m in matches if m.variant_id is not None]
        failures: list[tuple[str, str]] = []
        for m in matched:
            try:
                content = m.path.read_bytes()
                mime_type = MIME_MAP.get(m.path.suffix.lower(), "image/png")
                target = create_staged_upload(
                    client, store_domain, token, m.path.name, mime_type, len(content)
                )
                upload_staged_file(client, target, m.path.name, mime_type, content)
                media_id = create_product_media(
                    client, store_domain, token, product_id, target["resourceUrl"], m.wood_name
                )
                wait_for_media_ready(client, store_domain, token, media_id)
                append_media_to_variant(
                    client, store_domain, token, product_id, m.variant_id, media_id
                )
                print(f"  uploaded: {m.path.name} -> {m.wood_name}")
            except ShopifyApiError as exc:
                failures.append((m.path.name, str(exc)))
                print(f"  FAILED: {m.path.name} -> {exc}")

    if failures:
        print(f"\n{len(failures)} file(s) failed:")
        for name, msg in failures:
            print(f"  {name}: {msg}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_upload_to_shopify.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full test suite**

Run: `uv run pytest -q`
Expected: all PASS (no regressions in `test_signoff.py`, `test_coverage.py`, or anything else touching `backend.signoff`/`backend.materials`)

- [ ] **Step 6: Commit**

```bash
git add scripts/upload_to_shopify.py tests/test_upload_to_shopify.py
git commit -m "feat: add upload_to_shopify.py CLI entrypoint"
```

---

### Task 5: Manual verification (not automated)

This task has no code changes — it's the manual checklist from the spec's Testing section, run once before the script is trusted for real use.

- [ ] **Step 1:** Create the custom Shopify app (Settings → Apps and sales channels → Develop apps), scopes `read_products` + `write_products`, install it, copy the Admin API access token.
- [ ] **Step 2:** Add `SHOPIFY_STORE_DOMAIN=your-store.myshopify.com` and `SHOPIFY_ADMIN_API_TOKEN=shpat_...` to `.env`.
- [ ] **Step 3:** Pick one real product title + its Shopify product gid, and a folder of a few already-approved images for it.
- [ ] **Step 4:** Run a dry run (no `--confirm`):
  ```bash
  uv run python scripts/upload_to_shopify.py --title "<real title>" --folder "<real folder>" --product "gid://shopify/Product/<id>"
  ```
  Confirm the preview's Matched/Unmatched split looks correct against the real variant list before ever passing `--confirm`.
- [ ] **Step 5:** Only after the dry run looks right, re-run with `--confirm` on a small batch and check the images land on the correct variants in Shopify Admin.

---

## Self-Review

**Spec coverage:**
- Source of truth for approved → operator curation, no code change to Save-to-Folder — reflected in Global Constraints and the spec doc; no task needed since it's an explicit non-change.
- Product targeting: explicit `shopify_product_id` on the sign-off record → Task 1.
- Variant targeting: normalized match + mandatory preview → Task 3 (`match_files_to_variants`, `print_preview`) and Task 4 (`main()` always prints the preview before checking `--confirm`).
- CLI interface → Task 4.
- Auth via `.env` → Task 4 (`read_shopify_credentials`).
- Staged-upload → create-media → append-to-variant flow → Task 2.
- Error handling (missing credentials, missing product link, missing folder, unparseable filenames, per-file GraphQL errors, stuck media) → covered across Task 2 (`ShopifyApiError`, `wait_for_media_ready`) and Task 4 (`main()`'s per-file try/except, `resolve_material_type`'s `SystemExit`, folder validation).
- Testing section → Tasks 1–4 each carry their own tests; Task 5 is the spec's manual dry-run step.
- Out of scope items (bulk run, UI panel, idempotency, replace/delete) → intentionally have no task; called out again here so a reviewer doesn't go looking for them.

**Placeholder scan:** no TBD/TODO, no "add appropriate error handling"-style steps — every step has real code or a concrete command.

**Type consistency:** `MatchResult`, `Variant`, `ShopifyApiError` are defined once (Tasks 2–3) and imported with matching names/signatures everywhere they're used later (Task 4's `main()`). `resolve_material_type`'s `data_dir` parameter matches its test calls. `read_shopify_credentials`'s return type (`tuple[str, str]`) matches how `main()` unpacks it.
