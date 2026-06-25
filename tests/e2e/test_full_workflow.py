"""End-to-End tests: full workflow — register → annotate → review → deliver.

Uses the FastAPI TestClient to simulate a complete annotation pipeline workflow.
Each step validates HTTP status codes and response content.
"""
import os
import sys
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ["JWT_SECRET"] = "test-secret-key-for-pytest-e2e-32chars!!"

# Base URL for tests - can be overridden with IMDF_TEST_URL env var
BASE_URL = os.environ.get("IMDF_TEST_URL", "")


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient for E2E workflow tests."""
    from api.canvas_web import app
    with TestClient(app) as c:
        yield c


# ── Helper: Response validation ─────────────────────────────────────────

def assert_ok(resp, step_name: str):
    """Assert response is 2xx, with a helpful failure message."""
    assert 200 <= resp.status_code < 300, (
        f"[{step_name}] Expected 2xx, got {resp.status_code}: {resp.text[:500]}"
    )


def assert_status(resp, expected: int, step_name: str):
    """Assert response status is exactly 'expected'."""
    assert resp.status_code == expected, (
        f"[{step_name}] Expected {expected}, got {resp.status_code}: {resp.text[:500]}"
    )


def assert_json_has(resp, *keys, step_name: str = ""):
    """Assert JSON response contains all specified keys."""
    data = resp.json()
    for k in keys:
        assert k in data, f"[{step_name}] Response missing key '{k}': {data}"


# ═══════════════════════════════════════════════════════════════════════════
#  E2E Workflow: Registration → Annotation → Review → Delivery
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.e2e
class TestRegistrationLogin:
    """Phase 1: User registration and authentication."""

    def test_register_new_user(self, client):
        """Register a new annotator account."""
        resp = client.post("/auth/register", json={
            "username": "annotator_e2e",
            "password": "StrongP@ss1",
            "role": "annotator",
        })
        assert_ok(resp, "register")
        data = resp.json()
        assert data["username"] == "annotator_e2e"
        assert data["role"] == "annotator"
        assert "created_at" in data

    def test_register_reviewer_account(self, client):
        """Register a reviewer account for the pipeline."""
        resp = client.post("/auth/register", json={
            "username": "reviewer_e2e",
            "password": "StrongP@ss2",
            "role": "reviewer",
        })
        assert_ok(resp, "register reviewer")

    def test_login_annotator(self, client):
        """Login as annotator to obtain JWT."""
        resp = client.post("/auth/login", json={
            "username": "annotator_e2e",
            "password": "StrongP@ss1",
        })
        assert_ok(resp, "login annotator")
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20

    def test_login_reviewer(self, client):
        """Login as reviewer to obtain JWT."""
        resp = client.post("/auth/login", json={
            "username": "reviewer_e2e",
            "password": "StrongP@ss2",
        })
        assert_ok(resp, "login reviewer")
        return resp.json()["access_token"]

    def test_invalid_login_rejected(self, client):
        """Invalid credentials should be rejected with 401."""
        resp = client.post("/auth/login", json={
            "username": "annotator_e2e",
            "password": "WrongPassword1",
        })
        assert_status(resp, 401, "invalid login")


@pytest.mark.e2e
class TestAPIKeyWorkflow:
    """Phase 2: Create and use API keys."""

    @pytest.fixture
    def annotator_headers(self, client):
        """Get auth headers for the annotator."""
        resp = client.post("/auth/login", json={
            "username": "annotator_e2e",
            "password": "StrongP@ss1",
        })
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def test_create_api_key(self, client, annotator_headers):
        """Annotator creates an API key."""
        resp = client.post("/api/v1/api-keys/create",
                           json={"name": "e2e-production-key"},
                           headers=annotator_headers)
        assert_ok(resp, "create api key")
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["key"].startswith("imdf_sk-")
        assert data["data"]["name"] == "e2e-production-key"

    def test_list_api_keys(self, client, annotator_headers):
        """List API keys shows the created key."""
        resp = client.get("/api/v1/api-keys", headers=annotator_headers)
        assert_ok(resp, "list api keys")
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1
        # Keys should NOT expose the secret key value
        for entry in data["data"]:
            assert "key" not in entry  # Only id, name, metadata

    def test_revoke_and_recreate_key(self, client, annotator_headers):
        """Revoke an API key and create a new one."""
        # Create
        create_resp = client.post("/api/v1/api-keys/create",
                                  json={"name": "temp-key"},
                                  headers=annotator_headers)
        key_id = create_resp.json()["data"]["id"]

        # Revoke
        revoke_resp = client.delete(f"/api/v1/api-keys/{key_id}",
                                    headers=annotator_headers)
        assert_ok(revoke_resp, "revoke key")

        # Create another
        resp = client.post("/api/v1/api-keys/create",
                           json={"name": "replacement-key"},
                           headers=annotator_headers)
        assert_ok(resp, "create replacement key")
        assert resp.json()["data"]["key"].startswith("imdf_sk-")


@pytest.mark.e2e
class TestAnnotationPipeline:
    """Phase 3: Annotation and review pipeline."""

    def test_annotation_submission(self):
        """Test submitting annotations to the pipeline engine."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()

        # Submit annotations for review
        item1 = {"id": "e2e_item_001", "label": "cat", "bbox": [0.1, 0.1, 0.5, 0.5]}
        item2 = {"id": "e2e_item_002", "label": "dog", "bbox": [0.2, 0.2, 0.4, 0.4]}
        item3 = {"id": "e2e_item_003", "label": "bird", "bbox": [0.3, 0.3, 0.3, 0.3]}

        r1 = pipeline.submit_for_review(item1)
        r2 = pipeline.submit_for_review(item2)
        r3 = pipeline.submit_for_review(item3)

        assert r1["status"] == "pending"
        assert r2["stage"] == "initial"
        assert r3["priority"] == 2  # default normal priority

    def test_initial_review_approve(self):
        """Initial review: approve → advance to secondary."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()
        pipeline.submit_for_review({"id": "e2e_item_001"})

        result = pipeline.process_review(
            "e2e_item_001", "reviewer1",
            decision="approve",
            comments="Looks correct.",
        )
        assert result["success"] is True
        assert result["item"]["stage"] == "secondary"
        assert result["item"]["decision"] == "initial_approved"

    def test_secondary_review_approve(self):
        """Secondary review: approve → advance to final."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()
        pipeline.submit_for_review({"id": "e2e_item_001"})
        pipeline.process_review("e2e_item_001", "rev1", "approve")

        result = pipeline.process_review(
            "e2e_item_001", "rev2",
            decision="approve",
            comments="Secondary review passed.",
        )
        assert result["success"] is True
        assert result["item"]["stage"] == "final"

    def test_final_review_approve(self):
        """Final review: approve → fully approved."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()
        pipeline.submit_for_review({"id": "e2e_item_001"})
        pipeline.process_review("e2e_item_001", "rev1", "approve")
        pipeline.process_review("e2e_item_001", "rev2", "approve")

        result = pipeline.process_review(
            "e2e_item_001", "rev3",
            decision="approve",
            comments="Final approval granted.",
        )
        assert result["success"] is True
        assert result["item"]["status"] == "approved"
        assert result["item"]["decision"] == "final_approved"

    def test_review_with_rejection(self):
        """Review that rejects an annotation."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()
        pipeline.submit_for_review({"id": "e2e_item_004"})

        result = pipeline.process_review(
            "e2e_item_004", "rev1",
            decision="reject",
            comments="Label is incorrect, should be 'cat' not 'dog'.",
        )
        assert result["success"] is True
        assert result["item"]["status"] == "rejected"

    def test_review_return_for_revision(self):
        """Review that returns an item for revision."""
        from engines.annotation_quality import AnnotationPipeline

        pipeline = AnnotationPipeline()
        pipeline.submit_for_review({"id": "e2e_item_005"})

        result = pipeline.process_review(
            "e2e_item_005", "rev1",
            decision="return",
            comments="Bounding box needs adjustment.",
        )
        assert result["success"] is True
        assert result["item"]["status"] == "returned"


