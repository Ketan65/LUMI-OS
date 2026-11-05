"""HYBRID-RRF-ENGINE: Sub-10ms Lexical + Dense N-Gram Vector Retrieval with Reciprocal Rank Fusion.

Provides local, zero-download, CPU-native hybrid retrieval combining:
1. Okapi BM25 (k1=1.5, b=0.75) with Robertson-Sparck Jones IDF weighting and identifier sub-tokenization.
2. 256-dimensional L2-normalized Character/Word N-Gram Feature Hashing Vector Embeddings with SWE domain concept projection.
3. Reciprocal Rank Fusion (RRF_score = 1 / (k + rank_bm25) + 1 / (k + rank_vec)) + Exact Symbol Match Boost.
"""

from __future__ import annotations

import math
import re
import zlib
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

EMBEDDING_DIM = 256
RRF_K = 60

# Lightweight SWE & personal-assistant semantic concept clusters.
# Tokens in the same cluster project a shared latent concept feature into the hash embedding
# so paraphrased queries ("auth bug check") align with code ("verify_jwt_token InvalidSignatureError").
_CONCEPT_CLUSTERS: dict[str, str] = {
    # Auth & Security
    "auth": "concept_auth_sec",
    "authenticate": "concept_auth_sec",
    "authentication": "concept_auth_sec",
    "authorize": "concept_auth_sec",
    "authorization": "concept_auth_sec",
    "login": "concept_auth_sec",
    "jwt": "concept_auth_sec",
    "token": "concept_auth_sec",
    "credential": "concept_auth_sec",
    "credentials": "concept_auth_sec",
    "password": "concept_auth_sec",
    "secret": "concept_auth_sec",
    "session": "concept_auth_sec",
    "signature": "concept_auth_sec",
    "permission": "concept_auth_sec",
    "policy": "concept_auth_sec",
    # Bugs, Errors & Diagnostics
    "bug": "concept_error_bug",
    "bugs": "concept_error_bug",
    "error": "concept_error_bug",
    "errors": "concept_error_bug",
    "exception": "concept_error_bug",
    "crash": "concept_error_bug",
    "fail": "concept_error_bug",
    "failure": "concept_error_bug",
    "fault": "concept_error_bug",
    "invalid": "concept_error_bug",
    "fix": "concept_error_bug",
    "repair": "concept_error_bug",
    "heal": "concept_error_bug",
    "debug": "concept_error_bug",
    "traceback": "concept_error_bug",
    # Verification, Testing & Auditing
    "check": "concept_verify_test",
    "verify": "concept_verify_test",
    "validate": "concept_verify_test",
    "validation": "concept_verify_test",
    "audit": "concept_verify_test",
    "inspect": "concept_verify_test",
    "test": "concept_verify_test",
    "pytest": "concept_verify_test",
    "assert": "concept_verify_test",
    "ensure": "concept_verify_test",
    # Storage, Database & Memory
    "db": "concept_storage_db",
    "database": "concept_storage_db",
    "sqlite": "concept_storage_db",
    "sql": "concept_storage_db",
    "store": "concept_storage_db",
    "storage": "concept_storage_db",
    "vault": "concept_storage_db",
    "memory": "concept_storage_db",
    "memories": "concept_storage_db",
    "fact": "concept_storage_db",
    "facts": "concept_storage_db",
    "persist": "concept_storage_db",
    "cache": "concept_storage_db",
    "backup": "concept_storage_db",
    # Search, Indexing & Retrieval
    "search": "concept_search_rag",
    "query": "concept_search_rag",
    "retrieve": "concept_search_rag",
    "retriever": "concept_search_rag",
    "retrieval": "concept_search_rag",
    "index": "concept_search_rag",
    "rank": "concept_search_rag",
    "bm25": "concept_search_rag",
    "vector": "concept_search_rag",
    "embed": "concept_search_rag",
    "embedding": "concept_search_rag",
    "semantic": "concept_search_rag",
    # Code Structure, AST & Graph
    "ast": "concept_code_ast",
    "symbol": "concept_code_ast",
    "function": "concept_code_ast",
    "method": "concept_code_ast",
    "class": "concept_code_ast",
    "module": "concept_code_ast",
    "import": "concept_code_ast",
    "dependency": "concept_code_ast",
    "caller": "concept_code_ast",
    "graph": "concept_code_ast",
    "impact": "concept_code_ast",
    # Execution, Orchestration & Tools
    "run": "concept_exec_agent",
    "execute": "concept_exec_agent",
    "dispatch": "concept_exec_agent",
    "tool": "concept_exec_agent",
    "agent": "concept_exec_agent",
    "orchestrator": "concept_exec_agent",
    "planner": "concept_exec_agent",
    "schedule": "concept_exec_agent",
}

