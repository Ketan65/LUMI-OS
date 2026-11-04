"""Unit & Integration tests for Phase 3: Web search/read, Python sandbox, and Disk report."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.orchestrator import Orchestrator
from safety.gate import SafetyGate
from tools.cleanup import format_bytes, make_disk_reporter, register_cleanup_tools
from tools.registry import ToolRegistry
from tools.sandbox import make_python_runner, register_sandbox_tools
from tools.web import (
    is_safe_web_url,
    register_web_tools,
    web_read,
    web_search,
)


# --- 1. Web Security & Tools ---

def test_is_safe_web_url_blocks_ssrf_and_invalid_schemes():
    # Schemes
    assert not is_safe_web_url("ftp://example.com")[0]
    assert not is_safe_web_url("file:///etc/passwd")[0]
    assert not is_safe_web_url("javascript:alert(1)")[0]

    # Localhost / loopback / private
    assert not is_safe_web_url("http://localhost:8000")[0]
    assert not is_safe_web_url("http://127.0.0.1:8765")[0]
    assert not is_safe_web_url("http://0.0.0.0:80")[0]

    # Valid public domain
    safe, msg = is_safe_web_url("https://example.com")
    assert safe is True
    assert msg == ""


def test_web_search_empty_query():
    out = web_search("")
    assert "cannot be empty" in out


def test_web_search_formatting():
    fake_results = [
        {"title": "Python Docs", "href": "https://docs.python.org", "body": "Official documentation."},
        {"title": "Python PEPs", "href": "https://peps.python.org", "body": "Python enhancement proposals."},
    ]

    with patch("duckduckgo_search.DDGS") as mock_ddgs_cls:
        mock_instance = MagicMock()
        mock_instance.__enter__.return_value = mock_instance
        mock_instance.text.return_value = fake_results
        mock_ddgs_cls.return_value = mock_instance

        res = web_search("python docs", max_results=2)
        assert "Search results for: 'python docs'" in res
        assert "[1] Python Docs" in res
        assert "https://docs.python.org" in res
        assert "Official documentation." in res
        assert "[2] Python PEPs" in res


def test_web_read_blocks_ssrf():
    res = web_read("http://127.0.0.1/sensitive")
    assert "Security blocked URL" in res


def test_web_read_extracts_html():
    html_sample = """
    <!DOCTYPE html>
    <html>
      <head><title>Test Article Title</title></head>
      <body>
        <nav><a href="/">Home</a></nav>
        <script>console.log("bad");</script>
        <h1>Main Heading</h1>
        <p>This is the first paragraph with vital information.</p>
        <p>This is the second paragraph.</p>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """

    fake_resp = MagicMock()
    fake_resp.text = html_sample
    fake_resp.headers = {"content-type": "text/html; charset=utf-8"}
    fake_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.get.return_value = fake_resp
        mock_client_cls.return_value = mock_client

        out = web_read("https://example.com/test")
        assert "Test Article Title" in out
        assert "Main Heading" in out
        assert "first paragraph with vital information" in out
        assert "console.log" not in out
        assert "Copyright 2026" not in out


# --- 2. Sandbox (run_python) ---

def test_run_python_simple_execution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = make_python_runner(tmp_dir)
        res = runner("print(35 * 2)")
        assert "[Exit code: 0]" in res
        assert "70" in res


def test_run_python_cwd_is_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = make_python_runner(tmp_dir)
        res = runner("import os; print(os.path.realpath(os.getcwd()))")
        assert "[Exit code: 0]" in res
        assert str(Path(tmp_dir).resolve()).lower() in res.lower()


def test_run_python_error_handling():
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = make_python_runner(tmp_dir)
        res = runner("raise ValueError('something went wrong')")
        assert "[Exit code: 1 (Failed)]" in res
        assert "ValueError: something went wrong" in res


def test_run_python_timeout():
    with tempfile.TemporaryDirectory() as tmp_dir:
        runner = make_python_runner(tmp_dir)
        with patch("tools.sandbox.DEFAULT_TIMEOUT_SEC", 0.5):
            res = runner("import time; time.sleep(2)")
            assert "timed out after" in res


# --- 3. Disk Report ---

def test_format_bytes():
    assert format_bytes(500) == "500 B"
    assert "1.0 KB" in format_bytes(1024)
    assert "1.0 MB" in format_bytes(1024 * 1024)
    assert "1.5 GB" in format_bytes(int(1.5 * 1024 * 1024 * 1024))


def test_disk_report_scans_correctly():
    with tempfile.TemporaryDirectory() as tmp_dir:
        base = Path(tmp_dir)
        sub1 = base / "sub1"
        sub1.mkdir()
        f1 = sub1 / "file1.txt"
        f1.write_text("a" * 5000, encoding="utf-8")

        f2 = base / "file2.txt"
        f2.write_text("b" * 2000, encoding="utf-8")

        reporter = make_disk_reporter(base)
        report = reporter()

        assert "Disk Report for:" in report
        assert "Largest Files:" in report
        assert "file1.txt" in report
        assert "file2.txt" in report
        assert "sub1/" in report


# --- 4. Orchestrator Integration & Safety ---

def test_web_search_taints_turn_and_wraps_untrusted():
    registry = ToolRegistry()
    register_web_tools(registry)

    # Fake brain that calls web_search once, then finishes
    class FakeBrain:
        def __init__(self):
            self.turn = 0
            self.last_model = "test-brain"
        def chat(self, session, tools=None, on_token=None):
            self.turn += 1
            if self.turn == 1:
                call = {"name": "web_search", "args": {"query": "python"}, "type": "function"}
                reply = MagicMock()
                reply.text = ""
                reply.tool_calls = [call]
                return reply
            reply = MagicMock()
            reply.text = "Here is the web result."
            reply.tool_calls = []
            return reply

    brain = FakeBrain()
    tool = registry.get("web_search")
    assert tool is not None
    tool.handler = MagicMock(return_value="Sample python info")
    orc = Orchestrator(brain=brain, registry=registry)

    result = orc.run_turn("search python")
    assert result["reply"] == "Here is the web result."

    # Check tool message in session was tainted & wrapped
    tool_msgs = [m for m in orc.session if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert '<untrusted source="web_search">' in tool_msgs[0]["content"]
    assert "Sample python info" in tool_msgs[0]["content"]


def test_run_python_requires_approval():
    registry = ToolRegistry()
    with tempfile.TemporaryDirectory() as tmp_dir:
        register_sandbox_tools(registry, tmp_dir)
        tool = registry.get("run_python")
        assert tool is not None
        assert tool.risk == "ask"

        gate = SafetyGate({"permissions": {"run_python": "ask"}})
        verdict, reason = gate.check("run_python", tool.risk)
        assert verdict == "ask"
