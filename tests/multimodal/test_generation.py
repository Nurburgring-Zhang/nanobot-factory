"""P4-7-W2 tests — CrossModalGeneration covers 4 modalities.

Test count (>= 3 required, we ship 7):
1. test_generate_image            — image target → 1+ candidate
2. test_generate_video            — video target → 1+ candidate
3. test_generate_audio            — audio target → 1+ candidate
4. test_generate_text             — text target → 1+ candidate
5. test_generate_n_candidates     — n=4 → 4 candidates
6. test_providers_endpoint        — /providers returns list
7. test_generate_empty_text_rejected
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imdf.multimodal.generation import CrossModalGeneration
from imdf.multimodal.routes import build_router
from imdf.multimodal.types import GenerationRequest, GenerationTarget, MediaRef, ModalKind


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def _run(target: str, refs: int = 0, n: int = 1):
    gen = CrossModalGeneration()
    req = GenerationRequest(
        text="a cat astronaut",
        target=GenerationTarget(target),
        ref_images=[MediaRef(kind=ModalKind.IMAGE, url=f"stub://image/ref{i}.jpg") for i in range(refs)],
        params={"n": n},
    )
    return gen.generate(req)


def test_generate_image():
    # Same logic as other targets but proven separately for IMAGE; the helper
    # is reused so any latent initialization issue surfaces in the first call.
    r = _run("image", refs=0, n=1)
    assert r.target == GenerationTarget.IMAGE
    assert len(r.candidates) >= 1
    assert r.candidates[0].mime == "image/png"
    assert r.candidates[0].url.startswith("stub://image/")


def test_generate_video():
    r = _run("video", refs=0, n=1)
    assert r.target == GenerationTarget.VIDEO
    assert r.candidates[0].mime == "video/mp4"
    assert r.candidates[0].duration_sec == 4.0


def test_generate_audio():
    r = _run("audio", refs=0, n=1)
    assert r.target == GenerationTarget.AUDIO
    assert r.candidates[0].mime == "audio/wav"
    assert r.candidates[0].duration_sec == 10.0


def test_generate_text():
    r = _run("text", refs=0, n=1)
    assert r.target == GenerationTarget.TEXT
    assert r.candidates[0].mime == "text/plain"


def test_generate_n_candidates():
    r = _run("image", refs=3, n=4)
    assert len(r.candidates) == 4
    # candidate urls are unique
    urls = [c.url for c in r.candidates]
    assert len(set(urls)) == 4


def test_providers_endpoint(client):
    r = client.get("/api/v1/multimodal/providers")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    names = [p["name"] for p in data["providers"]]
    assert {"openai_compatible", "volcengine", "comfyui", "jimeng_cli"}.issubset(set(names))


def test_generate_empty_text_rejected(client):
    body = {"text": "", "target": "image"}
    r = client.post("/api/v1/multimodal/generate", json=body)
    assert r.status_code == 422


def test_generate_unknown_target_rejected(client):
    body = {"text": "x", "target": "hologram"}
    r = client.post("/api/v1/multimodal/generate", json=body)
    assert r.status_code == 422