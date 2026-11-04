"""Web API endpoint tests for Phase 2 EYES: Vision endpoints."""

import asyncio
import base64
import io
from unittest.mock import patch

import httpx
import pytest
from PIL import Image

from web.server import create_app


class StubOrch:
    def __init__(self):
        self.config = {
            "web": {"allow_remote": True},
            "permissions": {"analyze_screen": "auto"},
        }
        self.memory = None
        self.brain = None
        self.registry = None
        self.audit = None
        self.projects = None


class SyncClient:
    def __init__(self, app):
        self.app = app

    def _req(self, method, url, **kw):
        async def go():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as c:
                return await c.request(method, url, **kw)

        return asyncio.run(go())

    def get(self, url, **kw):
        return self._req("GET", url, **kw)

    def post(self, url, **kw):
        return self._req("POST", url, **kw)


@pytest.fixture
def client():
    orch = StubOrch()
    return SyncClient(create_app(orch))


def test_vision_analyze_with_image(client):
    img = Image.new("RGB", (20, 20), color=(0, 255, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    with patch("tools.vision.analyze_screen_image", return_value="Green square detected."):
        resp = client.post("/api/vision/analyze", json={"prompt": "What color?", "image_base64": b64})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "Green square detected." in data["analysis"]
        assert data["image_url"] == "/api/vision/latest"


def test_vision_latest_endpoint(client):
    # After analyzing with image, latest should return the image
    resp = client.get("/api/vision/latest")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
