"""Tests for Phase 3 BRAIN: Autonomous Goal Planning & Multi-Step Execution."""

from unittest.mock import MagicMock

from core.planner import decompose_goal, execute_goal, extract_json_array
from tools.planner import register_planner_tools
from tools.registry import Tool, ToolRegistry


def test_extract_json_array_raw():
    text = '[{"step": 1, "title": "Test step", "tool": "test", "args": {}}]'
    res = extract_json_array(text)
    assert res is not None
    assert len(res) == 1
    assert res[0]["step"] == 1


def test_extract_json_array_markdown():
    text = '```json\n[{"step": 1, "title": "Write code", "tool": "write_file", "args": {"path": "a.py"}}]\n```'
    res = extract_json_array(text)
    assert res is not None
    assert len(res) == 1
    assert res[0]["tool"] == "write_file"


def test_extract_json_array_invalid():
    text = "Sorry, I cannot plan that."
    res = extract_json_array(text)
    assert res is None


def test_decompose_goal_fallback():
    mock_brain = MagicMock()
    mock_brain.chat.side_effect = Exception("LLM unavailable")
    steps = decompose_goal("create a python script to calculate primes", mock_brain)
    assert len(steps) >= 1
    assert steps[0]["tool"] == "run_python"


def test_execute_goal_success():
    reg = ToolRegistry()
    reg.register(Tool(name="step_one", description="1", params_schema={}, handler=lambda: "file created", risk="auto"))
    reg.register(Tool(name="step_two", description="2", params_schema={}, handler=lambda: "test passed", risk="auto"))

    mock_orch = MagicMock()
    mock_orch.registry = reg

    mock_brain = MagicMock()
    mock_reply = MagicMock()
    mock_reply.text = '[{"step": 1, "title": "Create", "tool": "step_one", "args": {}}, {"step": 2, "title": "Verify", "tool": "step_two", "args": {}}]'
    mock_brain.chat.return_value = mock_reply
    mock_orch.brain = mock_brain

    res = execute_goal("Build and test feature", mock_orch)
    assert "Autonomous Goal Execution" in res
    assert "Step 1: `Create` — ✅ Succeeded" in res
    assert "Step 2: `Verify` — ✅ Succeeded" in res
    assert "Goal Completed Successfully" in res


def test_register_planner_tools():
    reg = ToolRegistry()
    mock_orch = MagicMock()
    register_planner_tools(reg, mock_orch)
    tool = reg.get("execute_goal")
    assert tool is not None
    assert tool.risk == "auto"
    assert "goal" in tool.params_schema["properties"]
