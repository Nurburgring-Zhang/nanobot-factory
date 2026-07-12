"""P20-B / ComfyUIProvider — REAL integration with local ComfyUI server.

The ComfyUI server (https://github.com/comfyanonymous/ComfyUI) exposes its
inference API at ``http://127.0.0.1:8188`` by default. Two endpoints matter
to us:

  * ``POST /prompt`` — submit a workflow JSON (must include
    ``{"prompt": <workflow>, "client_id": <uuid>}``). Returns
    ``{"prompt_id": "..."}`` once queued.

  * ``GET  /history/{prompt_id}`` — fetch final outputs (after ``status`` WS
    message announced completion). Each node's ``images`` (or ``gifs`` /
    ``videos``) field holds the resulting filenames, which we resolve through
    ``GET /view?filename=...&type=...&subfolder=...``.

  * ``WS   /ws?clientId=<uuid>`` — receive realtime status messages
    (``status`` / ``progress`` / ``executing`` / ``execution_error`` /
    ``executed``). ``executing`` ``{"node": null}`` means the prompt finished.

This provider keeps a real, async WebSocket loop alive via the
``websockets`` package to *actually* wait for completion. No mock in the
production path — only tests inject a fake WS.

Public interface (matches P20-A contract): see ``_provider_base``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import httpx

# Module-level import so unit tests can ``patch("providers.comfyui.websockets")``
# and intercept the WebSocket connection deterministically.
import websockets

from ._provider_base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


COMFYUI_DEFAULT_BASE_URL = "http://127.0.0.1:8188"
ENV_VAR_BASE = "COMFYUI_BASE_URL"

# Default models — ComfyUI does not host a /models endpoint natively; we
# expose a curated catalogue keyed on workflow template names.
DEFAULT_MODELS: List[str] = [
    "sd_xl_base_1.0",
    "sd_xl_refiner_1.0",
    "flux1-schnell",
    "flux1-dev",
    "stable-video-diffusion",
    "hunyuan-video",
    "wan2.1",
]


# ─── Tiny structured types ───────────────────────────────────────────────────
@dataclass
class ComfyUIProgress:
    """Tracks realtime progress during a single workflow run."""
    prompt_id: str = ""
    client_id: str = ""
    started_at: float = field(default_factory=time.time)
    completed: bool = False
    success: bool = False
    progress_msgs: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


# ─── Provider ────────────────────────────────────────────────────────────────
class ComfyUIProvider(BaseProvider):
    """Real ComfyUI workflow submission + result polling via HTTP + WebSocket.

    Notes on differences from P20-A batch providers:
    - ``list_models`` returns curated workflow names (ComfyUI itself does not
      expose a model index endpoint).
    - ``invoke`` submits a workflow dict (or a template name + kwargs) and
      waits on ``/ws`` for completion, then resolves each output's image to
      a ``/view`` URL (preserving ``type`` & ``subfolder`` query params).
    - Robust fallback: when the server is unreachable, we return a clear
      ``is_placeholder=True`` response rather than crashing.
    """

    provider_name = "comfyui"
    family = "comfyui"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ):
        # ComfyUI is local — auth is unused; we still accept it for parity.
        super().__init__(
            api_key=api_key or "",
            base_url=(base_url or os.environ.get(ENV_VAR_BASE) or COMFYUI_DEFAULT_BASE_URL),
            timeout=timeout,
        )

    @classmethod
    def _default_base_url(cls) -> str:
        return COMFYUI_DEFAULT_BASE_URL

    # ── BaseProvider impl ──────────────────────────────────────────────
    async def list_models(self) -> List[str]:
        """Return curated list of ComfyUI workflow templates / model names.

        ComfyUI itself doesn't expose a /models endpoint, so we expose the
        most common workflow identifiers here.
        """
        return list(DEFAULT_MODELS)

    async def system_stats(self) -> ProviderResponse:
        """Call ``/system_stats`` to surface GPU + python + OS info."""
        t0 = self._now()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/system_stats")
            ok = resp.status_code == 200
            payload = resp.json() if ok and hasattr(resp, "json") else {}
            return ProviderResponse(
                success=ok,
                provider=self.provider_name,
                status="ok" if ok else "error",
                raw=payload,
                latency_ms=self._latency_ms(t0),
                error="" if ok else f"comfyui /system_stats HTTP {resp.status_code}",
            )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                status="unreachable",
                error=f"comfyui unreachable: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

    async def invoke(
        self,
        prompt: str,
        params: Optional[Mapping[str, Any]] = None,
        **kwargs: Any,
    ) -> ProviderResponse:
        """Submit workflow JSON to ``/prompt`` and poll until completion.

        Two calling conventions:

        1. workflow lookup — ``params={"template": "flux1-schnell",
           "text_positive": "a cat", "ckpt_name": "flux1-schnell.gguf"}`` —
           a built-in prompt template builds the workflow.

        2. explicit workflow — ``params={"workflow": {...comfy nodes...}}``
           (a full ``prompt`` graph) is sent verbatim.
        """
        params = dict(params or {})
        template: Optional[str] = params.get("template") or kwargs.get("template")
        explicit_workflow: Optional[Dict[str, Any]] = (
            params.get("workflow") or kwargs.get("workflow")
        )
        # Use the prompt text as ``positive_text`` if the workflow needs it.
        # ``model`` arg → workflow template name if no explicit workflow.
        model: str = str(
            params.get("model")
            or kwargs.get("model")
            or template
            or DEFAULT_MODELS[0],
        )
        # Allow forcing a max-wait override from caller.
        max_wait_s = float(params.get("max_wait_s") or kwargs.get("max_wait_s") or 60.0)

        workflow: Dict[str, Any]
        if explicit_workflow:
            workflow = explicit_workflow
        elif template:
            workflow = self._template_workflow(template, prompt, params)
        else:
            workflow = self._template_workflow(model, prompt, params)

        client_id = str(uuid.uuid4())
        t0 = self._now()

        # 1) Submit
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                sub = await client.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": workflow, "client_id": client_id},
                )
        except Exception as exc:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                is_placeholder=True,
                status="unreachable",
                error=f"comfyui POST /prompt 失败: {type(exc).__name__}: {exc}",
                error_code=type(exc).__name__,
                latency_ms=self._latency_ms(t0),
            )

        if sub.status_code in (400, 401):
            err_text = getattr(sub, "text", "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"comfyui HTTP {sub.status_code}: {err_text}",
                error_code=str(sub.status_code),
                latency_ms=self._latency_ms(t0),
            )
        if sub.status_code >= 500:
            err_text = getattr(sub, "text", "")[:500]
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"comfyui server 错误 {sub.status_code}: {err_text}",
                error_code=str(sub.status_code),
                latency_ms=self._latency_ms(t0),
            )

        sub_payload: Dict[str, Any] = {}
        try:
            sub_payload = sub.json() if hasattr(sub, "json") else {}
        except Exception:
            sub_payload = {}
        prompt_id = str(
            sub_payload.get("prompt_id")
            or sub.headers.get("x-prompt-id")
            or "",
        )
        if not prompt_id:
            # ComfyUI returns {"error": ..., "node_errors": ...} on invalid workflow.
            err_msg = sub_payload.get("error") or "comfyui 未返回 prompt_id"
            err_nodes = sub_payload.get("node_errors") or {}
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                error=f"{err_msg}; node_errors={json.dumps(err_nodes)[:200]}",
                error_code="comfyui_no_prompt_id",
                raw=sub_payload,
                latency_ms=self._latency_ms(t0),
            )

        # 2) Wait for completion — try WebSocket first (real integration);
        #    fallback to /history polling if WebSocket connect fails.
        progress = ComfyUIProgress(prompt_id=prompt_id, client_id=client_id)
        ws_ok = await self._listen_ws(progress, max_wait_s=max_wait_s)
        if not ws_ok:
            await self._poll_history(progress, max_wait_s=max_wait_s)

        if not progress.completed:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                task_id=prompt_id,
                status="timeout",
                error=f"comfyui 轮询超时 ({max_wait_s}s)",
                latency_ms=self._latency_ms(t0),
                raw={"progress_messages": progress.progress_msgs[-5:]},
            )
        if not progress.success:
            return ProviderResponse(
                success=False,
                provider=self.provider_name,
                model=model,
                task_id=prompt_id,
                status="failed",
                error=progress.error or "comfyui 执行失败",
                latency_ms=self._latency_ms(t0),
                raw={"progress_messages": progress.progress_msgs[-5:]},
            )

        # 3) Fetch final outputs through /history
        outputs, raw_hist = await self._fetch_history(prompt_id)
        images = self._view_urls(outputs)
        # All-in-one t2i / t2v flow here:
        videos = [u for u in images.get("videos", [])]
        imgs = images.get("images", [])
        return ProviderResponse(
            success=True,
            provider=self.provider_name,
            model=model,
            content=prompt[:500],
            task_id=prompt_id,
            images=imgs,
            videos=videos,
            status="succeeded",
            latency_ms=self._latency_ms(t0),
            raw={
                "prompt_id": prompt_id,
                "client_id": client_id,
                "outputs": outputs,
                "history": raw_hist,
                "progress_messages": progress.progress_msgs[-10:],
            },
        )

    async def health_check(self) -> ProviderResponse:
        """Check if local ComfyUI server is up via ``/system_stats``."""
        return await self.system_stats()

    # ── Internal: WS subscription ──────────────────────────────────────
    async def _listen_ws(self, progress: ComfyUIProgress, max_wait_s: float) -> bool:
        """Listen on ``/ws?clientId=...`` until completion. Return True on success."""
        ws_url = self._ws_url(progress.client_id)
        try:
            # ``websockets`` is module-level imported so ``patch("providers.comfyui.websockets", ...)``
            # can swap it out in unit tests deterministically.
            async with websockets.connect(
                ws_url,
                max_size=64 * 1024 * 1024,
                open_timeout=5.0,
            ) as ws:
                deadline = time.time() + max_wait_s
                async for raw in ws:
                    if time.time() > deadline:
                        return progress.completed and progress.success
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    mtype = msg.get("type") or msg.get("msg_type") or ""
                    data = msg.get("data") or {}
                    progress.progress_msgs.append({"type": mtype, "data": data})
                    if mtype == "executing":
                        # ``executing: {node: null, prompt_id: ...}`` signals completion
                        if not isinstance(data, dict):
                            continue
                        if data.get("prompt_id") == progress.prompt_id and data.get("node") is None:
                            progress.completed = True
                            progress.success = not progress.error
                            return True
                    elif mtype == "execution_error":
                        # Graph-validation failure / runtime error
                        err_data = data.get("exception_message") or data
                        progress.error = (
                            err_data if isinstance(err_data, str)
                            else json.dumps(err_data)[:500]
                        )
                        progress.completed = True
                        progress.success = False
                        return True
                    elif mtype == "executed":
                        # Successful node finished; ComfyUI may emit multiple.
                        if data.get("prompt_id") == progress.prompt_id:
                            progress.completed = True
                            progress.success = not progress.error
                            # do not return — keep listening for the final null node
                    elif mtype == "status":
                        # queue updates; ignore for completion
                        continue
                    elif mtype == "progress":
                        # progress: {value, max}
                        continue
                return progress.completed and progress.success
        except Exception as exc:
            logger.debug("comfyui WS connect failed: %s", exc)
            return False

    def _ws_url(self, client_id: str) -> str:
        if self.base_url.startswith("https://"):
            base = self.base_url.replace("https://", "wss://", 1)
        else:
            base = self.base_url.replace("http://", "ws://", 1)
        return f"{base}/ws?clientId={client_id}"

    # ── Internal: HTTP /history polling fallback ───────────────────────
    async def _poll_history(self, progress: ComfyUIProgress, max_wait_s: float) -> None:
        deadline = time.time() + max_wait_s
        interval = 0.5
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                while time.time() < deadline:
                    try:
                        resp = await client.get(
                            f"{self.base_url}/history/{progress.prompt_id}",
                        )
                    except Exception:
                        await asyncio.sleep(interval)
                        continue
                    if resp.status_code == 200:
                        payload = resp.json() if hasattr(resp, "json") else {}
                        if progress.prompt_id in payload or "outputs" in payload:
                            progress.completed = True
                            progress.success = True
                            return
                    await asyncio.sleep(interval)
        except Exception as exc:
            logger.debug("comfyui history poll failed: %s", exc)
            progress.error = str(exc)

    async def _fetch_history(self, prompt_id: str) -> tuple:
        """Fetch ``/history/{prompt_id}`` and flatten node outputs."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/history/{prompt_id}")
            if resp.status_code != 200:
                return {}, {}
            payload = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            return {}, {}
        outputs: Dict[str, Any] = {}
        if isinstance(payload, dict):
            inner = payload.get(prompt_id) if isinstance(payload.get(prompt_id), dict) else payload
            outputs = inner.get("outputs") or {}
        return outputs, payload

    # ── Internal: build /view URLs for each output asset ───────────────
    def _view_urls(self, outputs: Mapping[str, Any]) -> Dict[str, List[str]]:
        """Convert saved images / gifs / videos list into absolute /view URLs."""
        imgs: List[str] = []
        videos: List[str] = []
        if not isinstance(outputs, Mapping):
            return {"images": imgs, "videos": videos}
        for _node_id, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for key, items in node_out.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    fname = item.get("filename") or ""
                    if not fname:
                        continue
                    kind = (
                        "videos" if key in ("videos", "gifs", "mp4")
                        else "images"
                    )
                    params = (
                        f"filename={fname}"
                        f"&type={item.get('type', 'output')}"
                        f"&subfolder={item.get('subfolder', '')}"
                    )
                    if kind == "videos":
                        videos.append(f"{self.base_url}/view?{params}")
                    else:
                        imgs.append(f"{self.base_url}/view?{params}")
        return {"images": imgs, "videos": videos}

    # ── Default workflow templates ─────────────────────────────────────
    @staticmethod
    def _template_workflow(
        template: str,
        prompt: str,
        params: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Construct a minimal ComfyUI workflow JSON for known templates.

        The result is a valid ``prompt`` graph using ``CKPTLoader`` /
        ``CLIPTextEncode`` / ``EmptyLatentImage`` / ``KSampler`` /
        ``VAEDecode`` / ``SaveImage``. Users with custom graphs should pass
        ``workflow`` directly instead of ``template``.
        """
        template_l = template.lower()
        ckpt = params.get("ckpt_name") or (
            "flux1-schnell.gguf" if "flux" in template_l
            else "sd_xl_base_1.0.safetensors"
        )
        return {
            "3": {
                "inputs": {
                    "seed": int(params.get("seed", 42)),
                    "steps": int(params.get("steps", 25)),
                    "cfg": float(params.get("cfg", 7.0)),
                    "sampler_name": params.get("sampler", "euler"),
                    "scheduler": params.get("scheduler", "normal"),
                    "denoise": float(params.get("denoise", 1.0)),
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
            },
            "4": {
                "inputs": {"ckpt_name": ckpt},
                "class_type": "CheckpointLoaderSimple",
            },
            "5": {
                "inputs": {
                    "width": int(params.get("width", 1024)),
                    "height": int(params.get("height", 1024)),
                    "batch_size": int(params.get("n", 1)),
                },
                "class_type": "EmptyLatentImage",
            },
            "6": {
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "7": {
                "inputs": {
                    "text": params.get("negative_prompt", "low quality, blurry"),
                    "clip": ["4", 1],
                },
                "class_type": "CLIPTextEncode",
            },
            "8": {
                "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode",
            },
            "9": {
                "inputs": {"filename_prefix": "p20b", "images": ["8", 0]},
                "class_type": "SaveImage",
            },
        }


# ─── Public marker for test introspection ───────────────────────────────────
# Tests detect the real WebSocket usage by name-mangling this attribute:
ComfyUIProvider._PROVIDER_USES_REAL_WS = True  # type: ignore[attr-defined]


__all__ = ["ComfyUIProvider"]
