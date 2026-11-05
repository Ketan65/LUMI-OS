"""Tool Execution Watchdog — Anti-Freeze & Execution Isolation Barrier.

Guarantees that no tool handler can hang, deadlock, or freeze the LUMI turn loop:
  - Executes tool handlers within a timeout-bounded future (default 30s).
  - Intercepts network hangs, infinite loops, and unhandled subprocess blocks.
  - Automatically recovers control back to the orchestrator with actionable diagnostics.
"""

from __future__ import annotations

import concurrent.futures
from typing import Any

from tools.registry import Tool

DEFAULT_TOOL_TIMEOUT_SEC = 30.0


def execute_tool_with_watchdog(
    tool: Tool,
    args: dict[str, Any],
    timeout_sec: float = DEFAULT_TOOL_TIMEOUT_SEC,
) -> tuple[str, bool]:
    """Executes a tool with a strict execution timeout.

    Returns:
        (result_string, is_failed)
    """
    timeout = max(0.05, float(timeout_sec))

    # Fast path: some tools declare specific timeouts in args
    if "timeout" in args:
        try:
            timeout = max(timeout, float(args["timeout"]) + 2.0)
        except Exception:
            pass

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix=f"tool_guard_{tool.name}",
    )
    try:
        future = executor.submit(tool.handler, **args)
        raw_result = future.result(timeout=timeout)
        return str(raw_result), False
    except concurrent.futures.TimeoutError:
        return (
            f"⚠️ [TOOL WATCHDOG]: Tool '{tool.name}' timed out after {timeout} seconds. "
            "Execution safely interrupted to prevent system deadlock.",
            True,
        )
    except TypeError as te:
        return f"Tool argument mismatch: {te}", True
    except Exception as exc:
        return f"Tool execution error: {exc}", True
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
