"""Deep-Reasoner Tools for LUMI (Phase 16).

Provides LLM-callable tools for:
  - deep_reason: performs Monte-Carlo tree search, branching hypothesis generation, and step verification
  - verify_hypothesis: self-critiques and scores a single proposed solution hypothesis
  - get_reasoning_history: retrieves recent reasoning sessions and verification trees
"""

from __future__ import annotations

import logging
from typing import Any

from brain.mcts_reasoner import DeepReasoner, get_deep_reasoner
from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.tools.reasoner")


def register_reasoner_tools(
    registry: ToolRegistry,
    reasoner: DeepReasoner | None = None,
    brain: Any = None,
) -> DeepReasoner:
    """Registers deep reasoning, tree search, and verification tools into ToolRegistry."""
    active_reasoner = reasoner or get_deep_reasoner(brain=brain)

    def deep_reason(
        problem: str,
        depth: int = 2,
        branches: int = 3,
        domain: str = "general",
    ) -> dict:
        """Executes deep test-time reasoning across divergent hypothesis branches, scoring each for correctness and scalability."""
        return active_reasoner.explore(
            problem=problem,
            depth=depth,
            branches=branches,
            domain=domain,
        )

    def verify_hypothesis(hypothesis: str, problem_context: str = "") -> dict:
        """Evaluates a single proposed solution or algorithmic hypothesis against edge cases and performance trade-offs."""
        return active_reasoner.verify_hypothesis(
            hypothesis=hypothesis,
            problem_context=problem_context,
        )

    def get_reasoning_history(limit: int = 5) -> list[dict]:
        """Returns the most recent extended reasoning sessions and their decision trees."""
        return active_reasoner.get_history(limit=limit)

    # Register in ToolRegistry
    registry.register(Tool(
        name="deep_reason",
        description="MCTS-inspired extended test-time thinking engine: explores multi-branch solution trees, evaluates edge cases, and selects the optimal path.",
        params_schema={
            "type": "object",
            "properties": {
                "problem": {"type": "string", "description": "The complex problem, algorithm, or architecture to reason through"},
                "depth": {"type": "integer", "default": 2, "description": "Depth of exploration tree"},
                "branches": {"type": "integer", "default": 3, "description": "Number of divergent solution hypotheses to evaluate"},
                "domain": {"type": "string", "default": "general", "description": "Problem domain (e.g. 'architecture', 'database', 'algorithm')"},
            },
            "required": ["problem"],
        },
        handler=deep_reason,
        risk="auto",
    ))

    registry.register(Tool(
        name="verify_hypothesis",
        description="Critiques and scores an individual solution hypothesis for correctness, efficiency, and edge-case boundaries.",
        params_schema={
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string", "description": "The specific solution proposal to verify"},
                "problem_context": {"type": "string", "description": "Context and constraints of the problem"},
            },
            "required": ["hypothesis"],
        },
        handler=verify_hypothesis,
        risk="auto",
    ))

    registry.register(Tool(
        name="get_reasoning_history",
        description="Retrieves recent extended reasoning session trees and decision rationales.",
        params_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5, "description": "Number of past reasoning sessions to retrieve"},
            },
        },
        handler=get_reasoning_history,
        risk="auto",
    ))

    return active_reasoner
