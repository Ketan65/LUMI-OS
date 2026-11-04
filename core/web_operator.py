"""WEB-OPERATOR: Autonomous Computer & Browser Agent — Phase 11.

Allows LUMI to autonomously browse websites, extract clean markdown/text from pages,
follow links, summarize articles, and scrape daily tech/AI trend briefings.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 LUMI/2.0"


def clean_html_to_text(html_content: str, max_chars: int = 4000) -> str:
    """Converts raw HTML into clean, human-readable text, stripping scripts, styles, and tags."""
    # Remove script and style elements
    text = re.sub(r"<(script|style|svg|noscript)[^>]*>[\s\S]*?</\1>", " ", html_content, flags=re.IGNORECASE)
    # Replace block tags with newlines
    text = re.sub(r"</?(div|p|h[1-6]|li|blockquote|tr|table|article|section)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Unescape HTML entities
    text = html.unescape(text)
    # Collapse multiple whitespaces and consecutive newlines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    non_empty = [line for line in lines if line]
    cleaned = "\n".join(non_empty)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + f"\n...[truncated to {max_chars} chars]"
    return cleaned


def extract_links(html_content: str, base_url: str, limit: int = 15) -> list[dict[str, str]]:
    """Extracts anchor links from HTML with resolved absolute URLs."""
    pattern = r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>'
    matches = re.findall(pattern, html_content, flags=re.IGNORECASE | re.DOTALL)
    links: list[dict[str, str]] = []
    seen: set[str] = set()

    for href, anchor_text in matches:
        href = href.strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            full_url = urllib.parse.urljoin(base_url, href)
        except Exception:
            continue

        clean_text = clean_html_to_text(anchor_text, max_chars=100).replace("\n", " ").strip()
        if not clean_text or len(clean_text) < 2:
            clean_text = href

        if full_url not in seen:
            seen.add(full_url)
            links.append({"title": clean_text[:80], "url": full_url})
            if len(links) >= limit:
                break

    return links


@dataclass
class PageData:
    url: str
    status_code: int
    title: str
    text: str
    links: list[dict[str, str]]


class WebOperator:
    """Autonomous Web Operator engine for reading, extracting, and summarizing web pages."""

    def __init__(self, brain: Any = None):
        self.brain = brain

    def fetch_page(self, url: str, timeout: float = 10.0) -> PageData:
        """Fetches web page via HTTP GET with browser spoofing."""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.status
                raw_bytes = resp.read()
                # Charset decode
                charset = resp.headers.get_content_charset() or "utf-8"
                content = raw_bytes.decode(charset, errors="replace")

            # Extract Title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", content, flags=re.IGNORECASE | re.DOTALL)
            title = html.unescape(title_match.group(1).strip()) if title_match else url

            # Clean text and extract links
            text = clean_html_to_text(content)
            links = extract_links(content, url)

            return PageData(url=url, status_code=status_code, title=title, text=text, links=links)
        except Exception as exc:
            return PageData(
                url=url,
                status_code=500,
                title="Error Loading Page",
                text=f"Failed to fetch {url}: {exc}",
                links=[],
            )

    def summarize_page(self, url: str, max_chars: int = 1500) -> str:
        """Reads page and generates a concise intelligence briefing (LLM-synthesized when brain is present)."""
        page = self.fetch_page(url)
        if page.status_code >= 400:
            return f"❌ Could not access `{url}`: {page.text}"

        ai_summary = ""
        if self.brain is not None and page.text.strip():
            try:
                prompt = (
                    f"Webpage Title: {page.title}\n"
                    f"URL: {page.url}\n"
                    f"Extracted Content:\n{page.text[:3000]}\n\n"
                    "Provide a sharp 3-5 bullet Executive Intelligence Summary of the core technical/factual content on this page."
                )
                reply = self.brain.chat(
                    [
                        {
                            "role": "system",
                            "content": "You are LUMI's Web Intelligence Analyst. Summarize web pages into concise, high-signal technical bullet points.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                text = (reply.text if hasattr(reply, "text") else str(reply)).strip()
                if len(text) > 30:
                    ai_summary = text
            except Exception:
                ai_summary = ""

        summary_lines = [
            f"### 🌐 Web Intelligence: {page.title}",
            f"**Source URL:** {page.url}",
            f"**Status:** HTTP {page.status_code}",
            "",
        ]
        if ai_summary:
            summary_lines.extend([
                "**🧠 AI Intelligence Synthesis:**",
                ai_summary,
                "",
            ])
        summary_lines.extend([
            "**Key Content Preview:**",
            page.text[:max_chars],
        ])

        if page.links:
            summary_lines.append("")
            summary_lines.append("**Extracted Links:**")
            for l in page.links[:6]:
                summary_lines.append(f"- [{l['title']}]({l['url']})")

        return "\n".join(summary_lines)

    def fetch_tech_briefing(self) -> str:
        """Pulls top current tech trends from HackerNews RSS/HTML feed."""
        hn_url = "https://news.ycombinator.com"
        page = self.fetch_page(hn_url)
        if page.status_code >= 400:
            return "Unable to reach tech news aggregator at this moment."

        stories = [l for l in page.links if not l["url"].startswith("https://news.ycombinator.com/from?")]
        briefing_lines = [
            "### 📰 LUMI Autonomous Tech Briefing",
            "Top stories from the developer frontier right now:",
            "",
        ]

        count = 0
        for s in stories:
            if "item?id=" in s["url"] or "ycombinator" in s["url"]:
                continue
            count += 1
            briefing_lines.append(f"{count}. **{s['title']}**\n   🔗 {s['url']}")
            if count >= 7:
                break

        if count == 0:
            briefing_lines.append("No active news items parsed from feed.")

        return "\n".join(briefing_lines)
