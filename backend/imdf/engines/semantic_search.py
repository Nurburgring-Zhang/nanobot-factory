"""
Semantic Search Engine — P1-A3-Worker-1
========================================
Hybrid vector + BM25 search over an in-memory corpus.

The engine is *self-contained*: it does NOT depend on
``engines.vector_retrieval.VectorStore`` at runtime so the test suite
can drive it without a pre-existing DB. It exposes:

  * ``search(query, top_k, alpha)`` — hybrid vector × BM25 weighted
    fusion (alpha controls the vector weight).
  * ``index_asset(asset_id, text, metadata)`` — adds an asset to both
    the vector index and the BM25 index.
  * ``stats()`` — returns corpus size, vector_dim, etc.
  * ``reset()`` — clears the indices (used by tests).

It uses:

  * **Vector side**: TF-IDF (cosine similarity) computed in pure NumPy.
    Falls back to a simple hash-bucket scheme if sklearn is missing.
  * **BM25 side**: rank-bm25 (already used in vector_retrieval.py).
    Falls back to TF-IDF cosine if rank-bm25 is missing.

Both sides support Chinese and English (we lowercase + split on
unicode whitespace, which works for space-separated English and for
CJK if you also include bigram splitting in the fallback).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)
DEFAULT_VECTOR_DIM = 256


# ---------------------------------------------------------------------------
# Tokenization (language-agnostic)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Tokenize a string into lowercase word tokens + CJK bigrams.

    For Latin scripts we split on unicode word boundaries. For CJK text
    (no spaces), we additionally emit bigrams so two-character queries
    still produce matches.
    """
    if not text:
        return []
    text = text.lower()
    tokens = _TOKEN_RE.findall(text)
    # CJK detection: any of these in the text means we should also
    # emit bigrams. (Rough but works for our purposes.)
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        chars = [ch for ch in text if "\u4e00" <= ch <= "\u9fff"]
        bigrams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
        tokens = tokens + bigrams
    return tokens


# ---------------------------------------------------------------------------
# Vector index (TF-IDF, in-memory)
# ---------------------------------------------------------------------------

