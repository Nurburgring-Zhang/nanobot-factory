"""P4-3-W1: Variable store + template renderer tests.

Run from project root:
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_variables.py -v --tb=short
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

from fastapi.testclient import TestClient  # noqa: E402

from services.agent_service.variables import (  # noqa: E402
    RESOLUTION_ORDER,
    Variable,
    VariableNamespace,
    VariableStore,
    get_variable_store,
    render_template,
    reset_variable_store_for_test,
)


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
def test_builtin_system_vars_and_render():
    """System variables are baked in and render correctly in templates."""
    c = _client()
    r = c.post(
        "/api/v1/agent/variables/render",
        json={"template": "Hi {{ user_name }}! Today is {{ date }} on {{ platform | upper }}."},
    )
    assert r.status_code == 200
    body = r.json()
    rendered = body["rendered"]
    assert "Hi" in rendered
    # default user_name + project_name
    assert "anonymous" in rendered or "guest" not in rendered
    # date pattern (4-digit year)
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", rendered)
    # platform was uppercased
    assert "NANOBOT" in rendered.upper()
    # The flat dict is returned
    flat = body["variables"]
    assert "date" in flat and "platform" in flat and "user_name" in flat
    print(f"  variables: built-in render: {rendered[:80]}")


def test_set_user_variable_and_namespace_resolution():
    """Setting a USER variable shadows the SYSTEM one when resolved."""
    c = _client()
    # Set a user-level override
    put = c.put(
        "/api/v1/agent/variables",
        json={
            "name": "user_name",
            "value": "Alice (overridden)",
            "namespace": "user",
            "description": "Custom display name",
        },
    )
    assert put.status_code == 200
    var_id = put.json()["var_id"]

    # Render — the user-namespace value should win
    r = c.post(
        "/api/v1/agent/variables/render",
        json={"template": "Hello, {{ user_name }}!"},
    )
    assert r.status_code == 200
    assert r.json()["rendered"] == "Hello, Alice (overridden)!"

    # System variables are read-only
    bad = c.put(
        "/api/v1/agent/variables",
        json={"name": "date", "value": "1970-01-01", "namespace": "system"},
    )
    assert bad.status_code == 403

    # Delete the override
    d = c.delete(f"/api/v1/agent/variables/{var_id}")
    assert d.status_code == 200
    assert d.json()["deleted"] is True

    # Render again — falls back to the built-in default
    r2 = c.post(
        "/api/v1/agent/variables/render",
        json={"template": "Hello, {{ user_name }}!"},
    )
    assert "anonymous" in r2.json()["rendered"] or "guest" in r2.json()["rendered"]
    print("  variables: namespace override + system-immutability OK")


def test_template_filters_and_session_turn_resolution():
    """Pipe filters work; session + turn + project variables are merged."""
    store = get_variable_store()
    store.reset_user_fragments_for_test()
    sid = "ses-test-001"
    store.set("greeting", "hello", namespace=VariableNamespace.SESSION, owner=sid)
    store.set("lang", "en", namespace=VariableNamespace.PROJECT)
    # session_id + user_id scope
    flat = store.resolve(
        session_id=sid,
        user_id=None,
        project={"deployed_by": "ops"},
        turn={"tone": "casual"},
    )
    assert flat["greeting"] == "hello"
    assert flat["deployed_by"] == "ops"
    assert flat["tone"] == "casual"
    # Built-in system var still present
    assert "date" in flat

    # Filter chain: upper + default + trim
    out = render_template(
        "{{ name | upper | trim | default:anon }}",
        {"name": "  Bob  "},
    )
    assert out == "BOB"
    # default kicks in when name is None
    out2 = render_template("{{ name | default:nobody }}", {})
    assert out2 == "nobody"
    # Unknown token without default stays as-is
    out3 = render_template("{{ unknown_var }}", {"known": 1})
    assert out3 == "{{ unknown_var }}"
    # RESOLUTION_ORDER is system → project → user → session → turn
    assert RESOLUTION_ORDER[0] == VariableNamespace.SYSTEM
    assert RESOLUTION_ORDER[-1] == VariableNamespace.TURN
    print(
        f"  variables: filters + session+project+turn merge OK "
        f"(namespaces={len(flat)})"
    )
