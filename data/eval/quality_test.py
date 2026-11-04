"""A/B response-quality harness — local (llama3.1:8b) vs cloud (nemotron-120b).

10 mixed prompts (Hinglish chat, reasoning, explain, format, tool) — har prompt
ke dono provider outputs save hote hain:
    data/eval/run_YYYYMMDD/local/prompt_NN.txt
    data/eval/run_YYYYMMDD/cloud/prompt_NN.txt
Chalao:  python data/eval/quality_test.py
Phir side-by-side table (manual review checklist: accuracy/format/tone/length).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from brain.cloud_adapter import NVIDIABrain          # noqa: E402
from brain.ollama_adapter import OllamaBrain, load_config  # noqa: E402
from tools.files import register_file_tools          # noqa: E402
from tools.registry import ToolRegistry              # noqa: E402

# (prompt, needs_tool_loop) — 10 mixed: chat / reasoning / explain / format / tool
PROMPTS = [
    ("what is your name? aur kya kar sakta hai — 3 line me", False),
    ("aaj ka din kaisa raha tera? — natural reply de, 2 line", False),
    ("recursion kya hota hai? 5 line me samjha do", False),
    ("python me list vs tuple — table format me fark batao", False),
    ("quick sort ka dry run: [7,2,5,1,9] step by step", False),
    ("decimal 0.1 + 0.2 kyu 0.3 nahi hota? simple bhasha me", False),
    ("csv mean nikalne ka chhota python script do (code block me)", False),
    ("code review: def f(l): return sorted(l)[-1] — isme kya dikkat hai?", False),
    ("git ke 5 common commands, har ek ki 1 line body — numbered list", False),
    ("downloads folder ki list dikhao", True),           # tool turn (mini loop)
]


def tool_loop(brain, prompt: str) -> str:
    """1 tool round — orchestrator jaisa wire format, bina DB/gate ke."""
    allowed = list(load_config("config.yaml").get("allowed_paths") or [])
    registry = ToolRegistry()
    register_file_tools(registry, allowed)
    schemas = registry.to_llm_schemas()
    messages: list[dict] = [{"role": "user", "content": prompt}]
    for _ in range(3):
        reply = brain.chat(messages, tools=schemas)
        if not reply.tool_calls:
            return reply.text or "(khaali reply)"
        wire = []
        for i, call in enumerate(reply.tool_calls, 1):
            cid = f"eval_{i}"
            wire.append({"id": cid, "type": "function",
                         "function": {"name": call["name"],
                                      "arguments": call.get("args") or {}}})
            tool = registry.get(call["name"])
            try:
                result = tool.handler(**(call.get("args") or {})) if tool else "unknown tool"
            except Exception as exc:  # noqa: BLE001 — harness = keep going
                result = f"Tool error: {exc}"
            messages.append({"role": "tool", "content": str(result),
                             "tool_call_id": cid})
        messages.append({"role": "assistant", "content": reply.text or "",
                         "tool_calls": wire})
    return "(tool loop cap)"


def one(brain, prompt: str, use_tool: bool) -> str:
    try:
        return tool_loop(brain, prompt) if use_tool else (
            brain.chat([{"role": "user", "content": prompt}]).text or "(khaali)")
    except Exception as exc:  # noqa: BLE001 — provider down = record, aage badho
        return f"(FAILED: {exc})"


def preview(text: str, n: int = 70) -> str:
    return " ".join(text.replace("\n", " ").split())[:n]


def next_run_dir() -> Path:
    """run_YYYYMMDD_NN — N auto-increment (champion-challenger ka data layout)."""
    base = ROOT / "data" / "eval"
    day = f"{date.today():%Y%m%d}"
    n = 1
    while (base / f"run_{day}_{n:02d}").exists():
        n += 1
    return base / f"run_{day}_{n:02d}"


def run_eval(brain) -> dict:
    """CALLABLE (/eval run) — 10 prompts × current policy brain, avg ms + paths."""
    run_dir = next_run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    times: list[int] = []
    for i, (prompt, use_tool) in enumerate(PROMPTS, 1):
        t0 = time.time()
        out = one(brain, prompt, use_tool)
        ms = int((time.time() - t0) * 1000)
        times.append(ms)
        (run_dir / f"prompt_{i:02d}.txt").write_text(
            f"PROMPT: {prompt}\nMS: {ms}\n{'=' * 60}\n{out}\n", encoding="utf-8")
        print(f"[eval {i}/10] {ms}ms  {preview(prompt, 45)}")
    summary = {"run": run_dir.name, "prompts": len(times),
               "avg_ms": round(sum(times) / len(times)),
               "per_prompt_ms": times}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2),
                                          encoding="utf-8")
    return summary


def compare_eval() -> str:
    """/eval compare — last 2 runs ka meta diff (paths + lines + avg ms)."""
    runs = sorted(p for p in (ROOT / "data" / "eval").glob("run_*_*")
                  if p.is_dir())
    if len(runs) < 2:
        return "Compare ke liye 2 runs chahiye — pehle /eval run chalao."
    a, b = runs[-2], runs[-1]

    def meta(p: Path) -> tuple[int, int]:
        files = list(p.glob("prompt_*.txt"))
        lines = sum(len(f.read_text(encoding="utf-8").splitlines()) for f in files)
        return len(files), lines

    def avg(p: Path):
        try:
            return json.loads((p / "summary.json").read_text(encoding="utf-8"))["avg_ms"]
        except (OSError, ValueError, KeyError):
            return "?"
    fa, la = meta(a)
    fb, lb = meta(b)
    return (f"eval compare (content review tum karo) —\n"
            f"  {a.name}: {fa} files, {la} lines, avg {avg(a)}ms\n"
            f"  {b.name}: {fb} files, {lb} lines, avg {avg(b)}ms")


def main() -> None:
    config = load_config("config.yaml")
    local = OllamaBrain(config=config)
    cloud = None
    if os.environ.get("NVIDIA_API_KEY"):
        try:
            cloud = NVIDIABrain(config)
        except Exception as exc:  # noqa: BLE001
            print(f"cloud init fail: {exc}")
    else:
        print("NOTE: NVIDIA_API_KEY missing — cloud column hogi (skipped)")
    run_dir = ROOT / "data" / "eval" / f"run_{date.today():%Y%m%d}"
    for prov in ("local", "cloud"):
        (run_dir / prov).mkdir(parents=True, exist_ok=True)

    rows = []
    for i, (prompt, use_tool) in enumerate(PROMPTS, 1):
        out = {}
        for prov, brain in (("local", local), ("cloud", cloud)):
            if brain is None:
                out[prov] = "(skipped — key missing)"
                continue
            print(f"[{i}/10] {prov}: {preview(prompt, 50)} ...")
            out[prov] = one(brain, prompt, use_tool)
            (run_dir / prov / f"prompt_{i:02d}.txt").write_text(
                f"PROMPT: {prompt}\n{'=' * 60}\n{out[prov]}\n", encoding="utf-8")
        rows.append((i, prompt, out))

    # side-by-side review table (console + run_YYYYMMDD/REPORT.md)
    table = ["# A/B quality report — " + str(date.today()), ""]
    for i, prompt, out in rows:
        table.append(f"## {i}. {prompt}")
        for prov in ("local", "cloud"):
            table.append(f"- **{prov}** ({len(out[prov])} chars): {preview(out[prov], 160)}")
            table.append(f"  - full: `{prov}/prompt_{i:02d}.txt`")
        table.append("")
    (run_dir / "REPORT.md").write_text("\n".join(table), encoding="utf-8")
    print("\n" + "=" * 60)
    for i, prompt, out in rows:
        print(f"{i:>2}. {preview(prompt, 45):<45} L={len(out['local']):>5}"
              f"  C={len(out['cloud']):>5}")
    print(f"\nsaved: {run_dir} (local/, cloud/, REPORT.md)")


if __name__ == "__main__":
    main()