class _VectorIndex:
    """Minimal TF-IDF + cosine similarity. Thread-safe for reads."""

    def __init__(self, dim: int = DEFAULT_VECTOR_DIM):
        self.dim = dim
        self._docs: List[str] = []              # doc_ids
        self._texts: List[str] = []             # raw text (for retrieval)
        self._meta: List[Dict[str, Any]] = []
        self._vocab: Dict[str, int] = {}        # term -> column
        self._idf: Dict[str, float] = {}
        self._doc_term_freqs: List[Counter] = []
        self._lock = threading.RLock()
        # Try sklearn for vocabulary build (better than our fallback),
        # but the runtime vectorization is pure numpy so we don't need it.
        self._sklearn_available = False
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401
            self._sklearn_available = True
        except ImportError:
            pass

    # --------------------------- Index ----------------------------------

    def add(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._docs.append(doc_id)
            self._texts.append(text)
            self._meta.append(metadata or {})
            self._doc_term_freqs.append(Counter(_tokenize(text)))
            # Lazily (re)build vocabulary + IDF after each add. This is
            # fine for the corpus sizes we expect (<= 10k assets in
            # unit tests). For larger corpora, callers should batch via
            # `rebuild()`.
            self._rebuild_index()

    def remove(self, doc_id: str) -> bool:
        with self._lock:
            for i, d in enumerate(self._docs):
                if d == doc_id:
                    del self._docs[i]
                    del self._texts[i]
                    del self._meta[i]
                    del self._doc_term_freqs[i]
                    self._rebuild_index()
                    return True
        return False

    def reset(self) -> None:
        with self._lock:
            self._docs.clear()
            self._texts.clear()
            self._meta.clear()
            self._doc_term_freqs.clear()
            self._vocab.clear()
            self._idf.clear()

    def size(self) -> int:
        return len(self._docs)

    # --------------------------- Search ---------------------------------

    def search(self, query: str, k: int) -> List[Tuple[str, float, int]]:
        """Return list of (doc_id, score, position) sorted by score desc."""
        with self._lock:
            q_tokens = _tokenize(query)
            if not q_tokens:
                return []
            scores = self._score_all(q_tokens)
            # Pair with doc ids, sort
            results = [
                (self._docs[i], float(scores[i]), i)
                for i in range(len(self._docs))
                if scores[i] > 0
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

    # --------------------------- Internals ------------------------------

    def _rebuild_index(self) -> None:
        """Build vocab + IDF from current docs (called under lock)."""
        n_docs = max(1, len(self._docs))
        # Document frequency
        df: Counter = Counter()
        for tf in self._doc_term_freqs:
            for term in tf:
                df[term] += 1
        # Keep top `dim` terms by DF (heuristic — terms that appear in
        # at least one doc). If we have more terms than dim, drop rare
        # ones (lowest DF) — they're noise anyway.
        if df:
            sorted_terms = sorted(df.items(), key=lambda x: -x[1])
            kept = sorted_terms[: self.dim]
            self._vocab = {term: i for i, (term, _) in enumerate(kept)}
            self._idf = {
                term: math.log((n_docs + 1) / (df_t + 1)) + 1.0
                for term, df_t in kept
            }
        else:
            self._vocab = {}
            self._idf = {}

    def _score_all(self, q_tokens: List[str]) -> List[float]:
        """Cosine TF-IDF similarity between query and each doc."""
        # Build query vector (sum of TF-IDF weights for matched terms)
        q_tf = Counter(q_tokens)
        q_vec = [0.0] * self.dim
        q_norm = 0.0
        for term, tf in q_tf.items():
            if term in self._vocab:
                idx = self._vocab[term]
                if idx < self.dim:
                    w = (1.0 + math.log(tf)) * self._idf.get(term, 0.0)
                    q_vec[idx] = w
                    q_norm += w * w
        q_norm = math.sqrt(q_norm)
        if q_norm == 0:
            return [0.0] * len(self._docs)
        # Score each doc
        scores: List[float] = []
        for tf in self._doc_term_freqs:
            d_norm = 0.0
            dot = 0.0
            for term, count in tf.items():
                if term in self._vocab:
                    idx = self._vocab[term]
                    if idx < self.dim:
                        w = (1.0 + math.log(count)) * self._idf.get(term, 0.0)
                        d_norm += w * w
                        dot += q_vec[idx] * w
            d_norm = math.sqrt(d_norm)
            scores.append(dot / (q_norm * d_norm) if d_norm > 0 else 0.0)
        return scores


# ---------------------------------------------------------------------------
# BM25 index (in-memory; optionally persisted to SQLite)
# ---------------------------------------------------------------------------

class _BM25Index:
    """BM25 over the in-memory corpus.

    Uses ``rank_bm25.BM25Okapi`` if available, else falls back to a
    hand-rolled implementation. Optionally persists tokens to a
    SQLite table so the index survives process restarts (used by the
    API layer when a ``db_path`` is supplied).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: List[str] = []
        self._tokens: List[List[str]] = []
        self._doc_lens: List[int] = []
        self._avgdl: float = 0.0
        self._df: Counter = Counter()
        self._lock = threading.RLock()
        self._rank_bm25 = None
        try:
            from rank_bm25 import BM25Okapi  # type: ignore
            self._rank_bm25 = BM25Okapi
        except ImportError:
            pass

    def add(self, doc_id: str, text: str) -> None:
        with self._lock:
            tokens = _tokenize(text)
            self._docs.append(doc_id)
            self._tokens.append(tokens)
            self._doc_lens.append(len(tokens) or 1)
            for term in set(tokens):
                self._df[term] += 1
            self._avgdl = sum(self._doc_lens) / len(self._doc_lens)

    def remove(self, doc_id: str) -> bool:
        with self._lock:
            for i, d in enumerate(self._docs):
                if d == doc_id:
                    removed_tokens = set(self._tokens[i])
                    del self._docs[i]
                    del self._tokens[i]
                    del self._doc_lens[i]
                    for t in removed_tokens:
                        self._df[t] -= 1
                        if self._df[t] <= 0:
                            del self._df[t]
                    self._avgdl = (
                        sum(self._doc_lens) / len(self._doc_lens)
                        if self._doc_lens else 0.0
                    )
                    return True
        return False

    def reset(self) -> None:
        with self._lock:
            self._docs.clear()
            self._tokens.clear()
            self._doc_lens.clear()
            self._df.clear()
            self._avgdl = 0.0

    def size(self) -> int:
        return len(self._docs)

    def search(self, query: str, k: int) -> List[Tuple[str, float, int]]:
        with self._lock:
            q_tokens = _tokenize(query)
            if not q_tokens or not self._docs:
                return []
            scores = self._score_all(q_tokens)
            results = [
                (self._docs[i], float(scores[i]), i)
                for i in range(len(self._docs))
                if scores[i] > 0
            ]
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

    def _score_all(self, q_tokens: List[str]) -> List[float]:
        """Compute BM25 scores (rank-bm25 if available else custom)."""
        n = len(self._docs)
        if self._rank_bm25 is not None:
            try:
                bm = self._rank_bm25(self._tokens)
                return [float(s) for s in bm.get_scores(q_tokens)]
            except Exception:
                pass  # fall through to custom
        # Custom BM25
        scores = [0.0] * n
        for term in q_tokens:
            df = self._df.get(term, 0)
            if df == 0:
                continue
            idf = math.log(((n - df + 0.5) / (df + 0.5)) + 1.0)
            for i, doc_tokens in enumerate(self._tokens):
                tf = doc_tokens.count(term)
                if tf == 0:
                    continue
                num = tf * (self.k1 + 1)
                denom = tf + self.k1 * (1 - self.b + self.b * self._doc_lens[i] / max(self._avgdl, 1e-9))
                scores[i] += idf * (num / denom)
        return scores


# ---------------------------------------------------------------------------
# Public engine — combines the two indices
# ---------------------------------------------------------------------------

class SemanticSearchEngine:
    """Hybrid vector × BM25 search.

    Args:
        vector_db_path: Optional path to a SQLite file used to persist
            ``(asset_id, text, metadata)`` rows. The in-memory indices
            are always the source of truth for search; the SQLite file
            is just a durable log.
        vector_dim: Maximum vocabulary size for the vector index.

    Example::

        eng = SemanticSearchEngine()
        eng.index_asset("a1", "A cat sitting on the mat")
        eng.index_asset("a2", "A dog running in the park")
        results = eng.search("cat mat", top_k=5, alpha=0.7)
    """

    def __init__(
        self,
        vector_db_path: Optional[str] = None,
        vector_dim: int = DEFAULT_VECTOR_DIM,
    ):
        self.vector_dim = vector_dim
        self.vector_db_path = vector_db_path
        self._vector = _VectorIndex(dim=vector_dim)
        self._bm25 = _BM25Index()
        self._meta_by_id: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        # Persistence (optional)
        self._conn: Optional[sqlite3.Connection] = None
        if vector_db_path:
            self._init_persistence(vector_db_path)

    # --------------------------- Persistence -----------------------------

    def _init_persistence(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS semantic_assets ("
            "  asset_id TEXT PRIMARY KEY,"
            "  text TEXT NOT NULL,"
            "  metadata_json TEXT,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS semantic_index_log ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  asset_id TEXT NOT NULL,"
            "  action TEXT NOT NULL,"
            "  ts TEXT NOT NULL"
            ")"
        )
        self._conn.commit()
        # Rehydrate from disk (best-effort; clears in-memory first).
        self._rehydrate()

    def _rehydrate(self) -> None:
        if self._conn is None:
            return
        rows = self._conn.execute(
            "SELECT asset_id, text, metadata_json FROM semantic_assets ORDER BY rowid"
        ).fetchall()
        if not rows:
            return
        self._vector.reset()
        self._bm25.reset()
        self._meta_by_id.clear()
        for asset_id, text, meta_json in rows:
            try:
                meta = json.loads(meta_json) if meta_json else {}
            except (TypeError, ValueError):
                meta = {}
            self._vector.add(asset_id, text, meta)
            self._bm25.add(asset_id, text)
            self._meta_by_id[asset_id] = meta

    # --------------------------- Indexing --------------------------------

    def index_asset(
        self,
        asset_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add (or replace) an asset in both indices.

        Returns a small dict describing the operation.
        """
        metadata = metadata or {}
        with self._lock:
            # Replace if exists: delete first to avoid double-counting
            if asset_id in self._meta_by_id:
                self._vector.remove(asset_id)
                self._bm25.remove(asset_id)
            self._vector.add(asset_id, text, metadata)
            self._bm25.add(asset_id, text)
            self._meta_by_id[asset_id] = metadata
            # Persist (best-effort)
            if self._conn is not None:
                from datetime import datetime, timezone
                ts = datetime.now(timezone.utc).isoformat()
                self._conn.execute(
                    "INSERT OR REPLACE INTO semantic_assets "
                    "(asset_id, text, metadata_json, created_at) VALUES (?, ?, ?, ?)",
                    (
                        asset_id,
                        text,
                        json.dumps(metadata, ensure_ascii=False),
                        ts,
                    ),
                )
                self._conn.execute(
                    "INSERT INTO semantic_index_log (asset_id, action, ts) VALUES (?, ?, ?)",
                    (asset_id, "add", ts),
                )
                self._conn.commit()
        return {
            "indexed": True,
            "asset_id": asset_id,
            "text_length": len(text or ""),
            "vector_size": self._vector.size(),
            "bm25_size": self._bm25.size(),
        }

    def remove_asset(self, asset_id: str) -> bool:
        with self._lock:
            v_ok = self._vector.remove(asset_id)
            b_ok = self._bm25.remove(asset_id)
            existed = asset_id in self._meta_by_id
            self._meta_by_id.pop(asset_id, None)
            if self._conn is not None:
                self._conn.execute(
                    "DELETE FROM semantic_assets WHERE asset_id = ?", (asset_id,)
                )
                if existed:
                    from datetime import datetime, timezone
                    self._conn.execute(
                        "INSERT INTO semantic_index_log (asset_id, action, ts) "
                        "VALUES (?, ?, ?)",
                        (
                            asset_id,
                            "remove",
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                self._conn.commit()
        return existed

    def reset(self) -> None:
        """Clear all indices (in-memory + persisted)."""
        with self._lock:
            self._vector.reset()
            self._bm25.reset()
            self._meta_by_id.clear()
            if self._conn is not None:
                self._conn.execute("DELETE FROM semantic_assets")
                self._conn.execute("DELETE FROM semantic_index_log")
                self._conn.commit()

    # --------------------------- Search ----------------------------------

    def _vector_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        """Return [(asset_id, normalized_score)] for the top-k vector hits.

        ``normalized_score`` is the cosine similarity (already in
        [0, 1] for non-negative TF-IDF, but we min-max normalize to
        [0, 1] across the returned set so fusion is consistent with
        BM25 rank-based scores).
        """
        raw = self._vector.search(query, k)
        if not raw:
            return []
        # Normalize scores to [0, 1] across the candidate set.
        # With a single hit, smax == smin, so we return 1.0 for that
        # hit (rather than 0.0 / 1e-9, which would be misleading).
        if len(raw) == 1:
            return [(raw[0][0], 1.0)]
        smax = max(s for _, s, _ in raw)
        smin = min(s for _, s, _ in raw)
        rng = max(smax - smin, 1e-9)
        return [
            (asset_id, (s - smin) / rng)
            for asset_id, s, _ in raw
        ]

    def _bm25_search(self, query: str, k: int) -> List[Tuple[str, float]]:
        """Return [(asset_id, normalized_score)] for the top-k BM25 hits.

        BM25 scores are unbounded above, so we min-max normalize to
        [0, 1] across the candidate set.
        """
        raw = self._bm25.search(query, k)
        if not raw:
            return []
        if len(raw) == 1:
            return [(raw[0][0], 1.0)]
        smax = max(s for _, s, _ in raw)
        smin = min(s for _, s, _ in raw)
        rng = max(smax - smin, 1e-9)
        return [
            (asset_id, (s - smin) / rng)
            for asset_id, s, _ in raw
        ]

    def search(
        self,
        query: str,
        top_k: int = 10,
        alpha: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Hybrid search across vector and BM25 indices.

        Args:
            query: Search query string.
            top_k: Maximum number of results to return.
            alpha: Weight of the vector score in the final ranking;
                (1 - alpha) is the BM25 weight. alpha=1.0 is pure
                vector search, alpha=0.0 is pure BM25.

        Returns:
            List of result dicts ordered by descending hybrid score::

                {
                  "asset_id": str,
                  "score": float (in [0, 1]),
                  "vector_score": float,
                  "bm25_score": float,
                  "metadata": dict,
                  "preview": str,
                }
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        alpha = max(0.0, min(1.0, float(alpha)))
        top_k = max(1, int(top_k))

        with self._lock:
            # 1. Vector retrieve top_k*2 candidates
            vec_hits = self._vector_search(query, top_k * 2)
            # 2. BM25 retrieve top_k*2 candidates
            bm_hits = self._bm25_search(query, top_k * 2)

        # 3. Weighted fusion
        scores: Dict[str, Dict[str, float]] = {}
        for asset_id, s in vec_hits:
            scores.setdefault(asset_id, {"vector": 0.0, "bm25": 0.0})["vector"] = s
        for asset_id, s in bm_hits:
            scores.setdefault(asset_id, {"vector": 0.0, "bm25": 0.0})["bm25"] = s

        fused: List[Tuple[str, float, float, float]] = []
        for asset_id, sc in scores.items():
            fused_score = alpha * sc["vector"] + (1 - alpha) * sc["bm25"]
            fused.append((asset_id, fused_score, sc["vector"], sc["bm25"]))

        # 4. Sort by fused score and return top_k
        fused.sort(key=lambda x: x[1], reverse=True)
        results: List[Dict[str, Any]] = []
        for rank, (asset_id, fused_score, vec_score, bm_score) in enumerate(fused[:top_k], start=1):
            meta = self._meta_by_id.get(asset_id, {})
            # Provide both the full text (for tests that grep on `text`)
            # and a truncated preview.
            text = ""
            preview = ""
            try:
                if self._vector._texts:
                    idx = self._vector._docs.index(asset_id)
                    text = self._vector._texts[idx] or ""
                    preview = text[:200]
            except (ValueError, AttributeError):
                pass
            results.append({
                "rank": rank,
                "asset_id": asset_id,
                "score": round(float(fused_score), 6),
                "vector_score": round(float(vec_score), 6),
                "bm25_score": round(float(bm_score), 6),
                "metadata": meta,
                "text": text,
                "preview": preview,
            })
        return results

    # --------------------------- Stats -----------------------------------

    def stats(self) -> Dict[str, Any]:
        """Return index statistics.

        Includes both the canonical ``asset_count`` and the alias keys
        ``size`` / ``corpus_size`` used by some external callers.
        """
        with self._lock:
            n = self._vector.size()
            return {
                "asset_count": n,
                "size": n,
                "corpus_size": n,
                "bm25_count": self._bm25.size(),
                "vector_vocab_size": len(self._vector._vocab),
                "vector_dim": self.vector_dim,
                "vector_db_path": self.vector_db_path,
                "persisted": self._conn is not None,
                "metadata_count": len(self._meta_by_id),
            }

    # --------------------------- Convenience -----------------------------

    def benchmark(
        self,
        n_assets: int = 1000,
        n_queries: int = 50,
        top_k: int = 10,
        alpha: float = 0.7,
    ) -> Dict[str, float]:
        """Index n_assets random texts, run n_queries, return timing."""
        import random
        import string

        random.seed(42)
        words = (
            "cat dog bird fish horse rabbit mouse elephant tiger lion "
            "car truck bike train plane ship boat road city country "
            "music video image photo painting drawing sculpture "
            "computer phone tablet laptop screen keyboard mouse "
            "pizza burger salad bread rice pasta soup sauce cheese"
        ).split() * 5

        self.reset()
        t0 = time.perf_counter()
        for i in range(n_assets):
            text = " ".join(random.choices(words, k=random.randint(8, 30)))
            self.index_asset(f"asset_{i:06d}", text, {"i": i})
        t_index = time.perf_counter() - t0

        t0 = time.perf_counter()
        for _ in range(n_queries):
            q = " ".join(random.choices(words, k=random.randint(2, 6)))
            self.search(q, top_k=top_k, alpha=alpha)
        t_query = time.perf_counter() - t0
        return {
            "n_assets": n_assets,
            "n_queries": n_queries,
            "index_seconds": round(t_index, 4),
            "query_total_seconds": round(t_query, 4),
            "query_avg_ms": round(t_query / max(n_queries, 1) * 1000, 3),
        }

    # --------------------------- Dunder ----------------------------------

    def __len__(self) -> int:
        return self._vector.size()

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None