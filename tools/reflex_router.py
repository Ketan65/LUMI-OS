"""Tool bindings for LUMI ReflexRouter (Department 1: Speed, Streaming & Reflex Routing).

Registers:
- `reflex_prune_preview`: Simulates Tier-0 reflex detection and Top-K semantic tool
  pruning for a given user query against all currently registered tools.
- `reflex_router_telemetry`: Reports cumulative Tier-0 reflex hit rates, average tools
  pruned per turn, schema reduction percentage, and estimated token savings.
"""

from __future__ import annotations

from core.reflex_router import ReflexRouter, get_reflex_router
from tools.registry import Tool, ToolRegistry


def register_reflex_router_tools(
    registry: ToolRegistry,
    router: ReflexRouter | None = None,
) -> ReflexRouter:
    """Registers `reflex_prune_preview` and `reflex_router_telemetry` in `ToolRegistry`."""
    rx = router or get_reflex_router()

    def reflex_prune_preview(query: str, top_k: int = 14) -> str:
        """Previews Tier-0 reflex matching and Top-K semantic tool pruning for a query."""
        q = (query or "").strip()
        if not q:
            return "Please provide a non-empty `query` string to preview reflex routing."
        try:
            k = max(4, min(40, int(top_k)))
        except (TypeError, ValueError):
            k = 14

        all_specs = registry.to_llm_schemas()
        tier0 = rx.check_tier0_reflex(q, context={"tools_count": len(all_specs)})
        selected = rx.select_relevant_tools(q, all_specs, top_k=k)
        selected_names = [
            (s.get("function") or {}).get("name", "")
            for s in selected
            if isinstance(s, dict)
        ]
        pruned_count = max(0, len(all_specs) - len(selected_names))
        reduction_pct = (
            round((pruned_count / len(all_specs)) * 100.0, 1) if all_specs else 0.0
        )

        lines = [
            f"### ⚡ Reflex Router Prune Preview",
            f"- **Query:** `{q}`",
            f"- **Tier-0 Deterministic Reflex:** "
            + (
                f"✅ MATCHED (`intent={tier0['intent']}`, `{tier0.get('latency_ms', 0)}ms`) → {tier0['response']}"
                if tier0 and tier0.get("matched")
                else "⏭️ Bypassed (routes to Top-K Pruned LLM / Tool Loop)"
            ),
            f"- **Total Registered Tools:** `{len(all_specs)}`",
            f"- **Pruned Active Tools (`top_k={k}`):** `{len(selected_names)}` "
            f"(`-{pruned_count}` schemas pruned, **{reduction_pct}%** reduction, ~`{pruned_count * 85}` tokens saved)",
            f"- **Selected Tool Schemas:** {', '.join(f'`{n}`' for n in selected_names)}",
        ]
        return "\n".join(lines)

    def reflex_router_telemetry() -> str:
        """Returns live performance telemetry from the ReflexRouter."""
        stats = rx.get_router_telemetry()
        lines = [
            "### 🚀 Reflex Router Live Telemetry (RTX 5060 8B Optimization)",
            f"- **Total Queries Evaluated:** `{stats['total_queries']}`",
            f"- **Tier-0 Instant Reflex Hits (<5ms):** `{stats['tier0_reflex_hits']}` (`{stats['tier0_hit_rate_pct']}%` hit rate)",
            f"- **Last Tier-0 Intent:** `{stats['last_intent']}`",
            f"- **Tool Prune Invocations:** `{stats['tool_prune_calls']}`",
            f"- **Avg Tools (Before → After):** `{stats['avg_tools_before']}` → `{stats['avg_tools_after']}` "
            f"(avg `{stats['avg_tools_pruned']}` pruned/turn)",
            f"- **Prompt Schema Bloat Reduction:** **{stats['schema_reduction_pct']}%**",
            f"- **Estimated Prompt Tokens Saved:** `~{stats['estimated_tokens_saved']}` tokens",
        ]
        if stats.get("last_selected_tools"):
            lines.append(
                f"- **Last Selected Toolset:** {', '.join(f'`{n}`' for n in stats['last_selected_tools'])}"
            )
        return "\n".join(lines)

    registry.register(
        Tool(
            name="reflex_prune_preview",
            description=(
                "Previews Tier-0 deterministic reflex detection and Dynamic Top-K semantic "
                "tool pruning for a user query, showing selected tools and token savings."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User query to test against Tier-0 reflex and Top-K tool pruner",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum number of tool schemas to retain (default 14)",
                    },
                },
                "required": ["query"],
            },
            handler=reflex_prune_preview,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="reflex_router_telemetry",
            description=(
                "Returns cumulative telemetry for LUMI's ReflexRouter including Tier-0 reflex "
                "hits, average tools pruned per turn, and estimated prompt token savings."
            ),
            params_schema={
                "type": "object",
                "properties": {},
            },
            handler=reflex_router_telemetry,
            risk="auto",
        )
    )

    return rx
