"""DPO Self-Evolution Flywheel — Continuous Preference & Self-Healing Dataset Builder.

Transforms LUMI-OS's runtime experiences into Direct Preference Optimization (DPO)
training trajectories stored in `data/dpo_flywheel.jsonl` (git-ignored under `data/*.jsonl`).

Captures:
  1. Explicit & Implicit Preference Pairs: `(prompt, chosen, rejected, category, metadata)`
  2. Self-Healed Tool Repair Trajectories: when a tool call or DAG node initially fails
     (`rejected` call/arguments + error) and subsequently succeeds (`chosen` call/arguments)
  3. Reflection-Guided Corrections: turns where `evolution/reflect.py` identifies a
     `minor` or `major` lesson with concrete `improve_next` guidance.
  4. Readiness telemetry (`get_flywheel_stats`) and TRL/Unsloth-compatible DPO export.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from tools.registry import Tool, ToolRegistry


class DPOFlywheel:
    """Thread-safe DPO preference pair collector and LoRA/DPO dataset exporter."""

    def __init__(
        self,
        dataset_path: str | Path = "data/dpo_flywheel.jsonl",
        ready_threshold: int = 50,
    ) -> None:
        self.dataset_path = Path(dataset_path)
        self.ready_threshold = max(1, int(ready_threshold))
        self._lock = threading.Lock()
        self.dataset_path.parent.mkdir(parents=True, exist_ok=True)

    def record_preference_pair(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
        category: str = "general",
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Appends a validated `(prompt, chosen, rejected)` DPO tuple to `data/dpo_flywheel.jsonl`."""
        p = (prompt or "").strip()
        c = (chosen or "").strip()
        r = (rejected or "").strip()
        if not p or not c or not r or c == r:
            return {"recorded": False, "error": "prompt, chosen, and distinct rejected strings are required."}

        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "category": (category or "general").strip().lower(),
            "prompt": p[:4000],
            "chosen": c[:4000],
            "rejected": r[:4000],
            "reason": (reason or "self_evolution_flywheel").strip()[:500],
            "metadata": metadata or {},
        }

        with self._lock:
            with open(self.dataset_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return {"recorded": True, "entry": entry}

    def record_tool_repair(
        self,
        user_prompt: str,
        tool_name: str,
        failed_args: dict[str, Any] | str,
        failed_error: str,
        healed_args: dict[str, Any] | str,
        healed_result: str = "",
    ) -> dict[str, Any]:
        """Records a self-healed tool execution trajectory as a DPO preference pair."""
        prompt_str = (
            f"User Goal: {user_prompt}\n"
            f"Target Tool: {tool_name}\n"
            f"Task: Invoke `{tool_name}` with valid, safe arguments that succeed without errors."
        )
        chosen_str = json.dumps(
            {"tool": tool_name, "arguments": healed_args, "outcome": healed_result[:300] or "ok"},
            ensure_ascii=False,
        )
        rejected_str = json.dumps(
            {"tool": tool_name, "arguments": failed_args, "error": failed_error[:300]},
            ensure_ascii=False,
        )
        return self.record_preference_pair(
            prompt=prompt_str,
            chosen=chosen_str,
            rejected=rejected_str,
            category="tool_self_healing",
            reason=f"Tool '{tool_name}' failed with '{failed_error[:120]}' and was self-healed.",
            metadata={"tool": tool_name},
        )

    def load_entries(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Reads recorded DPO pairs from disk."""
        if not self.dataset_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self._lock:
            try:
                with open(self.dataset_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except Exception:
                return []
        if limit and limit > 0:
            return entries[-limit:]
        return entries

    def get_flywheel_stats(self) -> dict[str, Any]:
        """Computes dataset readiness metrics, category breakdown, and file size."""
        entries = self.load_entries()
        total = len(entries)
        categories: dict[str, int] = {}
        for e in entries:
            cat = str(e.get("category") or "general")
            categories[cat] = categories.get(cat, 0) + 1

        size_kb = (
            round(self.dataset_path.stat().st_size / 1024.0, 2)
            if self.dataset_path.exists()
            else 0.0
        )
        progress_pct = min(100, int((total / self.ready_threshold) * 100))
        return {
            "dataset_path": str(self.dataset_path),
            "total_pairs": total,
            "ready_threshold": self.ready_threshold,
            "ready_for_dpo_training": total >= self.ready_threshold,
            "readiness_pct": progress_pct,
            "categories": categories,
            "file_size_kb": size_kb,
            "latest_timestamp": entries[-1].get("timestamp") if entries else None,
        }

    def export_trl_dataset(self, output_path: str | Path = "data/dpo_trl_export.jsonl") -> dict[str, Any]:
        """Exports clean HuggingFace TRL / Unsloth DPO trainer format (`prompt`, `chosen`, `rejected`)."""
        entries = self.load_entries()
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with self._lock:
            with open(out_file, "w", encoding="utf-8") as f:
                for e in entries:
                    if e.get("prompt") and e.get("chosen") and e.get("rejected"):
                        row = {
                            "prompt": e["prompt"],
                            "chosen": e["chosen"],
                            "rejected": e["rejected"],
                        }
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        count += 1
        return {
            "exported_count": count,
            "output_path": str(out_file),
            "ready": count >= self.ready_threshold,
        }


_GLOBAL_FLYWHEEL: DPOFlywheel | None = None


def get_dpo_flywheel(dataset_path: str | Path = "data/dpo_flywheel.jsonl") -> DPOFlywheel:
    global _GLOBAL_FLYWHEEL
    if _GLOBAL_FLYWHEEL is None:
        _GLOBAL_FLYWHEEL = DPOFlywheel(dataset_path=dataset_path)
    return _GLOBAL_FLYWHEEL


def register_dpo_flywheel_tools(
    registry: ToolRegistry,
    dataset_path: str | Path = "data/dpo_flywheel.jsonl",
) -> DPOFlywheel:
    flywheel = get_dpo_flywheel(dataset_path=dataset_path)

    def dpo_flywheel_status(export_trl: bool = False) -> str:
        """Returns DPO Self-Evolution Flywheel statistics, category breakdown, and training readiness."""
        st = flywheel.get_flywheel_stats()
        badge = "🟢 READY FOR DPO FINETUNE" if st["ready_for_dpo_training"] else "🟡 COLLECTING TRAJECTORIES"
        lines = [
            f"### 🧬 LUMI DPO Self-Evolution Flywheel ({badge})",
            f"- **Dataset File:** `{st['dataset_path']}` (`{st['file_size_kb']} KB`)",
            f"- **Preference Pairs Collected:** `{st['total_pairs']} / {st['ready_threshold']}` (`{st['readiness_pct']}%`)",
            f"- **Categories:** `{json.dumps(st['categories'])}`",
        ]
        if export_trl:
            exp = flywheel.export_trl_dataset()
            lines.append(
                f"- **TRL/Unsloth Export:** Exported `{exp['exported_count']}` pairs to `{exp['output_path']}`"
            )
        return "\n".join(lines)

    def record_dpo_preference(
        prompt: str,
        chosen: str,
        rejected: str,
        category: str = "code_repair",
        reason: str = "",
    ) -> str:
        """Records a `(prompt, chosen, rejected)` preference trajectory into the DPO self-evolution flywheel."""
        res = flywheel.record_preference_pair(
            prompt=prompt,
            chosen=chosen,
            rejected=rejected,
            category=category,
            reason=reason,
        )
        if not res.get("recorded"):
            return f"❌ Failed to record DPO pair: {res.get('error')}"
        st = flywheel.get_flywheel_stats()
        return (
            f"✅ Recorded DPO preference pair under `{category}`. "
            f"Total flywheel pairs: `{st['total_pairs']}/{st['ready_threshold']}` (`{st['readiness_pct']}%`)."
        )

    registry.register(
        Tool(
            name="dpo_flywheel_status",
            description="Inspects the DPO Self-Evolution Flywheel dataset statistics, category counts, and LoRA/DPO fine-tuning readiness.",
            params_schema={
                "type": "object",
                "properties": {
                    "export_trl": {
                        "type": "boolean",
                        "description": "If true, exports a clean TRL/Unsloth JSONL dataset to data/dpo_trl_export.jsonl.",
                        "default": False,
                    },
                },
            },
            handler=dpo_flywheel_status,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="record_dpo_preference",
            description="Records a (prompt, chosen, rejected) preference pair or self-healed code/tool trajectory into the DPO flywheel.",
            params_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The user prompt or task context."},
                    "chosen": {"type": "string", "description": "The verified/superior response or self-healed tool call."},
                    "rejected": {"type": "string", "description": "The suboptimal/failed response or broken tool call."},
                    "category": {
                        "type": "string",
                        "description": "Category tag (e.g. 'tool_self_healing', 'code_repair', 'hinglish_style').",
                        "default": "code_repair",
                    },
                    "reason": {"type": "string", "description": "Why the chosen response is superior to the rejected one."},
                },
                "required": ["prompt", "chosen", "rejected"],
            },
            handler=record_dpo_preference,
            risk="auto",
        )
    )

    return flywheel
