"""
Async model-gateway chat task (P2-1-W2)
========================================

Task:
- ``chat`` — invoke ``ModelGateway.chat`` (which is async) from a sync Celery
             worker by bridging through ``asyncio.run``.

The gateway supports multiple providers (DeepSeek / OpenAI / Anthropic /
Google / Zhipu) and auto-routes. We just expose its async ``chat`` coroutine
to the queue, returning a JSON-friendly dict.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import shared_task

_THIS_FILE = Path(__file__).resolve()
_IMDF_DIR = _THIS_FILE.parent.parent          # backend/imdf
_BACKEND_DIR = _IMDF_DIR.parent                # backend
for _p in (str(_BACKEND_DIR), str(_IMDF_DIR)):
    if _p and _p not in sys.path:
        sys.path.insert(0, _p)

logger = logging.getLogger(__name__)


def _to_chat_response_dict(resp) -> Dict[str, Any]:
    if resp is None:
        return {"success": False, "error": "model_gateway_returned_none"}
    if hasattr(resp, "to_dict"):
        return resp.to_dict()
    if hasattr(resp, "__dict__"):
        return dict(resp.__dict__)
    return {"success": True, "value": str(resp)}


async def _invoke_chat(
    messages: List[Dict[str, Any]],
    model: str,
    temperature: float,
    max_tokens: int,
) -> Any:
    from engines.model_gateway import ModelGateway
    gw = ModelGateway()
    return await gw.chat(
        messages=list(messages or []),
        model=model or "auto",
        temperature=float(temperature or 0.7),
        max_tokens=int(max_tokens or 4096),
    )


@shared_task(name="imdf.tasks.model_gateway.chat", bind=True, acks_late=True)
def chat(
    self,
    messages: List[Dict[str, Any]],
    model: str = "auto",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """Run a chat completion through the multi-provider gateway."""
    try:
        if not messages:
            return {
                "ok": False, "error": "messages_required",
                "task_id": self.request.id,
            }
        # Bridge async gateway to sync worker.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an event loop (shouldn't happen in a
                # worker, but be defensive). Run in a fresh loop.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    resp = ex.submit(
                        asyncio.run,
                        _invoke_chat(messages, model, temperature, max_tokens),
                    ).result()
            else:
                resp = loop.run_until_complete(
                    _invoke_chat(messages, model, temperature, max_tokens)
                )
        except RuntimeError:
            # No running loop — safe to use asyncio.run directly.
            resp = asyncio.run(_invoke_chat(messages, model, temperature, max_tokens))

        d = _to_chat_response_dict(resp)
        return {"ok": True, "result": d, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        logger.exception("model_gateway.chat failed")
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "task_id": self.request.id,
        }


@shared_task(name="imdf.tasks.model_gateway.health_check", bind=True)
def health_check(self, model_id: Optional[str] = None) -> Dict[str, Any]:
    """Probe provider health through the gateway."""
    try:
        from engines.model_gateway import ModelGateway
        gw = ModelGateway()

        async def _probe():
            if model_id:
                return await gw.health_check(model_id)
            # No model specified — list enabled models as a coarse probe.
            models = await gw.list_models()
            out = []
            for m in models or []:
                if isinstance(m, dict):
                    if m.get("enabled", True):
                        out.append(m)
                else:
                    if getattr(m, "enabled", True):
                        out.append(getattr(m, "to_dict", lambda: dict(m.__dict__))())
            return {"enabled": out, "count": len(out)}

        result = asyncio.run(_probe())
        if hasattr(result, "__dict__"):
            result = dict(result.__dict__)
        return {"ok": True, "result": result, "task_id": self.request.id}
    except Exception as exc:  # pragma: no cover
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            "task_id": self.request.id,
        }
