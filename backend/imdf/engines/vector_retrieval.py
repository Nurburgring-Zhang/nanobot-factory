"""
F1.14: Multimodal Vector Retrieval Engine
=========================================
Lightweight vector storage using SQLite + local embeddings (no external service needed).

Features:
  - Text: BM25 + TF-IDF keyword vectors (rank-bm25 + sklearn)
  - Image: Perceptual hash (pHash) + Dominant Color fingerprint
  - Hybrid: BM25 + FTS5 combined retrieval
  - Index management: create_index, insert_vectors, search

Collections stored in SQLite: data/vector_store.db
"""

import os
import json
import sqlite3
import hashlib
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_VECTOR_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "vector_store.db"
)
# Ensure absolute path
DEFAULT_VECTOR_DB = os.path.abspath(DEFAULT_VECTOR_DB)

VECTOR_DIM_TEXT = 256      # TF-IDF vocabulary dimension (truncated)
VECTOR_DIM_IMAGE = 128     # pHash(64) + color histogram(64)


# ============================================================================
# Image Fingerprint (pHash + Dominant Color)
# ============================================================================

class ImageFingerprint:
    """Perceptual image hashing and color fingerprint.

    Uses Average Hash (aHash) for similarity + Dominant Color histogram
    for color-based retrieval. No deep learning — pure Pillow.
    """

    @staticmethod
    def average_hash(image_path: str, hash_size: int = 8) -> np.ndarray:
        """Compute Average Hash (aHash) for an image.

        Returns a binary vector of size hash_size*hash_size (typically 64).
        """
        try:
            from PIL import Image
            img = Image.open(image_path).convert('L')  # grayscale
            img = img.resize((hash_size, hash_size), Image.LANCZOS)
            pixels = np.array(img, dtype=np.float64)
            avg = pixels.mean()
            hash_bits = (pixels > avg).flatten().astype(np.uint8)
            return hash_bits
        except Exception as e:
            logger.warning(f"average_hash failed for {image_path}: {e}")
            return np.zeros(hash_size * hash_size, dtype=np.uint8)

    @staticmethod
    def dct_hash(image_path: str, hash_size: int = 8) -> np.ndarray:
        """Compute DCT-based pHash for better robustness.

        Returns a binary vector of size hash_size*hash_size.
        """
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(image_path).convert('L')
            img = img.resize((hash_size * 4, hash_size * 4), Image.LANCZOS)
            pixels = np.array(img, dtype=np.float64)

            # 2D DCT
            dct = ImageFingerprint._dct2d(pixels)
            # Keep top-left hash_size x hash_size
            dct_low = dct[:hash_size, :hash_size]
            median = np.median(dct_low)
            hash_bits = (dct_low > median).flatten().astype(np.uint8)
            return hash_bits
        except Exception as e:
            logger.warning(f"dct_hash failed for {image_path}: {e}")
            return np.zeros(hash_size * hash_size, dtype=np.uint8)

    @staticmethod
    def _dct2d(a: np.ndarray) -> np.ndarray:
        """2D Discrete Cosine Transform."""
        from scipy.fftpack import dct
        return dct(dct(a.T, norm='ortho').T, norm='ortho')

    @staticmethod
    def dominant_colors(image_path: str, n_colors: int = 8) -> np.ndarray:
        """Extract dominant color histogram from an image.

        Returns a normalized histogram vector of size n_colors*3 (RGB).
        """
        try:
            from PIL import Image
            img = Image.open(image_path).convert('RGB')
            img = img.resize((32, 32), Image.LANCZOS)
            pixels = np.array(img, dtype=np.float64).reshape(-1, 3)

            # Simple approach: average color of grid cells
            grid = int(np.sqrt(n_colors))
            if grid * grid != n_colors:
                grid = int(np.ceil(np.sqrt(n_colors)))

            # Resize to grid x grid to get dominant region colors
            img_small = Image.fromarray(pixels.reshape(32, 32, 3).astype(np.uint8))
            img_small = img_small.resize((grid, grid), Image.LANCZOS)
            cell_colors = np.array(img_small, dtype=np.float64).reshape(-1, 3)

            # Ensure exactly n_colors * 3 output
            result = np.zeros(n_colors * 3, dtype=np.float64)
            flat_colors = cell_colors.flatten()
            copy_len = min(len(flat_colors), n_colors * 3)
            result[:copy_len] = flat_colors[:copy_len]

            # Normalize
            result /= 255.0
            return result
        except Exception as e:
            logger.warning(f"dominant_colors failed for {image_path}: {e}")
            return np.zeros(n_colors * 3, dtype=np.float64)

    @staticmethod
    def fingerprint(image_path: str, dim: int = VECTOR_DIM_IMAGE) -> np.ndarray:
        """Compute full image fingerprint: pHash + dominant colors.

        Args:
            image_path: Path to image file.
            dim: Target output dimension.

        Returns:
            Normalized float64 vector of length `dim`.
        """
        # Try DCT first, fallback to average
        try:
            hash_vec = ImageFingerprint.dct_hash(image_path, hash_size=8)
        except Exception:
            hash_vec = ImageFingerprint.average_hash(image_path, hash_size=8)

        color_vec = ImageFingerprint.dominant_colors(image_path, n_colors=8)

        # Concatenate: 64-bit hash + 24-dim color
        combined = np.concatenate([hash_vec.astype(np.float64), color_vec])

        # Pad or truncate to target dim
        if len(combined) < dim:
            combined = np.pad(combined, (0, dim - len(combined)), 'constant')
        elif len(combined) > dim:
            combined = combined[:dim]

        # Normalize
        norm = np.linalg.norm(combined)
        if norm > 0:
            combined = combined / norm

        return combined


