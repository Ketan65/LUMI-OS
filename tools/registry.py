"""Tool registry — dataclass tools + LLM schema export (registry pattern)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    params_schema: dict          # JSON schema for LLM tool-calling
    handler: Callable[..., Any]
    risk: str = "auto"           # auto | ask | block (policy default)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        return list(self._tools.values())

    def to_llm_schemas(self) -> list[dict]:
        return [
            {"type": "function", "function": {
                "name": t.name, "description": t.description,
                "parameters": t.params_schema}}
            for t in self._tools.values()
        ]
