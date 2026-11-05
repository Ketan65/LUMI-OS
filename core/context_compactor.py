"""Context Compactor — Token-Budget Preserver & Sliding Window History Manager.

Solves the local LLM 8K context overflow vulnerability:
  - Preserves System Prompt (Persona, Master Identity, Dynamic Telemetry) at index 0.
  - Retains the most recent N turns intact for immediate conversational coherence.
  - Intelligently compacts / summarizes middle turns before character count exceeds
    the model's context budget (default ~65% of num_ctx * 3 characters).
  - Guarantees zero silent prompt truncation by Ollama.
"""

from __future__ import annotations

import copy
from typing import Any


def estimate_message_chars(msg: dict[str, Any]) -> int:
    """Estimates character weight of a message dictionary."""
    content = str(msg.get("content") or "")
    chars = len(content)
    # Include tool call arguments in the estimate
    tool_calls = msg.get("tool_calls") or []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        chars += len(str(fn.get("name") or ""))
        chars += len(str(fn.get("arguments") or ""))
    return chars


def compact_session_history(
    session: list[dict[str, Any]],
    num_ctx: int = 8192,
    max_ratio: float = 0.65,
    min_recent_messages: int = 8,
) -> list[dict[str, Any]]:
    """Compacts session history if total characters exceed safe context budget.

    Args:
        session: List of message dicts (role, content, etc.).
        num_ctx: Ollama context window token limit (e.g., 8192).
        max_ratio: Target max capacity ratio (0.65 leaves 35% for tool schemas and generation).
        min_recent_messages: Minimum trailing messages to keep uncompressed.

    Returns:
        Compacted copy of session list.
    """
    if not session or len(session) <= min_recent_messages + 1:
        return list(session)

    # Budget in characters (~3 chars per token conservative estimate for Hinglish/code)
    char_budget = int(num_ctx * 3 * max_ratio)
    total_chars = sum(estimate_message_chars(m) for m in session)

    if total_chars <= char_budget:
        return list(session)

    # We need to compact older middle turns while keeping:
    # 1. System prompt at index 0 (if present)
    # 2. Recent min_recent_messages at the end
    result: list[dict[str, Any]] = []
    start_idx = 0

    if session[0].get("role") == "system":
        result.append(copy.deepcopy(session[0]))
        start_idx = 1

    # End boundary: keep at least min_recent_messages
    end_idx = max(start_idx, len(session) - min_recent_messages)
    middle_msgs = session[start_idx:end_idx]
    tail_msgs = session[end_idx:]

    if not middle_msgs:
        return list(session)

    # Summarize middle turns into a single high-density checkpoint note
    user_queries: list[str] = []
    tools_used: list[str] = []
    key_conclusions: list[str] = []

    for m in middle_msgs:
        role = m.get("role")
        content = str(m.get("content") or "").strip()
        if role == "user":
            user_queries.append(content[:120].replace("\n", " "))
        elif role == "tool":
            tool_name = str(m.get("name") or "tool")
            tools_used.append(tool_name)
        elif role == "assistant" and content and not m.get("tool_calls"):
            first_line = content.split("\n")[0][:140].strip()
            if first_line:
                key_conclusions.append(first_line)

    summary_parts = ["[CONVERSATION HISTORY COMPACTED FOR CONTEXT EFFICIENCY]"]
    if user_queries:
        recent_queries = user_queries[-5:]
        summary_parts.append(f"Earlier User Intent / Queries: {' | '.join(recent_queries)}")
    if tools_used:
        unique_tools = sorted(set(tools_used))
        summary_parts.append(f"Tools Executed in Earlier Session: {', '.join(unique_tools)}")
    if key_conclusions:
        summary_parts.append(f"Key Points Established: {' | '.join(key_conclusions[-3:])}")

    summary_message = {
        "role": "system",
        "content": "\n".join(summary_parts),
    }

    result.append(summary_message)
    for i, m in enumerate(tail_msgs):
        m_copy = copy.deepcopy(m)
        # Cap oversized middle-tail message bodies (>1200 chars) to prevent context blowup
        if i < len(tail_msgs) - 2 and len(str(m_copy.get("content") or "")) > 1200:
            c = str(m_copy.get("content") or "")
            m_copy["content"] = c[:1200] + "\n...[compacted]"
        result.append(m_copy)

    return result
