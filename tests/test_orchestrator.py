"""Orchestrator: turn lock, tool-output cap, protected-write end-to-end."""
import threading

from brain.base import BrainReply
from core.orchestrator import MAX_TOOL_CHARS, Orchestrator
from safety.gate import SafetyGate
from tools.files import register_file_tools
from tools.registry import Tool, ToolRegistry

from conftest import FakeBrain


def make(home, downloads, brain, extra_tools=()):
    allowed = [str(home), str(downloads)]
    cfg = {"allowed_paths": allowed, "max_iterations": 4,
           "permissions": {"write_file": "ask", "delete_file": "ask"}}
    reg = ToolRegistry()
    register_file_tools(reg, allowed)
    for t in extra_tools:
        reg.register(t)
    gate = SafetyGate(cfg)
    return Orchestrator(brain=brain, config=cfg, registry=reg, gate=gate)


def test_turns_never_overlap_across_threads(home, downloads):
    brain = FakeBrain(delay=0.05)
    orch = make(home, downloads, brain)
    ts = [threading.Thread(target=orch.run_turn, args=(f"hi {i}",)) for i in range(5)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert brain.calls == 5
    assert brain.max_concurrent == 1            # lock ne serialize kiya
    roles = [m["role"] for m in orch.session]
    assert roles == ["user", "assistant"] * 5   # history interleave nahi hui


def test_stream_releases_lock_when_client_disconnects(home, downloads):
    orch = make(home, downloads, FakeBrain())
    gen = orch.run_turn_stream("hello")
    next(gen)                                   # turn shuru, lock held
    gen.close()                                 # browser band
    assert orch._turn_lock.acquire(timeout=1)   # lock free hona chahiye
    orch._turn_lock.release()


def test_stream_emits_done_with_reply(home, downloads):
    orch = make(home, downloads, FakeBrain([BrainReply(text="namaste")]))
    events = list(orch.run_turn_stream("hi"))
    assert events[-1]["type"] == "done" and events[-1]["reply"] == "namaste"


def test_model_cannot_write_own_code(home, downloads):
    target = str(home / "safety" / "gate.py")
    brain = FakeBrain([
        BrainReply(tool_calls=[{"name": "write_file",
                                "args": {"path": target, "content": "pwned"}}]),
        BrainReply(text="done")])
    orch = make(home, downloads, brain)
    out = orch.run_turn("rewrite your gate")
    assert (home / "safety" / "gate.py").read_text(encoding="utf-8") == "# gate"
    assert "LUMI ka apna code" in orch.session[-2]["content"]
    assert out["tool_trace"][0]["tool"] == "write_file"


def test_model_can_write_workspace_without_asking(home, downloads):
    target = home / "workspace" / "hello.txt"
    brain = FakeBrain([
        BrainReply(tool_calls=[{"name": "write_file",
                                "args": {"path": str(target), "content": "hi"}}]),
        BrainReply(text="done")])
    orch = make(home, downloads, brain)
    orch.run_turn("save hi")
    assert target.read_text(encoding="utf-8") == "hi"


def test_huge_tool_output_is_truncated_for_model(home, downloads):
    big = Tool("big", "x", {"type": "object", "properties": {}},
               lambda: "A" * 50_000, risk="auto")
    brain = FakeBrain([BrainReply(tool_calls=[{"name": "big", "args": {}}]),
                       BrainReply(text="summary")])
    orch = make(home, downloads, brain, extra_tools=[big])
    orch.run_turn("dump")
    tool_msg = next(m for m in orch.session if m["role"] == "tool")
    assert len(tool_msg["content"]) < MAX_TOOL_CHARS + 200
    assert "truncated" in tool_msg["content"]
