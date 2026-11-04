"""Tests for Phase 4 SOUL: Deep Semantic Memory & Morning Briefing."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from core.scheduler import LumiScheduler
from memory.repo import MemoryRepo
from tools.memory import register_memory_tools
from tools.registry import ToolRegistry


def test_search_memory_tool(tmp_path):
    config = {"memory": {"db_path": str(tmp_path / "test.db")}}
    repo = MemoryRepo(config)

    # Save a fact
    repo.remember("favorite_framework", "FastAPI and PyTorch", category="preference")

    # Save a conversation message
    repo.save_both("user", "Kal humne transformer model train kiya tha")
    repo.save_both("assistant", "Haan, loss 0.25 tak chala gaya tha")

    reg = ToolRegistry()
    register_memory_tools(reg, repo)

    tool = reg.get("search_memory")
    assert tool is not None

    # Search for fact
    res1 = tool.handler("favorite_framework")
    assert "FastAPI and PyTorch" in res1

    # Search for conversation
    res2 = tool.handler("transformer")
    assert "transformer model" in res2


def test_enhanced_briefing(tmp_path):
    config = {"memory": {"db_path": str(tmp_path / "test.db")}}
    repo = MemoryRepo(config)
    repo.save_reminder("Complete autonomous agent testing", "14:00")

    scheduler = LumiScheduler(memory=repo, config=config)
    briefing = scheduler.generate_briefing()

    assert "Morning Briefing" in briefing
    assert "System Health" in briefing
    assert "Disk Free" in briefing
    assert "Complete autonomous agent testing" in briefing
