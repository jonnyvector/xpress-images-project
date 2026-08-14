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
mutation ProductVariantAppendMedia(
  $productId: ID!
  $variantMedia: [ProductVariantAppendMediaInput!]!
) {
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
