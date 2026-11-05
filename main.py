"""LUMI entry point: config -> memory -> tools -> safety -> brain -> CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# allow running as `python main.py` from anywhere — config/db paths are relative,
# so pin cwd to the project root (warna alag folder se chalane pe naya khaali DB banta)
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.chdir(Path(__file__).resolve().parent)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from brain.cloud_adapter import CloudBrain, NVIDIABrain
from brain.ollama_adapter import (OllamaBrain, load_config, set_facts,
                                  set_lessons, set_skills)
from brain.router import ModelRouter
from core.orchestrator import Orchestrator
from evolution.journal import Journal, load_lessons
from evolution.skills import list_skills, register_skill_tool
from interface import cli
from memory.repo import MemoryRepo
from safety.audit import AuditLog
from safety.gate import SafetyGate
from safety.notifier import Notifier, recent_alerts
from safety.watchdog import Watchdog
from tools.cleanup import register_cleanup_tools
from tools.desktop import register_desktop_tools
from tools.files import register_file_tools
from tools.gui import register_gui_tools
from tools.memory import register_memory_tools
from tools.projects import ProjectRegistry, register_project_tools
from tools.registry import ToolRegistry
from tools.sandbox import register_sandbox_tools
from tools.vision import register_vision_tools
from tools.web import register_web_tools


def build_router(config: dict) -> ModelRouter:
    """Local always on (direct merged model if present, else Ollama); cloud if API key exists."""
    local_engine = str(config.get("local_engine", "auto")).lower()
    merged_path = Path(config.get("merged_model_path", "models/lumi-qwen3-4b-hinglish-merged"))
    if not merged_path.is_absolute():
        merged_path = Path.cwd() / merged_path

    if local_engine in {"transformers", "hf", "direct", "auto"} and merged_path.exists():
        try:
            from brain.local_hf_adapter import LocalHFBrain
            local = LocalHFBrain(config=config)
            print("[brain] Active Local Engine: Native GPU (Merged LUMI Model)")
        except Exception as exc:
            print(f"[brain] Native GPU load fallback ({exc}) -> Ollama")
            local = OllamaBrain(config=config)
    else:
        local = OllamaBrain(config=config)

    cloud = None
    has_key = bool(
        os.environ.get("NVIDIA_API_KEY")
        or os.environ.get("GROQ_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("LUMI_CLOUD_API_KEY")
    )
    if has_key:
        try:
            cloud = CloudBrain(config)         # same persona system prompt
        except Exception as exc:  # noqa: BLE001 — init fail = friendly note
            print(f"LUMI: cloud brain start nahi hua — {exc} (local chal raha)")
    router = ModelRouter(local, cloud, config)
    prov = getattr(cloud, "provider", "cloud") if cloud else "none"
    state = f"cloud ({prov}) + local" if cloud else "local only (key missing)"
    print(f"[brain] policy={router.active_policy} | {state}")
    return router


def build_orchestrator(web: bool = False) -> Orchestrator | None:
    """Config -> memory -> tools -> safety -> brain -> orchestrator (shared)."""
    config = load_config("config.yaml")

    try:
        memory = MemoryRepo(config)      # init DB (WAL) + fresh session id
        memory.startup_backup()          # dated backup before anything else
        journal_mode = memory.journal_mode()
        journal = Journal(memory.db_path)         # evolution STORE (req #5)
        evo = config.get("evolution") or {}
        if evo.get("enabled"):                    # INJECT: lessons -> system prompt
            set_lessons(load_lessons(memory.db_path,
                                     int(evo.get("inject_last_n", 5))))
        sk_cfg = config.get("skills") or {}
        if sk_cfg.get("enabled"):                 # INJECT: active skills -> prompt
            set_skills(list_skills("active")[:int(sk_cfg.get("inject_max", 10))])
        set_facts(memory.load_facts_for_prompt(limit=10))  # INJECT: long-term facts -> prompt
    except Exception as exc:  # noqa: BLE001 — corrupt/locked DB = friendly message
        print(f"LUMI: memory database problem — {exc}")
        print("Hint: data/lumi.db band karke dobara try karo (corrupt ho toh "
              "data/backups/ se latest restore kar lena).")
        return None

    # ONE shared mutable allowlist: file tools closure + gate + registry merge
    allowed = list(config.get("allowed_paths") or [])
    registry = ToolRegistry()
    register_file_tools(registry, allowed)
    register_memory_tools(registry, memory)
    ws_path = Path(allowed[0]) / "workspace" if allowed else Path("workspace")
    register_web_tools(registry)
    register_sandbox_tools(registry, ws_path)
    register_cleanup_tools(registry, ws_path)
    register_desktop_tools(registry)
    register_vision_tools(registry)
    register_gui_tools(registry)
    projects = ProjectRegistry(allowed_paths=allowed)   # loads data/projects.yaml
    register_project_tools(registry, projects)
    if (config.get("skills") or {}).get("enabled"):
        register_skill_tool(registry)            # get_skill = read-only recipe loader
    from tools.mcp_client import get_mcp_manager
    get_mcp_manager().init_from_config(config, registry)
    audit = AuditLog(memory.db_path)
    gate = SafetyGate(config, asker=cli.web_asker if web else cli.ask_user,
                      audit=audit, is_web=web)
    gate.allowed_paths = allowed                 # same object — registered = allowed

    brain = build_router(config)
    alerts, wd = None, None                    # watchdog (req #11) — notify only
    wd_cfg = config.get("watchdog") or {}
    if wd_cfg.get("enabled"):
        tg = config.get("telegram") or {}
        alerts = Notifier(memory.db_path,
                          int(wd_cfg.get("dedupe_cooldown_min", 30)),
                          telegram_ids=tg.get("allowed_chat_ids") or [])
        wd = Watchdog("config.yaml", emit=alerts.emit,
                      db_path=str(memory.db_path))
        wd.start()
        import atexit
        atexit.register(wd.stop)
    from core.scheduler import get_lumi_scheduler, register_scheduler_tools
    scheduler = get_lumi_scheduler(memory=memory, notifier=alerts, config=config)
    register_scheduler_tools(registry, scheduler)
    scheduler.start()
    import atexit
    atexit.register(scheduler.stop)
    orchestrator = Orchestrator(brain=brain, config=config, memory=memory,
                                registry=registry, gate=gate, audit=audit,
                                projects=projects, journal=journal,
                                alerts=alerts)
    orchestrator.watchdog = wd                 # debug/tests ke liye handle
    from tools.planner import register_planner_tools
    register_planner_tools(registry, orchestrator)
    from tools.swarm import register_swarm_tools
    register_swarm_tools(registry, orchestrator, ws_path)
    from tools.vault import register_vault_tools
    orchestrator.vault = register_vault_tools(registry)
    from tools.web_operator import register_web_operator_tools
    orchestrator.web_operator = register_web_operator_tools(registry, orchestrator)
    from tools.nexus import register_nexus_tools
    orchestrator.nexus = register_nexus_tools(registry)
    from safety.sentry import AmbieSentry
    from tools.sentry import register_sentry_tools
    sentry = None
    sentry_cfg = config.get("sentry") or {}
    if sentry_cfg.get("enabled", True):
        sentry = AmbieSentry(config=config, notifier=alerts, db_path=str(memory.db_path),
                             downloads_path=str(Path.home() / "Downloads"),
                             workspace_path=str(Path(".").resolve()))
        sentry.start()
        import atexit
        atexit.register(sentry.stop)
        register_sentry_tools(registry, sentry)
    orchestrator.sentry = sentry
    from safety.biometrics import get_presence_watcher
    from tools.biometrics import register_biometrics_tools
    bio_cfg = config.get("biometrics") or {}
    bio_watcher = register_biometrics_tools(registry, notifier=alerts)
    if bio_cfg.get("enabled", True) and bio_cfg.get("auto_start", False):
        bio_watcher.start()
        import atexit
        atexit.register(bio_watcher.stop)
    orchestrator.biometrics = bio_watcher
    from core.synthesizer import get_tool_synthesizer
    from tools.synthesizer import register_synthesizer_tools
    orchestrator.synthesizer = register_synthesizer_tools(registry, brain=brain)
    from finance.oracle import get_fintech_oracle
    from tools.finance import register_finance_tools
    orchestrator.finance = register_finance_tools(registry)
    from brain.mcts_reasoner import get_deep_reasoner
    from tools.reasoner import register_reasoner_tools
    orchestrator.reasoner = register_reasoner_tools(registry, brain=brain)
    from voice.emotion_synthesizer import get_emotion_synthesizer
    from tools.emotion_voice import register_emotion_voice_tools
    orchestrator.emotion_voice = register_emotion_voice_tools(registry)
    from mesh.cluster import get_cluster_mesh
    from tools.cluster import register_cluster_tools
    orchestrator.cluster = register_cluster_tools(registry, config=config, notifier=alerts)
    from tools.deep_research import register_deep_research_tools
    orchestrator.researcher = register_deep_research_tools(registry, workspace_root=ws_path, brain=brain)
    from evolution.digital_shadow import register_digital_shadow_tools
    orchestrator.digital_shadow = register_digital_shadow_tools(registry, repo_root=".", brain=brain)
    from tools.code_oracle import register_code_oracle_tools
    orchestrator.code_oracle = register_code_oracle_tools(registry, workspace_root=".")
    from tools.workstation_cleaner import register_cleaner_tools
    orchestrator.workstation_guardian = register_cleaner_tools(registry, workspace_root=".")
    from tools.cognitive_graph import register_cognitive_graph_tools
    orchestrator.cognitive_graph = register_cognitive_graph_tools(
        registry, db_path=str(memory.db_path), brain=brain
    )
    from tools.cyber_sentinel import register_cyber_sentinel_tools
    orchestrator.cyber_sentinel = register_cyber_sentinel_tools(
        registry, workspace_root=".", brain=brain
    )
    from tools.dag_executor import register_dag_executor_tools
    orchestrator.dag_executor = register_dag_executor_tools(registry, brain=brain)
    from tools.world_model import register_world_model_tools
    orchestrator.world_model = register_world_model_tools(
        registry, workspace_root=ws_path, brain=brain
    )
    # ── Phase 29–35 (v35.0): STARK APEX PROTOCOL (Depts 1, 2, 3, 4) ──────
    from tools.reflex_router import register_reflex_router_tools
    orchestrator.reflex_router = register_reflex_router_tools(registry)
    from tools.repo_graph import register_repo_graph_tools
    orchestrator.repo_graph = register_repo_graph_tools(registry, workspace_root=".")
    from tools.context_sensor import register_context_sensor_tools
    orchestrator.context_sensor = register_context_sensor_tools(registry, workspace_root=".")
    from tools.mission_queue import register_mission_queue_tools
    orchestrator.mission_queue = register_mission_queue_tools(
        registry, orchestrator=orchestrator, workspace_root=ws_path, brain=brain
    )
    from evolution.dpo_flywheel import register_dpo_flywheel_tools
    orchestrator.dpo_flywheel = register_dpo_flywheel_tools(registry)
    names = ", ".join(t.name for t in registry.list_all())
    print(f"[memory] {memory.count_messages()} messages, journal={journal_mode}")
    print(f"[evolution] {'on' if (config.get('evolution') or {}).get('enabled') else 'off'}"
          f" | reflections today={journal.count_today()}")
    print(f"[projects] {len(projects.projects)} registered | "
          f"[tools] {names} | [safety] gate ON")
    if alerts:
        last = recent_alerts(str(memory.db_path), 1)
        tail = f"{last[0]['severity']} {last[0]['rule']}" if last else "none"
        print(f"[watchdog] ON — last: {tail}")
    else:
        print("[watchdog] off (config: watchdog.enabled=false)")
    # telegram (req #12) — env token ONLY, allowlist config; fail = LUMI unaffected
    tg = config.get("telegram") or {}
    if tg.get("enabled"):
        from interface.telegram_bot import MANUAL, TelegramBot
        bot = TelegramBot(orchestrator, tg.get("allowed_chat_ids") or [])
        if bot.ready:
            bot.start()
            import atexit
            atexit.register(bot.stop)
            print(f"[telegram] ON ({len(bot.allowed)} chat)")
        else:
            print("[telegram] OFF (no token)")
            print(MANUAL)                      # bootstrap steps = console pe
        orchestrator.tg_bot = bot
    else:
        print("[telegram] off (config: telegram.enabled=false)")
    vc = config.get("voice") or {}
    if vc.get("enabled"):
        tts = vc.get("tts") or {}
        tail = (f" | TTS: {tts.get('engine', 'edge')}/{tts.get('voice', '?')}"
                if tts.get("enabled") else " | TTS OFF")
        print(f"[voice] ON ({vc.get('whisper_model', 'small')}/"
              f"{vc.get('device', 'auto')}){tail}")
    else:
        print("[voice] OFF (disabled)")
    from core import values as V
    V.ensure_file()                              # missing -> '[values] created'
    _vd = V.load_values()
    _vc2 = V.counts(_vd)
    print(f"[values] ok ({_vc2['total']} rules)")
    print()
    return orchestrator


def pick_port() -> int | None:
    # localhost bind check — busy ho toh next port try (8765 -> 8766)
    import socket
    for port in (8765, 8766):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return None


def run_web(orchestrator: Orchestrator) -> None:
    """--web: uvicorn on 127.0.0.1 (LAN exposure NAHI — see web/server.py)."""
    import uvicorn
    import webbrowser

    from web.server import create_app

    port = pick_port()
    if port is None:
        print("LUMI: 8765 aur 8766 dono busy hain — koi process band karke "
              "phir try karo.")
        return
    url = f"http://127.0.0.1:{port}"
    orchestrator.web_port = port                # /values CLI line ke liye real port
    print(f"[web] {url} par chal raha hai (localhost only)")
    webbrowser.open(url)                     # auto-open browser
    uvicorn.run(create_app(orchestrator), host="127.0.0.1", port=port,
                log_level="warning")


def main() -> None:
    web_mode = "--web" in sys.argv[1:]
    orchestrator = build_orchestrator(web=web_mode)
    if orchestrator is None:
        return
    if web_mode:
        run_web(orchestrator)
    else:
        cli.run(orchestrator)               # default = CLI (as before)


if __name__ == "__main__":
    main()
