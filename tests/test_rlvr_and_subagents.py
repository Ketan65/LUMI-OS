"""Tests for Secret #1 (RLVR Verifiable-Reward Engine) & Secret #3 (Context-Isolated Subagents + Reactive Wakeup)."""

from __future__ import annotations

import time
from pathlib import Path

import core.mission_queue as mq_mod
from brain.base import BrainReply
from conftest import FakeBrain
from core.orchestrator import Orchestrator
from core.subagents import MAX_SUMMARY_CHARS, SubagentRunner, register_subagent_tools
from evolution.dpo_flywheel import DPOFlywheel, register_dpo_flywheel_tools
from safety.gate import SafetyGate
from tools.files import register_file_tools
from tools.mission_queue import register_mission_queue_tools
from tools.registry import Tool, ToolRegistry


def test_rlvr_trajectory_recording_stats_and_export(tmp_path: Path):
    """Verify deterministic +1.0/-1.0 RLVR rewards, stats computation, and GRPO JSONL export."""
    flywheel = DPOFlywheel(
        dataset_path=tmp_path / "dpo.jsonl",
        rlvr_path=tmp_path / "rlvr.jsonl",
    )

    r1 = flywheel.record_rlvr_trajectory(
        prompt="write adder",
        tool_name="write_file",
        args={"path": "workspace/calc.py"},
        verifier_output="[Auto-Verifier] pytest test_calc.py: PASSED",
        passed=True,
    )
    r2 = flywheel.record_rlvr_trajectory(
        prompt="fix subtractor",
        tool_name="edit_file",
        args={"path": "workspace/calc.py"},
        verifier_output="[Auto-Verifier] pytest test_calc.py: FAILED",
        passed=False,
    )
    assert r1["reward"] == 1.0
    assert r2["reward"] == -1.0

    stats = flywheel.get_rlvr_stats()
    assert stats["total_trajectories"] == 2
    assert stats["passed_count"] == 1
    assert stats["failed_count"] == 1
    assert stats["pass_rate_pct"] == 50.0
    assert stats["mean_reward"] == 0.0
    assert stats["ready_for_grpo"] is False

    export_file = tmp_path / "grpo_export.jsonl"
    exp = flywheel.export_rlvr_grpo_dataset(output_path=export_file)
    assert exp["exported_count"] == 2
    assert export_file.is_file()


def test_orchestrator_records_rlvr_after_verified_write_and_slash_cmd(home: Path, downloads: Path, tmp_path: Path):
    """Verify Orchestrator records RLVR trajectory automatically after verified write_file and /rlvr reports it."""
    ws = home / "workspace"
    mod_file = ws / "greeter.py"
    test_file = ws / "test_greeter.py"
    test_file.write_text(
        "from greeter import greet\n\n"
        "def test_greet():\n"
        "    assert greet('LUMI') == 'Hello, LUMI'\n",
        encoding="utf-8",
    )

    allowed = [str(home), str(downloads)]
    cfg = {
        "allowed_paths": allowed,
        "max_iterations": 4,
        "permissions": {"write_file": "auto", "edit_file": "auto"},
    }
    reg = ToolRegistry()
    register_file_tools(reg, allowed)
    flywheel = DPOFlywheel(
        dataset_path=tmp_path / "dpo.jsonl",
        rlvr_path=tmp_path / "rlvr.jsonl",
    )
    # Also register tools via a fresh registry check + wire flywheel directly onto orchestrator
    register_dpo_flywheel_tools(reg, dataset_path=tmp_path / "dpo.jsonl")

    brain = FakeBrain([
        BrainReply(tool_calls=[{
            "name": "write_file",
            "args": {
                "path": str(mod_file),
                "content": "def greet(name: str) -> str:\n    return f'Hello, {name}'\n",
            },
        }]),
        BrainReply(text="Greeter module written and verified."),
    ])
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    orch.dpo_flywheel = flywheel

    turn = orch.run_turn("create greeter module")
    assert turn["reply"] == "Greeter module written and verified."

    stats = flywheel.get_rlvr_stats()
    assert stats["total_trajectories"] == 1
    assert stats["passed_count"] == 1
    assert stats["mean_reward"] == 1.0

    # When registry tool is unregistered or queried directly via flywheel fallback, /rlvr formats stats
    reg.unregister("rlvr_gym_status")
    should_exit, rlvr_msg = orch.command("/rlvr")
    assert should_exit is False
    assert "'total_trajectories': 1" in rlvr_msg


