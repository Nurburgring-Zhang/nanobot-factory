"""P4-7-W2 tests — CrossModalUnderstanding covers 8 tasks.

Test count:
1. test_healthz                 — healthz exposes 8 understanding tasks
2. test_caption                 — caption stub returns non-empty text
3. test_vqa                     — vqa requires query, returns answer
4. test_classification          — classification returns label + score
5. test_relation                — relation returns >= 1 edge when >= 2 inputs
6. test_sentiment               — sentiment returns label in {positive, neutral, negative}
7. test_ocr                     — OCR returns extracted text
8. test_asr                     — ASR returns transcript
9. test_reasoning               — reasoning returns answer with context
10. test_understand_batch       — batch endpoint returns >= 2 results
11. test_citations_nonempty     — citations contain at least one entry per media
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imdf.multimodal.routes import build_router
from imdf.multimodal.types import (
    MediaRef,
    ModalKind,
    UnderstandingRequest,
    UnderstandingTask,
)


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def test_healthz(client):
    r = client.get("/api/v1/multimodal/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["service"] == "multimodal"
    assert "understanding_model" in data


def test_caption(client):
    body = {"task": "caption", "media": [{"url": "stub://image/test.jpg"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["task"] == "caption"
    assert len(data["text"]) > 0
    assert data["elapsed_ms"] >= 0


def test_vqa(client):
    body = {
        "task": "vqa",
        "media": [{"url": "stub://image/test.jpg"}],
        "query": "what is in this image?",
    }
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "image" in data["text"].lower() or "stub" in data["text"].lower()


def test_classification(client):
    body = {"task": "classification", "media": [{"url": "stub://image/cat.jpg"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["label"]
    assert 0 <= data["score"] <= 1.0


def test_relation(client):
    body = {
        "task": "relation",
        "media": [{"url": "stub://image/a.jpg"}, {"url": "stub://image/b.jpg"}],
    }
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "--[" in data["text"]


def test_sentiment(client):
    body = {"task": "sentiment", "media": [{"kind": "text", "text": "I love this product!"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["label"] in {"positive", "neutral", "negative"}
    assert 0 <= data["score"] <= 1.0


def test_ocr(client):
    body = {"task": "ocr", "media": [{"url": "stub://image/doc.png"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    assert len(r.json()["text"]) > 0


def test_asr(client):
    body = {"task": "asr", "media": [{"url": "stub://audio/clip.mp3"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    assert len(r.json()["text"]) > 0


def test_reasoning(client):
    body = {
        "task": "reasoning",
        "media": [{"url": "stub://image/scene.jpg"}, {"kind": "text", "text": "Context: sunset"}],
        "query": "Why is the sky red?",
    }
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "sky" in data["text"].lower() or "context" in data["text"].lower()


def test_understand_batch(client):
    body = [
        {"task": "caption", "media": [{"url": "stub://image/1.jpg"}]},
        {"task": "vqa", "media": [{"url": "stub://image/2.jpg"}], "query": "what color?"},
        {"task": "classification", "media": [{"url": "stub://image/3.jpg"}]},
    ]
    r = client.post("/api/v1/multimodal/understand/batch", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert len(data["results"]) == 3


def test_citations_nonempty(client):
    body = {
        "task": "caption",
        "media": [{"url": "stub://image/x.jpg"}, {"kind": "text", "text": "extra context"}],
    }
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert len(data["citations"]) >= 2


def test_vqa_requires_query(client):
    body = {"task": "vqa", "media": [{"url": "stub://image/x.jpg"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 422


def test_unknown_task_rejected(client):
    body = {"task": "nonsense", "media": [{"url": "stub://image/x.jpg"}]}
    r = client.post("/api/v1/multimodal/understand", json=body)
    assert r.status_code == 422