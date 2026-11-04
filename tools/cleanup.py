"""Cleanup & Disk tools — disk_report for inspecting storage and identifying large files/folders.

Safety:
  - Strictly read-only analysis (no delete or move functionality).
  - Risk policy: "auto".
  - Gracefully ignores inaccessible or protected system directories.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable

from tools.registry import Tool, ToolRegistry


def format_bytes(size: float | int) -> str:
    """Formats bytes into human readable string."""
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    val = float(size)
    while val >= 1024.0 and unit_idx < len(units) - 1:
        val /= 1024.0
        unit_idx += 1
    return f"{val:.1f} {units[unit_idx]}" if unit_idx > 0 else f"{int(val)} B"


def make_disk_reporter(default_base_path: str | Path) -> Callable[..., str]:
    default_dir = Path(default_base_path).expanduser().resolve()

    def disk_report(target_path: str = "", top_n: int = 10) -> str:
        """Inspects disk usage and reports free space and largest items."""
        raw_path = target_path.strip() if target_path else str(default_dir)
        try:
            target = Path(raw_path).expanduser().resolve()
            if not target.exists():
                return f"Path does not exist: {target}"
            if not target.is_dir():
                return f"Path is not a directory: {target}"
        except Exception as exc:
            return f"Invalid path '{raw_path}': {exc}"

        try:
            limit = max(3, min(int(top_n), 30))
        except (TypeError, ValueError):
            limit = 10

        lines: list[str] = [f"📊 Disk Report for: {target}"]

        # 1. Drive statistics
        try:
            usage = shutil.disk_usage(str(target))
            lines.append(
                f"Drive Total: {format_bytes(usage.total)} | "
                f"Used: {format_bytes(usage.used)} | "
                f"Free: {format_bytes(usage.free)}"
            )
        except Exception:
            pass

        lines.append("")

        # 2. Collect top files
        files_collected: list[tuple[int, Path]] = []
        dir_sizes: dict[Path, int] = {}

        try:
            for root, dirs, files in os.walk(str(target)):
                root_path = Path(root)
                # Compute total for top-level subdirectories of target
                is_direct_sub = (root_path.parent == target)

                current_dir_bytes = 0
                for fname in files:
                    try:
                        fpath = root_path / fname
                        fstat = fpath.stat()
                        fsize = fstat.st_size
                        current_dir_bytes += fsize
                        files_collected.append((fsize, fpath))
                    except (PermissionError, OSError):
                        continue

                if is_direct_sub:
                    dir_sizes[root_path] = dir_sizes.get(root_path, 0) + current_dir_bytes
        except Exception as exc:
            lines.append(f"Scan encountered error: {exc}")

        # Top largest files
        files_collected.sort(key=lambda x: x[0], reverse=True)
        lines.append(f"Top {min(limit, len(files_collected))} Largest Files:")
        if files_collected:
            for fsize, fpath in files_collected[:limit]:
                try:
                    rel = fpath.relative_to(target)
                except ValueError:
                    rel = fpath
                lines.append(f"  • {format_bytes(fsize):>10}  |  {rel}")
        else:
            lines.append("  (No files found)")

        lines.append("")

        # Top largest direct subdirectories (if target has subdirs)
        lines.append(f"Direct Subdirectory Sizes:")
        if dir_sizes:
            sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)
            for dpath, dsize in sorted_dirs[:limit]:
                lines.append(f"  • {format_bytes(dsize):>10}  |  {dpath.name}/")
        else:
            lines.append("  (No subdirectories found)")

        return "\n".join(lines)

    return disk_report


def register_cleanup_tools(registry: ToolRegistry, default_path: str | Path) -> None:
    reporter = make_disk_reporter(default_path)
    registry.register(Tool(
        name="disk_report",
        description="Inspects disk usage and lists largest files and directories in a given folder (read-only report).",
        params_schema={
            "type": "object",
            "properties": {
                "target_path": {"type": "string", "description": "Directory path to inspect (defaults to workspace)."},
                "top_n": {"type": "integer", "description": "Number of top files to report (default 10).", "default": 10},
            },
        },
        handler=reporter,
        risk="auto",
    ))
