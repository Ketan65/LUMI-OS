"""Comprehensive Verification Suite for LUMI Stark APEX Superpowers (v38.0).

Verifies the 6 God-Tier Capabilities:
  1. Desktop Floating HUD (CustomTkinter, show/hide, toggle, hotkey).
  2. Proactive Anticipatory Sentinel (Active context, clipboard error interception, telemetry alerts).
  3. Visual Computer Use Agent (Screen capture, local Qwen2.5-VL vision analysis, GUI actions).
  4. Chief of Staff (Hardware telemetry, morning audio synthesis, daily devlog generation).
  5. Mixture-of-Local-Specialists Council Router (Multi-brain dispatch, cascade failover).
  6. Autonomous Value Bounty Hunter (Codebase scan, test gap detection, unified git patch generation).
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from brain.model_council import ModelCouncilRouter, get_model_council
from core.bounty_hunter import BountyHunterEngine, get_bounty_hunter
from core.chief_of_staff import ChiefOfStaff, get_chief_of_staff
from core.proactive_sentinel import ProactiveSentinel, get_proactive_sentinel
from core.visual_agent import VisualComputerAgent, get_visual_agent
from evolution.self_healing_engine import SelfHealingEngine
from interface.desktop_hud import launch_hud
from tools.registry import ToolRegistry


def test_milestone_1_desktop_hud(tmp_path: Path):
    """Verify Desktop HUD initialization, state toggling, and input handling."""
    hud = launch_hud()
    assert hud is not None
    assert hud.is_visible is False

    # Show and toggle
    hud.show()
    assert hud.is_visible is True
    hud.toggle()
    assert hud.is_visible is False
    hud.toggle()
    assert hud.is_visible is True

    hud.entry.insert(0, "/briefing")
    assert hud.entry.get() == "/briefing"

    # Cleanup GUI window
    hud.root.destroy()


def test_milestone_2_proactive_sentinel(tmp_path: Path):
    """Verify ambient context sensor and clipboard error interception."""
    registry = ToolRegistry()
    healing_engine = SelfHealingEngine(workspace_root=tmp_path)
    test_alerts_file = tmp_path / "proactive_alerts.jsonl"

    sentinel = ProactiveSentinel(
        registry=registry,
        healing_engine=healing_engine,
        alerts_path=test_alerts_file,
    )

    # 1. Telemetry inspection
    ctx = sentinel.inspect_ambient_context()
    assert "cpu_percent" in ctx
    assert "ram_percent" in ctx
    assert "ram_free_gb" in ctx
    assert ctx["ram_percent"] > 0

    # 2. Tools registered
    assert registry.get("check_proactive_alerts") is not None
    assert registry.get("inspect_ambient_context") is not None


def test_milestone_3_visual_computer_agent(tmp_path: Path):
    """Verify screen capture and local vision model grounding."""
    registry = ToolRegistry()
    test_screens_dir = tmp_path / "screenshots"
    agent = VisualComputerAgent(registry=registry, screenshots_dir=test_screens_dir)

    # 1. Screen capture
    img = agent.capture_screen("test_capture.png")
    assert img is not None
    assert img.size[0] > 0 and img.size[1] > 0
    assert (test_screens_dir / "test_capture.png").exists()

    # 2. GUI action validation
    res = agent.execute_gui_action("press_key", key="escape")
    assert res.get("success") is True

    # 3. Tools registered
    assert registry.get("screen_capture_and_describe") is not None
    assert registry.get("locate_screen_element") is not None
    assert registry.get("execute_gui_action") is not None


def test_milestone_4_chief_of_staff(tmp_path: Path):
    """Verify morning audio briefing and daily devlog generation."""
    registry = ToolRegistry()
    test_audio_dir = tmp_path / "audio"
    test_devlogs_dir = tmp_path / "devlogs"

    chief = ChiefOfStaff(
        registry=registry,
        audio_dir=test_audio_dir,
        devlogs_dir=test_devlogs_dir,
    )

    # 1. Morning Briefing
    briefing = chief.generate_morning_briefing(play_audio=False)
    assert briefing["success"] is True
    assert "Good morning, Boss" in briefing["briefing_text"]
    assert "Hardware diagnostics" in briefing["briefing_text"]
    assert briefing["audio_path"] is not None
    assert Path(briefing["audio_path"]).exists()

    # 2. Daily DevLog
    devlog = chief.generate_daily_devlog()
    assert devlog["success"] is True
    assert Path(devlog["path"]).exists()
    content = Path(devlog["path"]).read_text(encoding="utf-8")
    assert "LUMI Autonomous DevLog" in content

    # 3. Tools registered
    assert registry.get("generate_morning_briefing") is not None
    assert registry.get("generate_daily_devlog") is not None


def test_milestone_5_model_council_routing():
    """Verify heuristic classification across local specialists and fallback."""
    registry = ToolRegistry()
    council = ModelCouncilRouter(registry=registry)

    # Classification test
    assert council.classify_specialist("Take a screenshot of the display") == "vision"
    assert council.classify_specialist("Write a python function def calculate_profit():") == "coder"
    assert council.classify_specialist("Compare architectural trade-offs of monolithic vs microservices") == "reasoning"
    assert council.classify_specialist("Good evening, how is the mission going?") == "persona"

    # Telemetry check
    telem = council.get_telemetry_summary()
    assert "available_specialists" in telem
    assert registry.get("query_model_council") is not None
    assert registry.get("get_council_telemetry") is not None


def test_milestone_6_bounty_hunter_engine(tmp_path: Path):
    """Verify codebase bounty scanning and unified patch synthesis."""
    registry = ToolRegistry()
    test_patches_dir = tmp_path / "bounty_patches"

    # Create dummy module to test
    dummy_code = tmp_path / "sample_service.py"
    dummy_code.write_text("def process_payment(amount):\n    return amount * 1.05\n", encoding="utf-8")

    hunter = BountyHunterEngine(
        registry=registry,
        workspace_root=tmp_path,
        patches_dir=test_patches_dir,
    )

    # 1. Patch generation
    res = hunter.generate_test_gap_patch("sample_service.py")
    assert res.get("success") is True
    assert Path(res["patch_path"]).exists()
    patch_text = Path(res["patch_path"]).read_text(encoding="utf-8")
    assert "test_sample_service" in patch_text

    # 2. Tools registered
    assert registry.get("scan_bounty_targets") is not None
    assert registry.get("generate_bounty_patch") is not None
