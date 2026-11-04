"""Deep Research tools for LUMI."""

from __future__ import annotations

from typing import Any

from core.researcher import DeepResearcher
from tools.registry import Tool, ToolRegistry


def register_deep_research_tools(
    registry: ToolRegistry,
    workspace_root: str = "workspace",
    brain: Any = None,
) -> DeepResearcher:
    researcher = DeepResearcher(workspace_root=workspace_root, brain=brain)

    def deep_web_research(topic: str, max_sources: int = 4) -> str:
        """Executes deep multi-query web search, reads sources, and compiles an in-depth cited Markdown dossier."""
        res = researcher.conduct_research(topic, max_sources=max_sources)
        return (
            f"✅ Deep Research Complete for '{res['topic']}' ({res['sources_count']} sources analyzed in {res['elapsed_ms']}ms):\n\n"
            f"📄 Dossier saved to: {res['dossier_file']}\n\n"
            f"{res['dossier_markdown'][:2000]}\n\n[...Full dossier preserved in file]"
        )

    registry.register(Tool(
        name="deep_web_research",
        description="Autonomous multi-query deep web researcher: crawls multiple sources, extracts paragraphs, and generates a structured cited Markdown dossier.",
        params_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "The complex research topic, question, or technology to investigate."},
                "max_sources": {"type": "integer", "description": "Number of distinct sources to analyze (default 4).", "default": 4},
            },
            "required": ["topic"],
        },
        handler=deep_web_research,
        risk="auto",
    ))

    return researcher
