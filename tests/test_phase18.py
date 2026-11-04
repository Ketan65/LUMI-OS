"""Unit & Integration tests for Phase 18: CLUSTER-OMNI.

Tests:
  - Sovereign multi-device cluster topology initialization
  - Peer registration and heartbeat tracking
  - Intelligent task routing with RTX 5060 heavy node offloading
  - State handoff synchronization with HMAC-SHA256 signatures
  - Cluster ToolRegistry integration
  - FastAPI /api/cluster/* endpoints
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from mesh.cluster import ClusterMesh, ClusterNode
from tools.cluster import register_cluster_tools
from tools.registry import ToolRegistry
from web.server import create_app


@pytest.fixture
def temp_cluster_mesh(tmp_path: Path) -> ClusterMesh:
    topo_file = tmp_path / "test_cluster_nodes.json"
    mesh = ClusterMesh(topology_path=topo_file)
    return mesh


def test_cluster_mesh_initialization(temp_cluster_mesh: ClusterMesh):
    status = temp_cluster_mesh.get_cluster_status()
    assert status["enabled"] is True
    assert status["local_node_id"] == "node_workstation_rtx3050"
    assert status["total_nodes"] >= 3
    assert status["online_nodes"] >= 1
    assert "RTX" in temp_cluster_mesh.local_alias

    local_node = temp_cluster_mesh.nodes.get("node_workstation_rtx3050")
    assert local_node is not None
    assert local_node.role == "primary"
    assert "vision" in local_node.capabilities
    assert "deep_reasoning" in local_node.capabilities


def test_cluster_node_registration_and_heartbeat(temp_cluster_mesh: ClusterMesh):
    # Register new satellite tablet
    reg_res = temp_cluster_mesh.register_node(
        node_id="node_tablet_ipad",
        alias="Boss iPad Pro",
        role="satellite",
        host="192.168.1.55",
        port=8768,
        capabilities=["touch_ui", "sketch_vision"],
    )
    assert reg_res["success"] is True
    assert "node_tablet_ipad" in temp_cluster_mesh.nodes

    # Send heartbeat
    hb_res = temp_cluster_mesh.record_heartbeat(
        node_id="node_tablet_ipad",
        telemetry={"battery_pct": 88, "active_tasks": 1},
    )
    assert hb_res["success"] is True
    node = temp_cluster_mesh.nodes["node_tablet_ipad"]
    assert node.telemetry["battery_pct"] == 88


def test_cluster_intelligent_task_routing(temp_cluster_mesh: ClusterMesh):
    # Heavy GPU task should route to RTX 5060 workstation node
    optimal_gpu = temp_cluster_mesh.select_optimal_node("vision")
    assert optimal_gpu is not None
    assert optimal_gpu.role == "primary"

    optimal_reason = temp_cluster_mesh.select_optimal_node("deep_reasoning")
    assert optimal_reason is not None
    assert optimal_reason.node_id == "node_workstation_rtx3050"

    # Local dispatch execution
    disp_res = temp_cluster_mesh.dispatch_task(
        task_type="vision",
        payload={"prompt": "test screen", "benchmark": True},
    )
    assert disp_res["success"] is True
    assert disp_res["status"] == "completed"
    assert "RTX" in disp_res.get("acceleration", "")
    assert disp_res["execution_time_ms"] > 0


def test_cluster_remote_peer_dispatch_and_fallback(temp_cluster_mesh: ClusterMesh):
    # Dispatching to satellite peer
    disp_res = temp_cluster_mesh.dispatch_task(
        task_type="ui",
        payload={"action": "open_tab", "url": "https://github.com"},
        target_node="node_laptop_zenbook",
    )
    assert disp_res["success"] is True
    assert disp_res["target_node"] == "node_laptop_zenbook"
    assert disp_res["status"] in ("completed", "delegated")


def test_cluster_state_sync_and_signature(temp_cluster_mesh: ClusterMesh):
    sync_res = temp_cluster_mesh.sync_state(
        context_data={"user": "Boss", "project": "LUMI", "phase": 18}
    )
    assert sync_res["success"] is True
    assert "sync_id" in sync_res
    assert len(sync_res["signature"]) == 64  # SHA256 hex length
    assert sync_res["origin_node"] == "node_workstation_rtx3050"


def test_cluster_tools_registration_and_execution(temp_cluster_mesh: ClusterMesh):
    registry = ToolRegistry()
    active_mesh = register_cluster_tools(registry, mesh=temp_cluster_mesh)
    assert active_mesh is temp_cluster_mesh

    # Check registered tool names
    tool_names = [t.name for t in registry.list_all()]
    assert "cluster_node_status" in tool_names
    assert "mesh_dispatch_task" in tool_names
    assert "sync_cluster_state" in tool_names
    assert "register_mesh_node" in tool_names

    # Execute tools
    status_tool = registry.get("cluster_node_status")
    status = status_tool.handler()
    assert status["total_nodes"] >= 3

    dispatch_tool = registry.get("mesh_dispatch_task")
    disp = dispatch_tool.handler(
        task_type="audio_transcription",
        payload_json=json.dumps({"audio_len_s": 12.5}),
    )
    assert disp["success"] is True

    sync_tool = registry.get("sync_cluster_state")
    sync = sync_tool.handler()
    assert sync["success"] is True

    reg_tool = registry.get("register_mesh_node")
    reg = reg_tool.handler(
        node_id="node_backup_nas",
        alias="Home NAS Storage",
        capabilities_csv="storage,backups",
    )
    assert reg["success"] is True


@pytest.mark.asyncio
async def test_cluster_web_api_endpoints(temp_cluster_mesh: ClusterMesh):
    mock_orc = MagicMock()
    mock_orc.config = {"web": {"allow_remote": True}, "cluster": {"enabled": True}}
    mock_orc.cluster = temp_cluster_mesh
    mock_orc.registry = None
    mock_orc.memory = None
    mock_orc.projects = None
    mock_orc.audit = None
    mock_orc.vault = None
    mock_orc.nexus = None
    mock_orc.sentry = None
    mock_orc.biometrics = None
    mock_orc.synthesizer = None
    mock_orc.finance = None
    mock_orc.reasoner = None
    mock_orc.emotion_voice = None

    app = create_app(mock_orc)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. GET /api/cluster/status
        r_status = await client.get("/api/cluster/status")
        assert r_status.status_code == 200
        d_status = r_status.json()
        assert d_status["total_nodes"] >= 3

        # 2. POST /api/cluster/dispatch
        r_disp = await client.post(
            "/api/cluster/dispatch",
            json={"task_type": "deep_reasoning", "payload": {"problem": "math"}},
        )
        assert r_disp.status_code == 200
        d_disp = r_disp.json()
        assert d_disp["success"] is True

        # 3. POST /api/cluster/sync
        r_sync = await client.post(
            "/api/cluster/sync",
            json={"context_data": {"active": True}},
        )
        assert r_sync.status_code == 200
        d_sync = r_sync.json()
        assert d_sync["success"] is True

        # 4. POST /api/cluster/register
        r_reg = await client.post(
            "/api/cluster/register",
            json={
                "node_id": "node_wearable_watch",
                "alias": "Boss Smartwatch",
                "role": "client",
                "host": "192.168.1.99",
                "port": 8770,
                "capabilities": ["haptic", "notifications"],
            },
        )
        assert r_reg.status_code == 200
        d_reg = r_reg.json()
        assert d_reg["success"] is True

        # 5. POST /api/cluster/heartbeat
        r_hb = await client.post(
            "/api/cluster/heartbeat",
            json={"node_id": "node_wearable_watch", "telemetry": {"battery_pct": 95}},
        )
        assert r_hb.status_code == 200

        # 6. POST /api/cluster/execute
        r_exec = await client.post(
            "/api/cluster/execute",
            json={
                "dispatch_id": "disp_test_123",
                "task_type": "benchmark",
                "payload": {},
                "origin_node": "node_laptop_zenbook",
            },
        )
        assert r_exec.status_code == 200
        d_exec = r_exec.json()
        assert d_exec["status"] == "completed"
