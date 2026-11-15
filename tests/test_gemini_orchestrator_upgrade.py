"""Verification suite for Gemini/Antigravity-level Orchestrator & File Engine upgrades."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from brain.base import BrainReply
from brain.router import ModelRouter
from core.orchestrator import Orchestrator
from safety.gate import SafetyGate
from tools.files import register_file_tools
from tools.registry import ToolRegistry
from conftest import FakeBrain


def test_fuzzy_edit_file_and_syntax_rollback(tmp_path: Path):
    """Verify CRLF/indentation-tolerant edit_file and AST syntax guard rollback on edit_file & write_file."""
    target = tmp_path / "calc.py"
    target.write_text(
        "class Calculator:\n"
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n",
        encoding="utf-8",
    )

    reg = ToolRegistry()
    register_file_tools(reg, [str(tmp_path)])
    edit_fn = reg.get("edit_file").handler
    write_fn = reg.get("write_file").handler

    # 1. Fuzzy match: wrong indentation & CRLF in target still matches uniquely
    ok_res = edit_fn(
        path=str(target),
        target="def add(self, a: int, b: int) -> int:\r\n  return a + b",
        replacement="    def add(self, a: int, b: int) -> int:\n        return a + b + 1",
    )
    assert ok_res.startswith("File edited successfully:")
    assert "a + b + 1" in target.read_text(encoding="utf-8")

    # 2. Invalid syntax in edit_file must be rolled back without touching original file
    err_edit = edit_fn(
        path=str(target),
        target="return a + b + 1",
        replacement="        return (a + b",
    )
    assert "SyntaxError" in err_edit
    assert "rolled back" in err_edit
    assert "return a + b + 1" in target.read_text(encoding="utf-8")

    # 3. Invalid syntax in write_file overwrite must be rejected
    new_py = tmp_path / "broken.py"
    err_write = write_fn(path=str(new_py), content="def broken(:\n    pass\n")
    assert "SyntaxError" in err_write
    assert "rejected" in err_write
    assert not new_py.exists()


def test_hybrid_router_escalation(tmp_path: Path):
    """Verify /model hybrid toggle stays local on simple turns and escalates on errors/architecture."""
    local_brain = FakeBrain([
        BrainReply(text="local ok"),
        BrainReply(text="local after down"),
    ])
    cloud_brain = FakeBrain([
        BrainReply(text="cloud error fix"),
        BrainReply(text="cloud architect"),
    ])
    router = ModelRouter(
        local=local_brain,
        cloud=cloud_brain,
        config={"router": {"enabled": True, "policy": "prefer_local", "fallback_to_local": True}},
        log_path=str(tmp_path / "brain.log"),
    )

    msg = router.set_policy("hybrid")
    assert "Hybrid Architect Mode" in msg
    assert router.active_policy == "hybrid"

    # Routine short turn -> stays on local
    r_local = router.chat([{"role": "user", "content": "hi lumi"}])
    assert r_local.text == "local ok"
    assert router.last_provider == "ollama"

    # Tool error recovery -> escalates to cloud
    r_err = router.chat([
        {"role": "user", "content": "fix calc.py"},
        {"role": "tool", "content": "Error: Edit rolled back due to Python SyntaxError at line 3"},
    ])
    assert r_err.text == "cloud error fix"
    assert router.last_provider == "nvidia"

    # Architectural keyword -> escalates to cloud
    r_arch = router.chat([{"role": "user", "content": "Please refactor multi-file auth module"}])
    assert r_arch.text == "cloud architect"
    assert router.last_provider == "nvidia"


def test_orchestrator_architect_plan_and_auto_verifier(home: Path, downloads: Path):
    """Verify Orchestrator.plan(), /architect command, and post-edit pytest _auto_verify_edit()."""
    ws = home / "workspace"
    mod_file = ws / "math_mod.py"
    mod_file.write_text("def double(x: int) -> int:\n    return x * 2\n", encoding="utf-8")
    test_file = ws / "test_math_mod.py"
    test_file.write_text(
        "from math_mod import double\n\n"
        "def test_double():\n"
        "    assert double(3) == 6\n",
        encoding="utf-8",
    )

    brain = FakeBrain([
        BrainReply(text="1. Target Files: math_mod.py\n2. Surgical Changes: triple\n3. Edge Cases: 0\n4. Verification: pytest"),
        BrainReply(tool_calls=[{
            "name": "edit_file",
            "args": {
                "path": str(mod_file),
                "target": "return x * 2",
                "replacement": "    return x * 2",
            },
        }]),
        BrainReply(text="All verified!"),
    ])
    mock_rg = MagicMock()
    mock_rg.modules = {"math_mod": {}}
    mock_rg.locate_symbol.return_value = [{"file": "workspace/math_mod.py", "line": 1}]

    allowed = [str(home), str(downloads)]
    cfg = {
        "allowed_paths": allowed,
        "max_iterations": 4,
        "permissions": {"write_file": "auto", "edit_file": "auto"},
    }
    reg = ToolRegistry()
    register_file_tools(reg, allowed)
    orch = Orchestrator(brain=brain, config=cfg, registry=reg, gate=SafetyGate(cfg))
    orch.repo_graph = mock_rg

    # 1. /architect command triggers 4-point blueprint with AST context
    should_exit, arch_out = orch.command("/architect Refactor double helper")
    assert should_exit is False
    assert "Execution Blueprint" in arch_out
    assert "1. Target Files" in arch_out
    mock_rg.locate_symbol.assert_called()

    # 2. edit_file in workspace runs _auto_verify_edit -> pytest PASSED
    turn = orch.run_turn("update math_mod.py")
    assert turn["reply"] == "All verified!"
    tool_msg_content = next(m["content"] for m in orch.session if m.get("role") == "tool")
    assert "[Auto-Verifier] pytest test_math_mod.py: PASSED" in tool_msg_content

    # 3. Direct AST-only validation when no test file exists
    no_test_py = ws / "solo_script.py"
    assert "AST Syntax Validated" in orch._auto_verify_edit("write_file", {"path": str(no_test_py)})
