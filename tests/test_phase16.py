"""Unit & Integration tests for Phase 16: DEEP-REASONER.

Tests:
  - Monte-Carlo Tree Search branching, step evaluation, and backpropagation
  - Hypothesis self-critique, verification scoring, and edge-case detection
  - Decision tree persistence and history retrieval
  - Deep reasoner tools registration in ToolRegistry
  - FastAPI /api/reasoner/explore and /api/reasoner/recent endpoints
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from brain.mcts_reasoner import DeepReasoner
from tools.reasoner import register_reasoner_tools
from tools.registry import ToolRegistry
from web.server import create_app


@pytest.fixture
def temp_reasoner(tmp_path: Path) -> DeepReasoner:
    hist_file = tmp_path / "reasoning_hist_test.json"
    return DeepReasoner(history_file=hist_file)


def test_deep_reasoner_explore_and_tree_structure(temp_reasoner: DeepReasoner):
    problem = "Design a high-throughput real-time telemetry streaming service for 100k IoT devices"
    result = temp_reasoner.explore(problem=problem, depth=2, branches=3, domain="architecture")

    assert result["problem"] == problem
    assert result["confidence_score"] >= 80.0
    assert result["branches_evaluated"] == 3
    assert len(result["thought_trace"]) >= 4
    assert "Optimal Architecture" in result["optimal_solution"]

    # Verify Tree structure
    tree = result["tree"]
    assert tree["id"] == "node_0"
    assert len(tree["children"]) == 3
    # At least one child node should be OPTIMAL
    optimal_children = [c for c in tree["children"] if c["status"] == "OPTIMAL"]
    assert len(optimal_children) == 1
    assert optimal_children[0]["verifier_score"] >= 90.0

    # Verify history persistence
    hist = temp_reasoner.get_history()
    assert len(hist) == 1
    assert hist[0]["problem"] == problem


def test_verify_hypothesis(temp_reasoner: DeepReasoner):
    hypo = "Implement a distributed LRU cache with async worker threads and vector indexing"
    res = temp_reasoner.verify_hypothesis(hypothesis=hypo, problem_context="Cache optimization")

    assert res["verifier_score"] >= 85.0
    assert len(res["pros"]) >= 2
    assert "High throughput & logarithmic lookup complexity" in res["pros"]
    assert "Non-blocking concurrent execution" in res["pros"]


def test_reasoner_tools_registration(temp_reasoner: DeepReasoner):
    registry = ToolRegistry()
    registered_reasoner = register_reasoner_tools(registry, reasoner=temp_reasoner)
    assert registered_reasoner is temp_reasoner

    assert registry.get("deep_reason") is not None
    assert registry.get("verify_hypothesis") is not None
    assert registry.get("get_reasoning_history") is not None

    # Test deep_reason tool handler
    reason_fn = registry.get("deep_reason").handler
    res = reason_fn(problem="Optimize database indexing for 10M rows")
    assert "optimal_solution" in res
    assert res["branches_evaluated"] == 3

    # Test verify_hypothesis tool handler
    verify_fn = registry.get("verify_hypothesis").handler
    v_res = verify_fn(hypothesis="Use B-tree indexing on primary keys")
    assert v_res["verifier_score"] >= 80.0


@pytest.mark.asyncio
async def test_reasoner_web_api(temp_reasoner: DeepReasoner):
    registry = ToolRegistry()
    register_reasoner_tools(registry, reasoner=temp_reasoner)

    mock_orch = MagicMock()
    mock_orch.config = {"web": {"allow_remote": True}}
    mock_orch.registry = registry
    mock_orch.reasoner = temp_reasoner

    app = create_app(mock_orch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. POST /api/reasoner/explore
        r = await client.post("/api/reasoner/explore", json={
            "problem": "Implement self-healing consensus across 5 distributed nodes",
            "branches": 3,
            "domain": "distributed_systems"
        })
        assert r.status_code == 200
        data = r.json()
        assert "optimal_solution" in data
        assert data["branches_evaluated"] == 3
        assert "tree" in data

        # 2. GET /api/reasoner/recent
        r_hist = await client.get("/api/reasoner/recent")
        assert r_hist.status_code == 200
        hist_data = r_hist.json()
        assert len(hist_data["history"]) >= 1
