"""LUMI-OS 1-Second Preflight Doctor & Zero-Friction Bootstrapper.

Verifies Python version, core dependencies, workspace/data directories, local
Ollama daemon status, and optional Cloud 550B / Gemini keys before launch.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
REQUIRED_MODULES = ("yaml", "fastapi", "uvicorn", "requests", "psutil")


def check_environment() -> dict:
    py_ok = sys.version_info >= (3, 11)
    missing_pkgs: list[str] = []
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing_pkgs.append(mod)

    # Ensure required directories exist
    for folder in ("workspace", "data", "data/backups"):
        (ROOT_DIR / folder).mkdir(parents=True, exist_ok=True)

    # Check local Ollama service (<0.6s timeout)
    ollama_online = False
    ollama_models: list[str] = []
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            ollama_online = True
            ollama_models = [str(m.get("name", "")) for m in (payload.get("models") or [])]
    except Exception:
        ollama_online = False

    has_nvidia = bool(os.environ.get("NVIDIA_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_ok": py_ok,
        "missing_packages": missing_pkgs,
        "dirs_ready": True,
        "ollama_online": ollama_online,
        "ollama_models": ollama_models,
        "cloud_nvidia_configured": has_nvidia,
        "cloud_gemini_configured": has_gemini,
        "ready": py_ok and not missing_pkgs,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = check_environment()
    print("=" * 68)
    print("  LUMI-OS :: SOVEREIGN AI ENGINEER PREFLIGHT DOCTOR")
    print("=" * 68)
    print(f"  [+] Python Runtime    : v{report['python_version']} ({'OK' if report['python_ok'] else 'UPGRADE TO 3.11+'})")
    if report["missing_packages"]:
        print(f"  [!] Missing Packages  : {', '.join(report['missing_packages'])} (Run: pip install -r requirements.txt)")
    else:
        print("  [+] Core Dependencies : ALL INSTALLED (FastAPI, Uvicorn, PyYAML, Requests, Psutil)")
    print("  [+] Sandbox Folders   : workspace/ and data/ verified")

    if report["ollama_online"]:
        models_str = ", ".join(report["ollama_models"][:4]) or "No models pulled yet (run: ollama pull hermes3:latest)"
        print(f"  [+] Local GPU Brain   : ONLINE ({models_str})")
    else:
        print("  [~] Local GPU Brain   : Ollama daemon not detected on :11434 (Start Ollama or use /model cloud)")

    cloud_badges: list[str] = []
    if report["cloud_nvidia_configured"]:
        cloud_badges.append("NVIDIA NIM 550B")
    if report["cloud_gemini_configured"]:
        cloud_badges.append("Google Gemini")
    print(
        f"  [+] Cloud Escalation  : {', '.join(cloud_badges) if cloud_badges else 'Local-Only Mode (set NVIDIA_API_KEY / GEMINI_API_KEY for /model hybrid)'}"
    )
    print("=" * 68)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
