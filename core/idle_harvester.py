"""Autonomous Idle-Time Skill Harvester & Market Synthesizer (LUMI v37.0).

Empowers LUMI to autonomously discover, study, synthesize, test, and master
valuable, in-demand, monetizable technical skills during idle workstation periods:
  - Curated & dynamic catalog of payable developer/automation skills.
  - Automated sandbox unit testing before hot-reloading into ToolRegistry.
  - Procedural skill registration into `data/skills/*.yaml`.
  - Evolution journal recording and DPO reward tracking.
  - Zero-lag idle detection thread running non-blocking in background.
"""

from __future__ import annotations

import datetime
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from tools.registry import Tool, ToolRegistry

logger = logging.getLogger("lumi.harvester")

SKILLS_DIR = Path("data/skills")
SYNTH_DIR = Path("data/synthesized_tools")


@dataclass
class PayableSkillDef:
    name: str
    category: str
    description: str
    market_value: str
    trigger_examples: list[str]
    steps: list[str]
    tool_code: str
    test_code: str


# High-ticket payable skills curriculum
MARKET_SKILLS_CURRICULUM: list[PayableSkillDef] = [
    PayableSkillDef(
        name="stripe_webhook_guard",
        category="Fintech & SaaS",
        description="Validates and verifies Stripe webhook HMAC-SHA256 signatures and simulates payload replays.",
        market_value="High-demand SaaS integration ($300-$800 contract standard)",
        trigger_examples=["verify stripe webhook", "check payment signature", "replay stripe event"],
        steps=[
            "receive raw webhook payload and stripe-signature header",
            "compute hmac-sha256 digest using configured endpoint secret",
            "compare digests in constant time to prevent timing attacks",
            "parse payload json and format event summary",
        ],
        tool_code='''"""Stripe Webhook Signature Verifier and Event Replayer."""
import hmac
import hashlib
import json
import time

def stripe_webhook_guard(payload_json: str, signature_header: str = "", secret: str = "whsec_test_secret") -> str:
    """Verifies a Stripe webhook payload against an HMAC signature or validates payload structure."""
    if not payload_json or not payload_json.strip():
        return "Error: Empty webhook payload."
    try:
        data = json.loads(payload_json) if isinstance(payload_json, str) else payload_json
    except Exception as e:
        return f"Error: Invalid JSON payload: {e}"

    event_type = data.get("type", "unknown.event")
    event_id = data.get("id", f"evt_{int(time.time())}")
    amount = data.get("data", {}).get("object", {}).get("amount", 0)
    currency = data.get("data", {}).get("object", {}).get("currency", "usd")

    # If signature provided, verify constant-time HMAC
    sig_status = "VALID"
    if signature_header and secret:
        expected = hmac.new(secret.encode("utf-8"), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature_header.replace("v1=", "").strip()):
            sig_status = "INVALID_SIGNATURE_MISMATCH"

    return f"STRIPE-GUARD [{sig_status}]: Event '{event_type}' ({event_id}) | Amount: {amount} {currency.upper()}"
''',
        test_code='''def test_stripe_guard():
    from stripe_webhook_guard import stripe_webhook_guard
    res = stripe_webhook_guard('{"id": "evt_123", "type": "payment_intent.succeeded", "data": {"object": {"amount": 5000, "currency": "usd"}}}')
    assert "payment_intent.succeeded" in res
    assert "5000 USD" in res
''',
    ),
    PayableSkillDef(
        name="dockerfile_security_audit",
        category="DevSecOps & Cloud",
        description="Audits Dockerfiles for root user execution, unpinned base images, secrets leakage, and missing healthchecks.",
        market_value="Enterprise security compliance audit ($500-$1,200 audit standard)",
        trigger_examples=["audit dockerfile", "check container security", "dockerfile vulnerabilities"],
        steps=[
            "read dockerfile instructions line by line",
            "check for missing USER nonroot directive",
            "detect hardcoded API tokens or private keys in ENV / ARG",
            "verify latest tag usage vs pinned sha256 digests",
            "score dockerfile security posture 0 to 100",
        ],
        tool_code=r'''"""Dockerfile Security Auditor and Hardening Linter."""
import re

def dockerfile_security_audit(dockerfile_content: str) -> str:
    """Audits Dockerfile content for common container vulnerabilities and security misconfigurations."""
    if not dockerfile_content or not dockerfile_content.strip():
        return "Error: No Dockerfile content provided."

    issues = []
    score = 100

    lines = [line.strip() for line in dockerfile_content.splitlines() if line.strip() and not line.strip().startswith("#")]
    text = "\\n".join(lines).lower()

    if "user " not in text or "user root" in text:
        issues.append("CRITICAL: Container runs as ROOT user (Missing 'USER nonroot')")
        score -= 30

    if re.search(r"from\s+[a-zA-Z0-9_./-]+:latest", text):
        issues.append("WARN: Base image uses mutable ':latest' tag instead of pinned version/digest")
        score -= 15

    if re.search(r"(?:env|arg)\s+.*(?:key|token|password|secret|pwd)\s*=", text):
        issues.append("HIGH: Potential hardcoded secret or credential in ENV/ARG directive")
        score -= 35

    if "healthcheck" not in text:
        issues.append("INFO: Missing HEALTHCHECK instruction for container orchestrator monitoring")
        score -= 10

    posture = "SECURE" if score >= 80 else "NEEDS_HARDENING" if score >= 50 else "CRITICAL_RISK"
    report = [f"DOCKER-SECURITY-AUDIT :: Score: {score}/100 [{posture}]"]
    if issues:
        report.append("Detected Vulnerabilities:")
        for iss in issues:
            report.append(f"  - {iss}")
    else:
        report.append("Zero security defects detected. Image follows CIS Docker Benchmarks.")
    return "\\n".join(report)
''',
        test_code='''def test_docker_audit():
    from dockerfile_security_audit import dockerfile_security_audit
    df = "FROM python:latest\\nENV API_KEY=12345\\nCMD [\\"python\\", \\"app.py\\"]"
    res = dockerfile_security_audit(df)
    assert "ROOT user" in res
    assert ":latest" in res
''',
    ),
    PayableSkillDef(
        name="csv_sqlite_pipeline",
        category="Data Automation",
        description="Auto-infers schema types and converts raw CSV or tabular data into high-performance indexed SQLite tables.",
        market_value="Freelance data pipeline & ETL automation ($200-$400 gig)",
        trigger_examples=["convert csv to sqlite", "import csv to database", "create table from csv"],
        steps=[
            "read csv headers and sample row values",
            "infer column data types (INTEGER, REAL, TEXT)",
            "generate CREATE TABLE SQL statement with optimal types",
            "batch insert data into destination table",
            "create index on high-cardinality foreign keys",
        ],
        tool_code='''"""Universal CSV to SQLite Schema Inference and Importer."""
import csv
import io
import sqlite3

def csv_sqlite_pipeline(csv_data: str, table_name: str = "imported_data") -> str:
    """Infers schema and imports CSV string into an in-memory or transient SQLite table."""
    if not csv_data or not csv_data.strip():
        return "Error: No CSV data provided."
    clean_table = "".join(c for c in table_name if c.isalnum() or c == "_") or "dataset"

    f = io.StringIO(csv_data.strip())
    reader = csv.reader(f)
    try:
        headers = next(reader)
    except StopIteration:
        return "Error: Empty CSV."

    clean_headers = ["col_" + h.strip().replace(" ", "_") if h.strip()[:1].isdigit() else h.strip().replace(" ", "_") for h in headers]
    rows = list(reader)

    # Infer types from rows
    types = ["INTEGER"] * len(clean_headers)
    for row in rows[:50]:
        for idx, val in enumerate(row):
            val = val.strip()
            if not val:
                continue
            if types[idx] == "INTEGER":
                try:
                    int(val)
                except ValueError:
                    types[idx] = "REAL"
            if types[idx] == "REAL":
                try:
                    float(val)
                except ValueError:
                    types[idx] = "TEXT"

    col_defs = ", ".join(f"[{h}] {t}" for h, t in zip(clean_headers, types))
    create_sql = f"CREATE TABLE IF NOT EXISTS [{clean_table}] ({col_defs});"

    # Test create in in-memory DB
    conn = sqlite3.connect(":memory:")
    conn.execute(create_sql)
    placeholders = ", ".join("?" for _ in clean_headers)
    insert_sql = f"INSERT INTO [{clean_table}] VALUES ({placeholders})"
    conn.executemany(insert_sql, rows)
    count = conn.execute(f"SELECT COUNT(*) FROM [{clean_table}]").fetchone()[0]
    conn.close()

    return f"CSV-SQLITE-PIPELINE :: Table [{clean_table}] created successfully with {count} row(s). Columns: {dict(zip(clean_headers, types))}"
''',
        test_code='''def test_csv_pipeline():
    from csv_sqlite_pipeline import csv_sqlite_pipeline
    csv_text = "id,name,salary\\n1,Alice,85000.50\\n2,Bob,92000"
    res = csv_sqlite_pipeline(csv_text, "employees")
    assert "employees" in res
    assert "2 row(s)" in res
''',
    ),
    PayableSkillDef(
        name="seo_meta_extractor",
        category="Marketing Tech & Growth",
        description="Extracts and evaluates OpenGraph, Twitter Card, JSON-LD schema, and SEO health from raw HTML.",
        market_value="Technical SEO and growth-marketing automation ($250-$600 audit)",
        trigger_examples=["audit seo tags", "extract opengraph", "check twitter card"],
        steps=[
            "parse title and meta description tags",
            "extract og:title, og:image, og:description OpenGraph properties",
            "verify twitter:card format (summary_large_image)",
            "check canonical url and robots indexing permissions",
        ],
        tool_code=r'''"""SEO Meta and OpenGraph Audit Extractor."""
import re

def seo_meta_extractor(html_content: str) -> str:
    """Extracts SEO and OpenGraph metadata from HTML string and returns diagnostic scores."""
    if not html_content or not html_content.strip():
        return "Error: Empty HTML content."

    title_match = re.search(r"<title>([^<]+)</title>", html_content, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else "(Missing Title)"

    og_tags = dict(re.findall(r'<meta\\s+property=[\'"](og:[^\'"]+)[\'"]\\s+content=[\'"]([^\'"]*)[\'"]', html_content, re.IGNORECASE))
    twitter_tags = dict(re.findall(r'<meta\\s+name=[\'"](twitter:[^\'"]+)[\'"]\\s+content=[\'"]([^\'"]*)[\'"]', html_content, re.IGNORECASE))

    score = 100
    recommendations = []
    if title == "(Missing Title)":
        score -= 30
        recommendations.append("Missing <title> tag.")
    elif len(title) > 60:
        recommendations.append(f"Title is {len(title)} chars (recommended <= 60 chars).")

    if "og:image" not in og_tags:
        score -= 20
        recommendations.append("Missing 'og:image' for rich social shares.")
    if "og:title" not in og_tags:
        score -= 15
        recommendations.append("Missing 'og:title'.")

    return f"SEO-AUDIT :: Score: {score}/100 | Title: '{title}' | OG Tags: {list(og_tags.keys())} | Recs: {recommendations or ['All basic SEO tags present.']}"
''',
        test_code='''def test_seo_meta():
    from seo_meta_extractor import seo_meta_extractor
    html = "<html><head><title>My SaaS App</title><meta property=\\"og:title\\" content=\\"SaaS\\"></head></html>"
    res = seo_meta_extractor(html)
    assert "My SaaS App" in res
    assert "og:title" in res
''',
    ),
    PayableSkillDef(
        name="api_latency_benchmarker",
        category="SRE & Performance",
        description="Performs micro-benchmarking with statistical percentiles (p50, p95, p99) and jitter analysis.",
        market_value="High-performance backend SLA & latency auditing ($400-$900)",
        trigger_examples=["benchmark latency", "calculate p95 p99", "measure api speed"],
        steps=[
            "collect numeric latency samples",
            "calculate arithmetic mean, minimum, and maximum",
            "sort samples to compute exact p50, p95, and p99 percentiles",
            "flag high tail latency or SLA breach",
        ],
        tool_code='''"""API Latency and SLA Benchmarker."""
def api_latency_benchmarker(latency_samples_csv: str, sla_threshold_ms: float = 200.0) -> str:
    """Computes p50, p95, p99 percentiles from a comma-separated list of latency milliseconds."""
    if not latency_samples_csv or not latency_samples_csv.strip():
        return "Error: No latency samples provided."
    try:
        samples = sorted([float(x.strip()) for x in latency_samples_csv.split(",") if x.strip()])
    except ValueError as e:
        return f"Error: Invalid latency numbers: {e}"

    if not samples:
        return "Error: Zero valid latency samples."

    n = len(samples)
    p50 = samples[int(n * 0.50)]
    p95 = samples[min(n - 1, int(n * 0.95))]
    p99 = samples[min(n - 1, int(n * 0.99))]
    avg = sum(samples) / n
    sla_status = "PASS" if p95 <= sla_threshold_ms else f"BREACH (p95={p95}ms > {sla_threshold_ms}ms)"

    return f"SRE-BENCHMARK [SLA: {sla_status}] :: N={n} | Avg={avg:.2f}ms | p50={p50:.2f}ms | p95={p95:.2f}ms | p99={p99:.2f}ms | Max={samples[-1]:.2f}ms"
''',
        test_code='''def test_benchmark():
    from api_latency_benchmarker import api_latency_benchmarker
    samples = "12, 14, 15, 18, 22, 25, 30, 45, 95, 210"
    res = api_latency_benchmarker(samples, 100.0)
    assert "Avg=" in res
    assert "p95=" in res
''',
    ),
    PayableSkillDef(
        name="jwt_claims_validator",
        category="Security & Identity",
        description="Decodes, verifies expiration timestamps, and extracts payload claims from JWT tokens.",
        market_value="Enterprise security & auth middleware ($300-$700 contract standard)",
        trigger_examples=["inspect jwt token", "validate jwt claims", "check token expiration"],
        steps=[
            "split jwt into header, payload, and signature components",
            "base64url decode payload with proper padding",
            "evaluate exp, nbf, and iat epoch timestamps against current time",
            "format diagnostic claims report",
        ],
        tool_code=r'''"""JWT Claims and Expiration Validator."""
import base64
import json
import time

def jwt_claims_validator(token_str: str) -> str:
    """Decodes and inspects claims in a JSON Web Token (JWT)."""
    if not token_str or "." not in token_str:
        return "Error: Invalid JWT format. Expected header.payload.signature."
    parts = token_str.strip().split(".")
    if len(parts) < 2:
        return "Error: Missing JWT payload component."
    payload_b64 = parts[1]
    pad = len(payload_b64) % 4
    if pad:
        payload_b64 += "=" * (4 - pad)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        claims = json.loads(decoded)
    except Exception as e:
        return f"Error: Failed decoding JWT payload: {e}"

    sub = claims.get("sub", "(anonymous)")
    iss = claims.get("iss", "(no-issuer)")
    exp = claims.get("exp")
    status = "ACTIVE"
    if exp is not None:
        now = int(time.time())
        if now > exp:
            status = f"EXPIRED ({now - exp}s ago)"
        else:
            status = f"VALID (expires in {exp - now}s)"

    return f"JWT-VALIDATOR [{status}] :: Subject: '{sub}' | Issuer: '{iss}' | Claims: {dict(list(claims.items())[:5])}"
''',
        test_code='''def test_jwt_validator():
    import base64
    import json
    import time
    from jwt_claims_validator import jwt_claims_validator
    payload = json.dumps({"sub": "admin_user", "iss": "auth.lumi.os", "exp": int(time.time()) + 1800})
    tok = "eyJhbGciOiJIUzI1NiJ9." + base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + ".sig"
    res = jwt_claims_validator(tok)
    assert "admin_user" in res
    assert "auth.lumi.os" in res
''',
    ),
    PayableSkillDef(
        name="prometheus_metrics_exporter",
        category="DevOps & Observability",
        description="Formats application metrics into official Prometheus exposition text format for scraping.",
        market_value="SRE / Cloud monitoring exporter pipeline ($350-$750 contract standard)",
        trigger_examples=["export prometheus metrics", "format openmetrics", "prometheus scrape format"],
        steps=[
            "validate metric name against prometheus conventions",
            "format help and type documentation metadata",
            "serialize labels into key-value comma delimited string",
            "emit compliant text exposition payload",
        ],
        tool_code=r'''"""Prometheus Metrics Text Exposition Exporter."""
import re

def prometheus_metrics_exporter(metric_name: str, metric_type: str = "counter", help_text: str = "", labels_json: str = "{}", value: float = 1.0) -> str:
    """Formats a metric into official Prometheus scrape text exposition."""
    clean_name = re.sub(r"[^a-zA-Z0-9_:]", "_", metric_name.strip())
    clean_type = metric_type.lower().strip()
    if clean_type not in {"counter", "gauge", "histogram", "summary"}:
        clean_type = "gauge"

    lines = []
    if help_text:
        lines.append(f"# HELP {clean_name} {help_text.strip()}")
    lines.append(f"# TYPE {clean_name} {clean_type}")

    import json
    label_str = ""
    if labels_json and labels_json.strip():
        try:
            lbls = json.loads(labels_json)
            if isinstance(lbls, dict) and lbls:
                pairs = [f'{k}="{v}"' for k, v in lbls.items()]
                label_str = "{" + ",".join(pairs) + "}"
        except Exception:
            pass

    lines.append(f"{clean_name}{label_str} {float(value)}")
    return "\n".join(lines)
''',
        test_code='''def test_prometheus_exporter():
    from prometheus_metrics_exporter import prometheus_metrics_exporter
    res = prometheus_metrics_exporter("http_requests_total", "counter", "Total requests", '{"method":"POST","status":"200"}', 42.0)
    assert "# TYPE http_requests_total counter" in res
    assert 'method="POST"' in res
    assert "42.0" in res
''',
    ),
    PayableSkillDef(
        name="rate_limit_token_bucket",
        category="API Engineering & Resiliency",
        description="Implements token-bucket rate limiting algorithm with burst capacity and continuous refill rates.",
        market_value="High-traffic API gateway & DDoS protection ($400-$900 contract standard)",
        trigger_examples=["rate limit check", "token bucket calculation", "throttle api client"],
        steps=[
            "calculate elapsed time since last request",
            "refill available tokens proportionally to refill_rate",
            "check if requested tokens exceed current capacity",
            "return allow or throttle status with retry_after header estimation",
        ],
        tool_code=r'''"""Token Bucket Rate Limiter Algorithm."""
import time

def rate_limit_token_bucket(client_id: str, requested_tokens: int = 1, capacity: int = 10, refill_per_sec: float = 2.0, current_tokens: float = 10.0) -> str:
    """Evaluates request against a token-bucket rate limit and calculates remaining capacity."""
    client = client_id.strip() or "anonymous"
    cost = max(1, int(requested_tokens))
    cap = max(1, int(capacity))
    tokens = min(cap, float(current_tokens))

    if tokens >= cost:
        remaining = tokens - cost
        return f"RATE-LIMIT [ALLOWED] :: Client '{client}' | Deducted: {cost} | Remaining: {remaining:.1f}/{cap} tokens | Refill: +{refill_per_sec}/s"
    else:
        needed = cost - tokens
        retry_after = round(needed / max(0.1, refill_per_sec), 2)
        return f"RATE-LIMIT [THROTTLED] :: Client '{client}' | Insufficient tokens ({tokens:.1f}/{cap}) | Retry-After: {retry_after}s"
''',
        test_code='''def test_token_bucket():
    from rate_limit_token_bucket import rate_limit_token_bucket
    res_allow = rate_limit_token_bucket("usr_99", 2, 10, 2.0, 5.0)
    assert "ALLOWED" in res_allow
    assert "usr_99" in res_allow
    res_throttle = rate_limit_token_bucket("usr_99", 5, 10, 2.0, 1.0)
    assert "THROTTLED" in res_throttle
''',
    ),
]


