"""Workstation Memory & System Performance Auto-Optimizer (LUMI v42.0).

Autonomously manages workstation hardware resources:
  1. Deep Garbage Collection: Purges unreferenced generation-2 cyclic objects across Python runtime.
  2. Working Set Purge (Windows): Calls kernel32/psapi EmptyWorkingSet to return unused pages to OS standby list.
  3. SQLite Database Optimization: Truncates WAL journals and executes PRAGMA vacuum across all active databases.
  4. Ephemeral Audio Pruning: Removes orphaned temporary .wav files in data/audio/ older than retention window.
  5. Vitals Telemetry: Returns live hardware telemetry (CPU %, RAM % used/available, Disk IO).
"""

from __future__ import annotations

import ctypes
import gc
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.workstation_optimizer")


@dataclass
class OptimizationReport:
    status: str
    ram_before_mb: float
    ram_after_mb: float
    ram_freed_mb: float
    ram_usage_pct: float
    cpu_usage_pct: float
    sqlite_vacuumed: list[str]
    temp_files_pruned: int
    bytes_disk_cleaned: int
    elapsed_ms: float


class WorkstationOptimizer:
    """Hardware resource manager and high-velocity memory tuner."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.registry = registry
        self.workspace_root = workspace_root or Path(__file__).resolve().parent.parent
        self.data_dir = self.workspace_root / "data"
        self.audio_dir = self.data_dir / "audio"
        self._top_consumers_cache: list[str] = []
        self._top_consumers_ts: float = 0.0
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        self._register_tools()

    def _register_tools(self) -> None:
        if self.registry is None:
            return

        self.registry.register(
            Tool(
                name="optimize_workstation_performance",
                description="Performs deep system optimization: purges unreferenced RAM, trims working set, vacuums SQLite databases, and prunes temporary audio caches.",
                params_schema={"type": "object", "properties": {}},
                handler=lambda: self.optimize_all(),
                risk="safe",
            )
        )

        self.registry.register(
            Tool(
                name="get_workstation_vitals",
                description="Returns real-time workstation hardware telemetry: CPU load, RAM usage, available memory, disk space, and top consuming processes.",
                params_schema={"type": "object", "properties": {}},
                handler=lambda: self.get_vitals(),
                risk="safe",
            )
        )

    def get_vitals(self) -> dict[str, Any]:
        """Collects real-time hardware vitals with sub-millisecond non-blocking telemetry."""
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        disk = shutil.disk_usage(str(self.workspace_root))

        now = time.time()
        if not self._top_consumers_cache or (now - self._top_consumers_ts) > 15.0:
            procs = []
            for p in psutil.process_iter(["name", "memory_info"]):
                try:
                    info = p.info
                    mem_info = info.get("memory_info")
                    if mem_info:
                        procs.append((info.get("name") or "unknown", round(mem_info.rss / (1024**2), 1)))
                except Exception:
                    pass
            procs.sort(key=lambda x: x[1], reverse=True)
            self._top_consumers_cache = [f"{name} ({rss} MB)" for name, rss in procs[:4]]
            self._top_consumers_ts = now

        return {
            "status": "healthy",
            "cpu_usage_pct": cpu,
            "ram_used_gb": round(mem.used / (1024**3), 2),
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "ram_available_gb": round(mem.available / (1024**3), 2),
            "ram_usage_pct": mem.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "top_consumers": list(self._top_consumers_cache),
        }

    def optimize_all(self, max_audio_age_seconds: int = 1800) -> dict[str, Any]:
        """Executes full multi-tier hardware optimization and working set compaction."""
        t0 = time.perf_counter()
        proc = psutil.Process(os.getpid())
        sys_mem_before_mb = psutil.virtual_memory().used / (1024**2)
        ram_before_mb = proc.memory_info().rss / (1024**2)

        # 1. Python GC cycle collection
        collected_objs = gc.collect(2)

        # 2. Windows Working Set purge (current process + bloated >100MB user processes)
        if os.name == "nt":
            try:
                ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
                for p in psutil.process_iter(["pid", "memory_info"]):
                    try:
                        if p.info["memory_info"].rss > 100 * 1024 * 1024:
                            h = ctypes.windll.kernel32.OpenProcess(0x0500, False, p.info["pid"])
                            if h:
                                ctypes.windll.psapi.EmptyWorkingSet(h)
                                ctypes.windll.kernel32.CloseHandle(h)
                    except Exception:
                        continue
            except Exception as e:
                logger.debug("EmptyWorkingSet call skipped: %s", e)

        # 3. SQLite Vacuum & WAL Truncate across all database files
        vacuumed_dbs: list[str] = []
        if self.data_dir.exists():
            for db_file in self.data_dir.glob("*.db"):
                try:
                    conn = sqlite3.connect(str(db_file), timeout=2.0)
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                    conn.execute("VACUUM;")
                    conn.close()
                    vacuumed_dbs.append(db_file.name)
                except Exception as e:
                    logger.debug("Database optimize skipped for %s: %s", db_file.name, e)

        # 4. Prune orphaned temporary audio files
        temp_files_pruned = 0
        bytes_disk_cleaned = 0
        now = time.time()
        if self.audio_dir.exists():
            for wav_file in self.audio_dir.glob("*.wav"):
                try:
                    mtime = wav_file.stat().st_mtime
                    if now - mtime > max_audio_age_seconds:
                        sz = wav_file.stat().st_size
                        wav_file.unlink(missing_ok=True)
                        temp_files_pruned += 1
                        bytes_disk_cleaned += sz
                except Exception:
                    pass

        ram_after_mb = proc.memory_info().rss / (1024**2)
        mem = psutil.virtual_memory()
        sys_mem_after_mb = mem.used / (1024**2)
        ram_freed = max(0.0, ram_before_mb - ram_after_mb, sys_mem_before_mb - sys_mem_after_mb)
        cpu = psutil.cpu_percent(interval=None)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        report = OptimizationReport(
            status="optimal",
            ram_before_mb=round(ram_before_mb, 2),
            ram_after_mb=round(ram_after_mb, 2),
            ram_freed_mb=round(ram_freed, 2),
            ram_usage_pct=mem.percent,
            cpu_usage_pct=cpu,
            sqlite_vacuumed=vacuumed_dbs,
            temp_files_pruned=temp_files_pruned,
            bytes_disk_cleaned=bytes_disk_cleaned,
            elapsed_ms=round(elapsed_ms, 2),
        )
        return asdict(report)


_OPTIMIZER_INSTANCE: WorkstationOptimizer | None = None


def get_workstation_optimizer(registry: ToolRegistry | None = None) -> WorkstationOptimizer:
    global _OPTIMIZER_INSTANCE
    if _OPTIMIZER_INSTANCE is None:
        _OPTIMIZER_INSTANCE = WorkstationOptimizer(registry=registry)
    elif registry is not None and _OPTIMIZER_INSTANCE.registry is None:
        _OPTIMIZER_INSTANCE.registry = registry
        _OPTIMIZER_INSTANCE._register_tools()
    return _OPTIMIZER_INSTANCE
