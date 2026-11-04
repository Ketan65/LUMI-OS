"""Project registry (req #6): data/projects.yaml + 5 tools + safe git status."""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import yaml

from tools.registry import Tool, ToolRegistry

REGISTRY_FILE = "data/projects.yaml"

_SYSTEM_DIRS = ("windows", "program files", "program files (x86)",
                "programdata", "$recycle.bin", "system volume information")


def _too_broad(target: Path) -> bool:
    """Drive root, user-profile root, ya OS folder = project nahi, register mat karo."""
    try:
        t = target.resolve()
    except OSError:
        return True
    if t == Path(t.anchor):                    # C:\
        return True
    if t == Path.home().resolve() or t == Path.home().resolve().parent:
        return True
    parts = [p.lower() for p in t.parts[1:]]
    return bool(parts) and parts[0] in _SYSTEM_DIRS


class ProjectRegistry:
    """data/projects.yaml backed store + session active_project state."""

    def __init__(self, allowed_paths: list[str] | None = None,
                 registry_file: str = REGISTRY_FILE):
        self.file = Path(registry_file)
        self.allowed = allowed_paths              # shared mutable allowlist
        self.projects: list[dict] = self._load()
        self.active: dict | None = None
        self._merge_allow()                       # registered roots = read access

    def _load(self) -> list[dict]:
        if not self.file.exists():
            self.file.parent.mkdir(parents=True, exist_ok=True)
            self.file.write_text("[]\n", encoding="utf-8")   # auto-create empty
            return []
        try:
            data = yaml.safe_load(self.file.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save(self) -> None:
        self.file.write_text(
            yaml.safe_dump(self.projects, allow_unicode=True, sort_keys=False),
            encoding="utf-8")

    def get(self, name: str) -> dict | None:
        key = str(name).strip().lower()
        for p in self.projects:
            if str(p.get("name", "")).lower() == key:
                return p
        return None

    def add(self, name: str, path: str, stack: str = "", goal: str = "") -> str:
        name = str(name).strip()
        if not name:
            return "Naam khaali hai — register_project me name do."
        target = Path(str(path).strip()).expanduser()
        if not target.is_dir():
            return f"Folder nahi mila: {path} — existing folder path do."
        if _too_broad(target):
            return (f"Ye path bahut broad/system folder hai: {path} — "
                    "kisi specific project folder ko register karo.")
        if self.get(name):
            return f"Project '{name}' already registered — path: {self.get(name)['path']}"
        self.projects.append({"name": name, "path": str(target.resolve()),
                              "stack": str(stack).strip(),
                              "goal": str(goal).strip(), "added": str(date.today())})
        self._save()
        self._merge_allow()
        return f"Registered: {name} -> {target.resolve()} (ab file access me aa gaya)"

    def use(self, name: str) -> str:
        p = self.get(name)
        if p is None:
            return f"Project '{name}' registered nahi hai — pehle register_project chalao."
        self.active = p
        return f"Ab {p['path']} pe focus 🎯 (stack: {p.get('stack') or '?'})"

    def _merge_allow(self) -> None:
        # dynamic allowlist: registered roots append -> file tools + gate dono
        # same list object share karte hain (main.py se wiring)
        if self.allowed is None:
            return
        for p in self.projects:
            path = str(p.get("path", ""))
            if path and path not in self.allowed:
                self.allowed.append(path)

    def active_context(self) -> str:
        if not self.active:
            return ""
        p = self.active
        return (f"PROJECT CONTEXT (active project): name={p.get('name')}, "
                f"path={p.get('path')}, stack={p.get('stack') or '?'}, "
                f"goal={p.get('goal') or '?'}. Follow-up sawaal isi project ke "
                f"liye samjho — path already hai, dobara mat poochho.")


def git_status(path: str) -> str:
    """Safe git call: fixed args list only, never shell=True / interpolation."""
    if not Path(path).is_dir():
        return f"Folder nahi mila: {path}"
    try:
        proc = subprocess.run(["git", "status", "--porcelain"], cwd=path,
                              capture_output=True, text=True, timeout=10)
    except FileNotFoundError:
        return "git command nahi mila — Git install karo (git-scm.com)."
    except (subprocess.TimeoutExpired, OSError):
        return "git status fail (timeout/lock) — thodi der baad try karo."
    if proc.returncode != 0:
        return "git repo nahi — 'git init' chalu karna ho toh bolo"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return "Clean — sab committed, koi pending change nahi."
    changed = [line for line in lines if not line.startswith("??")]
    untracked = [line for line in lines if line.startswith("??")]
    top = "\n".join(f"  {line[:90]}" for line in lines[:5])
    return (f"{len(changed)} changed, {len(untracked)} untracked\n"
            f"Top files:\n{top}")


def _tree(root: Path, budget: int = 40) -> list[str]:
    """Top 2-level tree: dirs + files, max ~budget entries."""
    out: list[str] = []
    for child in sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if len(out) >= budget:
            out.append("  ...(aur entries truncated)")
            return out
        if child.is_dir():
            if child.name in {"__pycache__", ".git", "node_modules", ".venv"}:
                continue
            out.append(f"[DIR]  {child.name}/")
            for sub in sorted(child.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if len(out) >= budget:
                    break
                out.append(f"  [DIR]  {sub.name}/" if sub.is_dir()
                           else f"  [FILE] {sub.name}")
        else:
            out.append(f"[FILE] {child.name}")
    return out


def register_project_tools(registry: ToolRegistry, projects: ProjectRegistry) -> None:
    def _find(name: str) -> dict | None:
        return projects.get(str(name))

    def register_project(name: str, path: str, stack: str = "",
                         goal: str = "") -> str:
        return projects.add(str(name), str(path), str(stack), str(goal))

    def list_projects() -> str:
        if not projects.projects:
            return "Koi project registered nahi — register_project se shuru karo."
        return "\n".join(
            f"{p.get('name')} — {p.get('path')} [{p.get('stack') or '?'}]"
            + ("  <- ACTIVE" if p is projects.active else "")
            for p in projects.projects)

    def project_overview(name: str) -> str:
        p = _find(name)
        if p is None:
            return f"Project '{name}' nahi mila — list_projects dekho."
        root = Path(str(p.get("path", "")))
        if not root.is_dir():
            return f"Path exist nahi karta: {p.get('path')} — registry theek karo."
        out = [f"{p.get('name')} ({p.get('stack') or '?'}) — {p.get('goal') or '?'}",
               f"Path: {root}", "Tree (top 2 levels):"]
        out += ["  " + line for line in _tree(root)]
        readme = root / "README.md"
        if readme.is_file():
            text = readme.read_text(encoding="utf-8", errors="replace")[:500]
            out += ["", "README (first 500 chars):", text]
        out += ["", "Git:", git_status(str(root))]
        return "\n".join(out)

    def git_status_tool(name: str) -> str:
        p = _find(name)
        if p is None:
            return f"Project '{name}' nahi mila — list_projects dekho."
        return git_status(str(p.get("path", "")))

    def use_project(name: str) -> str:
        return projects.use(str(name))

    registry.register(Tool("register_project", "Naya project registry me add karta "
        "hai (path exist hona chahiye) — uska file access khul jaata hai.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Chhota unique naam"},
            "path": {"type": "string", "description": "Project folder path"},
            "stack": {"type": "string", "description": "python/go/js..."},
            "goal": {"type": "string", "description": "Project ka goal 1 line"}},
         "required": ["name", "path"]}, register_project, risk="ask"))
    registry.register(Tool("list_projects", "Saare registered projects: naam, path, stack.",
        {"type": "object", "properties": {}}, list_projects, risk="auto"))
    registry.register(Tool("project_overview", "Project ka overview: stack, goal, "
        "2-level tree, README snippet, git status — kaam se PEHLE ye dekho.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Project naam"}},
         "required": ["name"]}, project_overview, risk="auto"))
    registry.register(Tool("git_status", "Project pe safe git status (changed/"
        "untracked counts + top 5 files). Fixed args, timeout 10s.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Project naam"}},
         "required": ["name"]}, git_status_tool, risk="auto"))
    registry.register(Tool("use_project", "Session ka active project set karta hai "
        "— follow-up sawaal usi project ke liye honge.",
        {"type": "object", "properties": {
            "name": {"type": "string", "description": "Project naam"}},
         "required": ["name"]}, use_project, risk="auto"))
