"""Async Mission Queue — Non-Blocking Background Execution Engine for LUMI-OS.

Allows heavy multi-step operations (Swarm project builds, Topological DAG missions,
Deep Web Research, Cyber-Sentinel VAPT workspace audits, or custom callables) to
execute asynchronously in a background `ThreadPoolExecutor(max_workers=2)` without
blocking the interactive chat turn!

Features:
  - `submit_mission(name, kind, fn, *args, **kwargs) -> dict`
  - `get_mission(mission_id) -> dict`
  - `list_missions(status=None, limit=20) -> list[dict]`
  - Live progress percentage (`0..100`), timestamped event logs, execution duration,
    and optional notification callback on completion.
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable


class AsyncMissionQueue:
    """Thread-safe non-blocking background mission dispatcher & telemetry tracker."""

    def __init__(
        self,
        max_workers: int = 2,
        on_complete: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.on_complete = on_complete
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="lumi_mission",
        )
        self._lock = threading.Lock()
        self._missions: dict[str, dict[str, Any]] = {}
        self._futures: dict[str, Future] = {}

    def submit_mission(
        self,
        name: str,
        kind: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submits a callable to run asynchronously in the background worker pool."""
        mission_id = f"msn_{uuid.uuid4().hex[:8]}"
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")
        record: dict[str, Any] = {
            "mission_id": mission_id,
            "name": (name or "Background Mission").strip(),
            "kind": (kind or "custom").strip().lower(),
            "status": "queued",
            "progress": 0,
            "created_at": now_str,
            "started_at": None,
            "finished_at": None,
            "elapsed_ms": 0,
            "events": [f"[{now_str}] Mission queued ({kind})"],
            "result": None,
            "error": None,
        }

        with self._lock:
            self._missions[mission_id] = record

        def _runner() -> Any:
            t0 = time.time()
            self.update_progress(mission_id, 10, f"Worker thread started for '{record['name']}'")
            with self._lock:
                self._missions[mission_id]["status"] = "running"
                self._missions[mission_id]["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            try:
                out = fn(*args, **kwargs)
                elapsed = int((time.time() - t0) * 1000)
                summary_str = self._extract_summary(out)
                with self._lock:
                    m = self._missions[mission_id]
                    m["status"] = "completed"
                    m["progress"] = 100
                    m["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    m["elapsed_ms"] = elapsed
                    m["result"] = summary_str
                    m["events"].append(
                        f"[{m['finished_at']}] Mission completed in {elapsed}ms"
                    )
                    snapshot = dict(m)
                if self.on_complete:
                    try:
                        self.on_complete(snapshot)
                    except Exception:
                        pass
                return out
            except Exception as exc:
                elapsed = int((time.time() - t0) * 1000)
                with self._lock:
                    m = self._missions[mission_id]
                    m["status"] = "failed"
                    m["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    m["elapsed_ms"] = elapsed
                    m["error"] = str(exc)
                    m["events"].append(
                        f"[{m['finished_at']}] Mission failed after {elapsed}ms: {exc}"
                    )
                    snapshot = dict(m)
                if self.on_complete:
                    try:
                        self.on_complete(snapshot)
                    except Exception:
                        pass
                raise

        fut = self._executor.submit(_runner)
        with self._lock:
            self._futures[mission_id] = fut
            return dict(self._missions[mission_id])

    def update_progress(self, mission_id: str, progress: int, event_msg: str = "") -> None:
        """Updates live progress percentage (0-100) and appends a timestamped log entry."""
        with self._lock:
            m = self._missions.get(mission_id)
            if not m:
                return
            m["progress"] = max(0, min(100, int(progress)))
            if event_msg:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                m["events"].append(f"[{ts}] {event_msg}")

    def get_mission(self, mission_id: str) -> dict[str, Any] | None:
        """Returns a copy of a specific mission's status and telemetry."""
        with self._lock:
            m = self._missions.get((mission_id or "").strip())
            if not m:
                return None
            return dict(m, events=list(m["events"]))

    def list_missions(self, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Lists recent background missions ordered newest-first."""
        with self._lock:
            items = [dict(m, events=list(m["events"])) for m in self._missions.values()]
        if status:
            st = status.strip().lower()
            items = [m for m in items if m["status"] == st]
        items.reverse()
        return items[: max(1, int(limit))]

    @staticmethod
    def _extract_summary(output: Any) -> str:
        if output is None:
            return "Completed (no output)."
        if isinstance(output, dict):
            for key in ("summary", "dossier_markdown", "standup_markdown", "reply", "verdict"):
                if key in output and output[key]:
                    return str(output[key])[:2000]
            return str(output)[:2000]
        return str(output)[:2000]

    def shutdown(self, wait: bool = False) -> None:
        try:
            self._executor.shutdown(wait=wait, cancel_futures=True)
        except Exception:
            pass


_GLOBAL_QUEUE: AsyncMissionQueue | None = None


def get_mission_queue(max_workers: int = 2) -> AsyncMissionQueue:
    global _GLOBAL_QUEUE
    if _GLOBAL_QUEUE is None:
        _GLOBAL_QUEUE = AsyncMissionQueue(max_workers=max_workers)
    return _GLOBAL_QUEUE
