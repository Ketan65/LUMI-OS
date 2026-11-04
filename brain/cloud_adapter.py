"""Cloud LLM adapter — OpenAI-compatible interface supporting NVIDIA NIM, Groq, OpenRouter, and OpenAI.

Key rule: API keys are loaded ONLY from environment variables (never committed to YAML).
"""

from __future__ import annotations

import json
import os

from brain.base import Brain, BrainReply
from brain.ollama_adapter import _text_tool_call, build_system_prompt, get_dynamic_telemetry

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "env_key": "NVIDIA_API_KEY",
        "default_model": "meta/llama-3.2-11b-vision-instruct",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "env_key": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.1-70b-instruct",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
}


class CloudBrain(Brain):
    """Generic OpenAI-compatible Brain supporting multiple cloud providers."""

    def __init__(self, config: dict):
        self.config = config or {}
        rc = dict(self.config.get("router") or {})
        self.provider = str(rc.get("cloud_provider", "nvidia")).lower()
        p_info = PROVIDER_DEFAULTS.get(self.provider, PROVIDER_DEFAULTS["nvidia"])

        self.base_url = str(rc.get("cloud_base_url") or p_info["base_url"])
        self.model = str(rc.get("cloud_model") or p_info["default_model"])
        self.system_prompt = build_system_prompt(self.config)

        env_var = p_info["env_key"]
        api_key = (
            os.environ.get(env_var, "")
            or os.environ.get("LUMI_CLOUD_API_KEY", "")
            or os.environ.get("NVIDIA_API_KEY", "")
        )

        if not api_key:
            raise RuntimeError(f"Cloud API key missing ({env_var} env var set karo)")

        from openai import OpenAI
        self.client = OpenAI(base_url=self.base_url, api_key=api_key)

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             on_token=None, temperature: float | None = None) -> BrainReply:
        sys_content = self.system_prompt + get_dynamic_telemetry()
        payload = ([{"role": "system", "content": sys_content}]
                   + self._wire(list(messages)))
        kwargs: dict = {"model": self.model, "messages": payload}
        if temperature is not None:
            kwargs["temperature"] = float(temperature)
        if tools:
            kwargs["tools"] = tools

        try:
            if on_token is None:
                response = self.client.chat.completions.create(**kwargs, timeout=60)
                return self._parse(response)
            return self._stream(kwargs, on_token)
        except ConnectionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ConnectionError(friendly_cloud_error(exc, self.provider)) from None

    def _stream(self, kwargs: dict, on_token) -> BrainReply:
        """SSE delta streaming — content chunks on_token pe, tool_calls accumulate."""
        text_parts: list[str] = []
        acc: dict[int, dict] = {}
        stream = self.client.chat.completions.create(**kwargs, stream=True, timeout=60)
        for event in stream:
            if not event.choices:
                continue
            delta = event.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                text_parts.append(delta.content)
                on_token(delta.content)
            for tc in delta.tool_calls or []:
                slot = acc.setdefault(tc.index, {"name": "", "args": ""})
                if tc.function is None:
                    continue
                if tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function.arguments:
                    slot["args"] += tc.function.arguments

        calls = []
        for slot in acc.values():
            try:
                args = json.loads(slot["args"] or "{}")
            except ValueError:
                args = {"_raw": slot["args"]}
            calls.append({"name": slot["name"], "args": args})

        text = "".join(text_parts)
        if not calls and text:
            fallback = _text_tool_call(text)
            if fallback:
                calls, text = [fallback], ""
        return BrainReply(text=text, tool_calls=calls)

    @staticmethod
    def _wire(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            m = dict(m)
            tcs = []
            for tc in m.get("tool_calls") or []:
                fn = dict(tc.get("function") or {})
                if not isinstance(fn.get("arguments"), str):
                    fn["arguments"] = json.dumps(fn.get("arguments") or {})
                tcs.append({**tc, "function": fn})
            if tcs:
                m["tool_calls"] = tcs
            out.append(m)
        return out

    @staticmethod
    def _parse(response) -> BrainReply:
        choice = response.choices[0]
        msg = choice.message
        text = msg.content or ""
        calls: list[dict] = []
        for tc in msg.tool_calls or []:
            raw = tc.function.arguments or "{}"
            try:
                args = json.loads(raw)
            except ValueError:
                args = {"_raw": raw}
            calls.append({"name": tc.function.name, "args": args})
        if not calls and text:
            fallback = _text_tool_call(text)
            if fallback:
                calls, text = [fallback], ""
        return BrainReply(text=text, tool_calls=calls)


# Backward compatibility alias
NVIDIABrain = CloudBrain


def friendly_cloud_error(exc: Exception, provider: str = "cloud") -> str:
    """Map API failures to Hinglish one-liners — no stacktraces ever."""
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    p_upper = provider.upper()
    if status == 401 or "401" in text or "unauthorized" in text:
        return f"{p_upper} key galat/expired hai — API key env var check karo"
    if status == 429 or "429" in text or "rate" in text or "quota" in text:
        return f"{p_upper} quota khatam ho gaya — thodi der baad try karo"
    if "timeout" in text or "timed out" in text or "slow" in text:
        return f"{p_upper} cloud slow hai — timeout ho gaya"
    return f"{p_upper} error: {exc}"
