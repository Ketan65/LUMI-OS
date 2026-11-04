"""Unit tests for Phase 10 NEURAL-VAULT (Local Codebase Indexing & Semantic Vector RAG)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from core.vault import NeuralVault, tokenize_code
from tools.registry import ToolRegistry
from tools.vault import register_vault_tools
from web.server import create_app


def test_tokenize_code():
    tokens = tokenize_code("def calculate_user_tax(annualIncome): pass")
    assert "calculate" in tokens
    assert "user" in tokens
    assert "tax" in tokens
    assert "annual" in tokens
    assert "income" in tokens


def test_vault_indexing_and_incremental(tmp_path: Path):
    db_file = tmp_path / "test_vault.db"
    vault = NeuralVault(db_path=db_file)

    # Create dummy project
    repo_dir = tmp_path / "my_project"
    repo_dir.mkdir()
    (repo_dir / "auth.py").write_text(
        "def verify_jwt_token(token):\n    '''Checks user signature.'''\n    return token == 'secret'\n",
        encoding="utf-8",
    )
    (repo_dir / "readme.md").write_text("# Project Auth\nThis handles login security.", encoding="utf-8")

    # Ignored directory
    git_dir = repo_dir / ".git"
    git_dir.mkdir()
    (git_dir / "config.txt").write_text("git internal", encoding="utf-8")

    # Initial Indexing
    stats1 = vault.index_path(repo_dir)
    assert stats1["indexed"] == 2
    assert stats1["skipped"] == 0

    v_stats1 = vault.get_stats()
    assert v_stats1["documents"] == 2
    assert v_stats1["chunks"] >= 2

    # Second Indexing without changes (incremental should skip)
    stats2 = vault.index_path(repo_dir)
    assert stats2["indexed"] == 0
    assert stats2["skipped"] == 2


def test_vault_search(tmp_path: Path):
    db_file = tmp_path / "test_vault.db"
    vault = NeuralVault(db_path=db_file)

    repo_dir = tmp_path / "codebase"
    repo_dir.mkdir()
    (repo_dir / "database.py").write_text(
        "import sqlite3\n\ndef connect_database(path):\n    return sqlite3.connect(path)\n",
        encoding="utf-8",
    )
    (repo_dir / "server.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/ping')\ndef ping(): return 'pong'\n",
        encoding="utf-8",
    )

    vault.index_path(repo_dir)

    # Search for database
    results = vault.search("connect sqlite database")
    assert len(results) > 0
    top = results[0]
    assert "database.py" in top.file_path
    assert "connect_database" in top.snippet

    # Filter search
    filtered = vault.search("ping", file_filter="server.py")
    assert len(filtered) == 1
    assert "server.py" in filtered[0].file_path


def test_vault_tools_and_commands(tmp_path: Path):
    reg = ToolRegistry()
    db_file = tmp_path / "test_vault.db"
    vault = NeuralVault(db_path=db_file)

    sample_file = tmp_path / "notes.md"
    sample_file.write_text("# Boss's Notes\nLUMI is an autonomous AI assistant.", encoding="utf-8")

    active_vault = register_vault_tools(reg, vault=vault)
    assert reg.get("vault_search") is not None
    assert reg.get("vault_index") is not None

    # Test index tool
    idx_res = reg.get("vault_index").handler(path=str(sample_file))
    assert "NEURAL-VAULT Indexed" in idx_res

    # Test search tool
    s_res = reg.get("vault_search").handler(query="assistant LUMI")
    assert "NEURAL-VAULT Search" in s_res
    assert "notes.md" in s_res

    # Test empty query
    assert "Please provide" in reg.get("vault_search").handler(query="")


def test_orchestrator_vault_command(tmp_path: Path):
    from core.orchestrator import Orchestrator

    db_file = tmp_path / "test_vault.db"
    vault = NeuralVault(db_path=db_file)
    (tmp_path / "script.py").write_text("def run_batch(): pass", encoding="utf-8")
    vault.index_path(tmp_path)

    orc = Orchestrator(brain=MagicMock())
    orc.vault = vault

    # /vault stats
    _, msg = orc.command("/vault stats")
    assert "NEURAL-VAULT:" in msg
    assert "chunks" in msg

    # /vault search
    _, msg2 = orc.command("/vault search batch")
    assert "NEURAL-VAULT" in msg2 or "Results:" in msg2


def test_web_vault_endpoints(tmp_path: Path):
    db_file = tmp_path / "test_vault.db"
    vault = NeuralVault(db_path=db_file)
    (tmp_path / "api_sample.py").write_text("def fetch_records(): return [1, 2, 3]", encoding="utf-8")
    vault.index_path(tmp_path)

    mock_orc = MagicMock()
    mock_orc.vault = vault
    mock_orc.config = {"web": {"auth_token": ""}}
    mock_orc.memory = None

    app = create_app(mock_orc)
    transport = httpx.ASGITransport(app=app)

    async def run_checks():
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8765") as client:
            # Stats
            r_stats = await client.get("/api/vault/stats")
            assert r_stats.status_code == 200
            assert "documents" in r_stats.json()

            # Query
            r_query = await client.post("/api/vault/query", json={"query": "fetch records"})
            assert r_query.status_code == 200
            data = r_query.json()
            assert data["count"] > 0
            assert "api_sample.py" in data["results"][0]["file_path"]

            # Index
            r_idx = await client.post("/api/vault/index", json={"path": str(tmp_path)})
            assert r_idx.status_code == 200
            assert "stats" in r_idx.json()

    asyncio.run(run_checks())
