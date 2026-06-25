"""P3-4-W2 — 25 评分/筛选/导出算子 真实现验证 (scoring/dataset/eval services).

Smoke 5+ operators each service via fastapi.testclient.TestClient.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

# Backend root on sys.path
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))


# ── scoring-service ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def scoring_client():
    from services.scoring_service.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_scoring_healthz(scoring_client):
    r = scoring_client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "scoring-service"


def test_scoring_list_returns_15(scoring_client):
    r = scoring_client.get("/api/v1/score/list")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 15
    assert body["registry"] == "modular"
    op_ids = {o["id"] for o in body["operators"]}
    expected = {
        "score.aesthetic", "score.technical", "score.clarity",
        "score.composition", "score.color_harmony", "score.resolution",
        "score.noise", "score.text_quality", "score.diversity",
        "score.safety", "score.relevance", "score.preference",
        "score.difficulty", "score.creativity", "score.consistency",
    }
    assert op_ids == expected, f"missing: {expected - op_ids}; extra: {op_ids - expected}"


def test_scoring_get_one(scoring_client):
    r = scoring_client.get("/api/v1/score/score.aesthetic")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "score.aesthetic"
    assert "name" in body
    assert "description" in body


def test_scoring_unknown_returns_404(scoring_client):
    r = scoring_client.get("/api/v1/score/score.bogus")
    assert r.status_code == 404


def test_scoring_run_text_quality(scoring_client):
    r = scoring_client.post("/api/v1/score/score.text_quality/run",
                            json={"data": "Hello world. This is a test sentence.", "params": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["op_id"] == "score.text_quality"
    assert body["result"]["text_quality"] >= 0


def test_scoring_run_diversity_list(scoring_client):
    r = scoring_client.post("/api/v1/score/score.diversity/run",
                            json={"data": ["apple banana", "cherry date", "egg fruit grape"], "params": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    res = body["result"]
    assert "diversity" in res
    assert res["diversity"] >= 0


def test_scoring_run_safety(scoring_client):
    r = scoring_client.post("/api/v1/score/score.safety/run",
                            json={"data": ["contact me at test@example.com or 13800001111"], "params": {}})
    assert r.status_code == 200
    body = r.json()
    res = body["result"]
    # result is a list (one item per input)
    if isinstance(res, list):
        res = res[0]
    assert "safety" in res
    assert res["pii_hits"] >= 1


def test_scoring_run_consistency(scoring_client):
    r = scoring_client.post("/api/v1/score/score.consistency/run",
                            json={"data": {"text": "a cat on a mat",
                                           "image": "cat_image_001.jpg",
                                           "audio": "audio_cat_meow.wav"},
                                  "params": {}})
    assert r.status_code == 200
    body = r.json()
    res = body["result"]
    assert "consistency" in res
    assert res["modalities"] == 3


# ── dataset-service ────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def dataset_client():
    from services.dataset_service.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_dataset_healthz(dataset_client):
    r = dataset_client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


def test_filter_list_returns_10(dataset_client):
    r = dataset_client.get("/api/v1/dataset/filter/list")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    op_ids = {o["id"] for o in body["operators"]}
    expected = {
        "filter.top_k", "filter.percentile", "filter.threshold",
        "filter.diversity", "filter.balance", "filter.language",
        "filter.domain", "filter.quality", "filter.random_sample",
        "filter.rule_based",
    }
    assert op_ids == expected


def test_export_list_returns_12(dataset_client):
    r = dataset_client.get("/api/v1/dataset/export/list")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 12
    op_ids = {o["id"] for o in body["operators"]}
    expected = {
        "export.jsonl", "export.parquet", "export.csv", "export.tfrecord",
        "export.coco", "export.voc", "export.yolo",
        "export.alpaca", "export.sharegpt", "export.conversation",
        "export.video_frames", "export.audio_wav",
    }
    assert op_ids == expected


def test_filter_run_top_k(dataset_client):
    r = dataset_client.post("/api/v1/dataset/filter/filter.top_k/run",
                            json={"data": [{"score": 0.9}, {"score": 0.3}, {"score": 0.7}],
                                  "params": {"k": 2, "score_field": "score"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["kept_count"] == 2
    assert body["result"]["kept"][0]["score"] == 0.9


def test_filter_run_threshold(dataset_client):
    r = dataset_client.post("/api/v1/dataset/filter/filter.threshold/run",
                            json={"data": [0.1, 0.5, 0.9, 0.3],
                                  "params": {"min": 0.3, "max": 0.7}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["kept_count"] == 2  # 0.5 and 0.3


def test_filter_run_rule_based(dataset_client):
    r = dataset_client.post("/api/v1/dataset/filter/filter.rule_based/run",
                            json={"data": [
                                {"scores": {"aesthetic": 80}, "label": "good"},
                                {"scores": {"aesthetic": 40}, "label": "bad"},
                            ], "params": {"rules": [
                                {"field": "scores.aesthetic", "op": "gte", "value": 60},
                            ]}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["kept_count"] == 1
    assert body["result"]["kept"][0]["label"] == "good"


def test_filter_run_balance(dataset_client):
    r = dataset_client.post("/api/v1/dataset/filter/filter.balance/run",
                            json={"data": [
                                {"label": "A"}, {"label": "A"}, {"label": "A"},
                                {"label": "B"}, {"label": "B"},
                            ], "params": {"target_per_class": 2, "mode": "undersample", "seed": 1}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["kept_count"] == 4  # 2 + 2
    assert body["result"]["per_class_counts"] == {"A": 2, "B": 2}


def test_filter_unknown_returns_404(dataset_client):
    r = dataset_client.post("/api/v1/dataset/filter/filter.bogus/run",
                            json={"data": [], "params": {}})
    assert r.status_code == 404


def test_export_run_jsonl(dataset_client, tmp_path):
    out = tmp_path / "out.jsonl"
    r = dataset_client.post("/api/v1/dataset/export/export.jsonl/run",
                            json={"data": [{"a": 1}, {"a": 2}, {"a": 3}],
                                  "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["format"] == "jsonl"
    assert body["result"]["rows_written"] == 3
    assert out.exists()
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 3


def test_export_run_csv(dataset_client, tmp_path):
    out = tmp_path / "out.csv"
    r = dataset_client.post("/api/v1/dataset/export/export.csv/run",
                            json={"data": [{"a": 1, "b": 2}, {"a": 3, "b": 4}],
                                  "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "csv"
    assert body["result"]["rows_written"] == 2
    assert "a" in body["result"]["columns"]


def test_export_run_alpaca(dataset_client, tmp_path):
    out = tmp_path / "alpaca.jsonl"
    r = dataset_client.post("/api/v1/dataset/export/export.alpaca/run",
                            json={"data": [{"instruction": "Q1", "input": "ctx", "output": "A1"}],
                                  "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "alpaca"
    assert body["result"]["rows_written"] == 1


def test_export_run_sharegpt(dataset_client, tmp_path):
    out = tmp_path / "sharegpt.jsonl"
    r = dataset_client.post("/api/v1/dataset/export/export.sharegpt/run",
                            json={"data": [{"conversations": [
                                {"role": "user", "content": "hi"},
                                {"role": "assistant", "content": "hello"},
                            ]}], "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "sharegpt"
    assert body["result"]["rows_written"] == 1


def test_export_run_yolo(dataset_client, tmp_path):
    out = tmp_path / "yolo_out"
    r = dataset_client.post("/api/v1/dataset/export/export.yolo/run",
                            json={"data": [
                                {"image": "img1.jpg", "width": 100, "height": 100,
                                 "bbox": [[10, 10, 50, 50]], "category": ["cat"]},
                            ], "params": {"dir": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "yolo"
    assert body["result"]["label_count"] == 1
    assert (out / "classes.txt").exists()
    assert (out / "data.yaml").exists()


def test_export_run_coco(dataset_client, tmp_path):
    out = tmp_path / "coco.json"
    r = dataset_client.post("/api/v1/dataset/export/export.coco/run",
                            json={"data": [
                                {"image": "img1.jpg", "width": 640, "height": 480,
                                 "bbox": [[10, 10, 100, 100]], "category": ["dog"]},
                            ], "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "coco"
    assert body["result"]["annotation_count"] == 1


def test_export_run_voc(dataset_client, tmp_path):
    out = tmp_path / "voc_out"
    r = dataset_client.post("/api/v1/dataset/export/export.voc/run",
                            json={"data": [
                                {"image": "img1.jpg", "width": 640, "height": 480,
                                 "bbox": [[10, 10, 100, 100]], "category": ["dog"]},
                            ], "params": {"dir": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "voc"
    assert body["result"]["annotation_count"] == 1
    assert (out / "Annotations" / "img1.xml").exists()


def test_export_run_conversation(dataset_client, tmp_path):
    out = tmp_path / "conv.jsonl"
    r = dataset_client.post("/api/v1/dataset/export/export.conversation/run",
                            json={"data": [
                                {"system": "You are helpful.",
                                 "messages": [{"role": "user", "content": "Hi"},
                                              {"role": "assistant", "content": "Hello!"}]},
                            ], "params": {"path": str(out)}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "conversation"


def test_export_run_video_frames(dataset_client, tmp_path):
    out = tmp_path / "vf_out"
    r = dataset_client.post("/api/v1/dataset/export/export.video_frames/run",
                            json={"data": ["fake_video_001.mp4", "fake_video_002.mp4"],
                                  "params": {"dir": str(out), "fps": 2.0}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "video_frames"
    assert body["result"]["video_count"] == 2


def test_export_run_audio_wav(dataset_client, tmp_path):
    out = tmp_path / "audio_out"
    # Provide raw int samples for at least one item
    samples = [0, 1000, -1000, 0] * 100  # tiny waveform
    r = dataset_client.post("/api/v1/dataset/export/export.audio_wav/run",
                            json={"data": [{"audio": "x.wav", "samples": samples}],
                                  "params": {"dir": str(out), "sample_rate": 8000}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["format"] == "audio_wav"
    assert body["result"]["wav_written"] == 1


def test_export_unknown_returns_404(dataset_client):
    r = dataset_client.post("/api/v1/dataset/export/export.bogus/run",
                            json={"data": [], "params": {}})
    assert r.status_code == 404


# ── evaluation-service (sanity — main routes still work) ───────────────────────
@pytest.fixture(scope="module")
def eval_client():
    from services.evaluation_service.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_eval_healthz(eval_client):
    r = eval_client.get("/healthz")
    assert r.status_code == 200


def test_eval_metrics_catalog(eval_client):
    r = eval_client.get("/api/v1/evaluations/metrics/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 8
    metric_names = {m["name"] for m in body["metrics"]}
    assert {"accuracy", "f1_score", "bleu", "rouge_l"}.issubset(metric_names)


# ── cross-service: dynamic dispatch coverage ───────────────────────────────────
def test_scoring_dynamic_dispatch_all_15(scoring_client):
    """POST /api/v1/score/{op_id}/run works for every op in the registry."""
    r = scoring_client.get("/api/v1/score/list")
    op_ids = [o["id"] for o in r.json()["operators"]]
    assert len(op_ids) == 15
    for op_id in op_ids:
        # Pick a payload most ops will accept
        payload = {"data": "hello world", "params": {}}
        if op_id == "score.diversity":
            payload["data"] = ["a", "b", "c"]
        if op_id == "score.consistency":
            payload["data"] = {"text": "x", "image": "y"}
        if op_id == "score.preference":
            payload["params"] = {"chosen": "good answer", "rejected": "bad answer"}
        if op_id == "score.creativity":
            payload["params"] = {"background": []}
        r2 = scoring_client.post(f"/api/v1/score/{op_id}/run", json=payload)
        assert r2.status_code == 200, f"{op_id} returned {r2.status_code} {r2.text}"


def test_filter_dynamic_dispatch_all_10(dataset_client):
    """POST /api/v1/dataset/filter/{op_id}/run works for every op in the registry."""
    r = dataset_client.get("/api/v1/dataset/filter/list")
    op_ids = [o["id"] for o in r.json()["operators"]]
    assert len(op_ids) == 10
    payloads = {
        "filter.top_k": {"data": [{"score": 0.9}, {"score": 0.5}], "params": {"k": 1}},
        "filter.percentile": {"data": [0.1, 0.5, 0.9], "params": {"percentile": 50}},
        "filter.threshold": {"data": [0.1, 0.5, 0.9], "params": {"min": 0.3, "max": 0.7}},
        "filter.diversity": {"data": ["hello world", "foo bar"], "params": {"k": 1}},
        "filter.balance": {"data": [{"label": "A"}, {"label": "B"}], "params": {"target_per_class": 1}},
        "filter.language": {"data": ["hello", "你好"], "params": {"target": "any"}},
        "filter.domain": {"data": ["apple"], "params": {"include_keywords": ["apple"]}},
        "filter.quality": {"data": [{"scores": {"aesthetic": 80}}], "params": {"min_score": 50}},
        "filter.random_sample": {"data": [1, 2, 3, 4, 5], "params": {"n": 2, "seed": 1}},
        "filter.rule_based": {"data": [{"x": 5}], "params": {"rules": [{"field": "x", "op": "gte", "value": 3}]}},
    }
    for op_id in op_ids:
        r2 = dataset_client.post(f"/api/v1/dataset/filter/{op_id}/run", json=payloads[op_id])
        assert r2.status_code == 200, f"{op_id} returned {r2.status_code} {r2.text}"


def test_export_dynamic_dispatch_all_12(dataset_client, tmp_path):
    """POST /api/v1/dataset/export/{op_id}/run works for every op in the registry."""
    r = dataset_client.get("/api/v1/dataset/export/list")
    op_ids = [o["id"] for o in r.json()["operators"]]
    assert len(op_ids) == 12
    payload_per_op = {
        "export.jsonl": {"data": [{"a": 1}], "params": {"path": str(tmp_path / "x.jsonl")}},
        "export.parquet": {"data": [{"a": 1}], "params": {"path": str(tmp_path / "x.csv")}},
        "export.csv": {"data": [{"a": 1}], "params": {"path": str(tmp_path / "x.csv")}},
        "export.tfrecord": {"data": [{"x": "y"}], "params": {"path": str(tmp_path / "x.tfrecord")}},
        "export.coco": {"data": [{"image": "a.jpg", "bbox": [[0, 0, 10, 10]], "category": ["o"]}],
                        "params": {"path": str(tmp_path / "coco.json")}},
        "export.voc": {"data": [{"image": "a.jpg", "bbox": [[0, 0, 10, 10]], "category": ["o"]}],
                       "params": {"dir": str(tmp_path / "voc")}},
        "export.yolo": {"data": [{"image": "a.jpg", "width": 100, "height": 100,
                                   "bbox": [[10, 10, 50, 50]], "category": ["c"]}],
                        "params": {"dir": str(tmp_path / "yolo")}},
        "export.alpaca": {"data": [{"instruction": "q", "output": "a"}],
                          "params": {"path": str(tmp_path / "a.jsonl")}},
        "export.sharegpt": {"data": [{"conversations": [{"from": "human", "value": "hi"}]}],
                            "params": {"path": str(tmp_path / "s.jsonl")}},
        "export.conversation": {"data": [{"messages": [{"role": "user", "content": "hi"}]}],
                                "params": {"path": str(tmp_path / "c.jsonl")}},
        "export.video_frames": {"data": ["v1.mp4"], "params": {"dir": str(tmp_path / "vf"), "fps": 1.0}},
        "export.audio_wav": {"data": [{"samples": [0, 1, 0, -1] * 50}],
                             "params": {"dir": str(tmp_path / "aw"), "sample_rate": 8000}},
    }
    for op_id in op_ids:
        r2 = dataset_client.post(f"/api/v1/dataset/export/{op_id}/run", json=payload_per_op[op_id])
        assert r2.status_code == 200, f"{op_id} returned {r2.status_code} {r2.text}"
