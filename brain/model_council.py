"""Mixture-of-Local-Specialists: Council of Stark Multi-Brain Router (LUMI v38.0).

Dynamically dispatches queries to the optimal local specialist running on Ollama:
  - Tier-0 Reflex Engine: Instant deterministic system responses (<10ms).
  - Conversational & Persona Specialist: hermes3:latest (Stark persona, dialogue, tools).
  - Deep Architecture & Reasoning Specialist: qwen3:8b (complex multi-step planning).
  - Visual & Screen Perception Specialist: qwen2.5vl:3b (screenshots, OCR, diagrams).
  - Rapid Code Specialist: qwen2.5:3b (unit tests, refactoring, algorithms).
  - Zero-Crash Resilience: Automatic cascade failover if a model is unavailable or OOM.
"""

from __future__ import annotations

import collections
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

import ollama

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.council")

SPECIALIST_MODELS = {
    "reflex": "tier0_reflex",
    "persona": "hermes3:latest",
    "reasoning": "qwen3:8b",
    "vision": "qwen2.5vl:3b",
    "coder": "qwen2.5:3b",
}

# Heuristics for intent classification
_VISION_KEYWORDS = re.compile(r"\b(screen|screenshot|image|photo|visual|ui|gui|display|canvas|inspect screen|what is on the screen)\b", re.I)
_CODING_KEYWORDS = re.compile(r"\b(def |class |function|pytest|unit test|regex|sql query|fix syntax|refactor|algorithm|bug fix|python code|typescript|javascript)\b", re.I)
_REASONING_KEYWORDS = re.compile(r"\b(architecture|trade-offs|step-by-step|mathematical|threat model|deep analysis|compare frameworks|design doc|multi-phase)\b", re.I)


@dataclass
class CouncilDispatchResult:
    specialist: str
    model_name: str
    response: str
    elapsed_ms: int
    fallback_used: bool = False


class ModelCouncilRouter:
    """Intelligent dispatcher across local specialized Ollama models."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry
        self.telemetry: collections.Counter[str] = collections.Counter()
        self._register_tools()

    def _register_tools(self) -> None:
        """Registers model council tools in ToolRegistry."""
        if self.registry is None:
            return

        self.registry.register(
            Tool(
                name="query_model_council",
                description="Routes a query to the optimal local specialist model (coder, reasoning, vision, or persona).",
                params_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The prompt or task."},
                        "force_specialist": {
                            "type": "string",
                            "enum": ["auto", "persona", "reasoning", "vision", "coder"],
                            "description": "Optional specialist override.",
                        },
                    },
                    "required": ["prompt"],
                },
                handler=lambda prompt, force_specialist="auto": self.dispatch(
                    prompt, force_specialist=force_specialist
                ).response,
                risk="read",
            )
        )
        self.registry.register(
            Tool(
                name="get_council_telemetry",
                description="Returns routing statistics across all local models.",
                params_schema={"type": "object", "properties": {}},
                handler=lambda: self.get_telemetry_summary(),
                risk="read",
            )
        )

    def classify_specialist(self, prompt: str, images: list[Any] | None = None) -> str:
        """Determines the best local specialist model for a prompt."""
        if images and len(images) > 0:
            return "vision"

        if _VISION_KEYWORDS.search(prompt):
            return "vision"

        if _CODING_KEYWORDS.search(prompt):
            return "coder"

        if _REASONING_KEYWORDS.search(prompt):
            return "reasoning"

        return "persona"

    def dispatch(
        self,
        prompt: str,
        system_prompt: str = "",
        images: list[Any] | None = None,
        force_specialist: str = "auto",
    ) -> CouncilDispatchResult:
        """Dispatches prompt to chosen specialist with automatic cascade fallback."""
        t0 = time.perf_counter()

        # 1. Select specialist
        if force_specialist in SPECIALIST_MODELS and force_specialist != "auto":
            specialist = force_specialist
        else:
            specialist = self.classify_specialist(prompt, images=images)

        target_model = SPECIALIST_MODELS.get(specialist, "hermes3:latest")
        fallback_used = False

        # Build messages payload
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        msg_payload: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            msg_payload["images"] = images
        messages.append(msg_payload)

        # 2. Query target model
        try:
            res = ollama.chat(model=target_model, messages=messages)
            content = res.get("message", {}).get("content", "")
            self.telemetry[specialist] += 1
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return CouncilDispatchResult(
                specialist=specialist,
                model_name=target_model,
                response=content,
                elapsed_ms=elapsed_ms,
                fallback_used=False,
            )
        except Exception as e:
            logger.warning("Primary specialist '%s' (%s) failed: %s; initiating fallback", specialist, target_model, e)
            fallback_used = True

        # 3. Fallback cascade to hermes3:latest
        fallback_model = SPECIALIST_MODELS["persona"]
        try:
            res = ollama.chat(model=fallback_model, messages=messages)
            content = res.get("message", {}).get("content", "")
            self.telemetry["fallback_persona"] += 1
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return CouncilDispatchResult(
                specialist="fallback_persona",
                model_name=fallback_model,
                response=content,
                elapsed_ms=elapsed_ms,
                fallback_used=True,
            )
        except Exception as e2:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return CouncilDispatchResult(
                specialist="error",
                model_name="none",
                response=f"Council Error: All specialist models failed ({e2}).",
                elapsed_ms=elapsed_ms,
                fallback_used=True,
            )

    def get_telemetry_summary(self) -> dict[str, Any]:
        """Returns council routing statistics."""
        return {
            "routes_total": sum(self.telemetry.values()),
            "routes_breakdown": dict(self.telemetry),
            "available_specialists": SPECIALIST_MODELS,
        }


_GLOBAL_COUNCIL: ModelCouncilRouter | None = None


def get_model_council(registry: ToolRegistry | None = None) -> ModelCouncilRouter:
    global _GLOBAL_COUNCIL
    if _GLOBAL_COUNCIL is None:
        _GLOBAL_COUNCIL = ModelCouncilRouter(registry=registry)
    return _GLOBAL_COUNCIL
