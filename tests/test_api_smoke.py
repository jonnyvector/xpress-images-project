from fastapi.testclient import TestClient

from backend.app import app


def test_styles_endpoint_returns_list() -> None:
    with TestClient(app) as client:
        resp = client.get("/api/styles", params={"material": "wood"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data, "Expected at least one style"
