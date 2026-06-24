"""P4-7-W1: multimodal RAG tests (3: cross-modal retrieval + LLM citations)."""
from __future__ import annotations

import base64
import io
import math

import numpy as np
import pytest

from imdf.multimodal.parser import (
    MultiModalParser,
    MultimodalDocument,
    DocumentSegment,
    DocumentImage,
    MODALITY_TEXT,
    MODALITY_IMAGE,
    MODALITY_VIDEO,
    MODALITY_AUDIO,
    MODALITY_DOCUMENT,
)
from imdf.multimodal.embedding import (
    MultiModalEmbedder,
    EmbeddingRequest,
    UNIFIED_DIM,
)
from services.search_service.multimodal_rag import (
    CrossModalReranker,
    LlmAnswerSynthesizer,
    MultimodalQuery,
    MultimodalRAG,
    RagAnswer,
    RagCandidate,
    index_document,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def embedder() -> MultiModalEmbedder:
    return MultiModalEmbedder()


@pytest.fixture
def rag(embedder: MultiModalEmbedder) -> MultimodalRAG:
    return MultimodalRAG(embedder=embedder, parser=MultiModalParser())


def _seed_corpus(embedder: MultiModalEmbedder) -> None:
    """Index a small cross-modal corpus: 2 video + 1 image + 2 docs.

    Each is a MultimodalDocument so the doc/segment/image encoders can do
    their job.  Snippets in metadata carry the retrieval text.
    """
    docs = [
        MultimodalDocument(
            doc_id="vid-001", modality=MODALITY_VIDEO,
            text="A wide shot of blue sky over mountains with white clouds.",
            segments=[DocumentSegment(
                segment_id="v1-s0", text="blue sky clouds mountains",
                start=0, end=27, timestamp=0.0, segment_type="text",
            )],
            images=[DocumentImage(
                image_id="v1-frame-0", mime_type="image/jpeg",
                timestamp=0.0, page=1,
            )],
            metadata={"title": "Blue Sky Drone Footage", "snippet": "blue sky clouds mountains"},
        ),
        MultimodalDocument(
            doc_id="vid-002", modality=MODALITY_VIDEO,
            text="Ocean waves crashing on a sandy beach at sunset.",
            segments=[DocumentSegment(
                segment_id="v2-s0", text="ocean waves beach sunset",
                start=0, end=25, timestamp=0.0, segment_type="text",
            )],
            images=[DocumentImage(
                image_id="v2-frame-0", mime_type="image/jpeg",
                timestamp=0.0, page=1,
            )],
            metadata={"title": "Ocean Waves", "snippet": "ocean waves beach sunset"},
        ),
        MultimodalDocument(
            doc_id="img-001", modality=MODALITY_IMAGE,
            text="Photo of a clear blue sky.",
            images=[DocumentImage(
                image_id="img-001", mime_type="image/jpeg", page=1,
            )],
            metadata={"title": "Blue Sky Photo", "snippet": "clear blue sky photo"},
        ),
        MultimodalDocument(
            doc_id="doc-001", modality=MODALITY_DOCUMENT,
            text="This report analyses the impact of urban noise on bird populations.",
            segments=[DocumentSegment(
                segment_id="d1-s0", text="urban noise bird populations",
                start=0, end=33, segment_type="text",
            )],
            metadata={"title": "Urban Noise Report", "snippet": "urban noise bird populations"},
        ),
        MultimodalDocument(
            doc_id="doc-002", modality=MODALITY_DOCUMENT,
            text="An academic study of sky colour perception in art history.",
            segments=[DocumentSegment(
                segment_id="d2-s0", text="sky colour perception art history",
                start=0, end=39, segment_type="text",
            )],
            metadata={"title": "Sky in Art History", "snippet": "sky colour perception art history"},
        ),
    ]
    for d in docs:
        index_document(embedder, d, {
            "entity_type": d.modality,
            "entity_id": d.doc_id,
        })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_reranker_expected_modality():
    rr = CrossModalReranker()
    assert rr.expected_modality(MultimodalQuery(text="show me a video about cats")) == MODALITY_VIDEO
    assert rr.expected_modality(MultimodalQuery(text="image of a blue sky")) == MODALITY_IMAGE
    assert rr.expected_modality(MultimodalQuery(text="audio clip of music")) == MODALITY_AUDIO
    assert rr.expected_modality(MultimodalQuery(text="随便聊一聊")) == MODALITY_TEXT


def test_reranker_modal_bonus(embedder: MultiModalEmbedder, rag: MultimodalRAG):
    _seed_corpus(embedder)
    q = MultimodalQuery(text="展示蓝色天空的视频", top_k=3)
    cands = rag.search(q)
    assert cands, "expected at least one candidate"
    expected = rag.reranker.expected_modality(q)
    assert expected == MODALITY_VIDEO
    # At least one of the top hits should be a video, and it should have
    # the modal bonus applied.
    top = cands[0]
    assert top.modality == MODALITY_VIDEO
    assert top.modal_bonus > 0


def test_rag_answer_with_citations(embedder: MultiModalEmbedder, rag: MultimodalRAG):
    _seed_corpus(embedder)
    q = MultimodalQuery(text="展示蓝色天空的视频", top_k=3)
    ans = rag.answer(q)
    assert isinstance(ans, RagAnswer)
    assert ans.citations, "answer should include citations"
    # Citations should reference the indexed docs
    eids = {c["entity_id"] for c in ans.citations}
    assert "vid-001" in eids or "img-001" in eids, f"expected blue-sky refs, got {eids}"
    # The synthesized text should mention the top entity type
    assert "video" in ans.text.lower() or "image" in ans.text.lower()
    # Source should be either the template or a real LLM
    assert ans.llm_source in ("template-v1", "template-empty", "callback")


def test_rag_with_real_payload(embedder: MultiModalEmbedder, rag: MultimodalRAG):
    """A query carrying actual image bytes should retrieve image docs."""
    _seed_corpus(embedder)
    # build a 4x4 PNG and base64-encode
    from PIL import Image
    img = Image.new("RGB", (4, 4), (0, 0, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    q = MultimodalQuery(text="blue sky", base64=b64,
                        filename="sky.png", mime_type="image/png", top_k=2)
    cands = rag.search(q)
    assert cands
    # Expected modality should be image
    assert rag.reranker.expected_modality(q) == MODALITY_IMAGE


def test_llm_synthesizer_template(embedder: MultiModalEmbedder, rag: MultimodalRAG):
    _seed_corpus(embedder)
    q = MultimodalQuery(text="blue sky video", top_k=2)
    cands = rag.search(q)
    syn = LlmAnswerSynthesizer()
    text, citations, src = syn.synthesize(q, cands)
    assert "blue sky" in text
    assert citations
    assert src == "template-v1"


def test_llm_synthesizer_callback():
    cb = lambda q, cits: f"Q={q}; n_cites={len(cits)}"
    syn = LlmAnswerSynthesizer(llm_callback=cb)
    text, cits, src = syn.synthesize(
        MultimodalQuery(text="hi", top_k=1),
        [RagCandidate(entity_id="x", entity_type="img", modality=MODALITY_IMAGE,
                      score=0.9, vector_score=0.8, modal_bonus=0.1,
                      snippet="snippet")],
    )
    assert text == "Q=hi; n_cites=1"
    assert src == "callback"


def test_multimodal_rag_empty(rag: MultimodalRAG):
    """With no corpus, the answer should still produce a well-formed response."""
    q = MultimodalQuery(text="anything", top_k=3)
    ans = rag.answer(q)
    assert ans.llm_source == "template-empty"
    assert "未找到" in ans.text
    assert ans.citations == []