@pytest.mark.e2e
class TestIAAAndQuality:
    """Phase 4: Inter-annotator agreement and quality metrics."""

    def test_iaa_two_annotators(self):
        """Compute IAA for two annotators."""
        from engines.annotation_quality import IAAEngine

        rater1 = ["cat", "dog", "cat", "dog", "cat"]
        rater2 = ["cat", "dog", "cat", "bird", "cat"]

        kappa = IAAEngine.cohen_kappa(rater1, rater2)
        assert 0.4 < kappa < 1.0  # High but not perfect agreement

    def test_iaa_comprehensive_report(self):
        """Generate a comprehensive IAA report."""
        from engines.annotation_quality import IAAEngine

        annotations = [
            {"objects": [{"label": "cat"}, {"label": "dog"}]},
            {"objects": [{"label": "cat"}, {"label": "bird"}]},
        ]
        report = IAAEngine.agreement_report(annotations)
        assert "cohen_kappa_avg" in report
        assert "fleiss_kappa" in report
        assert "quality" in report
        assert report["n_annotators"] == 2

    def test_gold_standard_validation(self):
        """Validate annotations against gold standard."""
        from engines.annotation_quality import GoldStandardValidator

        gsv = GoldStandardValidator()
        gsv.add_gold_item({"id": "gold1"}, {"label": "cat"})
        gsv.add_gold_item({"id": "gold2"}, {"label": "dog"})

        annotations = [
            {"id": "gold1", "label": "cat"},
            {"id": "gold2", "label": "dog"},
        ]
        result = gsv.validate_annotator(annotations)
        assert result["annotator_accuracy"] == pytest.approx(1.0, abs=0.01)
        assert result["passed"] is True


