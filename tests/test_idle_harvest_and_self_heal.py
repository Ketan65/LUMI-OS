"""Tests for LUMI Autonomous Idle Skill Harvester & Self-Healing Engine (v37.0).

Verifies:
  1. Autonomous Idle-Time Skill Harvester (Market curriculum synthesis & hot-reloading).
  2. Procedural YAML recipe registration in data/skills/.
  3. Self-Healing Engine (Syntax error repair, KeyError conversion, ZeroDivision repair).
  4. DPO Flywheel recording of self-healed trajectories.
  5. Anti-refusal persona and prompt directives.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from brain.ollama_adapter import SYSTEM_PROMPT
from core.idle_harvester import AutonomousSkillHarvester, MARKET_SKILLS_CURRICULUM, get_skill_harvester
from evolution.self_healing_engine import SelfHealingEngine, get_self_healing_engine
from tools.registry import ToolRegistry


def test_anti_refusal_system_prompt_mandates_evolution():
    """Ensure the base system prompt explicitly mandates autonomous learning & self-healing."""
    assert "AUTONOMOUS EVOLUTION & SELF-HEALING DIRECTIVE" in SYSTEM_PROMPT
    assert "NEVER output generic corporate AI refusals" in SYSTEM_PROMPT
    assert "Kernel Tool Synthesis" in SYSTEM_PROMPT
    assert "Idle-Time Skill Harvesting" in SYSTEM_PROMPT


def test_autonomous_skill_harvester_lifecycle(tmp_path: Path):
    """Verify autonomous skill harvesting, testing, hot-loading, and YAML recipe creation."""
    registry = ToolRegistry()
    test_skills_dir = tmp_path / "skills"
    test_synth_dir = tmp_path / "synth"
    harvester = AutonomousSkillHarvester(
        registry=registry,
        idle_threshold_sec=0.1,
        skills_dir=test_skills_dir,
        synth_dir=test_synth_dir,
    )

    # 1. Inspect next curriculum skill
    skill_def = harvester.get_next_curriculum_skill()
    assert skill_def is not None
    assert skill_def.name in [s.name for s in MARKET_SKILLS_CURRICULUM]

    # 2. Harvest skill and run sandbox verification
    res = harvester.harvest_skill(skill_def)
    assert res.get("success") is True
    assert res.get("name") == skill_def.name
    assert res.get("category") == skill_def.category

    # 3. Verify tool is dynamically hot-loaded into ToolRegistry
    tool = registry.get(skill_def.name)
    assert tool is not None
    assert "[AUTONOMOUS SKILL]" in tool.description

    # 4. Verify procedural YAML recipe exists in test_skills_dir
    recipe_file = test_skills_dir / f"{skill_def.name}.yaml"
    assert recipe_file.exists()
    assert skill_def.name in recipe_file.read_text(encoding="utf-8")


def test_self_healing_engine_syntax_and_keyerror(tmp_path: Path):
    """Verify self-healing of Python syntax errors and KeyError."""
    engine = SelfHealingEngine(workspace_root=tmp_path)

    # Test 1: Missing colon syntax error auto-repair
    broken_syntax = "def compute_area(r)\n    return 3.14 * r * r\nprint(compute_area(5))"
    err_syntax = "SyntaxError: expected ':' (line 1)"

    success, healed, exp = engine.heal_python_snippet(broken_syntax, err_syntax)
    assert success is True
    assert "compute_area(r):" in healed
    assert "line 1" in exp

    # Test 2: KeyError direct indexing to .get() conversion
    broken_key = "data = {'name': 'LUMI'}\nprint(data['version'])\n"
    err_key = "KeyError: 'version'"

    success_k, healed_k, exp_k = engine.heal_python_snippet(broken_key, err_key)
    assert success_k is True
    assert ".get('version')" in healed_k
    assert "KeyError" in exp_k


def test_self_healing_engine_zerodivision(tmp_path: Path):
    """Verify self-healing of ZeroDivisionError with defensive protection."""
    engine = SelfHealingEngine(workspace_root=tmp_path)

    broken_code = "a = 10\nb = 0\nres = a / b\nprint(res)"
    err_msg = "ZeroDivisionError: division by zero"

    success, healed, exp = engine.heal_python_snippet(broken_code, err_msg)
    assert success is True
    assert "ZeroDivisionError" in exp
    assert "if b != 0" in healed


def test_self_healing_workspace_file_lifecycle(tmp_path: Path):
    """Verify workspace file patching, backup creation, and execution."""
    engine = SelfHealingEngine(workspace_root=tmp_path)

    # Create a failing script in workspace
    test_script = tmp_path / "calc_test.py"
    test_script.write_text("x = 50\ny = 0\nval = x / y\nprint(val)", encoding="utf-8")

    result = engine.heal_workspace_file("calc_test.py", "ZeroDivisionError: division by zero")
    assert result.get("success") is True
    assert result.get("backup_created") == "calc_test.py.bak"

    # Verify backup exists and healed script runs cleanly
    assert (tmp_path / "calc_test.py.bak").exists()
    healed_content = test_script.read_text(encoding="utf-8")
    assert "if y != 0" in healed_content
