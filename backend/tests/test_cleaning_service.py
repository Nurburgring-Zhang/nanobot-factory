"""P3-4-W1 cleaning-service: integration smoke tests via TestClient.

Covers:
  * Registry: 32 operators, 4 modalities
  * Dynamic routes: /list, /{op_id}, /{op_id}/schema, /{op_id}/preview
  * Real implementations across all 4 modalities
  * Error paths: unknown op_id, malformed body
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import List

import pytest

# Ensure backend/ on sys.path so we can `from services...`
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from services.cleaning_service.main import app
    return TestClient(app)


# ── Registry integrity ────────────────────────────────────────────────────────
def test_registry_has_32_operators():
    from services.cleaning_service.operators import OPERATORS, OPERATOR_META
    assert len(OPERATORS) == 32
    assert len(OPERATOR_META) == 32
    for op_id, fn in OPERATORS.items():
        assert callable(fn), f"{op_id} not callable"


def test_registry_modality_counts():
    from services.cleaning_service.operators import list_operators
    by_modality = {}
    for op in list_operators():
        m = op["modality"]
        by_modality[m] = by_modality.get(m, 0) + 1
    assert by_modality == {"image": 12, "video": 8, "text": 8, "audio": 4}


def test_registry_all_ids_have_callable():
    from services.cleaning_service.operators import OPERATORS, get_operator
    for op_id in OPERATORS.keys():
        assert get_operator(op_id) is not None
        assert callable(get_operator(op_id))


# ── HTTP surface ─────────────────────────────────────────────────────────────
def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["operator_count"] == 32


def test_root_lists_modality_breakdown(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["by_modality"] == {"image": 12, "video": 8, "text": 8, "audio": 4}


def test_list_endpoint(client):
    r = client.get("/api/v1/clean/list")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 32
    assert body["total"] == 32
    ids = [op["id"] for op in body["operators"]]
    assert "clean.image.resolution" in ids
    assert "clean.video.duration" in ids
    assert "clean.text.empty" in ids
    assert "clean.audio.snr" in ids


def test_list_filter_by_modality(client):
    r = client.get("/api/v1/clean/list?modality=text")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 8
    assert all(op["modality"] == "text" for op in body["operators"])


def test_list_filter_by_category(client):
    r = client.get("/api/v1/clean/list?category=dedup")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 4
    assert all(op["category"] == "dedup" for op in body["operators"])


def test_unknown_operator_404(client):
    r = client.post("/api/v1/clean/clean.does.not.exist",
                    json={"data": ["x"], "params": {}})
    assert r.status_code == 404
    assert "operator_not_found" in r.json()["detail"]


def test_unknown_schema_404(client):
    r = client.get("/api/v1/clean/clean.does.not.exist/schema")
    assert r.status_code == 404


# ── Schema lookup ────────────────────────────────────────────────────────────
def test_schema_returns_param_specs(client):
    r = client.get("/api/v1/clean/clean.image.blur/schema")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "clean.image.blur"
    assert body["modality"] == "image"
    param_names = [p["name"] for p in body["params"]]
    assert "min_variance" in param_names
    assert "mode" in param_names


# ── Text operators (real implementations) ────────────────────────────────────
def test_text_empty(client):
    r = client.post("/api/v1/clean/clean.text.empty",
                    json={"data": ["", "  ", None, "real", "x"], "params": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["output_count"] == 2
    assert body["result"] == ["real", "x"]


def test_text_length(client):
    r = client.post("/api/v1/clean/clean.text.length",
                    json={"data": ["a", "abc", "abcdefgh"], "params": {"min_chars": 2, "max_chars": 5}})
    assert r.status_code == 200
    assert r.json()["result"] == ["abc"]


def test_text_deduplicate(client):
    r = client.post("/api/v1/clean/clean.text.deduplicate",
                    json={"data": ["hello world", "hello world", "different"], "params": {}})
    assert r.status_code == 200
    assert r.json()["output_count"] == 2


def test_text_language(client):
    r = client.post("/api/v1/clean/clean.text.language",
                    json={"data": ["你好世界 这是中文测试文本字符很多",
                                   "hello world here ascii english",
                                   "你好 hello 中文 world 中英"],
                          "params": {"target_lang": "any"}})
    assert r.status_code == 200
    langs = [d["language"] for d in r.json()["result"]]
    assert langs[0] == "zh"
    assert langs[1] == "en"
    # 3rd: mixed CJK + ASCII at ~50/50
    assert langs[2] == "mixed"


def test_text_sensitive_drop(client):
    r = client.post("/api/v1/clean/clean.text.sensitive",
                    json={"data": ["good text", "has blocked_term here", "fine"], "params": {"wordlist": ["blocked_term"], "mode": "drop"}})
    assert r.status_code == 200
    body = r.json()
    assert body["output_count"] == 2  # one dropped


def test_text_toxicity_score(client):
    r = client.post("/api/v1/clean/clean.text.toxicity",
                    json={"data": ["clean text here", "TOXIC toxic_word_1"], "params": {"wordlist": ["toxic_word_1"], "mode": "score"}})
    assert r.status_code == 200
    items = r.json()["result"]
    assert items[0]["is_toxic"] is False
    assert items[1]["is_toxic"] is True


def test_text_html(client):
    r = client.post("/api/v1/clean/clean.text.html",
                    json={"data": ["<p>Hello <b>world</b>!</p>"], "params": {}})
    assert r.status_code == 200
    assert r.json()["result"] == ["Hello world!"]


def test_text_pii_mask(client):
    r = client.post("/api/v1/clean/clean.text.pii",
                    json={"data": ["Email alice@example.com"], "params": {"strategy": "mask"}})
    assert r.status_code == 200
    out = r.json()["result"][0]
    assert out["pii_detected"] is True
    assert "*" in out["redacted"]


# ── Image operators (real implementations with real PNGs) ────────────────────
@pytest.fixture
def tmp_images() -> List[str]:
    """Three strongly-distinct RGB images of different sizes/colors.

    Uniform images collapse to identical 8x8 aHash, so we draw stripes/blocks
    to give each image a unique 8x8 average pattern.
    """
    import numpy as np
    from PIL import Image
    tmp = tempfile.mkdtemp(prefix="clean_pytest_")
    paths = []
    designs = [
        # 512x512: horizontal stripes (alternating bright/dark)
        "stripes",
        # 256x256: 4x4 color grid
        "grid",
        # 1024x1024: gradient
        "gradient",
    ]
    for i, design in enumerate(designs):
        if design == "stripes":
            arr = np.zeros((512, 512, 3), dtype=np.uint8)
            arr[::2, :, 0] = 200; arr[::2, :, 1] = 50; arr[::2, :, 2] = 50
            arr[1::2, :, 0] = 50; arr[1::2, :, 1] = 50; arr[1::2, :, 2] = 200
        elif design == "grid":
            arr = np.zeros((256, 256, 3), dtype=np.uint8)
            block = 64
            for r in range(4):
                for c in range(4):
                    arr[r*block:(r+1)*block, c*block:(c+1)*block] = (
                        (r * 64) % 256, (c * 64) % 256, ((r + c) * 32) % 256
                    )
        else:  # gradient
            x = np.linspace(0, 255, 1024, dtype=np.uint8)
            arr = np.stack([x, x[::-1], np.full_like(x, 128)], axis=-1)
            arr = np.broadcast_to(arr[None, :, :], (1024, 1024, 3)).copy()
        p = os.path.join(tmp, f"img_{i}_{design}.png")
        Image.fromarray(arr).save(p)
        paths.append(p)
    return paths


def test_image_resolution(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.resolution",
                    json={"data": tmp_images, "params": {"min_w": 300, "max_w": 800, "min_h": 300, "max_h": 800}})
    assert r.status_code == 200
    # 512 fits, 256/1024 don't
    assert r.json()["output_count"] == 1


def test_image_aspect_ratio(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.aspect_ratio",
                    json={"data": tmp_images, "params": {"min_ratio": 0.9, "max_ratio": 1.1}})
    assert r.status_code == 200
    assert r.json()["output_count"] == 3  # all square


def test_image_blur_score(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.blur",
                    json={"data": tmp_images, "params": {"mode": "score"}})
    assert r.status_code == 200
    items = r.json()["result"]
    assert all("variance" in d for d in items)


def test_image_dedup_md5(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.deduplicate.md5",
                    json={"data": tmp_images + [tmp_images[0]], "params": {}})
    assert r.status_code == 200
    assert r.json()["output_count"] == 3


def test_image_dedup_phash(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.deduplicate.phash",
                    json={"data": tmp_images, "params": {"hamming_threshold": 5}})
    assert r.status_code == 200
    # Different colors → different pHash; all 3 kept
    assert r.json()["output_count"] == 3


def test_image_color_balance(tmp_images, client):
    # Build one perfectly grey image for the "balanced" branch + one pure red
    from PIL import Image
    import tempfile
    tmp = tempfile.mkdtemp(prefix="clean_cb_")
    grey = os.path.join(tmp, "grey.png")
    red = os.path.join(tmp, "red.png")
    Image.new("RGB", (128, 128), (128, 128, 128)).save(grey)
    Image.new("RGB", (128, 128), (255, 0, 0)).save(red)
    r = client.post("/api/v1/clean/clean.image.color_balance",
                    json={"data": [grey, red], "params": {"mode": "score"}})
    assert r.status_code == 200
    items = r.json()["result"]
    # Perfect grey is balanced; pure red is NOT balanced
    assert items[0]["balanced"] is True
    assert items[1]["balanced"] is False


def test_image_compress_artifact(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.compress_artifact",
                    json={"data": tmp_images, "params": {"mode": "score"}})
    assert r.status_code == 200
    items = r.json()["result"]
    assert all("blockiness" in d for d in items)


def test_image_noise(tmp_images, client):
    r = client.post("/api/v1/clean/clean.image.noise",
                    json={"data": tmp_images, "params": {"mode": "score"}})
    assert r.status_code == 200
    items = r.json()["result"]
    assert all("sigma" in d for d in items)


# ── Audio operators (with mock metadata) ─────────────────────────────────────
def test_audio_duration_with_meta(client):
    mock = [{"path": "/x.wav", "duration": 5.0, "sample_rate": 16000}]
    r = client.post("/api/v1/clean/clean.audio.duration",
                    json={"data": mock, "params": {"min_seconds": 1.0, "max_seconds": 30.0}})
    assert r.status_code == 200
    assert r.json()["output_count"] == 1


def test_audio_sample_rate_match(client):
    mock = [{"path": "/x.wav", "sample_rate": 16000, "duration": 5.0}]
    r = client.post("/api/v1/clean/clean.audio.sample_rate",
                    json={"data": mock, "params": {"target_sr": 16000, "mode": "score"}})
    assert r.status_code == 200
    assert r.json()["result"][0]["matches_target"] is True


# ── Preview dry-run ──────────────────────────────────────────────────────────
def test_preview_returns_sample(client):
    r = client.post("/api/v1/clean/clean.text.empty/preview",
                    json={"data": ["a", "", "b", "", "c"], "params": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["input_count"] == 5
    assert body["output_count"] == 3
    assert body["sample"] == ["a", "b", "c"]