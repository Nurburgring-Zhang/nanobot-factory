"""
P1-A1-W1: C2PA 1.4 Content Authenticity Tests
================================================
10+ test cases covering C2PAEngine class + 5 API endpoints.

Test strategy:
  * Engine-level tests use C2PAEngine directly with tmpdir cert/key.
  * API-level tests use FastAPI TestClient with isolated C2PA cert/key in tmp.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any, Generator, List

import pytest

# ── Path setup: import api package from imdf/ ─────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
_IMDF_ROOT = _BACKEND / "imdf"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_IMDF_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMDF_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Engine under test
from engines.c2pa_engine import C2PAEngine  # noqa: E402

# Routes under test
from api import copyright_routes  # noqa: E402
from api.copyright_routes import router as copyright_router  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────
def _make_asset(tmp: Path, content: bytes = None, name: str = "asset.bin") -> str:
    """Create a binary asset file in tmp dir."""
    if content is None:
        content = b"Hello C2PA world! " * 256
    p = tmp / name
    p.write_bytes(content)
    return str(p)


def _build_c2pa_app(tmp: Path) -> FastAPI:
    """Build a minimal FastAPI app with copyright router and isolated C2PA state."""
    # Reset singleton so the new cert paths take effect
    copyright_routes._reset_c2pa_engine_for_tests()

    # Override env to point at tmp cert/key (so engine picks them up)
    cert = tmp / "c2pa_cert.pem"
    key = tmp / "c2pa_key.pem"
    os.environ["C2PA_CERT_PATH"] = str(cert)
    os.environ["C2PA_KEY_PATH"] = str(key)
    copyright_routes._C2PA_CERT_PATH = str(cert)
    copyright_routes._C2PA_KEY_PATH = str(key)

    app = FastAPI()
    app.include_router(copyright_router)
    return app


@pytest.fixture
def tmp_root() -> Generator[Path, None, None]:
    """Isolated tmp dir for one test."""
    d = Path(tempfile.mkdtemp(prefix="c2pa_test_"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def _clean_c2pa_db() -> Generator[None, None]:
    """Clean c2pa_manifests table and engine singleton between API tests.

    The shared copyright.db lives at backend/data/copyright.db; without this
    fixture, prior tests' revoked manifests would leak into the CRL of later
    tests, making count-based assertions flaky.
    """
    copyright_routes._reset_c2pa_engine_for_tests()
    db_path = Path(copyright_routes.DB_PATH)
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("DELETE FROM c2pa_manifests")
                conn.commit()
        except Exception:
            pass
    yield
    # Post-test cleanup
    copyright_routes._reset_c2pa_engine_for_tests()


# ─────────────────────────────────────────────────────────────────────────
# Engine-level tests
# ─────────────────────────────────────────────────────────────────────────
class TestC2PAEngineCore:
    """Direct C2PAEngine class tests."""

    def test_01_engine_init_generates_cert_and_key(self, tmp_root: Path):
        """Init engine without pre-existing cert/key should auto-generate them."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        assert not cert.exists()
        assert not key.exists()

        engine = C2PAEngine(str(cert), str(key))
        assert cert.exists(), "cert file not created"
        assert key.exists(), "key file not created"
        assert engine.cert is not None
        assert engine.key is not None
        # cert_fingerprint is 64 hex chars (SHA-256)
        assert len(engine.cert_fingerprint()) == 64
        # CRL starts empty
        assert engine.crl == []

    def test_02_engine_reloads_existing_cert_and_key(self, tmp_root: Path):
        """Re-init engine with existing cert/key should load them (no regeneration)."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        e1 = C2PAEngine(str(cert), str(key))
        fp1 = e1.cert_fingerprint()
        e2 = C2PAEngine(str(cert), str(key))
        fp2 = e2.cert_fingerprint()
        assert fp1 == fp2, "re-loaded cert should have same fingerprint"

    def test_03_sign_asset_generates_manifest_id_and_signature(self, tmp_root: Path):
        """sign_asset should return a manifest dict with manifest_id + signature."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)

        manifest = engine.sign_asset(
            asset,
            {"creator": "alice", "actions": [{"action": "c2pa.created"}]},
        )
        assert manifest["manifest_id"].startswith("manifest_")
        assert manifest["signature"] != ""
        assert len(manifest["signature"]) > 100, "RSA-PSS sig should be >100 b64 chars"
        assert manifest["claim_generator"].startswith("IMDF-C2PA")
        assert manifest["actions"][0]["action"] == "c2pa.created"
        assert manifest["hash_algorithm"] == "sha256"
        assert manifest["signature_algorithm"] == "rsa-pss-sha256"
        assert len(manifest["asset_hash"]) == 64  # SHA-256 hex
        assert manifest["cert_fingerprint"] == engine.cert_fingerprint()

    def test_04_verify_just_signed_asset_returns_true(self, tmp_root: Path):
        """verify_signature on freshly signed asset should be True."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        engine.sign_asset(asset, {"creator": "bob"})

        is_valid, result = engine.verify_signature(asset)
        assert is_valid is True
        assert result["reason"] == "ok"

    def test_05_verify_tampered_asset_returns_false(self, tmp_root: Path):
        """Modifying the asset after signing should break verification."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        engine.sign_asset(asset, {"creator": "eve"})

        # Tamper with the asset
        with open(asset, "ab") as f:
            f.write(b"TAMPERED!")

        is_valid, result = engine.verify_signature(asset)
        assert is_valid is False
        assert result["reason"] == "asset_hash_mismatch"

    def test_06_revoke_makes_verify_return_false(self, tmp_root: Path):
        """After revoke(), verify should return False with reason=revoked."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        m = engine.sign_asset(asset, {"creator": "x"})
        # Sanity
        assert engine.verify_signature(asset)[0] is True

        # Revoke
        newly = engine.revoke(m["manifest_id"])
        assert newly is True
        assert m["manifest_id"] in engine.crl

        is_valid, result = engine.verify_signature(asset)
        assert is_valid is False
        assert result["reason"] == "revoked"

    def test_07_revoke_idempotent_returns_false_second_time(self, tmp_root: Path):
        """Revoking the same manifest_id twice: first=True, second=False."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        m = engine.sign_asset(asset, {"creator": "x"})

        assert engine.revoke(m["manifest_id"]) is True
        assert engine.revoke(m["manifest_id"]) is False
        # CRL still has only one entry
        assert engine.crl.count(m["manifest_id"]) == 1

    def test_08_crl_includes_revoked_manifest_id(self, tmp_root: Path):
        """get_crl() should include revoked manifest_ids."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        m = engine.sign_asset(asset, {"creator": "x"})
        engine.revoke(m["manifest_id"])

        crl = engine.get_crl()
        assert len(crl) == 1
        assert crl[0]["manifest_id"] == m["manifest_id"]
        assert "revoked_at" in crl[0]

    def test_09_manifest_has_chain_link(self, tmp_root: Path):
        """Each manifest should reference the previous manifest's hash (chain)."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))

        m1 = engine.sign_asset(_make_asset(tmp_root, name="a1.bin"), {"creator": "x"})
        m2 = engine.sign_asset(_make_asset(tmp_root, name="a2.bin"), {"creator": "y"})

        # First manifest has no previous
        assert m1["previous_manifest_id"] is None
        assert m1["previous_manifest_hash"] is None
        # Second manifest chains to first
        assert m2["previous_manifest_id"] == m1["manifest_id"]
        assert m2["previous_manifest_hash"] == m1["manifest_hash"]
        # Each manifest has its own manifest_hash
        assert m1["manifest_hash"] != m2["manifest_hash"]
        assert len(m1["manifest_hash"]) == 64

    def test_10_manifest_contains_required_c2pa_fields(self, tmp_root: Path):
        """Manifest must contain claim_generator, actions, hash algorithm per C2PA 1.4."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        m = engine.sign_asset(
            asset,
            {
                "creator": "alice",
                "license": "CC-BY-4.0",
                "actions": [
                    {"action": "c2pa.created", "when": "2026-06-22T01:00:00Z"}
                ],
            },
        )
        # claim_generator (required)
        assert "claim_generator" in m
        assert isinstance(m["claim_generator"], str)
        assert len(m["claim_generator"]) > 0
        # actions (required, non-empty)
        assert "actions" in m
        assert isinstance(m["actions"], list)
        assert len(m["actions"]) > 0
        assert "action" in m["actions"][0]
        # hash_algorithm (required)
        assert "hash_algorithm" in m
        assert m["hash_algorithm"] in ("sha256", "sha-256", "SHA-256", "SHA256")
        # signature_algorithm (required)
        assert "signature_algorithm" in m
        assert "pss" in m["signature_algorithm"].lower() or "rsa" in m["signature_algorithm"].lower()

    def test_11_sign_nonexistent_asset_raises(self, tmp_root: Path):
        """sign_asset on missing file should raise FileNotFoundError."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        with pytest.raises(FileNotFoundError):
            engine.sign_asset(str(tmp_root / "ghost.bin"), {"creator": "x"})

    def test_12_verify_nonexistent_asset_returns_false(self, tmp_root: Path):
        """verify_signature on missing file should return (False, error_dict)."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        is_valid, result = engine.verify_signature(str(tmp_root / "ghost.bin"))
        assert is_valid is False
        assert result.get("error") == "asset_not_found"

    def test_13_sign_with_invalid_claim_shape_raises(self, tmp_root: Path):
        """sign_asset with non-dict claim should raise ValueError."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        asset = _make_asset(tmp_root)
        with pytest.raises(ValueError):
            engine.sign_asset(asset, "not a dict")  # type: ignore[arg-type]

    def test_14_hash_chain_detects_tampered_prev_link(self, tmp_root: Path):
        """Modifying previous_manifest_hash in a manifest should break its signature."""
        cert = tmp_root / "cert.pem"
        key = tmp_root / "key.pem"
        engine = C2PAEngine(str(cert), str(key))
        m1 = engine.sign_asset(_make_asset(tmp_root, name="a1.bin"), {"creator": "x"})
        m2 = engine.sign_asset(_make_asset(tmp_root, name="a2.bin"), {"creator": "y"})
        a2 = _make_asset(tmp_root, name="a2.bin")
        sidecar = a2 + ".c2pa.json"
        # Tamper with the previous_manifest_hash in m2's sidecar
        with open(sidecar, "r", encoding="utf-8") as f:
            d = json.load(f)
        d["previous_manifest_hash"] = "0" * 64
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump(d, f)
        # Verify should fail (signature input changed)
        is_valid, result = engine.verify_signature(a2)
        assert is_valid is False
        # Either signature or manifest-hash recomputation must catch the tamper
        assert result.get("reason") in (
            "signature_verification_failed",
            "manifest_hash_mismatch",
        ), f"Unexpected reason: {result.get('reason')}"


