"""Vision and Screen Perception tools for LUMI — EYES.

Enables LUMI to see, analyze, and understand the user's display:
  - capture_screen: captures the desktop/active display to an image file.
  - analyze_screen: inspects the screen or an image using multimodal vision models,
                    explaining code errors, UI state, documents, and active windows.
"""

from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.registry import Tool, ToolRegistry

SCREENSHOTS_DIR = Path("data/screenshots")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
LATEST_SCREENSHOT = SCREENSHOTS_DIR / "latest.jpg"

VISION_SYSTEM_PROMPT = """You are LUMI's visual cortex — the multimodal vision system of Commander's personal AI operating system.
Your job is to analyze screenshots of Boss's desktop, code editors (VS Code), terminals, browsers, and applications.
Rules:
1. Speak in a sharp, confident, friendly tone (Hinglish or English).
2. If code, a terminal stack trace, or compiler error is visible: diagnose the root cause immediately and give the exact fix.
3. If a webpage or document is shown: summarize key highlights and main sections.
4. If a UI/app is visible: identify the application and active window context.
5. Be concise, direct, and structured (use bullet points and backticks for code)."""


def capture_screen(output_path: str | None = None) -> tuple[bool, str]:
    """Capture current monitor to disk.
    
    Returns (success, file_path_or_error_message).
    """
    target = Path(output_path) if output_path else SCREENSHOTS_DIR / f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try PIL.ImageGrab (native Windows GDI)
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if img:
            # Convert to RGB if needed (handles RGBA / palettes)
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.save(str(target), "JPEG", quality=88)
            try:
                img.save(str(LATEST_SCREENSHOT), "JPEG", quality=88)
            except Exception:
                pass
            return True, str(target)
    except Exception:
        pass

    # 2. Try mss (multi-monitor fast grab)
    try:
        import mss
        with mss.MSS() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            from PIL import Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            img.save(str(target), "JPEG", quality=88)
            try:
                img.save(str(LATEST_SCREENSHOT), "JPEG", quality=88)
            except Exception:
                pass
            return True, str(target)
    except Exception:
        pass

    # 3. Fallback: check if latest screenshot was uploaded/synced by Web HUD or user
    if LATEST_SCREENSHOT.exists():
        age_seconds = time.time() - LATEST_SCREENSHOT.stat().st_mtime
        if age_seconds < 3600:  # Fresh within the last hour
            return True, str(LATEST_SCREENSHOT)

    png_latest = SCREENSHOTS_DIR / "latest.png"
    if png_latest.exists():
        return True, str(png_latest)

    return False, (
        "Desktop screen grab unavailable in headless background context. "
        "Web HUD me '📸 SNAP SCREEN' button dabao ya active window share karo."
    )


