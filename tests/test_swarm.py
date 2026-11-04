"""Unit tests for Phase 9 SWARM-DEV (Autonomous Multi-Agent Software Engineering Team)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.swarm import (
    ArchitectAgent,
    CoderAgent,
    DebuggerAgent,
    SwarmCoordinator,
    SwarmFileSpec,
    SwarmProjectSpec,
    TesterAgent,
    extract_code_block,
    extract_json_object,
)
from tools.registry import ToolRegistry
from tools.swarm import register_swarm_tools


class DummyReply:
    def __init__(self, text: str):
        self.text = text


def test_extract_code_and_json_helpers():
    code_md = "```python\ndef hello():\n    return 42\n```"
    assert "def hello():" in extract_code_block(code_md)

    json_md = '```json\n{"project_name": "calc", "files": []}\n```'
    parsed = extract_json_object(json_md)
    assert parsed is not None
    assert parsed["project_name"] == "calc"


def test_architect_agent_with_brain_and_fallback(tmp_path: Path):
    architect = ArchitectAgent()

    # Test with mock brain returning JSON
    brain = MagicMock()
    spec_json = {
        "project_name": "prime_finder",
        "overview": "Finds prime numbers efficiently",
        "tech_stack": ["python"],
        "files": [
            {"path": "primes.py", "description": "Prime logic", "type": "code"},
            {"path": "test_primes.py", "description": "Unit tests", "type": "test"},
        ],
    }
    brain.chat.return_value = DummyReply(json.dumps(spec_json))
    spec = architect.design("Build prime finder", brain)

    assert spec.project_name == "prime_finder"
    assert len(spec.files) == 2
    assert spec.files[0].path == "primes.py"

    # Test fallback when brain fails
    brain.chat.side_effect = RuntimeError("Brain offline")
    spec_fallback = architect.design("Build matrix multiplier", brain)
    assert spec_fallback.project_name is not None
    assert len(spec_fallback.files) >= 2


def test_coder_agent_generates_files(tmp_path: Path):
    coder = CoderAgent()
    brain = MagicMock()
    brain.chat.return_value = DummyReply("```python\ndef add(a, b):\n    return a + b\n```")

    project_dir = tmp_path / "math_app"
    project_dir.mkdir()

    file_spec = SwarmFileSpec(path="math_utils.py", description="Math utility functions", type="code")
    proj_spec = SwarmProjectSpec(
        project_name="math_app",
        overview="Math tools",
        tech_stack=["python"],
        files=[file_spec],
    )

    out_file = coder.code_file(project_dir, file_spec, proj_spec, brain)
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "def add(a, b):" in content


def test_tester_agent_pass_and_fail(tmp_path: Path):
    tester = TesterAgent()
    project_dir = tmp_path / "test_run"
    project_dir.mkdir()

    # Case 1: Passing test
    test_code = (
        "import unittest\n\n"
        "class TestPass(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertEqual(1 + 1, 2)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    (project_dir / "test_pass.py").write_text(test_code, encoding="utf-8")

    passed, out = tester.run_tests(project_dir)
    assert passed is True
    assert "Ran 1 test" in out or "OK" in out

    # Case 2: Failing test
    fail_code = (
        "import unittest\n\n"
        "class TestFail(unittest.TestCase):\n"
        "    def test_bad(self):\n"
        "        self.assertEqual(1 + 1, 999)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )
    (project_dir / "test_pass.py").write_text(fail_code, encoding="utf-8")

    passed2, out2 = tester.run_tests(project_dir)
    assert passed2 is False


def test_debugger_agent_heals_code(tmp_path: Path):
    debugger = DebuggerAgent()
    brain = MagicMock()
    # Debugger returns fixed implementation
    brain.chat.return_value = DummyReply("```python\ndef solve():\n    return 100\n```")

    project_dir = tmp_path / "debug_run"
    project_dir.mkdir()
    buggy_file = project_dir / "solver.py"
    buggy_file.write_text("def solve():\n    return 0\n", encoding="utf-8")

    spec = SwarmProjectSpec(
        project_name="debug_run",
        overview="Debug test",
        tech_stack=["python"],
        files=[SwarmFileSpec(path="solver.py", description="Solver", type="code")],
    )

    healed = debugger.heal(project_dir, "solver.py: assertion error 0 != 100", spec, brain)
    assert "solver.py" in healed
    assert "return 100" in buggy_file.read_text(encoding="utf-8")


def test_swarm_coordinator_end_to_end(tmp_path: Path):
    brain = MagicMock()
    # Architect reply
    arch_json = {
        "project_name": "greeter",
        "overview": "Greeting system",
        "tech_stack": ["python"],
        "files": [
            {"path": "greeter.py", "description": "Greeter function", "type": "code"},
            {"path": "test_greeter.py", "description": "Tests", "type": "test"},
        ],
    }
    # Coder replies
    def mock_chat(messages, **kwargs):
        role_prompt = messages[0]["content"]
        if "Architect" in role_prompt:
            return DummyReply(json.dumps(arch_json))
        if "Senior Software Engineer" in role_prompt:
            user_msg = messages[1]["content"]
            if "File to implement: test_greeter.py" in user_msg:
                return DummyReply(
                    "```python\nimport unittest\nfrom greeter import greet\n\n"
                    "class TestGreet(unittest.TestCase):\n"
                    "    def test_g(self):\n"
                    "        self.assertEqual(greet('LUMI'), 'Hello LUMI')\n\n"
                    "if __name__ == '__main__':\n"
                    "    unittest.main()\n```"
                )
            return DummyReply("```python\ndef greet(name):\n    return f'Hello {name}'\n```")
        return DummyReply("OK")

    brain.chat.side_effect = mock_chat

    coordinator = SwarmCoordinator(workspace_root=tmp_path, brain=brain)
    result = coordinator.develop(goal="Build greeting module")

    assert result["ok"] is True
    assert result["project_name"] == "greeter"
    assert "greeter.py" in result["files"]
    assert "test_greeter.py" in result["files"]
    assert (tmp_path / "greeter" / "greeter.py").exists()
    assert "LUMI SWARM-DEV" in result["summary"]


def test_register_swarm_tools_and_execution(tmp_path: Path):
    reg = ToolRegistry()
    mock_orc = MagicMock()
    mock_brain = MagicMock()
    mock_brain.chat.return_value = DummyReply(
        json.dumps({
            "project_name": "mini_tool",
            "overview": "Mini test tool",
            "tech_stack": ["python"],
            "files": [
                {"path": "app.py", "description": "App", "type": "code"},
                {"path": "test_app.py", "description": "Tests", "type": "test"},
            ],
        })
    )
    mock_orc.brain = mock_brain

    register_swarm_tools(reg, mock_orc, workspace_root=tmp_path)
    tool = reg.get("swarm_develop")
    assert tool is not None
    assert tool.name == "swarm_develop"

    # Empty goal validation
    empty_res = tool.handler(project_goal="")
    assert "Please provide a valid" in empty_res

    # Real run
    out = tool.handler(project_goal="Create a mini tool")
    assert "LUMI SWARM-DEV" in out


def test_orchestrator_swarm_command(tmp_path: Path):
    from core.orchestrator import Orchestrator
    brain = MagicMock()
    brain.chat.return_value = DummyReply(
        json.dumps({
            "project_name": "cmd_test",
            "overview": "Command test",
            "tech_stack": ["python"],
            "files": [
                {"path": "app.py", "description": "App", "type": "code"},
                {"path": "test_app.py", "description": "Tests", "type": "test"},
            ],
        })
    )
    orc = Orchestrator(brain=brain)
    # Missing args
    should_exit, msg = orc.command("/swarm")
    assert should_exit is False
    assert "usage: /swarm" in msg

    # Valid run
    should_exit, msg2 = orc.command("/swarm Build a simple test tool")
    assert should_exit is False
    assert "LUMI SWARM-DEV" in msg2


def test_web_swarm_endpoint():
    import asyncio
    import httpx
    from web.server import create_app
    mock_orc = MagicMock()
    mock_brain = MagicMock()
    mock_brain.chat.return_value = DummyReply(
        json.dumps({
            "project_name": "api_test",
            "overview": "API test",
            "tech_stack": ["python"],
            "files": [
                {"path": "app.py", "description": "App", "type": "code"},
                {"path": "test_app.py", "description": "Tests", "type": "test"},
            ],
        })
    )
    mock_orc.brain = mock_brain
    mock_orc.config = {"web": {"auth_token": ""}}
    mock_orc.memory = None

    app = create_app(mock_orc)
    transport = httpx.ASGITransport(app=app)

    async def run_checks():
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            res_err = await client.post("/api/swarm", json={"goal": "  "})
            assert res_err.status_code == 400

            res_ok = await client.post("/api/swarm", json={"goal": "Build an API test script", "project_name": "api_test"})
            assert res_ok.status_code == 200
            data = res_ok.json()
            assert data["project_name"] == "api_test"
            assert "summary" in data

    asyncio.run(run_checks())

