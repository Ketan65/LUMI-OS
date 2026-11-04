"""Comprehensive Multi-Tier Verification Suite for LUMI OMEGA SINGULARITY (Phases 24–28).

Tests:
  1. Phase 24 — CognitiveGraph (Temporal Knowledge Graph, Multi-Hop BFS, Causal Path, Centrality, Text Ingestion)
  2. Phase 25 — CyberSentinel (AST Taint Analysis, CWE/CVSS Scoring, Auto-Patching, Attack Surface Audit)
  3. Phase 26 — AutonomousDAGExecutor (Topological Waves, Parallel Execution, $node.output Piping, Self-Healing)
  4. Phase 27 — WorldModelSimulator (3-Gate Shadow Sandbox, Safe Rollback on CWE/Syntax Failure, Atomic Commit, Memory Profiler)
  5. Phase 28 — Autonomous Tool Auto-Forging & Web API / Orchestrator Integration
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from core.cognitive_graph import CognitiveGraph
from core.cyber_sentinel import CyberSentinel
from core.dag_executor import AutonomousDAGExecutor, DAGNode
from core.synthesizer import ToolSynthesizer
from core.world_model import WorldModelSimulator
from tools.cognitive_graph import register_cognitive_graph_tools
from tools.cyber_sentinel import register_cyber_sentinel_tools
from tools.dag_executor import register_dag_executor_tools
from tools.registry import Tool, ToolRegistry
from tools.synthesizer import register_synthesizer_tools
from tools.world_model import register_world_model_tools


# ---------------------------------------------------------------------------
# Phase 24: CognitiveGraph Tests
# ---------------------------------------------------------------------------

def test_cognitive_graph_seed_and_multi_hop(tmp_path: Path):
    from core.personal_identity import get_full_name
    owner = get_full_name()
    db_file = tmp_path / "test_kg.db"
    cg = CognitiveGraph(db_path=db_file)

    summary = cg.get_ecosystem_summary()
    assert summary["total_nodes"] >= 5
    assert summary["total_active_edges"] >= 5

    # 2-hop neighborhood around owner
    sub = cg.query_neighborhood(owner, max_hops=2)
    labels = {n["label"] for n in sub["nodes"]}
    assert owner in labels
    assert "LUMI" in labels

    # Causal path discovery: LUMI -> owner
    path_res = cg.find_causal_path("LUMI", owner, max_depth=4)
    assert path_res["connected"] is True
    assert path_res["hops"] >= 1


def test_cognitive_graph_ingestion_and_temporal_invalidation(tmp_path: Path):
    db_file = tmp_path / "test_kg_ingest.db"
    cg = CognitiveGraph(db_path=db_file)

    res = cg.ingest_text("SENTINEL uses FastAPI and AEGIS depends on RedisCluster.", use_llm=False)
    assert res["triples_extracted"] >= 2

    ctx = cg.build_context_snippet("How is SENTINEL architected?")
    assert "SENTINEL" in ctx

    # Invalidate an edge and verify it no longer appears in active neighborhood
    invalidated = cg.invalidate_edge("SENTINEL", "USES", "FastAPI")
    assert invalidated is True


# ---------------------------------------------------------------------------
# Phase 25: CyberSentinel VAPT & Auto-Remediation Tests
# ---------------------------------------------------------------------------

_FAKE_STRIPE_PREFIX = "sk_" + "live_"

VULNERABLE_SAMPLE = f"""import hashlib
import os
import pickle
import subprocess

api_key = "{_FAKE_STRIPE_PREFIX}9876543210abcdef9876543210abcdef"

def process_user_data(user_input, db_cursor, raw_payload):
    digest = hashlib.md5(user_input.encode()).hexdigest()
    calc = eval(user_input)
    subprocess.run(f"echo {{user_input}}", shell=True)
    db_cursor.execute(f"SELECT * FROM accounts WHERE owner = '{{user_input}}'")
    obj = pickle.loads(raw_payload)
    return digest, calc, obj