def analyze_screen_image(image_input: str | Path | bytes, prompt: str = "") -> str:
    """Analyze an image using NVIDIA NIM multimodal vision models."""
    from PIL import Image

    # 1. Load image
    if isinstance(image_input, (str, Path)):
        img_path = Path(image_input)
        if not img_path.exists():
            return f"Error: Image file not found: {img_path}"
        try:
            img = Image.open(img_path)
            img.load()
        except Exception as exc:
            return f"Error reading image: {exc}"
    elif isinstance(image_input, bytes):
        try:
            img = Image.open(io.BytesIO(image_input))
            img.load()
        except Exception as exc:
            return f"Error decoding image bytes: {exc}"
    else:
        return "Error: Invalid image input format."

    # Convert to RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Resize if excessively large to keep latency under 3 seconds
    max_dim = 1600
    w, h = img.size
    if w > max_dim or h > max_dim:
        ratio = min(max_dim / w, max_dim / h)
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Encode to JPEG Base64
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Prepare prompt
    query = (prompt or "").strip()
    if not query:
        query = "Explain what is on the screen right now, highlight any open apps, code, terminals, or errors, and provide actionable observations."

    # 2. VISION ROUTING — cloud pehle (auto), local VLM = offline fallback
    vcfg = _vision_cfg()
    engine = str(vcfg.get("engine", "auto")).lower()
    if engine == "local":
        return _vision_local(b64_data, query, "")
    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key and engine != "cloud":
        # key missing → pehle se offline mode — local VLM direct
        return _vision_local(b64_data, query, "cloud key missing")

    cloud_err = ""
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=api_key,
                timeout=45.0,
            )

            response = client.chat.completions.create(
                model=str(vcfg.get("cloud_model",
                                   "meta/llama-3.2-11b-vision-instruct")),
                messages=[
                    {"role": "system", "content": VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": query},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_data}",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=1024,
                temperature=0.2,
            )

            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            cloud_err = "cloud returned empty response"
        except Exception as exc:  # noqa: BLE001 — fallback to local VLM
            cloud_err = str(exc)

    if engine == "cloud":
        return f"Vision processing failed: {cloud_err}"
    return _vision_local(b64_data, query, cloud_err)


def _vision_cfg() -> dict:
    """config.yaml vision block (lazy, cached) — offline mode switch."""
    if hasattr(_vision_cfg, "_cache"):
        return _vision_cfg._cache
    out: dict = {}
    try:
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            out = (yaml.safe_load(f) or {}).get("vision") or {}
    except Exception:
        out = {}
    _vision_cfg._cache = out
    return out


def _vision_local(b64_data: str, query: str, cloud_err: str) -> str:
    """Local Ollama VLM — fully offline screen understanding (no internet)."""
    local_model = str(_vision_cfg().get("local_model", "qwen2.5vl:3b"))
    try:
        import ollama
        resp = ollama.chat(
            model=local_model,
            messages=[{"role": "user",
                       "content": f"{VISION_SYSTEM_PROMPT}\n\n{query}",
                       "images": [b64_data]}],
            keep_alive=-1,  # NUMBER (string "-1" server 400 deta hai: missing duration unit)
            options={"temperature": 0.2},
        )
        text = str(((resp.get("message") or {}).get("content") or "")).strip()
        if not text:
            return "Vision (local) returned an empty response."
        note = f"[offline VLM {local_model}]" if cloud_err else ""
        return f"{note} {text}".strip()
    except Exception as exc:  # noqa: BLE001 — dono down = honest error
        return (f"Vision down — cloud error: {cloud_err or 'n/a'} | "
                f"local ({local_model}) error: {exc}")


def analyze_screen(prompt: str = "Explain what is on my screen right now", image_path: str = "") -> str:
    """Take a screenshot of the user's active display (or use provided image) and analyze it."""
    # If specific image provided
    if image_path.strip():
        p = Path(image_path.strip())
        if p.exists():
            return analyze_screen_image(p, prompt=prompt)
        return f"Error: Specified image path does not exist: {image_path}"

    # Capture active screen
    ok, path_or_err = capture_screen()
    if not ok:
        return f"Could not capture screen: {path_or_err}"

    return analyze_screen_image(path_or_err, prompt=prompt)


def register_vision_tools(registry: ToolRegistry) -> None:
    """Register screen perception and vision tools into LUMI's tool registry."""
    registry.register(
        Tool(
            name="analyze_screen",
            description=(
                "Captures and visually analyzes the user's screen or an image using multimodal AI vision. "
                "Use this whenever the user asks 'screen dekho', 'ye error samjhao', 'screen pe kya hai', "
                "'explain this diagram', or asks for help with anything visible on their display."
            ),
            params_schema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Specific question or instruction about the screen (e.g. 'what error is showing in terminal?', 'summarize this web page').",
                    },
                    "image_path": {
                        "type": "string",
                        "description": "Optional path to an existing image or screenshot to analyze instead of capturing a new one.",
                    },
                },
            },
            handler=analyze_screen,
            risk="auto",
        )
    )
