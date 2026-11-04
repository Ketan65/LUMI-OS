"""Tool bindings for LUMI Cognitive Graph & Temporal Memory Palace (Phase 24)."""

from __future__ import annotations

from typing import Any

from core.cognitive_graph import CognitiveGraph
from tools.registry import Tool, ToolRegistry


def register_cognitive_graph_tools(
    registry: ToolRegistry,
    db_path: str = "data/lumi.db",
    brain: Any = None,
) -> CognitiveGraph:
    graph = CognitiveGraph(db_path=db_path, brain=brain)

    def graph_remember_relation(
        source: str,
        relation: str,
        target: str,
        evidence: str = "",
        source_type: str = "Entity",
        target_type: str = "Entity",
    ) -> str:
        """Stores a directed semantic/causal relationship in LUMI's Temporal Knowledge Graph."""
        res = graph.upsert_edge(
            source_label=source,
            relation=relation,
            target_label=target,
            evidence=evidence,
            source_type=source_type,
            target_type=target_type,
        )
        return (
            f"🧠 Cognitive Graph Updated:\n"
            f"  `{res['source']}` --[{res['relation']}]--> `{res['target']}` "
            f"(weight={res['weight']}, evidence='{res['evidence']}')"
        )

    def graph_query_neighborhood(entity: str, max_hops: int = 2) -> str:
        """Queries the multi-hop knowledge graph neighborhood around an entity."""
        res = graph.query_neighborhood(entity, max_hops=max(1, min(3, int(max_hops))))
        if not res["nodes"]:
            return f"No knowledge graph nodes matched '{entity}'."
        lines = [
            f"### 🕸️ Cognitive Graph Subgraph: `{entity}` ({len(res['nodes'])} nodes, {len(res['edges'])} edges)",
            "",
            "**Connected Relations:**",
        ]
        for e in res["edges"]:
            ev = f" — *{e['evidence']}*" if e.get("evidence") else ""
            lines.append(f"- `{e['source']}` **[{e['relation']}]** ➔ `{e['target']}` (w={e['weight']}){ev}")
        return "\n".join(lines)

    def graph_causal_path(source: str, target: str) -> str:
        """Discovers the shortest causal/semantic chain connecting two entities in the knowledge graph."""
        res = graph.find_causal_path(source, target)
        if not res.get("connected"):
            return f"⚠️ {res.get('message', 'No path found.')}"
        if res.get("hops") == 0:
            return f"Both queries resolve to the same node: `{res['source']}`."
        return (
            f"🔗 **Causal Path Found ({res['hops']} hops):**\n"
            f"`{res['chain_summary']}`"
        )

    def graph_ecosystem_map() -> str:
        """Returns centrality rankings and active relationships across Boss's entire knowledge graph."""
        summary = graph.get_ecosystem_summary(top_n=10)
        lines = [
            f"### 🌐 LUMI Sovereign Knowledge Graph ({summary['total_nodes']} Nodes | {summary['total_active_edges']} Active Edges)",
            "",
            "**Top Central Entities:**",
        ]
        for n in summary["central_entities"]:
            lines.append(f"- **{n['label']}** (`{n['entity_type']}`) — degree: {n['degree']}, importance: {n['importance']}")
        lines.append("\n**Key Active Relations:**")
        for r in summary["key_relations"][:8]:
            lines.append(f"- `{r['source']}` --[{r['relation']}]--> `{r['target']}`")
        return "\n".join(lines)

    registry.register(
        Tool(
            name="graph_remember_relation",
            description="Stores a directed entity-relation-entity triple into LUMI's Temporal Knowledge Graph.",
            params_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source entity name (e.g. 'SENTINEL', 'Commander')"},
                    "relation": {"type": "string", "description": "Relationship verb (e.g. 'USES', 'DETECTS', 'DEPLOYED_ON')"},
                    "target": {"type": "string", "description": "Target entity name (e.g. 'FastAPI', 'SQL Injection')"},
                    "evidence": {"type": "string", "description": "Context or evidence for this relation"},
                },
                "required": ["source", "relation", "target"],
            },
            handler=graph_remember_relation,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="graph_query_neighborhood",
            description="Queries 1-to-3 hop semantic neighborhood around an entity in the Knowledge Graph.",
            params_schema={
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Entity name to explore"},
                    "max_hops": {"type": "integer", "description": "Traversal depth (1 to 3, default 2)"},
                },
                "required": ["entity"],
            },
            handler=graph_query_neighborhood,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="graph_causal_path",
            description="Finds the shortest multi-hop causal or semantic path between two entities in the Knowledge Graph.",
            params_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Starting entity"},
                    "target": {"type": "string", "description": "Target entity"},
                },
                "required": ["source", "target"],
            },
            handler=graph_causal_path,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="graph_ecosystem_map",
            description="Returns top central entities and active relationships in Boss's Sovereign Knowledge Graph.",
            params_schema={"type": "object", "properties": {}},
            handler=graph_ecosystem_map,
            risk="auto",
        )
    )

    return graph