_STOPWORDS = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "what", "all", "can", "when", "where",
    "who", "will", "into", "out", "about", "how", "which", "their", "there",
})


def extract_code_tokens(text: str) -> tuple[list[str], set[str]]:
    """Extracts sub-tokens (camelCase/snake_case split) and exact raw identifiers.

    Returns:
        (sub_tokens, exact_identifiers)
    """
    if not text:
        return [], set()

    # Raw identifiers (snake_case, CamelCase, dotted names, etc.)
    raw_words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text)
    exact_identifiers: set[str] = {w.lower() for w in raw_words if "_" in w or any(c.isupper() for c in w[1:]) or len(w) >= 4}

    # Split camelCase & PascalCase boundaries: "verifyJWTToken" -> "verify JWT Token"
    s1 = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s1)
    words = re.findall(r"[a-zA-Z0-9_]{2,}", s2)

    sub_tokens: list[str] = []
    for w in words:
        w_low = w.lower()
        # If compound snake_case, include both the full identifier and its parts
        if "_" in w_low:
            sub_tokens.append(w_low)
            for part in w_low.split("_"):
                if len(part) >= 2 and part not in _STOPWORDS:
                    sub_tokens.append(part)
        else:
            if len(w_low) >= 2 and w_low not in _STOPWORDS:
                sub_tokens.append(w_low)

    return sub_tokens, exact_identifiers


@dataclass
class HybridRankedDoc:
    """Detailed scoring breakdown for a single ranked document."""
    doc: dict[str, Any]
    rrf_score: float
    bm25_score: float
    vector_score: float
    bm25_rank: int
    vector_rank: int
    exact_boost: float = 0.0
    matched_terms: list[str] = field(default_factory=list)


