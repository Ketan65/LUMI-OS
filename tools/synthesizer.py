"""Kernel-Synthesis Tools for LUMI (Phase 14).

Provides LLM-callable tools for:
  - forge_custom_tool: compiles, tests in sandbox, and dynamically injects new tools into LUMI's brain
  - list_synthesized_tools: lists dynamic self-compiled tools and execution metrics
  - revoke_synthesized_tool: unloads and revokes synthesized tools
  - benchmark_synthesized_tool: measures execution latency of a dynamic tool
"""

from __future__ import annotations

import logging
from typing import Any

from core.synthesizer import ToolSynthesizer, get_tool_synthesizer
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.tools.synthesizer")


def register_synthesizer_tools(
    registry: ToolRegistry,
    synthesizer: ToolSynthesizer | None = None,
    brain: Any = None,
) -> ToolSynthesizer:
    """Registers tool synthesis and dynamic compilation tools into ToolRegistry."""
    active_synth = synthesizer or get_tool_synthesizer(brain=brain, registry=registry)
    active_synth.registry = registry

    def forge_custom_tool(
        tool_name: str,
        description: str,
        python_code: str,
        test_code: str,
        params_schema: dict | None = None,
    ) -> dict:
        """Forges, sandbox tests, and dynamically hot-injects a new Python tool into LUMI's active runtime."""
        schema = params_schema or {"type": "object", "properties": {}}
        return active_synth.forge_tool(
            tool_name=tool_name,
            description=description,
            python_code=python_code,
            test_code=test_code,
            params_schema=schema,
            risk="auto",
        )

    def list_synthesized_tools() -> list[dict]:
        """Lists all dynamically synthesized tools, their execution statistics, latency, and status."""
        return active_synth.list_tools()

    def revoke_synthesized_tool(tool_name: str) -> dict:
        """Revokes and unregisters a synthesized tool from LUMI's active runtime."""
        success = active_synth.revoke_tool(tool_name, registry)
        return {
            "success": success,
            "tool_name": tool_name,
            "status": "REVOKED" if success else "NOT_FOUND",
            "message": f"Tool '{tool_name}' successfully revoked." if success else f"Tool '{tool_name}' not found.",
        }

    def benchmark_synthesized_tool(tool_name: str, sample_args: dict | None = None) -> dict:
        """Measures average, minimum, and maximum execution latency of a synthesized tool."""
        return active_synth.benchmark_tool(tool_name=tool_name, sample_args=sample_args)

    def auto_forge_tool(tool_name: str, specification: str) -> dict:
        """Autonomously writes Python code + pytest unit tests from a natural-language specification, self-heals in sandbox, and hot-injects the tool."""
        return active_synth.auto_forge_from_spec(tool_name=tool_name, specification=specification)

    registry.register(Tool(
        name="auto_forge_tool",
        description="Autonomously compiles, tests, self-heals, and hot-injects a brand new Python tool from a natural-language specification.",
        params_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Identifier name of the new tool (snake_case)"},
                "specification": {"type": "string", "description": "Natural-language specification of inputs, behavior, and outputs"},
            },
            "required": ["tool_name", "specification"],
        },
        handler=auto_forge_tool,
        risk="auto",
    ))

    # Register in ToolRegistry
    registry.register(Tool(
        name="forge_custom_tool",
        description="Autonomous tool compiler: writes Python code, verifies unit tests in sandbox, and dynamically injects the new tool into LUMI.",
        params_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Identifier name of the new tool (e.g. 'epub_to_md')"},
                "description": {"type": "string", "description": "Clear explanation of what the tool does"},
                "python_code": {"type": "string", "description": "Full Python code implementing the tool handler"},
                "test_code": {"type": "string", "description": "Pytest unit test code verifying the handler behavior"},
                "params_schema": {"type": "object", "description": "JSON schema definition for tool arguments"},
            },
            "required": ["tool_name", "description", "python_code", "test_code"],
        },
        handler=forge_custom_tool,
        risk="ask",
    ))

    registry.register(Tool(
        name="list_synthesized_tools",
        description="Lists all dynamically compiled custom tools, their execution statistics, and latency profiles.",
        params_schema={"type": "object", "properties": {}},
        handler=list_synthesized_tools,
        risk="auto",
    ))

    registry.register(Tool(
        name="revoke_synthesized_tool",
        description="Unloads and deactivates a synthesized tool from LUMI's active brain.",
        params_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the synthesized tool to revoke"},
            },
            "required": ["tool_name"],
        },
        handler=revoke_synthesized_tool,
        risk="ask",
    ))

    registry.register(Tool(
        name="benchmark_synthesized_tool",
        description="Benchmarks latency and execution stability of a synthesized custom tool.",
        params_schema={
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Name of the tool to benchmark"},
                "sample_args": {"type": "object", "description": "Optional dictionary of test arguments"},
            },
            "required": ["tool_name"],
        },
        handler=benchmark_synthesized_tool,
        risk="auto",
    ))

    # Also automatically restore any previously synthesized active tools at boot
    active_synth.load_all(registry)

    return active_synth
