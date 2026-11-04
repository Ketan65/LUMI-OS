"""Tests for Phase 4: Model Context Protocol (MCP) Client Layer."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.orchestrator import Orchestrator
from tools.mcp_client import McpBridge, McpManager, McpServerInstance
from tools.registry import ToolRegistry


@pytest.fixture
def mock_mcp_server_script():
    """Creates a temporary stdio FastMCP server script."""
    fd, path = tempfile.mkstemp(suffix=".py", prefix="test_mcp_srv_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write('''
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("demo_service")

@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Adds two integers."""
    return a + b

if __name__ == "__main__":
    mcp.run("stdio")
''')
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


def test_mcp_bridge_lifecycle():
    bridge = McpBridge()
    bridge.start()

    async def simple_task():
        return 42

    res = bridge.run_coro(simple_task(), timeout=5.0)
    assert res == 42
    bridge.stop()


def test_mcp_server_connection_and_tool_execution(mock_mcp_server_script):
    registry = ToolRegistry()
    bridge = McpBridge()
    mgr = McpManager(bridge=bridge)
    mgr.registry = registry

    server = McpServerInstance(
        name="calculator",
        command=sys.executable,
        args=[mock_mcp_server_script],
        enabled=True,
    )
    mgr.servers["calculator"] = server

    ok, msg = mgr.start_server("calculator")
    assert ok is True
    assert "calculator" in msg
    assert server.status == "connected"
    assert len(server.tools) >= 1

    # Check registered tool in ToolRegistry
    reg_tool = registry.get("mcp__calculator__add_numbers")
    assert reg_tool is not None
    assert reg_tool.risk == "ask"  # Must default to ask for safety

    # Execute tool via handler
    result = reg_tool.handler(a=15, b=27)
    assert "42" in result

    # Stop server
    ok_stop, stop_msg = mgr.stop_server("calculator")
    assert ok_stop is True
    assert registry.get("mcp__calculator__add_numbers") is None
    bridge.stop()


def test_mcp_server_handles_failure_gracefully():
    registry = ToolRegistry()
    bridge = McpBridge()
    mgr = McpManager(bridge=bridge)
    mgr.registry = registry

    server = McpServerInstance(
        name="bad_server",
        command="non_existent_executable_12345",
        args=[],
        enabled=True,
    )
    mgr.servers["bad_server"] = server

    ok, msg = mgr.start_server("bad_server")
    assert ok is False
    assert server.status == "error"
    bridge.stop()


def test_orchestrator_mcp_commands():
    orc = Orchestrator(brain=MagicMock())
    _, text = orc.command("/mcp")
    assert "MCP Servers" in text or "config.yaml" in text

    _, desk_text = orc.command("/desktop off")
    assert "Desktop control stopped" in desk_text
