"""REPO-AST-GRAPH: Cross-File Symbol, Call & Impact-Radius Graph Engine.

Scans a Python workspace via `ast` to construct a complete structural dependency graph:
- Modules, Classes, Functions/Methods (with full type-annotated signatures & docstrings)
- Cross-file import graph (`module_a -> module_b`)
- Cross-file call graph (`caller -> callee` and reverse `callee -> callers`)
- Blast/Impact Radius Analysis ("If I modify X, which downstream modules, functions, and tests break?")
- Aider/SWE-agent style compact repository map ranked by structural centrality.
"""

from __future__ import annotations

import ast
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IGNORED_GRAPH_DIRS = frozenset({
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".gemini",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "backups",
})


@dataclass
class SymbolNode:
    """Represents a class, function, or method definition in the repository."""
    name: str
    qualified_name: str      # e.g. "core.vault.NeuralVault.search" or "NeuralVault.search"
    short_qname: str         # e.g. "NeuralVault.search" or "init_db"
    kind: str                # "class" | "function" | "async_function" | "method" | "async_method"
    module: str              # e.g. "core.vault"
    file: str                # relative POSIX path e.g. "core/vault.py"
    line: int
    end_line: int
    signature: str
    docstring: str
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)


@dataclass
class ModuleNode:
    """Represents a parsed Python source file in the repository."""
    module: str              # e.g. "core.vault"
    file: str                # relative POSIX path e.g. "core/vault.py"
    docstring: str
    imports: list[str] = field(default_factory=list)            # imported module/symbol names
    resolved_imports: list[str] = field(default_factory=list)   # internal repo modules imported
    symbols: list[SymbolNode] = field(default_factory=list)
    is_test: bool = False


class _CallExtractor(ast.NodeVisitor):
    """Collects function/method call names inside an AST scope without descending into nested defs."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._seen: set[str] = set()

    def _add(self, name: str) -> None:
        if name and name not in self._seen:
            self._seen.add(name)
            self.calls.append(name)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name):
            self._add(func.id)
        elif isinstance(func, ast.Attribute):
            # Capture both `obj.method` and bare `method` for cross-file resolution
            attr_name = func.attr
            if isinstance(func.value, ast.Name):
                prefix = func.value.id
                if prefix not in ("self", "cls", "super"):
                    self._add(f"{prefix}.{attr_name}")
            self._add(attr_name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Do not descend into nested functions (they are visited separately)
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def _format_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Renders a clean Python signature string from a FunctionDef AST node."""
    args_Node = node.args
    parts: list[str] = []

    # Positional-only + normal args
    pos_args = list(args_Node.posonlyargs) + list(args_Node.args)
    num_defaults = len(args_Node.defaults)
    default_offset = len(pos_args) - num_defaults

    for idx, arg in enumerate(pos_args):
        s = arg.arg
        if arg.annotation:
            try:
                s += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        if idx >= default_offset:
            def_node = args_Node.defaults[idx - default_offset]
            try:
                s += f" = {ast.unparse(def_node)}"
            except Exception:
                s += " = ..."
        parts.append(s)

    if args_Node.vararg:
        va = f"*{args_Node.vararg.arg}"
        if args_Node.vararg.annotation:
            try:
                va += f": {ast.unparse(args_Node.vararg.annotation)}"
            except Exception:
                pass
        parts.append(va)
    elif args_Node.kwonlyargs:
        parts.append("*")

    for kw_arg, kw_def in zip(args_Node.kwonlyargs, args_Node.kw_defaults):
        s = kw_arg.arg
        if kw_arg.annotation:
            try:
                s += f": {ast.unparse(kw_arg.annotation)}"
            except Exception:
                pass
        if kw_def is not None:
            try:
                s += f" = {ast.unparse(kw_def)}"
            except Exception:
                s += " = ..."
        parts.append(s)

    if args_Node.kwarg:
        kwa = f"**{args_Node.kwarg.arg}"
        if args_Node.kwarg.annotation:
            try:
                kwa += f": {ast.unparse(args_Node.kwarg.annotation)}"
            except Exception:
                pass
        parts.append(kwa)

    ret_suffix = ""
    if node.returns:
        try:
            ret_suffix = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(parts)}){ret_suffix}"


