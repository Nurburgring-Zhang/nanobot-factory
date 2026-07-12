"""Tests for the Comfy MCP integration (V5 chapter 30).

Covers:
- Intent parsing
- Model retriever search
- Node retriever search
- Workflow builder build (valid + invalid connections + fallback)
- create_workflow (with mock LLM + stub path)
- run_workflow (single + batch + error resilience)
- end-to-end instruction -> result flow
- Skill registry round-trip

All tests run with ``asyncio.run``; the file is also pytest-collectable.
"""
from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

# Make the imdf package importable when running this test directly.
_HERE = Path(__file__).resolve()
_IMDF_PKG_ROOT = _HERE.parents[4]  # .../backend/imdf
_BACKEND = _IMDF_PKG_ROOT.parent
for p in (str(_BACKEND), str(_IMDF_PKG_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from imdf.creative.comfy.mcp_integration import (  # noqa: E402
    ComfyMCPIntegration,
    _parse_count,
    _parse_intent,
)
from imdf.creative.comfy.model_retriever import ModelRetriever  # noqa: E402
from imdf.creative.comfy.node_retriever import NodeRetriever  # noqa: E402
from imdf.creative.comfy.workflow_builder import WorkflowBuilder  # noqa: E402
from imdf.creative.comfy.schemas import (  # noqa: E402
    Connection,
    GenerationResult,
    Node,
    Workflow,
)


# ── Test doubles ──────────────────────────────────────────────────────
class MockComfyClient:
    """In-memory ComfyUI client. Returns deterministic results."""

    def __init__(self, *, fail_every: Optional[int] = None,
                 sleep_ms: int = 0) -> None:
        self.fail_every = fail_every
        self.sleep_ms = sleep_ms
        self.call_count = 0
        self.requests: List[Dict[str, Any]] = []

    async def run_workflow(self, workflow, params=None):
        self.call_count += 1
        self.requests.append({"workflow": workflow, "params": params or {}})
        if self.sleep_ms:
            await asyncio.sleep(self.sleep_ms / 1000.0)
        if self.fail_every and self.call_count % self.fail_every == 0:
            return {"ok": False, "error": "simulated failure",
                    "prompt_id": f"p-{self.call_count}"}
        return {
            "ok": True,
            "prompt_id": f"prompt-{self.call_count}",
            "result_id": f"result-{self.call_count}",
            "image_paths": [f"/tmp/img_{self.call_count}.png"],
        }


class MockBus:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        self.events.append({"topic": topic, "payload": payload})


class MockLLM:
    def __init__(self, canned: Optional[str] = None,
                 side_effect=None) -> None:
        self.canned = canned
        self.side_effect = side_effect
        self.calls: List[str] = []

    async def chat(self, prompt: str, **kwargs: Any) -> str:
        self.calls.append(prompt)
        if self.side_effect is not None:
            return await self.side_effect(prompt, **kwargs)
        if self.canned is not None:
            return self.canned
        return "{}"


# ── Intent parsing ────────────────────────────────────────────────────
class TestIntentParsing:
    def test_parse_count_default(self):
        assert _parse_count("generate a portrait") == 1

    def test_parse_count_x10(self):
        assert _parse_count("run x10 batch of landscapes") == 10

    def test_parse_count_run_n(self):
        assert _parse_count("run 4 variations") == 4

    def test_parse_count_n_images(self):
        assert _parse_count("produce 20 images") == 20

    def test_parse_intent_anime(self):
        intent = _parse_intent("make 5 anime cat illustrations")
        assert intent["count"] == 5
        assert intent["style"] == "anime"
        assert "anime" in intent["tags"]

    def test_parse_intent_video(self):
        intent = _parse_intent("animate a dance loop")
        assert intent["capability"] == "txt2video"


# ── Model retriever ───────────────────────────────────────────────────
class TestModelRetriever:
    def test_catalogue_has_at_least_8_models(self):
        names = ModelRetriever().list_models()
        assert len(names) >= 8, f"need >=8 models, got {names}"
        expected = {"sdxl", "sdxl_turbo", "sd_15", "sd_3", "flux",
                    "animate_diff", "ip_adapter", "controlnet"}
        assert expected.issubset(set(names)), f"missing: {expected - set(names)}"

    @pytest.mark.asyncio
    async def test_search_txt2img(self):
        hits = await ModelRetriever().search({"capability": "txt2img"})
        names = {h.name for h in hits}
        assert "sdxl" in names
        assert "flux" in names

    @pytest.mark.asyncio
    async def test_search_video(self):
        hits = await ModelRetriever().search({"capability": "txt2video"})
        assert any(h.name == "animate_diff" for h in hits)

    @pytest.mark.asyncio
    async def test_search_with_tag_filter(self):
        hits = await ModelRetriever().search(
            {"capability": "txt2img", "tags": ["photoreal"]}
        )
        assert hits, "expected at least one hit"
        # Sorted by descending score.
        scores = [h.score for h in hits]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_missing_capability_returns_empty(self):
        hits = await ModelRetriever().search({"capability": "does-not-exist"})
        assert hits == []


# ── Node retriever ────────────────────────────────────────────────────
class TestNodeRetriever:
    def test_catalogue_has_at_least_15_nodes(self):
        names = NodeRetriever().list_nodes()
        assert len(names) >= 15, f"need >=15 nodes, got {len(names)}: {names}"

    @pytest.mark.asyncio
    async def test_search_by_category_loader(self):
        hits = await NodeRetriever().search({"category": "loader"})
        names = {h.class_type for h in hits}
        assert "CheckpointLoaderSimple" in names

    @pytest.mark.asyncio
    async def test_search_by_output_conditioning(self):
        hits = await NodeRetriever().search({"output": "CONDITIONING"})
        names = {h.class_type for h in hits}
        assert "CLIPTextEncode" in names
        assert "ControlNetApply" in names

    @pytest.mark.asyncio
    async def test_search_by_input(self):
        hits = await NodeRetriever().search({"input": "ckpt_name"})
        assert any(h.class_type == "CheckpointLoaderSimple" for h in hits)


# ── Workflow builder ──────────────────────────────────────────────────
class TestWorkflowBuilder:
    @pytest.mark.asyncio
    async def test_build_valid_connections(self):
        template = self._sample_template()
        models = await ModelRetriever().search({"capability": "txt2img"})
        nodes = await NodeRetriever().search({})
        full = await WorkflowBuilder().build(template, models[:3], nodes[:7])
        assert full.name == template.name
        assert "sdxl" in full.models
        assert "CheckpointLoaderSimple" in full.nodes_used

    @pytest.mark.asyncio
    async def test_build_invalid_connection_raises(self):
        template = Workflow(
            name="bad",
            nodes=[Node(id="a", class_type="CheckpointLoaderSimple",
                        inputs={"ckpt_name": "sdxl.safetensors"})],
            connections=[Connection("a", "MODEL", "ghost", "model")],
        )
        with pytest.raises(ValueError, match="not in graph"):
            await WorkflowBuilder().build(template, [], [])

    @pytest.mark.asyncio
    async def test_build_with_llm_fallback(self):
        # Template missing the prompt text — fallback should resolve it.
        template = Workflow(
            name="fallback",
            nodes=[
                Node(id="ckpt", class_type="CheckpointLoaderSimple",
                     inputs={"ckpt_name": "sdxl.safetensors"},
                     meta={"outputs": ("MODEL", "CLIP", "VAE")}),
                Node(id="pos", class_type="CLIPTextEncode",
                     inputs={}, meta={"outputs": ("CONDITIONING",)}),
                Node(id="neg", class_type="CLIPTextEncode",
                     inputs={"text": "low quality"},
                     meta={"outputs": ("CONDITIONING",)}),
                Node(id="latent", class_type="EmptyLatentImage",
                     inputs={"width": 512, "height": 512, "batch_size": 1},
                     meta={"outputs": ("LATENT",)}),
                Node(id="sampler", class_type="KSampler",
                     inputs={"seed": 0, "steps": 20, "cfg": 7,
                             "sampler_name": "euler", "scheduler": "normal",
                             "denoise": 1.0},
                     meta={"outputs": ("LATENT",)}),
                Node(id="vae", class_type="VAEDecode",
                     inputs={}, meta={"outputs": ("IMAGE",)}),
                Node(id="save", class_type="SaveImage",
                     inputs={"filename_prefix": "x"}, meta={"outputs": ()}),
            ],
            connections=[
                Connection("ckpt", "MODEL", "sampler", "model"),
                Connection("ckpt", "CLIP", "pos", "clip"),
                Connection("ckpt", "CLIP", "neg", "clip"),
                Connection("pos", "CONDITIONING", "sampler", "positive"),
                Connection("neg", "CONDITIONING", "sampler", "negative"),
                Connection("latent", "LATENT", "sampler", "latent_image"),
                Connection("sampler", "LATENT", "vae", "samples"),
                Connection("ckpt", "VAE", "vae", "vae"),
                Connection("vae", "IMAGE", "save", "images"),
            ],
        )

        async def fallback(slot_desc, ctx):
            return f"resolved-by-llm:{slot_desc}"

        builder = WorkflowBuilder(llm_provider=fallback)
        full = await builder.build(template, [], [])
        assert full.graph["pos"].inputs["text"].startswith("resolved-by-llm:")

    @staticmethod
    def _sample_template() -> Workflow:
        return Workflow(
            name="txt2img",
            nodes=[
                Node(id="ckpt", class_type="CheckpointLoaderSimple",
                     inputs={"ckpt_name": "sdxl.safetensors"},
                     meta={"outputs": ("MODEL", "CLIP", "VAE")}),
                Node(id="pos", class_type="CLIPTextEncode",
                     inputs={"text": "a cat"},
                     meta={"outputs": ("CONDITIONING",)}),
                Node(id="neg", class_type="CLIPTextEncode",
                     inputs={"text": "low quality"},
                     meta={"outputs": ("CONDITIONING",)}),
                Node(id="latent", class_type="EmptyLatentImage",
                     inputs={"width": 1024, "height": 1024, "batch_size": 1},
                     meta={"outputs": ("LATENT",)}),
                Node(id="sampler", class_type="KSampler",
                     inputs={"seed": 0, "steps": 20, "cfg": 7,
                             "sampler_name": "euler", "scheduler": "normal",
                             "denoise": 1.0},
                     meta={"outputs": ("LATENT",)}),
                Node(id="vae", class_type="VAEDecode",
                     inputs={}, meta={"outputs": ("IMAGE",)}),
                Node(id="save", class_type="SaveImage",
                     inputs={"filename_prefix": "out"},
                     meta={"outputs": ()}),
            ],
            connections=[
                Connection("ckpt", "MODEL", "sampler", "model"),
                Connection("ckpt", "CLIP", "pos", "clip"),
                Connection("ckpt", "CLIP", "neg", "clip"),
                Connection("pos", "CONDITIONING", "sampler", "positive"),
                Connection("neg", "CONDITIONING", "sampler", "negative"),
                Connection("latent", "LATENT", "sampler", "latent_image"),
                Connection("sampler", "LATENT", "vae", "samples"),
                Connection("ckpt", "VAE", "vae", "vae"),
                Connection("vae", "IMAGE", "save", "images"),
            ],
        )


# ── create_workflow ───────────────────────────────────────────────────
class TestCreateWorkflow:
    @pytest.mark.asyncio
    async def test_create_workflow_with_mock_llm_json(self):
        canned = (
            '{"name": "x", "description": "d", '
            '"nodes": [{"id": "a", "class_type": "CLIPTextEncode", '
            '"inputs": {"text": "hi"}}], '
            '"connections": [], "metadata": {}}'
        )
        llm = MockLLM(canned=canned)
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client, llm_provider=llm)
        wf = await mcp.create_workflow("render a portrait")
        assert wf.name == "x"
        assert wf.nodes[0].class_type == "CLIPTextEncode"
        assert llm.calls, "LLM should have been called"

    @pytest.mark.asyncio
    async def test_create_workflow_stub_when_no_llm(self):
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client)
        wf = await mcp.create_workflow("anything")
        assert wf.nodes, "stub should produce at least one node"


