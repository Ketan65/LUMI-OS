"""Cluster Mesh Tools for LUMI (Phase 18).

Provides LLM-callable tools for:
  - cluster_node_status: inspects sovereign cluster topology, RTX 5060 load, and peer status
  - mesh_dispatch_task: offloads compute tasks (vision, transcription, reasoning, compiling) across nodes
  - sync_cluster_state: synchronizes live session context and bookmarks across devices for seamless handoff
  - register_mesh_node: connects and enrolls a new peer device into LUMI's sovereign mesh
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from mesh.cluster import ClusterMesh, get_cluster_mesh
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.tools.cluster")


def register_cluster_tools(
    registry: ToolRegistry,
    mesh: Optional[ClusterMesh] = None,
    config: Optional[Dict[str, Any]] = None,
    notifier: Any = None,
) -> ClusterMesh:
    """Registers sovereign cluster mesh tools into ToolRegistry."""
    active_mesh = mesh or get_cluster_mesh(config=config)

    def cluster_node_status() -> dict:
        """Inspects status of all nodes in LUMI's sovereign compute cluster (RTX 5060 Workstation, Laptop, Mobile)."""
        return active_mesh.get_cluster_status()

    def mesh_dispatch_task(
        task_type: str,
        payload_json: str = "{}",
        target_node: Optional[str] = None,
    ) -> dict:
        """Dispatches a task across the sovereign mesh, intelligently offloading heavy tasks to RTX 5060."""
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) and payload_json.strip() else {}
        except Exception:
            payload = {"raw_payload": payload_json}
        res = active_mesh.dispatch_task(task_type=task_type, payload=payload, target_node=target_node)
        if notifier and res.get("status") == "delegated":
            try:
                notifier.emit("cluster_delegated", f"Mesh: Delegated '{task_type}' to {res.get('target_alias')}")
            except Exception:
                pass
        return res

    def sync_cluster_state(target_node: Optional[str] = None) -> dict:
        """Synchronizes active session state, active swarms, and unread alerts across connected cluster nodes."""
        return active_mesh.sync_state(destination_node=target_node)

    def register_mesh_node(
        node_id: str,
        alias: str,
        role: str = "satellite",
        host: str = "127.0.0.1",
        port: int = 8766,
        capabilities_csv: str = "general",
    ) -> dict:
        """Enrolls or updates a peer device (Laptop, Phone, Tablet) in LUMI's sovereign mesh cluster."""
        caps = [c.strip() for c in capabilities_csv.split(",") if c.strip()]
        return active_mesh.register_node(
            node_id=node_id,
            alias=alias,
            role=role,
            host=host,
            port=port,
            capabilities=caps,
        )

    # Register in ToolRegistry
    registry.register(
        Tool(
            name="cluster_node_status",
            description="Inspects real-time topology, RTX 5060 GPU compute status, and peer connectivity across LUMI's sovereign multi-device mesh.",
            params_schema={"type": "object", "properties": {}},
            handler=cluster_node_status,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="mesh_dispatch_task",
            description="Dispatches heavy compute tasks (vision, transcription, deep reasoning, code compilation) across connected sovereign cluster nodes.",
            params_schema={
                "type": "object",
                "properties": {
                    "task_type": {
                        "type": "string",
                        "description": "Task category: 'vision', 'audio_transcription', 'deep_reasoning', 'code_compilation', 'general'",
                    },
                    "payload_json": {
                        "type": "string",
                        "description": "JSON string containing task arguments, data or payloads",
                        "default": "{}",
                    },
                    "target_node": {
                        "type": "string",
                        "description": "Optional specific node ID (e.g. 'node_workstation_rtx3050'). If omitted, auto-routes to optimal node.",
                    },
                },
                "required": ["task_type"],
            },
            handler=mesh_dispatch_task,
            risk="ask",
        )
    )

    registry.register(
        Tool(
            name="sync_cluster_state",
            description="Synchronizes session context, task queues, and memory bookmarks across cluster devices for seamless cross-device handoff.",
            params_schema={
                "type": "object",
                "properties": {
                    "target_node": {
                        "type": "string",
                        "description": "Optional destination node ID. If omitted, syncs across all online peers.",
                    }
                },
            },
            handler=sync_cluster_state,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="register_mesh_node",
            description="Enrolls or updates a peer device (satellite laptop, mobile terminal, home server) into LUMI's sovereign cluster network.",
            params_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "Unique identifier for the device (e.g. 'node_laptop_zenbook')"},
                    "alias": {"type": "string", "description": "Friendly label (e.g. 'Boss Satellite Zenbook')"},
                    "role": {"type": "string", "enum": ["primary", "satellite", "client"], "default": "satellite"},
                    "host": {"type": "string", "default": "127.0.0.1"},
                    "port": {"type": "integer", "default": 8766},
                    "capabilities_csv": {"type": "string", "default": "general", "description": "Comma-separated capabilities (e.g. 'ui,web_browsing,local_cli')"},
                },
                "required": ["node_id", "alias"],
            },
            handler=register_mesh_node,
            risk="ask",
        )
    )

    return active_mesh
