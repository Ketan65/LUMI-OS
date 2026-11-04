"""COGNITIVE-GRAPH: Temporal Knowledge Graph & Episodic Memory Palace (Phase 24).

Moves LUMI beyond flat key-value memory into a structured, multi-hop causal Knowledge Graph:
1. Persistent SQLite Graph Store (kg_nodes, kg_edges) with temporal validity (valid_from / valid_until).
2. Multi-Hop Subgraph Traversal (BFS 1..N hops) for deep contextual recall.
3. Shortest Causal Path Discovery between any two entities in Boss's ecosystem.
4. Weighted Centrality Ranking to surface top architectural & project nodes.
5. Autonomous Text-to-Graph Ingestion (hybrid deterministic + LLM relation extraction).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("lumi.cognitive_graph")


def _norm_id(name: str) -> str:
    """Normalizes an entity name into a canonical graph node ID."""
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name.strip()).strip("_").lower()
    return clean or "unknown_entity"


class CognitiveGraph:
    """Sovereign Temporal Knowledge Graph & Multi-Hop Reasoning Memory."""

    def __init__(self, db_path: str | Path = "data/lumi.db", brain: Any = None):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.brain = brain
        self._init_schema()
        self._seed_sovereign_core()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    entity_type TEXT NOT NULL DEFAULT 'Concept',
                    properties_json TEXT NOT NULL DEFAULT '{}',
                    importance REAL NOT NULL DEFAULT 1.0,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kg_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    evidence TEXT NOT NULL DEFAULT '',
                    valid_from TEXT NOT NULL,
                    valid_until TEXT DEFAULT NULL,
                    FOREIGN KEY(source_id) REFERENCES kg_nodes(node_id),
                    FOREIGN KEY(target_id) REFERENCES kg_nodes(node_id)
                );

                CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_tgt ON kg_edges(target_id);
                """
            )

    def _seed_sovereign_core(self) -> None:
        """Seeds the operator's core identity and project graph from local identity config if empty."""
        with self._conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            if count > 0:
                return

        from core.personal_identity import load_identity
        ident = load_identity()
        user = ident.get("user", {})
        user_name = user.get("name", "Commander")
        handle = user.get("handle", "Operator")
        college = user.get("college", "Research Lab")
        org = user.get("internship", "Cyber Defense Division")
        org_short = org.split("(")[0].strip() if "(" in org else org[:25]
        if "SecOps" in org:
            org_short = "CyberDefense SecOps"
        gpu_name = ident.get("devices", {}).get("pc", "NVIDIA RTX GPU")

        seed_nodes = [
            (user_name, "Person", {"alias": handle, "role": "Cybersecurity & AI Engineer", "institution": college}, 10.0),
            ("LUMI", "System", {"role": "Sovereign JARVIS OS", "engine": "Ollama 8B (Hermes3 + Qwen3)"}, 9.5),
            (org_short, "Organization", {"focus": org}, 9.0),
            (gpu_name, "Hardware", {"os": "Windows 11"}, 8.0),
        ]
        projects = ident.get("projects", [])
        proj_names: list[str] = []
        for p in projects[:5]:
            if isinstance(p, dict) and p.get("name"):
                pname = p["name"].split("/")[0].strip()
                proj_names.append(pname)
                seed_nodes.append((pname, "Project", {"desc": p.get("desc", "")}, 9.0))

        for label, etype, props, imp in seed_nodes:
            self.upsert_node(label, entity_type=etype, properties=props, importance=imp)

        seed_edges = [
            (user_name, "ARCHITECT_OF", "LUMI", "Creator and Commander of LUMI OS"),
            (user_name, "WORKS_WITH", org_short, "Security & VAPT operations"),
            ("LUMI", "ACCELERATED_BY", gpu_name, "Local 8B inference acceleration"),
        ]
        for pname in proj_names:
            seed_edges.append((user_name, "DEVELOPS", pname, "Core engineering project"))
        if proj_names:
            seed_edges.append((proj_names[0], "DEPLOYED_FOR", org_short, "Threat intelligence deployment"))

        for src, rel, tgt, ev in seed_edges:
            self.upsert_edge(src, rel, tgt, evidence=ev, weight=2.0)

    def upsert_node(
        self,
        label: str,
        entity_type: str = "Concept",
        properties: dict[str, Any] | None = None,
        importance: float = 1.0,
    ) -> dict[str, Any]:
        node_id = _norm_id(label)
        now = datetime.now().isoformat(timespec="seconds")
        props = properties or {}

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT properties_json, importance FROM kg_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            if existing:
                try:
                    merged_props = json.loads(existing["properties_json"] or "{}")
                except Exception:
                    merged_props = {}
                merged_props.update(props)
                new_imp = max(float(existing["importance"]), float(importance))
                conn.execute(
                    """
                    UPDATE kg_nodes
                    SET label = ?, entity_type = ?, properties_json = ?, importance = ?, updated_at = ?
                    WHERE node_id = ?
                    """,
                    (label.strip(), entity_type, json.dumps(merged_props), new_imp, now, node_id),
                )
            else:
                merged_props = props
                new_imp = float(importance)
                conn.execute(
                    """
                    INSERT INTO kg_nodes (node_id, label, entity_type, properties_json, importance, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (node_id, label.strip(), entity_type, json.dumps(merged_props), new_imp, now),
                )
        return {
            "node_id": node_id,
            "label": label.strip(),
            "entity_type": entity_type,
            "properties": merged_props,
            "importance": new_imp,
        }

    def upsert_edge(
        self,
        source_label: str,
        relation: str,
        target_label: str,
        evidence: str = "",
        weight: float = 1.0,
        source_type: str = "Entity",
        target_type: str = "Entity",
    ) -> dict[str, Any]:
        src_node = self.upsert_node(source_label, entity_type=source_type)
        tgt_node = self.upsert_node(target_label, entity_type=target_type)
        rel_clean = re.sub(r"[^A-Z0-9_]+", "_", relation.strip().upper()).strip("_") or "RELATED_TO"
        edge_id = f"{src_node['node_id']}__{rel_clean}__{tgt_node['node_id']}"
        now = datetime.now().isoformat(timespec="seconds")

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT weight FROM kg_edges WHERE edge_id = ? AND valid_until IS NULL",
                (edge_id,),
            ).fetchone()
            if existing:
                new_weight = round(float(existing["weight"]) + 0.5, 2)
                conn.execute(
                    """
                    UPDATE kg_edges
                    SET weight = ?, evidence = CASE WHEN ? != '' THEN ? ELSE evidence END
                    WHERE edge_id = ?
                    """,
                    (new_weight, evidence, evidence, edge_id),
                )
            else:
                new_weight = float(weight)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO kg_edges
                    (edge_id, source_id, target_id, relation, weight, evidence, valid_from, valid_until)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (edge_id, src_node["node_id"], tgt_node["node_id"], rel_clean, new_weight, evidence, now),
                )
        return {
            "edge_id": edge_id,
            "source": src_node["label"],
            "relation": rel_clean,
            "target": tgt_node["label"],
            "weight": new_weight,
            "evidence": evidence,
        }

    def invalidate_edge(self, source_label: str, relation: str, target_label: str) -> bool:
        """Marks an outdated temporal relation as no longer valid (temporal knowledge decay)."""
        src_id = _norm_id(source_label)
        tgt_id = _norm_id(target_label)
        rel_clean = re.sub(r"[^A-Z0-9_]+", "_", relation.strip().upper()).strip("_")
        edge_id = f"{src_id}__{rel_clean}__{tgt_id}"
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE kg_edges SET valid_until = ? WHERE edge_id = ? AND valid_until IS NULL",
                (now, edge_id),
            )
            return cur.rowcount > 0

    def query_neighborhood(self, entity_query: str, max_hops: int = 2, limit: int = 25) -> dict[str, Any]:
        """Traverses up to N hops around matching seed nodes using Breadth-First Search (BFS)."""
        q_norm = _norm_id(entity_query)
        q_like = f"%{entity_query.strip()}%"

        with self._conn() as conn:
            seeds = conn.execute(
                """
                SELECT * FROM kg_nodes
                WHERE node_id = ? OR label LIKE ? OR properties_json LIKE ?
                ORDER BY importance DESC LIMIT 5
                """,
                (q_norm, q_like, q_like),
            ).fetchall()

            if not seeds:
                return {
                    "query": entity_query,
                    "matched_seeds": [],
                    "nodes": [],
                    "edges": [],
                    "hops_explored": 0,
                }

            visited_nodes: dict[str, dict[str, Any]] = {}
            collected_edges: dict[str, dict[str, Any]] = {}
            queue: deque[tuple[str, int]] = deque()

            for s in seeds:
                nid = s["node_id"]
                visited_nodes[nid] = {
                    "node_id": nid,
                    "label": s["label"],
                    "entity_type": s["entity_type"],
                    "properties": json.loads(s["properties_json"] or "{}"),
                    "importance": s["importance"],
                    "hop": 0,
                }
                queue.append((nid, 0))

            while queue and len(collected_edges) < limit:
                curr_id, depth = queue.popleft()
                if depth >= max_hops:
                    continue

                rows = conn.execute(
                    """
                    SELECT e.*, n_src.label AS src_label, n_src.entity_type AS src_type,
                           n_tgt.label AS tgt_label, n_tgt.entity_type AS tgt_type
                    FROM kg_edges e
                    JOIN kg_nodes n_src ON e.source_id = n_src.node_id
                    JOIN kg_nodes n_tgt ON e.target_id = n_tgt.node_id
                    WHERE (e.source_id = ? OR e.target_id = ?) AND e.valid_until IS NULL
                    ORDER BY e.weight DESC
                    """,
                    (curr_id, curr_id),
                ).fetchall()

                for r in rows:
                    eid = r["edge_id"]
                    if eid not in collected_edges:
                        collected_edges[eid] = {
                            "edge_id": eid,
                            "source_id": r["source_id"],
                            "source": r["src_label"],
                            "relation": r["relation"],
                            "target_id": r["target_id"],
                            "target": r["tgt_label"],
                            "weight": r["weight"],
                            "evidence": r["evidence"],
                        }

                    neighbor_id = r["target_id"] if r["source_id"] == curr_id else r["source_id"]
                    if neighbor_id not in visited_nodes:
                        n_row = conn.execute(
                            "SELECT * FROM kg_nodes WHERE node_id = ?", (neighbor_id,)
                        ).fetchone()
                        if n_row:
                            visited_nodes[neighbor_id] = {
                                "node_id": neighbor_id,
                                "label": n_row["label"],
                                "entity_type": n_row["entity_type"],
                                "properties": json.loads(n_row["properties_json"] or "{}"),
                                "importance": n_row["importance"],
                                "hop": depth + 1,
                            }
                            queue.append((neighbor_id, depth + 1))

        return {
            "query": entity_query,
            "matched_seeds": [s["label"] for s in seeds],
            "nodes": list(visited_nodes.values()),
            "edges": list(collected_edges.values()),
            "hops_explored": max_hops,
        }

    def find_causal_path(self, source_query: str, target_query: str, max_depth: int = 5) -> dict[str, Any]:
        """Finds the shortest semantic/causal chain connecting two entities via bidirectional/BFS search."""
        src_id = _norm_id(source_query)
        tgt_id = _norm_id(target_query)

        with self._conn() as conn:
            # Resolve fuzzy node IDs if exact match not found
            s_row = conn.execute(
                "SELECT node_id, label FROM kg_nodes WHERE node_id = ? OR label LIKE ? LIMIT 1",
                (src_id, f"%{source_query.strip()}%"),
            ).fetchone()
            t_row = conn.execute(
                "SELECT node_id, label FROM kg_nodes WHERE node_id = ? OR label LIKE ? LIMIT 1",
                (tgt_id, f"%{target_query.strip()}%"),
            ).fetchone()

            if not s_row or not t_row:
                return {
                    "connected": False,
                    "source": source_query,
                    "target": target_query,
                    "path": [],
                    "message": "One or both entities were not found in the Cognitive Graph.",
                }

            start_id, start_label = s_row["node_id"], s_row["label"]
            end_id, end_label = t_row["node_id"], t_row["label"]

            if start_id == end_id:
                return {
                    "connected": True,
                    "source": start_label,
                    "target": end_label,
                    "hops": 0,
                    "path": [start_label],
                }

            queue: deque[tuple[str, list[dict[str, str]]]] = deque([(start_id, [])])
            visited: set[str] = {start_id}

            while queue:
                curr_id, path = queue.popleft()
                if len(path) >= max_depth:
                    continue

                edges = conn.execute(
                    """
                    SELECT e.*, n_src.label AS src_label, n_tgt.label AS tgt_label
                    FROM kg_edges e
                    JOIN kg_nodes n_src ON e.source_id = n_src.node_id
                    JOIN kg_nodes n_tgt ON e.target_id = n_tgt.node_id
                    WHERE (e.source_id = ? OR e.target_id = ?) AND e.valid_until IS NULL
                    """,
                    (curr_id, curr_id),
                ).fetchall()

                for edge in edges:
                    is_forward = edge["source_id"] == curr_id
                    next_id = edge["target_id"] if is_forward else edge["source_id"]
                    step = {
                        "from": edge["src_label"] if is_forward else edge["tgt_label"],
                        "relation": edge["relation"] if is_forward else f"<-{edge['relation']}-",
                        "to": edge["tgt_label"] if is_forward else edge["src_label"],
                        "evidence": edge["evidence"],
                    }
                    new_path = path + [step]
                    if next_id == end_id:
                        chain_str = " ➔ ".join(
                            f"{s['from']} --[{s['relation']}]--> {s['to']}" for s in new_path
                        )
                        return {
                            "connected": True,
                            "source": start_label,
                            "target": end_label,
                            "hops": len(new_path),
                            "path": new_path,
                            "chain_summary": chain_str,
                        }
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, new_path))

        return {
            "connected": False,
            "source": start_label,
            "target": end_label,
            "hops": -1,
            "path": [],
            "message": f"No causal path found between '{start_label}' and '{end_label}' within {max_depth} hops.",
        }

    def ingest_text(self, text: str, use_llm: bool = True) -> dict[str, Any]:
        """Extracts structured (subject, relation, object) triples from text and merges them into the graph."""
        extracted: list[dict[str, str]] = []

        # 1. Deterministic pattern extraction for fast common statements
        patterns = [
            (r"([A-Z][A-Za-z0-9_\-]{1,25})\s+(?:uses|utilizes|runs on)\s+([A-Z][A-Za-z0-9_\-]{1,25})", "USES"),
            (r"([A-Z][A-Za-z0-9_\-]{1,25})\s+(?:depends on|requires)\s+([A-Z][A-Za-z0-9_\-]{1,25})", "DEPENDS_ON"),
            (r"([A-Z][A-Za-z0-9_\-]{1,25})\s+(?:built|created|developed)\s+([A-Z][A-Za-z0-9_\-]{1,25})", "DEVELOPS"),
        ]
        for pat, rel in patterns:
            for m in re.finditer(pat, text):
                extracted.append({
                    "source": m.group(1).strip(),
                    "relation": rel,
                    "target": m.group(2).strip(),
                    "evidence": m.group(0).strip()[:150],
                })

        # 2. LLM Triple Extraction when brain is available
        if use_llm and self.brain is not None and len(text.strip()) >= 20:
            try:
                prompt = (
                    f"Extract up to 4 high-value knowledge triples from this text:\n"
                    f"Text: {text[:1500]}\n\n"
                    "Return ONLY a JSON array of objects with keys: "
                    '[{"source": "EntityA", "source_type": "Project|Person|Tech|Concept", '
                    '"relation": "UPPER_SNAKE_VERB", "target": "EntityB", "target_type": "Concept", "evidence": "short reason"}]'
                )
                reply = self.brain.chat(
                    [
                        {"role": "system", "content": "You are LUMI's Knowledge Graph Triple Extractor. Output valid JSON array only."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                )
                raw = reply.text if hasattr(reply, "text") else str(reply)
                m = re.search(r"\[[\s\S]*\]", raw)
                if m:
                    items = json.loads(m.group(0))
                    if isinstance(items, list):
                        for item in items[:5]:
                            if isinstance(item, dict) and item.get("source") and item.get("target"):
                                extracted.append({
                                    "source": str(item["source"]).strip(),
                                    "source_type": str(item.get("source_type") or "Entity"),
                                    "relation": str(item.get("relation") or "RELATED_TO").strip(),
                                    "target": str(item["target"]).strip(),
                                    "target_type": str(item.get("target_type") or "Entity"),
                                    "evidence": str(item.get("evidence") or text[:100]).strip(),
                                })
            except Exception as exc:
                logger.debug("LLM triple extraction fallback: %s", exc)

        saved_edges = []
        for item in extracted:
            edge = self.upsert_edge(
                source_label=item["source"],
                relation=item["relation"],
                target_label=item["target"],
                evidence=item.get("evidence", ""),
                source_type=item.get("source_type", "Entity"),
                target_type=item.get("target_type", "Entity"),
            )
            saved_edges.append(edge)

        return {
            "triples_extracted": len(saved_edges),
            "edges": saved_edges,
        }

    def get_ecosystem_summary(self, top_n: int = 12) -> dict[str, Any]:
        """Computes node degree centrality + importance ranking across the entire knowledge graph."""
        with self._conn() as conn:
            nodes_count = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            edges_count = conn.execute("SELECT COUNT(*) FROM kg_edges WHERE valid_until IS NULL").fetchone()[0]
            top_nodes = conn.execute(
                """
                SELECT n.node_id, n.label, n.entity_type, n.importance,
                       COUNT(e.edge_id) AS degree
                FROM kg_nodes n
                LEFT JOIN kg_edges e
                  ON (e.source_id = n.node_id OR e.target_id = n.node_id) AND e.valid_until IS NULL
                GROUP BY n.node_id
                ORDER BY (n.importance + COUNT(e.edge_id) * 1.5) DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()

            recent_edges = conn.execute(
                """
                SELECT n1.label AS source, e.relation, n2.label AS target, e.weight, e.evidence
                FROM kg_edges e
                JOIN kg_nodes n1 ON e.source_id = n1.node_id
                JOIN kg_nodes n2 ON e.target_id = n2.node_id
                WHERE e.valid_until IS NULL
                ORDER BY e.valid_from DESC, e.weight DESC
                LIMIT ?
                """,
                (top_n,),
            ).fetchall()

        return {
            "total_nodes": nodes_count,
            "total_active_edges": edges_count,
            "central_entities": [dict(r) for r in top_nodes],
            "key_relations": [dict(r) for r in recent_edges],
        }

    def build_context_snippet(self, user_prompt: str, max_relations: int = 6) -> str:
        """Finds any graph entities mentioned in `user_prompt` and returns their 1-hop causal context."""
        tokens = [w for w in re.findall(r"[A-Za-z0-9_]{3,}", user_prompt) if len(w) >= 3]
        if not tokens:
            return ""

        matched_Relations: list[str] = []
        seen_edges: set[str] = set()

        for tok in tokens[:6]:
            sub = self.query_neighborhood(tok, max_hops=1, limit=4)
            for e in sub.get("edges", []):
                eid = e["edge_id"]
                if eid not in seen_edges:
                    seen_edges.add(eid)
                    ev = f" ({e['evidence']})" if e.get("evidence") else ""
                    matched_Relations.append(f"{e['source']} --[{e['relation']}]--> {e['target']}{ev}")
                    if len(matched_Relations) >= max_relations:
                        break
            if len(matched_Relations) >= max_relations:
                break

        if not matched_Relations:
            return ""
        return "Cognitive Graph Context: " + " | ".join(matched_Relations)
