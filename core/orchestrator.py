"""Orchestrator loop v2 — state machine + safety gate + retry (healing seed):
UNDERSTAND -> tool? -> SAFETY -> ACT (retry x1) -> OBSERVE -> RESPOND."""

from __future__ import annotations

import queue
import threading
import time

from brain.base import Brain
from core.states import State
from memory.repo import MemoryRepo
from safety.audit import AuditLog
from safety.gate import SafetyGate
from tools.registry import ToolRegistry
from core.context_compactor import compact_session_history
from core.resilient_parser import coerce_tool_arguments, repair_and_parse_json
from core.tool_watchdog import execute_tool_with_watchdog

MAX_TOOL_CHARS = 6000          # model ko ek tool result se zyada context nahi milega
UNTRUSTED_TOOLS = {"read_file", "search_files", "web_search", "web_read", "browse_page"}


class Orchestrator:
    def __init__(self, brain: Brain, config: dict | None = None,
                 memory: MemoryRepo | None = None,
                 registry: ToolRegistry | None = None,
                 gate: SafetyGate | None = None,
                 audit: AuditLog | None = None,
                  projects=None,                  # ProjectRegistry (req #6)
                  journal=None,                   # evolution Journal (req #5)
                  alerts=None):                   # watchdog Notifier (req #11)
        self.brain = brain
        self.config = config or {}
        self.memory = memory
        self.registry = registry
        self.gate = gate
        self.audit = audit
        self.projects = projects
        self.journal = journal
        self.alerts = alerts                      # None = watchdog off (hooks skip)
        self.wd_cfg = dict(self.config.get("watchdog") or {})
        self.evolution = dict(self.config.get("evolution") or {})
        self.max_iterations = int(self.config.get("max_iterations", 10))
        # seed last 20 messages from DB — context survives restarts
        self.session: list[dict] = memory.load_history_for_llm() if memory else []
        self._retries: dict[str, int] = {}       # failed call key -> attempts used
        self._approved: set[str] = set()         # y-approved keys (per user turn)
        self._cid = 0                            # OpenAI-style tool_call id counter
        self._trace: list[dict] = []             # per-turn tool trace (web UI)
        # evolution state (req #5) — triggers, cooldown, session budget
        self._turn_count = 0
        self._retried_turn = False
        self._refl_session = 0
        self._refl_last_ts = 0.0
        self._session_tools: list[str] = []
        self._last_turn = ("", "")               # /reflect manual ke liye
        self._skill_calls: list[str] = []        # is turn me get_skill (Task O)
        self._turn_tools: dict[str, int] = {}    # loop detect: (tool+args) counts
        self._loop_stop = False                  # loop CRITICAL -> turn force-stop
        # ek time pe ek turn: web + telegram + CLI ek hi session share karte hain
        self._turn_lock = threading.Lock()
        self.state = State.UNDERSTAND
        # Stark Apex Protocol (v35.0) — Depts 1–4 subsystems
        self.reflex_router = None
        self.repo_graph = None
        self.context_sensor = None
        self.mission_queue = None
        self.dpo_flywheel = None
        self._failed_tool_records: dict[str, dict] = {}

    # -- stubs (real work happens inside the loop states below) -----------
    def plan(self) -> None:
        pass

    def reflect(self) -> None:
        pass

    # ---------------------------------------------------------------------
    def run_turn(self, user_input: str) -> dict:
        """One chat turn — THE shared loop for CLI and Web (no duplicate logic).
        Returns {reply, tool_trace, provider, model, elapsed_ms}."""
        with self._turn_lock:
            self._trace = []
            started = time.time()
            reply = self.step(user_input)
            self._turn_end_watch()             # Task Q: instant disk CRITICAL
            return {"reply": reply, "tool_trace": self._trace,
                    "provider": getattr(self.brain, "last_provider", "ollama"),
                    "model": getattr(self.brain, "last_model",
                                     getattr(self.brain, "model", "-")),
                    "elapsed_ms": int((time.time() - started) * 1000)}

    def command(self, cmd: str) -> tuple[bool, str]:
        """Slash commands shared by CLI + web chips.
        Returns (should_exit, display_text) — caller prints 'LUMI: {text}'."""
        name = cmd.split()[0].lower()
        if name in {"/exit", "/quit", "/q"}:
            return True, "Chalo, milte hain phir! Bye boss 👋"
        if name == "/history":
            return False, f"last 10 messages —\n{self.history_text(10)}"
        if name == "/audit":
            return False, f"last 5 tool decisions —\n{self.audit_text(5)}"
        if name == "/tools":
            return False, f"registered tools —\n{self.tools_text()}"
        if name == "/model":
            parts = cmd.split()
            if len(parts) == 1:
                return False, f"model status —\n{self.model_status_text()}"
            return False, self.set_model_policy(parts[1].lower())
        if name == "/projects":
            return False, f"registered projects —\n{self.projects_text()}"
        if name == "/use":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "use kaise — /use <naam> (list = /projects)"
            return False, self.use_project(parts[1])
        if name == "/new":
            self.session_end_reflect()           # session_end trigger (exempt)
            sid = self.new_session()
            return False, f"Naya session shuru ({sid}). Purani baatein DB me safe hain."
        if name == "/journal":
            return False, f"last reflections —\n{self.journal_text(10)}"
        if name == "/skills":
            return False, f"skill library —\n{self.skills_list()}"
        if name == "/skill":
            return False, self.skill_command(cmd)
        if name == "/reflect":
            return False, self.force_reflect()
        if name == "/evolution":
            return False, self.evolution_cmd(cmd)
        if name == "/eval":
            return False, self.eval_cmd(cmd)
        if name == "/alerts":
            return False, self.alerts_text()
        if name == "/values":
            from core import values as V
            n = V.counts(V.load_values())["total"]
            port = getattr(self, "web_port", 8765)
            return False, (f"values file — {V.values_path()}\n"
                           f"{n} rules loaded\n"
                           f"web me kholein: http://localhost:{port} "
                           "-> VALUES page")
        if name == "/decide":
            from core.decide import decide
            parts = cmd.split(maxsplit=1)
            sit = parts[1] if len(parts) > 1 else ""
            out = decide(sit, self.brain, self.memory)
            if sit and self.audit:               # tool_calls log (Z2 contract)
                try:
                    self.audit.log(self._sid(), "decide",
                                   {"situation": sit[:200]}, "auto",
                                   "ok " + out[:150])
                except Exception:                # noqa: BLE001 — log fail = no crash
                    pass
            return False, out
        if name == "/facts":
            parts = cmd.split(maxsplit=1)
            cat = parts[1] if len(parts) > 1 else ""
            facts = self.memory.list_facts(cat) if self.memory else []
            if not facts:
                return False, "Abhi koi facts saved nahi hain (use: /remember <key>: <value>)."
            lines = [f"- [{f.get('category','general')}] {f['key']}: {f['value']}" for f in facts]
            return False, f"saved facts ({len(facts)}) —\n" + "\n".join(lines)
        if name == "/remember":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2 or ":" not in parts[1]:
                return False, "usage: /remember <key>: <value>"
            k, v = parts[1].split(":", 1)
            if self.memory:
                self.memory.remember(k.strip(), v.strip())
                from brain.ollama_adapter import set_facts
                set_facts(self.memory.load_facts_for_prompt(10))
                return False, f"Yaad rakh liya: '{k.strip()}' = '{v.strip()}'"
            return False, "Memory attached nahi hai."
        if name == "/forget":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /forget <key>"
            k = parts[1].strip()
            if self.memory:
                ok = self.memory.forget(k)
                from brain.ollama_adapter import set_facts
                set_facts(self.memory.load_facts_for_prompt(10))
                return False, f"Fact '{k}' bhool gaya." if ok else f"'{k}' nahi mila."
            return False, "Memory attached nahi hai."
        if name == "/backup":
            return False, self.backup()
        if name == "/mcp":
            from tools.mcp_client import get_mcp_manager
            mgr = get_mcp_manager()
            parts = cmd.split()
            if len(parts) == 1:
                return False, mgr.status_text()
            sub = parts[1].lower()
            if sub == "enable" and len(parts) > 2:
                _, msg = mgr.start_server(parts[2])
                return False, msg
            if sub == "disable" and len(parts) > 2:
                _, msg = mgr.stop_server(parts[2])
                return False, msg
            return False, "usage: /mcp | /mcp enable <name> | /mcp disable <name>"
        if name == "/desktop":
            parts = cmd.split()
            if len(parts) > 1 and parts[1].lower() in {"off", "stop", "disable"}:
                from tools.mcp_client import get_mcp_manager
                _, msg = get_mcp_manager().stop_server("desktop")
                return False, f"Desktop control stopped: {msg}"
            return False, "usage: /desktop off (kill-switch)"
        if name == "/reminders":
            from core.scheduler import get_lumi_scheduler
            tool = self.registry.get("list_reminders") if self.registry else None
            if tool:
                return False, tool.handler()
            return False, "Reminders tool registered nahi hai."
        if name == "/briefing":
            from core.scheduler import get_lumi_scheduler
            sched = get_lumi_scheduler(memory=self.memory, notifier=self.alerts, config=self.config)
            return False, sched.generate_briefing()
        if name == "/plan":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /plan <goal>\nexample: /plan Create a python script in workspace/primes.py and run it"
            from core.planner import execute_goal
            return False, execute_goal(parts[1], self)
        if name == "/sentry":
            from safety.sentry import sentry_status_text
            return False, sentry_status_text(getattr(self, "sentry", None))
        if name == "/swarm":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /swarm <project_goal>\nexample: /swarm Build a CLI Pomodoro Timer with sqlite database"
            from core.swarm import SwarmCoordinator
            coordinator = SwarmCoordinator(workspace_root="workspace", brain=self.brain)
            res = coordinator.develop(goal=parts[1])
            return False, res.get("summary", "Swarm finished.")
        if name == "/vault":
            parts = cmd.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else "stats"
            from core.vault import NeuralVault
            v = getattr(self, "vault", None) or NeuralVault()
            if sub == "stats":
                s = v.get_stats()
                return False, f"NEURAL-VAULT: {s['documents']} files, {s['chunks']} chunks ({s['db_size_kb']} KB) indexed in data/vault.db"
            if sub == "index":
                target = parts[2] if len(parts) > 2 else "."
                tool = self.registry.get("vault_index") if self.registry else None
                return False, tool.handler(path=target) if tool else f"Indexed: {v.index_path(target)}"
            if sub == "search" and len(parts) > 2:
                tool = self.registry.get("vault_search") if self.registry else None
                return False, tool.handler(query=parts[2]) if tool else f"Results: {v.search(parts[2])}"
            return False, "usage: /vault stats | /vault index [path] | /vault search <query>"
        if name == "/browse":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /browse <url>\nexample: /browse https://news.ycombinator.com"
            tool = self.registry.get("browse_page") if self.registry else None
            from core.web_operator import WebOperator
            op = getattr(self, "web_operator", None) or WebOperator(brain=self.brain)
            return False, tool.handler(url=parts[1]) if tool else op.summarize_page(parts[1])
        if name == "/tech":
            tool = self.registry.get("tech_briefing") if self.registry else None
            from core.web_operator import WebOperator
            op = getattr(self, "web_operator", None) or WebOperator(brain=self.brain)
            return False, tool.handler() if tool else op.fetch_tech_briefing()
        if name == "/nexus":
            parts = cmd.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else "status"
            from core.nexus import NexusHub
            hub = getattr(self, "nexus", None) or NexusHub()
            if sub == "status":
                st = hub.get_status()
                return False, f"NEXUS-IOT: Preset='{st['current_preset']}' | Host={st['hostname']} ({st['local_ip']}) | Available: {', '.join(st['available_presets'])}"
            if sub == "focus":
                preset = parts[2] if len(parts) > 2 else "code_sprint"
                tool = self.registry.get("workstation_focus") if self.registry else None
                return False, tool.handler(preset=preset) if tool else str(hub.set_focus_preset(preset))
            if sub == "scan":
                tool = self.registry.get("scan_lan_devices") if self.registry else None
                return False, tool.handler() if tool else str(hub.scan_lan())
            if sub == "trigger" and len(parts) > 2:
                tool = self.registry.get("iot_webhook") if self.registry else None
                return False, tool.handler(url=parts[2]) if tool else str(hub.trigger_webhook(parts[2]))
            return False, "usage: /nexus status | /nexus focus [preset] | /nexus scan | /nexus trigger <url>"
        if name in {"/research", "/deepsearch"}:
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /research <topic>\nexample: /research Quantum computing error mitigation 2026"
            tool = self.registry.get("deep_web_research") if self.registry else None
            from core.researcher import DeepResearcher
            r = getattr(self, "researcher", None) or DeepResearcher(brain=self.brain)
            return False, tool.handler(topic=parts[1]) if tool else r.conduct_research(parts[1])["dossier_markdown"]
        if name in {"/shadow", "/digest", "/standup"}:
            tool = self.registry.get("generate_developer_digest") if self.registry else None
            from evolution.digital_shadow import DigitalShadow
            s = getattr(self, "digital_shadow", None) or DigitalShadow()
            return False, tool.handler() if tool else s.generate_standup_digest()["standup_markdown"]
        if name in {"/code", "/oracle"}:
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                return False, "usage: /code <file_path>\nexample: /code main.py"
            target_file = parts[1].replace("audit", "").strip()
            tool = self.registry.get("code_oracle_audit") if self.registry else None
            from tools.code_oracle import CodeOracle
            co = getattr(self, "code_oracle", None) or CodeOracle()
            return False, tool.handler(file_path=target_file) if tool else str(co.audit_file(target_file))
        if name in {"/optimize", "/clean", "/health"}:
            parts = cmd.split()
            dry = True
            if len(parts) > 1 and parts[1].lower() in {"clean", "purge", "force", "now"}:
                dry = False
            tool = self.registry.get("optimize_workstation_health") if self.registry else None
            from tools.workstation_cleaner import WorkstationGuardian
            g = getattr(self, "workstation_guardian", None) or WorkstationGuardian()
            return False, tool.handler(dry_run=dry) if tool else str(g.optimize_health(dry_run=dry))
        if name == "/graph":
            parts = cmd.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else "map"
            from core.cognitive_graph import CognitiveGraph
            cg = getattr(self, "cognitive_graph", None) or CognitiveGraph(db_path=str(self.memory.db_path), brain=self.brain)
            if sub == "map":
                tool = self.registry.get("graph_ecosystem_map") if self.registry else None
                return False, tool.handler() if tool else str(cg.get_ecosystem_summary())
            if sub == "query" and len(parts) > 2:
                tool = self.registry.get("graph_query_neighborhood") if self.registry else None
                return False, tool.handler(entity=parts[2]) if tool else str(cg.query_neighborhood(parts[2]))
            if sub == "path" and len(parts) > 2 and "->" in parts[2]:
                src, tgt = [x.strip() for x in parts[2].split("->", 1)]
                tool = self.registry.get("graph_causal_path") if self.registry else None
                return False, tool.handler(source=src, target=tgt) if tool else str(cg.find_causal_path(src, tgt))
            return False, "usage: /graph map | /graph query <entity> | /graph path <EntityA -> EntityB>"
        if name == "/vapt":
            parts = cmd.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else "surface"
            if sub == "surface":
                tool = self.registry.get("vapt_surface_audit") if self.registry else None
                if tool:
                    return False, tool.handler()
            if sub == "scan" and len(parts) > 2:
                tool = self.registry.get("vapt_deep_scan") if self.registry else None
                if tool:
                    return False, tool.handler(file_path=parts[2])
            if sub == "patch" and len(parts) > 2:
                tool = self.registry.get("vapt_auto_patch") if self.registry else None
                if tool:
                    return False, tool.handler(file_path=parts[2])
            return False, "usage: /vapt surface | /vapt scan <file.py> | /vapt patch <file.py>"
        if name == "/dag":
            parts = cmd.split(maxsplit=1)
            if len(parts) < 2:
                tool = self.registry.get("inspect_dag_history") if self.registry else None
                return False, tool.handler() if tool else "usage: /dag <mission>"
            tool = self.registry.get("execute_dag_mission") if self.registry else None
            if tool:
                return False, tool.handler(mission=parts[1])
            from core.dag_executor import AutonomousDAGExecutor
            ex = getattr(self, "dag_executor", None) or AutonomousDAGExecutor(registry=self.registry, brain=self.brain)
            return False, ex.execute_mission(parts[1])["summary"]
        if name == "/simulate":
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                return False, "usage: /simulate <file_path> <optimization_goal>"
            tool = self.registry.get("simulate_and_apply_patch") if self.registry else None
            if tool:
                return False, tool.handler(file_path=parts[1], optimization_goal=parts[2])
            return False, "World-Model simulator tool not registered."
        if name == "/forge":
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                return False, "usage: /forge <tool_name> <natural_language_spec>"
            tool = self.registry.get("auto_forge_tool") if self.registry else None
            if tool:
                return False, str(tool.handler(tool_name=parts[1], specification=parts[2]))
            return False, "Synthesizer auto_forge_tool not registered."
        if name == "/reflex":
            from core.reflex_router import get_reflex_router
            rx = getattr(self, "reflex_router", None) or get_reflex_router()
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                tool = self.registry.get("reflex_prune_preview") if self.registry else None
                if tool:
                    return False, tool.handler(query=parts[1])
            tool = self.registry.get("reflex_router_telemetry") if self.registry else None
            return False, tool.handler() if tool else str(rx.get_router_telemetry())
        if name == "/repo":
            parts = cmd.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else "map"
            from core.repo_graph import RepoASTGraph
            rg = getattr(self, "repo_graph", None) or RepoASTGraph(root_dir=".")
            if sub == "map":
                tool = self.registry.get("repo_structural_map") if self.registry else None
                return False, tool.handler() if tool else rg.generate_repo_map()
            if sub == "locate" and len(parts) > 2:
                tool = self.registry.get("repo_symbol_locate") if self.registry else None
                return False, tool.handler(symbol_name=parts[2]) if tool else str(rg.locate_symbol(parts[2]))
            if sub == "impact" and len(parts) > 2:
                tool = self.registry.get("repo_impact_radius") if self.registry else None
                return False, tool.handler(symbol_or_file=parts[2]) if tool else str(rg.analyze_impact_radius(parts[2]))
            return False, "usage: /repo map | /repo locate <symbol> | /repo impact <symbol_or_file>"
        if name in {"/context", "/sensor"}:
            tool = self.registry.get("sense_active_context") if self.registry else None
            if tool:
                return False, tool.handler()
            from core.context_sensor import get_context_sensor
            return False, get_context_sensor().format_context_injection("manual sensor check")
        if name in {"/missions", "/bg"}:
            parts = cmd.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else ""
            if sub == "run" and len(parts) > 2:
                tool = self.registry.get("dispatch_background_mission") if self.registry else None
                if tool:
                    return False, tool.handler(mission_goal=parts[2])
            tool = self.registry.get("check_mission_queue") if self.registry else None
            if tool:
                return False, tool.handler(mission_id=sub)
            from core.mission_queue import get_mission_queue
            return False, str(get_mission_queue().list_missions())
        if name == "/dpo":
            export_flag = "export" in cmd.lower()
            tool = self.registry.get("dpo_flywheel_status") if self.registry else None
            if tool:
                return False, tool.handler(export_trl=export_flag)
            from evolution.dpo_flywheel import get_dpo_flywheel
            return False, str(get_dpo_flywheel().get_flywheel_stats())
        if name in {"/harvest", "/evolve"}:
            tool = self.registry.get("harvest_market_skill") if self.registry else None
            if tool:
                return False, tool.handler()
            from core.idle_harvester import get_skill_harvester
            res = get_skill_harvester(self.registry).harvest_next_available()
            return False, str(res)
        if name == "/heal":
            parts = cmd.split(maxsplit=2)
            target = parts[1] if len(parts) > 1 else "app.py"
            err_ctx = parts[2] if len(parts) > 2 else ""
            tool = self.registry.get("self_heal_code") if self.registry else None
            if tool:
                return False, tool.handler(target_file=target, error_context=err_ctx)
            from evolution.self_healing_engine import get_self_healing_engine
            res = get_self_healing_engine().heal_workspace_file(target, err_ctx)
            return False, str(res)
        if name == "/briefing":
            tool = self.registry.get("generate_morning_briefing") if self.registry else None
            if tool:
                return False, tool.handler()
            from core.chief_of_staff import get_chief_of_staff
            return False, get_chief_of_staff(self.registry).generate_morning_briefing()["briefing_text"]
        if name == "/devlog":
            tool = self.registry.get("generate_daily_devlog") if self.registry else None
            if tool:
                return False, tool.handler()
            from core.chief_of_staff import get_chief_of_staff
            return False, get_chief_of_staff(self.registry).generate_daily_devlog()["summary"]
        if name == "/screen":
            parts = cmd.split(maxsplit=1)
            inst = parts[1] if len(parts) > 1 else "Describe everything visible on this screen."
            tool = self.registry.get("screen_capture_and_describe") if self.registry else None
            if tool:
                return False, tool.handler(instruction=inst)
            from core.visual_agent import get_visual_agent
            return False, get_visual_agent(self.registry).analyze_screen(inst)
        if name in {"/sentinel", "/proactive"}:
            tool = self.registry.get("check_proactive_alerts") if self.registry else None
            if tool:
                return False, tool.handler()
            from core.proactive_sentinel import get_proactive_sentinel
            return False, get_proactive_sentinel(self.registry).get_alerts_summary()
        if name == "/council":
            tool = self.registry.get("get_council_telemetry") if self.registry else None
            if tool:
                return False, str(tool.handler())
            from brain.model_council import get_model_council
            return False, str(get_model_council(self.registry).get_telemetry_summary())
        if name == "/bounty":
            parts = cmd.split(maxsplit=2)
            sub = parts[1] if len(parts) > 1 else "scan"
            from core.bounty_hunter import get_bounty_hunter
            bh = get_bounty_hunter(self.registry)
            if sub == "scan":
                target = parts[2] if len(parts) > 2 else "core"
                return False, bh.scan_directory_summary(target)
            if sub == "patch" and len(parts) > 2:
                return False, str(bh.generate_test_gap_patch(parts[2]))
            return False, "usage: /bounty scan <dir> | /bounty patch <file.py>"
        return False, ("command nahi pehchana — /history /audit /tools /model "
                       "/projects /use <naam> /new /journal /skills /skill "
                       "/evolution /eval /alerts /values /decide <situation> "
                       "/facts /remember /forget /mcp /desktop /reminders /briefing /plan /sentry /swarm /vault /browse /tech /nexus /research /shadow /code /optimize /graph /vapt /dag /simulate /forge /reflex /repo /context /missions /dpo /harvest /heal /backup ya exit")

    # -- skills (Task O): list + approve/retire/save + use accounting --------
    def skills_list(self) -> str:
        if not (self.config.get("skills") or {}).get("enabled"):
            return "Skills band hain (config: skills.enabled=false)."
        from evolution.skills import skills_text
        return skills_text()

    def skill_command(self, cmd: str) -> str:
        parts = cmd.split()
        if len(parts) < 2:
            return "usage: /skill approve <name> | /skill retire <name> | /skill save"
        if not (self.config.get("skills") or {}).get("enabled"):
            return "Skills band hain (config: skills.enabled=false)."
        from evolution import skills as sk
        sub = parts[1].lower()
        if sub == "approve" and len(parts) > 2:
            return sk.approve(parts[2])
        if sub == "retire" and len(parts) > 2:
            return sk.retire(parts[2])
        if sub == "save":
            tools = [t.get("tool") for t in self._trace]
            if not tools:
                return ("Is session me abhi koi tool-task hua nahi — "
                        "pehle kaam karwao, phir /skill save.")
            user, _ = self._last_turn
            ctx = {"severity": "none", "id": 0, "lesson": user[:150],
                   "what_worked": [f"clean turn: {', '.join(tools)} chale"],
                   "tools": tools}
            return (sk.propose_skill(ctx, self.brain, force=True)
                    or "Skill propose nahi hui (LLM fail/invalid output — dobara try).")
        return "skill subcommand nahi samjha — approve | retire | save"

    def _account_skills(self) -> None:
        """Turn end pe: get_skill use count — clean turn = success, retry = fail."""
        calls, self._skill_calls = self._skill_calls, []
        if not calls or not (self.config.get("skills") or {}).get("enabled"):
            return
        from evolution.skills import mark_used
        ok = not self._retried_turn
        for nm in calls:
            try:
                mark_used(nm, ok)
            except Exception:                    # noqa: BLE001 — count fail = ignore
                pass

    # -- watchdog hooks (Task Q): NOTIFY ONLY, enabled=false = skip --------
    def _alert(self, severity: str, rule: str, message: str) -> None:
        if not self.alerts:                    # None = watchdog band
            return
        try:
            self.alerts.emit(severity, rule, message)
        except Exception:                      # noqa: BLE001 — alert fail = turn pe asar 0
            pass

    def alerts_text(self, limit: int = 10) -> str:
        from safety.notifier import recent_alerts
        db = str(self.memory.db_path) if self.memory else ""
        try:
            rows = recent_alerts(db, limit)
        except Exception:                      # noqa: BLE001 — friendly msg
            return "Alerts padhe nahi ja sakte (watchdog off hoga)."
        if not rows:
            return "clean ✅ — abhi tak koi alert nahi (last 10)."
        glyph = {"CRITICAL": "🔴", "WARN": "⚠", "INFO": "·"}
        return "\n".join(
            f"{glyph.get(r['severity'], '·')} [{r['ts']}] "
            f"{r['rule']}: {r['message']}" for r in rows)

    def _turn_end_watch(self) -> None:
        """Turn-end quick disk check — <1GB = immediate CRITICAL (60s wait nahi)."""
        if not self.alerts or not self.wd_cfg.get("enabled"):
            return
        try:
            import shutil
            free = shutil.disk_usage("C:/").free / (1 << 30)
            if free < 1.0:
                self._alert("CRITICAL", "disk_free",
                            f"disk free {free:.1f} GB < 1 GB (turn-end check)")
        except OSError:
            pass

    # -- evolution metrics (Task P): /evolution + /eval ---------------------
    def evolution_cmd(self, cmd: str) -> str:
        parts = cmd.split()
        if len(parts) > 1 and parts[1].lower() == "judge":
            if self.journal is None:
                return "Journal attach nahi hai."
            from evolution.metrics import judge_unjudged
            return judge_unjudged(self.brain, self.journal)   # manual = sirf yahan
        from evolution.metrics import evolution_report, report_text
        from evolution.skills import list_skills
        db = str(self.memory.db_path) if self.memory else ""
        return report_text(evolution_report(db, list_skills()))   # INSTANT (0 LLM)

    @staticmethod
    def _eval_module():
        """data/eval/quality_test.py ko path se load (data/ = package nahi)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lumi_quality_test", "data/eval/quality_test.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def eval_cmd(self, cmd: str) -> str:
        parts = cmd.split()
        sub = parts[1].lower() if len(parts) > 1 else ""
        try:
            mod = self._eval_module()
            if sub == "run":
                s = mod.run_eval(self.brain)       # current policy brain (prefer_cloud)
                return (f"eval run saved: {s['run']}\n10 prompts · avg {s['avg_ms']}ms"
                        f" (per-prompt ms: summary.json)")
            if sub == "compare":
                return mod.compare_eval()
        except Exception as exc:                   # noqa: BLE001 — friendly msg
            return f"eval problem: {exc}"
        return "usage: /eval run | /eval compare"

    # -- evolution (req #5): REFLECT + STORE — reply ke baad, LLM call thread me
    def maybe_reflect(self, user_input: str, reply: str) -> None:
        """Reply deliver hone KE BAAD call ho — trigger pick + cooldown (sync),
        LLM call daemon thread me (user kabhi block nahi hota)."""
        if not self.evolution.get("enabled"):
            return
        on = set(self.evolution.get("reflect_on") or [])
        hb = int(self.evolution.get("heartbeat_every_n", 10) or 0)
        trigger = None
        if self._retried_turn and "error_retry" in on:
            trigger = "error_retry"
        elif self._trace and "tool_task" in on:
            trigger = "tool_task"
        elif hb and self._turn_count % hb == 0:
            trigger = "heartbeat"
        if trigger:
            self._spawn_reflect(trigger, user_input, reply)

    def _spawn_reflect(self, trigger: str, user_input: str, reply: str,
                       exempt: bool = False) -> None:
        """Cooldown + session cap check, phir reflection ko thread me de do."""
        if not self.evolution.get("enabled") or self.journal is None:
            return
        now = time.time()
        if not exempt:
            cooldown = float(self.evolution.get("min_interval_min", 5)) * 60
            cap = int(self.evolution.get("max_per_session", 3))
            if now - self._refl_last_ts < cooldown or self._refl_session >= cap:
                return                          # cooldown/cap = silent skip
        self._refl_last_ts = now
        self._refl_session += 1
        if trigger == "session_end":
            tools, retries = sorted(set(self._session_tools)), 0
            reply = f"session summary: {self._turn_count} turns, {reply[:200]}"
        else:
            tools = [t.get("tool") for t in self._trace]
            retries = 1 if self._retried_turn else 0
        turn = {"user": user_input, "reply": reply, "tools": tools,
                "retries": retries, "trigger": trigger}
        brain, journal, sid = self.brain, self.journal, self._sid()
        from evolution import reflect as _evolve       # local import = startup fast
        threading.Thread(target=lambda: _evolve.run(brain, turn, journal, sid),
                         daemon=True).start()

    def session_end_reflect(self) -> None:
        """/new ya exit pe — cooldown/cap exempt, summary-style entry."""
        if not self.evolution.get("enabled") or self.journal is None:
            return
        if self._turn_count <= 0:               # kuch hua hi nahi = skip
            return
        self._spawn_reflect("session_end", "(session end)",
                            f"tools: {', '.join(sorted(set(self._session_tools))) or 'koi nahi'}",
                            exempt=True)

    def force_reflect(self) -> str:
        """/reflect — manual force (cooldown exempt, enabled=false = refuse)."""
        if not self.evolution.get("enabled") or self.journal is None:
            return "Evolution band hai (config: evolution.enabled=false)."
        user, reply = self._last_turn
        if not user:
            return "Abhi reflect karne layak koi turn hua nahi."
        self._spawn_reflect("manual", user, reply, exempt=True)
        return "Manual reflect chal raha hai — thodi der me /journal me dikh jayega."

    def journal_text(self, limit: int = 10) -> str:
        if self.journal is None:
            return "Journal attach nahi hai."
        rows = self.journal.last_n(limit)
        if not rows:
            return "Journal khali hai — abhi tak koi reflection nahi hui."
        return "\n".join(
            f"[{r['ts']}] {r['trigger']} ({r['severity']}): {r['lesson']}"
            + (f" -> {r['improve_next']}" if r.get("improve_next") else "")
            for r in rows)

    def step(self, user_input: str) -> str:
        """CLI/JSON path — same engine as stream, events consume ho ke text bante hain."""
        text = ""
        for ev in self._events(user_input):
            if ev["type"] == "final":
                text = ev["text"]
        return text

    def run_turn_stream(self, user_input: str):
        """SSE generator — events: thinking -> tool/tool_done -> token* -> final -> done."""
        self._turn_lock.acquire()           # disconnect/GeneratorExit = finally release
        try:
            self._trace = []
            started = time.time()
            text = ""
            for ev in self._events(user_input):
                if ev["type"] == "final":
                    text = ev["text"]
                yield ev
            self._turn_end_watch()             # Task Q: instant disk CRITICAL
            # reflection trigger isi turn ke trace se pick hota hai (thread spawn = fast)
            self.maybe_reflect(user_input, text)
            yield {"type": "done", "reply": text, "tool_trace": self._trace,
                   "provider": getattr(self.brain, "last_provider", "ollama"),
                   "model": getattr(self.brain, "last_model",
                                    getattr(self.brain, "model", "-")),
                   "elapsed_ms": int((time.time() - started) * 1000)}
        finally:
            self._turn_lock.release()

    def _events(self, user_input: str):
        """Shared turn engine (CLI + Web) — yields event dicts, ends with final."""
        self.state = State.UNDERSTAND
        self._turn_count += 1
        self._retried_turn = False
        self._turn_tainted = False
        self._skill_calls = []
        self._turn_tools = {}                  # Task Q: fresh loop counts per turn
        self._loop_stop = False
        self._approved.clear()                   # permission expires each turn
        self._failed_tool_records.clear()

        # Update activity timestamp for autonomous idle harvester
        harvester = getattr(self, "skill_harvester", None)
        if harvester and hasattr(harvester, "record_user_activity"):
            harvester.record_user_activity()

        # --- DEPT 3: ACTIVE CONTEXT SENSOR AUTO-INJECTION ---
        sensor = getattr(self, "context_sensor", None)
        llm_user_content = user_input
        if sensor and hasattr(sensor, "should_auto_inject_context"):
            try:
                if sensor.should_auto_inject_context(user_input):
                    live_block = sensor.format_context_injection(user_input)
                    if live_block:
                        llm_user_content = f"{live_block}\n\nUser Request: {user_input}"
                        yield {"type": "context_sensor", "summary": live_block[:240]}
            except Exception:
                pass

        self.session.append({"role": "user", "content": llm_user_content})
        self.session = compact_session_history(self.session, num_ctx=8192, max_ratio=0.65)
        self._persist("user", user_input)
        self._sync_project_context()             # active project -> system msg

        # --- DEPT 1: TIER-0 DETERMINISTIC REFLEX (<5ms) & DYNAMIC TOP-K TOOL PRUNING ---
        all_schemas = self.registry.to_llm_schemas() if self.registry else []
        rx = getattr(self, "reflex_router", None)
        if rx is not None and self.config.get("reflex_tier0", True):
            reflex_hit = rx.check_tier0_reflex(
                user_input,
                context={
                    "model": getattr(self.brain, "last_model", getattr(self.brain, "model", "hermes3:latest")),
                    "policy": getattr(self.brain, "active_policy", "prefer_local"),
                    "tools_count": len(all_schemas),
                },
            )
            if reflex_hit and reflex_hit.get("matched"):
                text = reflex_hit["response"]
                self.state = State.RESPOND
                self.session.append({"role": "assistant", "content": text})
                self._persist("assistant", text)
                self._last_turn = (user_input, text)
                for chunk in rx.split_into_speech_chunks(text):
                    yield {"type": "speech_chunk", "text": chunk}
                yield {"type": "final", "text": text, "reflex": reflex_hit}
                return

        if all_schemas and len(all_schemas) > 14:
            try:
                from core.reflex_router import get_reflex_router
                pruner = rx or get_reflex_router()
                tools = pruner.select_relevant_tools(user_input, all_schemas, top_k=14)
            except Exception:
                tools = all_schemas
        else:
            tools = all_schemas if all_schemas else None
        yield {"type": "thinking"}

        for _ in range(self.max_iterations):
            reply = yield from self._chat_stream(tools)
            if reply.tool_calls:
                # OpenAI wire format (tool_call_id etc.) — Ollama accepts it too
                wire = []
                for c in reply.tool_calls:
                    self._cid += 1
                    c["_cid"] = f"call_{self._cid}"
                    # dict args = Ollama native; cloud adapter re-serializes
                    wire.append({"id": c["_cid"], "type": "function",
                                 "function": {"name": c["name"],
                                              "arguments": c.get("args") or {}}})
                self.session.append({"role": "assistant", "content": reply.text or "",
                                     "tool_calls": wire})
                for call in reply.tool_calls:
                    if self._loop_stop:        # Task Q: loop detected -> skip rest
                        break
                    yield {"type": "tool",
                           "tool": str(call.get("name") or ""),
                           "args": call.get("args") if isinstance(call.get("args"), dict)
                           else {}}
                    yield from self._run_tool(call)         # SAFETY -> ACT -> OBSERVE
                    if self._trace:
                        yield {"type": "tool_done", **self._trace[-1]}
                if self._loop_stop:            # Task Q: force-stop = no infinite
                    yield {"type": "final",
                           "text": "🛑 **Loop detect** — same tool+args "
                                   f"{self.wd_cfg.get('rules', {}).get('loop_repeat', 3)}"
                                   " baar repeat, turn force-stop (watchdog "
                                   "alert 🔴 dekh /alerts)."}
                    return
                continue                          # back to model with results
            self.state = State.RESPOND
            text = reply.text or "(khaali reply aaya)"
            self.session.append({"role": "assistant", "content": text})
            self._persist("assistant", text)
            self.state = State.REFLECT
            self.reflect()
            self._last_turn = (user_input, text)  # /reflect manual ka source
            self._account_skills()                # get_skill use -> uses/successes
            yield {"type": "final", "text": text}
            return

        yield {"type": "final",
               "text": f"⚠️ {self.max_iterations} tool steps ho gaye — "
                       "beech me rok diya. Thoda specific hoke bol."}

    def _chat_stream(self, tools):
        """brain.chat ko background thread me chalakar token events yield karta hai
        (callback = producer, generator = consumer, queue = bridge)."""
        q: queue.Queue = queue.Queue()
        box: dict = {}

        def run() -> None:
            try:
                box["reply"] = self.brain.chat(self.session, tools=tools,
                                               on_token=lambda t: q.put(("token", t)))
            except Exception as exc:  # noqa: BLE001 — generator side pe re-raise
                box["err"] = exc
            finally:
                q.put(None)

        threading.Thread(target=run, daemon=True).start()
        while True:
            item = q.get()
            if item is None:
                break
            yield {"type": "token", "text": item[1]}
        if "err" in box:
            raise box["err"]
        return box["reply"]

    # -- tool branch -------------------------------------------------------
    def _run_tool(self, call: dict) -> None:
        name = str(call.get("name") or "")
        args = call.get("args") or {}
        if isinstance(args, str):
            args = repair_and_parse_json(args)
        elif not isinstance(args, dict):
            args = {"input": str(args)}
        print(f"⚙️ TOOL: {name}({SafetyGate.fmt_args(args)})")

        # --- loop detection (Task Q): same (tool+args) ×N in one turn ----
        lk = f"{name}:{SafetyGate.fmt_args(args)}"
        self._turn_tools[lk] = self._turn_tools.get(lk, 0) + 1
        repeat = max(2, int((self.wd_cfg.get("rules") or {}).get("loop_repeat", 3)))
        if (self.wd_cfg.get("enabled") and not self._loop_stop
                and self.wd_cfg.get("loop_force_stop", True)
                and self._turn_tools[lk] >= repeat):
            self._loop_stop = True
            self._alert("CRITICAL", "loop",
                        f"LUMI in a loop: {name} same args ×"
                        f"{self._turn_tools[lk]} — turn force-stop")
            self._finish(call, "🛑 loop detected — same tool+args repeat, "
                        "turn rok diya (watchdog)", name, args, None)
            return

        tool = self.registry.get(name) if self.registry else None
        if tool is None:
            self._finish(call, "tool parse failed: unknown tool", name, args, "error", "parse")
            return

        verdict, reason = (self.gate.check(name, tool.risk, self._sid(), args,
                                           tainted=self._turn_tainted)
                           if self.gate else ("allow", "policy:auto"))
        if verdict == "block":
            msg = self.gate.block_message(reason) if self.gate else "Blocked by safety gate"
            self._finish(call, msg, name, args, None)
            return

        key = f"{name}:{SafetyGate.fmt_args(args)}"
        if verdict == "ask":
            if key in self._approved:
                decision, reason = "ask_yes", reason + "+pre_approved"
            else:
                aid = self.gate.prepare_approval(name, args) if hasattr(self.gate, "prepare_approval") else None
                if aid:
                    yield {"type": "approval_required", "id": aid, "tool": name, "args": args}
                    approved = self.gate.wait_approval(aid, timeout=60.0, session_id=self._sid(),
                                                       tool_name=name, args=args)
                else:
                    approved = self.gate.confirm(name, args, self._sid())
                if approved:
                    self._approved.add(key)
                    decision = "ask_yes"
                else:
                    self._finish(call, "User refused", name, args, None)
                    return
        else:
            decision = "auto"

        # --- ACT: execute with watchdog isolation (req #10 seed) ---
        args = coerce_tool_arguments(tool.params_schema, args)
        result, failed = execute_tool_with_watchdog(tool, args, timeout_sec=30.0)

        if not failed:
            self._retries.pop(key, None)
            prev_fail = self._failed_tool_records.pop(name, None)
            if prev_fail and getattr(self, "dpo_flywheel", None):
                try:
                    self.dpo_flywheel.record_tool_repair(
                        user_prompt=self._last_turn[0] or "tool_repair_turn",
                        tool_name=name,
                        failed_args=prev_fail.get("args") or {},
                        failed_error=str(prev_fail.get("error") or "prior_attempt_failed"),
                        healed_args=args,
                        healed_result=result[:300],
                    )
                except Exception:
                    pass
            if name in UNTRUSTED_TOOLS or name.startswith("mcp__"):
                self._turn_tainted = True
                result = f'<untrusted source="{name}">\n{result}\n</untrusted>'
            self._finish(call, result, name, args, decision, reason)
            return

        self._failed_tool_records[name] = {"args": args, "error": result}
        attempts = self._retries.get(key, 0) + 1
        self._retries[key] = attempts
        if attempts >= 2:                        # round 2 failed — give up, audit it
            self._retries.pop(key, None)
            self._alert("WARN", "tool_fail",    # Task Q: user ko turant dikhe
                        f"{name} fail after retry — {result[:80]}")
            self._finish(call, f"tool failed after retry — {result}", name,
                         args, "error", reason, retry_used=1)
        else:                                     # round 1 failed — one fix chance
            self._finish(call, f"{result} — fix & retry kar sakte ho (1 chance left)",
                         name, args, None)

    def _finish(self, call: dict, result: str, name: str, args: dict,
                decision: str | None, reason: str = "", retry_used: int = 0) -> None:
        """OBSERVE: append tool result for the model (+ audit if decided)."""
        self.state = State.OBSERVE
        if len(result) > MAX_TOOL_CHARS:
            result = (result[:MAX_TOOL_CHARS]
                      + f"\n...[truncated: {len(result)} chars total — "
                        "summary do, poora dump mat karo]")
        tool_msg = {"role": "tool", "content": result}
        if call.get("_cid"):                     # required by NVIDIA/OpenAI API
            tool_msg["tool_call_id"] = call["_cid"]
        self.session.append(tool_msg)
        self._trace.append({"tool": name, "args": args,          # web tool trace
                            "decision": str(decision or reason or "-"),
                            "result_summary": result[:200]})
        if name:
            self._session_tools.append(name)     # session_end reflection ka summary
        if retry_used:
            self._retried_turn = True            # error_retry trigger (evolution)
        if name == "get_skill":
            self._skill_calls.append(str(args.get("name") or ""))
        if decision and self.gate:
            summary = f"{reason} | {result[:160]}" if reason else result[:200]
            self.gate.log(self._sid(), name, args, decision, summary, retry_used)

    # -- helpers -----------------------------------------------------------
    def _sync_project_context(self) -> None:
        """Session[0] = active-project system note (ya hata do agar inactive)."""
        ctx = self.projects.active_context() if self.projects else ""
        if self.session and self.session[0].get("role") == "system":
            if ctx:
                self.session[0] = {"role": "system", "content": ctx}
            else:
                self.session.pop(0)
        elif ctx:
            self.session.insert(0, {"role": "system", "content": ctx})

    def _sid(self) -> str:
        return self.memory.session_id if self.memory else ""

    def _persist(self, role: str, content: str) -> None:
        if not self.memory:
            return
        try:
            self.memory.save_both(role, content)
        except RuntimeError as exc:
            print(f"LUMI: memory problem — {exc}")

    # -- session commands --------------------------------------------------
    def history_text(self, limit: int = 10) -> str:
        if not self.memory:
            return "Abhi memory attached nahi hai."
        rows = self.memory.recent(limit)
        if not rows:
            return "Memory khali hai — abhi tak koi baat nahi hui."
        return "\n".join(f"[{r['ts']}] {r['role']}: {r['content'][:80]}"
                         for r in rows)

    def tools_text(self) -> str:
        if not self.registry:
            return "Abhi koi tool registered nahi hai."
        perms = self.config.get("permissions") or {}
        return "\n".join(f"{t.name} — risk={t.risk}, config={perms.get(t.name, 'default')}"
                         for t in self.registry.list_all())

    def audit_text(self, limit: int = 5) -> str:
        if not self.audit:
            return "Abhi audit attached nahi hai."
        rows = self.audit.recent(limit)
        if not rows:
            return "Audit khali hai — abhi tak koi tool call nahi hui."
        return "\n".join(
            f"[{r['ts']}] {r['tool']} {r['args']} -> {r['decision']}"
            f"{' (retry)' if r['retry'] else ''}: {r['summary'][:60]}" for r in rows)

    # -- model router (/model) --------------------------------------------
    def model_status_text(self) -> str:
        if hasattr(self.brain, "status_text"):
            return self.brain.status_text()
        return f"Router nahi laga — direct brain chal raha ({type(self.brain).__name__})."

    def set_model_policy(self, value: str) -> str:
        if hasattr(self.brain, "set_policy"):
            return self.brain.set_policy(value)
        return "Is session me router attached nahi hai."

    # -- projects (/projects, /use) ---------------------------------------
    def projects_text(self) -> str:
        if not self.projects or not self.projects.projects:
            return "Koi project registered nahi — register_project se shuru karo."
        return "\n".join(
            f"{p.get('name')} — {p.get('path')} [{p.get('stack') or '?'}]"
            + ("  <- ACTIVE" if p is self.projects.active else "")
            for p in self.projects.projects)

    def use_project(self, name: str) -> str:
        if not self.projects:
            return "Project registry attach nahi hai."
        return self.projects.use(name)

    def new_session(self) -> str:
        with self._turn_lock:
            sid = self.memory.new_session() if self.memory else "no-memory"
            self.session = []
            # fresh session = fresh evolution budget (cooldown stay — turant dobara fire na ho)
            self._turn_count = 0
            self._refl_session = 0
            self._session_tools = []
            self._last_turn = ("", "")
            return sid

    def backup(self) -> str:
        if not self.memory:
            return "Abhi memory attached nahi hai."
        return f"Backup ho gaya: {self.memory.startup_backup().resolve()}"
