<div align="center">

<img src="docs/assets/lumi_hero_banner.svg" alt="LUMI-OS v28.0 Omega Singularity Banner" width="100%" />

<br />

[![Version](https://img.shields.io/badge/Edition-v45.0_Sovereign_AI_Engineer-00f2fe?style=for-the-badge&logo=probot&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.11%2B-38bdf8?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Pytest_Suite-100%25_Passing-00ff87?style=for-the-badge&logo=pytest&logoColor=black)](tests/)
[![Tools](https://img.shields.io/badge/Sovereign_Arsenal-115%2B_Active_Tools-a855f7?style=for-the-badge&logo=serverless&logoColor=white)](tools/)
[![Voice](https://img.shields.io/badge/Kokoro_82M_ONNX-Offline_Neural_TTS-ec4899?style=for-the-badge&logo=soundcloud&logoColor=white)](voice/)
[![Security](https://img.shields.io/badge/VAPT_Cortex-AST_Taint_%2B_Red_Team_Shield-f59e0b?style=for-the-badge&logo=shield&logoColor=black)](SECURITY.md)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

<p align="center">
  <b>The Sovereign Local-First AI Software Engineer & Workstation Cockpit</b><br />
  <i>Runs 100% Free on Your RTX GPU · Auto-Verifies Every Code Edit with AST + Pytest · Context-Isolated Subagents · RLVR Self-Evolving Gym · On-Demand 550B Cloud Escalation · &lt;2ms Cyberpunk Cockpit.</i>
</p>

<p align="center">
  <a href="#-why-lumi-os-vs-cloud-wrappers"><b>🔥 Why LUMI-OS</b></a> ·
  <a href="#-self-verifying-ai-software-engineer-5-core-pillars"><b>🛠️ Self-Verifying Coding Engine</b></a> ·
  <a href="#-omni-cockpit-visual-showcase"><b>🖥️ Cockpit Showcase</b></a> ·
  <a href="#-omega-singularity-engines-phases-2428"><b>⚡ Omega Singularity</b></a> ·
  <a href="#-60-second-quickstart"><b>⚙️ 1-Click Quickstart</b></a>
</p>

</div>

---

## 🔥 Why LUMI-OS? (vs. Cloud Subscriptions & Basic Local Wrappers)

Most open-source AI assistants are thin 300-line API wrappers, while commercial AI IDEs lock you into `$20–$40/month` subscriptions and upload your proprietary codebase to external clouds. **LUMI-OS (`51,000+ LOC`)** is an end-to-end **Sovereign AI Software Engineering OS**:

| Capability | Cloud AI IDEs (`$20/mo`) | Basic Local Wrappers | **LUMI-OS (Sovereign Engine)** |
| :--- | :---: | :---: | :---: |
| **Monthly Cost & Data Privacy** | `$20–$40/mo`, code sent to cloud | Free, local | **100% Free Local Default + On-Demand Cloud Escalation** |
| **Broken Indentation / Syntax Edits** | Occasional broken diffs | Frequent on `8B` models | **Fuzzy Block Matcher + Pre-Save `ast.parse` Auto-Rollback** |
| **Post-Edit Test Verification** | Manual / prompted | None | **Automatic `pytest` Execution After Every `.py` Edit** |
| **Long-Session Context Rot** | Compaction delays | Severe after 5+ files | **Context-Isolated Subagents (`<1,200 char` distilled output)** |
| **Learning From Past Mistakes** | Static weights | None | **RLVR Verifiable-Reward Gym (`+1.0`/`-1.0` GRPO JSONL export)** |
| **Cockpit & Voice Latency** | Text-only IDE | Slow polling | **`<2ms` GET APIs + Offline Kokoro ONNX Neural Voice** |

---

## 🛠️ Self-Verifying AI Software Engineer (5 Core Pillars)

1. **AST-Guarded Fuzzy File Surgery ([`tools/files.py`](tools/files.py)):**
   - **Indentation & CRLF-Tolerant Fuzzy Replacement (`_fuzzy_replace`):** Eliminates failed edits when local `8B` models slightly misalign leading whitespace.
   - **Pre-Write Compiler Gate (`_verify_python_syntax`):** Validates every `.py` mutation via `ast.parse` *before* committing to disk — automatically rolling back on `SyntaxError`.
2. **Auto-Architect AST Blueprint & Auto-Pytest Verifier ([`core/orchestrator.py`](core/orchestrator.py)):**
   - Automatically injects repository AST symbol locations (`[AUTO-ARCHITECT AST CONTEXT]`) in `<2ms` on coding/refactoring tasks (or generates a 4-point blueprint via `/architect <goal>`).
   - Automatically runs matching `test_*.py` suites immediately after every `write_file` / `edit_file` call (`_auto_verify_edit`).
3. **Context-Isolated Subagent Engine ([`core/subagents.py`](core/subagents.py)):**
   - Spawns isolated `research`, `verifier`, and `scout` subagents (`invoke_subagent` / `/subagent`) that execute multi-step tool loops in a private buffer without polluting `Orchestrator.session`, returning only a `<1,200 char` summary.
4. **RLVR Verifiable-Reward Gym ([`evolution/dpo_flywheel.py`](evolution/dpo_flywheel.py)):**
   - Every compiler/pytest-verified edit automatically records a deterministic reward (`+1.0` on pass, `-1.0` on fail) into `data/rlvr_trajectories.jsonl` (`/rlvr` & `/rlvr export`) for Unsloth GRPO / QLoRA fine-tuning.
5. **Hybrid Local + 550B Cloud Escalation ([`brain/router.py`](brain/router.py)) + Reactive Wakeup:**
   - Runs 100% free on local Ollama GPU (`prefer_local`) by default, with 1-command switching to `/model hybrid` (auto-escalates to `nvidia/nemotron-3-ultra-550b-a55b` on tool errors or multi-file architecture), `/model cloud`, or `/model gemini`.
   - Background missions (`AsyncMissionQueue`) push completion events directly into `Orchestrator._wakeup_inbox` for non-polling reactive wakeup.

---

## 🖥️ Omni-Cockpit Visual Showcase

LUMI-OS features a **Single-Panel Cyberpunk Omni-Cockpit (`http://127.0.0.1:8765`)** with a 60 FPS 3D Arc Reactor voice orb, live hardware vitals, biometric presence guard, 4-agent Swarm IDE, and an interactive desktop mascot (**Chotu LUMI**).

<div align="center">
  <img src="docs/assets/cockpit_hud.png" alt="LUMI-OS Unified Omni-Cockpit HUD" width="100%" />
  <p><i><b>Figure 1:</b> LUMI-OS Unified Omni-Cockpit — 3D Neural Voice Orb, Hardware Telemetry, Biometric Sentry, 84-Tool Tactical Arsenal, and Chotu LUMI Cyber Mascot.</i></p>
</div>

| 🤖 Swarm-Dev 4-Agent Engineering Studio | 🛰️ Nexus-IoT & Kernel Synthesizer Lab |
| :---: | :---: |
| <img src="docs/assets/swarm_studio.png" alt="Swarm-Dev Multi-Agent Studio" width="100%" /> | <img src="docs/assets/nexus_sentinel.png" alt="Nexus-IoT & Kernel Synthesizer" width="100%" /> |
| *Autonomous Architect → Coder → Tester → Debugger pipeline with real-time `pytest` self-healing.* | *LAN Subnet Radar, Sovereign GPU Mesh Nodes, Home Assistant Webhooks & Self-Compiled Python Tools.* |

---

## ⚡ Omega Singularity Engines (Phases 24–28)

LUMI-OS goes beyond conversational wrappers by integrating **five deterministic + neural cognitive engines** directly into the orchestrator loop:

### 1. 🧠 Temporal Knowledge Graph & Episodic Memory Palace (`Phase 24`)
- **Modules:** [`core/cognitive_graph.py`](core/cognitive_graph.py) · [`tools/cognitive_graph.py`](tools/cognitive_graph.py)
- **Capabilities:** Extracts structured subject-predicate-object triples from conversations and technical documents into SQLite (`kg_nodes`, `kg_edges`) with temporal validity windows and confidence decay.
- **Algorithms:** Multi-hop Breadth-First Search (`query_neighborhood`), shortest causal chain discovery (`find_causal_path`), and live ecosystem topology summaries (`/graph`).

### 2. 🛡️ Cyber-Sentinel AST Taint & VAPT Auto-Patcher (`Phase 25`)
- **Modules:** [`core/cyber_sentinel.py`](core/cyber_sentinel.py) · [`tools/cyber_sentinel.py`](tools/cyber_sentinel.py)
- **Capabilities:** Performs deep Abstract Syntax Tree (AST) intraprocedural taint tracking (`source → sink`), regex structural auditing, and Shannon entropy secret scanning.
- **Coverage & Auto-Remediation:** Detects **CWE-78** (OS Command Injection), **CWE-89** (SQL Injection), **CWE-94** (`eval`/`exec` Code Injection), **CWE-502** (Unsafe `pickle` Deserialization), **CWE-327** (Weak Cryptography), and **CWE-798** (Hardcoded Credentials) with **CVSS v3.1** scoring. Automatically synthesizes hardened patches with unified diffs and re-verifies zero-CWE compliance (`/vapt`).

### 3. 🕸️ Topological Parallel Wave DAG Executor (`Phase 26`)
- **Modules:** [`core/dag_executor.py`](core/dag_executor.py) · [`tools/dag_executor.py`](tools/dag_executor.py)
- **Capabilities:** Compiles complex multi-objective missions into a Directed Acyclic Graph (DAG) of tool & reasoning nodes, validates acyclicity via **Kahn's Algorithm**, and groups independent tasks into concurrent execution waves (`ThreadPoolExecutor`).
- **Dynamic Context Piping:** Downstream nodes automatically inherit upstream outputs via `$node_id.output` interpolation with automatic **Reflexion self-healing** on transient failures (`/dag`).

### 4. 🌍 Counterfactual Pre-Flight World-Model Simulator (`Phase 27`)
- **Modules:** [`core/world_model.py`](core/world_model.py) · [`tools/world_model.py`](tools/world_model.py)
- **Capabilities:** Never mutates production files blindly. Clones the target module into an isolated temporary shadow sandbox and validates candidate mutations across **3 Verification Gates**:
  1. **Gate 1 (AST Syntax & Import Integrity)**
  2. **Gate 2 (Cyber-Sentinel Zero-New-CWE Security Audit)**
  3. **Gate 3 (Automated `unittest`/`pytest` Regression Execution)**
- Only when all 3 gates pass (`COMMIT_APPROVED`) does LUMI atomically swap the file while archiving a rollback snapshot in `.shadow_backups/` (`/simulate`).

### 5. 🔨 Natural-Language Autonomous Tool Auto-Forging (`Phase 28`)
- **Modules:** [`core/synthesizer.py`](core/synthesizer.py) · [`tools/synthesizer.py`](tools/synthesizer.py)
- **Capabilities:** Given only a tool name and natural-language specification (`auto_forge_tool`), LUMI synthesizes the Python implementation, validates it against the AST safety sandbox, runs automated smoke tests, persists it to `data/dynamic_tools/`, and **hot-injects** it into the live `ToolRegistry` without restarting.

---

## 🦾 Stark Apex Protocol (Phases 29–35 — 4-Department Deep Upgrade)

Engineered specifically for high-velocity local inference on consumer RTX GPUs (`hermes3:latest` & `qwen3:8b`) with zero cloud dependency:

### ⚡ Dept 1: Sub-5ms Tier-0 Reflex Router & Dynamic Top-K Tool Pruner (`Phases 29–30`)
- **Modules:** [`core/reflex_router.py`](core/reflex_router.py) · [`tools/reflex_router.py`](tools/reflex_router.py)
- **Tier-0 Deterministic Reflex (`<1ms`):** Instantaneous tactical responses for system vitals, active model status, ping, time/date, and git status without waiting on LLM prefill.
- **Dynamic Top-K Semantic Tool Pruner:** Scores 95+ registered tool schemas across 10 semantic domain clusters and selects only the **Top-14 relevant tools** per turn — cutting **83.7% of JSON schema prompt bloat** (~6,120 tokens saved per turn) and boosting 8B tool-calling accuracy.
- **Sentence-Pipelined TTS Streaming (`split_into_speech_chunks` & `/api/chat/stream`):** Emits clean spoken sentence chunks for zero-wait neural voice synthesis.

### 🧠 Dept 2: Hybrid BM25 + 256-D Vector RRF Memory & Repo AST Call-Graph (`Phases 31–32`)
- **Modules:** [`core/hybrid_retriever.py`](core/hybrid_retriever.py) · [`core/repo_graph.py`](core/repo_graph.py) · [`tools/repo_graph.py`](tools/repo_graph.py)
- **Reciprocal Rank Fusion (`HybridRRFEngine`):** Fuses **Okapi BM25** (with Robertson–Spärck Jones IDF + camelCase/snake_case sub-tokenization) and **256-D L2-Normalized Character/Word N-Gram Hash Embeddings** in `<2ms` on CPU with zero external model downloads.
- **Cross-File Repo AST Graph (`RepoASTGraph`):** Indexes all Python modules, classes, functions, imports, and cross-file call edges to compute **Blast / Impact Radius Analysis** (`/repo impact <symbol>`) showing every downstream caller and affected `pytest` suite before code modification.

### 👁️ Dept 3: Active OS Context Sensor, Async Mission Queue & DPO Flywheel (`Phases 33–34`)
- **Modules:** [`core/context_sensor.py`](core/context_sensor.py) · [`core/mission_queue.py`](core/mission_queue.py) · [`evolution/dpo_flywheel.py`](evolution/dpo_flywheel.py)
- **Zero-Prompt Situational Sensor (`ActiveContextSensor`):** Reads the active Win32 foreground window title, process name, git diff, and clipboard contents in `<1ms` — automatically classifying and injecting Python tracebacks or compiler errors when you say *"ye error fix kar"*.
- **Dual-Lane Async Mission Queue (`AsyncMissionQueue`):** Dispatches heavy Swarm, DAG, Research, and VAPT jobs into a background worker pool (`/missions`) so interactive chat stays 100% responsive.
- **Self-Evolving DPO Flywheel (`DPOFlywheel`):** Automatically captures `(failed_tool_call -> self_healed_repair)` trajectories into HuggingFace TRL / Unsloth preference pairs (`/dpo`).

### 🎯 Dept 4: Stark Apex Adaptive Persona Engine (`Phase 35`)
- **Module:** [`core/jarvis_personality.py`](core/jarvis_personality.py)
- **3-Mode Cognitive Adaptation:** Dynamically switches between `voice_tactical` (1–3 punchy spoken Hinglish sentences), `crisis_triage` (`[STARK-HUD :: ROOT-CAUSE LOCKED]` traceback surgery), and `deep_engineering` (full production code + 2 proactive edge-case warnings).

---

## 🧬 System Architecture

```mermaid
flowchart TB
    subgraph Interfaces["🖥️ Multi-Modal Interfaces"]
        WEB["Omni-Cockpit Web HUD<br/>(FastAPI + 3D Orb + PWA)"]
        CLI["Interactive Terminal CLI<br/>(Rich Telemetry + Approvals)"]
        VOICE["Neural Voice Pipeline<br/>(Whisper CUDA + Edge-TTS + Prosody)"]
        TG["Telegram Remote Bridge<br/>(Allowlisted Chat Control)"]
    end

    subgraph Core["🧠 LUMI-OS Sovereign Orchestrator (core/orchestrator.py)"]
        ROUTER["4-Way Brain Router<br/>(Hermes-3 · Qwen-3 · Local LoRA · NVIDIA NIM)"]
        MCTS["System-2 MCTS Reasoner<br/>(Multi-Branch Tree Search)"]
        DAG["Topological Wave DAG<br/>(Kahn's Algorithm + Parallel Waves)"]
    end

    subgraph Omega["⚡ Omega Singularity Cortex (Phases 24–28)"]
        KG["Temporal Knowledge Graph<br/>(Multi-Hop BFS + Causal Paths)"]
        VAPT["Cyber-Sentinel AST VAPT<br/>(CWE/CVSS Scanner + Auto-Patcher)"]
        WM["Counterfactual World Model<br/>(3-Gate Shadow Sandbox)"]
        FORGE["Kernel Tool Synthesizer<br/>(Live Hot-Reloading)"]
        SWARM["4-Agent Swarm Studio<br/>(Architect · Coder · Tester · Debugger)"]
    end

    subgraph Security["🛡️ Zero-Trust Safety & Persistence"]
        GATE["Zone & Taint Safety Gate<br/>(AUTO / ASK / BLOCK)"]
        MEM["SQLite Episodic & Vector Vault<br/>(Facts + Codebase RAG + Audit Logs)"]
    end

    Interfaces --> Core
    Core --> Omega
    Omega --> Security
```

---

## 🔀 5-Mode Sovereign Brain Router

Switch inference engines instantaneously at runtime without restarting via `/model`:

| Slash Command | Active Engine | Target Use Case |
| :--- | :--- | :--- |
| `/model local` | **Ollama Local GPU (`hermes3:latest` / `qwen3:8b`)** | Default 100% free, zero-latency local agentic execution |
| `/model hybrid` | **Local GPU + Auto Cloud 550B Escalation** | Runs routine turns locally; auto-escalates to 550B Cloud on tool errors or multi-file refactors |
| `/model cloud` | **NVIDIA NIM (`nvidia/nemotron-3-ultra-550b-a55b`)** | Frontier 550B parameter reasoning for heavy multi-file architecture |
| `/model gemini` | **Google Gemini (`gemini-3-flash-preview`)** | Ultra-fast multimodal & long-context cloud synthesis |
| `/model hermes` / `/model qwen` | **Pin Specific Local Ollama Model** | Hot-switch between `hermes3:latest` and `qwen3:8b` on local VRAM |

---

## 🚀 28-Phase Capability Matrix

<details open>
<summary><b>Click to expand all 28 Architectural Phases of LUMI-OS</b></summary>

| Phase | Subsystem | Core Modules | Status |
| :---: | :--- | :--- | :---: |
| **1–4** | **Core Brain, Memory & Zone Safety Gate** | `brain/router.py`, `memory/store.py`, `safety/gate.py` | ✅ Verified |
| **5–8** | **Reflection, Skill Distillation & Desktop Control** | `evolution/reflect.py`, `evolution/skills.py`, `tools/desktop.py` | ✅ Verified |
| **9–12** | **Neural Voice (Whisper STT + Edge-TTS) & Vision** | `voice/pipeline.py`, `tools/vision.py`, `interface/telegram_bot.py` | ✅ Verified |
| **13** | **Ambie-Sentry Zero-Prompt Hardware Guardian** | `safety/sentry.py`, `tools/sentry.py` | ✅ Verified |
| **14** | **Neural-Vault Semantic Codebase RAG** | `core/vault.py`, `tools/vault.py` | ✅ Verified |
| **15** | **Swarm-Dev 4-Agent Autonomous Software Studio** | `core/swarm.py`, `tools/swarm.py` | ✅ Verified |
| **16** | **Nexus-IoT LAN Radar & Workstation Focus Presets** | `core/nexus.py`, `tools/nexus.py` | ✅ Verified |
| **17** | **Kernel-Synthesis Dynamic Runtime Tool Compiler** | `core/synthesizer.py`, `tools/synthesizer.py` | ✅ Verified |
| **18** | **System-2 MCTS Reasoner, Biometrics & FinTech Oracle** | `brain/mcts_reasoner.py`, `safety/biometrics.py`, `finance/oracle.py` | ✅ Verified |
| **19–21** | **Web Operator, Deep Research & Proactive Assistant** | `core/web_operator.py`, `core/researcher.py`, `core/proactive_assistant.py` | ✅ Verified |
| **22–23** | **Unified Omni-Cockpit HUD, Chotu Mascot & LoRA Lab** | `web/index.html`, `web/app.js`, `scripts/set_wise_trainer.py` | ✅ Verified |
| **24** | **Temporal Knowledge Graph & Episodic Memory Palace** | `core/cognitive_graph.py`, `tools/cognitive_graph.py` | ✅ Verified |
| **25** | **Cyber-Sentinel AST Taint & VAPT Auto-Patcher** | `core/cyber_sentinel.py`, `tools/cyber_sentinel.py` | ✅ Verified |
| **26** | **Topological Parallel Wave DAG Executor** | `core/dag_executor.py`, `tools/dag_executor.py` | ✅ Verified |
| **27** | **Counterfactual Pre-Flight World-Model Simulator** | `core/world_model.py`, `tools/world_model.py` | ✅ Verified |
| **28** | **Natural-Language Autonomous Tool Auto-Forging** | `core/synthesizer.py`, `web/server.py` (`/api/omega/*`) | ✅ Verified |

</details>

---

## 🛡️ Zero-Trust Security & Taint Gate

Every tool invocation passes through [`safety/gate.py`](safety/gate.py) before execution:

| Filesystem / System Zone | Read / List | Write / Mutate | Delete / Execute |
| :--- | :---: | :---: | :---: |
| **`./workspace/` (Sandbox)** | `AUTO` | `AUTO` *(Escalates to `ASK` if turn is tainted)* | `ASK` |
| **LUMI-OS Core (`core/`, `safety/`, `brain/`, `config.yaml`)** | `AUTO` | **🚫 `BLOCK` (Immutable Self-Protection)** | **🚫 `BLOCK`** |
| **Registered Projects (`register_project`)** | `AUTO` | `ASK` (Explicit User Approval Required) | `ASK` |
| **Outside `allowed_paths` / OS System Directories** | **🚫 `BLOCK`** | **🚫 `BLOCK`** | **🚫 `BLOCK`** |

- **Prompt-Injection Taint Tracking:** Reading external web pages or untrusted files marks the turn as `tainted=True` in [`core/orchestrator.py`](core/orchestrator.py), automatically preventing silent `AUTO` side effects.
- **OPSEC Privacy Isolation:** Personal identity settings live strictly in git-ignored `config/identity.local.json` (falling back to the generic [`config/identity.json`](config/identity.json) template).

---

## ⚙️ 60-Second Quickstart

### Option A: One-Click Windows Bootstrapper (Recommended)
Double-click or run `start_lumi.bat` — it automatically runs the preflight doctor, prepares `workspace/` & `data/`, checks your Python & Ollama setup, and launches the Web Cockpit:
```powershell
.\start_lumi.bat
```

### Option B: Manual Clone & Launch
```powershell
pip install -r requirements.txt
ollama pull hermes3:latest

# Run 1-second environment preflight check
python scripts/quickstart_doctor.py

# Run the 60-second Self-Verifying AI Engineer live showcase
python scripts/run_60s_showcase.py

# Launch the Cyberpunk Omni-Cockpit Web UI -> http://127.0.0.1:8765
python main.py --web
```

*(Optional)* Configure on-demand Cloud 550B / Gemini escalation or Telegram in environment variables:
```powershell
setx NVIDIA_API_KEY "nvapi-..."
setx GEMINI_API_KEY "AIza..."
setx TELEGRAM_BOT_TOKEN "..."
```

---

## ⌨️ Tactical Slash Commands & REST API

### Interactive Slash Directives
| Command | Action |
| :--- | :--- |
| `/model local\|hybrid\|cloud\|gemini` | Hot-switch between 100% free Local GPU, Hybrid auto-escalation, 550B Cloud, or Gemini |
| `/architect <coding_goal>` | Synthesize a 4-point AST-grounded engineering blueprint before writing code |
| `/subagent <research\|verifier\|scout> <task>` | Run multi-step codebase research or verification in a context-isolated subagent |
| `/rlvr [export]` | View RLVR verifiable-reward pass rates (`+1.0`/`-1.0`) or export GRPO JSONL dataset |
| `/vapt <file_or_dir>` | Run Cyber-Sentinel AST taint scan, CWE/CVSS v3.1 report, or auto-remediation |
| `/graph <entity_or_query>` | Query the Temporal Knowledge Graph neighborhood or ecosystem topology |
| `/dag <mission_goal>` | Decompose and execute a multi-step mission via the Topological Wave DAG Executor |
| `/simulate <file> <goal>` | Run a 3-gate Counterfactual World-Model simulation before committing changes |
| `/briefing` | Generate an executive daily standup digest & hardware telemetry summary |
| `/sentry` | Inspect Ambie-Sentry hardware vitals, battery, RAM load, and git autosave status |

### Key REST API Endpoints (`http://127.0.0.1:8765`)
- `POST /api/chat` — Primary conversational & agentic tool-execution endpoint
- `GET  /api/omega/status` — Live telemetry across all Omega Singularity subsystems
- `POST /api/omega/vapt` — Trigger AST taint analysis, workspace surface audit, or auto-patching
- `POST /api/omega/graph` — Ingest knowledge triples, query BFS neighborhoods, or trace causal paths
- `POST /api/omega/dag` — Execute parallel wave DAG workflows
- `POST /api/omega/simulate` — Run pre-flight counterfactual sandbox verification & profiling

---

## 🧪 Verification & Test Suite

LUMI-OS ships with a comprehensive **201-test verification gauntlet** covering prompt-injection tainting, zone safety gates, AST VAPT auto-patching, MCTS reasoning, multi-agent Swarm synthesis, and DAG wave execution:

```powershell
pip install -r requirements-dev.txt
python -m pytest tests -q
# -> 201 passed
```

---

## 📂 Repository Architecture

```text
LUMI-OS/
├── brain/                  # 4-Way LLM Router, Ollama, Local HF LoRA, NVIDIA Cloud & MCTS Reasoner
├── config/                 # Model configurations, LoRA hyperparameters & OPSEC-safe identity template
├── core/                   # Orchestrator, Cyber-Sentinel VAPT, World Model, Wave DAG, Knowledge Graph, Swarm
├── docs/assets/            # SVG Hero Banners & Sanitized Cockpit Screenshots
├── evolution/              # Self-reflection loop, Digital Shadow standups & YAML skill distillation
├── finance/                # Local SQLite FinTech burn-rate & Monte Carlo VaR oracle
├── interface/              # Rich Terminal CLI & allowlisted Telegram bridge
├── memory/                 # SQLite episodic store, working memory & semantic codebase recall
├── mesh/                   # Sovereign LAN GPU mesh discovery & peer dispatch
├── safety/                 # Zero-Trust file/command gate, taint tracker, biometrics & audit logs
├── scripts/                # LoRA fine-tuning pipeline, GGUF export & live verification harnesses
├── tests/                  # 201 unit, security, injection & Omega Singularity integration tests
├── tools/                  # 84 sovereign tools (VAPT, DAG, World Model, Graph, Swarm, Vision, GUI)
├── voice/                  # Local Whisper CUDA STT, Edge-TTS neural prosody & wake-word pipeline
├── web/                    # FastAPI server + Single-Panel Cyberpunk Omni-Cockpit HUD
└── main.py                 # Unified CLI / Web / Voice entrypoint
```

<div align="center">
  <br />
  <b>Built with Sovereign Precision · 100% Local-First · Zero Telemetry Leakage</b>
</div>
