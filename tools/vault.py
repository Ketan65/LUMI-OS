"""Tool wrapper for LUMI NEURAL-VAULT (Phase 10: Local Codebase Index & Semantic RAG)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.vault import NeuralVault
from tools.registry import Tool, ToolRegistry


def _vault_cfg() -> dict:
    """config.yaml vault block — production me semantic embeddings on."""
    try:
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("vault") or {}
    except Exception:
        return {}


def register_vault_tools(registry: ToolRegistry, vault: NeuralVault | None = None) -> NeuralVault:
    """Registers vault_search and vault_index tools into ToolRegistry."""
    if vault is not None:
        active_vault = vault
    else:
        vcfg = _vault_cfg()             # production instance → config se semantic
        active_vault = NeuralVault(
            semantic=bool(vcfg.get("semantic", True)),
            embed_model=str(vcfg.get("embed_model", "nomic-embed-text")),
        )

    def vault_search(query: str, top_k: int = 5, file_filter: str = "") -> str:
        """Performs fast semantic BM25 search across local codebase and documents indexed in NEURAL-VAULT."""
        if not query or not query.strip():
            return "Please provide a search query."

        results = active_vault.search(query=query.strip(), top_k=top_k, file_filter=file_filter.strip() or None)
        if not results:
            return f"No matching snippets found in NEURAL-VAULT for '{query}'."

        lines: list[str] = [f"### 📚 NEURAL-VAULT Search: '{query}' ({len(results)} matches)", ""]
        for i, res in enumerate(results, start=1):
            lines.append(f"**{i}. `{res.file_path}` (Lines {res.start_line}–{res.end_line}, Score: {res.score})**")
            snippet_clean = "\n".join("  " + line for line in res.snippet.strip().splitlines()[:15])
            lines.append(f"```\n{snippet_clean}\n```\n")

        return "\n".join(lines)

    def vault_index(path: str = ".", recursive: bool = True) -> str:
        """Indexes or incrementally updates a codebase directory into local NEURAL-VAULT."""
        p = Path(path).resolve()
        if not p.exists():
            return f"Path does not exist: {path}"

        stats = active_vault.index_path(target_path=p, recursive=recursive)
        v_stats = active_vault.get_stats()
        return (
            f"✅ NEURAL-VAULT Indexed `{p}`:\n"
            f"- Newly Indexed / Updated: {stats['indexed']} files\n"
            f"- Skipped (Unchanged/Large): {stats['skipped']} files\n"
            f"- Total Vault Database: {v_stats['documents']} files, {v_stats['chunks']} chunks ({v_stats['db_size_kb']} KB)"
        )

    registry.register(
        Tool(
            name="vault_search",
            description="Deep semantic search across indexed local codebase, functions, notes, and documentation.",
            params_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'how is authentication handled', 'find JWT verify function').",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Maximum number of code snippets to return (default 5).",
                    },
                    "file_filter": {
                        "type": "string",
                        "description": "Optional filename substring or extension filter (e.g. '.py', 'server').",
                    },
                },
                "required": ["query"],
            },
            handler=vault_search,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="vault_index",
            description="Indexes or updates local files/codebases into NEURAL-VAULT for instant retrieval.",
            params_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to file or directory to index into the vault (default '.').",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Whether to index subdirectories recursively (default true).",
                    },
                },
            },
            handler=vault_index,
            risk="auto",
        )
    )

    return active_vault