@pytest.mark.e2e
class TestDeliveryWorkflow:
    """Phase 5: Delivery management."""

    def test_delivery_list(self, client):
        """GET /api/delivery/ should list deliveries."""
        resp = client.get("/api/delivery/")
        assert_ok(resp, "delivery list")
        data = resp.json()
        assert data["success"] is True
        assert "deliveries" in data

    def test_delivery_create(self, client):
        """POST /api/delivery/create should create a delivery."""
        resp = client.post("/api/delivery/create", json={
            "name": "E2E Test Delivery",
            "format": "json",
            "items": [
                {"id": "1", "label": "cat", "confidence": 0.95},
                {"id": "2", "label": "dog", "confidence": 0.88},
            ],
        })
        assert_ok(resp, "delivery create")
        data = resp.json()
        assert data["success"] is True
        assert "delivery_id" in data


@pytest.mark.e2e
class TestFullWorkflowIntegration:
    """End-to-end: complete workflow from registration to delivery."""

    def test_complete_workflow(self):
        """Simulate the entire pipeline: register → annotate → review → deliver."""
        from engines.annotation_quality import AnnotationPipeline, IAAEngine
        from engines.classification_engine import ClassificationEngine, ClassificationRule

        # ── Step 1: Set up classification rules ──────────────────────
        engine = ClassificationEngine(db_path=":memory:")
        engine.add_rule(ClassificationRule(
            id="wf_r001", name="人物检测", category="标注类型",
            priority=10, field="label", operator="contains", value="人物",
        ))

        # ── Step 2: Create annotation pipeline ───────────────────────
        pipeline = AnnotationPipeline()

        # Submit items for annotation
        items = [
            {"id": "wf_001", "label": "cat", "annotator": "alice"},
            {"id": "wf_002", "label": "dog", "annotator": "bob"},
            {"id": "wf_003", "label": "cat", "annotator": "alice"},
        ]
        for item in items:
            r = pipeline.submit_for_review(item, priority=2)
            assert r["status"] == "pending"

        # ── Step 3: Process reviews (3-stage pipeline) ───────────────
        for item_id in ["wf_001", "wf_002", "wf_003"]:
            # Initial review
            r1 = pipeline.process_review(item_id, "rev_initial", "approve", "OK")
            assert r1["success"] is True
            # Secondary review
            r2 = pipeline.process_review(item_id, "rev_secondary", "approve", "Good")
            assert r2["success"] is True
            # Final review
            r3 = pipeline.process_review(item_id, "rev_final", "approve", "Approved")
            assert r3["success"] is True
            assert r3["item"]["status"] == "approved"

        # ── Step 4: Check queue stats ────────────────────────────────
        stats = pipeline.get_review_queue_stats()
        assert stats["total_in_queue"] == 3
        assert stats["pending"] == 0  # All approved

        # ── Step 5: IAA quality check ────────────────────────────────
        rater_a = ["cat", "dog", "cat"]
        rater_b = ["cat", "dog", "cat"]  # Perfect agreement
        kappa = IAAEngine.cohen_kappa(rater_a, rater_b)
        assert kappa == pytest.approx(1.0, abs=0.01)

        # ── Step 6: Classify annotations ─────────────────────────────
        for item in items:
            result = engine.classify(item)
            assert isinstance(result, dict)

        # Workflow completed successfully
        assert True
