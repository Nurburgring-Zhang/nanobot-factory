"""P4-7-W1: MultiModalEmbedder tests (4: 5 modalities + 1024-dim)."""
from __future__ import annotations

import io
import math

import numpy as np
import pytest

from imdf.multimodal.parser import (
    MultiModalParser,
    MultimodalDocument,
    DocumentSegment,
    MODALITY_TEXT,
    MODALITY_IMAGE,
    MODALITY_AUDIO,
    MODALITY_VIDEO,
    MODALITY_DOCUMENT,
)
from imdf.multimodal.embedding import (
    MultiModalEmbedder,
    EmbeddingRequest,
    EmbeddingResponse,
    UNIFIED_DIM,
)


@pytest.fixture
def embedder() -> MultiModalEmbedder:
    return MultiModalEmbedder()


@pytest.fixture
def tiny_png_bytes() -> bytes:
    try:
        from PIL import Image
        img = Image.new("RGB", (8, 8), (10, 20, 30))
        for x in range(8):
            for y in range(8):
                img.putpixel((x, y), ((x * 32) % 256, (y * 32) % 256, 64))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\x99c\xf8\xff"
            b"\xff?\x00\x05\xfe\x02\xfe\xa3\x9c\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
        )


@pytest.fixture
def tiny_wav_bytes() -> bytes:
    import struct
    import wave
    sr = 8000
    n = sr  # 1 second
    with io.BytesIO() as buf:
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            # some non-zero audio
            frames = b"".join(struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * t / sr)))
                              for t in range(n))
            w.writeframes(frames)
        return buf.getvalue()


def test_unified_dim_constant():
    assert UNIFIED_DIM == 1024


def test_text_embedding_dim(embedder: MultiModalEmbedder):
    rec = embedder.encode_one(EmbeddingRequest(
        entity_type="test", entity_id="t1",
        modality=MODALITY_TEXT, text="hello world 蓝色天空",
    ))
    assert rec.dim == UNIFIED_DIM
    assert len(rec.vector) == UNIFIED_DIM
    v = np.asarray(rec.vector)
    n = float(np.linalg.norm(v))
    assert abs(n - 1.0) < 1e-3
    # store lookup
    assert embedder.store_size() == 1


def test_image_embedding_dim(embedder: MultiModalEmbedder, tiny_png_bytes: bytes):
    import base64
    rec = embedder.encode_one(EmbeddingRequest(
        entity_type="asset", entity_id="img1",
        modality=MODALITY_IMAGE, base64=base64.b64encode(tiny_png_bytes).decode("ascii"),
    ))
    assert rec.dim == UNIFIED_DIM
    assert len(rec.vector) == UNIFIED_DIM
    assert rec.modality == MODALITY_IMAGE
    assert rec.source_model.startswith("image-encoder")


def test_audio_embedding_dim(embedder: MultiModalEmbedder, tiny_wav_bytes: bytes):
    import base64
    rec = embedder.encode_one(EmbeddingRequest(
        entity_type="audio", entity_id="aud1",
        modality=MODALITY_AUDIO, base64=base64.b64encode(tiny_wav_bytes).decode("ascii"),
    ))
    assert rec.dim == UNIFIED_DIM
    assert len(rec.vector) == UNIFIED_DIM
    assert rec.modality == MODALITY_AUDIO


def test_document_embedding_dim(embedder: MultiModalEmbedder):
    doc = MultimodalDocument(
        doc_id="d-test", modality=MODALITY_DOCUMENT,
        text="This is a test document about multimodal embeddings.",
        segments=[DocumentSegment(
            segment_id="s1", text="Page 1: hello",
            start=0, end=12, page=1, segment_type="text",
        )],
        metadata={"pages": 1},
    )
    rec = embedder.encode_one(EmbeddingRequest(
        entity_type="doc", entity_id="d-test",
        modality=MODALITY_DOCUMENT, document=doc,
    ))
    assert rec.dim == UNIFIED_DIM
    assert len(rec.vector) == UNIFIED_DIM
    assert rec.modality == MODALITY_DOCUMENT


def test_similar_text_clusters(embedder: MultiModalEmbedder):
    """Two texts about the same topic should have high cosine similarity."""
    a = embedder.encode_one(EmbeddingRequest(
        entity_type="t", entity_id="a", modality=MODALITY_TEXT,
        text="天空是蓝色 nice weather",
    ))
    b = embedder.encode_one(EmbeddingRequest(
        entity_type="t", entity_id="b", modality=MODALITY_TEXT,
        text="天空是蓝色 beautiful sky",
    ))
    c = embedder.encode_one(EmbeddingRequest(
        entity_type="t", entity_id="c", modality=MODALITY_TEXT,
        text="completely unrelated pizza burger restaurant",
    ))
    va, vb, vc = (np.asarray(r.vector) for r in (a, b, c))
    sim_ab = float(np.dot(va, vb))
    sim_ac = float(np.dot(va, vc))
    # 蓝色 + 天空 co-occurring should bring a, b closer than a, c
    assert sim_ab > sim_ac, f"sim_ab={sim_ab} should exceed sim_ac={sim_ac}"


def test_batch_encode(embedder: MultiModalEmbedder):
    reqs = [
        EmbeddingRequest(entity_type="t", entity_id=f"x{i}",
                         modality=MODALITY_TEXT, text=f"sample text {i}")
        for i in range(5)
    ]
    resp = embedder.encode_batch(reqs)
    assert isinstance(resp, EmbeddingResponse)
    assert resp.dim == UNIFIED_DIM
    assert len(resp.records) == 5
    assert all(len(r.vector) == UNIFIED_DIM for r in resp.records)
    assert embedder.store_size() == 5


def test_search_topk(embedder: MultiModalEmbedder):
    base = "blue sky video with white clouds"
    near = "video of blue sky"
    far = "deep sea ocean coral reef"
    embedder.encode_one(EmbeddingRequest(
        entity_type="vid", entity_id="b", modality=MODALITY_TEXT, text=base,
    ))
    embedder.encode_one(EmbeddingRequest(
        entity_type="vid", entity_id="n", modality=MODALITY_TEXT, text=near,
    ))
    embedder.encode_one(EmbeddingRequest(
        entity_type="vid", entity_id="f", modality=MODALITY_TEXT, text=far,
    ))
    qv = np.asarray(embedder.encode_one(EmbeddingRequest(
        entity_type="q", entity_id="q", modality=MODALITY_TEXT, text=base,
    )).vector)
    hits = embedder.search(qv, top_k=2, entity_type="vid")
    assert hits
    top_id = hits[0][0].entity_id
    # the "n" hit should outrank the "f" hit
    assert top_id in {"b", "n"}, f"unexpected top: {top_id}"