class RepoASTGraph:
    """Repository-Wide AST Symbol & Dependency Graph Engine."""

    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.modules: dict[str, ModuleNode] = {}          # module_name -> ModuleNode
        self.file_to_module: dict[str, str] = {}          # rel_posix_path -> module_name
        self.symbols_by_name: dict[str, list[SymbolNode]] = {}
        self.symbols_by_qname: dict[str, SymbolNode] = {}
        # Graph edges
        self.module_imports: dict[str, set[str]] = {}     # mod -> set of imported internal mods
        self.reverse_imports: dict[str, set[str]] = {}    # mod -> set of mods that import it
        self.call_graph: dict[str, set[str]] = {}         # caller_qname -> set of callee_qnames
        self.reverse_calls: dict[str, list[dict[str, Any]]] = {}  # symbol_name/qname -> list of caller infos
        self._last_built: float = 0.0

    @staticmethod
    def _path_to_module(rel_path: Path) -> str:
        parts = list(rel_path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else "__root__"

    @staticmethod
    def _is_test_file(rel_posix: str) -> bool:
        name = Path(rel_posix).name.lower()
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "/tests/" in f"/{rel_posix.lower()}/"
        )

    def _ensure_built(self) -> None:
        if not self.modules:
            self.build_graph(self.root_dir)

    def build_graph(self, root_dir: Path | str | None = None) -> dict[str, Any]:
        """Scans Python files under `root_dir` and builds the Cross-File AST Dependency & Call Graph."""
        if root_dir is not None:
            self.root_dir = Path(root_dir).resolve()

        t0 = time.perf_counter()
        self.modules.clear()
        self.file_to_module.clear()
        self.symbols_by_name.clear()
        self.symbols_by_qname.clear()
        self.module_imports.clear()
        self.reverse_imports.clear()
        self.call_graph.clear()
        self.reverse_calls.clear()

        if not self.root_dir.exists():
            return {"files_scanned": 0, "symbols_indexed": 0, "elapsed_ms": 0.0}

        py_files: list[Path] = []
        for p in sorted(self.root_dir.rglob("*.py")):
            if not p.is_file():
                continue
            rel_parts = p.relative_to(self.root_dir).parts
            if any(part in IGNORED_GRAPH_DIRS or part.startswith(".venv") for part in rel_parts):
                continue
            py_files.append(p)

        # Pass 1: Parse AST of every file, collect modules and symbol definitions
        for file_path in py_files:
            try:
                rel_path = file_path.relative_to(self.root_dir)
                rel_posix = rel_path.as_posix()
                mod_name = self._path_to_module(rel_path)
                source = file_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=rel_posix)
            except Exception:
                continue

            mod_doc = (ast.get_docstring(tree) or "").strip().splitlines()[0] if ast.get_docstring(tree) else ""
            mod_node = ModuleNode(
                module=mod_name,
                file=rel_posix,
                docstring=mod_doc,
                is_test=self._is_test_file(rel_posix),
            )

            # Extract top-level and nested imports + definitions
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mod_node.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    base_mod = node.module or ""
                    if base_mod:
                        mod_node.imports.append(base_mod)
                    for alias in node.names:
                        full_imp = f"{base_mod}.{alias.name}" if base_mod else alias.name
                        mod_node.imports.append(full_imp)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sym = self._extract_function_symbol(node, mod_name, rel_posix, class_name=None)
                    mod_node.symbols.append(sym)
                    self._register_symbol(sym)
                elif isinstance(node, ast.ClassDef):
                    cls_sym, method_syms = self._extract_class_symbols(node, mod_name, rel_posix)
                    mod_node.symbols.append(cls_sym)
                    self._register_symbol(cls_sym)
                    for m_sym in method_syms:
                        mod_node.symbols.append(m_sym)
                        self._register_symbol(m_sym)

            # Also scan imports inside functions/blocks (lazy imports)
            for sub in ast.walk(tree):
                if isinstance(sub, ast.Import):
                    for alias in sub.names:
                        if alias.name not in mod_node.imports:
                            mod_node.imports.append(alias.name)
                elif isinstance(sub, ast.ImportFrom) and sub.module:
                    if sub.module not in mod_node.imports:
                        mod_node.imports.append(sub.module)
                    for alias in sub.names:
                        cand = f"{sub.module}.{alias.name}"
                        if cand not in mod_node.imports:
                            mod_node.imports.append(cand)

            self.modules[mod_name] = mod_node
            self.file_to_module[rel_posix] = mod_name
            self.module_imports[mod_name] = set()
            self.reverse_imports.setdefault(mod_name, set())

        # Pass 2: Resolve cross-file module imports and cross-file symbol calls
        known_modules = set(self.modules.keys())
        for mod_name, mod_node in self.modules.items():
            for imp in mod_node.imports:
                # Match exact module or parent module prefix
                target_mod = None
                if imp in known_modules:
                    target_mod = imp
                else:
                    parts = imp.split(".")
                    for i in range(len(parts) - 1, 0, -1):
                        prefix = ".".join(parts[:i])
                        if prefix in known_modules:
                            target_mod = prefix
                            break
                if target_mod and target_mod != mod_name:
                    mod_node.resolved_imports.append(target_mod)
                    self.module_imports[mod_name].add(target_mod)
                    self.reverse_imports.setdefault(target_mod, set()).add(mod_name)

            # Deduplicate resolved_imports preserving order
            mod_node.resolved_imports = list(dict.fromkeys(mod_node.resolved_imports))

            # Build call graph edges for all symbols in this module
            for sym in mod_node.symbols:
                self.call_graph.setdefault(sym.qualified_name, set())
                for raw_call in sym.calls:
                    bare_name = raw_call.split(".")[-1]
                    targets = self.symbols_by_name.get(bare_name, [])
                    for tgt in targets:
                        if tgt.qualified_name == sym.qualified_name:
                            continue
                        self.call_graph[sym.qualified_name].add(tgt.qualified_name)
                        caller_entry = {
                            "caller": sym.short_qname,
                            "caller_qualified": sym.qualified_name,
                            "file": sym.file,
                            "line": sym.line,
                            "module": sym.module,
                            "is_test": mod_node.is_test,
                        }
                        self.reverse_calls.setdefault(tgt.name, []).append(caller_entry)
                        if tgt.short_qname != tgt.name:
                            self.reverse_calls.setdefault(tgt.short_qname, []).append(caller_entry)
                        self.reverse_calls.setdefault(tgt.qualified_name, []).append(caller_entry)

        self._last_built = time.time()
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        total_symbols = sum(len(m.symbols) for m in self.modules.values())
        total_import_edges = sum(len(v) for v in self.module_imports.values())
        total_call_edges = sum(len(v) for v in self.call_graph.values())

        return {
            "root_dir": str(self.root_dir),
            "files_scanned": len(self.modules),
            "symbols_indexed": total_symbols,
            "import_edges": total_import_edges,
            "call_edges": total_call_edges,
            "elapsed_ms": elapsed_ms,
        }

    def _register_symbol(self, sym: SymbolNode) -> None:
        self.symbols_by_qname[sym.qualified_name] = sym
        self.symbols_by_name.setdefault(sym.name, []).append(sym)
        if sym.short_qname != sym.name:
            self.symbols_by_name.setdefault(sym.short_qname, []).append(sym)

    def _extract_function_symbol(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        mod_name: str,
        rel_posix: str,
        class_name: str | None = None,
    ) -> SymbolNode:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        if class_name:
            kind = "async_method" if is_async else "method"
            short_qname = f"{class_name}.{node.name}"
        else:
            kind = "async_function" if is_async else "function"
            short_qname = node.name

        qname = f"{mod_name}.{short_qname}"
        sig = _format_signature(node)
        doc = (ast.get_docstring(node) or "").strip()
        first_doc_line = doc.splitlines()[0].strip() if doc else ""

        extractor = _CallExtractor()
        for stmt in node.body:
            extractor.visit(stmt)

        decs: list[str] = []
        for d in node.decorator_list:
            try:
                decs.append(ast.unparse(d))
            except Exception:
                pass

        return SymbolNode(
            name=node.name,
            qualified_name=qname,
            short_qname=short_qname,
            kind=kind,
            module=mod_name,
            file=rel_posix,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            signature=sig,
            docstring=first_doc_line,
            decorators=decs,
            calls=extractor.calls,
        )

    def _extract_class_symbols(
        self,
        node: ast.ClassDef,
        mod_name: str,
        rel_posix: str,
    ) -> tuple[SymbolNode, list[SymbolNode]]:
        bases: list[str] = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                pass

        base_str = f"({', '.join(bases)})" if bases else ""
        sig = f"class {node.name}{base_str}"
        doc = (ast.get_docstring(node) or "").strip()
        first_doc_line = doc.splitlines()[0].strip() if doc else ""

        extractor = _CallExtractor()
        methods: list[SymbolNode] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                m_sym = self._extract_function_symbol(item, mod_name, rel_posix, class_name=node.name)
                methods.append(m_sym)
                for c in m_sym.calls:
                    extractor._add(c)
            else:
                extractor.visit(item)

        cls_sym = SymbolNode(
            name=node.name,
            qualified_name=f"{mod_name}.{node.name}",
            short_qname=node.name,
            kind="class",
            module=mod_name,
            file=rel_posix,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            signature=sig,
            docstring=first_doc_line,
            bases=bases,
            calls=extractor.calls,
        )
        return cls_sym, methods

    def locate_symbol(self, symbol_name: str) -> list[dict[str, Any]]:
        """Locates exact or partial matches for a class, function, or method across the repository."""
        self._ensure_built()
        query = (symbol_name or "").strip()
        if not query:
            return []

        matches: list[SymbolNode] = []
        seen_qnames: set[str] = set()

        # 1. Exact match on name, short_qname, or qualified_name
        if query in self.symbols_by_qname:
            sym = self.symbols_by_qname[query]
            matches.append(sym)
            seen_qnames.add(sym.qualified_name)

        for sym in self.symbols_by_name.get(query, []):
            if sym.qualified_name not in seen_qnames:
                matches.append(sym)
                seen_qnames.add(sym.qualified_name)

        # 2. Case-insensitive or substring match if no exact match found
        q_low = query.lower()
        if not matches:
            for qname, sym in self.symbols_by_qname.items():
                if (
                    sym.name.lower() == q_low
                    or sym.short_qname.lower() == q_low
                    or q_low in sym.short_qname.lower()
                ):
                    if qname not in seen_qnames:
                        matches.append(sym)
                        seen_qnames.add(qname)

        results: list[dict[str, Any]] = []
        for sym in matches:
            raw_callers = self.reverse_calls.get(sym.qualified_name, [])
            # Deduplicate callers by caller_qualified
            unique_callers: list[dict[str, Any]] = []
            seen_c: set[str] = set()
            for c in raw_callers:
                cq = c["caller_qualified"]
                if cq not in seen_c:
                    seen_c.add(cq)
                    unique_callers.append({
                        "caller": c["caller"],
                        "file": c["file"],
                        "line": c["line"],
                        "is_test": c["is_test"],
                    })

            results.append({
                "symbol": sym.name,
                "qualified_name": sym.qualified_name,
                "short_name": sym.short_qname,
                "kind": sym.kind,
                "file": sym.file,
                "module": sym.module,
                "line": sym.line,
                "end_line": sym.end_line,
                "signature": sym.signature,
                "docstring": sym.docstring,
                "calls": sym.calls[:15],
                "callers": unique_callers,
                "caller_count": len(unique_callers),
            })

        # Rank exact matches and non-test definitions first
        results.sort(
            key=lambda r: (
                0 if r["symbol"] == query or r["short_name"] == query else 1,
                1 if self._is_test_file(r["file"]) else 0,
                -r["caller_count"],
            )
        )
        return results

    def analyze_impact_radius(self, symbol_or_file: str) -> dict[str, Any]:
        """Computes the downstream blast radius if `symbol_or_file` is modified.

        Traces both:
        - Reverse call graph (functions/methods/classes calling the symbol)
        - Reverse module import graph (modules and `tests/test_*.py` importing the target module)
        """
        self._ensure_built()
        target_str = (symbol_or_file or "").strip().replace("\\", "/")
        if not target_str:
            return {"found": False, "error": "Empty symbol or file query."}

        seed_modules: set[str] = set()
        seed_symbols: list[SymbolNode] = []

        # Check if query matches a file path or module name
        if target_str in self.file_to_module:
            seed_modules.add(self.file_to_module[target_str])
        elif target_str in self.modules:
            seed_modules.add(target_str)
        else:
            # Check suffix match on file paths (e.g. "vault.py" or "core/vault.py")
            for f_posix, mod_name in self.file_to_module.items():
                if f_posix == target_str or f_posix.endswith(f"/{target_str}"):
                    seed_modules.add(mod_name)

        # Also check symbol matches
        located = self.locate_symbol(target_str)
        for loc in located:
            qname = loc["qualified_name"]
            if qname in self.symbols_by_qname:
                sym = self.symbols_by_qname[qname]
                seed_symbols.append(sym)
                seed_modules.add(sym.module)

        if not seed_modules and not seed_symbols:
            return {
                "found": False,
                "target": symbol_or_file,
                "error": f"No symbol or file matching '{symbol_or_file}' found in repository.",
                "direct_callers": [],
                "affected_files": [],
                "affected_tests": [],
                "risk_level": "LOW",
            }

        # 1. Direct & Transitive Callers via BFS over reverse_calls
        direct_callers: list[dict[str, Any]] = []
        transitive_callers: list[dict[str, Any]] = []
        visited_qnames: set[str] = {s.qualified_name for s in seed_symbols}
        call_queue: deque[tuple[str, int]] = deque((s.qualified_name, 0) for s in seed_symbols)

        # If target was a file/module without a single symbol, seed all symbols in those modules
        if not seed_symbols and seed_modules:
            for mod in seed_modules:
                for sym in self.modules[mod].symbols:
                    visited_qnames.add(sym.qualified_name)
                    call_queue.append((sym.qualified_name, 0))

        affected_files_set: set[str] = set()
        affected_tests_set: set[str] = set()

        while call_queue:
            curr_qname, depth = call_queue.popleft()
            for caller_info in self.reverse_calls.get(curr_qname, []):
                c_qname = caller_info["caller_qualified"]
                c_file = caller_info["file"]
                if caller_info["is_test"]:
                    affected_tests_set.add(c_file)
                else:
                    affected_files_set.add(c_file)

                entry = {
                    "caller": caller_info["caller"],
                    "file": c_file,
                    "line": caller_info["line"],
                    "hop": depth + 1,
                }
                if depth == 0 and entry not in direct_callers:
                    direct_callers.append(entry)
                elif depth > 0 and entry not in transitive_callers:
                    transitive_callers.append(entry)

                if c_qname not in visited_qnames and depth < 4:
                    visited_qnames.add(c_qname)
                    call_queue.append((c_qname, depth + 1))

        # 2. Transitive Module Dependents via BFS over reverse_imports
        visited_mods: set[str] = set(seed_modules)
        mod_queue: deque[tuple[str, int]] = deque((m, 0) for m in seed_modules)
        dependent_modules: list[dict[str, Any]] = []

        while mod_queue:
            curr_mod, depth = mod_queue.popleft()
            for dep_mod in sorted(self.reverse_imports.get(curr_mod, set())):
                if dep_mod not in visited_mods:
                    visited_mods.add(dep_mod)
                    mod_node = self.modules[dep_mod]
                    dependent_modules.append({
                        "module": dep_mod,
                        "file": mod_node.file,
                        "hop": depth + 1,
                        "is_test": mod_node.is_test,
                    })
                    if mod_node.is_test:
                        affected_tests_set.add(mod_node.file)
                    else:
                        affected_files_set.add(mod_node.file)
                    if depth < 4:
                        mod_queue.append((dep_mod, depth + 1))

        # 3. Heuristic test pairing (e.g. core/vault.py -> tests/test_vault.py)
        for mod in seed_modules:
            stem = Path(self.modules[mod].file).stem
            for f_posix, m_name in self.file_to_module.items():
                if self.modules[m_name].is_test and stem in Path(f_posix).stem:
                    affected_tests_set.add(f_posix)

        # Exclude the seed files themselves from downstream affected_files if desired, or keep clear
        seed_files = {self.modules[m].file for m in seed_modules if m in self.modules}
        downstream_files = sorted(affected_files_set - seed_files)
        affected_tests = sorted(affected_tests_set)

        blast_score = len(direct_callers) + len(downstream_files) * 2 + len(affected_tests)
        if blast_score >= 12:
            risk_level = "CRITICAL"
        elif blast_score >= 6:
            risk_level = "HIGH"
        elif blast_score >= 2:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "found": True,
            "target": symbol_or_file,
            "seed_files": sorted(seed_files),
            "seed_symbols": [s.qualified_name for s in seed_symbols],
            "direct_callers": direct_callers,
            "transitive_callers": transitive_callers,
            "dependent_modules": dependent_modules,
            "affected_files": downstream_files,
            "affected_tests": affected_tests,
            "risk_level": risk_level,
            "summary": (
                f"Impact radius for '{symbol_or_file}': {len(direct_callers)} direct caller(s), "
                f"{len(downstream_files)} downstream source file(s), and "
                f"{len(affected_tests)} test file(s) affected [{risk_level} RISK]."
            ),
        }

    def generate_repo_map(self, max_files: int = 40) -> str:
        """Generates a compact Aider/SWE-agent style repository structural map ranked by centrality."""
        self._ensure_built()
        if not self.modules:
            return "# Repository AST Map: (No Python files indexed)"

        # Rank modules by architectural centrality:
        # Non-test files first, then by (incoming imports * 3 + outgoing imports + symbol count)
        def _centrality(mod_node: ModuleNode) -> tuple[int, int, str]:
            in_deg = len(self.reverse_imports.get(mod_node.module, set()))
            out_deg = len(self.module_imports.get(mod_node.module, set()))
            sym_cnt = len(mod_node.symbols)
            score = in_deg * 4 + out_deg + min(sym_cnt, 10)
            return (0 if not mod_node.is_test else 1, -score, mod_node.file)

        ranked_mods = sorted(self.modules.values(), key=_centrality)[: max(1, max_files)]

        lines: list[str] = [
            f"# LUMI Repository Structural Map ({len(ranked_mods)}/{len(self.modules)} modules shown)"
        ]
        for mod in ranked_mods:
            in_deps = len(self.reverse_imports.get(mod.module, set()))
            dep_badge = f" [imported by {in_deps} module(s)]" if in_deps > 0 else ""
            lines.append(f"\n📄 {mod.file}{dep_badge}")
            if mod.docstring:
                lines.append(f"  \"\"\"{mod.docstring}\"\"\"")

            for sym in mod.symbols:
                if sym.kind == "class":
                    lines.append(f"  L{sym.line}: {sym.signature}")
                elif sym.kind in ("method", "async_method"):
                    lines.append(f"    L{sym.line}: {sym.signature}")
                else:
                    lines.append(f"  L{sym.line}: {sym.signature}")

        return "\n".join(lines)
