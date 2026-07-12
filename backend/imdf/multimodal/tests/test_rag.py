"""P10-B: Tests for rag.py → embedding.py (1024-dim unified space) integration.

Verifies:
1. MultimodalRAG + VectorStore use the new ``MultiModalEmbedder`` (1024-dim) interface
   via the ``get_embedding`` shim — not the old 512-dim ``MultimodalEmbedder``.
2. Indexing + search round-trip works for text refs.
3. Vector dim is 1024 (UNIFIED_DIM).
4. Cosine similarity is preserved (same text → high score).
"""
from __future__ import annotations

import sys
from pathlib import Path

# allow running from anywhere
BACKEND = Path(__file__).resolve().parent.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest

from multimodal.embedding import (
    MultiModalEmbedder,
    UNIFIED_DIM,
    get_embedding,
    get_global_embedder,
)
from multimodal.embedders import Embedding
from multimodal.rag import MultimodalRAG, VectorStore
from multimodal.types import MediaRef, ModalKind


# ── 1. embedding shim returns 1024-dim vector ────────────────────────────
def test_get_embedding_text_1024_dim():
    ref = MediaRef(kind=ModalKind.TEXT, text="hello multimodal world")
    vec = get_embedding(ref)
    assert isinstance(vec, list)
    assert len(vec) == UNIFIED_DIM == 1024, f"expected 1024, got {len(vec)}"
    # L2-normalised
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    assert 0.99 <= norm <= 1.01, f"vector not L2-normalised: norm={norm}"


def test_get_embedding_image_1024_dim():
    # 64x64 pseudo random image bytes
    import hashlib
    raw = hashlib.sha256(b"test-image-001").digest() * 256  # 8KB
    import base64
    ref = MediaRef(
        kind=ModalKind.IMAGE,
        data_b64=base64.b64encode(raw).decode("ascii"),
        mime="image/png",
    )
    vec = get_embedding(ref)
    assert len(vec) == 1024


def test_get_embedding_audio_1024_dim():
    import base64, hashlib
    raw = hashlib.sha256(b"test-audio-001").digest() * 32
    ref = MediaRef(
        kind=ModalKind.AUDIO,
        data_b64=base64.b64encode(raw).decode("ascii"),
    )
    vec = get_embedding(ref)
    assert len(vec) == 1024


def test_get_embedding_deterministic():
    ref = MediaRef(kind=ModalKind.TEXT, text="deterministic test")
    v1 = get_embedding(ref)
    v2 = get_embedding(ref)
    assert v1 == v2, "get_embedding should be deterministic for same text"


def test_get_embedding_similar_texts_cluster():
    a = get_embedding(MediaRef(kind=ModalKind.TEXT, text="quantum computing machine learning"))
    b = get_embedding(MediaRef(kind=ModalKind.TEXT, text="machine learning quantum computing"))
    c = get_embedding(MediaRef(kind=ModalKind.TEXT, text="banana fruit recipe kitchen"))
    import math
    def cos(x, y):
        return sum(xi * yi for xi, yi in zip(x, y))
    sim_ab = cos(a, b)
    sim_ac = cos(a, c)
    # same bag-of-words should cluster tighter than unrelated
    assert sim_ab > sim_ac, f"sim_ab={sim_ab} should exceed sim_ac={sim_ac}"


# ── 2. RAG VectorStore uses new interface ────────────────────────────────
def test_vector_store_uses_1024_dim():
    store = VectorStore()
    assert len(store) == 0
    ref = MediaRef(kind=ModalKind.TEXT, text="hello rag")
    parsed = store.add_media(ref)
    assert len(store) == 1
    # internal items are old Embedding dataclass (compat), vector is 1024
    item = store._items[0]
    assert isinstance(item, Embedding)
    assert len(item.vector) == 1024
    assert parsed.kind == ModalKind.TEXT


def test_rag_index_and_search():
    rag = MultimodalRAG()
    refs = [
        MediaRef(kind=ModalKind.TEXT, text="quantum entanglement physics"),
        MediaRef(kind=ModalKind.TEXT, text="chocolate cake recipe baking"),
        MediaRef(kind=ModalKind.TEXT, text="machine learning neural network"),
    ]
    out = rag.index(refs)
    assert len(out) == 3
    # search with related query
    hits = rag.search(MediaRef(kind=ModalKind.TEXT, text="neural network deep learning"), top_k=3)
    assert len(hits) == 3
    # top hit should be the ML-related one (index 2)
    assert hits[0].media.text == "machine learning neural network"
    assert hits[0].score > hits[-1].score


def test_rag_answer_uses_citations():
    rag = MultimodalRAG()
    rag.index([MediaRef(kind=ModalKind.TEXT, text="apple iphone release event")])
    out = rag.answer(MediaRef(kind=ModalKind.TEXT, text="apple product launch"))
    assert "text" in out
    assert "citations" in out
    assert "elapsed_ms" in out
    assert isinstance(out["citations"], list)


def test_rag_answer_with_llm_call():
    rag = MultimodalRAG()
    rag.index([MediaRef(kind=ModalKind.TEXT, text="Tesla car model 3 launch")])
    calls = []
    def mock_llm(prompt):
        calls.append(prompt)
        return "[MOCK] Answer based on context"
    out = rag.answer(MediaRef(kind=ModalKind.TEXT, text="electric vehicle"), llm_call=mock_llm)
    assert len(calls) == 1
    assert "[MOCK]" in out["text"]


# ── 3. Module-level invariants ───────────────────────────────────────────
def test_unified_dim_is_1024():
    from multimodal.embedding import UNIFIED_DIM
    assert UNIFIED_DIM == 1024


def test_get_global_embedder_singleton():
    a = get_global_embedder()
    b = get_global_embedder()
    assert a is b


def test_old_embedders_module_still_importable():
    """Compat: keep old embedders.py importable for legacy callers."""
    from multimodal.embedders import Embedding, MultimodalEmbedder, cosine  # noqa: F401
    assert Embedding is not None
    assert MultimodalEmbedder is not None
    assert callable(cosine)
