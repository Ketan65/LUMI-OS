"""Model router — prefer_local / prefer_cloud + auto fallback + brain.log.
Logs every attempt: ts provider model ms ok/err (+ clear FALLBACK events)."""

from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

from brain.base import Brain, BrainReply

LABEL = {"local": "ollama", "cloud": "nvidia", "hermes": "hermes3", "qwen": "qwen3:8b"}   # log-friendly provider names


class ModelRouter(Brain):
    """Drop-in Brain: orchestrator ise direct brain ki tarah use karta hai."""

    def __init__(self, local: Brain, cloud: Brain | None, config: dict,
                 log_path: str = "data/logs/brain.log",
                 hermes: Brain | None = None,
                 qwen: Brain | None = None):
        self.local = local
        self.cloud = cloud                       # None = key missing / init fail
        self.hermes = hermes                     # None = lazy loaded on /model hermes
        self.qwen = qwen                         # None = lazy loaded on /model qwen
        self.config = config or {}
        rc = self.config.get("router") or {}
        self.enabled = bool(rc.get("enabled", True))
        self.policy = str(rc.get("policy", "prefer_local"))
        self.fallback_to_local = bool(rc.get("fallback_to_local", True))
        self.key_present = bool(
            os.environ.get("NVIDIA_API_KEY")
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LUMI_CLOUD_API_KEY")
        )
        self.stats = {
            "requests_total": 0,
            "fallbacks_total": 0,
            "cloud_requests": 0,
            "local_requests": 0,
        }
        self.cloud_model = str(rc.get("cloud_model", "-"))
        self._override: str | None = None        # runtime toggle from /model
        self._warned_key = False                 # print key-missing note once
        # circuit breaker — internet down = cloud turant chhod ke local (stall nahi)
        self._cb_threshold = max(2, int(rc.get("circuit_fail_threshold", 3)))
        self._cb_cooldown_s = max(10, int(rc.get("circuit_cooldown_s", 120)))
        self._cloud_fail_streak = 0
        self._cloud_down_until = 0.0             # epoch ts — iske baad cloud retry
        self._cb_announced = False               # ek baar print, phir silent
        self.last_provider, self.last_model = "ollama", str(getattr(local, "model", "-"))
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def active_policy(self) -> str:
        return self._override or self.policy

    def set_policy(self, value: str) -> str:
        """Runtime toggle: local | hermes | qwen | cloud (config untouched — in-memory only)."""
        if value in {"local", "prefer_local"}:
            self._override = "prefer_local"
            return "Local default model active (Hermes 3 8B / Ollama)."
        if value in {"hermes", "hermes3"}:
            if self.hermes is None:
                try:
                    from brain.ollama_adapter import OllamaBrain
                    h_cfg = dict(self.config)
                    h_cfg["model_name"] = "hermes3:latest"
                    self.hermes = OllamaBrain(config=h_cfg)
                except Exception as exc:
                    return f"Hermes 3 start nahi hua: {exc}"
            self._override = "hermes"
            return "Hermes 3 (8B Uncensored) active! Heavy reasoning & autonomous coding engine ready."
        if value in {"qwen", "qwen3", "qwen3:8b"}:
            if self.qwen is None:
                try:
                    from brain.ollama_adapter import OllamaBrain
                    q_cfg = dict(self.config)
                    q_cfg["model_name"] = "qwen3:8b"
                    self.qwen = OllamaBrain(config=q_cfg)
                except Exception as exc:
                    return f"Qwen3 8B start nahi hua: {exc}"
            self._override = "qwen"
            return "Qwen3 (8B Tool-Calling Powerhouse) active! Autonomous coding & tool execution ready."
        if value in {"cloud", "prefer_cloud"}:
            if not self.key_present or self.cloud is None:
                return ("NVIDIA_API_KEY set nahi hai — local chal raha hu. "
                        'setx NVIDIA_API_KEY "nvapi-XXXX" chalao, phir restart')
            self._override = "prefer_cloud"
            return f"Cloud active: NVIDIA {self.cloud_model} (local fallback ON)."
        return "Policy samjha nahi — use: /model local | /model hermes | /model qwen | /model cloud"

    def status_text(self) -> str:
        key = "yes" if self.key_present else "no"
        provs = ["local"]
        if self.hermes or self.active_policy == "hermes":
            provs.append("hermes3")
        if self.qwen or self.active_policy == "qwen":
            provs.append("qwen3:8b")
        if self.cloud:
            provs.append("nvidia")
        return (f"policy={self.active_policy} (config={self.policy})\n"
                f"providers: {', '.join(provs)}\ncloud model: {self.cloud_model}\n"
                f"NVIDIA_API_KEY present: {key}\nfallback_to_local: {self.fallback_to_local}")

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             on_token=None, temperature: float | None = None) -> BrainReply:
        if not self.enabled:                     # router off = direct local
            return self._attempt(self.local, "local", messages, tools, None,
                                 on_token, temperature)
        if self.active_policy == "hermes":
            if self.hermes is None:
                from brain.ollama_adapter import OllamaBrain
                h_cfg = dict(self.config)
                h_cfg["model_name"] = "hermes3:latest"
                self.hermes = OllamaBrain(config=h_cfg)
            fallback = self.local if self.fallback_to_local else None
            return self._attempt(self.hermes, "hermes", messages, tools, fallback,
                                 on_token, temperature)
        if self.active_policy == "qwen":
            if self.qwen is None:
                from brain.ollama_adapter import OllamaBrain
                q_cfg = dict(self.config)
                q_cfg["model_name"] = "qwen3:8b"
                self.qwen = OllamaBrain(config=q_cfg)
            fallback = self.local if self.fallback_to_local else None
            return self._attempt(self.qwen, "qwen", messages, tools, fallback,
                                 on_token, temperature)
        if self.active_policy == "prefer_cloud":
            if self.cloud is None:               # key missing → friendly + local
                if not self._warned_key:
                    print('LUMI: NVIDIA_API_KEY set nahi hai — local chal raha hu '
                          '(setx NVIDIA_API_KEY "nvapi-...")')
                    self._warned_key = True
                return self._attempt(self.local, "local", messages, tools, None,
                                     on_token, temperature)
            if time.time() < self._cloud_down_until:
                # circuit OPEN — cloud down/stalling, local pe direct jao
                if not self._cb_announced:
                    print(f"🌩️ CIRCUIT OPEN ({self._cb_cooldown_s}s) — cloud "
                          "failure streak, local model active")
                    self._cb_announced = True
                return self._attempt(self.local, "local", messages, tools, None,
                                     on_token, temperature)
            fallback = self.local if self.fallback_to_local else None
            return self._attempt(self.cloud, "cloud", messages, tools, fallback,
                                 on_token, temperature)
        # prefer_local: Ollama first, cloud fallback only if key ho
        return self._attempt(self.local, "local", messages, tools, self.cloud,
                             on_token, temperature)

    def _attempt(self, brain: Brain, provider: str, messages: list[dict],
                 tools: list[dict] | None, fallback: Brain | None,
                 on_token=None, temperature: float | None = None) -> BrainReply:
        label = LABEL[provider]
        model = str(getattr(brain, "model", "-"))
        t0 = time.time()
        emitted = 0                             # tokens already shown to user
        sink = None
        if on_token is not None:
            def sink(chunk: str) -> None:       # noqa: E306 — count before forward
                nonlocal emitted
                emitted += 1
                on_token(chunk)
        self.stats["requests_total"] += 1
        if provider == "cloud":
            self.stats["cloud_requests"] += 1
        else:
            self.stats["local_requests"] += 1

        try:
            reply = brain.chat(messages, tools=tools, on_token=sink,
                               temperature=temperature)
        except Exception as exc:  # noqa: BLE001 — any failure feeds fallback
            reason = str(exc)
            self._log(f"provider={label}", model, t0, "err", reason)
            if provider == "cloud":              # streak → circuit breaker
                self._cloud_fail_streak += 1
                if self._cloud_fail_streak >= self._cb_threshold:
                    self._cloud_down_until = time.time() + self._cb_cooldown_s
                    self._cb_announced = False   # next chat pe print hoga
                    self._log(f"CIRCUIT OPEN {self._cb_cooldown_s}s", model, t0,
                              "event", f"{self._cloud_fail_streak} consecutive failures")
            if fallback is None or emitted > 0:
                raise            # partial tokens already out — fallback = duplicate text
            # resilience event — clearly logged (cloud→local or local→cloud)
            self.stats["fallbacks_total"] += 1
            other = "cloud" if provider == "local" else "local"
            self._log(f"FALLBACK {provider}→{other}", model, t0, "event", reason)
            print(f"🔁 FALLBACK {provider}→{other}: {reason}")
            return self._attempt(fallback, other, messages, tools, None, on_token,
                                 temperature)
        if provider == "cloud":                  # success = circuit healthy
            self._cloud_fail_streak = 0
            self._cloud_down_until = 0.0
        self._log(f"provider={label}", model, t0, "ok", "chat ok")
        self.last_provider, self.last_model = label, model   # for /api/status
        if provider == "cloud":
            print("☁️ [CLOUD]")                  # visible marker for replies
        return reply

    def get_stats(self) -> dict:
        return dict(self.stats)

    def _log(self, provider_field: str, model: str, t0: float,
             status: str, note: str) -> None:
        """Append one line: ts provider model ms ok/err (or FALLBACK event)."""
        ms = int((time.time() - t0) * 1000)
        ts = datetime.now().isoformat(timespec="seconds")
        line = f"{ts} {provider_field} model={model} ms={ms} {status} {note}\n"
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass                               # logging kabhi crash nahi karega
