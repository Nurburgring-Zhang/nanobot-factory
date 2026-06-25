"""P4-3-W1: Agent instructions tests.

Run from project root:
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_instructions.py -v --tb=short
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

from services.agent_service.instructions import (  # noqa: E402
    AgentInstructions,
    InstructionFragment,
    InstructionScope,
    SCOPE_ORDER,
    get_instructions,
    reset_instructions_for_test,
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
def test_create_user_instruction_roundtrip():
    """POST + GET + PUT + DELETE lifecycle for a USER instruction."""
    c = _client()
    create = c.post(
        "/api/v1/agent/instructions",
        json={
            "name": "my_rule",
            "content": "Always respond in formal English.",
            "scope": "user",
            "description": "Operator-uploaded tone rule",
            "priority": 50,
        },
    )
    assert create.status_code == 200, create.text
    frag = create.json()
    fid = frag["fragment_id"]
    assert frag["scope"] == "user"
    assert frag["enabled"] is True

    g = c.get(f"/api/v1/agent/instructions/{fid}")
    assert g.status_code == 200
    assert g.json()["content"] == "Always respond in formal English."

    # Update
    u = c.put(
        f"/api/v1/agent/instructions/{fid}",
        json={"content": "Always respond in informal English.", "priority": 25},
    )
    assert u.status_code == 200
    assert u.json()["content"] == "Always respond in informal English."
    assert u.json()["priority"] == 25

    d = c.delete(f"/api/v1/agent/instructions/{fid}")
    assert d.status_code == 200
    assert d.json()["deleted"] is True
    g2 = c.get(f"/api/v1/agent/instructions/{fid}")
    assert g2.status_code == 404
    print(f"  instructions: created/updated/deleted fragment {fid}")


def test_render_priority_order_and_template_substitution():
    """The render endpoint concatenates fragments in SCOPE_ORDER with {{var}} substitution."""
    c = _client()
    inst = get_instructions()
    inst.reset_user_fragments_for_test()

    # Add one USER fragment with a template variable
    inst.add(
        InstructionFragment(
            name="user_template",
            content="User said: {{ user_name | default:guest }} on {{ date }}",
            scope=InstructionScope.USER,
            priority=10,
        )
    )
    inst.add(
        InstructionFragment(
            name="user_extra",
            content="Extra note about {{ project_name | upper }}.",
            scope=InstructionScope.USER,
            priority=20,
        )
    )

    r = c.post(
        "/api/v1/agent/instructions/render",
        json={"session_id": None, "variables": {"user_name": "Alice"}},
    )
    assert r.status_code == 200
    prompt = r.json()["prompt"]
    # System fragments are present
    assert "core_safety" in prompt
    assert "platform_identity" in prompt
    assert "response_format" in prompt
    # User fragment rendered with the variable
    assert "User said: Alice on" in prompt
    assert "nanobot-factory" in prompt.lower() or "NANOBOT-FACTORY" in prompt
    # Priority order: user_template (10) should appear before user_extra (20)
    assert prompt.index("user_template") < prompt.index("user_extra")
    print(f"  render: {len(prompt)} chars, system+user+project layers merged")


def test_system_fragments_immutable_and_list_summary():
    """SYSTEM fragments are baked in; you can't create one via the API."""
    c = _client()
    # Try to create a system fragment — should be rejected
    bad = c.post(
        "/api/v1/agent/instructions",
        json={"name": "fake_system", "content": "x", "scope": "system"},
    )
    assert bad.status_code == 403

    # Try to delete a system fragment — should be rejected
    inst = get_instructions()
    system_frag = next(
        (f for f in inst.list(scope=InstructionScope.SYSTEM) if f.name == "core_safety"),
        None,
    )
    assert system_frag is not None, "core_safety should be a built-in system fragment"
    deleted = inst.delete(system_frag.fragment_id)
    assert deleted is False
    assert inst.get(system_frag.fragment_id) is not None

    # List summary counts include system + user fragments
    listing = c.get("/api/v1/agent/instructions")
    assert listing.status_code == 200
    summary = listing.json()["summary"]
    assert summary["counts"]["system"] >= 3  # 3 built-ins
    # SCOPE_ORDER is system → project → user → per_session
    assert SCOPE_ORDER[0] == InstructionScope.SYSTEM
    assert SCOPE_ORDER[-1] == InstructionScope.PER_SESSION
    print(
        f"  system protection: 3 built-in fragments preserved, "
        f"counts={summary['counts']}"
    )
