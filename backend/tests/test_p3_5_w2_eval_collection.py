"""P3-5-W2 smoke test — evaluation-service + collection-service.

Uses FastAPI TestClient (hermetic, no live uvicorn) to verify:
  - 10 eval operators listed + execute on synthetic data
  - 15 collection operators listed + execute on sample queries
"""
from __future__ import annotations

import sys
from pathlib import Path

# Path: backend/tests/test_*.py → backend/ is parent of tests/
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Sandbox: don't try real network
import os
os.environ.setdefault("IMDF_SANDBOX_MODE", "1")

from fastapi.testclient import TestClient


def _section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ── evaluation-service ───────────────────────────────────────────────────────
def test_evaluation_service() -> tuple[int, int]:
    _section("evaluation-service (port 8007)")
    from services.evaluation_service.main import app
    client = TestClient(app)
    r = client.get("/healthz")
    print(f"GET /healthz  → {r.status_code}  {r.json()}")
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/eval/list")
    j = r.json()
    print(f"GET /api/v1/eval/list  → {r.status_code}  count={j['count']}  total={j['total']}")
    assert r.status_code == 200
    assert j["count"] == 10, f"expected 10 operators, got {j['count']}"
    assert j["total"] == 10

    ok = 0
    total = 0
    # Smoke 5+ operators with synthetic data
    smoke_cases = [
        ("eval.image.fid", {"items": ["/no/such/path/img.jpg"] * 3, "params": {}}),
        ("eval.image.clip_score", {"items": [
            {"text": "a cat on the mat", "image": {"caption": "cat mat", "tags": ["cat"]}},
        ], "params": {}}),
        ("eval.text.bleu", {"items": ["the cat is on the mat"],
                            "params": {"refs": ["the cat sits on the mat"]}}),
        ("eval.text.rouge", {"items": ["the cat is on the mat"],
                             "params": {"refs": ["the cat sits on the mat"]}}),
        ("eval.text.bert_score", {"items": ["the cat is on the mat"],
                                  "params": {"refs": ["the cat sits on the mat"]}}),
        ("eval.image.aesthetic", {"items": ["/no/such/path.jpg"] * 2, "params": {}}),
        ("eval.image.hpsv2", {"items": [
            {"prompt": "a beautiful sunset", "image": {"caption": "sunset sky"}},
        ], "params": {}}),
        ("eval.video.quality", {"items": [
            {"width": 1920, "height": 1080, "fps": 30, "duration": 60.0, "bitrate_kbps": 4000},
        ], "params": {}}),
        ("eval.audio.quality", {"items": [
            {"sample_rate": 16000, "channels": 1, "duration": 5.0,
             "snr_db": 25.0, "silence_ratio": 0.1, "dynamic_range_db": 30.0},
        ], "params": {}}),
        ("eval.bad_case.detect", {"items": [
            {"sample_id": "s0", "scores": {"accuracy": 0.3, "bleu": 0.05}},
            {"sample_id": "s1", "scores": {"accuracy": 0.9, "bleu": 0.8}},
        ], "params": {}}),
    ]
    for op_id, body in smoke_cases:
        total += 1
        r = client.post(f"/api/v1/eval/{op_id}", json=body)
        if r.status_code == 200:
            ok += 1
            j = r.json()
            print(f"  POST /api/v1/eval/{op_id}  → 200  in={j['input_count']} out={j['output_count']}")
        else:
            print(f"  POST /api/v1/eval/{op_id}  → {r.status_code}  {r.text[:200]}")
    print(f"eval pass: {ok}/{total}")
    return ok, total


# ── collection-service ───────────────────────────────────────────────────────
def test_collection_service() -> tuple[int, int]:
    _section("collection-service (port 8012)")
    from services.collection_service.main import app
    client = TestClient(app)
    r = client.get("/healthz")
    print(f"GET /healthz  → {r.status_code}  {r.json()}")
    assert r.status_code == 200
    r = client.get("/api/v1/collect/list")
    j = r.json()
    print(f"GET /api/v1/collect/list  → {r.status_code}  count={j['count']}  total={j['total']}")
    assert j["count"] == 15, f"expected 15 operators, got {j['count']}"
    assert j["total"] == 15

    # Smoke test all 15 operators with sample queries
    smoke_cases = [
        ("collect.web.crawler", {"query": "https://example.com", "params": {}}),
        ("collect.video.youtube", {"query": "machine learning", "params": {"max_results": 3}}),
        ("collect.social.twitter", {"query": "AI", "params": {"max_results": 3}}),
        ("collect.video.bilibili", {"query": "deep learning", "params": {"max_results": 3}}),
        ("collect.social.instagram", {"query": "photography", "params": {"max_results": 3}}),
        ("collect.video.tiktok", {"query": "funny", "params": {"max_results": 3}}),
        ("collect.api.wikipedia", {"query": "Artificial_intelligence", "params": {}}),
        ("collect.image.unsplash", {"query": "mountains", "params": {"max_results": 3}}),
        ("collect.video.pexels", {"query": "ocean", "params": {"max_results": 3}}),
        ("collect.media.pixabay", {"query": "music", "params": {"max_results": 3}}),
        ("collect.web.common_crawl", {"query": "github.com", "params": {"max_results": 3}}),
        ("collect.academic.arxiv", {"query": "transformer", "params": {"max_results": 3}}),
        ("collect.code.github", {"query": "fastapi", "params": {"max_results": 3}}),
        ("collect.dataset.kaggle", {"query": "image", "params": {"max_results": 3}}),
        ("collect.dataset.huggingface", {"query": "text", "params": {"max_results": 3}}),
    ]
    ok = 0
    total = len(smoke_cases)
    for op_id, body in smoke_cases:
        r = client.post(f"/api/v1/collect/{op_id}", json=body)
        if r.status_code == 200:
            ok += 1
            j = r.json()
            result = j.get("result", {})
            count = result.get("count", "?")
            print(f"  POST /api/v1/collect/{op_id}  → 200  count={count}  mode={result.get('mode', '?')}")
        else:
            print(f"  POST /api/v1/collect/{op_id}  → {r.status_code}  {r.text[:200]}")
    print(f"collect pass: {ok}/{total}")
    return ok, total


if __name__ == "__main__":
    eval_ok, eval_total = test_evaluation_service()
    collect_ok, collect_total = test_collection_service()
    print("\n" + "=" * 70)
    print(f"FINAL: eval {eval_ok}/{eval_total}  collect {collect_ok}/{collect_total}")
    print("=" * 70)
    if eval_ok == eval_total and collect_ok == collect_total:
        print("ALL PASS")
        sys.exit(0)
    sys.exit(1)
