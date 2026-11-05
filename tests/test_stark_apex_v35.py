"""End-to-End Verification Suite for LUMI v35.0 — STARK APEX PROTOCOL (Phases 29–35).

Tests all 4 Specialized Upgrade Departments:
  - Dept 1: ReflexRouter (Tier-0 deterministic <5ms reflexes, Dynamic Top-K semantic tool pruning,
            sentence-boundary TTS speech chunking, /api/chat/stream SSE endpoint)
  - Dept 2: HybridRRFEngine (Okapi BM25 + 256-D N-Gram Vector RRF in memory & vault) &
            RepoASTGraph (Cross-file symbol locator, blast/impact radius, SWE repo map)
  - Dept 3: ActiveContextSensor (Win32 foreground window + clipboard traceback auto-injection),
            AsyncMissionQueue (Non-blocking background job pool), and
            DPOFlywheel (Automatic self-healed tool repair preference logging)
  - Dept 4: Stark Apex Persona Engine (classify_interaction_mode, tactical HUD header,
            situational greetings, code-safe tone_response)
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from brain.base import Brain, BrainReply
from core.context_sensor import ActiveContextSensor
from core.hybrid_retriever import HybridRRFEngine
from core.jarvis_personality import (
    build_situational_greeting,
    build_system_prompt,
    build_tactical_hud_header,
    classify_interaction_mode,
    tone_response,
)
from core.mission_queue import AsyncMissionQueue
from core.orchestrator import Orchestrator
from core.reflex_router import ReflexRouter
from core.repo_graph import RepoASTGraph
from evolution.dpo_flywheel import DPOFlywheel, register_dpo_flywheel_tools
from memory.store import get_facts, init_db, save_fact, search_facts
from tools.context_sensor import register_context_sensor_tools
from tools.mission_queue import register_mission_queue_tools
from tools.reflex_router import register_reflex_router_tools
from tools.registry import Tool, ToolRegistry
from tools.repo_graph import register_repo_graph_tools
from web.server import create_app


# ---------------------------------------------------------------------------
# Dept 1: Speed, Streaming & Reflex Router Tests
# ---------------------------------------------------------------------------


def test_dept1_tier0_reflex_and_topk_tool_pruning():
    router = ReflexRouter()

    # 1. Tier-0 Reflex match (<10ms deterministic response)
    t0 = time.perf_counter()
    hit = router.check_tier0_reflex(
        "ping",
        context={"model": "hermes3:latest", "policy": "prefer_local", "tools_count": 90},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert hit is not None
    assert hit["matched"] is True
    assert elapsed_ms < 25.0
    assert "operational" in hit["response"].lower() or "reflex" in hit["response"].lower()

    # Complex engineering prompt must NOT false-trigger Tier-0
    miss = router.check_tier0_reflex("Write a Python function to parse git status output and save to file")
    assert miss is None

    # 2. Dynamic Top-K Tool Pruning (80+ schemas -> 14 relevant schemas)
    mock_specs = [
        {"type": "function", "function": {"name": f"dummy_tool_{i}", "description": f"Generic helper {i}"}}
        for i in range(75)
    ] + [
        {"type": "function", "function": {"name": "read_file", "description": "Read a file from disk"}},
        {"type": "function", "function": {"name": "write_file", "description": "Write a file to disk"}},
        {"type": "function", "function": {"name": "vapt_deep_scan", "description": "Scan Python file for CWE security vulnerabilities"}},
        {"type": "function", "function": {"name": "vapt_auto_patch", "description": "Auto patch CWE security vulnerabilities"}},
    ]
    pruned = router.select_relevant_tools("Scan auth.py for CWE security vulnerabilities and patch it", mock_specs, top_k=14)
    assert len(pruned) == 14
    selected_names = {t["function"]["name"] for t in pruned}
    assert "read_file" in selected_names
    assert "vapt_deep_scan" in selected_names
    assert "vapt_auto_patch" in selected_names

    # 3. Speech chunking for pipelined TTS
    chunks = router.split_into_speech_chunks(
        "Namaste Boss! Systems 100% green hain. Abhi VAPT scan complete ho gaya hai. Koi critical CWE nahi mila."
    )
    assert len(chunks) >= 2
    assert "Namaste Boss!" in chunks[0]

    telemetry = router.get_router_telemetry()
    assert telemetry["tier0_reflex_hits"] >= 1
    assert telemetry["estimated_tokens_saved"] > 0


# ---------------------------------------------------------------------------
# Dept 2: Hybrid RRF Memory & Repo AST Graph Tests
# ---------------------------------------------------------------------------


def test_dept2_hybrid_rrf_retriever_and_memory_store(tmp_path: Path):
    rrf = HybridRRFEngine()
    docs = [
        {"id": 1, "content": "def verify_jwt_token(token): raise InvalidSignatureError('bad sig')"},
        {"id": 2, "content": "def render_cyberpunk_orb(canvas): draw_glow(canvas)"},
        {"id": 3, "content": "SELECT * FROM sqlite_master WHERE type='table'"},
    ]

    # Exact identifier lookup
    res_exact = rrf.rank_documents("verify_jwt_token", docs, text_key="content", top_k=2)
    assert res_exact[0]["id"] == 1
    assert res_exact[0]["exact_match_boost"] > 0

    # Paraphrased semantic concept query ("auth bug check") -> matches JWT signature error doc!
    res_sem = rrf.rank_documents("auth bug check", docs, text_key="content", top_k=2)
    assert res_sem[0]["id"] == 1

    # Verify memory/store.py hybrid search_facts integration
    db_file = tmp_path / "hybrid_mem.db"
    init_db(db_file)
    save_fact("workstation_gpu", "NVIDIA RTX 5060 CUDA 16GB", category="hardware", db_path=db_file)
    save_fact("code_theme", "Cyberpunk Neon Dark", category="ui", db_path=db_file)

    facts = search_facts("NVIDIA RTX hardware", limit=3, db_path=db_file)
    assert len(facts) >= 1
    assert facts[0]["key"] == "workstation_gpu"


def test_dept2_repo_ast_graph_and_impact_radius(tmp_path: Path):
    # Create a miniature 3-file Python repository
    (tmp_path / "core_auth.py").write_text(
        "def validate_session(token: str) -> bool:\n"
        "    '''Validates user session token.'''\n"
        "    return len(token) > 10\n",
        encoding="utf-8",
    )
    (tmp_path / "api_router.py").write_text(
        "from core_auth import validate_session\n\n"
        "def handle_login(req_token: str) -> str:\n"
        "    if validate_session(req_token):\n"
        "        return 'OK'\n"
        "    return 'DENIED'\n",
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_login.py").write_text(
        "from api_router import handle_login\n\n"
        "def test_handle_login():\n"
        "    assert handle_login('12345678901') == 'OK'\n",
        encoding="utf-8",
    )

    graph = RepoASTGraph(root_dir=tmp_path)
    summary = graph.build_graph()
    assert summary["files_scanned"] == 3

    located = graph.locate_symbol("validate_session")
    assert len(located) == 1
    assert located[0]["file"] == "core_auth.py"
    assert located[0]["caller_count"] >= 1

    impact = graph.analyze_impact_radius("validate_session")
    assert impact["found"] is True
    assert "api_router.py" in impact["affected_files"]
    assert any("test_login.py" in t for t in impact["affected_tests"])

    repo_map = graph.generate_repo_map(max_files=10)
    assert "core_auth.py" in repo_map
    assert "validate_session" in repo_map


# ---------------------------------------------------------------------------
# Dept 3: Active Context Sensor, Async Mission Queue & DPO Flywheel Tests
# ---------------------------------------------------------------------------


def test_dept3_context_sensor_mission_queue_and_dpo(tmp_path: Path):
    # 1. ActiveContextSensor traceback classification & auto-injection detection
    sensor = ActiveContextSensor(workspace_root=tmp_path)
    assert sensor.should_auto_inject_context("Boss ye error fix kar jaldi") is True
    assert sensor.should_auto_inject_context("explain traceback in terminal") is True
    assert sensor.should_auto_inject_context("write a poem about stars") is False

    tb_sample = (
        'Traceback (most recent call last):\n'
        '  File "app.py", line 42, in <module>\n'
        '    result = 1 / 0\n'
        'ZeroDivisionError: division by zero'
    )
    classified = sensor.classify_clipboard(tb_sample)
    assert classified["kind"] == "python_traceback"
    assert "ZeroDivisionError" in classified["exception_line"]

    # 2. AsyncMissionQueue non-blocking execution
    mq = AsyncMissionQueue(max_workers=2)
    submitted = mq.submit_mission(
        "Background Security Audit",
        "vapt",
        lambda x: {"scanned": x, "verdict": "FORTIFIED"},
        12,
    )
    mid = submitted["mission_id"]
    for _ in range(30):
        status = mq.get_mission(mid)
        if status and str(status["status"]).lower() == "completed":
            break
        time.sleep(0.05)
    final_status = mq.get_mission(mid)
    assert final_status is not None
    assert str(final_status["status"]).lower() == "completed"
    assert "FORTIFIED" in str(final_status["result"])

    # 3. DPOFlywheel preference logging & TRL export
    dpo_file = tmp_path / "dpo_test.jsonl"
    fw = DPOFlywheel(dataset_path=dpo_file)
    rec = fw.record_tool_repair(
        user_prompt="Read config file",
        tool_name="read_file",
        failed_args={"path": "wrong.yaml"},
        failed_error="FileNotFoundError",
        healed_args={"path": "config.yaml"},
        healed_result="model_name: hermes3:latest",
    )
    assert rec["recorded"] is True
    stats = fw.get_flywheel_stats()
    assert stats["total_pairs"] == 1
    assert stats["categories"]["tool_self_healing"] == 1


# ---------------------------------------------------------------------------
# Dept 4: Stark Apex Persona & Full Orchestrator + Web Server Integration
# ---------------------------------------------------------------------------


def test_dept4_stark_persona_and_orchestrator_end_to_end(tmp_path: Path):
    assert classify_interaction_mode("hey lumi battery kitni hai", voice_mode=True) == "voice_tactical"
    assert classify_interaction_mode("Traceback (most recent call last): ValueError", has_traceback=True) == "crisis_triage"
    assert classify_interaction_mode("Design a multi-agent DAG architecture with SQLite persistence") == "deep_engineering"

    code_reply = "Here is the fix:\n```python\ndef add(a, b):\n    return a + b\n```"
    # Never truncate code in text mode!
    assert "def add(a, b):" in tone_response(code_reply, mode="text")
    # Strip code block for spoken voice_tactical mode
    spoken = tone_response(code_reply, mode="voice_tactical")
    assert "```" not in spoken

    hud = build_tactical_hud_header({"cpu_percent": 18, "ram_percent": 64, "model": "hermes3:latest"})
    assert "STARK-HUD" in hud
    greeting = build_situational_greeting({"user": {"call_name": "Boss"}}, {"ram_percent": 64})
    assert "Boss" in greeting

    # End-to-End Orchestrator DPO Self-Healing & Slash Commands
    class RepairBrain(Brain):
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools=None, on_token=None):
            self.calls += 1
            if self.calls == 1:
                # 1st attempt: bad args (triggers TypeError)
                return BrainReply(text="", tool_calls=[{"name": "strict_add", "args": {"wrong_arg": 1}}])
            if self.calls == 2:
                # 2nd attempt: healed args!
                return BrainReply(text="", tool_calls=[{"name": "strict_add", "args": {"a": 10, "b": 20}}])
            return BrainReply(text="Sum is 30, Boss!", tool_calls=[])

    reg = ToolRegistry()
    reg.register(Tool(
        name="strict_add",
        description="Adds two integers a and b",
        params_schema={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}, "required": ["a", "b"]},
        handler=lambda a, b: a + b,
        risk="auto",
    ))

    orc = Orchestrator(brain=RepairBrain(), registry=reg)
    orc.reflex_router = register_reflex_router_tools(reg)
    orc.repo_graph = register_repo_graph_tools(reg, workspace_root=tmp_path)
    orc.context_sensor = register_context_sensor_tools(reg, workspace_root=tmp_path)
    orc.mission_queue = register_mission_queue_tools(reg, orchestrator=orc, workspace_root=tmp_path)
    orc.dpo_flywheel = DPOFlywheel(dataset_path=tmp_path / "orc_dpo.jsonl")

    res = orc.run_turn("Calculate 10 + 20 using strict_add")
    assert "30" in res["reply"]
    # Verify DPOFlywheel captured the failed -> healed tool repair trajectory automatically!
    assert orc.dpo_flywheel.get_flywheel_stats()["total_pairs"] == 1

    # Verify new slash commands
    _, reflex_out = orc.command("/reflex")
    assert "REFLEX" in reflex_out.upper() or "TELEMETRY" in reflex_out.upper()
    _, dpo_out = orc.command("/dpo")
    assert "total_pairs" in dpo_out or "DPO" in dpo_out.upper()

    # Verify FastAPI /api/apex/* and /api/chat/stream endpoints
    app = create_app(orc)
    client = TestClient(app)

    r_status = client.get("/api/apex/status", headers={"Host": "127.0.0.1:8765"})
    assert r_status.status_code == 200
    assert "Stark Apex" in r_status.json()["edition"]

    r_stream = client.post(
        "/api/chat/stream",
        json={"message": "/reflex"},
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
    )
    assert r_stream.status_code == 200
    assert "data:" in r_stream.text
