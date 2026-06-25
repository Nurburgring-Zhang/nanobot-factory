"""P4-3-W2: MCP server smoke tests.

3 tests:

  1. test_mcp_server_5_tools_listed
  2. test_mcp_server_resources_and_prompts
  3. test_mcp_server_jsonrpc_dispatch

Run with::

    cd D:\\Hermes\\生产平台\\nanobot-factory
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_mcp.py -v
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")


def _fresh_server(tmp_path=None):
    import tempfile

    from services.agent_service.mcp import reset_mcp_server_for_test
    from services.agent_service.hindsight import HindsightConfig, reset_hindsight_for_test
    from services.agent_service.memory_palace import reset_memory_palace_for_test

    if tmp_path is None:
        tmp_path = tempfile.mkdtemp(prefix="mcp_")
    # Reset dependencies so tools that touch them start clean
    reset_memory_palace_for_test(db_path=str(tmp_path / "palace.db"))
    reset_hindsight_for_test(config=HindsightConfig(db_path=str(tmp_path / "hindsight.db")))
    return reset_mcp_server_for_test()


# ── 1. 5 tools listed ───────────────────────────────────────────────────────
def test_mcp_server_5_tools_listed(tmp_path):
    server = _fresh_server(tmp_path)
    assert server.tool_count() == 5
    names = {t.name for t in server.list_tools()}
    expected = {
        "mempalace_search",
        "mempalace_retain",
        "mempalace_wake_up",
        "hindsight_search",
        "hindsight_retain",
    }
    assert names == expected
    # Each tool has a JSON schema
    for t in server.list_tools():
        assert "type" in t.schema and t.schema["type"] == "object"


# ── 2. Resources + prompts ──────────────────────────────────────────────────
def test_mcp_server_resources_and_prompts(tmp_path):
    server = _fresh_server(tmp_path)
    # 3 resources: soul://current, wings://list, rooms://list
    assert server.resource_count() == 3
    uris = {r.uri for r in server.list_resources()}
    assert uris == {"soul://current", "wings://list", "rooms://list"}
    # 2 prompts: summarize_room, generate_storyboard
    assert server.prompt_count() == 2
    pnames = {p.name for p in server.list_prompts()}
    assert pnames == {"summarize_room", "generate_storyboard"}


# ── 3. JSON-RPC dispatch end-to-end ─────────────────────────────────────────
def test_mcp_server_jsonrpc_dispatch(tmp_path):
    server = _fresh_server(tmp_path)
    # initialize
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["id"] == 1
    assert "result" in resp
    assert resp["result"]["serverInfo"]["name"] == "nanobot-factory-mcp"

    # tools/list
    resp = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp["result"]["tools"], "tools/list should return at least 1 tool"

    # tools/call — mempalace_retain (L2 wing)
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "mempalace_retain",
                "arguments": {
                    "level": "L2_wing",
                    "payload": {
                        "name": "smoke-wing",
                        "description": "created from MCP",
                        "trigger_keywords": ["smoke", "mcp"],
                    },
                },
            },
        }
    )
    assert "result" in resp, f"unexpected error: {resp}"
    assert resp["result"]["isError"] is False
    body = resp["result"]["content"][0]["data"]
    assert body["ok"] is True
    assert body["level"] == "L2_wing"

    # tools/call — mempalace_wake_up
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "mempalace_wake_up", "arguments": {}},
        }
    )
    assert "result" in resp
    body = resp["result"]["content"][0]["data"]
    assert "palace_stats" in body

    # tools/call — hindsight_retain
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "hindsight_retain",
                "arguments": {
                    "content": "verbatim: user said hello",
                    "role": "user",
                    "source": "session:mcp",
                    "layer": "L3_full",
                },
            },
        }
    )
    assert "result" in resp
    body = resp["result"]["content"][0]["data"]
    assert body["ok"] is True
    assert body["layer"] == "L3_full"

    # method_not_found
    resp = server.handle({"jsonrpc": "2.0", "id": 6, "method": "tools/unknown"})
    assert "error" in resp
    assert resp["error"]["code"] == -32601

    # resources/read soul://current
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/read",
            "params": {"uri": "soul://current"},
        }
    )
    assert "result" in resp

    # prompts/get — without matching wing should raise
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "prompts/get",
            "params": {"name": "generate_storyboard", "arguments": {"wing_id": "no-such-wing"}},
        }
    )
    # Server wraps KeyError as internal_error
    assert "error" in resp
    assert resp["error"]["code"] == -32603


__all__ = [
    "test_mcp_server_5_tools_listed",
    "test_mcp_server_resources_and_prompts",
    "test_mcp_server_jsonrpc_dispatch",
]
