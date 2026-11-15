# 🚀 LUMI-OS Market Launch & Viral Distribution Playbook

This playbook contains the **60-Second No-Cut Video Script** and ready-to-post launch copy for **Hacker News (`Show HN`)**, **Reddit (`r/LocalLLaMA`)**, **X (Twitter)**, and **LinkedIn**.

---

## 🎬 1. The 60-Second "No-Cut" Demo Recording Script

Record a single 60-second screen capture (`1920x1080`, split screen: Terminal on left, `http://127.0.0.1:8765` Cyberpunk Cockpit on right):

1. **`0:00 – 0:10` (The Hook):**
   - Run `python scripts/quickstart_doctor.py` -> show green preflight check (`Local GPU ONLINE + Hybrid Cloud Ready`).
   - Say/caption: *"Cloud coding IDEs charge $20–$40/month and upload your private code. Here is LUMI-OS: a 51,000-line Sovereign Local-First AI Software Engineer running free on my local RTX GPU."*
2. **`0:10 – 0:35` (The 5 Self-Verifying Coding Pillars Live):**
   - Run `python scripts/run_60s_showcase.py` in the terminal.
   - Highlight on screen as each stage prints:
     - **`<2ms` Reflex & Top-14 Tool Pruner** (cuts 83% schema bloat)
     - **Context-Isolated Subagent** (`0` messages added to main chat — no context rot)
     - **AST Compiler Guard** (blocks a broken Python edit & rolls back automatically)
     - **Fuzzy Edit + Auto-Pytest (`PASSED ✅`)**
     - **RLVR Verifiable-Reward Gym (`+1.0` reward logged for GRPO fine-tuning)**
3. **`0:35 – 0:60` (The Omni-Cockpit & Hybrid Escalation):**
   - Switch to `http://127.0.0.1:8765` Web Cockpit.
   - Type `/model hybrid` -> show that routine tasks stay 100% free on local GPU (`hermes3:latest`), while complex multi-file refactors or tool errors auto-escalate to 550B Cloud.

---

## 🟧 2. Hacker News (`Show HN`) Post

**Title:**
`Show HN: LUMI-OS – Local-first AI software engineer with AST rollback, auto-pytest, and RLVR gym`

**Body:**
```text
Hi HN,

I built LUMI-OS, a local-first AI software engineering agent and workstation cockpit designed to solve the three biggest problems I kept hitting with local 8B models (Hermes-3 / Qwen-3) on consumer RTX GPUs:

1. Broken edits & syntax corruption on 8B models:
Small local models frequently miss indentation by 2 spaces or drop a closing parenthesis during file edits. LUMI-OS uses a line-stripped/CRLF-tolerant fuzzy block matcher in `tools/files.py` and runs `ast.parse()` before touching disk—automatically rolling back any edit that introduces a SyntaxError.

2. Context rot during multi-file exploration:
Reading 5+ files into the main chat history degrades local model reasoning rapidly. LUMI-OS spawns context-isolated subagents (`core/subagents.py` -> `research`, `verifier`, `scout`) in a separate temporary message buffer and returns only a <1,200-char distilled summary to the main orchestrator.

3. Self-verification & RLVR (Reinforcement Learning with Verifiable Rewards):
After every `.py` write or edit, the orchestrator automatically runs the matching `test_*.py` suite via `pytest` and logs deterministic (+1.0 PASS / -1.0 FAIL) trajectories into `data/rlvr_trajectories.jsonl` for Unsloth GRPO / QLoRA fine-tuning.

It runs 100% free on local Ollama by default (`prefer_local`), and includes a `/model hybrid` mode that stays local for routine turns and only escalates to a 550B cloud model when a tool error or multi-file architectural refactor occurs.

You can test all 5 pillars locally in ~2 seconds with:
`python scripts/run_60s_showcase.py`

Feedback on the AST verifier gate and RLVR trajectory schema is very welcome!
```

---

## 👽 3. Reddit (`r/LocalLLaMA`) Post

**Title:**
`I built a 51k-LOC Sovereign Local-First Coding Agent that fixes 8B model edit failures (Fuzzy Edit + AST Rollback + Auto-Pytest + RLVR GRPO Gym)`

**Body:**
```markdown
Everyone loves running `hermes3:8b` or `qwen3:8b` locally on an RTX GPU until the model tries to edit a 300-line Python file, messes up 2 spaces of indentation, or leaves an unclosed bracket.

Over the past several months I engineered **LUMI-OS** to make local 8B models behave like frontier coding agents without paying $20/mo subscriptions:

- **Top-14 Semantic Tool Pruner (`core/reflex_router.py`):** Instead of stuffing 100+ JSON tool schemas into an 8k context window, LUMI scores tools in `<1ms` and feeds only the Top 14 schemas per turn (~83% prompt token reduction).
- **Fuzzy Block Surgery + Pre-Save `ast.parse` Rollback (`tools/files.py`):** Tolerates CRLF and leading-whitespace drift from 8B models, and rejects/rolls back any edit that fails Python AST compilation before saving.
- **Zero-Context-Rot Subagents (`core/subagents.py`):** Multi-step `read_file`/`grep_search` loops run in an isolated buffer and return a `<1,200 char` summary so your main session never bloats.
- **Auto-Pytest + RLVR Trajectory Collector (`evolution/dpo_flywheel.py`):** Every code edit automatically runs matching `pytest` tests and logs `+1.0` / `-1.0` verifiable rewards to `data/rlvr_trajectories.jsonl` (with `/rlvr export` for Unsloth GRPO training).
- **On-Demand `/model hybrid` Mode:** 100% free local GPU by default; automatically escalates to 550B Cloud only if a tool fails or you ask for a multi-file architectural refactor.

Run `python scripts/run_60s_showcase.py` to see all 5 stages execute live in under 3 seconds.
```

---

## 🐦 4. X (Twitter) / LinkedIn Launch Post

```text
95% of "AI Agents" on GitHub are 300-line wrappers around a paid cloud API.

I wanted a Sovereign AI Software Engineer that runs 100% FREE on my local RTX GPU—without breaking code or rotting its context window.

Meet LUMI-OS (51,000+ LOC):
⚡ <2ms Tier-0 Reflex + Top-14 Semantic Tool Pruner (cuts 83% prompt bloat)
🛡️ Pre-save AST Syntax Guard + Fuzzy Block Edit (0 broken Python files)
🧪 Auto-Pytest Verifier after every code edit
🕵️ Context-Isolated Subagents (0 main-chat context rot)
🎯 RLVR Gym: logs +1.0/-1.0 pytest rewards for GRPO fine-tuning
🧠 Hybrid Brain: 100% local by default, auto-escalates to 550B Cloud only when needed

1-click launch: .\start_lumi.bat
60s live benchmark: python scripts/run_60s_showcase.py
```
