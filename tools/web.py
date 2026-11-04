"""Web tools — web_search (DuckDuckGo) and web_read (safe HTTP extraction).

Security & Safety:
  - SSRF protection: blocks localhost, private IPs, link-local, loopback, non-HTTP schemes.
  - Domain deny-list.
  - Output capped to prevent context flooding.
  - Read-only tools; flagged as UNTRUSTED by orchestrator (taints turn, degrades write).
"""

from __future__ import annotations

import ipaddress
import re
import socket
import urllib.parse
from typing import Any

from tools.registry import Tool, ToolRegistry

MAX_WEB_CHARS = 6000
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 LUMI/1.0"

DENIED_DOMAINS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}


def is_safe_web_url(url: str) -> tuple[bool, str]:
    """Validates URL against SSRF and private network access."""
    if not url or not isinstance(url, str):
        return False, "Invalid URL"

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as exc:
        return False, f"URL parse error: {exc}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Blocked scheme '{parsed.scheme}': only http and https are allowed"

    host = parsed.hostname
    if not host:
        return False, "Missing hostname in URL"

    host_lower = host.lower()
    if host_lower in DENIED_DOMAINS:
        return False, f"Blocked target: '{host}' is not permitted"

    # Resolve IP and check if it targets local or private address spaces
    try:
        resolved_ip = socket.gethostbyname(host)
        ip = ipaddress.ip_address(resolved_ip)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Blocked access to private/reserved IP: {resolved_ip}"
    except (socket.gaierror, ValueError) as exc:
        return False, f"DNS resolution failed for '{host}': {exc}"

    return True, ""


def web_search(query: str, max_results: int = 5) -> str:
    """Searches DuckDuckGo and returns top results with titles, links, and snippets."""
    query = (query or "").strip()
    if not query:
        return "Search query cannot be empty."

    try:
        max_n = max(1, min(int(max_results), 10))
    except (TypeError, ValueError):
        max_n = 5

    try:
        from duckduckgo_search import DDGS

        results: list[dict[str, Any]] = []
        # Try backend='lite' first as it avoids standard HTML/API rate limits
        for backend in ("lite", "api", "html"):
            try:
                with DDGS() as ddgs:
                    raw = list(ddgs.text(query, backend=backend, max_results=max_n))
                    if raw:
                        results = raw
                        break
            except Exception:
                continue

        if not results:
            return f"No search results found for: '{query}'"

        out_lines: list[str] = [f"Search results for: '{query}'\n"]
        for idx, item in enumerate(results[:max_n], start=1):
            title = (item.get("title") or "No title").strip()
            href = (item.get("href") or item.get("link") or "").strip()
            body = (item.get("body") or item.get("snippet") or "").strip()

            out_lines.append(f"[{idx}] {title}")
            if href:
                out_lines.append(f"    URL: {href}")
            if body:
                out_lines.append(f"    Snippet: {body}")
            out_lines.append("")

        res_text = "\n".join(out_lines).strip()
        if len(res_text) > MAX_WEB_CHARS:
            res_text = res_text[:MAX_WEB_CHARS] + "\n...[truncated]"
        return res_text

    except Exception as exc:
        return f"Web search error: {exc}"


def web_read(url: str, max_chars: int = 5000) -> str:
    """Safely fetches and extracts text/markdown from a web page."""
    url = (url or "").strip()
    is_safe, reason = is_safe_web_url(url)
    if not is_safe:
        return f"Security blocked URL: {reason}"

    try:
        char_cap = max(500, min(int(max_chars), MAX_WEB_CHARS))
    except (TypeError, ValueError):
        char_cap = 5000

    try:
        import httpx
        from bs4 import BeautifulSoup

        headers = {"User-Agent": DEFAULT_USER_AGENT}
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "").lower()

            # Text content or HTML
            if "html" not in content_type and "text" in content_type:
                text = resp.text
                if len(text) > char_cap:
                    return text[:char_cap] + "\n...[truncated]"
                return text

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove non-content elements
            for tag in soup(["script", "style", "noscript", "header", "footer",
                             "nav", "svg", "iframe", "button", "form", "aside"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Extract text preserving paragraphs
            lines: list[str] = []
            if title:
                lines.append(f"# {title}\n")

            for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
                txt = el.get_text(separator=" ", strip=True)
                if txt:
                    if el.name in ("h1", "h2", "h3", "h4"):
                        lines.append(f"\n### {txt}\n")
                    elif el.name == "li":
                        lines.append(f"* {txt}")
                    else:
                        lines.append(f"{txt}\n")

            full_text = "\n".join(lines).strip()
            # Clean excessive blank lines
            full_text = re.sub(r"\n{3,}", "\n\n", full_text)

            if not full_text:
                full_text = soup.get_text(separator=" ", strip=True)

            if not full_text:
                return f"Page at {url} returned empty readable content."

            if len(full_text) > char_cap:
                full_text = full_text[:char_cap] + f"\n...[truncated to {char_cap} chars]"

            return full_text

    except Exception as exc:
        return f"Web read error: {exc}"


def register_web_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="web_search",
        description="Searches DuckDuckGo on the internet for queries, live facts, documentation, or news.",
        params_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query to look up on the web."},
                "max_results": {"type": "integer", "description": "Number of results to return (1-10, default 5).", "default": 5},
            },
            "required": ["query"],
        },
        handler=web_search,
        risk="auto",
    ))

    registry.register(Tool(
        name="web_read",
        description="Fetches a public web page URL and extracts readable text and articles. Protected against SSRF.",
        params_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The public HTTP or HTTPS web URL to fetch."},
                "max_chars": {"type": "integer", "description": "Maximum characters to extract (up to 6000, default 5000).", "default": 5000},
            },
            "required": ["url"],
        },
        handler=web_read,
        risk="auto",
    ))
