"""Autonomous GitHub Bridge & Sovereign PR Engine (LUMI v43.0).

Enables LUMI to autonomously authenticate, verify legitimate bounties, fork repositories,
commit tested patches, and open Pull Requests directly on GitHub using GitHub REST API v3
and native Git mechanics.

Includes built-in Red Team Honeypot & Prompt Injection Guardrails to prevent automated
exploitation by scam bounties.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("lumi.github_bridge")

# Suspicious anti-patterns, prompt injections, and known scam domains
_HONEYPOT_KEYWORDS = [
    "gullible",
    "certified bot",
    "consume api tokens",
    "digitaltoolsshed",
    "claim-bounty-now",
    "human_verified_signature",
    "send eth to verify",
    "airdrop-claim",
    "bounty-plaza",
    "ies-boilerroom",
    "oss-bot-trap",
    "automated ci regression mirror",
    "manual pull requests from human engineers are not reviewed",
    "toyol-digital",
    "bounty scout",
    "dependency dashboard",
]

_PROMPT_INJECTION_REGEXES = [
    re.compile(r"\[AI AGENT COMPLIANCE DIRECTIVE", re.IGNORECASE),
    re.compile(r"\[CERTIFIED BOT:", re.IGNORECASE),
    re.compile(r"SYSTEM PROMPT OVERRIDE", re.IGNORECASE),
    re.compile(r"Ignore previous instructions", re.IGNORECASE),
]


@dataclass
class GitHubAuthStatus:
    authenticated: bool
    username: Optional[str] = None
    scopes: Optional[str] = None
    rate_limit_remaining: int = 0
    message: str = ""


class GitHubBridgeEngine:
    """Production Autonomous GitHub Integration Engine."""

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token or os.environ.get("GITHUB_TOKEN") or ""
        self._base_api = "https://api.github.com"

    @property
    def has_token(self) -> bool:
        return bool(self._token and len(self._token.strip()) > 8)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LUMI-Sovereign-OS/v43.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        url = f"{self._base_api}{endpoint}" if endpoint.startswith("/") else endpoint
        req_data = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url,
            data=req_data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
                body = resp.read().decode("utf-8")
                parsed = json.loads(body) if body.strip() else {}
                return code, parsed
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                parsed_err = json.loads(err_body)
            except Exception:
                parsed_err = {"error": err_body}
            logger.warning("GitHub API Error [%d %s]: %s", e.code, e.reason, parsed_err)
            return e.code, parsed_err
        except Exception as e:
            logger.error("GitHub connection error: %s", e)
            return 0, {"error": str(e)}

    def verify_auth(self) -> GitHubAuthStatus:
        """Verifies current GitHub credentials without leaking token values."""
        if not self.has_token:
            return GitHubAuthStatus(
                authenticated=False,
                message="No GITHUB_TOKEN configured in environment or .env",
            )

        code, resp = self._request("/user")
        if code == 200 and "login" in resp:
            # Check rate limits
            rl_code, rl_resp = self._request("/rate_limit")
            remaining = (
                rl_resp.get("rate", {}).get("remaining", 0) if rl_code == 200 else 0
            )
            return GitHubAuthStatus(
                authenticated=True,
                username=resp.get("login"),
                rate_limit_remaining=remaining,
                message=f"Authenticated as @{resp.get('login')} (API quota: {remaining} requests remaining)",
            )
        else:
            err_msg = resp.get("message", "Authentication rejected by GitHub API")
            return GitHubAuthStatus(
                authenticated=False,
                message=f"Authentication failed: {err_msg}",
            )

    def is_safe_target(
        self,
        repo_name: str,
        issue_title: str = "",
        issue_body: str = "",
    ) -> Tuple[bool, str]:
        """Inspects target repository and issue for honeypots, scams, or prompt injections."""
        combined_text = f"{repo_name} {issue_title} {issue_body}".lower()

        for kw in _HONEYPOT_KEYWORDS:
            if kw in combined_text:
                return (
                    False,
                    f"Blocked by Security Policy: Detected honeypot/scam pattern '{kw}'",
                )

        for regex in _PROMPT_INJECTION_REGEXES:
            if regex.search(combined_text):
                return (
                    False,
                    "Blocked by Red Team Policy: Detected indirect prompt injection directive",
                )

        return True, "Target verified safe"

    def fork_repository(self, owner: str, repo: str) -> Tuple[bool, Dict[str, Any]]:
        """Forks an upstream repository to authenticated user account."""
        if not self.has_token:
            return False, {"error": "Authentication required"}

        code, resp = self._request(f"/repos/{owner}/{repo}/forks", method="POST")
        if code in (200, 202):
            return True, {
                "fork_full_name": resp.get("full_name"),
                "clone_url": resp.get("clone_url"),
                "default_branch": resp.get("default_branch", "main"),
            }
        return False, resp

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> Tuple[bool, Dict[str, Any]]:
        """Opens a Pull Request from head branch to upstream repository."""
        if not self.has_token:
            return False, {"error": "Authentication required"}

        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        }
        code, resp = self._request(f"/repos/{owner}/{repo}/pulls", method="POST", data=payload)
        if code in (200, 201):
            return True, {
                "pr_url": resp.get("html_url"),
                "pr_number": resp.get("number"),
                "state": resp.get("state"),
            }
        return False, resp
