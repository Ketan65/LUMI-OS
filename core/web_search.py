"""Web Search — LUMI internet se jankari laya kar sake (agar network available ho).

Tries DuckDuckGo HTML first, falls back to honest "no internet" message.
China-side network flaky hone ke karan graceful degradation zaroori hai.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


def search_web(query: str, max_results: int = 3) -> str:
    """Web search karein aur top results return karein."""
    try:
        url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Simple regex extraction of result titles + snippets
        results = re.findall(
            r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>',
            html,
        )[:max_results]

        if not results:
            return "Mujhe internet se koi result nahi mila, Sir."

        lines = [f"Internet search results for: {query}"]
        for i, (link, title) in enumerate(results, 1):
            title = re.sub(r"<[^>]+>", "", title).strip()
            lines.append(f"{i}. {title}")
        return "\n".join(lines)

    except urllib.error.URLError:
        return "Internet available nahi hai, Sir — offline mode mein search nahi ho sakta."
    except Exception as exc:
        return f"Search error: {exc}"


def search_web_brief(query: str) -> str:
    """Short search — pehla result hi do."""
    result = search_web(query, max_results=1)
    return result.split("\n", 1)[-1] if result else "Koi result nahi mila."
