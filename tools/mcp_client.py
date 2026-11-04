"""Model Context Protocol (MCP) Client Layer for LUMI.

Provides a synchronous bridge over an asyncio background thread, connecting LUMI
to external tools (e.g. Google Workspace, Desktop Automation, GitHub, custom MCP servers)
via the official MCP python SDK.

Security & Safety:
  - All external MCP tools are registered with prefix `mcp__{server}__{tool}`.
  - Default policy risk is "ask" (never runs without explicit confirmation).
  - External MCP tool outputs are automatically treated as UNTRUSTED by the orchestrator,
    tainting the turn so prompt injection from emails/calendar cannot silently write files.
  - Server crash, disconnect, or timeout produces friendly messages without crashing LUMI.
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Any, Callable

from tools.registry import Tool, ToolRegistry


class McpBridge:
    """Manages a background asyncio event loop thread for async MCP operations."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="LumiMcpBridge")
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if not self._running:
                self._running = True
                self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def stop(self) -> None:
        with self._lock:
            if self._running:
                self._running = False
                self._loop.call_soon_threadsafe(self._loop.stop)

    def run_coro(self, coro, timeout: float = 30.0) -> Any:
        self.start()
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)


class McpServerInstance:
    """Represents a single stdio MCP server process connection."""

    def __init__(self, name: str, command: str, args: list[str] | None = None,
                 env: dict[str, str] | None = None, enabled: bool = True) -> None:
        self.name = name
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.enabled = enabled
        self.status = "disconnected"
        self.error_msg = ""
        self.tools: list[dict] = []
        self._req_q: asyncio.Queue | None = None
        self._worker_task: asyncio.Task | None = None
        self._session = None

    async def _worker(self, started_evt: asyncio.Event) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        full_env = os.environ.copy()
        full_env.update(self.env)
        params = StdioServerParameters(command=self.command, args=self.args, env=full_env)

        try:
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    self._session = session
                    await session.initialize()
                    tools_res = await session.list_tools()
                    self.tools = [
                        {
                            "name": t.name,
                            "description": t.description or "",
                            "params_schema": t.inputSchema or {},
                        }
                        for t in tools_res.tools
                    ]
                    self.status = "connected"
                    self.error_msg = ""
                    started_evt.set()

                    while True:
                        req_type, payload, resp_future = await self._req_q.get()
                        if req_type == "call_tool":
                            try:
                                t_name = payload["tool"]
                                t_args = payload["args"]
                                res = await session.call_tool(t_name, t_args)
                                texts: list[str] = []
                                for c in (res.content or []):
                                    if hasattr(c, "text"):
                                        texts.append(c.text)
                                    elif isinstance(c, dict) and "text" in c:
                                        texts.append(c["text"])
                                    else:
                                        texts.append(str(c))
                                out_text = "\n".join(texts) if texts else "(Empty response)"
                                if getattr(res, "isError", False):
                                    out_text = f"Error: {out_text}"
                                if not resp_future.done():
                                    resp_future.set_result(out_text)
                            except Exception as ex:
                                if not resp_future.done():
                                    resp_future.set_exception(ex)
                        elif req_type == "stop":
                            if not resp_future.done():
                                resp_future.set_result(True)
                            break
        except Exception as exc:
            self.status = "error"
            self.error_msg = str(exc)
            started_evt.set()
            if self._req_q:
                while not self._req_q.empty():
                    _, _, resp_fut = self._req_q.get_nowait()
                    if not resp_fut.done():
                        resp_fut.set_exception(exc)

    async def _start_coro(self) -> None:
        self._req_q = asyncio.Queue()
        started_evt = asyncio.Event()
        self._worker_task = asyncio.create_task(self._worker(started_evt))
        await started_evt.wait()

    async def _call_tool_coro(self, tool_name: str, args: dict) -> str:
        if self.status != "connected" or not self._req_q:
            raise RuntimeError(f"MCP server '{self.name}' is not connected (status: {self.status})")
        loop = asyncio.get_running_loop()
        resp_future = loop.create_future()
        await self._req_q.put(("call_tool", {"tool": tool_name, "args": args}, resp_future))
        return await resp_future

    async def _stop_coro(self) -> None:
        if self._req_q and self.status == "connected":
            loop = asyncio.get_running_loop()
            resp_future = loop.create_future()
            await self._req_q.put(("stop", {}, resp_future))
            try:
                await asyncio.wait_for(resp_future, timeout=2.0)
            except Exception:
                pass
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
        self.status = "disconnected"
        self._session = None