def test_subagent_context_isolation_and_summary_cap(home: Path, downloads: Path):
    """Verify SubagentRunner executes multi-step research without mutating parent Orchestrator.session."""
    ws = home / "workspace"
    (ws / "alpha.py").write_text("# alpha module\nVALUE = 42\n", encoding="utf-8")

    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4}
    reg = ToolRegistry()
    register_file_tools(reg, allowed)

    sub_brain = FakeBrain([
        BrainReply(tool_calls=[{"name": "list_files", "args": {"path": str(ws)}}]),
        BrainReply(tool_calls=[{"name": "read_file", "args": {"path": str(ws / "alpha.py")}}]),
        BrainReply(text="A" * 2000),  # Verify summary cap truncates cleanly to <= MAX_SUMMARY_CHARS
    ])
    parent_brain = FakeBrain([BrainReply(text="parent ok")])
    orch = Orchestrator(brain=parent_brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    orch.run_turn("initial parent message")
    initial_session_len = len(orch.session)
    assert initial_session_len == 2

    runner = SubagentRunner(orchestrator=orch, brain=sub_brain, registry=reg)
    res = runner.run_subagent(role="research", task="Inspect workspace alpha.py")

    assert res["role"] == "research"
    assert res["steps_taken"] == 3
    assert res["tools_used"] == ["list_files", "read_file"]
    assert len(res["summary"]) <= MAX_SUMMARY_CHARS
    # Critical check: parent Orchestrator.session MUST remain untouched!
    assert len(orch.session) == initial_session_len


def test_subagent_tool_registration_and_slash_command(home: Path, downloads: Path):
    """Verify invoke_subagent tool and /subagent slash command execute cleanly."""
    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4}
    reg = ToolRegistry()
    register_file_tools(reg, allowed)

    brain = FakeBrain([
        BrainReply(text="Distilled scout summary: all checks nominal."),
        BrainReply(text="Distilled slash summary: verified."),
    ])
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    orch.subagent_runner = register_subagent_tools(reg, orchestrator=orch)

    tool = reg.get("invoke_subagent")
    assert tool is not None
    out = tool.handler(role="scout", task="Summarize workspace")
    assert "Subagent [SCOUT]" in out
    assert "all checks nominal" in out

    should_exit, cmd_out = orch.command("/subagent research Check repo")
    assert should_exit is False
    assert "Subagent [RESEARCH]" in cmd_out


def test_reactive_background_mission_wakeup(home: Path, downloads: Path, tmp_path: Path, monkeypatch):
    """Verify AsyncMissionQueue completion pushes wakeup notification drained on next Orchestrator turn."""
    monkeypatch.setattr(mq_mod, "MISSIONS_STATE_PATH", tmp_path / "missions_state.json")
    monkeypatch.setattr(mq_mod, "_GLOBAL_QUEUE", None)

    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4}
    reg = ToolRegistry()
    brain = FakeBrain([BrainReply(text="Acknowledged background mission result.")])
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))

    queue = register_mission_queue_tools(reg, orchestrator=orch, workspace_root=home / "workspace", brain=brain)
    try:
        record = queue.submit_mission(
            name="Index docs",
            kind="dag",
            fn=lambda: "Indexed 12 files cleanly.",
        )
        # Wait briefly for fast background worker to finish and fire on_complete
        deadline = time.time() + 3.0
        while time.time() < deadline and not orch._wakeup_inbox:
            time.sleep(0.02)

        assert len(orch._wakeup_inbox) == 1
        assert orch._wakeup_inbox[0]["mission_id"] == record["mission_id"]

        events = list(orch.run_turn_stream("status?"))
        wakeup_events = [e for e in events if e.get("type") == "wakeup"]
        assert len(wakeup_events) == 1
        assert wakeup_events[0]["notifications"][0]["mission_id"] == record["mission_id"]

        # Inbox must be drained and injected into user turn message
        assert orch._wakeup_inbox == []
        user_msgs = [m["content"] for m in orch.session if m.get("role") == "user"]
        assert any("[BACKGROUND TASK WAKEUP]" in c and "Indexed 12 files cleanly." in c for c in user_msgs)
    finally:
        queue.shutdown(wait=True)
        monkeypatch.setattr(mq_mod, "_GLOBAL_QUEUE", None)


def test_tool_failure_retry_regression(home: Path, downloads: Path):
    """Regression test: failing tool hits retry handler after _auto_verify_edit placement fix."""
    def exploding_tool() -> str:
        raise RuntimeError("boom on purpose")

    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4, "permissions": {"boom": "auto"}}
    reg = ToolRegistry()
    reg.register(Tool("boom", "Fails on execution", {"type": "object", "properties": {}}, exploding_tool, risk="auto"))

    brain = FakeBrain([
        BrainReply(tool_calls=[{"name": "boom", "args": {}}]),
        BrainReply(text="Recovered gracefully."),
    ])
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    turn = orch.run_turn("run boom")
    assert turn["reply"] == "Recovered gracefully."
    tool_msgs = [m["content"] for m in orch.session if m.get("role") == "tool"]
    assert any("fix & retry kar sakte ho (1 chance left)" in msg for msg in tool_msgs)


def test_automatic_activation_on_normal_task(home: Path, downloads: Path):
    """Verify ReflexRouter retains invoke_subagent and Orchestrator auto-injects AST context on normal tasks."""
    from unittest.mock import MagicMock
    from core.reflex_router import ReflexRouter

    router = ReflexRouter()
    mock_specs = [
        {"type": "function", "function": {"name": f"dummy_tool_{i}", "description": f"Generic helper {i}"}}
        for i in range(60)
    ] + [
        {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
        {"type": "function", "function": {"name": "invoke_subagent", "description": "Isolated subagent"}},
    ]
    pruned = router.select_relevant_tools("Refactor authentication module", mock_specs, top_k=14)
    selected_names = {t["function"]["name"] for t in pruned}
    assert "invoke_subagent" in selected_names

    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4}
    reg = ToolRegistry()
    brain = FakeBrain([BrainReply(text="Refactored double cleanly.")])
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    mock_rg = MagicMock()
    mock_rg.modules = {"math_mod": {}}
    mock_rg.locate_symbol.return_value = [{"file": "workspace/math_mod.py", "line": 1}]
    orch.repo_graph = mock_rg

    turn = orch.run_turn("Refactor double function in math_mod.py")
    assert turn["reply"] == "Refactored double cleanly."
    mock_rg.locate_symbol.assert_called()
    user_msgs = [m["content"] for m in orch.session if m.get("role") == "user"]
    assert any("[AUTO-ARCHITECT AST CONTEXT]" in msg and "workspace/math_mod.py" in msg for msg in user_msgs)