class HybridRRFEngine:
    """Pure-Python Sub-10ms Hybrid Retrieval Engine (Okapi BM25 + 256-D N-Gram Hash Vectors + RRF)."""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        rrf_k: int = RRF_K,
        dim: int = EMBEDDING_DIM,
        exact_match_boost: float = 0.015,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.rrf_k = rrf_k
        self.dim = dim
        self.exact_match_boost = exact_match_boost

    @staticmethod
    def _hash_feature(feature: str, dim: int = EMBEDDING_DIM) -> tuple[int, float]:
        """Deterministic signed feature hash (Weinberger et al. trick) via CRC32."""
        h = zlib.crc32(feature.encode("utf-8"))
        idx = h % dim
        sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
        return idx, sign

    def compute_embedding(self, text: str) -> list[float]:
        """Computes a 256-dimensional L2-normalized Character/Word N-Gram Feature Hash Embedding."""
        vec = [0.0] * self.dim
        if not text or not text.strip():
            return vec

        sub_tokens, exact_ids = extract_code_tokens(text)
        if not sub_tokens and not exact_ids:
            # Fallback for very short or symbol-heavy strings
            clean = text.strip().lower()
            for i in range(max(1, len(clean) - 2)):
                idx, sign = self._hash_feature(f"c3:{clean[i:i+3]}", self.dim)
                vec[idx] += sign
        else:
            # 1. Exact identifier features (weight = 2.5)
            for ident in exact_ids:
                idx, sign = self._hash_feature(f"id:{ident}", self.dim)
                vec[idx] += sign * 2.5

            # 2. Word unigrams + semantic concept projection + character n-grams
            for i, tok in enumerate(sub_tokens):
                # Word unigram (weight = 2.0)
                idx, sign = self._hash_feature(f"w1:{tok}", self.dim)
                vec[idx] += sign * 2.0

                # Prefix stem (first 4 and 5 chars catch morphological variants: auth/authenticate)
                if len(tok) >= 4:
                    idx_p4, sign_p4 = self._hash_feature(f"p4:{tok[:4]}", self.dim)
                    vec[idx_p4] += sign_p4 * 1.2
                if len(tok) >= 5:
                    idx_p5, sign_p5 = self._hash_feature(f"p5:{tok[:5]}", self.dim)
                    vec[idx_p5] += sign_p5 * 1.2

                # Semantic domain concept projection (weight = 2.2)
                concept = _CONCEPT_CLUSTERS.get(tok)
                if concept:
                    c_idx, c_sign = self._hash_feature(f"sem:{concept}", self.dim)
                    vec[c_idx] += c_sign * 2.2

                # Word bigram (weight = 1.4)
                if i + 1 < len(sub_tokens):
                    bigram = f"w2:{tok}_{sub_tokens[i + 1]}"
                    b_idx, b_sign = self._hash_feature(bigram, self.dim)
                    vec[b_idx] += b_sign * 1.4

                # Character 3-grams and 4-grams with boundary markers (weight = 0.75)
                padded = f"<{tok}>"
                plen = len(padded)
                for j in range(plen - 2):
                    ng3 = padded[j : j + 3]
                    n_idx, n_sign = self._hash_feature(f"c3:{ng3}", self.dim)
                    vec[n_idx] += n_sign * 0.75
                    if j + 4 <= plen:
                        ng4 = padded[j : j + 4]
                        n4_idx, n4_sign = self._hash_feature(f"c4:{ng4}", self.dim)
                        vec[n4_idx] += n4_sign * 0.6

        # L2 Normalization to unit hypersphere
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-12:
            inv_norm = 1.0 / norm
            vec = [v * inv_norm for v in vec]
        return vec

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Computes cosine similarity between two vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        # Vectors produced by compute_embedding are already L2-normalized,
        # but guard against unnormalized external vectors.
        n1 = sum(a * a for a in v1)
        n2 = sum(b * b for b in v2)
        if n1 <= 1e-12 or n2 <= 1e-12:
            return 0.0
        if abs(n1 - 1.0) > 1e-4 or abs(n2 - 1.0) > 1e-4:
            dot /= math.sqrt(n1 * n2)
        return max(0.0, min(1.0, dot))

    def compute_bm25_scores(
        self,
        query_tokens: list[str],
        doc_token_lists: list[list[str]],
    ) -> list[float]:
        """Computes Okapi BM25 scores across a corpus of tokenized documents."""
        n_docs = len(doc_token_lists)
        if n_docs == 0 or not query_tokens:
            return [0.0] * n_docs

        doc_lens = [len(tokens) for tokens in doc_token_lists]
        avg_dl = sum(doc_lens) / max(n_docs, 1)
        if avg_dl <= 0:
            avg_dl = 1.0

        # Document frequency per unique query term
        q_counter = Counter(query_tokens)
        unique_q = list(q_counter.keys())
        doc_Counters = [Counter(tokens) for tokens in doc_token_lists]

        idf: dict[str, float] = {}
        for term in unique_q:
            df = sum(1 for c in doc_Counters if term in c)
            # Robertson-Sparck Jones smoothed IDF (always positive)
            idf[term] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

        scores: list[float] = []
        for idx, t_counts in enumerate(doc_Counters):
            dl = doc_lens[idx]
            if dl == 0:
                scores.append(0.0)
                continue
            score = 0.0
            norm_factor = self.k1 * (1.0 - self.b + self.b * (dl / avg_dl))
            for q_term, q_qf in q_counter.items():
                f = t_counts.get(q_term, 0)
                if f > 0:
                    tf_sat = (f * (self.k1 + 1.0)) / (f + norm_factor)
                    score += idf[q_term] * tf_sat * q_qf
            scores.append(score)

        return scores

    def rank_documents(
        self,
        query: str,
        docs: list[dict[str, Any]],
        text_key: str = "content",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Ranks documents by fusing Okapi BM25 and 256-D N-Gram Vector similarity via RRF.

        Args:
            query: Search query (exact code identifier or natural language).
            docs: List of document dictionaries.
            text_key: Key in each dict holding the text to rank (falls back to composite keys).
            top_k: Maximum number of top-ranked documents to return.

        Returns:
            List of top_k document dicts enriched with `rrf_score`, `bm25_score`, `vector_score`,
            `bm25_rank`, `vector_rank`, and `exact_match_boost`.
        """
        if not docs or not query or not query.strip():
            return []

        q_clean = query.strip()
        q_low = q_clean.lower()
        q_tokens, q_exact_ids = extract_code_tokens(q_clean)
        q_vec = self.compute_embedding(q_clean)

        doc_texts: list[str] = []
        doc_token_lists: list[list[str]] = []
        doc_exact_sets: list[set[str]] = []
        doc_vecs: list[list[float]] = []

        for d in docs:
            raw_text = str(d.get(text_key) or "")
            if not raw_text:
                # Fallback for facts or multi-field dicts
                parts = [str(d.get(k, "")) for k in ("key", "value", "category", "file_path", "snippet") if d.get(k)]
                raw_text = " ".join(parts)
            doc_texts.append(raw_text)

            tokens, exact_ids = extract_code_tokens(raw_text)
            doc_token_lists.append(tokens)
            doc_exact_sets.append(exact_ids)

            # Use precomputed 256-dim embedding if stored on the dict and matching dimension
            pre_vec = d.get("embedding")
            if isinstance(pre_vec, list) and len(pre_vec) == self.dim:
                doc_vecs.append(pre_vec)
            else:
                doc_vecs.append(self.compute_embedding(raw_text))

        # 1. Lexical Okapi BM25 scores
        bm25_scores = self.compute_bm25_scores(q_tokens, doc_token_lists)

        # 2. Dense N-Gram Vector cosine similarity scores
        vec_scores = [self.cosine_similarity(q_vec, dv) for dv in doc_vecs]

        # 3. Compute 1-based ranks for BM25 and Vector modalities
        n = len(docs)
        bm25_order = sorted(range(n), key=lambda i: bm25_scores[i], reverse=True)
        vec_order = sorted(range(n), key=lambda i: vec_scores[i], reverse=True)

        bm25_ranks = [0] * n
        vec_ranks = [0] * n
        for rank_idx, doc_idx in enumerate(bm25_order, start=1):
            bm25_ranks[doc_idx] = rank_idx
        for rank_idx, doc_idx in enumerate(vec_order, start=1):
            vec_ranks[doc_idx] = rank_idx

        # 4. Reciprocal Rank Fusion + Exact Identifier / Substring Boost
        fused_results: list[tuple[float, int, dict[str, Any]]] = []
        for i, d in enumerate(docs):
            # Only grant BM25 RRF contribution if there is a positive lexical signal,
            # or if vector similarity is non-trivial.
            bm25_s = bm25_scores[i]
            vec_s = vec_scores[i]
            if bm25_s <= 0.0 and vec_s <= 0.02:
                continue

            r_bm25 = bm25_ranks[i]
            r_vec = vec_ranks[i]

            rrf_bm25 = (1.0 / (self.rrf_k + r_bm25)) if bm25_s > 0.0 else 0.0
            rrf_vec = (1.0 / (self.rrf_k + r_vec)) if vec_s > 0.0 else 0.0

            # Exact symbol / phrase boost
            boost = 0.0
            raw_low = doc_texts[i].lower()
            if len(q_low) >= 3 and q_low in raw_low:
                boost += self.exact_match_boost
            if q_exact_ids and (q_exact_ids & doc_exact_sets[i]):
                boost += self.exact_match_boost * len(q_exact_ids & doc_exact_sets[i])

            total_rrf = rrf_bm25 + rrf_vec + boost

            enriched = dict(d)
            enriched["rrf_score"] = round(total_rrf, 6)
            enriched["bm25_score"] = round(bm25_s, 4)
            enriched["vector_score"] = round(vec_s, 4)
            enriched["bm25_rank"] = r_bm25
            enriched["vector_rank"] = r_vec
            enriched["exact_match_boost"] = round(boost, 6)
            fused_results.append((total_rrf, i, enriched))

        # Sort by RRF score descending, breaking ties by BM25 + vector score
        fused_results.sort(
            key=lambda item: (
                item[0],
                item[2]["bm25_score"] + item[2]["vector_score"],
            ),
            reverse=True,
        )

        return [item[2] for item in fused_results[: max(1, top_k)]]