# ============================================================================
# Text Vectorizer (BM25 + TF-IDF)
# ============================================================================

class TextVectorizer:
    """Keyword-based text vectorization using BM25 + TF-IDF.

    No external embedding service needed. Uses:
      - scikit-learn TfidfVectorizer for initial vocabulary
      - rank-bm25 for BM25 scoring
    """

    def __init__(self, max_features: int = VECTOR_DIM_TEXT):
        self.max_features = max_features
        self._tfidf = None
        self._vocabulary: Dict[str, int] = {}
        self._idf: Dict[str, float] = {}
        self._fitted = False

        # Lazy import
        self._sklearn_available = False
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._TfidfVectorizer = TfidfVectorizer
            self._sklearn_available = True
        except ImportError:
            logger.warning("scikit-learn not available; falling back to simple TF")

    def fit(self, documents: List[str]) -> None:
        """Build vocabulary / IDF from a corpus."""
        if not documents:
            return

        if self._sklearn_available:
            self._tfidf = self._TfidfVectorizer(
                max_features=self.max_features,
                stop_words='english',
                lowercase=True,
                norm='l2',
            )
            self._tfidf.fit(documents)
            self._vocabulary = self._tfidf.vocabulary_
            idf_array = self._tfidf.idf_
            for term, idx in self._vocabulary.items():
                if idx < len(idf_array):
                    self._idf[term] = float(idf_array[idx])
        else:
            # Simple TF vocabulary builder
            word_counts: Dict[str, int] = {}
            for doc in documents:
                for word in doc.lower().split():
                    word = word.strip('.,!?;:()[]{}"\'')
                    if len(word) > 1:
                        word_counts[word] = word_counts.get(word, 0) + 1

            # Sort by frequency, keep top max_features
            sorted_words = sorted(word_counts.items(), key=lambda x: -x[1])[:self.max_features]
            self._vocabulary = {w: i for i, (w, _) in enumerate(sorted_words)}
            # Simple IDF
            n_docs = len(documents)
            for word in self._vocabulary:
                df = sum(1 for doc in documents if word in doc.lower())
                self._idf[word] = max(0.1, np.log((n_docs + 1) / (df + 1)))

        self._fitted = True

    def vectorize(self, text: str) -> np.ndarray:
        """Convert a text string into a sparse vector (TF-IDF weights)."""
        if not self._fitted:
            # If not fitted, just return zeros
            return np.zeros(self.max_features, dtype=np.float64)

        vec = np.zeros(self.max_features, dtype=np.float64)
        words = text.lower().split()
        for word in words:
            word = word.strip('.,!?;:()[]{}"\'')
            if word in self._vocabulary:
                idx = self._vocabulary[word]
                if idx < self.max_features:
                    tf = 1.0  # simplified TF (binary or count)
                    idf = self._idf.get(word, 1.0)
                    vec[idx] = tf * idf

        # Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def bm25_score(self, query: str, doc: str) -> float:
        """Compute BM25 score between query and a document."""
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [doc.lower().split()]
            tokenized_query = query.lower().split()
            bm25 = BM25Okapi(tokenized)
            scores = bm25.get_scores(tokenized_query)
            return float(scores[0])
        except ImportError:
            # Fallback: cosine similarity of TF-IDF vectors
            q_vec = self.vectorize(query)
            d_vec = self.vectorize(doc)
            return float(np.dot(q_vec, d_vec))


