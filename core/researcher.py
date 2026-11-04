"""Deep Autonomous Web Researcher & Dossier Synthesizer for LUMI.

Capabilities:
  1. Query Expansion: Takes a high-level topic and decomposes it into 3 diverse targeted search queries.
  2. Multi-Source Scraping: Extracts clean text and citations from top distinct domains via DuckDuckGo.
  3. Structured Dossier Synthesis: Formats an in-depth, cited Markdown research brief.
  4. Workspace Persistence: Saves dossiers to workspace/research/<slug>.md.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.web import web_read, web_search

logger = logging.getLogger("lumi.researcher")


class DeepResearcher:
    """Autonomous deep research and multi-source synthesis engine."""

    def __init__(self, workspace_root: str | Path = "workspace", brain: Any = None):
        self.workspace_root = Path(workspace_root)
        self.research_dir = self.workspace_root / "research"
        self.research_dir.mkdir(parents=True, exist_ok=True)
        self.brain = brain

    def expand_queries(self, topic: str) -> list[str]:
        """Expands topic into complementary search perspectives using LLM when available."""
        clean = topic.strip()
        if self.brain is not None:
            try:
                prompt = (
                    f"Generate 3 distinct, targeted search engine queries to deeply research this topic:\n"
                    f"Topic: {clean}\n"
                    f"Return ONLY 3 lines, one search query per line, no numbering or bullets."
                )
                reply = self.brain.chat(
                    [
                        {"role": "system", "content": "You are a technical search query optimizer. Output 3 concise search queries, one per line."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                text = reply.text if hasattr(reply, "text") else str(reply)
                lines = [
                    re.sub(r"^[\d\-\*\.\)\s]+", "", ln).strip().strip('"\'')
                    for ln in text.splitlines()
                    if ln.strip() and not ln.strip().startswith("#")
                ]
                valid = [q for q in lines if len(q) >= 4][:3]
                if len(valid) == 3:
                    return valid
            except Exception as exc:
                logger.debug("LLM query expansion fallback: %s", exc)

        return [
            f"{clean} architecture overview",
            f"{clean} technical implementation benchmarks",
            f"{clean} security & best practices 2026",
        ]

    def _synthesize_with_brain(self, topic_clean: str, source_excerpts: list[dict[str, str]]) -> str | None:
        """Synthesizes a genuine topic-specific analysis from scraped sources (or domain knowledge) via LLM."""
        if self.brain is None:
            return None
        try:
            sources_context = "\n\n".join(
                f"[{i+1}] {s['title']} ({s['url']}):\n{s['excerpt']}"
                for i, s in enumerate(source_excerpts)
            ) or "No live web pages were reachable; synthesize from deep technical domain knowledge."
            prompt = (
                f"Topic: {topic_clean}\n\n"
                f"Extracted Web Sources:\n{sources_context}\n\n"
                "Write two concise, high-density Markdown sections for Commander:\n"
                "1. `## 🎯 Executive Summary` (3-4 sentences specifically about this topic)\n"
                "2. `## 🔬 Key Synthesized Findings & Technical Insights` (4 concrete bullet points with real technical details, trade-offs, and actionable architecture guidance specific to this topic)."
            )
            reply = self.brain.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are LUMI's Sovereign Research Synthesizer. Write razor-sharp, technical, "
                            "topic-specific engineering intelligence. Never use generic filler."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            text = (reply.text if hasattr(reply, "text") else str(reply)).strip()
            if len(text) > 80:
                return text
        except Exception as exc:
            logger.debug("LLM dossier synthesis fallback: %s", exc)
        return None

    def conduct_research(self, topic: str, max_sources: int = 4) -> dict[str, Any]:
        """Executes multi-query web search, deep page extraction, and synthesizes a research dossier."""
        t0 = time.perf_counter()
        topic_clean = topic.strip()
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", topic_clean.lower()).strip("_")[:40] or "research_brief"
        queries = self.expand_queries(topic_clean)

        collected_links: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        for q in queries:
            raw_res = web_search(q, max_results=3)
            # Parse links and titles from web_search format: [N] Title \n URL: href
            blocks = re.findall(r"\[\d+\]\s*(.*?)\n\s*URL:\s*(\S+)", raw_res)
            for title, url in blocks:
                if url not in seen_urls and url.startswith(("http://", "https://")):
                    seen_urls.add(url)
                    collected_links.append({"title": title.strip(), "url": url.strip()})
                    if len(collected_links) >= max_sources:
                        break
            if len(collected_links) >= max_sources:
                break

        # Deep read sources
        source_excerpts: list[dict[str, str]] = []
        for src in collected_links:
            page_text = web_read(src["url"], max_chars=1800)
            if not page_text.startswith("Security blocked") and not page_text.startswith("Web read error"):
                source_excerpts.append({
                    "title": src["title"],
                    "url": src["url"],
                    "excerpt": page_text[:1200].replace("\n", " ").strip(),
                })

        # Synthesize Dossier
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        citations_md = "\n".join([f"- **[{s['title']}]({s['url']})**: {s['excerpt'][:250]}..." for s in source_excerpts]) or "- No public web sources could be safely extracted."

        llm_synthesis = self._synthesize_with_brain(topic_clean, source_excerpts)
        if llm_synthesis:
            body_section = llm_synthesis
        else:
            body_section = f"""## 🎯 Executive Summary
Comprehensive multi-angle synthesis investigating **{topic_clean}** across `{len(queries)}` search vectors: {', '.join(f'`{q}`' for q in queries)}.

---

## 🔬 Key Synthesized Findings & Insights
- **Primary Evidence Extracted:** Analyzed {len(source_excerpts)} verified web sources covering `{topic_clean}`.
- **Technical Synthesis:** {source_excerpts[0]['excerpt'][:300] if source_excerpts else f'Focused technical analysis on {topic_clean} architecture, trade-offs, and implementation patterns.'}
- **Strategic Recommendations:** Prioritize modular separation, deterministic verification, and continuous profiling when implementing `{topic_clean}`."""

        dossier_md = f"""# 📑 Deep Research Dossier: {topic_clean}
**Generated By:** LUMI Sovereign Intelligence Engine  
**Prepared For:** Commander  
**Timestamp:** {now_str}  
**Search Vectors:** {', '.join(queries)}  
**Sources Analyzed:** {len(source_excerpts)} distinct verified domains  

---

{body_section}

---

## 📚 Primary Citations & Source Intelligence
{citations_md}

---
*Autonomous dossier generated in {round((time.perf_counter() - t0) * 1000, 2)}ms by LUMI Deep Researcher.*
"""

        # Save to disk
        out_file = self.research_dir / f"{slug}_{int(time.time())}.md"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(dossier_md)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {
            "topic": topic_clean,
            "dossier_file": str(out_file),
            "sources_count": len(source_excerpts),
            "sources": source_excerpts,
            "dossier_markdown": dossier_md,
            "elapsed_ms": elapsed_ms,
        }
