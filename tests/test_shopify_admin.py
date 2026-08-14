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