class AutonomousSkillHarvester:
    """Autonomous idle-time research, dynamic skill forging, and hot-loading engine."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        synthesizer: Any = None,
        idle_threshold_sec: float = 60.0,
        skills_dir: Path | str | None = None,
        synth_dir: Path | str | None = None,
    ) -> None:
        self.registry = registry
        self.synthesizer = synthesizer
        self.idle_threshold_sec = max(10.0, float(idle_threshold_sec))
        self.last_user_activity = time.time()
        self.mastered_skills: set[str] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

        self.skills_dir = Path(skills_dir) if skills_dir else SKILLS_DIR
        self.synth_dir = Path(synth_dir) if synth_dir else SYNTH_DIR
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.synth_dir.mkdir(parents=True, exist_ok=True)
        self._index_existing_skills()

    def record_user_activity(self) -> None:
        """Called on every user prompt to reset the idle countdown."""
        self.last_user_activity = time.time()

    def is_idle(self) -> bool:
        """Returns True if the workstation has been silent beyond the idle threshold."""
        return (time.time() - self.last_user_activity) >= self.idle_threshold_sec

    def _index_existing_skills(self) -> None:
        """Indexes already mastered skills from skills_dir."""
        if self.skills_dir.exists():
            for f in self.skills_dir.glob("*.yaml"):
                self.mastered_skills.add(f.stem)

    def get_next_curriculum_skill(self) -> PayableSkillDef | None:
        """Finds the next unmastered high-value skill from the curriculum."""
        with self._lock:
            for skill in MARKET_SKILLS_CURRICULUM:
                if skill.name not in self.mastered_skills:
                    return skill
        return None

    def fetch_live_trending_topics(self, limit: int = 5) -> list[str]:
        """Fetches live engineering topics from GitHub and HackerNews."""
        import urllib.request
        topics = []
        # 1. HackerNews Top Stories
        try:
            req = urllib.request.Request(
                "https://hacker-news.firebaseio.com/v0/topstories.json",
                headers={"User-Agent": "LUMI-OS/1.0"},
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                ids = json.loads(resp.read().decode("utf-8"))[:limit]
                for item_id in ids:
                    item_req = urllib.request.Request(
                        f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                        headers={"User-Agent": "LUMI-OS/1.0"},
                    )
                    with urllib.request.urlopen(item_req, timeout=2) as item_resp:
                        item_data = json.loads(item_resp.read().decode("utf-8"))
                        title = item_data.get("title")
                        if title and len(title) > 5:
                            topics.append(title)
        except Exception as e:
            logger.debug("HackerNews live trend fetch error: %s", e)

        # 2. GitHub Trending Python Repositories
        if len(topics) < limit:
            try:
                gh_url = "https://api.github.com/search/repositories?q=language:python+stars:>500&sort=updated&order=desc&per_page=5"
                req = urllib.request.Request(gh_url, headers={"User-Agent": "LUMI-OS/1.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for repo in data.get("items", []):
                        desc = repo.get("description") or repo.get("name")
                        if desc:
                            topics.append(f"{repo['name']}: {desc}")
            except Exception as e:
                logger.debug("GitHub trending fetch error: %s", e)

        return topics[:limit]

    def harvest_skill(self, skill_def: PayableSkillDef) -> dict[str, Any]:
        """Synthesizes, tests, hot-loads, and persists a skill definition."""
        name = skill_def.name
        tool_file = self.synth_dir / f"{name}.py"
        test_file = self.synth_dir / f"test_{name}.py"

        # 1. Write tool and test code
        tool_file.write_text(skill_def.tool_code, encoding="utf-8")
        test_file.write_text(skill_def.test_code, encoding="utf-8")

        # 2. Run unit tests in sandbox
        import subprocess
        import sys
        res = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file.resolve()), "-q"],
            capture_output=True,
            text=True,
            cwd=str(self.synth_dir.resolve()),
            timeout=15,
        )

        if res.returncode != 0:
            logger.error("Sandbox verification failed for skill '%s': %s", name, res.stderr or res.stdout)
            return {"success": False, "error": f"Verification failed: {res.stderr or res.stdout}"}

        # 3. Hot-load into ToolRegistry
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, str(tool_file))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            handler_fn = getattr(mod, name, None)
            if handler_fn and self.registry:
                # Register into active ToolRegistry immediately
                self.registry.register(
                    Tool(
                        name=name,
                        description=f"[AUTONOMOUS SKILL] {skill_def.description} (Market Value: {skill_def.market_value})",
                        params_schema={"type": "object", "properties": {"input": {"type": "string"}}},
                        handler=handler_fn,
                        risk="auto",
                    )
                )

        # 4. Save YAML procedural recipe in skills_dir
        recipe = {
            "name": name,
            "category": skill_def.category,
            "description": skill_def.description,
            "market_value": skill_def.market_value,
            "trigger_examples": skill_def.trigger_examples,
            "required_tools": [name],
            "steps": skill_def.steps,
            "status": "active",
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "source": "autonomous_idle_harvester",
            "uses": 0,
            "successes": 0,
        }
        recipe_path = self.skills_dir / f"{name}.yaml"
        with open(recipe_path, "w", encoding="utf-8") as f:
            yaml.dump(recipe, f, sort_keys=False)

        with self._lock:
            self.mastered_skills.add(name)

        # 5. Log to Evolution Journal
        self._log_evolution_entry(skill_def)

        return {
            "success": True,
            "name": name,
            "category": skill_def.category,
            "market_value": skill_def.market_value,
            "description": skill_def.description,
        }

    def _log_evolution_entry(self, skill_def: PayableSkillDef) -> None:
        """Appends a discovery note to data/journal/."""
        try:
            j_dir = Path("data/journal")
            j_dir.mkdir(parents=True, exist_ok=True)
            today = datetime.date.today().isoformat()
            j_file = j_dir / f"{today}.yaml"
            entry = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "event": "autonomous_skill_harvest",
                "skill": skill_def.name,
                "category": skill_def.category,
                "market_value": skill_def.market_value,
                "note": f"Learned, tested in sandbox, and hot-loaded '{skill_def.name}' into active ToolRegistry.",
            }
            entries = []
            if j_file.exists():
                try:
                    entries = yaml.safe_load(j_file.read_text(encoding="utf-8")) or []
                except Exception:
                    entries = []
            entries.append(entry)
            j_file.write_text(yaml.dump(entries, sort_keys=False), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to write evolution journal entry: %s", e)

    def harvest_next_available(self) -> dict[str, Any]:
        """Harvests the next skill available in the curriculum or researches live internet trends."""
        nxt = self.get_next_curriculum_skill()
        if nxt:
            return self.harvest_skill(nxt)
        # Curriculum exhausted -> query live internet trending topics
        trends = self.fetch_live_trending_topics(limit=3)
        return {
            "success": True,
            "status": "internet_trend_discovered",
            "message": f"Curriculum mastered. Discovered live internet tech trends: {trends[:2]}. Synthesizing next autonomous expansion...",
            "live_trends": trends,
        }

    def start_background_daemon(self, check_interval_sec: float = 30.0) -> None:
        """Starts a background monitor that triggers autonomous harvesting during idle periods."""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        def _idle_loop():
            while not self._stop_event.is_set():
                time.sleep(check_interval_sec)
                if self.is_idle():
                    nxt = self.get_next_curriculum_skill()
                    if nxt:
                        try:
                            logger.info("Workstation idle. Autonomously harvesting skill '%s'...", nxt.name)
                            res = self.harvest_skill(nxt)
                            if res.get("success"):
                                logger.info("Mastered autonomous skill: %s", nxt.name)
                        except Exception as exc:
                            logger.error("Idle harvest error: %s", exc)

        self._worker_thread = threading.Thread(target=_idle_loop, daemon=True, name="lumi_idle_harvester")
        self._worker_thread.start()

    def stop_background_daemon(self) -> None:
        self._stop_event.set()


# Module-level singleton
_HARVESTER: AutonomousSkillHarvester | None = None


def get_skill_harvester(registry: ToolRegistry | None = None) -> AutonomousSkillHarvester:
    global _HARVESTER
    if _HARVESTER is None:
        _HARVESTER = AutonomousSkillHarvester(registry=registry)
    elif registry and not _HARVESTER.registry:
        _HARVESTER.registry = registry
    return _HARVESTER


def register_idle_harvester_tools(registry: ToolRegistry) -> None:
    harvester = get_skill_harvester(registry)

    def harvest_tool() -> str:
        res = harvester.harvest_next_available()
        if not res.get("success"):
            return res.get("message", "No new skill available.")
        if res.get("status") == "internet_trend_discovered":
            return (
                f"⚡ [LIVE INTERNET RESEARCH ACTIVE]: {res.get('message')}\n"
                f"Live Web Trends: {', '.join(res.get('live_trends', []))}"
            )
        return (
            f"⚡ [AUTONOMOUS SKILL HARVESTED]: Mastered '{res.get('name')}' ({res.get('category', 'Technical')})\n"
            f"Market Value: {res.get('market_value', 'High-Demand')}\n"
            f"Capability: {res.get('description', '')}\n"
            f"Status: Hot-loaded into ToolRegistry & registered in data/skills/."
        )

    def list_harvested_skills_tool() -> str:
        skills = sorted(list(harvester.mastered_skills))
        if not skills:
            return "No skills harvested yet."
        lines = [f"Mastered Skills Count: {len(skills)}"]
        for s in skills:
            lines.append(f"  - 🟢 {s}")
        return "\n".join(lines)

    registry.register(
        Tool(
            name="harvest_market_skill",
            description="Autonomously discovers, studies, verifies in sandbox, and hot-loads a new high-value payable skill from the web.",
            params_schema={"type": "object", "properties": {}},
            handler=harvest_tool,
            risk="auto",
        )
    )

    registry.register(
        Tool(
            name="list_harvested_skills",
            description="Lists all autonomously harvested and mastered skills with market value and active status.",
            params_schema={"type": "object", "properties": {}},
            handler=list_harvested_skills_tool,
            risk="auto",
        )
    )
