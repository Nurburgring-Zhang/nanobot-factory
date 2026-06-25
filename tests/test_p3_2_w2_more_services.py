"""P3-2-W2 smoke tests for 4 new microservices: cleaning / scoring / dataset / evaluation.

Uses TestClient (hermetic, no live uvicorn). Runs ~12+ tests across 4 services.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

# Ensure backend/ is on sys.path (so `from services.* import app` works)
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Use a temp IMDF data dir for isolation
_TMP = tempfile.mkdtemp(prefix="p3_2_w2_")
os.environ["IMDF_DATA_DIR"] = _TMP

from fastapi.testclient import TestClient


# ── cleaning-service ─────────────────────────────────────────────────────────
def _cleaning_app():
    from services.cleaning_service.main import app
    return app


def test_cleaning_healthz():
    with TestClient(_cleaning_app()) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "cleaning-service"
        # 13 base + 20 extension (incl. base64) = 33 cleaning operators
        assert data["operator_count"] >= 32
        print(f"  cleaning /healthz: {data['operator_count']} operators")


def test_cleaning_list_operators():
    with TestClient(_cleaning_app()) as c:
        r = c.get("/api/v1/clean/operators")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 32
        ids = [o["id"] for o in data["operators"]]
        assert "clean.null_filter" in ids
        assert "clean.dedup_minhash" in ids
        assert "clean.base64_cleaner" in ids
        print(f"  cleaning /api/v1/clean/operators: {data['count']} ops, sampled: {ids[:3]}")


def test_cleaning_execute():
    with TestClient(_cleaning_app()) as c:
        r = c.post(
            "/api/v1/clean/execute",
            json={
                "op_id": "clean.null_filter",
                "data": ["hello", "", None, "world", ""],
                "params": {},
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        # result should be filtered (None and "" removed by imdf filter)
        print(f"  cleaning /execute: result={data['result']}")


def test_cleaning_batch_and_category_filter():
    with TestClient(_cleaning_app()) as c:
        r = c.get("/api/v1/clean/operators?category=privacy")
        assert r.status_code == 200
        ids = [o["id"] for o in r.json()["operators"]]
        assert "clean.email_masker" in ids
        assert "clean.phone_masker" in ids
        assert "clean.id_card_masker" in ids
        assert "clean.pii_detector" in ids
        print(f"  cleaning category=privacy: {ids}")


# ── scoring-service ──────────────────────────────────────────────────────────
def _scoring_app():
    from services.scoring_service.main import app
    return app


def test_scoring_healthz():
    with TestClient(_scoring_app()) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "scoring-service"
        assert data["operator_count"] == 15
        print(f"  scoring /healthz: {data['operator_count']} scorers")


def test_scoring_list_operators():
    with TestClient(_scoring_app()) as c:
        r = c.get("/api/v1/score/operators")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 15
        ids = [o["id"] for o in data["operators"]]
        assert "score.aesthetic" in ids
        assert "score.toxicity" in ids
        assert "score.code_quality" in ids
        print(f"  scoring /operators: {data['count']} scorers, sampled: {ids[:3]}")


def test_scoring_run_text_quality():
    with TestClient(_scoring_app()) as c:
        r = c.post(
            "/api/v1/score/run",
            json={
                "op_id": "score.text_quality",
                "data": "This is a well-written sentence. It has structure. Good punctuation.",
                "params": {},
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert "result" in data
        print(f"  scoring /run text_quality: {data['result']}")


def test_scoring_rank():
    with TestClient(_scoring_app()) as c:
        r = c.post(
            "/api/v1/score/rank",
            json={
                "op_id": "score.sentiment",
                "items": ["I love this product, it's great!", "This is terrible.", "It is okay."],
                "top_k": 3,
                "descending": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 3
        # First should be the positive one
        assert data["ranking"][0]["item"] == "I love this product, it's great!"
        print(f"  scoring /rank: top item = {data['ranking'][0]['item']!r}")


# ── dataset-service ──────────────────────────────────────────────────────────
def _dataset_app():
    from services.dataset_service.main import app
    return app


def test_dataset_healthz():
    with TestClient(_dataset_app()) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "dataset-service"
        print(f"  dataset /healthz: count={data['dataset_count']}")


def test_dataset_crud():
    with TestClient(_dataset_app()) as c:
        # Initially empty
        r = c.get("/api/v1/datasets")
        assert r.status_code == 200
        assert r.json()["count"] == 0
        # Create
        ds_name = f"test_ds_{uuid.uuid4().hex[:8]}"
        r = c.post(
            "/api/v1/datasets",
            json={"name": ds_name, "data_type": "image", "description": "test"},
        )
        assert r.status_code == 201, r.text
        # List
        r = c.get("/api/v1/datasets")
        assert r.json()["count"] == 1
        # Get one
        r = c.get(f"/api/v1/datasets/{ds_name}")
        assert r.status_code == 200
        # Delete
        r = c.delete(f"/api/v1/datasets/{ds_name}")
        assert r.status_code == 200
        # 404 after delete
        r = c.get(f"/api/v1/datasets/{ds_name}")
        assert r.status_code == 404
        print(f"  dataset CRUD: created, listed, deleted {ds_name}")


def test_dataset_versions_and_samples():
    with TestClient(_dataset_app()) as c:
        ds_name = f"ver_test_{uuid.uuid4().hex[:8]}"
        c.post("/api/v1/datasets", json={"name": ds_name, "data_type": "text"})
        # Create version
        r = c.post(
            f"/api/v1/datasets/{ds_name}/versions",
            json={"version": "v1", "description": "first"},
        )
        assert r.status_code == 201
        # List versions
        r = c.get(f"/api/v1/datasets/{ds_name}/versions")
        assert r.status_code == 200
        assert r.json()["versions"][0]["version"] == "v1"
        # Add samples
        r = c.post(
            f"/api/v1/datasets/{ds_name}/versions/v1/samples",
            json={"samples": [{"text": "hello"}, {"text": "world"}]},
        )
        assert r.status_code == 201
        assert r.json()["added"] == 2
        # List samples
        r = c.get(f"/api/v1/datasets/{ds_name}/versions/v1/samples?limit=10")
        assert r.status_code == 200
        assert r.json()["count"] == 2
        # Export
        r = c.post(
            f"/api/v1/datasets/{ds_name}/versions/v1/export",
            json={"format": "jsonl"},
        )
        assert r.status_code == 200
        assert r.json()["sample_count"] == 2
        # Cleanup
        c.delete(f"/api/v1/datasets/{ds_name}")
        print(f"  dataset versions/samples: 2 samples, exported OK")


# ── evaluation-service ──────────────────────────────────────────────────────
def _evaluation_app():
    from services.evaluation_service.main import app
    return app


def test_evaluation_healthz():
    with TestClient(_evaluation_app()) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "evaluation-service"
        print(f"  evaluation /healthz: evals={data['evaluation_count']} bad_cases={data['bad_case_count']}")


def test_evaluation_metrics_catalog():
    with TestClient(_evaluation_app()) as c:
        r = c.get("/api/v1/evaluations/metrics/catalog")
        assert r.status_code == 200
        assert r.json()["count"] == 8
        names = [m["name"] for m in r.json()["metrics"]]
        assert "accuracy" in names
        assert "clip_score" in names
        print(f"  evaluation metrics: {names}")


def test_evaluation_create_run_summary():
    with TestClient(_evaluation_app()) as c:
        # Create
        r = c.post(
            "/api/v1/evaluations",
            json={
                "name": "smoke-eval",
                "model_name": "test-model",
                "dataset_name": "test-ds",
                "dataset_version": "v1",
                "metrics": ["accuracy", "f1_score"],
                "sample_size": 20,
            },
        )
        assert r.status_code == 201, r.text
        eid = r.json()["id"]
        # Run
        r = c.post(f"/api/v1/evaluations/{eid}/run")
        assert r.status_code == 200, r.text
        run_data = r.json()
        assert run_data["status"] == "success"
        assert "accuracy" in run_data["summary"]
        # Summary
        r = c.get(f"/api/v1/evaluations/{eid}/summary")
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        # Results
        r = c.get(f"/api/v1/evaluations/{eid}/results?limit=5")
        assert r.status_code == 200
        assert r.json()["total"] == 20
        print(f"  evaluation run/summary: eid={eid} samples={run_data['sample_count']} summary={run_data['summary']}")
        return eid


def test_evaluation_bad_cases_flow():
    eid = test_evaluation_create_run_summary()  # re-run last
    with TestClient(_evaluation_app()) as c:
        # Extract bad cases
        r = c.post(f"/api/v1/evaluations/{eid}/bad_cases/extract?threshold=0.99")
        assert r.status_code == 200, r.text
        bc_data = r.json()
        # With threshold=0.99 most samples should be flagged
        assert bc_data["extracted"] >= 1
        # List bad cases
        r = c.get(f"/api/v1/bad_cases?evaluation_id={eid}")
        assert r.status_code == 200
        bcs = r.json()["bad_cases"]
        assert len(bcs) >= 1
        bc_id = bcs[0]["id"]
        # Get one
        r = c.get(f"/api/v1/bad_cases/{bc_id}")
        assert r.status_code == 200
        # Patch status
        r = c.patch(
            f"/api/v1/bad_cases/{bc_id}/status",
            json={"status": "fixed", "note": "smoke test fix"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "fixed"
        print(f"  evaluation bad_cases: extracted={bc_data['extracted']}, patched 1 to 'fixed'")


# ── runner ───────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("P3-2-W2 smoke test runner — 4 microservices")
    print("=" * 60)
    tests = [
        # cleaning
        ("cleaning /healthz", test_cleaning_healthz),
        ("cleaning /operators", test_cleaning_list_operators),
        ("cleaning /execute", test_cleaning_execute),
        ("cleaning /operators?category", test_cleaning_batch_and_category_filter),
        # scoring
        ("scoring /healthz", test_scoring_healthz),
        ("scoring /operators", test_scoring_list_operators),
        ("scoring /run text_quality", test_scoring_run_text_quality),
        ("scoring /rank", test_scoring_rank),
        # dataset
        ("dataset /healthz", test_dataset_healthz),
        ("dataset CRUD", test_dataset_crud),
        ("dataset versions+samples+export", test_dataset_versions_and_samples),
        # evaluation
        ("evaluation /healthz", test_evaluation_healthz),
        ("evaluation /metrics/catalog", test_evaluation_metrics_catalog),
        ("evaluation create+run+summary", test_evaluation_create_run_summary),
        ("evaluation bad_cases flow", test_evaluation_bad_cases_flow),
    ]
    passed, failed = 0, 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"  PASS: {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  FAIL: {name}: {e}")
    print("=" * 60)
    print(f"TOTAL: {passed} passed, {failed} failed (out of {len(tests)})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
