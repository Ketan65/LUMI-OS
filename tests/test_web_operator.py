"""Unit tests for Phase 11 WEB-OPERATOR (Autonomous Computer & Browser Agent)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest

from core.web_operator import WebOperator, clean_html_to_text, extract_links
from tools.registry import ToolRegistry
from tools.web_operator import register_web_operator_tools
from web.server import create_app


def test_clean_html_to_text():
    raw_html = """
    <html>
      <head><style>body { color: red; }</style></head>
      <body>
        <h1>Welcome to LUMI</h1>
        <script>alert('malicious')</script>
        <p>Autonomous AI operating system &amp; assistant.</p>
      </body>
    </html>
    """
    cleaned = clean_html_to_text(raw_html)
    assert "Welcome to LUMI" in cleaned
    assert "Autonomous AI operating system & assistant." in cleaned
    assert "alert" not in cleaned
    assert "color: red" not in cleaned


def test_extract_links():
    html_sample = """
    <div>
      <a href="/about">About Us</a>
      <a href="https://example.com/docs">Documentation</a>
      <a href="javascript:void(0)">Ignore</a>
      <a href="mailto:test@example.com">Contact</a>
    </div>
    """
    links = extract_links(html_sample, "https://example.com")
    urls = [l["url"] for l in links]
    assert "https://example.com/about" in urls
    assert "https://example.com/docs" in urls
    assert not any("javascript" in u or "mailto" in u for u in urls)


class MockHttpResponse:
    def __init__(self, content: bytes, status: int = 200, headers: dict | None = None):
        self._content = content
        self.status = status
        self.headers = MagicMock()
        self.headers.get_content_charset.return_value = "utf-8"

    def read(self):
        return self._content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@patch("urllib.request.urlopen")
def test_web_operator_fetch_and_summarize(mock_urlopen):
    sample_page = (
        b"<html><head><title>DeepMind News</title></head>"
        b"<body><article><h1>AlphaFold Update</h1><p>Revolutionary biology model deployed.</p>"
        b"<a href='/paper'>Read Paper</a></article></body></html>"
    )
    mock_urlopen.return_value = MockHttpResponse(sample_page)

    op = WebOperator()
    page = op.fetch_page("https://deepmind.google/news")
    assert page.status_code == 200
    assert page.title == "DeepMind News"
    assert "Revolutionary biology" in page.text
    assert len(page.links) == 1

    summary = op.summarize_page("https://deepmind.google/news")
    assert "### 🌐 Web Intelligence: DeepMind News" in summary
    assert "Read Paper" in summary


@patch("urllib.request.urlopen")
def test_web_operator_fetch_error_handling(mock_urlopen):
    mock_urlopen.side_effect = RuntimeError("Connection timeout")
    op = WebOperator()
    page = op.fetch_page("https://invalid-domain.xyz")
    assert page.status_code == 500
    assert "Failed to fetch" in page.text

    summary = op.summarize_page("https://invalid-domain.xyz")
    assert "❌ Could not access" in summary


@patch("urllib.request.urlopen")
def test_web_operator_tech_briefing(mock_urlopen):
    hn_mock = (
        b"<html><head><title>Hacker News</title></head>"
        b"<body><table>"
        b"<a href='https://github.com/fastapi/fastapi'>FastAPI release v0.115</a>"
        b"<a href='https://openai.com/research'>New Reasoning Paradigm</a>"
        b"</table></body></html>"
    )
    mock_urlopen.return_value = MockHttpResponse(hn_mock)

    op = WebOperator()
    briefing = op.fetch_tech_briefing()
    assert "### 📰 LUMI Autonomous Tech Briefing" in briefing
    assert "FastAPI release v0.115" in briefing


def test_tools_registration_and_orchestrator_command():
    from core.orchestrator import Orchestrator

    reg = ToolRegistry()
    mock_orc = Orchestrator(brain=MagicMock())
    op = register_web_operator_tools(reg, mock_orc)
    mock_orc.registry = reg
    mock_orc.web_operator = op

    assert reg.get("browse_page") is not None
    assert reg.get("tech_briefing") is not None

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value = MockHttpResponse(b"<html><head><title>Test</title></head><body>OK</body></html>")

        # Test tool handler
        out = reg.get("browse_page").handler(url="https://example.com")
        assert "Web Intelligence" in out

        # Test /browse command
        _, msg = mock_orc.command("/browse https://example.com")
        assert "Web Intelligence" in msg

        # Test /tech command
        _, msg2 = mock_orc.command("/tech")
        assert "Tech Briefing" in msg2


def test_web_server_browse_routes():
    mock_orc = MagicMock()
    mock_orc.config = {"web": {"auth_token": ""}}
    mock_orc.memory = None

    op = WebOperator()
    mock_orc.web_operator = op

    app = create_app(mock_orc)
    transport = httpx.ASGITransport(app=app)

    with patch("urllib.request.urlopen") as mock_url:
        mock_url.return_value = MockHttpResponse(
            b"<html><head><title>Route Test</title></head><body>Content Body</body></html>"
        )

        async def run_checks():
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
                # Browse
                res = await client.post("/api/web/browse", json={"url": "https://sample.com"})
                assert res.status_code == 200
                data = res.json()
                assert data["title"] == "Route Test"
                assert "Content Body" in data["text"]

                # Tech briefing
                res2 = await client.get("/api/web/tech-briefing")
                assert res2.status_code == 200
                assert "briefing" in res2.json()

        asyncio.run(run_checks())
