"""P4-3-W1: Tool registry tests.

Run from project root:
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_tools.py -v --tb=short
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
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

from fastapi.testclient import TestClient  # noqa: E402

from services.agent_service.tools.registry import (  # noqa: E402
    Tool,
    ToolRegistry,
    get_tool_registry,
    reset_tool_registry_for_test,
    tool,
)

EXPECTED_BUILTINS = {
    "search", "code_exec", "file_read", "file_write", "web_search",
    "sql_query", "http_request", "memory_search", "image_gen", "video_gen",
    "hash", "now", "echo",
}


def _client() -> TestClient:
    for mod_name in (
        "services.agent_service.memory.multi_turn",
        "services.agent_service.instructions",
        "services.agent_service.variables",
        "services.agent_service.tools.registry",
        "services.agent_service.loader",
        "services.agent_service.memory",
        "services.agent_service.store",
        "services.agent_service.scheduler",
        "services.agent_service.executor",
    ):
        m = importlib.import_module(mod_name)
        for fn_name in (
            "reset_session_manager_for_test",
            "reset_instructions_for_test",
            "reset_variable_store_for_test",
            "reset_tool_registry_for_test",
            "reset_loader_for_test",
            "reset_memory_for_test",
            "reset_store_singleton",
            "reset_scheduler_for_test",
            "reset_executor_for_test",
        ):
            fn = getattr(m, fn_name, None)
            if fn is not None:
                fn()
    try:
        eng = importlib.import_module("imdf.engines.agent_router")
        if hasattr(eng, "reset_agent_router_for_test"):
            eng.reset_agent_router_for_test()
    except Exception:  # noqa: BLE001
        pass
    return TestClient(importlib.import_module("services.agent_service.main").app)


# ── Tests ──────────────────────────────────────────────────────────────────
def test_list_builtin_tools_at_least_10():
    """GET /api/v1/agent/tools returns >= 10 built-in tools."""
    c = _client()
    r = c.get("/api/v1/agent/tools")
    assert r.status_code == 200
    body = r.json()
    names = {t["name"] for t in body["tools"]}
    assert len(names) >= 10, f"only {len(names)} tools, expected >=10"
    # The 10 required names from the spec are all present
    for required in {"search", "code_exec", "file_read", "file_write",
                     "web_search", "sql_query", "http_request",
                     "memory_search", "image_gen", "video_gen"}:
        assert required in names, f"missing required tool: {required}"
    # And the actual built-in catalogue matches our known set
    missing = EXPECTED_BUILTINS - names
    extra = names - EXPECTED_BUILTINS
    assert not missing, f"missing builtins: {missing}"
    assert not extra, f"unexpected builtins: {extra}"
    print(f"  tools: {len(names)} built-in tools registered")


def test_invoke_hash_and_echo():
    """Hash + echo are safe non-confirmation tools; both should work."""
    c = _client()
    h = c.post(
        "/api/v1/agent/tools/hash/invoke",
        json={"args": {"text": "hello world", "algorithm": "sha256"}},
    )
    assert h.status_code == 200, h.text
    body = h.json()
    assert body["error"] is None
    expected = (
        "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    )
    assert body["result"]["hash"] == expected
    assert body["result"]["algorithm"] == "sha256"
    assert body["tool"] == "hash"
    assert body["actor"] == "anonymous"

    e = c.post(
        "/api/v1/agent/tools/echo/invoke",
        json={"args": {"message": "hi"}, "actor": "tester"},
    )
    assert e.status_code == 200
    assert e.json()["result"] == {"echo": "hi"}
    assert e.json()["actor"] == "tester"
    print(f"  tools: hash + echo invoked OK")


def test_invoke_audit_chain_records_every_call():
    """Every invocation should appear in the audit chain."""
    c = _client()
    # Reset the registry's audit for a clean baseline
    get_tool_registry().clear_audit()
    for i in range(3):
        c.post(
            "/api/v1/agent/tools/echo/invoke",
            json={"args": {"message": f"audit-{i}"}, "actor": "audit_test"},
        )
    audit = c.get("/api/v1/agent/tools/audit?limit=50").json()
    assert audit["count"] == 50
    chain = audit["chain"]
    assert len(chain) >= 3
    echo_entries = [e for e in chain if e["tool"] == "echo"]
    assert len(echo_entries) >= 3
    for entry in echo_entries[-3:]:
        assert entry["error"] is None
        assert entry["actor"] == "audit_test"
        assert entry["duration_ms"] >= 0
        assert entry["invocation_id"].startswith("inv-")
    print(f"  tools: audit chain recorded {len(echo_entries)} echo invocations")


def test_tool_decorator_and_custom_registration():
    """A function decorated with @tool can be registered and invoked."""
    c = _client()
    reg = get_tool_registry()

    @tool(name="uppercase", description="Uppercase a string", tags=["test"])
    def _upper(text: str = "hello") -> dict:
        return {"text": text.upper()}

    t = reg.register_function(_upper, builtin=False)
    assert t.name == "uppercase"
    assert "test" in t.tags
    assert t.builtin is False

    # Invoke via REST
    r = c.post(
        "/api/v1/agent/tools/uppercase/invoke",
        json={"args": {"text": "abc"}, "actor": "unit_test"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"] == {"text": "ABC"}

    # Detail endpoint exposes the schema
    d = c.get("/api/v1/agent/tools/uppercase")
    assert d.status_code == 200
    schema = d.json()["schema"]
    assert "properties" in schema
    assert "text" in schema["properties"]
    # Cannot unregister a built-in (try with a known built-in name)
    assert reg.unregister("search") is False
    # Custom one can be removed
    assert reg.unregister("uppercase") is True
    missing = c.get("/api/v1/agent/tools/uppercase")
    assert missing.status_code == 404
    print("  tools: @tool decorator + custom registration lifecycle OK")


def test_invoke_unknown_tool_404():
    """Invoking a non-existent tool should return 404."""
    c = _client()
    r = c.post(
        "/api/v1/agent/tools/does_not_exist/invoke",
        json={"args": {}, "actor": "tester"},
    )
    assert r.status_code == 404
    # The common error handler wraps everything in {success, error:{code, message}}.
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "http_error"
    assert "tool_not_found" in str(body["error"]["message"])
    print("  tools: unknown tool returns 404")
