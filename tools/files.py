"""File tools: list/read/write/delete/search — allowed_paths boundary."""

from __future__ import annotations

import fnmatch
import shutil
from datetime import datetime
from pathlib import Path

from tools.registry import Tool, ToolRegistry


def resolve_within(path: str, allowed_paths: list[str]) -> Path | None:
    """Resolved path only if it sits inside one of the allowed roots (else None)."""
    clean = str(path).replace("\\", "/").strip()
    if clean.startswith("/home/user/"):
        clean = clean.replace("/home/user/", "")
    target = Path(clean).expanduser().resolve()
    for root in allowed_paths:
        try:
            target.relative_to(Path(root).expanduser().resolve())
            return target
        except (ValueError, OSError):
            continue
    return None


def boundary_message(allowed_paths: list[str]) -> str:
    # self-correction: model gets the exact allowed roots so it can retry
    return ("Permission needed: path allowed list mein nahi — config.yaml -> "
            "allowed_paths me add karo. Allowed: " + " | ".join(allowed_paths))


def _size(n: int) -> str:
    return f"{n / 1024:.1f} KB" if n >= 1024 else f"{n} B"


def register_file_tools(registry: ToolRegistry, allowed_paths: list[str]) -> None:
    def _inside(path: str) -> Path | None:
        return resolve_within(path, allowed_paths)

    def list_files(path: str) -> str:
        target = _inside(path)
        if target is None:
            return boundary_message(allowed_paths)
        if not target.exists():
            return f"Path nahi mila: {path} — sahi folder path de do."
        if not target.is_dir():
            return f"Ye file hai, folder nahi: {path} — read_file use karo."
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        lines = []
        for entry in entries[:60]:            # cap — bade folders ka raw dump nahi
            lines.append(f"[DIR]  {entry.name}/" if entry.is_dir()
                         else f"[FILE] {entry.name} ({_size(entry.stat().st_size)})")
        rest = len(entries) - 60
        if rest > 0:
            lines.append(f"...(aur {rest} entries — count/summary do, "
                         f"specific naam pe dobara list karo)")
        return "\n".join(lines) if lines else "(folder khali hai)"

    def read_file(path: str, start_line: int = 1, end_line: int | None = None, max_chars: int = 8000) -> str:
        try:
            max_chars = int(max_chars)
        except (TypeError, ValueError):
            max_chars = 8000
        target = _inside(path)
        if target is None:
            return boundary_message(allowed_paths)
        if not target.exists():
            return f"File nahi mili: {path}"
        if target.is_dir():
            return f"Ye folder hai: {path} — read_file ko file ka path do."
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        
        # Line-range slicing if specified
        if end_line is not None or start_line > 1:
            try:
                s = max(1, int(start_line)) - 1
                e = len(lines) if end_line is None else min(len(lines), int(end_line))
                numbered = [f"{i+1:4d} | {lines[i]}" for i in range(s, e)]
                text = "\n".join(numbered)
            except Exception:
                pass
        if len(text) > max_chars:
            return text[:max_chars] + f"\n...[truncated: total {len(text)} chars]"
        return text if text.strip() else "(file khali hai)"

    def write_file(path: str, content: str, mode: str = "overwrite") -> str:
        target = _inside(path)
        if target is None:
            return boundary_message(allowed_paths)
        if target.is_dir():
            return f"Ye folder hai: {path} — file ka path do."
        if mode not in ("overwrite", "append"):
            mode = "overwrite"
        target.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with target.open("a", encoding="utf-8") as fh:
                fh.write(content)
            return f"Append ho gaya: {target.name} (+{len(content)} chars)"
        backup_note = ""
        if target.exists():
            # data protection: dated .bak copy BEFORE overwrite
            bak = target.with_name(f"{target.stem}.backup_{datetime.now():%Y%m%d}{target.suffix}")
            shutil.copy2(target, bak)
            backup_note = f" (purani copy: {bak.name})"
        target.write_text(content, encoding="utf-8")
        return f"Likha gaya: {target.name}{backup_note} ({len(content)} chars)"

    def delete_file(path: str) -> str:
        target = _inside(path)
        if target is None:
            return boundary_message(allowed_paths)
        if target.is_dir():
            return f"Folder delete allow nahi hai — scope sirf files hai: {path}"
        if not target.exists():
            return f"File pehle se nahi hai: {path}"   # friendly, not an error
        name = target.name
        target.unlink()
        return f"Delete ho gaya: {name}"

    def edit_file(path: str, target: str, replacement: str) -> str:
        """Surgical search-and-replace edit without rewriting the entire file (Antigravity/Claude Code style)."""
        target_path = _inside(path)
        if target_path is None:
            return boundary_message(allowed_paths)
        if not target_path.exists():
            return f"File nahi mili: {path}"
        if target_path.is_dir():
            return f"Ye folder hai, file nahi: {path}"
        content = target_path.read_text(encoding="utf-8", errors="replace")
        if target not in content:
            return f"Error: Target text file me nahi mila. Exact matching required (check whitespace/indentation)."
        
        # Automatic backup before edit
        bak = target_path.with_name(f"{target_path.stem}.backup_{datetime.now():%Y%m%d}{target_path.suffix}")
        shutil.copy2(target_path, bak)
        
        new_content = content.replace(target, replacement, 1)
        target_path.write_text(new_content, encoding="utf-8")
        return f"File edited successfully: {target_path.name} (replaced {len(target)} chars with {len(replacement)} chars). Backup: {bak.name}"

    def grep_search(root: str, pattern: str, file_pattern: str = "*") -> str:
        """Searches for text or regex pattern inside file contents across directory."""
        target = _inside(root)
        if target is None:
            return boundary_message(allowed_paths)
        if not target.exists():
            return f"Path nahi mila: {root}"
        if not target.is_dir():
            target = target.parent
        matches = []
        import re
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except Exception:
            rx = re.compile(re.escape(pattern), re.IGNORECASE)
        scanned = 0
        for item in target.rglob(file_pattern):
            if item.is_file() and not any(part.startswith(".") for part in item.parts):
                scanned += 1
                if scanned > 5000:
                    break
                try:
                    text = item.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), start=1):
                        if rx.search(line):
                            rel = item.relative_to(target)
                            matches.append(f"{rel}:{i}: {line.strip()[:140]}")
                            if len(matches) >= 50:
                                break
                except Exception:
                    continue
            if len(matches) >= 50:
                break
        return "\n".join(matches) if matches else f"0 matches for '{pattern}' in {root}"

    def search_files(root: str, pattern: str) -> str:
        target = _inside(root)
        if target is None:
            return boundary_message(allowed_paths)
        if not target.exists():
            return f"Path nahi mila: {root}"
        if not target.is_dir():
            return f"Ye file hai — folder do: {root}"
        matches, scanned = [], 0
        for item in target.rglob("*"):
            scanned += 1
            if scanned > 20000:          # scan cap: kabhi hang na ho
                break
            name = item.name.lower()
            if pattern.lower() in name or fnmatch.fnmatch(name, pattern.lower()):
                matches.append(str(item.relative_to(target)))
        shown = matches[:50]
        note = f"{len(matches)} matches" + (" (pehle 50 dikhaye)" if len(matches) > 50 else "")
        return (note + "\n" + "\n".join(shown)) if matches else f"0 matches: {pattern}"

    registry.register(Tool("list_files", "Folder ke entries dikhata hai (sorted).",
                           {"type": "object", "properties": {
                               "path": {"type": "string", "description": "Folder path"}},
                            "required": ["path"]}, list_files, risk="auto"))
    registry.register(Tool("read_file", "File ka text padhta hai. Supports optional line range (start_line, end_line) and max_chars limit.",
                           {"type": "object", "properties": {
                               "path": {"type": "string", "description": "File path"},
                               "start_line": {"type": "integer", "description": "Start line (1-indexed, optional)"},
                               "end_line": {"type": "integer", "description": "End line (inclusive, optional)"},
                               "max_chars": {"type": "integer", "description": "Max chars (default 8000)"}},
                            "required": ["path"]}, read_file, risk="auto"))
    registry.register(Tool("write_file", "File create/overwrite karta hai. Overwrite "
                           "se pehle automatic .bak backup banata hai.",
                           {"type": "object", "properties": {
                               "path": {"type": "string", "description": "File path"},
                               "content": {"type": "string", "description": "File content"},
                               "mode": {"type": "string",
                                        "enum": ["overwrite", "append"],
                                        "description": "overwrite ya append"}},
                            "required": ["path", "content"]}, write_file, risk="ask"))
    registry.register(Tool("edit_file", "Surgical search-and-replace code editor. Replaces exact target code block with replacement without rewriting entire file. Makes automatic .bak backup.",
                           {"type": "object", "properties": {
                               "path": {"type": "string", "description": "File path to modify"},
                               "target": {"type": "string", "description": "Exact text/code to replace (including indentation)"},
                               "replacement": {"type": "string", "description": "New replacement code"}},
                            "required": ["path", "target", "replacement"]}, edit_file, risk="ask"))
    registry.register(Tool("delete_file", "Sirf file delete karta hai (folder nahi).",
                           {"type": "object", "properties": {
                               "path": {"type": "string", "description": "File path"}},
                            "required": ["path"]}, delete_file, risk="ask"))
    registry.register(Tool("search_files", "Filename me substring/glob search "
                           "(case-insensitive, max 50 results).",
                           {"type": "object", "properties": {
                               "root": {"type": "string", "description": "Folder to search"},
                               "pattern": {"type": "string", "description": "text ya *.ext"}},
                            "required": ["root", "pattern"]}, search_files, risk="auto"))
    registry.register(Tool("grep_search", "Ripgrep-speed search for text/regex pattern INSIDE file contents across codebase.",
                           {"type": "object", "properties": {
                               "root": {"type": "string", "description": "Folder to search in"},
                               "pattern": {"type": "string", "description": "Text or regex pattern to search for"},
                               "file_pattern": {"type": "string", "description": "Optional glob filter, e.g. '*.py' or '*.js'"}},
                            "required": ["root", "pattern"]}, grep_search, risk="auto"))
