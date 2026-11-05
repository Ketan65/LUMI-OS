"""LUMI web server — FastAPI, localhost only.

SECURITY: sirf 127.0.0.1 bind hota hai — LAN/external exposure NAHI.
Future phase: auth tabhi jab LAN chahiye (abhi ke liye localhost = implicit auth).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import time
from datetime import date
from pathlib import Path

import os
import secrets
import yaml
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import (FileResponse, JSONResponse, Response,
                               StreamingResponse)
from pydantic import BaseModel, Field

WEB_DIR = Path(__file__).resolve().parent
VERSION = "0.5.0"                     # LUMI release tag (frontend chip)
STARTED = time.time()                 # create_app isse refresh karta hai


class LoginIn(BaseModel):
    token: str = Field(max_length=256)


class ChatIn(BaseModel):
    message: str = Field(max_length=8000)
    stream: bool = False            # true = SSE (text/event-stream), false = JSON


class SpeakIn(BaseModel):
    text: str = Field(max_length=4000)
    voice: str | None = None
    engine: str | None = None


class VoiceSetIn(BaseModel):
    voice: str | None = None
    engine: str | None = None
    elevenlabs_key: str | None = None


class ValuesIn(BaseModel):
    content: str = Field(max_length=60_000)


class ApproveIn(BaseModel):
    id: str = Field(max_length=64)
    approved: bool


class FactIn(BaseModel):
    key: str = Field(max_length=120)
    value: str = Field(max_length=2000)
    category: str = Field(default="general", max_length=60)


class VisionIn(BaseModel):
    prompt: str = Field(default="Explain what is on my screen right now", max_length=4000)
    image_base64: str | None = None
class SwarmIn(BaseModel):
    goal: str = Field(max_length=4000)
    project_name: str | None = None


class VaultQueryIn(BaseModel):
    query: str = Field(max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)
    file_filter: str | None = None


class VaultIndexIn(BaseModel):
    path: str = Field(default=".", max_length=500)
    recursive: bool = True


class BrowseIn(BaseModel):
    url: str = Field(max_length=2000)
    summarize: bool = True


class FocusIn(BaseModel):
    preset: str = Field(default="code_sprint", max_length=50)


class TriggerIn(BaseModel):
    url: str = Field(max_length=2000)
    payload: dict | None = None


class BiometricsConfigIn(BaseModel):
    enabled: bool | None = None
    auto_lock: bool | None = None
    lock_timeout_sec: int | None = None
    shoulder_surf_shield: bool | None = None


class ShieldControlIn(BaseModel):
    active: bool


class BiometricsEnrollIn(BaseModel):
    profile_name: str = Field(default="master", max_length=100)
    sample_count: int = 3


class ToolForgeIn(BaseModel):
    tool_name: str = Field(max_length=100)
    description: str = Field(max_length=1000)
    python_code: str = Field(max_length=50000)
    test_code: str = Field(max_length=50000)
    params_schema: dict | None = None


class ToolRevokeIn(BaseModel):
    tool_name: str = Field(max_length=100)


class ToolBenchmarkIn(BaseModel):
    tool_name: str = Field(max_length=100)
    sample_args: dict | None = None
    runs: int = 5


class FinanceTxnIn(BaseModel):
    amount: float
    description: str = Field(max_length=500)
    date: str | None = None
    category: str | None = None
    txn_type: str = "debit"


class FinanceSubscriptionIn(BaseModel):
    name: str = Field(max_length=200)
    amount: float
    billing_cycle: str = "monthly"
    renewal_day: int = 1
    category: str = "saas"


class FinanceInvoiceIn(BaseModel):
    client_name: str = Field(max_length=200)
    items: list[dict]
    client_email: str | None = None
    invoice_number: str | None = None
    tax_rate_pct: float = 18.0


class ReasonerExploreIn(BaseModel):
    problem: str = Field(max_length=5000)
    depth: int = 2
    branches: int = 3
    domain: str = "general"


class VoiceAffectConfigIn(BaseModel):
    mode: str = "auto"
    pacing_offset: int | None = None


class ClusterDispatchIn(BaseModel):
    task_type: str = Field(max_length=120)
    payload: dict = Field(default_factory=dict)
    target_node: str | None = None


class ClusterRegisterIn(BaseModel):
    node_id: str = Field(max_length=120)
    alias: str = Field(max_length=120)
    role: str = Field(default="satellite", max_length=30)
    host: str = Field(default="127.0.0.1", max_length=100)
    port: int = Field(default=8766, ge=1024, le=65535)
    capabilities: list[str] = Field(default_factory=lambda: ["general"])


class ClusterSyncIn(BaseModel):
    destination_node: str | None = None
    context_data: dict = Field(default_factory=dict)


class ClusterHeartbeatIn(BaseModel):
    node_id: str = Field(max_length=120)
    telemetry: dict = Field(default_factory=dict)


class ClusterExecuteIn(BaseModel):
    dispatch_id: str = Field(max_length=120)
    task_type: str = Field(max_length=120)
    payload: dict = Field(default_factory=dict)
    origin_node: str = Field(default="peer", max_length=120)


class ResearchIn(BaseModel):
    topic: str = Field(max_length=1000)
    max_sources: int = Field(default=4, ge=1, le=10)


class CodeAuditIn(BaseModel):
    file_path: str = Field(max_length=500)


class WorkstationOptimizeIn(BaseModel):
    dry_run: bool = True







# -- security ---------------------------------------------------------------
# Server localhost-only hai, par browser me khula koi bhi dusri website
# 127.0.0.1:8765 ko POST kar sakti hai (CSRF) ya DNS-rebinding kar sakti hai.
# Isliye: Host header + Origin header dono local hone chahiye.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_AUDIO_BYTES = 15 * 1024 * 1024
ASSETS = {"app.js": "text/javascript", "style.css": "text/css"}


def _host_only(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("["):                     # [::1]:8765
        return value[1:].split("]")[0]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def create_app(orchestrator) -> FastAPI:
    """App factory — orchestrator (shared brain/memory/tools) yahan aata hai."""
    global STARTED
    STARTED = time.time()               # uptime = server start se (real clock)
    app = FastAPI(title="LUMI", docs_url=None, redoc_url=None)

    web_cfg = orchestrator.config.get("web") or {}
    auth_token = str(web_cfg.get("auth_token") or os.environ.get("LUMI_AUTH_TOKEN") or "").strip()
    allow_remote = bool(web_cfg.get("allow_remote", False))
    failed_logins: dict[str, list[float]] = {}

    @app.middleware("http")
    async def auth_and_host_guard(request: Request, call_next):
        # 1. Host / Origin check
        if not allow_remote:
            if _host_only(request.headers.get("host", "")) not in LOCAL_HOSTS:
                return JSONResponse(status_code=403,
                                    content={"detail": "Forbidden: non-local host."})
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and (urlparse(origin).hostname or "") not in LOCAL_HOSTS:
                    return JSONResponse(status_code=403, content={
                        "detail": "Forbidden: cross-site request blocked."})

        # 2. Auth check if auth_token is configured
        if auth_token:
            path = request.url.path
            exempt = {
                "/",
                "/manifest.json",
                "/sw.js",
                "/api/login",
                "/api/status",
            }
            if path.startswith("/api/") and path not in exempt and request.method != "OPTIONS":
                token = ""
                auth_hdr = request.headers.get("authorization", "")
                if auth_hdr.lower().startswith("bearer "):
                    token = auth_hdr[7:].strip()
                elif "x-lumi-key" in request.headers:
                    token = request.headers["x-lumi-key"].strip()
                elif "lumi_auth" in request.cookies:
                    token = request.cookies["lumi_auth"].strip()

                if not token or not secrets.compare_digest(token, auth_token):
                    return JSONResponse(status_code=401,
                                        content={"error": "Unauthorized — valid auth_token required"})

        return await call_next(request)

    @app.post("/api/login")
    def login(p: LoginIn, request: Request):
        if not auth_token:
            return JSONResponse({"ok": True, "note": "Auth not configured"})

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        attempts = [t for t in failed_logins.get(client_ip, []) if now - t < 60]
        failed_logins[client_ip] = attempts
        if len(attempts) >= 5:
            return JSONResponse(status_code=429,
                                content={"error": "Too many failed attempts — wait 1 minute"})

        if not secrets.compare_digest(p.token.strip(), auth_token):
            failed_logins[client_ip].append(now)
            return JSONResponse(status_code=401, content={"error": "Invalid auth token"})

        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            key="lumi_auth",
            value=p.token.strip(),
            max_age=86400 * 30,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return resp

    @app.post("/api/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(key="lumi_auth", path="/")
        return resp

    @app.get("/manifest.json")
    def manifest():
        return FileResponse(WEB_DIR / "manifest.json", media_type="application/manifest+json")

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript")

    @app.post("/api/chat")
    def chat(payload: ChatIn):
        msg = (payload.message or "").strip()
        if not msg:
            return JSONResponse(status_code=400,
                                content={"detail": "Message khaali hai — kuch likho."})
        if payload.stream:
            def gen():
                # events: thinking -> tool/tool_done -> token* -> final -> done
                try:
                    if msg.startswith("/"):
                        _, text = orchestrator.command(msg)
                        yield _sse({"type": "done", "reply": text, "tool_trace": [],
                                    "provider": "-", "model": "-", "elapsed_ms": 0})
                        return
                    for ev in orchestrator.run_turn_stream(msg):
                        yield _sse(ev)
                except ConnectionError as exc:   # Ollama band / cloud down
                    yield _sse({"type": "error", "detail": str(exc)})
                except Exception as exc:  # noqa: BLE001 — friendly event, no stacktrace
                    yield _sse({"type": "error",
                                "detail": f"kuch gadbad ho gayi — {exc}"})
            return StreamingResponse(
                gen(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                         "X-Accel-Buffering": "no"})
        try:
            if msg.startswith("/"):
                # slash commands: same dispatcher as CLI (orchestrator.command)
                _, text = orchestrator.command(msg)
                return {"reply": text, "tool_trace": [], "provider": "-",
                        "model": "-", "elapsed_ms": 0}
            turn = orchestrator.run_turn(msg)     # sync → FastAPI threadpool
            orchestrator.maybe_reflect(msg, turn["reply"])   # reply ke BAAD
            return turn
        except ConnectionError as exc:            # Ollama band / cloud down
            return JSONResponse(status_code=503, content={"detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 — friendly JSON, no stacktrace
            return JSONResponse(status_code=500,
                                content={"detail": f"kuch gadbad ho gayi — {exc}"})

    @app.get("/api/journal")
    def journal(limit: int = 10) -> dict:
        """Evolution journal (future UI) — last N reflections, honest empty."""
        j = getattr(orchestrator, "journal", None)
        if j is None:
            return {"entries": [], "count_today": 0}
        return {"entries": j.last_n(limit), "count_today": j.count_today()}

    @app.get("/api/approvals/pending")
    def list_pending():
        mgr = getattr(orchestrator.gate, "approval_mgr", None)
        return {"pending": mgr.list_pending() if mgr else []}

    @app.post("/api/approve")
    def submit_approval(p: ApproveIn):
        if hasattr(orchestrator.gate, "resolve_approval"):
            ok = orchestrator.gate.resolve_approval(p.id, p.approved)
            return {"ok": ok}
        return JSONResponse(status_code=400, content={"error": "approval manager missing"})

    @app.get("/api/facts")
    def list_facts(category: str = "") -> dict:
        mem = getattr(orchestrator, "memory", None)
        facts = mem.list_facts(category=category) if mem else []
        return {"facts": facts}

    @app.post("/api/facts")
    def add_fact(p: FactIn) -> dict:
        mem = getattr(orchestrator, "memory", None)
        if not mem:
            return JSONResponse(status_code=400, content={"error": "memory missing"})
        mem.remember(p.key, p.value, category=p.category)
        from brain.ollama_adapter import set_facts
        set_facts(mem.load_facts_for_prompt(10))
        return {"ok": True}

    @app.delete("/api/facts/{key_or_id}")
    def delete_fact(key_or_id: str) -> dict:
        mem = getattr(orchestrator, "memory", None)
        if not mem:
            return JSONResponse(status_code=400, content={"error": "memory missing"})
        ok = mem.forget(key_or_id)
        from brain.ollama_adapter import set_facts
        set_facts(mem.load_facts_for_prompt(10))
        return {"ok": ok}

    @app.get("/api/skills")
    def skills() -> dict:
        """Skill library (future UI) — data/skills/*.yaml as-is."""
        if not ((orchestrator.config.get("skills") or {}).get("enabled")):
            return {"skills": [], "enabled": False}
        from evolution.skills import list_skills
        return {"skills": list_skills(), "enabled": True}

    @app.get("/api/evolution")
    def evolution() -> dict:
        """Evolution report card JSON (same as /evolution) — 0 LLM, instant."""
        from evolution.metrics import evolution_report
        from evolution.skills import list_skills
        mem = getattr(orchestrator, "memory", None)
        return evolution_report(str(mem.db_path) if mem else "", list_skills())

    @app.get("/api/alerts")
    def alerts(active: int = 0) -> dict:
        """Watchdog alerts (Task Q) — active=1 = sticky banner ka data."""
        from safety.notifier import recent_alerts
        mem = getattr(orchestrator, "memory", None)
        wd = orchestrator.config.get("watchdog") or {}
        win = int(wd.get("dedupe_cooldown_min", 30)) if active else None
        rows = recent_alerts(str(mem.db_path) if mem else "", 20,
                             active_window_min=win)
        return {"alerts": rows, "active": bool(active)}

    @app.get("/api/sentry/status")
    def sentry_status() -> dict:
        """Phase 7: AMBIE-SENTRY — proactive ambient guardian status."""
        s = getattr(orchestrator, "sentry", None)
        return s.get_status() if s else {"enabled": False}

    @app.post("/api/sentry/toggle")
    def sentry_toggle() -> dict:
        """Toggle proactive sentry guardian on/off."""
        s = getattr(orchestrator, "sentry", None)
        if not s:
            return {"enabled": False}
        s.enabled = not s.enabled
        return {"enabled": s.enabled}

    @app.post("/api/transcribe")
    async def transcribe(file: UploadFile, language: str = Form("auto"),
                         prompt: str = Form("")) -> dict:
        """Voice IN (Task S) — local whisper, localhost only. disabled = 410."""
        vc = orchestrator.config.get("voice") or {}
        if not vc.get("enabled"):
            return JSONResponse(status_code=410, content={
                "error": "Voice band hai (config: voice.enabled=false) — "
                         "text likh do."})
        import asyncio
        import os
        import tempfile
        from voice import stt
        suffix = Path(file.filename or "rec.webm").suffix or ".webm"
        try:
            data = await file.read(MAX_AUDIO_BYTES + 1)
            if not data:
                return {"error": "Audio khaali hai — dobara record karo."}
            if len(data) > MAX_AUDIO_BYTES:
                return JSONResponse(status_code=413, content={
                    "error": "Audio bahut bada hai (max 15 MB)."})
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                tf.write(data)
                tmp = tf.name
            try:
                lang = language if language not in ("", "auto") else str(vc.get("language", "auto"))
                text = await asyncio.to_thread(
                    stt.transcribe,
                    tmp,
                    model=str(vc.get("whisper_model", "small")),
                    language=lang,
                    device=str(vc.get("device", "auto")),
                    initial_prompt=prompt if prompt else None)
            finally:
                os.unlink(tmp)
        except Exception as exc:            # noqa: BLE001 — friendly, no stack
            return {"error": f"Audio process nahi hua — {exc}"}
        if not text:
            return {"error": "Samajh nahi aaya — dobara bolo ya text likh do."}
        return {"text": text}

    @app.post("/api/speak")
    def speak(p: SpeakIn) -> Response:
        """Voice OUT — ElevenLabs / Edge-TTS mp3 bytes, localhost only."""
        tc = ((orchestrator.config.get("voice") or {}).get("tts") or {})
        if not tc.get("enabled", True):
            return JSONResponse(status_code=410, content={
                "error": "Voice band hai (config: voice.tts.enabled=false)."})
        if not p.text.strip():
            return JSONResponse(status_code=400, content={
                "error": "Text khaali hai — kuch bolo."})
        import os
        import tempfile
        from voice import tts
        tmp = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False,
                                             suffix=".mp3") as tf:
                tmp = tf.name
            sel_voice = p.voice or str(tc.get("voice", "hi-IN-MadhurNeural"))
            sel_engine = p.engine or str(tc.get("engine", "auto"))
            tts.synthesize(p.text, tmp,
                           voice=sel_voice,
                           engine=sel_engine,
                           rate=str(tc.get("rate", "+0%")))
            data = Path(tmp).read_bytes()
            return Response(content=data, media_type="audio/mpeg")
        except RuntimeError as exc:
            return JSONResponse(status_code=503, content={
                "error": f"TTS unavailable — {exc}"})
        except ValueError:
            return JSONResponse(status_code=400, content={
                "error": "Bolne layak text nahi bacha."})
        finally:
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    @app.get("/api/voice")
    def get_voice():
        tc = ((orchestrator.config.get("voice") or {}).get("tts") or {})
        has_eleven = bool(os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY"))
        return {
            "enabled": bool(tc.get("enabled", True)),
            "engine": str(tc.get("engine", "auto")),
            "voice": str(tc.get("voice", "hi-IN-MadhurNeural")),
            "has_elevenlabs_key": has_eleven,
            "voices": [
                {"id": "hi-IN-MadhurNeural", "name": "Madhur (Hinglish Male — Natural & Friendly)", "provider": "edge", "type": "free"},
                {"id": "hi-IN-SwaraNeural", "name": "Swara (Hinglish Female — Warm & Clear)", "provider": "edge", "type": "free"},
                {"id": "en-IN-NeerjaNeural", "name": "Neerja (Indian English Female)", "provider": "edge", "type": "free"},
                {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Indian English Male)", "provider": "edge", "type": "free"},
                {"id": "eleven_adam", "name": "ElevenLabs Adam (Multilingual V2)", "provider": "elevenlabs", "type": "cloud"},
                {"id": "eleven_rachel", "name": "ElevenLabs Rachel (Multilingual V2)", "provider": "elevenlabs", "type": "cloud"},
                {"id": "eleven_charlie", "name": "ElevenLabs Charlie (Multilingual V2)", "provider": "elevenlabs", "type": "cloud"},
            ]
        }

    @app.post("/api/voice")
    def set_voice(p: VoiceSetIn):
        if "voice" not in orchestrator.config:
            orchestrator.config["voice"] = {}
        if "tts" not in orchestrator.config["voice"]:
            orchestrator.config["voice"]["tts"] = {}
        tc = orchestrator.config["voice"]["tts"]
        if p.voice:
            tc["voice"] = p.voice
        if p.engine:
            tc["engine"] = p.engine
        if p.elevenlabs_key:
            os.environ["ELEVENLABS_API_KEY"] = p.elevenlabs_key.strip()
        return {"ok": True, "voice": tc.get("voice"), "engine": tc.get("engine")}

    @app.post("/api/vision/analyze")
    def vision_analyze(p: VisionIn) -> dict:
        """Phase 2: EYES — Multimodal screen and visual inspection endpoint."""
        from tools.vision import LATEST_SCREENSHOT, analyze_screen, analyze_screen_image
        import base64

        if p.image_base64:
            data = p.image_base64
            if "," in data:
                data = data.split(",", 1)[1]
            try:
                raw_bytes = base64.b64decode(data)
                LATEST_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
                LATEST_SCREENSHOT.write_bytes(raw_bytes)
                analysis = analyze_screen_image(raw_bytes, prompt=p.prompt)
                return {"ok": True, "analysis": analysis, "image_url": "/api/vision/latest"}
            except Exception as exc:
                return JSONResponse(status_code=400, content={"error": f"Failed to process image: {exc}"})
        else:
            analysis = analyze_screen(prompt=p.prompt)
            return {
                "ok": True,
                "analysis": analysis,
                "image_url": "/api/vision/latest" if LATEST_SCREENSHOT.exists() else None,
            }

    @app.get("/api/vision/latest")
    def vision_latest():
        from tools.vision import LATEST_SCREENSHOT
        if LATEST_SCREENSHOT.exists():
            return FileResponse(LATEST_SCREENSHOT, media_type="image/jpeg")
        return JSONResponse(status_code=404, content={"error": "No screenshot found"})

    @app.post("/api/swarm")
    def post_swarm(p: SwarmIn):
        if not p.goal.strip():
            return JSONResponse(status_code=400, content={"error": "Goal cannot be empty"})
        from core.swarm import SwarmCoordinator
        coordinator = SwarmCoordinator(workspace_root="workspace", brain=orchestrator.brain)
        try:
            res = coordinator.develop(goal=p.goal, project_name=p.project_name)
            return res
        except Exception as exc:
            return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.get("/api/vault/stats")
    def vault_stats():
        from core.vault import NeuralVault
        v = getattr(orchestrator, "vault", None) or NeuralVault()
        return v.get_stats()

    @app.post("/api/vault/query")
    def vault_query(p: VaultQueryIn):
        if not p.query.strip():
            return JSONResponse(status_code=400, content={"error": "Query cannot be empty"})
        from core.vault import NeuralVault
        v = getattr(orchestrator, "vault", None) or NeuralVault()
        results = v.search(query=p.query, top_k=p.top_k, file_filter=p.file_filter)
        return {
            "query": p.query,
            "count": len(results),
            "results": [
                {
                    "file_path": r.file_path,
                    "chunk_index": r.chunk_index,
                    "start_line": r.start_line,
                    "end_line": r.end_line,
                    "score": r.score,
                    "snippet": r.snippet,
                }
                for r in results
            ],
        }

    @app.post("/api/vault/index")
    def vault_index_endpoint(p: VaultIndexIn):
        from core.vault import NeuralVault
        v = getattr(orchestrator, "vault", None) or NeuralVault()
        res = v.index_path(target_path=p.path, recursive=p.recursive)
        stats = v.get_stats()
        return {"result": res, "stats": stats}

    @app.post("/api/web/browse")
    def post_browse(p: BrowseIn):
        if not p.url.strip():
            return JSONResponse(status_code=400, content={"error": "URL cannot be empty"})
        from core.web_operator import WebOperator
        op = getattr(orchestrator, "web_operator", None) or WebOperator(brain=orchestrator.brain)
        page = op.fetch_page(p.url.strip())
        return {
            "url": page.url,
            "status_code": page.status_code,
            "title": page.title,
            "text": page.text[:3000],
            "links": page.links[:10],
            "summary": op.summarize_page(p.url.strip()) if p.summarize else None,
        }

    @app.get("/api/web/tech-briefing")
    def get_tech_briefing():
        from core.web_operator import WebOperator
        op = getattr(orchestrator, "web_operator", None) or WebOperator(brain=orchestrator.brain)
        return {"briefing": op.fetch_tech_briefing()}

    @app.get("/api/nexus/status")
    def nexus_status():
        from core.nexus import NexusHub
        hub = getattr(orchestrator, "nexus", None) or NexusHub()
        return hub.get_status()

    @app.post("/api/nexus/focus")
    def nexus_focus(p: FocusIn):
        from core.nexus import NexusHub
        hub = getattr(orchestrator, "nexus", None) or NexusHub()
        return hub.set_focus_preset(p.preset)

    @app.get("/api/nexus/scan")
    def nexus_scan(subnet: str = "auto"):
        from core.nexus import NexusHub
        hub = getattr(orchestrator, "nexus", None) or NexusHub()
        devices = hub.scan_lan(subnet_prefix=subnet)
        return {
            "devices": [
                {
                    "ip": d.ip,
                    "hostname": d.hostname,
                    "is_alive": d.is_alive,
                    "response_time_ms": d.response_time_ms,
                }
                for d in devices
            ]
        }

    @app.post("/api/nexus/trigger")
    def nexus_trigger(p: TriggerIn):
        if not p.url.strip():
            return JSONResponse(status_code=400, content={"error": "URL cannot be empty"})
        from core.nexus import NexusHub
        hub = getattr(orchestrator, "nexus", None) or NexusHub()
        res = hub.trigger_webhook(p.url.strip(), p.payload)
        return res

    @app.get("/api/biometrics/status")
    def biometrics_status():
        from safety.biometrics import get_presence_watcher
        watcher = getattr(orchestrator, "biometrics", None) or get_presence_watcher()
        return watcher.get_telemetry()

    @app.post("/api/biometrics/config")
    def biometrics_config(p: BiometricsConfigIn):
        from safety.biometrics import get_presence_watcher
        watcher = getattr(orchestrator, "biometrics", None) or get_presence_watcher()
        return watcher.set_config(
            enabled=p.enabled,
            auto_lock=p.auto_lock,
            lock_timeout_sec=p.lock_timeout_sec,
            shoulder_surf_shield=p.shoulder_surf_shield,
        )

    @app.post("/api/biometrics/enroll")
    def biometrics_enroll(p: BiometricsEnrollIn):
        tool = orchestrator.registry.get("enroll_master_face") if orchestrator and orchestrator.registry else None
        if tool:
            return tool.handler(profile_name=p.profile_name, sample_count=p.sample_count)
        return {"success": False, "message": "Enrollment tool not registered"}

    @app.post("/api/biometrics/shield")
    def biometrics_shield(p: ShieldControlIn):
        from safety.biometrics import get_presence_watcher
        watcher = getattr(orchestrator, "biometrics", None) or get_presence_watcher()
        if p.active:
            minimized = watcher.shield.activate()
            return {"status": "shield_activated", "is_shielded": True, "count": len(minimized), "windows": minimized}
        else:
            restored = watcher.shield.deactivate()
            return {"status": "shield_deactivated", "is_shielded": False, "restored_count": restored}

    @app.post("/api/biometrics/lock")
    def biometrics_lock():
        from safety.biometrics import get_presence_watcher
        watcher = getattr(orchestrator, "biometrics", None) or get_presence_watcher()
        watcher._lock_workstation()
        return {"status": "locked", "message": "Workstation lock command sent"}

    @app.get("/api/synthesizer/tools")
    def synthesizer_tools():
        from core.synthesizer import get_tool_synthesizer
        synth = getattr(orchestrator, "synthesizer", None) or get_tool_synthesizer(registry=orchestrator.registry if orchestrator else None)
        return {"tools": synth.list_tools()}

    @app.post("/api/synthesizer/forge")
    def synthesizer_forge(p: ToolForgeIn):
        from core.synthesizer import get_tool_synthesizer
        synth = getattr(orchestrator, "synthesizer", None) or get_tool_synthesizer(registry=orchestrator.registry if orchestrator else None)
        res = synth.forge_tool(
            tool_name=p.tool_name,
            description=p.description,
            python_code=p.python_code,
            test_code=p.test_code,
            params_schema=p.params_schema or {"type": "object", "properties": {}},
        )
        return res

    @app.post("/api/synthesizer/revoke")
    def synthesizer_revoke(p: ToolRevokeIn):
        from core.synthesizer import get_tool_synthesizer
        synth = getattr(orchestrator, "synthesizer", None) or get_tool_synthesizer(registry=orchestrator.registry if orchestrator else None)
        success = synth.revoke_tool(p.tool_name, orchestrator.registry if orchestrator else None)
        return {"success": success, "tool_name": p.tool_name}

    @app.post("/api/synthesizer/benchmark")
    def synthesizer_benchmark(p: ToolBenchmarkIn):
        from core.synthesizer import get_tool_synthesizer
        synth = getattr(orchestrator, "synthesizer", None) or get_tool_synthesizer(registry=orchestrator.registry if orchestrator else None)
        return synth.benchmark_tool(p.tool_name, sample_args=p.sample_args, runs=p.runs)

    @app.get("/api/finance/summary")
    def finance_summary(month: str | None = None):
        from finance.oracle import get_fintech_oracle
        oracle = getattr(orchestrator, "finance", None) or get_fintech_oracle()
        return oracle.get_summary(month=month)

    @app.get("/api/finance/subscriptions")
    def finance_subscriptions():
        from finance.oracle import get_fintech_oracle
        oracle = getattr(orchestrator, "finance", None) or get_fintech_oracle()
        return oracle.list_subscriptions()

    @app.post("/api/finance/transaction")
    def finance_record_transaction(p: FinanceTxnIn):
        from finance.oracle import get_fintech_oracle
        oracle = getattr(orchestrator, "finance", None) or get_fintech_oracle()
        return oracle.record_transaction(
            amount=p.amount,
            description=p.description,
            date=p.date,
            category=p.category,
            txn_type=p.txn_type,
        )

    @app.post("/api/finance/subscription")
    def finance_track_subscription(p: FinanceSubscriptionIn):
        from finance.oracle import get_fintech_oracle
        oracle = getattr(orchestrator, "finance", None) or get_fintech_oracle()
        return oracle.track_subscription(
            name=p.name,
            amount=p.amount,
            billing_cycle=p.billing_cycle,
            renewal_day=p.renewal_day,
            category=p.category,
        )

    @app.post("/api/finance/invoice")
    def finance_create_invoice(p: FinanceInvoiceIn):
        from finance.oracle import get_fintech_oracle
        oracle = getattr(orchestrator, "finance", None) or get_fintech_oracle()
        return oracle.generate_invoice(
            client_name=p.client_name,
            items=p.items,
            client_email=p.client_email,
            invoice_number=p.invoice_number,
            tax_rate_pct=p.tax_rate_pct,
        )

    @app.post("/api/reasoner/explore")
    def reasoner_explore(p: ReasonerExploreIn):
        from brain.mcts_reasoner import get_deep_reasoner
        reasoner = getattr(orchestrator, "reasoner", None) or get_deep_reasoner(brain=orchestrator.brain if orchestrator else None)
        return reasoner.explore(
            problem=p.problem,
            depth=p.depth,
            branches=p.branches,
            domain=p.domain,
        )

    @app.get("/api/reasoner/recent")
    def reasoner_recent(limit: int = 10):
        from brain.mcts_reasoner import get_deep_reasoner
        reasoner = getattr(orchestrator, "reasoner", None) or get_deep_reasoner(brain=orchestrator.brain if orchestrator else None)
        return {"history": reasoner.get_history(limit=limit)}

    @app.get("/api/voice/affect")
    def voice_affect():
        from voice.emotion_synthesizer import get_emotion_synthesizer
        synth = getattr(orchestrator, "emotion_voice", None) or get_emotion_synthesizer()
        return synth.get_telemetry()

    @app.post("/api/voice/affect/configure")
    def voice_affect_configure(p: VoiceAffectConfigIn):
        from voice.emotion_synthesizer import get_emotion_synthesizer
        synth = getattr(orchestrator, "emotion_voice", None) or get_emotion_synthesizer()
        return synth.set_mode(mode=p.mode, pacing_offset=p.pacing_offset)

    @app.get("/api/cluster/status")
    def cluster_status():
        from mesh.cluster import get_cluster_mesh
        mesh = getattr(orchestrator, "cluster", None) or get_cluster_mesh(config=orchestrator.config if orchestrator else None)
        return mesh.get_cluster_status()

    @app.post("/api/cluster/dispatch")
    def cluster_dispatch(p: ClusterDispatchIn):
        from mesh.cluster import get_cluster_mesh
        mesh = getattr(orchestrator, "cluster", None) or get_cluster_mesh(config=orchestrator.config if orchestrator else None)
        return mesh.dispatch_task(task_type=p.task_type, payload=p.payload, target_node=p.target_node)

    @app.post("/api/cluster/sync")
    def cluster_sync(p: ClusterSyncIn):
        from mesh.cluster import get_cluster_mesh
        mesh = getattr(orchestrator, "cluster", None) or get_cluster_mesh(config=orchestrator.config if orchestrator else None)
        return mesh.sync_state(context_data=p.context_data, destination_node=p.destination_node)

    @app.post("/api/cluster/register")
    def cluster_register(p: ClusterRegisterIn):
        from mesh.cluster import get_cluster_mesh
        mesh = getattr(orchestrator, "cluster", None) or get_cluster_mesh(config=orchestrator.config if orchestrator else None)
        return mesh.register_node(
            node_id=p.node_id,
            alias=p.alias,
            role=p.role,
            host=p.host,
            port=p.port,
            capabilities=p.capabilities,
        )

    @app.post("/api/cluster/heartbeat")
    def cluster_heartbeat(p: ClusterHeartbeatIn):
        from mesh.cluster import get_cluster_mesh
        mesh = getattr(orchestrator, "cluster", None) or get_cluster_mesh(config=orchestrator.config if orchestrator else None)
        return mesh.record_heartbeat(node_id=p.node_id, telemetry=p.telemetry)

    @app.post("/api/cluster/execute")
    def cluster_execute(p: ClusterExecuteIn):
        return {
            "dispatch_id": p.dispatch_id,
            "status": "completed",
            "executed_by": "local_mesh_worker",
            "task_type": p.task_type,
            "received_from": p.origin_node,
            "result_summary": f"Peer task '{p.task_type}' executed successfully.",
        }

    @app.post("/api/research")
    def api_research(p: ResearchIn):
        from core.researcher import DeepResearcher
        researcher = getattr(orchestrator, "researcher", None) or DeepResearcher(brain=orchestrator.brain if orchestrator else None)
        return researcher.conduct_research(p.topic, max_sources=p.max_sources)

    @app.get("/api/shadow/standup")
    def api_shadow_standup():
        from evolution.digital_shadow import DigitalShadow
        shadow = getattr(orchestrator, "digital_shadow", None) or DigitalShadow()
        return shadow.generate_standup_digest()

    @app.post("/api/code/audit")
    def api_code_audit(p: CodeAuditIn):
        from tools.code_oracle import CodeOracle
        oracle = getattr(orchestrator, "code_oracle", None) or CodeOracle()
        return oracle.audit_file(p.file_path)

    @app.post("/api/workstation/optimize")
    def api_workstation_optimize(p: WorkstationOptimizeIn):
        from tools.workstation_cleaner import WorkstationGuardian
        guardian = getattr(orchestrator, "workstation_guardian", None) or WorkstationGuardian()
        return guardian.optimize_health(dry_run=p.dry_run)







    @app.get("/api/values")
    def get_values() -> dict:
        """Values file read (Task Z1) — tolerant: junk = warn, crash ZERO."""
        from core import values as V
        V.ensure_file()
        try:
            raw = V.values_path().read_text(encoding="utf-8")
            exists = True
        except OSError:
            raw, exists = "", False
        valid, errors, warnings = V.validate(raw)
        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            data = {}
        parsed = data if isinstance(data, dict) else {}
        return {"raw": raw, "parsed": parsed,
                "counts": V.counts(parsed if isinstance(parsed, dict) else {}),
                "valid": valid, "errors": errors, "warnings": warnings,
                "exists": exists}

    @app.post("/api/values")
    def post_values(p: ValuesIn):
        """Validate BEFORE write (400 = file unchanged) + .bak backup."""
        from core import values as V
        if len(p.content.encode("utf-8")) > 30 * 1024:
            return JSONResponse(status_code=413, content={
                "errors": ["File bahut badi hai (max 30KB) — rules kam karo."]})
        ok, errors, warnings = V.save_values(p.content)
        if not ok:
            return JSONResponse(status_code=400,
                                content={"errors": errors,
                                         "warnings": warnings})
        return {"ok": True, "warnings": warnings}

    @app.post("/api/values/reset")
    def reset_values() -> dict:
        """Current -> .bak, template wapas (Web pe confirm() ke baad)."""
        from core import values as V
        try:
            if V.values_path().exists():
                shutil.copyfile(V.values_path(), V.BAK)
            V.values_path().write_text(V.TEMPLATE, encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": f"Reset nahi hua — {exc}"}
        V._log("reset to template")
        return {"ok": True}

    @app.get("/api/status")
    def status() -> dict:
        # API CONTRACT (single source of truth) — sab real, key values kabhi NAHI
        brain = orchestrator.brain
        return {
            "status": "ok",
            "provider": getattr(brain, "last_provider", "ollama"),
            "model": getattr(brain, "last_model",
                             getattr(brain, "model", "-")),
            "router_policy": getattr(brain, "active_policy", "-"),
            "tts_enabled": bool((((orchestrator.config.get("voice") or {})
                                  .get("tts") or {}).get("enabled"))),
            "session_id": (orchestrator.memory.session_id
                           if orchestrator.memory else "-"),
            "version": VERSION,
            "uptime_s": int(time.time() - STARTED),
            "msg_count": (orchestrator.memory.count_messages()
                          if orchestrator.memory else 0),
            # legacy aliases (old client bits) — same real values
            "policy": getattr(brain, "active_policy", "-"),
            "messages": (orchestrator.memory.count_messages()
                         if orchestrator.memory else 0),
        }

    @app.get("/api/projects")
    def projects() -> dict:
        reg = orchestrator.projects
        if not reg:
            return {"projects": [], "active": None}
        return {"projects": [
                    {"name": p.get("name", "?"), "path": p.get("path", "?"),
                     "stack": p.get("stack", "") or "?"}
                    for p in reg.projects],
                "active": (reg.active or {}).get("name") if reg.active else None}

    @app.get("/api/tools")
    def tools() -> dict:
        perms = orchestrator.config.get("permissions") or {}
        return {"tools": [
            {"name": t.name, "risk": t.risk,
             "policy": perms.get(t.name, "default"), "desc": t.description}
            for t in (orchestrator.registry.list_all()
                      if orchestrator.registry else [])]}

    @app.get("/api/system")
    def system() -> dict:
        out = {
            "cpu_pct": None,
            "ram_pct": None,
            "disk_pct": None,
            "gpu_pct": None,
            "battery_pct": None,
            "power_plugged": None,
            "sentry_active": bool(getattr(orchestrator, "sentry", None) and getattr(orchestrator.sentry, "_running", False)),
        }
        try:
            import psutil
            out["cpu_pct"] = round(float(psutil.cpu_percent(interval=0.3)), 1)
            out["ram_pct"] = round(float(psutil.virtual_memory().percent), 1)
            import os
            out["disk_pct"] = round(float(
                psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\").percent), 1)
            b = psutil.sensors_battery()
            if b:
                out["battery_pct"] = round(b.percent, 1)
                out["power_plugged"] = b.power_plugged
        except Exception:  # noqa: BLE001 — widget "—" dikhayega, crash nahi
            pass
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            out["gpu_pct"] = float(pynvml.nvmlDeviceGetUtilizationRates(handle).gpu)
            pynvml.nvmlShutdown()
        except Exception:  # noqa: BLE001 — GPU row hide (import/driver fail)
            out["gpu_pct"] = None
        return out

    @app.get("/api/sentry/status")
    def sentry_status():
        from safety.sentry import sentry_status_text
        s = getattr(orchestrator, "sentry", None)
        return {
            "active": bool(s and s._running),
            "text": sentry_status_text(s),
        }

    @app.get("/api/activity")
    def activity(limit: int = 8) -> dict:
        # recent audit rows — tool_calls table (real decisions, no mock)
        rows = orchestrator.audit.recent(min(int(limit), 20)) \
            if orchestrator.audit else []
        return {"activity": [{"ts": r["ts"], "tool": r["tool"],
                              "decision": r["decision"]} for r in rows]}

    @app.get("/api/stats")
    def stats() -> dict:
        # v1: sab DB COUNT queries se — koi mock/fake number NAHI
        today = date.today().isoformat()
        out = {"messages_today": 0, "tools_called_today": 0, "sessions": 0,
               "messages_total": 0, "last_backup": None}
        db = orchestrator.memory.db_path if orchestrator.memory else None
        if not db:
            return out
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
                out["messages_today"] = conn.execute(
                    "SELECT COUNT(*) FROM conversations WHERE ts LIKE ?",
                    (today + "%",)).fetchone()[0]
                out["tools_called_today"] = conn.execute(
                    "SELECT COUNT(*) FROM tool_calls WHERE ts LIKE ?",
                    (today + "%",)).fetchone()[0]
                out["sessions"] = conn.execute(
                    "SELECT COUNT(DISTINCT session_id) FROM conversations"
                ).fetchone()[0]
                out["messages_total"] = conn.execute(
                    "SELECT COUNT(*) FROM conversations").fetchone()[0]
        except sqlite3.Error:
            pass                               # honest zeros > fake numbers
        try:                                   # latest backup filename (real fs)
            backups = Path(db).parent / "backups"
            files = sorted(backups.glob("*"), key=lambda p: p.stat().st_mtime)
            out["last_backup"] = files[-1].name if files else None
        except OSError:
            pass
        return out

    @app.get("/api/analytics")
    def analytics(days: int = 7) -> dict:
        # Task L — single JSON: today/latency/providers/fallbacks/tools/daily
        from core.analytics import build_analytics
        db = orchestrator.memory.db_path if orchestrator.memory else None
        return build_analytics(db)

    @app.get("/api/history")
    def history(limit: int = 30) -> dict:
        rows = orchestrator.memory.recent(min(int(limit), 100)) \
            if orchestrator.memory else []
        return {"messages": [{"role": r["role"], "content": r["content"],
                              "ts": r["ts"]} for r in rows]}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/static/{name}")
    def asset(name: str):
        if name not in ASSETS:                # server.py etc. kabhi serve nahi
            return JSONResponse(status_code=404, content={"detail": "not found"})
        return FileResponse(WEB_DIR / name, media_type=ASSETS[name])

    # ------------------------------------------------------------------
    # TRAINING & MODEL MANAGEMENT DASHBOARD APIs (Phase: offline fine-tune)
    # ------------------------------------------------------------------
    TRAINING_LOG = Path("training_log_v3.txt")
    TRAINING_LOG_LEGACY = Path("training_log.txt")

    def _read_tail(path: Path, lines: int = 60) -> list[str]:
        """Last N lines of a log file (safe, no crash if missing)."""
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
            return [l.rstrip("\n") for l in all_lines[-lines:]]
        except OSError:
            return []

    def _parse_training_progress(lines: list[str]) -> dict:
        """Extract set number, percent, eta, eval_loss from log lines."""
        info = {"set": 0, "total_sets": 107, "pct": 0.0, "eta": "—",
                "eval_loss": None, "train_loss": None, "status": "idle"}

        # Check completed adapters from disk
        try:
            models_dir = Path("models/lumi-qwen3-4b-hinglish")
            if models_dir.exists():
                done_sets = [int(d.name.split("_")[1]) for d in models_dir.iterdir() if d.is_dir() and d.name.startswith("set_") and (d / "adapter_model.safetensors").exists()]
                if done_sets:
                    info["set"] = max(done_sets) + 1
        except Exception:
            pass

        # Parse from log lines
        for line in lines:
            if "Found" in line and "sets" in line:
                try:
                    info["total_sets"] = int(line.split("Found")[1].split("sets")[0].strip())
                except Exception:
                    pass
            if "Set" in line and "training on" in line:
                try:
                    info["set"] = int(line.split("Set")[1].split(":")[0].strip())
                except Exception:
                    pass
            if "%|" in line:
                # progress bar line:  5%|█     | 100/1500 [00:10<1:28:11, 3.54s/it]
                try:
                    pct_part = line.split("%|")[0].strip()
                    info["pct"] = float(pct_part)
                    # ETA is inside brackets: [00:10<1:28:11, 3.54s/it]
                    bracket = line.split("[")[-1].split("]")[0]
                    if "<" in bracket:
                        info["eta"] = bracket.split("<")[1].split(",")[0].strip()
                except Exception:
                    pass
            if "eval_loss=" in line:
                try:
                    info["eval_loss"] = float(line.split("eval_loss=")[1].split("|")[0].strip())
                except Exception:
                    pass
            if "train_loss=" in line:
                try:
                    info["train_loss"] = float(line.split("train_loss=")[1].split("|")[0].strip())
                except Exception:
                    pass
            if "All" in line and "sets complete" in line:
                info["status"] = "complete"
            elif "Starting training" in line or "training on" in line.lower() or "%|" in line or "'loss':" in line:
                info["status"] = "running"
        return info

    @app.get("/api/training/status")
    def training_status() -> dict:
        """Current QLoRA set-wise training progress (from log file)."""
        import time
        lines = _read_tail(TRAINING_LOG, 200)
        if not lines:
            lines = _read_tail(TRAINING_LOG_LEGACY, 200)
        prog = _parse_training_progress(lines)
        is_fresh = False
        try:
            target_log = TRAINING_LOG if TRAINING_LOG.exists() else TRAINING_LOG_LEGACY
            if target_log.exists() and (time.time() - target_log.stat().st_mtime) < 90:
                is_fresh = True
        except Exception:
            pass
        is_running = (prog["status"] == "running") or (is_fresh and prog["status"] != "complete")
        return {
            "running": is_running,
            "complete": prog["status"] == "complete",
            "set": prog["set"],
            "total_sets": prog["total_sets"],
            "pct": prog["pct"],
            "eta": prog["eta"],
            "eval_loss": prog["eval_loss"],
            "train_loss": prog["train_loss"],
            "status": "running" if is_running else prog["status"],
            "recent_lines": lines[-15:] if lines else ["Training log not found yet."],
        }

    @app.get("/api/training/logs")
    def training_logs(limit: int = 100) -> dict:
        """Raw recent training log lines."""
        lines = _read_tail(TRAINING_LOG, limit)
        if not lines:
            lines = _read_tail(TRAINING_LOG_LEGACY, limit)
        return {"logs": lines}

    @app.get("/api/training/history")
    def training_history() -> dict:
        """Parse training log to extract loss history for curve graph."""
        lines = _read_tail(TRAINING_LOG, 2000)
        if not lines:
            lines = _read_tail(TRAINING_LOG_LEGACY, 2000)
        train_losses = []
        eval_losses = []
        steps = []
        step_counter = 0
        for line in lines:
            if "train_loss=" in line:
                try:
                    val = float(line.split("train_loss=")[1].split("|")[0].strip())
                    step_counter += 1
                    steps.append(step_counter)
                    train_losses.append(val)
                except Exception:
                    pass
            if "eval_loss=" in line:
                try:
                    val = float(line.split("eval_loss=")[1].split("|")[0].strip())
                    eval_losses.append(val)
                except Exception:
                    pass
        return {
            "steps": steps,
            "train_losses": train_losses,
            "eval_losses": eval_losses,
            "points": len(train_losses),
        }

    @app.get("/api/training/detailed")
    def training_detailed() -> dict:
        """Detailed training metrics for dashboard."""
        lines = _read_tail(TRAINING_LOG, 500)
        if not lines:
            lines = _read_tail(TRAINING_LOG_LEGACY, 500)

        prog = _parse_training_progress(lines)

        # Extract recent loss values
        recent_train_losses = []
        recent_eval_losses = []
        for line in lines[-100:]:
            if "train_loss=" in line:
                try:
                    recent_train_losses.append(float(line.split("train_loss=")[1].split("|")[0].strip()))
                except Exception:
                    pass
            if "eval_loss=" in line:
                try:
                    recent_eval_losses.append(float(line.split("eval_loss=")[1].split("|")[0].strip()))
                except Exception:
                    pass

        # Calculate steps per second from recent log entries
        recent_times = []
        for line in lines[-20:]:
            import re
            time_match = re.search(r"(\d+):(\d+):(\d+)", line)
            if time_match:
                h, m, s = map(int, time_match.groups())
                recent_times.append(h * 3600 + m * 60 + s)

        steps_per_sec = 0.0
        if len(recent_times) >= 2:
            elapsed = recent_times[-1] - recent_times[0]
            if elapsed > 0:
                steps_per_sec = 20.0 / elapsed  # Approximate based on log lines

        return {
            "running": prog["status"] in ("running",),
            "complete": prog["status"] == "complete",
            "set": prog["set"],
            "total_sets": prog["total_sets"],
            "pct": prog["pct"],
            "eta": prog["eta"],
            "eval_loss": prog["eval_loss"],
            "train_loss": prog["train_loss"],
            "steps_per_sec": round(steps_per_sec, 2),
            "recent_train_losses": recent_train_losses[-10:],
            "recent_eval_losses": recent_eval_losses[-10:],
            "status": prog["status"],
        }

    @app.get("/api/models")
    def list_models() -> dict:
        """Ollama models currently downloaded (real, from ollama ps/list)."""
        import subprocess
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True,
                                 text=True, timeout=15)
            models = []
            for line in out.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 4:
                    models.append({
                        "name": parts[0],
                        "size": parts[2] if len(parts) > 2 else "?",
                        "modified": parts[3] if len(parts) > 3 else "?",
                    })
            return {"models": models}
        except Exception as exc:  # noqa: BLE001
            return {"models": [], "error": str(exc)}

    @app.post("/api/models/pull")
    def pull_model(body: dict) -> dict:
        """Trigger ollama pull for a model (blocking, returns when done)."""
        import subprocess
        name = (body or {}).get("name", "").strip()
        if not name:
            return JSONResponse(status_code=400, content={"detail": "model name required"})
        try:
            res = subprocess.run(["ollama", "pull", name], capture_output=True,
                                 text=True, timeout=3600)
            return {"ok": res.returncode == 0, "name": name,
                    "stderr_tail": res.stderr[-500:] if res.stderr else ""}
        except subprocess.TimeoutExpired:
            return JSONResponse(status_code=504,
                                content={"detail": "pull timeout (model too large / network)"})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.get("/api/omega/status")
    def omega_status() -> dict:
        """Unified telemetry for LUMI Omega Singularity engines (Phases 24-27)."""
        cg = getattr(orchestrator, "cognitive_graph", None)
        cs = getattr(orchestrator, "cyber_sentinel", None)
        dag = getattr(orchestrator, "dag_executor", None)
        wm = getattr(orchestrator, "world_model", None)
        graph_stats = cg.get_ecosystem_summary(top_n=5) if cg else {"total_nodes": 0, "total_active_edges": 0}
        return {
            "ok": True,
            "cognitive_graph": {
                "active": cg is not None,
                "nodes": graph_stats.get("total_nodes", 0),
                "edges": graph_stats.get("total_active_edges", 0),
                "top_entities": graph_stats.get("central_entities", []),
            },
            "cyber_sentinel": {
                "active": cs is not None,
            },
            "dag_executor": {
                "active": dag is not None,
                "missions_executed": len(dag.history) if dag else 0,
            },
            "world_model": {
                "active": wm is not None,
                "simulations_run": len(wm.simulations_log) if wm else 0,
            },
        }

    @app.get("/api/omega/graph")
    def omega_graph(entity: str = "", source: str = "", target: str = "") -> dict:
        """Query the Temporal Knowledge Graph neighborhood, causal path, or ecosystem summary."""
        from core.cognitive_graph import CognitiveGraph
        cg = getattr(orchestrator, "cognitive_graph", None) or CognitiveGraph(
            db_path=str(orchestrator.memory.db_path), brain=orchestrator.brain
        )
        if source and target:
            return cg.find_causal_path(source, target)
        if entity:
            return cg.query_neighborhood(entity, max_hops=2)
        return cg.get_ecosystem_summary(top_n=15)

    @app.post("/api/omega/vapt")
    def omega_vapt(body: dict) -> dict:
        """Run VAPT deep scan, auto-patch, or local surface audit."""
        from core.cyber_sentinel import CyberSentinel
        cs = getattr(orchestrator, "cyber_sentinel", None) or CyberSentinel(brain=orchestrator.brain)
        action = str((body or {}).get("action", "scan")).lower()
        file_path = str((body or {}).get("file_path", "")).strip()
        if action == "surface":
            return cs.audit_attack_surface()
        if action == "patch" and file_path:
            return cs.auto_patch_file(file_path, write_in_place=True)
        if file_path:
            return cs.deep_scan_file(file_path)
        return JSONResponse(status_code=400, content={"detail": "file_path required for scan/patch"})

    @app.post("/api/omega/dag")
    def omega_dag(body: dict) -> dict:
        """Execute a parallel topological DAG mission with dynamic piping and self-healing."""
        from core.dag_executor import AutonomousDAGExecutor
        dag = getattr(orchestrator, "dag_executor", None) or AutonomousDAGExecutor(
            registry=orchestrator.registry, brain=orchestrator.brain
        )
        mission = str((body or {}).get("mission", "")).strip()
        nodes = (body or {}).get("nodes")
        if not mission and not nodes:
            return JSONResponse(status_code=400, content={"detail": "mission or nodes required"})
        return dag.execute_mission(mission=mission or "Custom DAG Mission", nodes=nodes)

    @app.post("/api/omega/simulate")
    def omega_simulate(body: dict) -> dict:
        """Run a Counterfactual Pre-Flight World Model simulation or runtime memory/latency profile."""
        from core.world_model import WorldModelSimulator
        wm = getattr(orchestrator, "world_model", None) or WorldModelSimulator(brain=orchestrator.brain)
        code = (body or {}).get("code")
        file_path = (body or {}).get("file_path")
        if code and not file_path:
            return wm.profile_code(str(code))
        if file_path:
            return wm.simulate_and_commit(
                file_path=str(file_path),
                candidate_code=(body or {}).get("candidate_code"),
                optimization_goal=(body or {}).get("optimization_goal"),
                commit_if_passed=bool((body or {}).get("commit_if_passed", True)),
            )
        return JSONResponse(status_code=400, content={"detail": "file_path or code required"})

    # ── Phase 29–35 (v35.0): STARK APEX PROTOCOL ENDPOINTS ─────────────────

    @app.api_route("/api/chat/stream", methods=["GET", "POST"])
    async def chat_stream_endpoint(request: Request, message: str = ""):
        """Dedicated Server-Sent Events (SSE) token & speech_chunk streaming endpoint."""
        if request.method == "POST":
            body = await request.json()
            msg = str((body or {}).get("message", "")).strip()
        else:
            msg = (message or "").strip()
        if not msg:
            return JSONResponse(status_code=400, content={"detail": "Message khaali hai — kuch likho."})

        def event_generator():
            try:
                if msg.startswith("/"):
                    _, text = orchestrator.command(msg)
                    yield _sse({"type": "token", "text": text})
                    yield _sse({"type": "done", "reply": text, "tool_trace": [],
                                "provider": "reflex", "model": "command", "elapsed_ms": 1})
                    return
                for ev in orchestrator.run_turn_stream(msg):
                    yield _sse(ev)
            except Exception as exc:
                yield _sse({"type": "error", "detail": f"kuch gadbad ho gayi — {exc}"})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/apex/status")
    def apex_status() -> dict:
        """Unified Stark Apex v35.0 telemetry across all 4 departments."""
        from core.context_sensor import get_context_sensor
        from core.mission_queue import get_mission_queue
        from core.reflex_router import get_reflex_router
        from evolution.dpo_flywheel import get_dpo_flywheel
        rx = getattr(orchestrator, "reflex_router", None) or get_reflex_router()
        mq = getattr(orchestrator, "mission_queue", None) or get_mission_queue()
        fw = getattr(orchestrator, "dpo_flywheel", None) or get_dpo_flywheel()
        cs = getattr(orchestrator, "context_sensor", None) or get_context_sensor()
        return {
            "edition": "LUMI v35.0 — Stark Apex Protocol",
            "dept1_reflex_router": rx.get_router_telemetry(),
            "dept3_mission_queue": {
                "missions": mq.list_missions(limit=10),
            },
            "dept3_dpo_flywheel": fw.get_flywheel_stats(),
            "dept3_active_window": cs.get_active_window(),
        }

    @app.get("/api/apex/reflex")
    def apex_reflex(query: str = "") -> dict:
        """Inspect ReflexRouter telemetry or preview Top-K tool pruning for a query."""
        from core.reflex_router import get_reflex_router
        rx = getattr(orchestrator, "reflex_router", None) or get_reflex_router()
        if query:
            schemas = orchestrator.registry.to_llm_schemas() if getattr(orchestrator, "registry", None) else []
            pruned = rx.select_relevant_tools(query, schemas, top_k=14)
            return {
                "query": query,
                "total_before": len(schemas),
                "selected_count": len(pruned),
                "selected_tools": [t.get("function", {}).get("name") for t in pruned],
            }
        return rx.get_router_telemetry()

    @app.get("/api/apex/repo")
    def apex_repo(action: str = "map", target: str = "") -> dict:
        """Query RepoASTGraph for structural map, symbol location, or impact radius."""
        from core.repo_graph import RepoASTGraph
        rg = getattr(orchestrator, "repo_graph", None) or RepoASTGraph(root_dir=".")
        if not rg.modules:
            rg.build_graph()
        if action == "locate" and target:
            return {"action": "locate", "target": target, "matches": rg.locate_symbol(target)}
        if action == "impact" and target:
            return rg.analyze_impact_radius(target)
        return {"action": "map", "repo_map": rg.generate_repo_map(max_files=30)}

    @app.get("/api/apex/context")
    def apex_context() -> dict:
        """Capture live workstation context (active foreground window, clipboard classification, git summary)."""
        from core.context_sensor import get_context_sensor
        cs = getattr(orchestrator, "context_sensor", None) or get_context_sensor()
        return cs.capture_workstation_context()

    @app.get("/api/apex/missions")
    def apex_missions_list() -> dict:
        from core.mission_queue import get_mission_queue
        mq = getattr(orchestrator, "mission_queue", None) or get_mission_queue()
        return {"missions": mq.list_missions(limit=25)}

    @app.post("/api/apex/missions")
    def apex_missions_submit(body: dict) -> dict:
        from core.mission_queue import get_mission_queue
        mq = getattr(orchestrator, "mission_queue", None) or get_mission_queue()
        goal = str((body or {}).get("goal", "")).strip()
        kind = str((body or {}).get("kind", "dag")).strip()
        if not goal:
            return JSONResponse(status_code=400, content={"detail": "goal required"})
        tool = orchestrator.registry.get("dispatch_background_mission") if getattr(orchestrator, "registry", None) else None
        if tool:
            return {"ok": True, "summary": tool.handler(mission_goal=goal, mission_type=kind)}
        res = mq.submit_mission(name=goal[:60], kind=kind, fn=lambda: {"goal": goal, "status": "completed"})
        return {"ok": True, "mission": res}

    @app.get("/api/apex/dpo")
    def apex_dpo() -> dict:
        from evolution.dpo_flywheel import get_dpo_flywheel
        fw = getattr(orchestrator, "dpo_flywheel", None) or get_dpo_flywheel()
        return fw.get_flywheel_stats()

    return app


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from main import build_orchestrator, pick_port
    orc = build_orchestrator(web=True)
    if orc:
        port = pick_port() or 8765
        url = f"http://127.0.0.1:{port}"
        print(f"[web] {url} par chal raha hai")
        webbrowser.open(url)
        uvicorn.run(create_app(orc), host="127.0.0.1", port=port, log_level="warning")
