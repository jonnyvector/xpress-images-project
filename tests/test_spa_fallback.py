"""App links (/doors/abc) must load the frontend on refresh; missing files still 404."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app import SPAStaticFiles


def _client(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "app.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=str(tmp_path), html=True))
    return TestClient(app)


def test_app_links_serve_index(tmp_path):
    client = _client(tmp_path)
    for path in ("/", "/library", "/doors/abc123", "/apiary"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="root"' in response.text


def test_real_files_are_served(tmp_path):
    assert _client(tmp_path).get("/app.js").text == "console.log(1)"


def test_missing_asset_and_api_paths_still_404(tmp_path):
    client = _client(tmp_path)
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/nope").status_code == 404
