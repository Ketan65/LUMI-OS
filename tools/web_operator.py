"""Tool wrapper for LUMI WEB-OPERATOR (Phase 11: Autonomous Browser Agent)."""

from __future__ import annotations

from typing import Any

from core.web_operator import WebOperator
from tools.registry import Tool, ToolRegistry


def register_web_operator_tools(registry: ToolRegistry, orchestrator: Any = None) -> WebOperator:
    """Registers browse_page and tech_briefing tools into ToolRegistry."""
    brain = getattr(orchestrator, "brain", None) if orchestrator else None
    op = WebOperator(brain=brain)

    def browse_page(url: str, summarize: bool = True) -> str:
        """Autonomously fetches and reads web page content, stripping noise, extracting text and key links."""
        if not url or not url.strip():
            return "Please provide a valid URL to browse."
        if summarize:
            return op.summarize_page(url.strip())
        page = op.fetch_page(url.strip())
        return f"### {page.title}\n\n{page.text}"

    def tech_briefing() -> str:
        """Pulls and summarizes top trending tech and AI stories from online aggregators."""
        return op.fetch_tech_briefing()

    registry.register(
        Tool(
            name="browse_page",
            description="Autonomously fetches and reads a web page, converting HTML into clean readable text with key links.",
            params_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The website URL to fetch and read.",
                    },
                    "summarize": {
                        "type": "boolean",
                        "description": "Whether to return a structured intelligence briefing (default true).",
                    },
                },
                "required": ["url"],
            },
            handler=browse_page,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="tech_briefing",
            description="Fetches current top tech, AI, and developer news trends from HackerNews and tech aggregators.",
            params_schema={
                "type": "object",
                "properties": {},
            },
            handler=tech_briefing,
            risk="auto",
        )
    )

    return op