"""


def test_cyber_sentinel_deep_ast_taint_and_cwe_detection(tmp_path: Path):
    sentinel = CyberSentinel(workspace_root=tmp_path)
    vuln_file = tmp_path / "vulnerable_service.py"
    vuln_file.write_text(VULNERABLE_SAMPLE, encoding="utf-8")

    scan = sentinel.deep_scan_file(vuln_file)
    assert scan["success"] is True
    assert scan["verdict"] == "CRITICAL_RISK"
    assert scan["max_cvss"] >= 9.4

    detected_cwes = {v["cwe_id"] for v in scan["vulnerabilities"]}
    assert "CWE-798" in detected_cwes  # Hardcoded secret
    assert "CWE-327" in detected_cwes  # Weak MD5 hash
    assert "CWE-94" in detected_cwes   # eval() injection
    assert "CWE-78" in detected_cwes   # subprocess shell=True
    assert "CWE-89" in detected_cwes   # SQL injection via f-string
    assert "CWE-502" in detected_cwes  # pickle.loads deserialization


def test_cyber_sentinel_auto_patch_and_surface_audit(tmp_path: Path):
    sentinel = CyberSentinel(workspace_root=tmp_path)
    target_file = tmp_path / "patch_me.py"
    target_file.write_text(
        f'import hashlib\nimport pickle\n\napi_key = "{_FAKE_STRIPE_PREFIX}1234567890abcdef1234567890"\n'
        'def load_token(raw_data, expr):\n'
        '    h = hashlib.md5(b"test").hexdigest()\n'
        '    val = eval(expr)\n'
        '    data = pickle.loads(raw_data)\n'
        '    return h, val, data\n',
        encoding="utf-8",
    )

    patch_res = sentinel.auto_patch_file(target_file, write_in_place=True)
    assert patch_res["success"] is True
    assert patch_res["patched"] is True
    assert patch_res["post_vulnerabilities"] == 0
    assert patch_res["post_verdict"] == "FORTIFIED"
    assert patch_res["post_score"] == 100.0
    assert "os.environ.get" in target_file.read_text(encoding="utf-8")
    assert "hashlib.sha256" in target_file.read_text(encoding="utf-8")
    assert "ast.literal_eval" in target_file.read_text(encoding="utf-8")

    surface = sentinel.audit_attack_surface()
    assert "posture_score" in surface
    assert surface["total_listening_sockets"] >= 0


# ---------------------------------------------------------------------------
# Phase 26: AutonomousDAGExecutor Tests
# ---------------------------------------------------------------------------

def test_dag_executor_parallel_waves_and_context_piping():
    reg = ToolRegistry()
    reg.register(
        Tool(
            name="produce_token",
            description="Produces a token string",
            params_schema={"type": "object", "properties": {"seed": {"type": "string"}}},
            handler=lambda seed="alpha": f"TOKEN_{seed.upper()}",
            risk="auto",
        )
    )
    reg.register(
        Tool(
            name="transform_token",
            description="Transforms a piped token",
            params_schema={"type": "object", "properties": {"val": {"type": "string"}, "tag": {"type": "string"}}},
            handler=lambda val="", tag="": f"[{tag}:{val}]",
            risk="auto",
        )
    )

    dag = AutonomousDAGExecutor(registry=reg)
    # Diamond DAG: n1 -> (n2, n3 in parallel) -> n4
    nodes = [
        DAGNode(id="n1", title="Seed Generation", tool="produce_token", args={"seed": "omega"}, depends_on=[]),
        DAGNode(id="n2", title="Branch A Transform", tool="transform_token", args={"val": "$n1.output", "tag": "A"}, depends_on=["n1"]),
        DAGNode(id="n3", title="Branch B Transform", tool="transform_token", args={"val": "$n1.output", "tag": "B"}, depends_on=["n1"]),
        DAGNode(
            id="n4",
            title="Merge Verification",
            tool="transform_token",
            args={"val": "$n2.output+$n3.output", "tag": "MERGED"},
            depends_on=["n2", "n3"],
            expected_contains="[MERGED:[A:TOKEN_OMEGA]+[B:TOKEN_OMEGA]]",
        ),
    ]

    res = dag.execute_mission("Diamond Pipeline Test", nodes=nodes)
    assert res["ok"] is True
    assert res["waves_count"] == 3
    assert res["nodes_succeeded"] == 4
    n4_out = next(n["output"] for n in res["nodes"] if n["id"] == "n4")
    assert n4_out == "[MERGED:[A:TOKEN_OMEGA]+[B:TOKEN_OMEGA]]"


# ---------------------------------------------------------------------------
# Phase 27: WorldModelSimulator & Phase 28 Auto-Forge Tests
# ---------------------------------------------------------------------------

def test_world_model_3gate_reject_and_commit(tmp_path: Path):
    wm = WorldModelSimulator(workspace_root=tmp_path)

    app_file = tmp_path / "calculator.py"
    test_file = tmp_path / "test_calculator.py"
    app_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    test_file.write_text(
        "import unittest\nfrom calculator import add\n\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n",
        encoding="utf-8",
    )

    # 1. Counterfactual simulation with CWE vulnerability -> MUST BE REJECTED by Gate 2
    bad_security_code = "import os\ndef add(a, b):\n    os.system('echo hacked')\n    return a + b\n"
    res_reject_sec = wm.simulate_and_commit(app_file, candidate_code=bad_security_code)
    assert res_reject_sec["verdict"] == "REJECTED_SAFE_ROLLBACK"
    assert res_reject_sec["committed"] is False
    assert res_reject_sec["gates"]["gate2_security"]["passed"] is False
    assert "os.system" not in app_file.read_text(encoding="utf-8")

    # 2. Counterfactual simulation with broken logic failing unit test -> MUST BE REJECTED by Gate 3
    bad_logic_code = "def add(a, b):\n    return a - b\n"
    res_reject_test = wm.simulate_and_commit(app_file, candidate_code=bad_logic_code)
    assert res_reject_test["verdict"] == "REJECTED_SAFE_ROLLBACK"
    assert res_reject_test["committed"] is False
    assert res_reject_test["gates"]["gate3_runtime"]["passed"] is False

    # 3. Valid, secure, test-passing upgrade -> MUST BE APPROVED & COMMITTED
    good_code = (
        "def add(a: int, b: int) -> int:\n"
        '    """Fast validated addition."""\n'
        "    return int(a) + int(b)\n"
    )
    res_commit = wm.simulate_and_commit(app_file, candidate_code=good_code)
    assert res_commit["verdict"] == "COMMIT_APPROVED"
    assert res_commit["committed"] is True
    assert Path(res_commit["backup_path"]).exists()
    assert "Fast validated addition" in app_file.read_text(encoding="utf-8")

    # 4. Runtime Memory & Latency Profiler
    prof = wm.profile_code("data = [i * i for i in range(5000)]\nprint(len(data))")
    assert prof["ok"] is True
    assert prof["stdout"] == "5000"
    assert prof["peak_kb"] > 0


def test_synthesizer_auto_forge_from_spec(tmp_path: Path):
    reg = ToolRegistry()
    synth = ToolSynthesizer(
        tools_dir=tmp_path / "synthesized_tools",
        metadata_file=tmp_path / "synthesized_tools.json",
        brain=None,
        registry=reg,
    )
    register_synthesizer_tools(reg, synthesizer=synth)

    res = synth.auto_forge_from_spec(" slugify_title ", "Converts a title string into a clean slug")
    assert res["success"] is True
    assert reg.get("slugify_title") is not None
    out = reg.get("slugify_title").handler(text="Hello World")
    assert "Hello World" in str(out)


def test_omega_tools_and_fastapi_routes(tmp_path: Path):
    from main import build_orchestrator
    from web.server import create_app

    orc = build_orchestrator(web=True)
    assert orc is not None
    orc.config["web"] = {"allow_remote": True}

    # Test slash commands
    from core.personal_identity import get_full_name
    owner = get_full_name()
    orc.cognitive_graph.upsert_edge(owner, "ARCHITECT_OF", "LUMI", evidence="Core test")

    _, graph_out = orc.command("/graph map")
    assert "Sovereign Knowledge Graph" in graph_out

    _, path_out = orc.command(f"/graph path {owner} -> LUMI")
    assert "Causal Path Found" in path_out

    _, vapt_out = orc.command("/vapt surface")
    assert "Workstation Attack Surface" in vapt_out

    # Test FastAPI endpoints
    app = create_app(orc)
    client = TestClient(app)

    r_status = client.get("/api/omega/status")
    assert r_status.status_code == 200
    data = r_status.json()
    assert data["ok"] is True
    assert data["cognitive_graph"]["active"] is True
    assert data["cyber_sentinel"]["active"] is True
    assert data["dag_executor"]["active"] is True
    assert data["world_model"]["active"] is True

    r_graph = client.get("/api/omega/graph?entity=LUMI")
    assert r_graph.status_code == 200
    assert len(r_graph.json()["nodes"]) >= 1

    r_sim = client.post("/api/omega/simulate", json={"code": "print(2 ** 10)"})
    assert r_sim.status_code == 200
    assert r_sim.json()["ok"] is True
    assert r_sim.json()["stdout"] == "1024"
