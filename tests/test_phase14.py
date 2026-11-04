"""Unit & Integration tests for Phase 14: KERNEL-SYNTHESIS.

Tests:
  - AST code safety validation (blocks os.system, shell=True, permits clean logic)
  - Tool compilation, pytest sandbox isolation, and runtime injection
  - Invocations, benchmarking, and execution telemetry
  - Tool revocation and unregistering from ToolRegistry
  - Persistence and boot restoration
  - Synthesizer tools and FastAPI /api/synthesizer/* endpoints
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from core.synthesizer import ToolSynthesizer
from tools.registry import ToolRegistry
from tools.synthesizer import register_synthesizer_tools
from web.server import create_app


@pytest.fixture
def temp_synth(tmp_path: Path) -> ToolSynthesizer:
    tools_dir = tmp_path / "tools"
    meta_file = tmp_path / "synthesized_tools.json"
    registry = ToolRegistry()
    return ToolSynthesizer(tools_dir=tools_dir, metadata_file=meta_file, registry=registry)


def test_ast_safety_inspection(temp_synth: ToolSynthesizer):
    # 1. Clean valid code
    clean_code = """
def calculate_bmi(weight_kg: float, height_m: float) -> dict:
    bmi = weight_kg / (height_m ** 2)
    return {"bmi": round(bmi, 2)}
"""
    is_safe, msg = temp_synth.validate_code_safety(clean_code)
    assert is_safe is True

    # 2. Syntax error
    bad_syntax = "def broken(:"
    is_safe, msg = temp_synth.validate_code_safety(bad_syntax)
    assert is_safe is False
    assert "Syntax Error" in msg

    # 3. Prohibited os.system
    os_sys_code = """
import os
def dangerous():
    os.system("calc.exe")
"""
    is_safe, msg = temp_synth.validate_code_safety(os_sys_code)
    assert is_safe is False
    assert "Security Violation" in msg

    # 4. Prohibited subprocess with shell=True
    shell_code = """
import subprocess
def run_cmd():
    subprocess.run("dir", shell=True)
"""
    is_safe, msg = temp_synth.validate_code_safety(shell_code)
    assert is_safe is False
    assert "shell=True is prohibited" in msg


def test_forge_tool_sandbox_and_injection(temp_synth: ToolSynthesizer):
    tool_code = """
def word_stats(text: str) -> dict:
    words = text.split()
    chars = len(text)
    return {"word_count": len(words), "char_count": chars}
"""
    test_code = """
from word_stats import word_stats

def test_word_stats():
    res = word_stats("hello world")
    assert res["word_count"] == 2
    assert res["char_count"] == 11
"""
    schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    res = temp_synth.forge_tool(
        tool_name="word_stats",
        description="Calculates word and character counts in text.",
        python_code=tool_code,
        test_code=test_code,
        params_schema=schema,
    )

    assert res["success"] is True
    assert res["tool_name"] == "word_stats"
    assert res["status"] == "ACTIVE"

    # Verify tool is registered in ToolRegistry
    tool = temp_synth.registry.get("word_stats")
    assert tool is not None
    assert tool.name == "word_stats"

    # Invoke tool and verify execution
    output = tool.handler(text="LUMI is sovereign AI")
    assert output["word_count"] == 4
    assert output["char_count"] == 20

    # Verify telemetry recorded
    meta = temp_synth.list_tools()
    assert len(meta) == 1
    assert meta[0]["calls"] == 1
    assert meta[0]["avg_latency_ms"] >= 0


def test_forge_tool_rejection_on_test_failure(temp_synth: ToolSynthesizer):
    tool_code = """
def bad_math(a: int, b: int) -> int:
    return a - b  # Bug intentionally added
"""
    test_code = """
from bad_math import bad_math

def test_bad_math():
    assert bad_math(2, 2) == 4  # Will fail!
"""
    res = temp_synth.forge_tool(
        tool_name="bad_math",
        description="Fails test",
        python_code=tool_code,
        test_code=test_code,
        params_schema={},
    )
    assert res["success"] is False
    assert res["stage"] == "testing"
    assert temp_synth.registry.get("bad_math") is None


def test_benchmark_and_revoke_tool(temp_synth: ToolSynthesizer):
    tool_code = """
def quick_hash(data: str) -> str:
    import hashlib
    return hashlib.sha256(data.encode('utf-8')).hexdigest()
"""
    test_code = """
from quick_hash import quick_hash

def test_quick_hash():
    h = quick_hash("boss")
    assert len(h) == 64
"""
    res = temp_synth.forge_tool(
        tool_name="quick_hash",
        description="SHA256 hash generator",
        python_code=tool_code,
        test_code=test_code,
        params_schema={},
    )
    assert res["success"] is True

    # Benchmark
    bench = temp_synth.benchmark_tool("quick_hash", {"data": "test_string"}, runs=3)
    assert bench["success"] is True
    assert bench["runs"] == 3
    assert bench["avg_ms"] >= 0

    # Revoke tool
    revoked = temp_synth.revoke_tool("quick_hash")
    assert revoked is True
    assert temp_synth.registry.get("quick_hash") is None

    # Status check
    tools = temp_synth.list_tools()
    assert tools[0]["status"] == "REVOKED"


def test_synthesizer_tools_registration(temp_synth: ToolSynthesizer):
    registry = ToolRegistry()
    registered_synth = register_synthesizer_tools(registry, synthesizer=temp_synth)
    assert registered_synth is temp_synth

    assert registry.get("forge_custom_tool") is not None
    assert registry.get("list_synthesized_tools") is not None
    assert registry.get("revoke_synthesized_tool") is not None
    assert registry.get("benchmark_synthesized_tool") is not None

    # Test list_synthesized_tools handler
    list_fn = registry.get("list_synthesized_tools").handler
    assert isinstance(list_fn(), list)


@pytest.mark.asyncio
async def test_synthesizer_web_api(temp_synth: ToolSynthesizer):
    registry = ToolRegistry()
    register_synthesizer_tools(registry, synthesizer=temp_synth)

    mock_orch = MagicMock()
    mock_orch.config = {"web": {"allow_remote": True}}
    mock_orch.registry = registry
    mock_orch.synthesizer = temp_synth

    app = create_app(mock_orch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/synthesizer/tools (empty initial list)
        r = await client.get("/api/synthesizer/tools")
        assert r.status_code == 200
        assert "tools" in r.json()

        # 2. POST /api/synthesizer/forge
        tool_code = "def add_ten(x: int) -> int:\n    return x + 10\n"
        test_code = "from add_ten import add_ten\ndef test_add():\n    assert add_ten(5) == 15\n"
        r = await client.post("/api/synthesizer/forge", json={
            "tool_name": "add_ten",
            "description": "Adds 10 to a number",
            "python_code": tool_code,
            "test_code": test_code,
            "params_schema": {"type": "object", "properties": {"x": {"type": "integer"}}}
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert data["tool_name"] == "add_ten"

        # 3. POST /api/synthesizer/benchmark
        r = await client.post("/api/synthesizer/benchmark", json={
            "tool_name": "add_ten",
            "sample_args": {"x": 20},
            "runs": 2
        })
        assert r.status_code == 200
        bench = r.json()
        assert bench["success"] is True
        assert bench["avg_ms"] >= 0

        # 4. POST /api/synthesizer/revoke
        r = await client.post("/api/synthesizer/revoke", json={"tool_name": "add_ten"})
        assert r.status_code == 200
        assert r.json()["success"] is True
