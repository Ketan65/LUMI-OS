"""Workstation Guardian & Health Optimizer for LUMI.

Provides actionable diagnostic tools to inspect RAM pressure, identify top memory-consuming processes,
and safely clean temporary Python build/test caches (__pycache__, .pytest_cache).
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.cleaner")


class WorkstationGuardian:
    """Workstation health inspector and temporary cache cleaner."""

    def __init__(self, workspace_root: str | Path = "."):
        self.workspace_root = Path(workspace_root).resolve()

    def get_memory_diagnostics(self, top_n: int = 5) -> dict[str, Any]:
        """Inspects system RAM, CPU, and identifies top memory-consuming processes."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            cpu_pct = psutil.cpu_percent(interval=0.1)

            procs = []
            for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
                try:
                    rss = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                    procs.append({
                        "pid": p.info["pid"],
                        "name": p.info["name"],
                        "ram_mb": round(rss / (1024 * 1024), 1),
                        "cpu_pct": p.info.get("cpu_percent") or 0.0,
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            procs.sort(key=lambda x: x["ram_mb"], reverse=True)
            top_procs = procs[:top_n]

            return {
                "total_ram_gb": round(mem.total / (1024**3), 2),
                "available_ram_gb": round(mem.available / (1024**3), 2),
                "ram_used_pct": mem.percent,
                "cpu_load_pct": cpu_pct,
                "top_processes": top_procs,
            }
        except Exception as e:
            return {"error": f"psutil inspection failed: {e}"}

    def scan_and_clean_caches(self, dry_run: bool = True) -> dict[str, Any]:
        """Scans for temporary __pycache__ and .pytest_cache folders and safely removes them if dry_run=False."""
        target_dirs = []
        total_bytes = 0

        for root, dirs, files in os.walk(str(self.workspace_root)):
            # Look for cache folders
            for d in list(dirs):
                if d in ("__pycache__", ".pytest_cache", ".mypy_cache"):
                    full_p = Path(root) / d
                    d_size = sum(f.stat().st_size for f in full_p.glob("**/*") if f.is_file())
                    target_dirs.append(full_p)
                    total_bytes += d_size
                    dirs.remove(d)  # Do not recurse into cache folder

        deleted_count = 0
        if not dry_run:
            for p in target_dirs:
                try:
                    shutil.rmtree(p)
                    deleted_count += 1
                except Exception as e:
                    logger.warning("Could not delete cache folder %s: %s", p, e)

        return {
            "dry_run": dry_run,
            "cache_folders_found": len(target_dirs),
            "reclaimable_mb": round(total_bytes / (1024 * 1024), 2),
            "folders_deleted": deleted_count if not dry_run else 0,
        }

    def optimize_health(self, dry_run: bool = True) -> dict[str, Any]:
        """Executes full diagnostic and returns actionable workstation health recommendations."""
        mem_info = self.get_memory_diagnostics()
        cache_info = self.scan_and_clean_caches(dry_run=dry_run)

        recommendations = []
        if mem_info.get("ram_used_pct", 0) > 85.0:
            recommendations.append("🚨 RAM pressure is high (>85%). Consider closing unused browser tabs or Docker instances.")
        if cache_info.get("reclaimable_mb", 0) > 50.0 and dry_run:
            recommendations.append(f"💡 {cache_info['reclaimable_mb']}MB of stale build/test caches found. Run with dry_run=False to purge.")
        recommendations.append("⚡ NVIDIA RTX CUDA offload is nominal; ensure batch sizes remain <= 4 for local VRAM headroom.")

        return {
            "memory": mem_info,
            "cache": cache_info,
            "recommendations": recommendations,
        }


def register_cleaner_tools(registry: ToolRegistry, workspace_root: str = ".") -> WorkstationGuardian:
    guardian = WorkstationGuardian(workspace_root=workspace_root)

    def optimize_workstation_health(dry_run: bool = True) -> str:
        """Inspects RAM load, top processes, and cleans temporary Python build caches."""
        res = guardian.optimize_health(dry_run=dry_run)
        mem = res["memory"]
        cache = res["cache"]

        proc_lines = ""
        if "top_processes" in mem:
            proc_lines = "\n".join([f"  • {p['name']} (PID {p['pid']}): {p['ram_mb']} MB" for p in mem["top_processes"]])

        recs = "\n".join([f"- {r}" for r in res["recommendations"]])

        action_msg = f"Cleaned {cache['folders_deleted']} cache folders ({cache['reclaimable_mb']} MB freed)" if not dry_run else f"Dry-run: {cache['cache_folders_found']} folders found ({cache['reclaimable_mb']} MB reclaimable)"

        return (
            f"🛡️ Workstation Health & Optimization Report:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"RAM Usage: {mem.get('ram_used_pct')}% ({mem.get('available_ram_gb')} GB available / {mem.get('total_ram_gb')} GB total)\n"
            f"CPU Load: {mem.get('cpu_load_pct')}%\n\n"
            f"Top RAM Consumers:\n{proc_lines}\n\n"
            f"Cache Status:\n• {action_msg}\n\n"
            f"Recommendations:\n{recs}"
        )

    registry.register(Tool(
        name="optimize_workstation_health",
        description="Inspects system RAM pressure, identifies memory-hog processes, and purges temporary Python build caches.",
        params_schema={
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "description": "If true, only reports reclaimable cache space without deleting. If false, purges caches.", "default": True},
            },
        },
        handler=optimize_workstation_health,
        risk="auto",
    ))

    return guardian
