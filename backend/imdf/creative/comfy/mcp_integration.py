"""Comfy MCP — natural-language orchestrator for ComfyUI (V5 ch.30).

The :class:`ComfyMCPIntegration` is the public entry point. Given a
plain-English instruction (e.g. ``"render 20 anime-style product
shots in batch"``), it:

  1. Parses intent (count, style hints, batch flag) with a tiny
     deterministic parser — no LLM dependency at this layer.
  2. Picks / creates a workflow via the retriever + builder.
  3. Drives the (mock or real) ComfyClient to execute — once for a
     single run, ``asyncio.gather`` for batch.
  4. Persists outputs and emits a ``comfy.workflow_executed`` bus event.

The LLM provider is only consulted for two things:

  - :meth:`create_workflow` (NL -> ComfyUI workflow JSON).
  - The workflow-builder fallback path when the template is missing a
    slot the retriever cannot resolve.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from .model_retriever import ModelRetriever, ModelMatch
from .node_retriever import NodeRetriever, NodeMatch
from .schemas import (
    Connection,
    FullWorkflow,
    GenerationResult,
    Node,
    Workflow,
)
from .workflow_builder import WorkflowBuilder

logger = logging.getLogger(__name__)


# ── Bus / LLM / ComfyClient type aliases ──────────────────────────────
class BusLike:
    """Protocol-shaped description of the project's event bus.

    The real bus lives elsewhere (services.event_bus) — we only need
    ``publish(topic, payload)``. Defined here as a structural type so
    tests can pass a mock without coupling to a concrete class.
    """

    async def publish(self, topic: str, payload: Dict[str, Any]) -> None:  # pragma: no cover
        raise NotImplementedError


class LLMProviderLike:
    """Protocol-shaped description of an LLM provider."""

    async def chat(self, prompt: str, **kwargs: Any) -> str:  # pragma: no cover
        raise NotImplementedError


class ComfyClientLike:
    """Protocol-shaped description of a ComfyUI HTTP client.

    Only the methods used by the MCP layer are listed; concrete
    implementations (e.g. :mod:`engines.comfyui_engine.ComfyUIEngine`)
    may have many more.
    """

    async def run_workflow(
        self,
        workflow: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


# ── Intent parsing ────────────────────────────────────────────────────
_BATCH_RE = re.compile(
    r"\b(?:batch|x\s*(\d+)|run\s+(\d+)|(\d+)\s+(?:images?|shots?|videos?|frames?))\b",
    re.IGNORECASE,
)
# Generic "{N} <word>" detector — picks up "5 anime cat illustrations",
# "20 variations", "4 designs" etc.  We only accept counts <= 64 to
# avoid pathological inputs.
_COUNT_RE = re.compile(
    r"\b(\d+)\s+(?:images?|shots?|videos?|frames?|illustrations?|"
    r"scenes?|designs?|compositions?|variations?|renders?|"
    r"张|幅|个|件)\b",
    re.IGNORECASE,
)
# Pure "{N}" fallback at the start of the instruction ("4 cats", "10 portraits").
_LEADING_COUNT_RE = re.compile(r"^\s*(\d+)\s+\w+", re.IGNORECASE)


def _parse_count(instruction: str) -> int:
    """Return the batch count implied by the instruction.

    Falls back to ``1`` when nothing matches. We deliberately keep
    this tiny and regex-only so it works without an LLM.

    Strategy:
      1. Try explicit batch markers (``x10``, ``run 5``, ``batch``,
         ``5 images`` / ``5 shots`` / ``5 illustrations`` / ...).
      2. Fall back to any standalone integer 1-64 in the instruction.
         This handles phrases like ``"5 anime cat illustrations"`` or
         ``"8 anime shots"`` where the number is separated from the
         noun by intervening words.
    """
    if not instruction:
        return 1
    m = _BATCH_RE.search(instruction)
    if m:
        for g in m.groups():
            if g and g.isdigit():
                return max(1, min(int(g), 64))
    m2 = _COUNT_RE.search(instruction)
    if m2:
        return max(1, min(int(m2.group(1)), 64))
    m3 = _LEADING_COUNT_RE.match(instruction)
    if m3:
        return max(1, min(int(m3.group(1)), 64))
    # Last-resort fallback: first standalone integer in 1-64.
    for tok in re.finditer(r"\b(\d+)\b", instruction):
        n = int(tok.group(1))
        if 1 <= n <= 64:
            return n
    return 1


def _parse_intent(instruction: str) -> Dict[str, Any]:
    """Extract minimal structured intent from the instruction.

    Recognises:
      - batch count
      - style hints (anime / photo / noir / ...)
      - capability hints (txt2img / video / face)
    """
    text = (instruction or "").lower()
    intent: Dict[str, Any] = {
        "instruction": instruction,
        "count": _parse_count(instruction),
        "style": None,
        "capability": None,
        "tags": [],
    }

    style_table = {
        "anime": "anime", "卡通": "anime",
        "photo": "photoreal", "真实": "photoreal", "写实": "photoreal",
        "noir": "noir", "电影": "cinematic", "cinematic": "cinematic",
    }
    for token, tag in style_table.items():
        if token in text:
            intent["style"] = tag
            intent["tags"].append(tag)
            break

    if "video" in text or "动画" in text or "animate" in text:
        intent["capability"] = "txt2video"
    elif "face" in text or "人脸" in text:
        intent["capability"] = "image_prompt"
    else:
        intent["capability"] = "txt2img"
    return intent


# ── Main integration class ────────────────────────────────────────────
class ComfyMCPIntegration:
    """Top-level orchestrator.

    Args:
        comfy_client: Anything implementing :class:`ComfyClientLike`.
            Tests pass a :class:`MockComfyClient`.
        llm_provider: Used by :meth:`create_workflow` and by the
            workflow builder fallback. Optional.
        bus:          Optional event bus. If ``None`` events are logged
            instead of published.
        model_retriever: Override for tests; default constructs a
            :class:`ModelRetriever`.
        node_retriever:  Same.
    """

    EVENT_TOPIC = "comfy.workflow_executed"

    def __init__(
        self,
        comfy_client: ComfyClientLike,
        llm_provider: Optional[LLMProviderLike] = None,
        bus: Optional[BusLike] = None,
        model_retriever: Optional[ModelRetriever] = None,
        node_retriever: Optional[NodeRetriever] = None,
        workflow_builder: Optional[WorkflowBuilder] = None,
    ) -> None:
        self.comfy_client = comfy_client
        self.llm_provider = llm_provider
        self.bus = bus
        self.model_retriever = model_retriever or ModelRetriever()
        self.node_retriever = node_retriever or NodeRetriever()
        self.workflow_builder = workflow_builder or WorkflowBuilder(
            model_retriever=self.model_retriever,
            node_retriever=self.node_retriever,
            llm_provider=self._llm_fallback if llm_provider else None,
        )
        # Local in-memory result store.
        self._results: Dict[str, GenerationResult] = {}

    # ── Public API ─────────────────────────────────────────────────────
    async def run_workflow(
        self,
        instruction: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> GenerationResult:
        """End-to-end: instruction -> saved :class:`GenerationResult`.

        Steps:
          1. parse intent (count, style, capability).
          2. retrieve matching models and nodes.
          3. build a :class:`FullWorkflow` from a default template.
          4. dispatch to ComfyClient (single run or ``_batch_execute``).
          5. persist results and emit a ``comfy.workflow_executed`` event.
        """
        params = dict(params or {})
        intent = _parse_intent(instruction)
        count = int(params.pop("count", intent["count"]))

        models = await self.model_retriever.search({
            "capability": intent["capability"],
            "tags": intent["tags"] or None,
        })
        nodes = await self.node_retriever.search({})
        if not models:
            raise ValueError(
                f"no models match capability {intent['capability']!r} for "
                f"instruction: {instruction!r}"
            )

        template = self._default_template(intent, models[0])
        full = await self.workflow_builder.build(template, models, nodes)

        if count <= 1:
            results = [await self._execute_one(full, params)]
        else:
            results = await self._batch_execute(full, count, params)

        # Persist every result.
        for r in results:
            self._results[r.result_id] = r

        # Emit ONE event per call (single or batch). Subscribers that
        # need per-image events can subscribe to the inner result ids
        # via the metadata payload.
        await self._emit(self.EVENT_TOPIC, {
            "instruction": instruction,
            "workflow_id": full.workflow_id,
            "count": count,
            "result_ids": [r.result_id for r in results],
            "status": ("success" if all(r.status == "success" for r in results)
                       else "partial" if any(r.status == "success" for r in results)
                       else "failed"),
        })

        # Return the first result (single mode) or a synthetic summary.
        if count == 1:
            return results[0]
        return GenerationResult(
            result_id=f"batch-{uuid.uuid4().hex[:8]}",
            workflow_id=full.workflow_id,
            status="success" if all(r.status == "success" for r in results) else "partial",
            image_paths=[p for r in results for p in r.image_paths],
            metadata={
                "instruction": instruction,
                "count": count,
                "individual_results": [r.result_id for r in results],
            },
            duration_ms=sum(r.duration_ms for r in results),
        )

    async def create_workflow(self, description: str) -> Workflow:
        """Use the LLM to convert NL → ComfyUI workflow JSON.

        When ``llm_provider`` is None, a deterministic stub is used that
        produces a minimal 4-node txt2img workflow. Tests rely on this
        stub unless they inject a mock LLM.
        """
        if self.llm_provider is None:
            return self._stub_workflow(description)

        prompt = (
            "Convert this user instruction into a ComfyUI workflow JSON.\n"
            "Return ONLY valid JSON with keys: name, nodes, connections, metadata.\n"
            f"Instruction: {description}"
        )
        raw = await self.llm_provider.chat(prompt)
        try:
            import json
            data = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM returned non-JSON (%s); falling back to stub.", exc)
            return self._stub_workflow(description)

        return Workflow(
            name=data.get("name", "llm_workflow"),
            description=data.get("description", description),
            nodes=[Node(**n) for n in data.get("nodes", [])],
            connections=[Connection(**c) for c in data.get("connections", [])],
            metadata=data.get("metadata", {}),
        )

    # ── Batch execution ────────────────────────────────────────────────
    async def _batch_execute(
        self,
        workflow: FullWorkflow,
        count: int,
        params: Dict[str, Any],
    ) -> List[GenerationResult]:
        """Run ``workflow`` ``count`` times in parallel.

        Uses :func:`asyncio.gather` with ``return_exceptions=True`` so
        one failing run does not poison the others. Errors are
        converted into :class:`GenerationResult` with ``status="failed"``.
        """
        coros = [self._execute_one(workflow, {**params, "_seed": i}) for i in range(count)]
        outcomes = await asyncio.gather(*coros, return_exceptions=True)
        results: List[GenerationResult] = []
        for idx, outcome in enumerate(outcomes):
            if isinstance(outcome, Exception):
                logger.warning("batch run %s failed: %s", idx, outcome)
                results.append(GenerationResult(
                    result_id=f"fail-{uuid.uuid4().hex[:8]}",
                    workflow_id=workflow.workflow_id,
                    status="failed",
                    error=str(outcome),
                    metadata={"seed": idx},
                ))
            else:
                results.append(outcome)
        return results

    async def _execute_one(
        self,
        workflow: FullWorkflow,
        params: Dict[str, Any],
    ) -> GenerationResult:
        """Execute a single run via the ComfyClient.

        ``params`` may include prompt overrides — we copy them into the
        node inputs of the first ``CLIPTextEncode`` we find.
        """
        started = time.monotonic()
        # Inject prompt params into the JSON-serialisable graph.
        graph_json: Dict[str, Any] = {
            nid: {
                "class_type": node.class_type,
                "inputs": dict(node.inputs),
            }
            for nid, node in workflow.graph.items()
        }
        if "prompt" in params:
            for nid, node in workflow.graph.items():
                if node.class_type == "CLIPTextEncode":
                    graph_json[nid]["inputs"]["text"] = params["prompt"]
                    break

        try:
            client_response = await self.comfy_client.run_workflow(
                {"prompt": graph_json},
                params,
            )
        except Exception as exc:  # noqa: BLE001
            return GenerationResult(
                result_id=f"err-{uuid.uuid4().hex[:8]}",
                workflow_id=workflow.workflow_id,
                status="failed",
                error=str(exc),
                metadata={"params": params},
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        result_id = client_response.get("result_id") or f"gen-{uuid.uuid4().hex[:8]}"
        image_paths = client_response.get("image_paths", [])
        return GenerationResult(
            result_id=result_id,
            workflow_id=workflow.workflow_id,
            status="success" if client_response.get("ok", True) else "failed",
            image_paths=image_paths,
            metadata={
                "prompt_id": client_response.get("prompt_id"),
                "seed": params.get("_seed"),
                "params": {k: v for k, v in params.items() if k != "_seed"},
            },
            duration_ms=duration_ms,
        )

    # ── Defaults / stubs / fallback ────────────────────────────────────
    def _default_template(
        self,
        intent: Dict[str, Any],
        primary_model: ModelMatch,
    ) -> Workflow:
        """Return a minimal 5-node txt2img template.

        Loader -> Positive prompt -> Sampler (with Negative prompt) ->
        EmptyLatent -> VAEDecode -> SaveImage. The sampler connects
        positive + negative + latent into KSampler.
        """
        ckpt_name = primary_model.name + ".safetensors"
        nodes = [
            Node(id="ckpt", class_type="CheckpointLoaderSimple",
                 inputs={"ckpt_name": ckpt_name},
                 meta={"outputs": ("MODEL", "CLIP", "VAE")}),
            Node(id="pos", class_type="CLIPTextEncode",
                 inputs={"text": intent["instruction"]},
                 meta={"outputs": ("CONDITIONING",)}),
            Node(id="neg", class_type="CLIPTextEncode",
                 inputs={"text": "low quality, blurry"},
                 meta={"outputs": ("CONDITIONING",)}),
            Node(id="latent", class_type="EmptyLatentImage",
                 inputs={"width": 1024, "height": 1024, "batch_size": 1},
                 meta={"outputs": ("LATENT",)}),
            Node(id="sampler", class_type="KSampler",
                 inputs={"seed": 0, "steps": 20, "cfg": 7.0,
                         "sampler_name": "euler", "scheduler": "normal",
                         "denoise": 1.0},
                 meta={"outputs": ("LATENT",)}),
            Node(id="vae", class_type="VAEDecode",
                 inputs={}, meta={"outputs": ("IMAGE",)}),
            Node(id="save", class_type="SaveImage",
                 inputs={"filename_prefix": "comfy_mcp"}, meta={"outputs": ()}),
        ]
        conns = [
            Connection("ckpt", "MODEL", "sampler", "model"),
            Connection("ckpt", "CLIP", "pos", "clip"),
            Connection("ckpt", "CLIP", "neg", "clip"),
            Connection("pos", "CONDITIONING", "sampler", "positive"),
            Connection("neg", "CONDITIONING", "sampler", "negative"),
            Connection("latent", "LATENT", "sampler", "latent_image"),
            Connection("sampler", "LATENT", "vae", "samples"),
            Connection("ckpt", "VAE", "vae", "vae"),
            Connection("vae", "IMAGE", "save", "images"),
        ]
        return Workflow(
            name=f"{primary_model.name}_template",
            description=f"auto-generated template for: {intent['instruction']}",
            nodes=nodes,
            connections=conns,
            metadata={"primary_model": primary_model.name,
                      "capability": intent["capability"]},
        )

    def _stub_workflow(self, description: str) -> Workflow:
        return self._default_template(_parse_intent(description), ModelMatch(
            name="sdxl",
            type="base",
            capabilities=["txt2img"],
            score=1.0,
        ))

    async def _llm_fallback(self, slot_desc: str, ctx: Dict[str, Any]) -> Any:
        """Bridge :class:`LLMProviderLike` -> :class:`WorkflowBuilder` callback."""
        if self.llm_provider is None:
            return None
        return await self.llm_provider.chat(
            f"suggest a value for workflow slot {slot_desc} ({ctx})"
        )

    async def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self.bus is None:
            logger.info("[event-bus stub] %s -> %s", topic, payload)
            return
        try:
            await self.bus.publish(topic, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("bus publish failed for %s: %s", topic, exc)

    # ── Result store helpers ───────────────────────────────────────────
    def get_result(self, result_id: str) -> Optional[GenerationResult]:
        return self._results.get(result_id)

    def list_results(self) -> List[GenerationResult]:
        return list(self._results.values())


__all__ = [
    "ComfyMCPIntegration",
    "BusLike",
    "LLMProviderLike",
    "ComfyClientLike",
]