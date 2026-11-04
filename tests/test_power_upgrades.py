"""Unit tests for LUMI's Power Upgrades (Deep Research, Digital Shadow, Code Oracle, Workstation Guardian)."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from core.researcher import DeepResearcher
from evolution.digital_shadow import DigitalShadow
from tools.code_oracle import CodeOracle
from tools.workstation_cleaner import WorkstationGuardian
from tools.registry import ToolRegistry
from tools.deep_research import register_deep_research_tools
from evolution.digital_shadow import register_digital_shadow_tools
from tools.code_oracle import register_code_oracle_tools
from tools.workstation_cleaner import register_cleaner_tools


def test_deep_researcher_query_expansion(tmp_path: Path):
    researcher = DeepResearcher(workspace_root=tmp_path)
    queries = researcher.expand_queries("Speculative Decoding in LLMs")
    assert len(queries) == 3
    assert any("overview" in q for q in queries)
    assert any("benchmarks" in q for q in queries)


def test_deep_researcher_dossier_synthesis(tmp_path: Path, monkeypatch):
    researcher = DeepResearcher(workspace_root=tmp_path)

    # Mock web_search and web_read for deterministic unit test
    def mock_search(q, max_results=3):
        return "[1] Speculative Decoding Fast Inference\nURL: https://example.com/spec_dec\nSnippet: 3x speedup."

    def mock_read(url, max_chars=1800):
        return "# Speculative Decoding\nSpeculative decoding utilizes draft models to accelerate generation."

    monkeypatch.setattr("core.researcher.web_search", mock_search)
    monkeypatch.setattr("core.researcher.web_read", mock_read)

    res = researcher.conduct_research("Speculative Decoding", max_sources=2)
    assert res["sources_count"] == 1
    assert "Speculative Decoding" in res["topic"]
    assert Path(res["dossier_file"]).exists()
    assert "# 📑 Deep Research Dossier" in res["dossier_markdown"]


def test_digital_shadow_standup_generation(tmp_path: Path):
    journal_dir = tmp_path / "journal"
    shadow = DigitalShadow(repo_root=".", journal_dir=journal_dir)
    res = shadow.generate_standup_digest()

    assert "date" in res
    assert Path(res["journal_file"]).exists()
    assert "# 🛡️ LUMI Digital Shadow — Engineering Daily Standup" in res["standup_markdown"]
    assert "Commander" in res["standup_markdown"]


def test_code_oracle_clean_file_audit(tmp_path: Path):
    sample_file = tmp_path / "clean_module.py"
    sample_file.write_text(
        '"""Clean sample module."""\n\ndef add(a: int, b: int) -> int:\n    """Adds two integers."""\n    return a + b\n',
        encoding="utf-8",
    )
    oracle = CodeOracle(workspace_root=tmp_path)
    res = oracle.audit_file(str(sample_file))

    assert res["success"] is True
    assert res["ast_valid"] is True
    assert res["functions"] == 1
    assert len(res["security_warnings"]) == 0
    assert res["quality_score"] >= 80


def test_code_oracle_vulnerability_detection(tmp_path: Path):
    bad_file = tmp_path / "unsafe_module.py"
    bad_file.write_text(
        'import subprocess\napi_key = "sk-1234567890abcdef"\ndef run(cmd):\n    eval(cmd)\n    subprocess.run(cmd, shell=True)\n',
        encoding="utf-8",
    )
    oracle = CodeOracle(workspace_root=tmp_path)
    res = oracle.audit_file(str(bad_file))

    assert res["success"] is True
    assert len(res["security_warnings"]) >= 2
    assert res["quality_score"] < 80


def test_workstation_guardian_diagnostics(tmp_path: Path):
    guardian = WorkstationGuardian(workspace_root=tmp_path)
    diag = guardian.get_memory_diagnostics(top_n=3)

    assert "total_ram_gb" in diag or "error" in diag
    if "total_ram_gb" in diag:
        assert diag["total_ram_gb"] > 0
        assert len(diag["top_processes"]) <= 3


def test_workstation_guardian_cache_scanner(tmp_path: Path):
    guardian = WorkstationGuardian(workspace_root=tmp_path)

    # Create dummy cache directory
    dummy_cache = tmp_path / "dummy_pkg" / "__pycache__"
    dummy_cache.mkdir(parents=True)
    (dummy_cache / "test.pyc").write_bytes(b"dummy bytecode" * 100)

    # Test dry run
    scan_dry = guardian.scan_and_clean_caches(dry_run=True)
    assert scan_dry["cache_folders_found"] == 1
    assert dummy_cache.exists()

    # Test live purge
    scan_live = guardian.scan_and_clean_caches(dry_run=False)
    assert scan_live["folders_deleted"] == 1
    assert not dummy_cache.exists()


def test_tool_registrations_all_registered():
    registry = ToolRegistry()
    register_deep_research_tools(registry)
    register_digital_shadow_tools(registry)
    register_code_oracle_tools(registry)
    register_cleaner_tools(registry)

    registered_names = {t.name for t in registry.list_all()}
    assert "deep_web_research" in registered_names
    assert "generate_developer_digest" in registered_names
    assert "code_oracle_audit" in registered_names
    assert "optimize_workstation_health" in registered_names
