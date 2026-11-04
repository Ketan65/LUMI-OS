"""NEURAL-VAULT: Local Codebase Indexing & Semantic Vector RAG — Phase 10.

Provides 100% local, sovereign, zero-cloud semantic search across Boss's code repos,
markdown documentation, notes, and system files.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_VAULT_DB = Path("data/vault.db")
IGNORED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    ".gemini",
    ".idea",
    ".vscode",
    "dist",
    "build",
    "backups",
}
INDEXABLE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
    ".json",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".sh",
    ".bat",
    ".ps1",
    ".sql",
}


def tokenize_code(text: str) -> list[str]:
    """Tokenizes code and text, handling camelCase, snake_case, and identifiers."""
    # Split camelCase
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    # Split alphanumeric from non-alphanumeric
    words = re.findall(r"[a-zA-Z0-9_]{2,}", s1)
    tokens: list[str] = []
    for w in words:
        parts = w.lower().split("_")
        for p in parts:
            if len(p) >= 2:
                tokens.append(p)
    return tokens


@dataclass
class SearchResult:
    file_path: str
    chunk_index: int
    start_line: int
    end_line: int
    score: float
    snippet: str


class NeuralVault:
    """Local Codebase Index & Semantic Retrieval Engine."""

    def __init__(self, db_path: str | Path = DEFAULT_VAULT_DB,
                 semantic: bool = False,
                 embed_model: str = "nomic-embed-text"):
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # semantic=True → Ollama embeddings se BM25 ke saath hybrid re-rank
        self.semantic = bool(semantic)
        self.embed_model = embed_model
        self._embed_ok = True          # ek failure = process me BM25-only (no spam)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_ext TEXT,
                    mtime REAL,
                    size INTEGER,
                    indexed_at REAL
                );
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id INTEGER NOT NULL,
                    chunk_index INTEGER,
                    start_line INTEGER,
                    end_line INTEGER,
                    content TEXT,
                    tokens TEXT,
                    token_count INTEGER,
                    embedding BLOB,
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                );
                """
            )
            # migration: purani DBs me embedding column nahi hoga
            chunk_cols = [r[1] for r in conn.execute("PRAGMA table_info(chunks)")]
            if "embedding" not in chunk_cols:
                conn.execute("ALTER TABLE chunks ADD COLUMN embedding BLOB")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_path ON documents(file_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunks(doc_id);")

    # -- semantic embeddings (Ollama, fully local) -------------------------
    def _embed(self, texts: list[str]) -> list[list[float] | None]:
        """Batch embed via Ollama — failure = [None]*n (BM25 fallback, no crash)."""
        if not self.semantic or not self._embed_ok or not texts:
            return [None] * len(texts)
        out: list[list[float] | None] = []
        try:
            import ollama
            for i in range(0, len(texts), 32):
                batch = texts[i:i + 32]
                resp = ollama.embed(model=self.embed_model, input=batch)
                vecs = list(resp.get("embeddings") or [])
                if len(vecs) != len(batch):
                    vecs = [None] * len(batch)
                out.extend(vecs)
            return out
        except Exception:
            self._embed_ok = False      # ollama down → silent BM25-only mode
            return [None] * len(texts)

    def _embed_one(self, text: str) -> list[float] | None:
        return self._embed([text])[0]

    @staticmethod
    def _load_vec(blob: Any) -> list[float] | None:
        if not blob:
            return None
        try:
            return json.loads(blob) if isinstance(blob, (bytes, str)) else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return max(0.0, dot / (na * nb))    # negative similarity = 0 weight

    def chunk_file(self, content: str, chunk_lines: int = 40, overlap: int = 5) -> list[dict[str, Any]]:
        """Splits file content into overlapping line chunks."""
        lines = content.splitlines(keepends=True)
        if not lines:
            return []

        chunks: list[dict[str, Any]] = []
        total_lines = len(lines)
        start = 0
        idx = 0

        while start < total_lines:
            end = min(start + chunk_lines, total_lines)
            chunk_text = "".join(lines[start:end])
            tokens = tokenize_code(chunk_text)
            chunks.append({
                "chunk_index": idx,
                "start_line": start + 1,
                "end_line": end,
                "content": chunk_text,
                "tokens": tokens,
                "token_count": len(tokens),
            })
            idx += 1
            if end >= total_lines:
                break
            start += chunk_lines - overlap

        return chunks

    def index_path(
        self,
        target_path: str | Path = ".",
        recursive: bool = True,
        max_file_size: int = 500_000,
    ) -> dict[str, int]:
        """Indexes or incrementally updates a directory into NeuralVault."""
        root = Path(target_path).resolve()
        if not root.exists():
            return {"indexed": 0, "skipped": 0, "errors": 0}

        files_to_process: list[Path] = []
        if root.is_file():
            if root.suffix.lower() in INDEXABLE_EXTENSIONS:
                files_to_process.append(root)
        else:
            iterator = root.rglob("*") if recursive else root.glob("*")
            for p in iterator:
                if p.is_file():
                    # Check ignored directories
                    if any(part in IGNORED_DIRS for part in p.parts):
                        continue
                    if p.suffix.lower() in INDEXABLE_EXTENSIONS:
                        files_to_process.append(p)

        indexed_count = 0
        skipped_count = 0
        error_count = 0

        with sqlite3.connect(self.db_path) as conn:
            for file_path in files_to_process:
                try:
                    stat = file_path.stat()
                    if stat.st_size > max_file_size:
                        skipped_count += 1
                        continue

                    str_path = str(file_path)
                    # Check existing mtime & size
                    row = conn.execute(
                        "SELECT id, mtime, size FROM documents WHERE file_path = ?",
                        (str_path,),
                    ).fetchone()

                    if row and row[1] == stat.st_mtime and row[2] == stat.st_size:
                        skipped_count += 1
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        error_count += 1
                        continue

                    chunks = self.chunk_file(content)
                    # semantic mode: chunk vectors (local Ollama, fail → None)
                    vecs = self._embed([c["content"] for c in chunks])

                    # Delete old chunks if document existed
                    if row:
                        doc_id = row[0]
                        conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
                        conn.execute(
                            "UPDATE documents SET mtime = ?, size = ?, indexed_at = ? WHERE id = ?",
                            (stat.st_mtime, stat.st_size, time.time(), doc_id),
                        )
                    else:
                        cursor = conn.execute(
                            """INSERT INTO documents (file_path, file_ext, mtime, size, indexed_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (str_path, file_path.suffix.lower(), stat.st_mtime, stat.st_size, time.time()),
                        )
                        doc_id = cursor.lastrowid

                    # Insert chunks
                    for c in chunks:
                        tokens_json = " ".join(c["tokens"])
                        vec = vecs[c["chunk_index"]] if vecs else None
                        emb_blob = json.dumps(vec) if vec else None
                        conn.execute(
                            """INSERT INTO chunks (doc_id, chunk_index, start_line, end_line, content, tokens, token_count, embedding)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                doc_id,
                                c["chunk_index"],
                                c["start_line"],
                                c["end_line"],
                                c["content"],
                                tokens_json,
                                c["token_count"],
                                emb_blob,
                            ),
                        )
                    indexed_count += 1
                except Exception as exc:
                    print(f"[Vault] Error indexing {file_path}: {exc}")
                    error_count += 1

            conn.commit()

        return {"indexed": indexed_count, "skipped": skipped_count, "errors": error_count}

    def add_text(
        self,
        text: str,
        source: str = "personal_memory",
        metadata: dict | None = None,
    ) -> dict:
        """Store a single text note in the vault (personal memory).

        Chunks the text, inserts into documents/chunks tables, and (if semantic)
        computes embeddings. Returns the doc_id and chunk count.
        """
        import time as _time

        now = _time.time()
        doc_path = f"{source}://{int(now)}"
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "INSERT INTO documents (file_path, file_ext, mtime, size, indexed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_path, ".txt", now, len(text.encode("utf-8")), now),
            )
            doc_id = cur.lastrowid

            chunks = self.chunk_file(text)
            for chunk in chunks:
                vec = self._embed_one(chunk["content"]) if self.semantic else None
                conn.execute(
                    "INSERT INTO chunks (doc_id, chunk_index, start_line, end_line, content, tokens, token_count, embedding) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        doc_id,
                        chunk["chunk_index"],
                        chunk["start_line"],
                        chunk["end_line"],
                        chunk["content"],
                        chunk["tokens"],
                        chunk["token_count"],
                        json.dumps(vec) if vec else None,
                    ),
                )
            conn.commit()

        return {"doc_id": doc_id, "chunks": len(chunks), "source": source}

    def search(
        self,
        query: str,
        top_k: int = 5,
        file_filter: str | None = None,
    ) -> list[SearchResult]:
        """Searches indexed codebase and documents using BM25 / TF-IDF scoring."""
        query_tokens = tokenize_code(query)
        if not query_tokens:
            return []

        # Connect to DB
        with sqlite3.connect(self.db_path) as conn:
            # Total chunks
            total_chunks_row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
            total_chunks = total_chunks_row[0] if total_chunks_row else 1
            if total_chunks == 0:
                return []

            # Filter clauses
            where_clause = ""
            params: list[Any] = []
            if file_filter:
                where_clause = "WHERE d.file_path LIKE ?"
                params.append(f"%{file_filter}%")

            # Fetch matching chunks
            sql = f"""
                SELECT c.id, d.file_path, c.chunk_index, c.start_line, c.end_line, c.content, c.tokens, c.token_count, c.embedding
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
                {where_clause}
            """
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        # Score matching chunks with BM25 formula
        k1 = 1.5
        b = 0.75
        avg_dl = sum(r[7] for r in rows) / max(len(rows), 1)

        bm25_pairs: list[tuple[float, Any]] = []
        q_counter = Counter(query_tokens)

        for r in rows:
            chunk_tokens = r[6].split()
            if not chunk_tokens:
                continue

            doc_len = r[7]
            term_freqs = Counter(chunk_tokens)
            score = 0.0

            for q_term, q_weight in q_counter.items():
                f = term_freqs.get(q_term, 0)
                if f > 0:
                    # Term frequency saturation
                    tf_component = (f * (k1 + 1)) / (f + k1 * (1 - b + b * (doc_len / max(avg_dl, 1))))
                    score += tf_component * q_weight

            bm25_pairs.append((score, r))

        # Hybrid path: semantic query embedding available → BM25 + cosine blend
        q_vec = self._embed_one(query) if self.semantic else None
        if q_vec is None:
            # Pure BM25 (legacy behavior — zero semantic dependence)
            scores = [(s, r) for s, r in bm25_pairs if s > 0.0]
        else:
            bm25_max = max((s for s, _ in bm25_pairs), default=0.0) or 1.0
            scores = []
            for bm25, r in bm25_pairs:
                row_vec = self._load_vec(r[8])
                sem = self._cosine(q_vec, row_vec) if row_vec else 0.0
                combined = 0.55 * (bm25 / bm25_max) + 0.45 * sem
                if combined > 0.001:            # keyword match ya meaning match — dono chalein
                    scores.append((combined, r))

        scores.sort(key=lambda x: x[0], reverse=True)
        results: list[SearchResult] = []

        for score, r in scores[:top_k]:
            results.append(
                SearchResult(
                    file_path=r[1],
                    chunk_index=r[2],
                    start_line=r[3],
                    end_line=r[4],
                    score=round(score, 3),
                    snippet=r[5],
                )
            )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Returns indexing statistics for NeuralVault."""
        if not self.db_path.exists():
            return {"documents": 0, "chunks": 0, "db_size_kb": 0}

        with sqlite3.connect(self.db_path) as conn:
            docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

        size_kb = round(self.db_path.stat().st_size / 1024, 1)
        return {"documents": docs, "chunks": chunks, "db_size_kb": size_kb}
