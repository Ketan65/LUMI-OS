"""Web server: Host/Origin guard (CSRF + DNS rebinding), static allowlist, limits."""
import asyncio
from types import SimpleNamespace

import httpx
import pytest

from web.server import create_app


class StubGate:
    def __init__(self):
        from safety.gate import ApprovalManager
        self.approval_mgr = ApprovalManager()

    def resolve_approval(self, aid, approved):
        return self.approval_mgr.resolve(aid, approved)


class StubOrch:
    config = {}
    memory = None
    audit = None
    registry = None
    projects = None
    gate = StubGate()
    brain = SimpleNamespace(last_provider="fake", last_model="m", active_policy="p")

    def run_turn(self, msg):
        return {"reply": f"echo:{msg}", "tool_trace": [], "provider": "fake",
                "model": "m", "elapsed_ms": 1}

    def maybe_reflect(self, *_):
        pass

    def command(self, cmd):
        return False, "cmd ok"



class SyncClient:
    """TestClient jaisa chhota wrapper (starlette 0.27 TestClient + httpx 0.28 = crash)."""

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


@pytest.fixture
def client():
    orch = StubOrch()
    c = SyncClient(create_app(orch))
    c.orch = orch
    return c




def test_chat_from_own_origin_works(client):
    r = client.post("/api/chat", json={"message": "hi"},
                    headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200 and r.json()["reply"] == "echo:hi"


def test_chat_without_origin_works(client):         # curl / scripts
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 200


@pytest.mark.parametrize("origin", ["http://evil.com", "https://127.0.0.1.evil.com",
                                    "null"])
def test_cross_site_post_blocked(client, origin):
    r = client.post("/api/chat", json={"message": "hi"}, headers={"Origin": origin})
    assert r.status_code == 403


def test_dns_rebinding_host_blocked(client):
    r = client.get("/api/status", headers={"Host": "evil.com:8765"})
    assert r.status_code == 403


def test_localhost_host_ok(client):
    r = client.get("/api/status", headers={"Host": "localhost:8765"})
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_static_allowlist_only(client):
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    for leak in ("server.py", "__init__.py", "index.html", "..%2Fconfig.yaml"):
        assert client.get(f"/static/{leak}").status_code == 404


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "LUMI" in r.text and "ARCHON" not in r.text


def test_oversized_message_rejected(client):
    r = client.post("/api/chat", json={"message": "x" * 8001})
    assert r.status_code == 422


def test_slash_command_path(client):
    r = client.post("/api/chat", json={"message": "/tools"})
    assert r.json()["reply"] == "cmd ok"


def test_approval_endpoints(client):
    # initially no pending approvals
    r = client.get("/api/approvals/pending")
    assert r.status_code == 200
    assert r.json() == {"pending": []}

    aid, _ = client.orch.gate.approval_mgr.create("write_file", {"path": "test.txt"})
    r2 = client.get("/api/approvals/pending")
    assert len(r2.json()["pending"]) == 1
    assert r2.json()["pending"][0]["id"] == aid

    # resolve it via post
    r3 = client.post("/api/approve", json={"id": aid, "approved": True})
    assert r3.status_code == 200 and r3.json()["ok"] is True