# ============================================================================
# Vector Store (SQLite-backed)
# ============================================================================

@dataclass
class VectorSearchResult:
    """A single search result."""
    doc_id: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_type: str = "text"
    preview: str = ""


class VectorStore:
    """SQLite-backed vector storage for multimodal retrieval.

    Stores vectors as JSON arrays in SQLite for simplicity.
    Supports cosine similarity search.
    """

    def __init__(self, db_path: str = DEFAULT_VECTOR_DB):
        self.db_path = db_path
        self._text_vectorizer = TextVectorizer()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    name TEXT PRIMARY KEY,
                    dimension INTEGER NOT NULL,
                    vector_type TEXT DEFAULT 'float32',
                    created_at TEXT NOT NULL,
                    doc_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_name TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    metadata_json TEXT DEFAULT '{}',
                    content_type TEXT DEFAULT 'text',
                    content_preview TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(collection_name, doc_id),
                    FOREIGN KEY(collection_name) REFERENCES collections(name)
                )
            """)
            # Index for fast collection lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_vectors_collection
                ON vectors(collection_name)
            """)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Index / Collection Management
    # ------------------------------------------------------------------

    def create_index(self, collection: str, dimension: int,
                     vector_type: str = "float32") -> Dict[str, Any]:
        """Create a new vector collection/index.

        Args:
            collection: Collection name (unique identifier).
            dimension: Vector dimension.
            vector_type: Data type of vectors (default: float32).

        Returns:
            Status dict.
        """
        conn = self._get_conn()
        try:
            existing = conn.execute(
                "SELECT name FROM collections WHERE name = ?", (collection,)
            ).fetchone()
            if existing:
                return {"success": True, "message": f"Collection '{collection}' already exists",
                        "collection": collection, "dimension": dimension}

            conn.execute(
                "INSERT INTO collections (name, dimension, vector_type, created_at) "
                "VALUES (?, ?, ?, ?)",
                (collection, dimension, vector_type, datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            return {"success": True, "message": f"Created collection '{collection}'",
                    "collection": collection, "dimension": dimension}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def list_indices(self) -> List[Dict[str, Any]]:
        """List all collections."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT name, dimension, vector_type, created_at, doc_count FROM collections"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def delete_index(self, collection: str) -> Dict[str, Any]:
        """Delete a collection and all its vectors."""
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM vectors WHERE collection_name = ?", (collection,))
            conn.execute("DELETE FROM collections WHERE name = ?", (collection,))
            conn.commit()
            return {"success": True, "message": f"Deleted collection '{collection}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Insert Vectors
    # ------------------------------------------------------------------

    def insert_vectors(self, collection: str,
                       vectors: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Insert vectors into a collection.

        Each item in `vectors` should be:
          {
            "doc_id": str,         # unique document identifier
            "vector": List[float], # the embedding vector
            "metadata": dict,      # optional metadata
            "content_type": str,   # "text", "image", "audio"
            "content_preview": str # short preview text
          }

        Returns:
            Status dict with count of inserted vectors.
        """
        conn = self._get_conn()
        try:
            # Ensure collection exists
            coll = conn.execute(
                "SELECT name, dimension FROM collections WHERE name = ?", (collection,)
            ).fetchone()

            if not coll:
                # Auto-create collection from first vector
                dim = len(vectors[0]["vector"]) if vectors else 256
                conn.execute(
                    "INSERT INTO collections (name, dimension, vector_type, created_at) "
                    "VALUES (?, ?, 'float32', ?)",
                    (collection, dim, datetime.now(timezone.utc).isoformat())
                )

            inserted = 0
            updated = 0
            for item in vectors:
                vector_json = json.dumps(item["vector"])
                metadata_json = json.dumps(item.get("metadata", {}))
                content_type = item.get("content_type", "text")
                content_preview = item.get("content_preview", "")
                doc_id = item["doc_id"]

                existing = conn.execute(
                    "SELECT id FROM vectors WHERE collection_name = ? AND doc_id = ?",
                    (collection, doc_id)
                ).fetchone()

                if existing:
                    conn.execute(
                        "UPDATE vectors SET vector_json=?, metadata_json=?, "
                        "content_type=?, content_preview=?, created_at=? "
                        "WHERE collection_name=? AND doc_id=?",
                        (vector_json, metadata_json, content_type, content_preview,
                         datetime.now(timezone.utc).isoformat(), collection, doc_id)
                    )
                    updated += 1
                else:
                    conn.execute(
                        "INSERT INTO vectors (collection_name, doc_id, vector_json, "
                        "metadata_json, content_type, content_preview, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (collection, doc_id, vector_json, metadata_json,
                         content_type, content_preview, datetime.now(timezone.utc).isoformat())
                    )
                    inserted += 1

            # Update doc count
            count = conn.execute(
                "SELECT COUNT(*) FROM vectors WHERE collection_name = ?", (collection,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE collections SET doc_count = ? WHERE name = ?",
                (count, collection)
            )
            conn.commit()

            return {"success": True, "inserted": inserted, "updated": updated,
                    "total_in_collection": count}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, collection: str, query: Any,
               top_k: int = 10) -> List[VectorSearchResult]:
        """Search for similar vectors in a collection.

        Args:
            collection: Collection name to search in.
            query: Query vector (List[float]) or text string for text collections.
            top_k: Number of top results to return.

        Returns:
            List of VectorSearchResult objects sorted by score descending.
        """
        conn = self._get_conn()
        try:
            # Get all vectors in collection
            rows = conn.execute(
                "SELECT doc_id, vector_json, metadata_json, content_type, content_preview "
                "FROM vectors WHERE collection_name = ?",
                (collection,)
            ).fetchall()

            if not rows:
                return []

            # Parse vectors
            db_docs = []
            db_vectors = []
            for row in rows:
                try:
                    vec = np.array(json.loads(row["vector_json"]), dtype=np.float64)
                    db_vectors.append(vec)
                    db_docs.append({
                        "doc_id": row["doc_id"],
                        "metadata": json.loads(row["metadata_json"]),
                        "content_type": row["content_type"],
                        "content_preview": row["content_preview"],
                    })
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse vector for doc_id={row['doc_id']}: {e}")

            if not db_vectors:
                return []

            # Convert query to vector
            if isinstance(query, str):
                # Text query — use TF-IDF vectorizer
                query_vec = self._text_vectorizer.vectorize(query)
            elif isinstance(query, (list, np.ndarray)):
                query_vec = np.array(query, dtype=np.float64)
            else:
                raise ValueError(f"Unsupported query type: {type(query)}")

            # Normalize query vector
            norm = np.linalg.norm(query_vec)
            if norm > 0:
                query_vec = query_vec / norm

            # Cosine similarity search
            db_matrix = np.array(db_vectors, dtype=np.float64)
            # Normalize all DB vectors
            db_norms = np.linalg.norm(db_matrix, axis=1, keepdims=True)
            db_norms[db_norms == 0] = 1.0
            db_matrix = db_matrix / db_norms

            scores = np.dot(db_matrix, query_vec)

            # Get top-k indices
            if top_k >= len(scores):
                top_indices = np.argsort(-scores)
            else:
                top_indices = np.argpartition(-scores, top_k)[:top_k]
                top_indices = top_indices[np.argsort(-scores[top_indices])]

            results = []
            for idx in top_indices:
                if scores[idx] > 0:  # Only return positive matches
                    doc = db_docs[idx]
                    results.append(VectorSearchResult(
                        doc_id=doc["doc_id"],
                        score=float(scores[idx]),
                        metadata=doc["metadata"],
                        content_type=doc["content_type"],
                        preview=doc["content_preview"],
                    ))

            return results
        finally:
            conn.close()

    def delete_vectors(self, collection: str, doc_ids: List[str]) -> Dict[str, Any]:
        """Delete specific vectors from a collection."""
        conn = self._get_conn()
        try:
            deleted = 0
            for doc_id in doc_ids:
                cursor = conn.execute(
                    "DELETE FROM vectors WHERE collection_name = ? AND doc_id = ?",
                    (collection, doc_id)
                )
                deleted += cursor.rowcount

            # Update count
            count = conn.execute(
                "SELECT COUNT(*) FROM vectors WHERE collection_name = ?", (collection,)
            ).fetchone()[0]
            conn.execute(
                "UPDATE collections SET doc_count = ? WHERE name = ?",
                (count, collection)
            )
            conn.commit()
            return {"success": True, "deleted": deleted}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()


# ============================================================================
# Multimodal Retriever (High-level API)
# ============================================================================

class MultimodalRetriever:
    """High-level multimodal search combining vector + FTS5 + image fingerprinting.

    Usage:
        retriever = MultimodalRetriever()

        # Index text documents
        retriever.index_text("my_corpus", docs, metadata_list)

        # Index images
        retriever.index_images("images", image_paths, metadata_list)

        # Search
        results = retriever.search("my_corpus", "search query", top_k=10)
        image_results = retriever.search_images("images", "/path/to/query.jpg", top_k=5)
    """

    # Default collection names
    TEXT_COLLECTION = "text_index"
    IMAGE_COLLECTION = "image_index"
    HYBRID_COLLECTION = "hybrid_index"

    def __init__(self, vector_db_path: str = DEFAULT_VECTOR_DB,
                 fts_db_path: str = None):
        self.store = VectorStore(vector_db_path)
        self.text_vectorizer = TextVectorizer()

        # FTS database path
        if fts_db_path is None:
            fts_db_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "data", "imdf.db"
            )
            fts_db_path = os.path.abspath(fts_db_path)
        self.fts_db_path = fts_db_path

        # Ensure default collections
        for coll, dim in [(self.TEXT_COLLECTION, VECTOR_DIM_TEXT),
                           (self.IMAGE_COLLECTION, VECTOR_DIM_IMAGE),
                           (self.HYBRID_COLLECTION, VECTOR_DIM_TEXT)]:
            self.store.create_index(coll, dim)

    # ------------------------------------------------------------------
    # Text Indexing
    # ------------------------------------------------------------------

    def index_text(self, collection: str, documents: List[str],
                   metadata_list: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Index text documents into vector store.

        Args:
            collection: Collection name.
            documents: List of text strings.
            metadata_list: Optional list of metadata dicts (same length).

        Returns:
            Status dict.
        """
        if metadata_list is None:
            metadata_list = [{}] * len(documents)

        # Fit vectorizer on documents
        self.text_vectorizer.fit(documents)

        vectors = []
        for i, doc in enumerate(documents):
            vec = self.text_vectorizer.vectorize(doc)
            doc_id = hashlib.md5(doc.encode()).hexdigest()[:16]
            meta = metadata_list[i] if i < len(metadata_list) else {}
            meta["original_text"] = doc[:200]  # Store preview

            vectors.append({
                "doc_id": doc_id,
                "vector": vec.tolist(),
                "metadata": meta,
                "content_type": "text",
                "content_preview": doc[:200],
            })

        result = self.store.insert_vectors(collection, vectors)

        # Also fit the default text collection
        if collection != self.TEXT_COLLECTION:
            all_docs = self._get_all_text_docs(self.TEXT_COLLECTION)
            all_docs.extend(documents)
            self.text_vectorizer.fit(all_docs)

        return result

    def _get_all_text_docs(self, collection: str) -> List[str]:
        """Get all text documents from a collection for refitting."""
        conn = self.store._get_conn()
        try:
            rows = conn.execute(
                "SELECT content_preview FROM vectors WHERE collection_name = ? AND content_type = 'text'",
                (collection,)
            ).fetchall()
            return [r["content_preview"] for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Image Indexing
    # ------------------------------------------------------------------

    def index_images(self, collection: str, image_paths: List[str],
                     metadata_list: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Index images by computing pHash + color fingerprints.

        Args:
            collection: Collection name.
            image_paths: List of paths to image files.
            metadata_list: Optional list of metadata dicts.

        Returns:
            Status dict.
        """
        if metadata_list is None:
            metadata_list = [{}] * len(image_paths)

        vectors = []
        for i, path in enumerate(image_paths):
            if not os.path.exists(path):
                logger.warning(f"Image not found: {path}")
                continue

            fp = ImageFingerprint.fingerprint(path, VECTOR_DIM_IMAGE)
            doc_id = hashlib.md5(path.encode()).hexdigest()[:16]
            meta = metadata_list[i] if i < len(metadata_list) else {}
            meta["file_path"] = path
            meta["filename"] = os.path.basename(path)

            vectors.append({
                "doc_id": doc_id,
                "vector": fp.tolist(),
                "metadata": meta,
                "content_type": "image",
                "content_preview": path,
            })

        if not vectors:
            return {"success": False, "error": "No valid images found"}

        return self.store.insert_vectors(collection, vectors)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, collection: str, query: str, top_k: int = 10,
               search_type: str = "vector") -> List[Dict[str, Any]]:
        """Unified search across text and images.

        Args:
            collection: Collection to search.
            query: Text query string.
            top_k: Number of results.
            search_type: "vector", "fts5", or "hybrid".

        Returns:
            List of result dicts.
        """
        results = []

        if search_type in ("vector", "hybrid"):
            # Use the retriever's vectorizer (fitted during index_text)
            query_vec = self.text_vectorizer.vectorize(query)
            vec_results = self.store.search(collection, query_vec.tolist(), top_k)
            for r in vec_results:
                results.append({
                    "doc_id": r.doc_id,
                    "score": r.score,
                    "content_type": r.content_type,
                    "preview": r.preview[:200] if r.preview else "",
                    "metadata": r.metadata,
                    "source": "vector",
                })

        if search_type in ("fts5", "hybrid"):
            fts_results = self._fts5_search(query, top_k)
            # Merge with existing results
            seen_ids = {r["doc_id"] for r in results}
            for r in fts_results:
                if r["doc_id"] not in seen_ids:
                    results.append(r)

        # Sort by score descending
        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results[:top_k]

    def search_images(self, collection: str, query_image_path: str,
                      top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar images using image fingerprint.

        Args:
            collection: Image collection name.
            query_image_path: Path to query image.
            top_k: Number of results.

        Returns:
            List of result dicts with similarity scores.
        """
        if not os.path.exists(query_image_path):
            return [{"error": f"Query image not found: {query_image_path}"}]

        query_fp = ImageFingerprint.fingerprint(query_image_path, VECTOR_DIM_IMAGE)
        vec_results = self.store.search(collection, query_fp.tolist(), top_k)

        return [
            {
                "doc_id": r.doc_id,
                "score": r.score,
                "content_type": r.content_type,
                "preview": r.preview,
                "metadata": r.metadata,
                "source": "vector",
            }
            for r in vec_results
        ]

    # ------------------------------------------------------------------
    # FTS5 Integration
    # ------------------------------------------------------------------

    def _fts5_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search using SQLite FTS5 (from search_engine.py)."""
        try:
            from engines.search_engine import FTSHelper
            fts = FTSHelper(self.fts_db_path)
            results = fts.search(query, limit)
            fts.close()

            return [
                {
                    "doc_id": str(r.get("rowid", r.get("id", ""))),
                    "score": float(r.get("rank", 999)),
                    "content_type": "text",
                    "preview": str(r)[:200],
                    "metadata": dict(r),
                    "source": "fts5",
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"FTS5 search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Hybrid Search (BM25 + FTS5 combination)
    # ------------------------------------------------------------------

    def hybrid_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Combine vector (BM25/TF-IDF) + FTS5 results with reciprocal rank fusion.

        Args:
            query: Search query string.
            top_k: Number of results.

        Returns:
            Merged and ranked results.
        """
        # Get results from both sources
        vec_results = self.search(self.TEXT_COLLECTION, query, top_k * 2, "vector")
        fts_results = self._fts5_search(query, top_k * 2)

        # Reciprocal Rank Fusion
        scores: Dict[str, float] = {}
        metadata: Dict[str, Dict] = {}
        previews: Dict[str, str] = {}

        k = 60  # RRF constant

        for rank, r in enumerate(vec_results):
            doc_id = r["doc_id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            metadata[doc_id] = r.get("metadata", {})
            previews[doc_id] = r.get("preview", "")

        for rank, r in enumerate(fts_results):
            doc_id = r["doc_id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            if doc_id not in metadata:
                metadata[doc_id] = r.get("metadata", {})
            if doc_id not in previews:
                previews[doc_id] = r.get("preview", "")

        # Sort by RRF score
        sorted_ids = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

        return [
            {
                "doc_id": doc_id,
                "score": round(score, 4),
                "preview": previews.get(doc_id, "")[:200],
                "metadata": metadata.get(doc_id, {}),
                "source": "hybrid",
            }
            for doc_id, score in sorted_ids
        ]


# ============================================================================
# Convenience: Global Instance
# ============================================================================

_retriever: Optional[MultimodalRetriever] = None


def get_retriever() -> MultimodalRetriever:
    """Get or create the global MultimodalRetriever instance."""
    global _retriever
    if _retriever is None:
        _retriever = MultimodalRetriever()
    return _retriever