class McpManager:
    """Orchestrates all MCP servers, tool registration, and lifecycle."""

    def __init__(self, bridge: McpBridge | None = None) -> None:
        self.bridge = bridge or McpBridge()
        self.servers: dict[str, McpServerInstance] = {}
        self.registry: ToolRegistry | None = None
        self._registered_tool_names: dict[str, set[str]] = {}

    def init_from_config(self, config: dict, registry: ToolRegistry) -> None:
        self.registry = registry
        servers_cfg = dict(config.get("mcp_servers") or {})
        for sname, scfg in servers_cfg.items():
            if not isinstance(scfg, dict):
                continue
            cmd = scfg.get("command") or ""
            args = list(scfg.get("args") or [])
            env = dict(scfg.get("env") or {})
            enabled = bool(scfg.get("enabled", False))
            self.servers[sname] = McpServerInstance(sname, cmd, args, env, enabled)
            if enabled:
                self.start_server(sname)

    def start_server(self, name: str) -> tuple[bool, str]:
        server = self.servers.get(name)
        if not server:
            return False, f"Server '{name}' not found."

        try:
            self.bridge.run_coro(server._start_coro(), timeout=15.0)
            if server.status == "connected":
                self._register_server_tools(server)
                return True, f"Server '{name}' connected ({len(server.tools)} tools available)."
            return False, f"Server '{name}' failed to start: {server.error_msg}"
        except Exception as exc:
            server.status = "error"
            server.error_msg = str(exc)
            return False, f"Error starting '{name}': {exc}"

    def stop_server(self, name: str) -> tuple[bool, str]:
        server = self.servers.get(name)
        if not server:
            return False, f"Server '{name}' not found."

        self._unregister_server_tools(name)
        try:
            self.bridge.run_coro(server._stop_coro(), timeout=5.0)
            return True, f"Server '{name}' stopped."
        except Exception as exc:
            return False, f"Error stopping '{name}': {exc}"

    def call_tool(self, server_name: str, tool_name: str, **args) -> str:
        server = self.servers.get(server_name)
        if not server:
            return f"MCP server '{server_name}' not found."
        try:
            return self.bridge.run_coro(server._call_tool_coro(tool_name, args), timeout=30.0)
        except Exception as exc:
            return f"MCP tool execution failed ({server_name}/{tool_name}): {exc}"

    def _register_server_tools(self, server: McpServerInstance) -> None:
        if not self.registry:
            return
        if server.name not in self._registered_tool_names:
            self._registered_tool_names[server.name] = set()

        for t in server.tools:
            lumi_name = f"mcp__{server.name}__{t['name']}"
            desc = f"[{server.name} MCP] {t.get('description', t['name'])}"
            params = t.get("params_schema") or {"type": "object", "properties": {}}

            # Handler closure
            def make_handler(s_name: str, t_orig_name: str):
                return lambda **kwargs: self.call_tool(s_name, t_orig_name, **kwargs)

            tool_obj = Tool(
                name=lumi_name,
                description=desc,
                params_schema=params,
                handler=make_handler(server.name, t["name"]),
                risk="ask",  # Default safety: always ask for MCP tools
            )
            self.registry.register(tool_obj)
            self._registered_tool_names[server.name].add(lumi_name)

    def _unregister_server_tools(self, server_name: str) -> None:
        if not self.registry:
            return
        names = self._registered_tool_names.pop(server_name, set())
        for nm in names:
            if nm in self.registry._tools:
                del self.registry._tools[nm]

    def list_servers(self) -> list[dict]:
        res: list[dict] = []
        for name, s in self.servers.items():
            res.append({
                "name": name,
                "command": s.command,
                "enabled": s.enabled,
                "status": s.status,
                "error": s.error_msg,
                "tools_count": len(s.tools),
                "tools": [t["name"] for t in s.tools],
            })
        return res

    def status_text(self) -> str:
        if not self.servers:
            return "Koi MCP servers configured nahi hain (config.yaml me mcp_servers check karo)."
        lines: list[str] = [f"MCP Servers ({len(self.servers)}):"]
        for s in self.list_servers():
            badge = "🟢 CONNECTED" if s["status"] == "connected" else f"⚪ {s['status'].upper()}"
            lines.append(f"- **{s['name']}** [{badge}]: {s['tools_count']} tools")
            if s["tools"]:
                lines.append(f"  Tools: {', '.join(s['tools'])}")
            if s["error"]:
                lines.append(f"  Error: {s['error']}")
        return "\n".join(lines)


# Global singleton instance
_GLOBAL_MCP_MANAGER: McpManager | None = None


def get_mcp_manager() -> McpManager:
    global _GLOBAL_MCP_MANAGER
    if _GLOBAL_MCP_MANAGER is None:
        _GLOBAL_MCP_MANAGER = McpManager()
    return _GLOBAL_MCP_MANAGER
