"""P6-Fix-P0-5: agent_service tests for the BaseAgent bridge.

The new ``imdf.agents`` package exposes 23 concrete
:class:`BaseAgent` subclasses.  This test file confirms the bridge
in :mod:`services.agent_service.agents` exposes them via
:func:`get_agent_class` and :data:`AGENT_CLASS_REGISTRY` without
breaking the legacy :data:`AGENT_REGISTRY` metadata contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# 1. Legacy metadata contract is preserved
# ---------------------------------------------------------------------------
def test_agent_registry_has_23_entries():
    from services.agent_service.agents import AGENT_REGISTRY

    assert len(AGENT_REGISTRY) == 23


def test_get_agent_config_works_for_each_type():
    from services.agent_service.agents import (
        AGENT_REGISTRY,
        AgentType,
        get_agent_config,
    )

    for at in AgentType:
        cfg = get_agent_config(at)
        assert cfg["id"] == at.value
        # Required keys per the legacy contract.
        for key in (
            "name", "description", "default_mode", "default_priority",
            "max_retries", "timeout_seconds", "downstream_service",
            "capabilities",
        ):
            assert key in cfg, f"{at} missing {key}"


def test_get_agent_config_unknown_raises_keyerror():
    from services.agent_service.agents import get_agent_config

    with pytest.raises(KeyError):
        get_agent_config("nonsense_type_does_not_exist_xyz")


def test_list_agent_summaries_returns_23_dicts():
    from services.agent_service.agents import list_agent_summaries

    summaries = list_agent_summaries()
    assert len(summaries) == 23
    for s in summaries:
        assert "id" in s
        assert "name" in s
        assert "description" in s
        assert "capabilities" in s


# ---------------------------------------------------------------------------
# 2. BaseAgent bridge — get_agent_class
# ---------------------------------------------------------------------------
def test_get_agent_class_returns_baseagent_subclass():
    from imdf.agents.base import BaseAgent
    from services.agent_service.agents import AgentType, get_agent_class

    cls = get_agent_class(AgentType.CLEANING)
    assert isinstance(cls, type)
    assert issubclass(cls, BaseAgent)


def test_get_agent_class_round_trip_for_all_23_types():
    from services.agent_service.agents import AgentType, get_agent_class

    for at in AgentType:
        cls = get_agent_class(at)
        instance = cls()
        assert instance.get_agent_type_slug() == at.value


def test_get_agent_class_accepts_string_slug():
    from services.agent_service.agents import AgentType, get_agent_class

    cls = get_agent_class("skill_orchestrator")
    assert cls().get_agent_type_slug() == "skill_orchestrator"
    assert cls is get_agent_class(AgentType.SKILL_ORCHESTRATOR)


def test_get_agent_class_unknown_raises_keyerror():
    from services.agent_service.agents import get_agent_class

    with pytest.raises(KeyError):
        get_agent_class("not_a_real_agent_type_xyz")


# ---------------------------------------------------------------------------
# 3. AGENT_CLASS_REGISTRY size + integrity
# ---------------------------------------------------------------------------
def test_agent_class_registry_has_23_entries():
    from imdf.agents import register_builtin_agents
    from imdf.agents.registry import PluginRegistry
    from services.agent_service.agents import (
        AGENT_CLASS_REGISTRY,
        register_builtin_agent_classes,
    )

    reg = PluginRegistry()
    reg.reset()
    register_builtin_agents(registry=reg)
    register_builtin_agent_classes()
    assert len(AGENT_CLASS_REGISTRY) == 23


def test_register_builtin_agent_classes_is_idempotent():
    from services.agent_service.agents import (
        AGENT_CLASS_REGISTRY,
        register_builtin_agent_classes,
    )

    n1 = len(register_builtin_agent_classes())
    n2 = len(register_builtin_agent_classes())
    assert n1 == n2 == 23
    assert len(AGENT_CLASS_REGISTRY) == 23


# ---------------------------------------------------------------------------
# 4. Real execute() round trip — every concrete class returns ok=True
# ---------------------------------------------------------------------------
def test_all_23_classes_execute_returns_ok_result():
    from imdf.agents.base import AgentContext
    from services.agent_service.agents import AgentType, get_agent_class

    for at in AgentType:
        cls = get_agent_class(at)
        instance = cls()
        ctx = AgentContext(
            task_id=f"task-{at.value}",
            agent_type=at.value,
            mode=instance.default_mode,
        )
        result = instance.execute(ctx)
        assert result.ok is True, f"{at.value} failed: {result.error}"
        assert result.agent_type == at.value
        assert result.task_id == f"task-{at.value}"
        # Plan must be a list with at least one step.
        assert isinstance(result.plan, list)
        assert result.plan, f"{at.value} returned empty plan"


# ---------------------------------------------------------------------------
# 5. Validation hook returns an error on empty task_id
# ---------------------------------------------------------------------------
def test_empty_task_id_returns_error():
    from imdf.agents.base import AgentContext
    from services.agent_service.agents import AgentType, get_agent_class

    for at in AgentType:
        cls = get_agent_class(at)
        instance = cls()
        ctx = AgentContext(task_id="", agent_type=at.value)
        result = instance.execute(ctx)
        assert result.ok is False
        assert "task_id" in (result.error or "")
        assert result.error_source == "validate"