# ─────────────────────────────────────────────────────────────────────────
# API-level tests (TestClient)
# ─────────────────────────────────────────────────────────────────────────
class TestC2PAAPIEndpoints:
    """HTTP-level tests via FastAPI TestClient."""

    @pytest.fixture
    def client(self, tmp_root: Path, _clean_c2pa_db) -> TestClient:
        app = _build_c2pa_app(tmp_root)
        return TestClient(app)

    def test_15_api_sign_returns_manifest_id(self, client: TestClient, tmp_root: Path):
        """POST /c2pa/sign returns manifest_id and full manifest."""
        asset = _make_asset(tmp_root)
        r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={
                "asset_path": asset,
                "claim": {
                    "creator": "alice",
                    "license": "CC-BY-4.0",
                    "actions": [{"action": "c2pa.created"}],
                },
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["manifest_id"].startswith("manifest_")
        assert "manifest" in data
        assert data["manifest"]["claim_generator"].startswith("IMDF-C2PA")
        assert data["manifest"]["actions"][0]["action"] == "c2pa.created"

    def test_16_api_verify_just_signed_asset(self, client: TestClient, tmp_root: Path):
        """GET /c2pa/verify/{manifest_id} should return is_valid=True for fresh sign."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "bob"}},
        )
        assert sign_r.status_code == 200
        mid = sign_r.json()["data"]["manifest_id"]

        v = client.get(f"/api/v1/copyright/c2pa/verify/{mid}")
        assert v.status_code == 200, v.text
        body = v.json()
        assert body["ok"] is True
        assert body["data"]["is_valid"] is True
        assert body["data"]["result"]["reason"] == "ok"

    def test_17_api_verify_tampered_asset(self, client: TestClient, tmp_root: Path):
        """Tampering with the asset should make verify return is_valid=False."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "x"}},
        )
        mid = sign_r.json()["data"]["manifest_id"]

        # Tamper
        with open(asset, "ab") as f:
            f.write(b"X" * 1024)

        v = client.get(f"/api/v1/copyright/c2pa/verify/{mid}")
        assert v.status_code == 200
        assert v.json()["data"]["is_valid"] is False
        assert v.json()["data"]["result"]["reason"] == "asset_hash_mismatch"

    def test_18_api_revoke_then_verify_returns_false(
        self, client: TestClient, tmp_root: Path
    ):
        """After POST /c2pa/revoke/{id}, verify should return is_valid=False."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "x"}},
        )
        mid = sign_r.json()["data"]["manifest_id"]

        # Revoke
        rv = client.post(f"/api/v1/copyright/c2pa/revoke/{mid}", json={"reason": "test"})
        assert rv.status_code == 200, rv.text
        assert rv.json()["data"]["revoked"] is True

        # Verify should now fail with reason=revoked
        v = client.get(f"/api/v1/copyright/c2pa/verify/{mid}")
        assert v.status_code == 200
        assert v.json()["data"]["is_valid"] is False
        assert v.json()["data"]["result"]["reason"] == "revoked"

    def test_19_api_crl_contains_revoked_manifest(self, client: TestClient, tmp_root: Path):
        """GET /c2pa/crl should list revoked manifests."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "x"}},
        )
        mid = sign_r.json()["data"]["manifest_id"]
        client.post(f"/api/v1/copyright/c2pa/revoke/{mid}", json={"reason": "test"})

        crl = client.get("/api/v1/copyright/c2pa/crl")
        assert crl.status_code == 200
        body = crl.json()
        assert body["ok"] is True
        assert body["data"]["count"] == 1
        ids = [e["manifest_id"] for e in body["data"]["revoked"]]
        assert mid in ids

    def test_20_api_manifest_get_returns_full_manifest(
        self, client: TestClient, tmp_root: Path
    ):
        """GET /c2pa/manifest/{id} returns the full manifest JSON."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={
                "asset_path": asset,
                "claim": {
                    "creator": "alice",
                    "actions": [{"action": "c2pa.created", "note": "init"}],
                },
            },
        )
        mid = sign_r.json()["data"]["manifest_id"]

        m = client.get(f"/api/v1/copyright/c2pa/manifest/{mid}")
        assert m.status_code == 200
        body = m.json()
        assert body["data"]["manifest_id"] == mid
        manifest = body["data"]["manifest"]
        assert manifest["claim_generator"].startswith("IMDF-C2PA")
        assert manifest["actions"][0]["action"] == "c2pa.created"
        assert manifest["hash_algorithm"] == "sha256"
        assert manifest["signature_algorithm"] == "rsa-pss-sha256"
        assert manifest["revoked"] is False

    def test_21_api_sign_missing_asset_returns_404(
        self, client: TestClient, tmp_root: Path
    ):
        """POST /c2pa/sign on missing file should return 404."""
        r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": str(tmp_root / "ghost.bin"), "claim": {"creator": "x"}},
        )
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_22_api_manifest_not_found_returns_404(self, client: TestClient):
        """GET /c2pa/manifest/manifest_doesnotexist returns 404."""
        r = client.get("/api/v1/copyright/c2pa/manifest/manifest_doesnotexist123")
        assert r.status_code == 404

    def test_23_api_revoke_unknown_manifest_returns_404(self, client: TestClient):
        """POST /c2pa/revoke/{unknown} returns 404."""
        r = client.post("/api/v1/copyright/c2pa/revoke/manifest_unknown9999", json={})
        assert r.status_code == 404

    def test_24_api_revoke_already_revoked_returns_409(
        self, client: TestClient, tmp_root: Path
    ):
        """Revoking the same manifest twice should return 409 on second call."""
        asset = _make_asset(tmp_root)
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "x"}},
        )
        mid = sign_r.json()["data"]["manifest_id"]
        # First revoke: 200
        r1 = client.post(f"/api/v1/copyright/c2pa/revoke/{mid}", json={})
        assert r1.status_code == 200
        # Second revoke: 409
        r2 = client.post(f"/api/v1/copyright/c2pa/revoke/{mid}", json={})
        assert r2.status_code == 409

    def test_25_api_sign_invalid_claim_returns_400(
        self, client: TestClient, tmp_root: Path
    ):
        """POST /c2pa/sign with claim=string (not dict) returns 422 (Pydantic)."""
        asset = _make_asset(tmp_root)
        r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": "not a dict"},
        )
        # Pydantic v2 rejects dict[str, any] = string with 422
        assert r.status_code in (400, 422)

    def test_26_api_verify_with_path_instead_of_manifest_id(
        self, client: TestClient, tmp_root: Path
    ):
        """GET /c2pa/verify/{asset_path} should also work (path-style lookup)."""
        asset = _make_asset(tmp_root, name="path_lookup.bin")
        sign_r = client.post(
            "/api/v1/copyright/c2pa/sign",
            json={"asset_path": asset, "claim": {"creator": "x"}},
        )
        assert sign_r.status_code == 200
        # Use the asset path (with backslashes escaped) as the asset_id
        v = client.get(f"/api/v1/copyright/c2pa/verify/{asset}")
        assert v.status_code == 200, v.text
        assert v.json()["data"]["is_valid"] is True
