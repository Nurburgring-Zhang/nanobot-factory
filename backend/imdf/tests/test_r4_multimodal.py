"""VDP-2026 R4 — Multimodal coordinator tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from capabilities_v2.engine import (  # noqa: E402
    configure_db as configure_cap_db, reset_registry_for_test,
)
from orchestration.bus import configure_db as configure_bus_db, reset_bus_for_test  # noqa: E402
from multimodal_v2.engine import (  # noqa: E402
    Modality, MODALITIES, EXPORTS, MultimodalPipeline, ModalityRegistry,
    get_pipeline, reset_pipeline_for_test, configure_db,
)


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    configure_cap_db(tmp_path / "cap.db")
    configure_bus_db(tmp_path / "bus.db")
    configure_db(tmp_path / "mm.db")
    reset_registry_for_test()
    reset_bus_for_test()
    reset_pipeline_for_test()
    yield


class TestCatalogue:
    def test_eight_modalities(self):
        assert len(MODALITIES) == 8
        for k in ("image", "video", "text", "audio", "multimodal", "sketch", "drama", "picturebook"):
            assert k in MODALITIES

    def test_each_modality_has_engine(self):
        for m in MODALITIES.values():
            assert m.default_engine
            assert m.label
            assert m.description
            assert m.canonical_formats

    def test_nine_exports(self):
        assert len(EXPORTS) >= 9
        for e in EXPORTS:
            assert e.format
            assert e.capability_id  # each export maps to R1 capability

    def test_describe_payload(self):
        p = get_pipeline()
        d = p.describe()
        assert "modalities" in d and "exports" in d and "format_modality_map" in d
        assert "coco" in d["format_modality_map"]


class TestRegistry:
    def test_by_format(self):
        reg = ModalityRegistry()
        ms = reg.by_format("coco")
        assert any(m.key == "image" for m in ms)


class TestPipeline:
    def test_run_image(self):
        p = get_pipeline()
        run = p.run(modality="image", inputs={"asset_count": 4})
        assert run.status == "succeeded"
        assert "artifacts" in run.outputs
        assert "preview" in run.outputs["artifacts"]
        runs = p.list_runs(modality="image")
        assert any(r["id"] == run.id for r in runs)

    def test_run_unknown_modality_raises(self):
        p = get_pipeline()
        with pytest.raises(ValueError):
            p.run(modality="invalid", inputs={})

    def test_run_video_preview_shape(self):
        p = get_pipeline()
        run = p.run(modality="video", inputs={"asset_count": 100})
        assert run.outputs["artifacts"]["preview"]["duration_s"] == 5
        assert run.outputs["artifacts"]["preview"]["fps"] == 24

    def test_run_drama_preview_shape(self):
        p = get_pipeline()
        run = p.run(modality="drama", inputs={"asset_count": 60})
        assert run.outputs["artifacts"]["preview"]["shots"] == 6

    def test_run_emits_bus_event(self):
        from orchestration.bus import get_bus
        p = get_pipeline()
        run = p.run(modality="text", inputs={"asset_count": 1})
        bus = get_bus()
        rows = bus.query(source_module="multimodal_v2")
        assert len(rows) >= 1

    def test_run_with_capability_steps(self):
        # When steps are provided, pipeline invokes each step through the registry
        p = get_pipeline()
        run = p.run(
            modality="image",
            inputs={"asset_count": 1},
            spec={"steps": [
                {"capability_id": "project.create", "inputs": {"name": "mm-x"}},
            ]},
        )
        assert "step_0" in run.outputs["artifacts"]
        assert run.outputs["artifacts"]["step_0"]["status"] in ("success", "error")


class TestHTTP:
    def _client(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
        except ImportError:
            return None
        from multimodal_v2.routes import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_routes(self):
        client = self._client()
        if client is None:
            pytest.skip("fastapi")
        r = client.get("/api/v1/multimodal_v2/modalities")
        assert r.status_code == 200
        assert r.json()["total"] == 8
        r = client.get("/api/v1/multimodal_v2/exports")
        assert r.status_code == 200
        assert r.json()["total"] >= 9
        r = client.get("/api/v1/multimodal_v2/modalities/image")
        assert r.status_code == 200
        r = client.get("/api/v1/multimodal_v2/modalities/bogus")
        assert r.status_code == 404
        r = client.post("/api/v1/multimodal_v2/run", json={"modality": "video", "inputs": {"asset_count": 10}})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "succeeded"
        r = client.post("/api/v1/multimodal_v2/run", json={"modality": "unknown"})
        assert r.status_code == 400
        r = client.get("/api/v1/multimodal_v2/health")
        assert r.status_code == 200
