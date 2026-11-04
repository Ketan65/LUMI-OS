"""Direct PyTorch/Transformers Brain for LUMI.
Runs the fully merged standalone model on RTX 5060 GPU with zero external dependencies.
Supports streaming, tool execution, and the full Hinglish persona.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import Thread

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

from brain.base import Brain, BrainReply
from brain.ollama_adapter import build_system_prompt, get_dynamic_telemetry, load_config


class LocalHFBrain(Brain):
    """Direct on-device GPU inference using the merged LUMI model."""

    _model = None
    _tokenizer = None

    def __init__(self, config: dict | None = None, config_path: str = "config.yaml"):
        self.config = config or load_config(config_path)
        self.model_path = str(self.config.get("merged_model_path", "models/lumi-qwen3-4b-hinglish-merged"))
        self.system_prompt = build_system_prompt(self.config)

        llm = self.config.get("llm") or {}
        self.temperature = float(llm.get("temperature", 0.65))
        self.max_new_tokens = int(llm.get("num_predict", 1024))
        self.model = "lumi-merged-qwen3"

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._init_model()

    def _init_model(self):
        if LocalHFBrain._model is None:
            full_path = Path(self.model_path)
            if not full_path.is_absolute():
                full_path = Path.cwd() / full_path
            print(f"[brain] Loading merged LUMI model (4-bit GPU) from {full_path}...")
            from transformers import BitsAndBytesConfig
            bnb = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
            LocalHFBrain._tokenizer = AutoTokenizer.from_pretrained(
                str(full_path), trust_remote_code=True
            )
            LocalHFBrain._model = AutoModelForCausalLM.from_pretrained(
                str(full_path),
                quantization_config=bnb,
                device_map=self.device,
                trust_remote_code=True,
            )
            LocalHFBrain._model.eval()
            print("[brain] Merged LUMI model loaded (only ~1.9GB VRAM used) & ready on GPU!")

        self.tokenizer = LocalHFBrain._tokenizer
        self.model_obj = LocalHFBrain._model

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             on_token=None, temperature: float | None = None) -> BrainReply:
        # Smart Tool Filtering: Keep VRAM low (<2.5GB) and response instant (<0.5s)
        active_tools = tools
        if tools and len(tools) > 12:
            active_tools = self._filter_tools_for_query(tools, messages)

        sys_content = self.system_prompt + get_dynamic_telemetry()
        if active_tools:
            sys_content += (
                "\n\n[MANDATORY TOOL EXECUTION RULE]\n"
                "You have registered tools available. If the user asks you to perform an action, inspect, "
                "list, read, write, create, search, run code, open an app, or check anything, you MUST NEVER "
                "simulate or talk about doing it in plain text. You MUST IMMEDIATELY invoke the tool via <tool_call>.\n"
                "Example format:\n"
                "<tool_call>\n"
                '{"name": "list_files", "arguments": {"path": "workspace"}}\n'
                "</tool_call>\n"
                "Only after the tool execution result is returned to you, give your final friendly Hinglish answer."
            )

        formatted_messages = [{"role": "system", "content": sys_content}]

        # Track current turn's user query and tool chain for multi-step autonomous execution
        orig_user_txt = ""
        turn_tools: list[tuple[str, dict, str]] = []  # (name, args, result)
        pending_calls: list[tuple[str, dict]] = []

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "user":
                orig_user_txt = str(content).lower()
                turn_tools.clear()
                pending_calls.clear()
                formatted_messages.append({"role": "user", "content": str(content)})
            elif role == "assistant":
                tcs = m.get("tool_calls") or []
                if tcs:
                    tc_blocks = []
                    for tc in tcs:
                        fn = tc.get("function") or {}
                        t_name = fn.get("name") or tc.get("name") or ""
                        t_args = fn.get("arguments") if "arguments" in fn else (tc.get("args") or {})
                        if isinstance(t_args, str):
                            try:
                                t_args = json.loads(t_args)
                            except Exception:
                                t_args = {}
                        pending_calls.append((str(t_name), t_args if isinstance(t_args, dict) else {}))
                        tc_blocks.append(
                            f'<tool_call>\n{json.dumps({"name": t_name, "arguments": t_args}, ensure_ascii=False)}\n</tool_call>'
                        )
                    full_asst = (str(content) + "\n" if content else "") + "\n".join(tc_blocks)
                    formatted_messages.append({"role": "assistant", "content": full_asst})
                else:
                    formatted_messages.append({"role": "assistant", "content": str(content)})
            elif role == "tool":
                t_res = str(content)
                if pending_calls:
                    p_name, p_args = pending_calls.pop(0)
                    turn_tools.append((p_name, p_args, t_res))
                else:
                    turn_tools.append(("tool", {}, t_res))
                formatted_messages.append({"role": "tool", "content": t_res})
            elif role == "system":
                formatted_messages.append({"role": "system", "content": str(content)})

        # -------------------------------------------------------------
        # MULTI-STEP AUTONOMOUS CHAINING & SELF-HEALING (JARVIS ENGINE)
        # -------------------------------------------------------------
        chain_prefill: str | None = None
        if active_tools and formatted_messages and formatted_messages[-1].get("role") == "tool" and len(turn_tools) < 6:
            last_t_name, last_t_args, last_t_res = turn_tools[-1]
            called_names = [t[0] for t in turn_tools]
            res_low = last_t_res.lower()

            # 1. Self-Healing: Did the last tool execution fail with a code error / traceback?
            has_exec_err = (
                "[exit code: 1]" in res_low
                or "traceback (most recent call last)" in res_low
                or "syntaxerror:" in res_low
                or "nameerror:" in res_low
                or "typeerror:" in res_low
                or "zerodivisionerror:" in res_low
                or " tool error:" in res_low
            )
            if has_exec_err and called_names.count("write_file") + called_names.count("edit_file") < 3:
                formatted_messages.append({
                    "role": "user",
                    "content": (
                        f"[JARVIS AUTO-HEAL]: Tool '{last_t_name}' failed with error:\n{last_t_res[:600]}\n"
                        "Immediately fix the bug in the file using edit_file or write_file."
                    ),
                })
                chain_prefill = '<tool_call>\n{"name": "'

            # 2. Multi-step progression when previous step succeeded
            elif not has_exec_err:
                wants_read = any(w in orig_user_txt for w in ["read", "padh", "inspect"])
                wants_edit = any(w in orig_user_txt for w in ["edit", "edit_file", "badal", "fix", "modify", "patch", "replace"])
                wants_run = any(w in orig_user_txt for w in ["run", "run_command", "run_python", "chala", "test", "verify", "execute", "output"])

                # Find the target file path from earlier write_file/read_file/edit_file in this turn
                target_path = ""
                for _, t_a, _ in reversed(turn_tools):
                    if isinstance(t_a, dict) and t_a.get("path"):
                        target_path = str(t_a["path"])
                        break

                if last_t_name == "write_file" and wants_read and "read_file" not in called_names and target_path:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return BrainReply(text="", tool_calls=[{"name": "read_file", "args": {"path": target_path}}])

                if last_t_name in {"read_file", "write_file", "grep_search"} and wants_edit and "edit_file" not in called_names:
                    formatted_messages.append({
                        "role": "user",
                        "content": (
                            f"[JARVIS NEXT STEP]: Now apply the requested modification to '{target_path or 'the file'}' "
                            f"using edit_file (or write_file) for: {orig_user_txt}"
                        ),
                    })
                    chain_prefill = '<tool_call>\n{"name": "edit_file", "arguments": {' if "edit_file" in orig_user_txt else '<tool_call>\n{"name": "'

                elif last_t_name in {"write_file", "edit_file"} and wants_run and target_path.endswith(".py"):
                    # Deterministic verification run of the written/edited Python script
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return BrainReply(text="", tool_calls=[{"name": "run_command", "args": {"command": f"python {target_path}"}}])

        # If this is the final post-tool summary turn, enforce concise JARVIS delivery
        had_tool_in_turn = len(turn_tools) > 0 and chain_prefill is None
        if had_tool_in_turn:
            steps_digest = "\n".join(
                f"- Step {idx + 1}: {t_n}({json.dumps(t_a, ensure_ascii=False)}) -> {t_r[:300]}"
                for idx, (t_n, t_a, t_r) in enumerate(turn_tools)
            )
            formatted_messages.append({
                "role": "user",
                "content": (
                    f"[JARVIS EXECUTION COMPLETE]\n{steps_digest}\n\n"
                    "Give a crisp, 1-2 sentence Hinglish engineering confirmation of the exact output above. "
                    "Do NOT add generic advice, motivational lines, or off-topic questions."
                ),
            })

        temp = 0.25 if had_tool_in_turn else (self.temperature if temperature is None else float(temperature))
        max_tokens = 240 if had_tool_in_turn else self.max_new_tokens

        prompt_kwargs = {
            "conversation": formatted_messages,
            "tokenize": False,
            "add_generation_prompt": True,
        }
        if active_tools:
            prompt_kwargs["tools"] = active_tools

        try:
            prompt = self.tokenizer.apply_chat_template(**prompt_kwargs)
        except Exception:
            prompt_kwargs.pop("tools", None)
            prompt = self.tokenizer.apply_chat_template(**prompt_kwargs)

        # -------------------------------------------------------------
        # ACTION PRE-FILL: Guarantee reliable tool execution on fine-tuned models
        # -------------------------------------------------------------
        is_action = chain_prefill is not None
        if not is_action and not had_tool_in_turn and active_tools and formatted_messages and formatted_messages[-1].get("role") == "user":
            user_txt = formatted_messages[-1].get("content", "").lower()
            action_verbs = [
                "bana", "create", "make", "write", "likh", "save",
                "edit", "badal", "modify", "replace", "change",
                "list", "dikha", "show", "read", "padh", "check", "dekh",
                "delete", "remove", "hata", "mita",
                "search", "dhund", "find", "khoj", "grep",
                "run", "chala", "execute", "calculate", "compute",
                "cmd", "command", "terminal", "shell", "powershell", "pip", "npm", "test", "pytest",
                "open", "khol", "launch",
                "remember", "yaad", "recall", "bhool", "forget",
                "git", "commit", "status", "push", "pull",
                "battery", "ram", "cpu", "disk", "system", "file", "folder", "dir"
            ]
            if any(re.search(r'\b' + re.escape(v) + r'\b', user_txt) for v in action_verbs):
                is_action = True

        if is_action:
            tool_prefix = chain_prefill or '<tool_call>\n{"name": "'
            action_prompt = prompt + tool_prefix
            act_inputs = self.tokenizer(action_prompt, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                act_outputs = self.model_obj.generate(
                    **act_inputs,
                    max_new_tokens=280,
                    do_sample=False,
                )
            gen_str = self.tokenizer.decode(
                act_outputs[0][act_inputs.input_ids.shape[1]:], skip_special_tokens=False
            )
            raw_call_text = tool_prefix + gen_str
            calls = self._extract_tool_calls(raw_call_text)
            if calls:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return BrainReply(text="", tool_calls=calls)

        # Normal generation (conversational chat or post-tool response)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)

        if on_token is not None:
            streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
            gen_kwargs = {
                **inputs,
                "max_new_tokens": max_tokens,
                "do_sample": temp > 0.0,
                "temperature": max(0.01, temp),
                "top_p": 0.9,
                "repetition_penalty": 1.12,
                "streamer": streamer,
            }
            def _generate_worker():
                with torch.inference_mode():
                    self.model_obj.generate(**gen_kwargs)

            thread = Thread(target=_generate_worker)
            thread.start()

            accumulated = []
            for new_text in streamer:
                accumulated.append(new_text)
                on_token(new_text)
            thread.join()
            full_text = "".join(accumulated)
        else:
            with torch.inference_mode():
                outputs = self.model_obj.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    do_sample=temp > 0.0,
                    temperature=max(0.01, temp),
                    top_p=0.9,
                    repetition_penalty=1.12,
                )
            full_text = self.tokenizer.decode(
                outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True
            )

        calls = self._extract_tool_calls(full_text)
        clean_text = self._clean_tool_text(full_text)
        clean_text = self._strip_cringe_smalltalk(clean_text, had_tool_in_turn=had_tool_in_turn)
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return BrainReply(text=clean_text, tool_calls=calls)

    def _filter_tools_for_query(self, tools: list[dict], messages: list[dict]) -> list[dict]:
        """Intelligently keep the top most relevant tools to prevent prompt explosion and VRAM OOM."""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", "")).lower()
                break

        # Core tools that are always available for basic assistant & autonomous engineering work
        core_names = {
            "list_files", "read_file", "write_file", "edit_file", "grep_search", "search_files",
            "remember", "recall", "list_facts", "web_search",
            "run_python", "run_command", "open_app", "system_control", "execute_goal", "code_oracle_audit"
        }

        selected = []
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "").lower()
            if name in core_names:
                selected.append(t)
            elif any(w in last_user for w in [name, name.replace("_", " ")]):
                selected.append(t)
            elif name in {"set_reminder", "list_reminders"} and any(w in last_user for w in ["remind", "reminder", "alarm"]):
                selected.append(t)
            elif "crypto" in name and any(w in last_user for w in ["crypto", "matrix", "coin", "price"]):
                selected.append(t)
            elif "finance" in name or "subscription" in name or "invoice" in name:
                if any(w in last_user for w in ["money", "rupee", "rs", "kharcha", "expense", "bill", "invoice", "sub"]):
                    selected.append(t)
            elif "sentry" in name or "biometric" in name or "privacy" in name or "lock" in name:
                if any(w in last_user for w in ["sentry", "privacy", "lock", "face", "guard"]):
                    selected.append(t)
            elif "cluster" in name or "mesh" in name:
                if any(w in last_user for w in ["cluster", "node", "mesh"]):
                    selected.append(t)
            elif "screen" in name or "gui" in name:
                if any(w in last_user for w in ["screen", "click", "mouse", "gui"]):
                    selected.append(t)
            elif "project" in name or "git" in name:
                if any(w in last_user for w in ["project", "git", "repo", "branch"]):
                    selected.append(t)

        return selected[:18]

    def _extract_tool_calls(self, text: str) -> list[dict]:
        calls = []
        # 1. Match <tool_call> blocks (supporting unclosed or trailing tags)
        for chunk in re.findall(r"<tool_call>(.*?)(?:</tool_call>|$)", text, re.DOTALL):
            chunk = chunk.strip()
            idx = chunk.find("{")
            if idx != -1:
                try:
                    decoder = json.JSONDecoder()
                    obj, _ = decoder.raw_decode(chunk[idx:])
                    name = obj.get("name")
                    args = obj.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    if name:
                        calls.append({"name": name, "args": args})
                except Exception:
                    pass

        # 2. Fallback: match raw {"name": "...", "arguments": {...}} anywhere in text
        if not calls:
            idx = 0
            decoder = json.JSONDecoder()
            while True:
                found = text.find('{"name"', idx)
                if found == -1:
                    found = text.find('{"name":', idx)
                if found == -1:
                    break
                try:
                    obj, end_pos = decoder.raw_decode(text[found:])
                    name = obj.get("name")
                    args = obj.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except Exception:
                            pass
                    if name:
                        calls.append({"name": name, "args": args})
                    idx = found + end_pos
                except Exception:
                    idx = found + 7

        return calls

    def _clean_tool_text(self, text: str) -> str:
        cleaned = re.sub(r"<tool_call>.*?(?:</tool_call>|$)", "", text, flags=re.DOTALL)
        cleaned = re.sub(r'\{\s*"name"\s*:\s*"[a-zA-Z0-9_]+"\s*,\s*"arguments"\s*:\s*\{.*?\}\s*\}', "", cleaned, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _strip_cringe_smalltalk(text: str, had_tool_in_turn: bool = False) -> str:
        """Remove casual LoRA small-talk drift (e.g. weekend/cafe/movie chatter) to preserve JARVIS composure."""
        if not text:
            return text
        cringe_patterns = re.compile(
            r"(?i)("
            r"\btereko kya pata\b|\btu kya plan karta hai\b|\bweekend ke liye\b|\bnaye cafe\b|\bkisi cafe\b|"
            r"\bchai peene chal\b|\bmaggie khane\b|\bmovie dekhne\b|\bghumne chal\b|\bshaam ka kya plan\b|"
            r"\braat ka kya plan\b|\baur bata kya chal\b|\bbata na yaar\b|\bparty karne\b|\bnetflix\b|"
            r"\bkabhi kisi naye\b|\btera weekend\b|\bpriority shift kar do\b|\bkabhi kabhi focus chalta\b|"
            r"\bchill kar\b|\bbreak le le\b|\baur abhi,?\s*tere project\b|\bchalo,?\s*koi naya plan\b|"
            r"\bsab theek rahega\b|😉😎"
            r")"
        )
        sentences = re.split(r"(?<=[.!?।])\s+", text.strip())
        kept = []
        for s in sentences:
            if cringe_patterns.search(s):
                break  # Stop right where casual small-talk drift starts
            kept.append(s)
            if had_tool_in_turn and len(kept) >= 2:
                break
        res = " ".join(kept).strip()
        return res if res else text.strip()
