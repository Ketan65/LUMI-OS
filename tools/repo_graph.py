"""REPO-GRAPH TOOLS: SWE-Agent Repository Comprehension & Blast-Radius Tools.

Registers `repo_symbol_locate`, `repo_impact_radius`, and `repo_structural_map`
into LUMI's `ToolRegistry`.
"""

from __future__ import annotations

from pathlib import Path

from core.repo_graph import RepoASTGraph
from tools.registry import Tool, ToolRegistry


def register_repo_graph_tools(
    registry: ToolRegistry,
    workspace_root: str | Path = ".",
) -> RepoASTGraph:
    """Registers repository AST graph tools (`repo_symbol_locate`, `repo_impact_radius`, `repo_structural_map`)."""
    graph = RepoASTGraph(root_dir=workspace_root)

    def repo_symbol_locate(symbol_name: str, refresh: bool = False) -> str:
        """Locates a Python class, function, or method across the repository with exact lines, signature, and callers."""
        if refresh or not graph.modules:
            graph.build_graph()

        matches = graph.locate_symbol(symbol_name)
        if not matches:
            return f"🔍 No symbol matching '{symbol_name}' found in {graph.root_dir}."

        out_lines = [f"🎯 Symbol Matches for '{symbol_name}' ({len(matches)} found):"]
        for m in matches[:10]:
            out_lines.append(
                f"\n• {m['qualified_name']} [{m['kind']}]\n"
                f"  File: {m['file']} (Lines {m['line']}–{m['end_line']})\n"
                f"  Signature: {m['signature']}"
            )
            if m["docstring"]:
                out_lines.append(f"  Docstring: {m['docstring']}")
            if m["calls"]:
                out_lines.append(f"  Calls: {', '.join(m['calls'][:10])}")
            if m["callers"]:
                caller_strs = [f"{c['caller']} ({c['file']}:{c['line']})" for c in m["callers"][:8]]
                out_lines.append(f"  Callers ({m['caller_count']}): {', '.join(caller_strs)}")
            else:
                out_lines.append("  Callers (0): None detected")

        return "\n".join(out_lines)

    def repo_impact_radius(symbol_or_file: str, refresh: bool = False) -> str:
        """Analyzes downstream impact radius (callers, dependent modules, and test files) if a symbol or file changes."""
        if refresh or not graph.modules:
            graph.build_graph()

        res = graph.analyze_impact_radius(symbol_or_file)
        if not res.get("found"):
            return f"⚠️ {res.get('error', 'Target not found.')}"

        direct_str = (
            "\n".join(
                f"  - {c['caller']} in {c['file']}:L{c['line']}"
                for c in res["direct_callers"][:15]
            )
            if res["direct_callers"]
            else "  - None"
        )
        files_str = (
            "\n".join(f"  - {f}" for f in res["affected_files"][:20])
            if res["affected_files"]
            else "  - None"
        )
        tests_str = (
            "\n".join(f"  - 🧪 {t}" for t in res["affected_tests"][:20])
            if res["affected_tests"]
            else "  - ⚠️ No paired downstream test files detected!"
        )

        return (
            f"💥 Blast / Impact Radius Analysis: {res['target']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Risk Level: {res['risk_level']} | {res['summary']}\n"
            f"Seed File(s): {', '.join(res['seed_files']) or 'N/A'}\n\n"
            f"Direct Callers ({len(res['direct_callers'])}):\n{direct_str}\n\n"
            f"Downstream Affected Source Files ({len(res['affected_files'])}):\n{files_str}\n\n"
            f"Affected Test Suites to Run ({len(res['affected_tests'])}):\n{tests_str}"
        )

    def repo_structural_map(max_files: int = 40, refresh: bool = False) -> str:
        """Generates a compact SWE-agent style repository AST symbol map ranked by dependency centrality."""
        if refresh or not graph.modules:
            graph.build_graph()
        return graph.generate_repo_map(max_files=max_files)

    registry.register(
        Tool(
            name="repo_symbol_locate",
            description=(
                "Locates any class, function, or method across the repository via AST: "
                "returns file path, line numbers, type signature, docstring, outgoing calls, and all cross-file callers."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "symbol_name": {
                        "type": "string",
                        "description": "Name of class, function, or method (e.g. 'NeuralVault', 'init_db', 'ToolRegistry.register').",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "Whether to force a fresh AST scan of the workspace (default: false).",
                    },
                },
                "required": ["symbol_name"],
            },
            handler=repo_symbol_locate,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="repo_impact_radius",
            description=(
                "Calculates the blast radius before editing a symbol or file: identifies all direct/transitive callers, "
                "dependent modules, and exact `tests/test_*.py` suites that must be run."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "symbol_or_file": {
                        "type": "string",
                        "description": "Symbol name (e.g. 'save_fact') or file path (e.g. 'memory/store.py').",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "Whether to force a fresh AST scan before computing impact (default: false).",
                    },
                },
                "required": ["symbol_or_file"],
            },
            handler=repo_impact_radius,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="repo_structural_map",
            description=(
                "Generates a compact Aider/SWE-agent style repository map of modules, classes, and function signatures "
                "ranked by structural centrality."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of high-centrality files to include (default: 40).",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "Whether to rebuild the AST graph before rendering the map (default: false).",
                    },
                },
                "required": [],
            },
            handler=repo_structural_map,
            risk="auto",
        )
    )

    return graph
