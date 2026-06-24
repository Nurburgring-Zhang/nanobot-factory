"""P4-3-W2: MCP HTTP transport — POST /mcp + GET /mcp/sse.

The MCP server is a singleton (see :mod:`mcp.server`).  This module
mounts it as a JSON-RPC-over-HTTP endpoint and a Server-Sent-Events
endpoint on the existing agent_service port (8008).

* ``POST /mcp``        — single request/response JSON-RPC
* ``POST /mcp/batch``  — list of JSON-RPC requests, returns list of responses
* ``GET  /mcp/sse``    — SSE; emits "endpoint" event then idles (real
                         clients would open a POST stream; the simpler
                         version is enough for the smoke tests).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from .mcp import get_mcp_server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent/mcp", tags=["mcp"])


@router.get("/status")
async def mcp_status() -> Dict[str, Any]:
    return get_mcp_server().status()


@router.get("/tools")
async def mcp_tools() -> Dict[str, Any]:
    server = get_mcp_server()
    return {
        "count": server.tool_count(),
        "tools": [t.to_dict() for t in server.list_tools()],
    }


@router.get("/resources")
async def mcp_resources() -> Dict[str, Any]:
    server = get_mcp_server()
    return {
        "count": server.resource_count(),
        "resources": [r.to_dict() for r in server.list_resources()],
    }


@router.get("/prompts")
async def mcp_prompts() -> Dict[str, Any]:
    server = get_mcp_server()
    return {
        "count": server.prompt_count(),
        "prompts": [p.to_dict() for p in server.list_prompts()],
    }


@router.post("")
async def mcp_rpc(request: Request) -> JSONResponse:
    """Single JSON-RPC request/response."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse_error: {exc}"},
            },
        )
    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "invalid_request: body must be a JSON object"},
            },
        )
    resp = get_mcp_server().handle(body)
    status_code = 200
    if "error" in resp:
        code = resp["error"].get("code", -1)
        if code == -32601:  # method not found
            status_code = 404
        elif code in (-32700, -32600):  # parse / invalid
            status_code = 400
        else:
            status_code = 500
    return JSONResponse(status_code=status_code, content=resp)


@router.post("/batch")
async def mcp_rpc_batch(request: Request) -> JSONResponse:
    """Batch JSON-RPC — list of requests, returns list of responses."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"parse_error: {exc}")
    if not isinstance(body, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="body must be a list of JSON-RPC requests")
    server = get_mcp_server()
    out: List[Dict[str, Any]] = [server.handle(req) for req in body]
    return JSONResponse(content=out)


@router.get("/sse")
async def mcp_sse() -> StreamingResponse:
    """Server-Sent Events endpoint.

    Emits an ``endpoint`` event so MCP clients know where to POST
    requests, then idles.  Real implementations would push notifications
    here (we have none yet, so we just keep the stream open until the
    client disconnects).
    """
    async def event_source():
        yield f"event: endpoint\ndata: /api/v1/agent/mcp\n\n"
        # Heartbeat every 15s until disconnect
        try:
            while True:
                await asyncio.sleep(15)
                yield f"event: ping\ndata: ok\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(event_source(), media_type="text/event-stream")


__all__ = ["router"]