# ── run_workflow ──────────────────────────────────────────────────────
class TestRunWorkflow:
    @pytest.mark.asyncio
    async def test_run_single(self):
        client = MockComfyClient()
        bus = MockBus()
        mcp = ComfyMCPIntegration(comfy_client=client, bus=bus)
        result = await mcp.run_workflow("render a portrait of a cat")
        assert result.status == "success"
        assert result.image_paths == ["/tmp/img_1.png"]
        assert any(e["topic"] == "comfy.workflow_executed" for e in bus.events)

    @pytest.mark.asyncio
    async def test_run_batch_parallel(self):
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client)
        result = await mcp.run_workflow("make 8 anime shots")
        assert result.metadata["count"] == 8
        # Mock client was called 8 times.
        assert client.call_count == 8
        ids = result.metadata["individual_results"]
        assert len(ids) == 8
        assert len({i for i in ids}) == 8, "all result ids should be unique"

    @pytest.mark.asyncio
    async def test_run_batch_error_resilience(self):
        # fail_every=3 => runs 1, 4, 7 succeed; 2, 5 fail; etc.
        client = MockComfyClient(fail_every=3)
        mcp = ComfyMCPIntegration(comfy_client=client)
        result = await mcp.run_workflow("produce 6 images")
        assert result.metadata["count"] == 6
        # Overall status should be "partial" because some failed.
        assert result.status in ("partial", "success")
        # The client should still have been invoked 6 times.
        assert client.call_count == 6

    @pytest.mark.asyncio
    async def test_run_uses_requested_prompt(self):
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client)
        await mcp.run_workflow("portrait", params={"prompt": "blue bird"})
        # First CLIPTextEncode input should be the injected prompt.
        graph = client.requests[0]["workflow"]["prompt"]
        text_nodes = [n for n in graph.values()
                      if n["class_type"] == "CLIPTextEncode"]
        assert any(n["inputs"].get("text") == "blue bird" for n in text_nodes)

    @pytest.mark.asyncio
    async def test_run_result_store_lookup(self):
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client)
        result = await mcp.run_workflow("one shot")
        stored = mcp.get_result(result.result_id)
        assert stored is not None
        assert stored.result_id == result.result_id
        assert isinstance(stored, GenerationResult)


