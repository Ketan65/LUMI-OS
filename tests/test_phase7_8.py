"""Tests for Phase 7 (Multi-cloud LLM Adapter & Router Stats) and Phase 8 (Auth, Security, PWA)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from brain.cloud_adapter import CloudBrain, PROVIDER_DEFAULTS, friendly_cloud_error
from brain.router import ModelRouter
from core.orchestrator import Orchestrator
from web.server import create_app


import asyncio

class SyncClient:
    def __init__(self, app):
        self.app = app

    def _req(self, method, url, **kw):
        async def go():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport,
                                         base_url="http://127.0.0.1:8765") as c:
                return await c.request(method, url, **kw)
        return asyncio.run(go())

    def get(self, url, **kw):
        return self._req("GET", url, **kw)

    def post(self, url, **kw):
        return self._req("POST", url, **kw)


# ── Phase 7: Multi-Cloud Adapter & Router ─────────────────────────────────────

def test_cloud_brain_provider_defaults():
    assert "nvidia" in PROVIDER_DEFAULTS
    assert "groq" in PROVIDER_DEFAULTS
    assert "openrouter" in PROVIDER_DEFAULTS
    assert "openai" in PROVIDER_DEFAULTS

    assert "api.groq.com" in PROVIDER_DEFAULTS["groq"]["base_url"]
    assert "openrouter.ai" in PROVIDER_DEFAULTS["openrouter"]["base_url"]


def test_cloud_brain_requires_key():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError) as exc_info:
            CloudBrain({"router": {"cloud_provider": "groq"}})
        assert "GROQ_API_KEY" in str(exc_info.value)


def test_model_router_tracks_stats():
    fake_local = MagicMock()
    fake_local.model = "local-llama"
    reply = MagicMock()
    reply.text = "Local response"
    reply.tool_calls = []
    fake_local.chat.return_value = reply

    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "brain.log"
        router = ModelRouter(fake_local, None, config={}, log_path=str(log_file))

        router.chat([{"role": "user", "content": "hi"}])
        router.chat([{"role": "user", "content": "hello"}])

        stats = router.get_stats()
        assert stats["requests_total"] == 2
        assert stats["local_requests"] == 2
        assert stats["cloud_requests"] == 0
        assert stats["fallbacks_total"] == 0


# ── Phase 8: Web Auth & Security & PWA ────────────────────────────────────────

def test_web_auth_protection_and_login():
    mock_brain = MagicMock()
    mock_brain.model = "test-model"
    reply = MagicMock()
    reply.text = "Hello from secured LUMI"
    reply.tool_calls = []
    mock_brain.chat.return_value = reply

    cfg = {
        "web": {"auth_token": "supersecretpassword123"},
        "allowed_paths": ["C:\\LUMI"],
    }
    orc = Orchestrator(brain=mock_brain, config=cfg)
    app = create_app(orc)
    client = SyncClient(app)

    # 1. Unauthenticated request to /api/chat -> 401
    resp_unauth = client.post("/api/chat", json={"message": "hi", "stream": False})
    assert resp_unauth.status_code == 401
    assert "Unauthorized" in resp_unauth.json()["error"]

    # 2. Public /api/status -> allowed without auth
    resp_status = client.get("/api/status")
    assert resp_status.status_code == 200

    # 3. Bad login attempt -> 401
    resp_bad_login = client.post("/api/login", json={"token": "wrongtoken"})
    assert resp_bad_login.status_code == 401

    # 4. Successful login -> sets cookie
    resp_login = client.post("/api/login", json={"token": "supersecretpassword123"})
    assert resp_login.status_code == 200
    assert resp_login.json()["ok"] is True
    assert "lumi_auth" in resp_login.cookies

    # 5. Authenticated with Bearer header -> 200
    resp_bearer = client.post(
        "/api/chat",
        json={"message": "hi", "stream": False},
        headers={"Authorization": "Bearer supersecretpassword123"},
    )
    assert resp_bearer.status_code == 200

    # 6. Authenticated with cookie -> 200
    auth_cookie = resp_login.cookies["lumi_auth"]
    resp_cookie = client.post(
        "/api/chat",
        json={"message": "hi", "stream": False},
        cookies={"lumi_auth": auth_cookie},
    )
    assert resp_cookie.status_code == 200


def test_web_pwa_manifest_and_sw():
    orc = Orchestrator(brain=MagicMock(), config={})
    app = create_app(orc)
    client = SyncClient(app)

    res_manifest = client.get("/manifest.json")
    assert res_manifest.status_code == 200
    data = res_manifest.json()
    assert data["name"] == "LUMI Assistant"
    assert data["short_name"] == "LUMI"

    res_sw = client.get("/sw.js")
    assert res_sw.status_code == 200
    assert "lumi-v1" in res_sw.text
