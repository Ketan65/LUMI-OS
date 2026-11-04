"""Tool wrapper for LUMI NEXUS-IOT (Phase 12: Smart Workstation & Hardware IoT Hub)."""

from __future__ import annotations

import json
from typing import Any

from core.nexus import NexusHub
from tools.registry import Tool, ToolRegistry


def register_nexus_tools(registry: ToolRegistry, hub: NexusHub | None = None) -> NexusHub:
    """Registers workstation_focus, scan_lan_devices, and iot_webhook tools into ToolRegistry."""
    active_hub = hub or NexusHub()

    def workstation_focus(preset: str = "code_sprint") -> str:
        """Sets workstation ambient mode (code_sprint, presentation, cinema, chill, reset)."""
        res = active_hub.set_focus_preset(preset)
        if not res.get("ok"):
            return f"❌ {res.get('error')}"
        return (
            f"⚡ Workstation Mode Activated: **{res['preset'].upper()}**\n"
            f"- {res['description']}\n"
            f"- Audio Level Target: {res['audio_level']}%\n"
            f"- Do Not Disturb (DND): {'ON' if res['dnd'] else 'OFF'}"
        )

    def scan_lan_devices(subnet: str = "auto") -> str:
        """Scans local subnet for active connected devices, smart hubs, and gateways."""
        devices = active_hub.scan_lan(subnet_prefix=subnet)
        lines = [f"### 📡 NEXUS Local Network Discovery ({len(devices)} active devices)", ""]
        for d in devices:
            lines.append(f"- **{d.hostname}** (`{d.ip}`) — Response: {d.response_time_ms}ms")
        return "\n".join(lines)

    def iot_webhook(url: str, payload_json: str = "{}") -> str:
        """Dispatches an HTTP trigger to a smart home webhook or local IoT service (Home Assistant, Shelly, etc.)."""
        if not url or not url.strip():
            return "Please provide a valid webhook URL."
        try:
            payload = json.loads(payload_json) if payload_json.strip() else {}
        except Exception:
            payload = {"raw": payload_json}

        res = active_hub.trigger_webhook(url.strip(), payload)
        if res.get("ok"):
            return f"✅ IoT Webhook Triggered ({url}) — HTTP {res['status_code']}: {res.get('response', 'OK')}"
        return f"❌ IoT Webhook Failed ({url}): {res.get('error')}"

    registry.register(
        Tool(
            name="workstation_focus",
            description="Controls workstation ambient environment with focus presets: 'code_sprint', 'presentation', 'cinema', 'chill', 'reset'.",
            params_schema={
                "type": "object",
                "properties": {
                    "preset": {
                        "type": "string",
                        "description": "Preset name: code_sprint | presentation | cinema | chill | reset",
                        "enum": ["code_sprint", "presentation", "cinema", "chill", "reset"],
                    }
                },
                "required": ["preset"],
            },
            handler=workstation_focus,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="scan_lan_devices",
            description="Scans the local area network to discover connected smart devices, phones, laptops, and router.",
            params_schema={
                "type": "object",
                "properties": {
                    "subnet": {
                        "type": "string",
                        "description": "Subnet prefix (e.g. '192.168.1' or 'auto'). Default is 'auto'.",
                    }
                },
            },
            handler=scan_lan_devices,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="iot_webhook",
            description="Sends a webhook trigger to a local or cloud IoT device, smart home endpoint, or mobile notification service.",
            params_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The webhook URL endpoint.",
                    },
                    "payload_json": {
                        "type": "string",
                        "description": "JSON string payload to send with the POST request.",
                    },
                },
                "required": ["url"],
            },
            handler=iot_webhook,
            risk="ask",
        )
    )

    return active_hub