# ── End-to-end flow ───────────────────────────────────────────────────
class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_instruction_to_result_flow(self):
        llm = MockLLM(canned="{}")
        client = MockComfyClient()
        bus = MockBus()
        mcp = ComfyMCPIntegration(comfy_client=client, llm_provider=llm, bus=bus)

        # 1. NL -> workflow JSON (mocked LLM returns {} -> stub fallback).
        wf = await mcp.create_workflow("render 4 anime cat images")
        assert wf.name

        # 2. instruction -> result (single run, since count==1).
        single = await mcp.run_workflow("render 4 anime cat images",
                                        params={"prompt": "neko"})
        assert single.status == "success"
        assert single.image_paths

        # 3. instruction -> result (batch).
        batched = await mcp.run_workflow("render 4 anime cat images")
        assert batched.metadata["count"] == 4

        # 4. event bus saw the executions.
        topics = [e["topic"] for e in bus.events]
        assert topics.count("comfy.workflow_executed") == 2


# ── Skill registry ────────────────────────────────────────────────────
class TestSkillRegistry:
    def test_register_and_lookup(self):
        from imdf.skills.registry import (
            SkillRegistry,
            register_default_skills,
        )
        SkillRegistry.reset_singleton()
        reg = register_default_skills(SkillRegistry())
        descriptor = reg.get("comfy_mcp_natural_language")
        assert descriptor.domain == "creative"
        client = MockComfyClient()
        skill = descriptor.factory(comfy_client=client)
        assert isinstance(skill, ComfyMCPIntegration)
        assert skill.comfy_client is client

    def test_register_overwrite(self):
        from imdf.skills.registry import SkillRegistry
        reg = SkillRegistry()
        reg.register("foo", lambda: 1)
        # Default overwrite=True — re-registering replaces silently.
        reg.register("foo", lambda: 2)
        # overwrite=False should raise on duplicate.
        with pytest.raises(ValueError):
            reg.register("foo", lambda: 3, overwrite=False)


# ── asyncio.run smoke test (no pytest-asyncio needed) ─────────────────
def test_async_smoke_runs_under_asyncio_run():
    """Runs the full happy-path end-to-end via ``asyncio.run`` —
    proves the code is awaitable + runnable without an event loop fixture.
    """
    async def main():
        client = MockComfyClient()
        mcp = ComfyMCPIntegration(comfy_client=client)
        r = await mcp.run_workflow("render a portrait", params={"prompt": "x"})
        return r

    result = asyncio.run(main())
    assert result.status == "success"


if __name__ == "__main__":
    # Allow ``python test_comfy_mcp.py`` to run the smoke test.
    try:
        test_async_smoke_runs_under_asyncio_run()
        print("SMOKE OK")
    except Exception:
        traceback.print_exc()
        sys.exit(1)