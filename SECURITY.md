# 🛡️ Security Policy & Sovereign Architecture

LUMI-OS is engineered with a **Zero-Trust, Local-First Sovereign Security Model**.

## Architectural Guardrails

| Security Layer | Mechanism | Enforcement |
| :--- | :--- | :--- |
| **Zone-Isolated File Gate** | [`safety/gate.py`](safety/gate.py) | Blocks self-modification of LUMI core, config, and databases (`BLOCK`). Restricts automated writes strictly to `./workspace/`. |
| **Dynamic Taint Tracking** | [`core/orchestrator.py`](core/orchestrator.py) | Untrusted web/external inputs taint the active turn, escalating any destructive or external tool execution to explicit human confirmation (`ASK`). |
| **Cyber-Sentinel AST VAPT** | [`core/cyber_sentinel.py`](core/cyber_sentinel.py) | Static AST taint tracking + Shannon entropy secret detection across CWE-78, CWE-89, CWE-94, CWE-327, CWE-502, and CWE-798 with CVSS v3.1 scoring. |
| **Counterfactual Shadow Sandbox** | [`core/world_model.py`](core/world_model.py) | All autonomous code mutations are tested inside an isolated shadow directory across 3 gates (AST + CWE + Pytest) before atomic commit. |
| **Loopback & CSRF Shield** | [`web/server.py`](web/server.py) | Binds strictly to `127.0.0.1:8765`. Rejects non-local `Host` headers (DNS rebinding protection) and cross-origin mutations (`403 Forbidden`). |
| **OPSEC Identity Isolation** | [`config/identity.json`](config/identity.json) | Personal profiles reside exclusively in git-ignored `config/identity.local.json`; API keys are loaded strictly from OS environment variables. |

## Reporting a Vulnerability

If you discover a security issue or bypass in the safety gate or sandbox, please open a GitHub Security Advisory or issue with reproduction steps.
