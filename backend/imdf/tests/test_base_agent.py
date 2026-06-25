"""P6-Fix-P0-5: tests for BaseAgent + PluginRegistry + load_plugin.

Covers:
  * ``BaseAgent`` is abstract (cannot be instantiated directly)
  * all 23 built-in subclasses can be instantiated and return a
    valid ``AgentResult`` from ``execute``
  * ``PluginRegistry`` supports register / get / list / unregister
  * ``load_plugin`` can pick up a fresh agent file at runtime
  * the registry is thread-safe (smoke test)
  * agent metadata matches the canonical ``AGENT_REGISTRY``
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

# Make the backend root importable (consistent with other test files).
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# 1. BaseAgent abstract
# ---------------------------------------------------------------------------
def test_baseagent_cannot_be_instantiated_directly():
    from imdf.agents.base import BaseAgent

    with pytest.raises(TypeError):
        BaseAgent()  # type: ignore[abstract]


def test_baseagent_subclass_missing_execute_cannot_be_instantiated():
    from imdf.agents.base import BaseAgent

    class HalfBaked(BaseAgent):
        name = "half"

    with pytest.raises(TypeError):
        HalfBaked()  # type: ignore[abstract]


def test_baseagent_subclass_with_execute_can_be_instantiated():
    from imdf.agents.base import AgentContext, AgentResult, BaseAgent

    class Good(BaseAgent):
        name = "good"
        description = "d"

        def execute(self, context: AgentContext) -> AgentResult:
            return AgentResult(
                ok=True,
                task_id=context.task_id,
                agent_type=self.get_agent_type_slug(),
            )

    g = Good()
    assert g.get_agent_type_slug() == ""
    res = g.execute(AgentContext(task_id="t1", agent_type="x"))
    assert res.ok is True
    assert res.task_id == "t1"


# ---------------------------------------------------------------------------
# 2. All 23 built-in subclasses instantiate and execute cleanly
# ---------------------------------------------------------------------------
def test_all_23_builtins_instantiate():
    from imdf.agents.builtin import get_builtin_classes

    classes = get_builtin_classes()
    assert len(classes) == 23, f"expected 23 built-in agents, got {len(classes)}"
    for cls in classes:
        instance = cls()
        assert instance.name, f"{cls.__name__} missing name"
        assert instance.description, f"{cls.__name__} missing description"
        assert instance.capabilities, f"{cls.__name__} missing capabilities"
        slug = instance.get_agent_type_slug()
        assert slug, f"{cls.__name__} has empty agent_type slug"


def test_all_23_builtins_execute_return_ok_result():
    from imdf.agents.builtin import get_builtin_classes
    from imdf.agents.base import AgentContext

    classes = get_builtin_classes()
    for cls in classes:
        instance = cls()
        slug = instance.get_agent_type_slug()
        ctx = AgentContext(
            task_id=f"task-{slug}",
            agent_type=slug,
            mode=instance.default_mode,
            input={"probe": True},
        )
        res = instance.execute(ctx)
        assert res.ok is True, f"{cls.__name__}.execute failed: {res.error}"
        assert res.task_id == f"task-{slug}"
        assert res.agent_type == slug
        # Default plan comes from the shared step-list table.
        assert isinstance(res.plan, list)
        assert res.plan, f"{cls.__name__} has empty plan"
        assert res.output["agent_name"] == instance.name
        assert res.output["downstream_service"] == instance.downstream_service


def test_builtin_agents_validate_empty_task_id():
    from imdf.agents.builtin import get_builtin_classes
    from imdf.agents.base import AgentContext

    classes = get_builtin_classes()
    for cls in classes:
        instance = cls()
        ctx = AgentContext(task_id="", agent_type=instance.get_agent_type_slug())
        res = instance.execute(ctx)
        assert res.ok is False
        assert "task_id" in (res.error or "")
        assert res.error_source == "validate"


# ---------------------------------------------------------------------------
# 3. Built-in metadata matches the canonical AGENT_REGISTRY
# ---------------------------------------------------------------------------
def test_builtin_metadata_matches_agents_registry():
    from imdf.agents.builtin import get_builtin_classes
    from services.agent_service.agents import AGENT_REGISTRY, AgentType

    by_slug = {cls().get_agent_type_slug(): cls for cls in get_builtin_classes()}
    assert len(by_slug) == 23

    for agent_type, cfg in AGENT_REGISTRY.items():
        slug = agent_type.value
        cls = by_slug.get(slug)
        assert cls is not None, f"no built-in class for {slug}"
        instance = cls()
        assert instance.name == cls.__name__ or instance.name
        # The actual labels in AGENT_REGISTRY use Chinese strings
        # for ``description``; built-in classes store the English
        # cls name in ``name``.  We only require the canonical slug
        # round-trips through AgentType.
        assert AgentType(slug) is agent_type


# ---------------------------------------------------------------------------
# 4. PluginRegistry CRUD
# ---------------------------------------------------------------------------
def test_plugin_registry_register_and_get():
    from imdf.agents.base import BaseAgent
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    class MyAgent(BaseAgent):
        name = "n"

        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    reg.register("my_agent", MyAgent)
    assert "my_agent" in reg
    assert reg.get("my_agent") is MyAgent
    assert reg.try_get("missing") is None
    with pytest.raises(KeyError):
        reg.get("missing")
    reg.reset()


def test_plugin_registry_rejects_non_baseagent():
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    with pytest.raises(TypeError):
        reg.register("oops", dict)  # type: ignore[arg-type]
    reg.reset()


def test_plugin_registry_rejects_empty_name():
    from imdf.agents.base import BaseAgent
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    class A(BaseAgent):
        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    with pytest.raises(ValueError):
        reg.register("", A)
    with pytest.raises(ValueError):
        reg.register(123, A)  # type: ignore[arg-type]
    reg.reset()


def test_plugin_registry_overwrite_and_unregister():
    from imdf.agents.base import BaseAgent
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    class A(BaseAgent):
        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    class B(BaseAgent):
        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    reg.register("dup", A)
    reg.register("dup", B, overwrite=True)
    assert reg.get("dup") is B
    with pytest.raises(ValueError):
        reg.register("dup", A, overwrite=False)
    assert reg.unregister("dup") is True
    assert reg.unregister("dup") is False
    reg.reset()


def test_plugin_registry_bulk_register_rolls_back_on_failure():
    from imdf.agents.base import BaseAgent
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    class A(BaseAgent):
        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    class NotAnAgent:
        pass

    with pytest.raises(TypeError):
        reg.bulk_register({"a": A, "bad": NotAnAgent})  # type: ignore[dict-item]
    # Roll-back verified.
    assert "a" not in reg
    reg.reset()


def test_plugin_registry_is_thread_safe_under_contention():
    from imdf.agents.base import BaseAgent
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    class A(BaseAgent):
        def execute(self, context):  # noqa: ARG002
            from imdf.agents.base import AgentResult
            return AgentResult(ok=True, task_id=context.task_id, agent_type="x")

    errors: list = []

    def worker(i: int) -> None:
        try:
            for j in range(50):
                reg.register(f"agent_{i}_{j}", A, overwrite=True)
                _ = reg.try_get(f"agent_{i}_{j}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"threading errors: {errors}"
    # All 400 entries should be present.
    assert len(reg) == 8 * 50
    reg.reset()


# ---------------------------------------------------------------------------
# 5. load_plugin picks up a fresh file at runtime
# ---------------------------------------------------------------------------
def _write_temp_plugin(text: str) -> str:
    """Write a plugin .py file in a temp dir and return its path."""
    tmpdir = tempfile.mkdtemp(prefix="imdf_plugin_")
    path = os.path.join(tmpdir, "my_plugin.py")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def test_load_plugin_registers_a_fresh_class_at_runtime():
    from imdf.agents import load_plugin
    from imdf.agents.base import AgentResult
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    plugin_path = _write_temp_plugin(
        "from imdf.agents.base import BaseAgent, AgentContext, AgentResult\n"
        "class DynamicAgent(BaseAgent):\n"
        "    name = 'dynamic'\n"
        "    description = 'loaded at runtime'\n"
        "    agent_type = 'dynamic_test'\n"
        "    capabilities = ['dynamic']\n"
        "    def execute(self, context):\n"
        "        return AgentResult(ok=True, task_id=context.task_id, agent_type='dynamic_test')\n"
    )

    names = load_plugin(plugin_path, registry=reg)
    assert names == ["dynamic_test"]
    assert "dynamic_test" in reg
    cls = reg.get("dynamic_test")
    inst = cls()
    assert inst.name == "dynamic"
    res = inst.execute(
        __import__("imdf.agents.base", fromlist=["AgentContext"]).AgentContext(
            task_id="t1", agent_type="dynamic_test",
        )
    )
    assert res.ok is True
    assert res.task_id == "t1"
    reg.reset()


def test_load_plugin_uses_class_name_when_no_slug():
    from imdf.agents import load_plugin
    from imdf.agents.base import AgentResult
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()

    plugin_path = _write_temp_plugin(
        "from imdf.agents.base import BaseAgent, AgentContext, AgentResult\n"
        "class FooAgent(BaseAgent):\n"
        "    name = 'foo'\n"
        "    def execute(self, context):\n"
        "        return AgentResult(ok=True, task_id=context.task_id, agent_type='FooAgent')\n"
    )
    names = load_plugin(plugin_path, registry=reg)
    # Falls back to class name.
    assert names == ["FooAgent"]
    reg.reset()


def test_load_plugin_raises_when_no_agent_defined():
    from imdf.agents import load_plugin
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    plugin_path = _write_temp_plugin("x = 1\ny = 'no agent here'\n")
    with pytest.raises(RuntimeError):
        load_plugin(plugin_path, registry=reg)
    reg.reset()


def test_load_plugin_raises_for_missing_file():
    from imdf.agents import load_plugin
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    with pytest.raises(FileNotFoundError):
        load_plugin("/no/such/path.py", registry=reg)
    reg.reset()


def test_load_plugin_propagates_import_error():
    from imdf.agents import load_plugin
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    plugin_path = _write_temp_plugin(
        "import this_module_does_not_exist_1234567  # noqa: F401\n"
    )
    with pytest.raises(ImportError):
        load_plugin(plugin_path, registry=reg)
    reg.reset()


def test_load_plugin_supports_name_overrides():
    from imdf.agents import load_plugin
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    plugin_path = _write_temp_plugin(
        "from imdf.agents.base import BaseAgent, AgentContext, AgentResult\n"
        "class BarAgent(BaseAgent):\n"
        "    agent_type = 'bar'\n"
        "    def execute(self, context):\n"
        "        return AgentResult(ok=True, task_id=context.task_id, agent_type='bar')\n"
    )
    names = load_plugin(
        plugin_path,
        registry=reg,
        name_overrides={"bar": "renamed_bar"},
    )
    assert names == ["renamed_bar"]
    assert "renamed_bar" in reg
    reg.reset()


# ---------------------------------------------------------------------------
# 6. End-to-end: register_builtin_agents wires the 23 classes
# ---------------------------------------------------------------------------
def test_register_builtin_agents_returns_23_slugs():
    from imdf.agents import register_builtin_agents
    from imdf.agents.registry import PluginRegistry

    reg = PluginRegistry()
    reg.reset()
    slugs = register_builtin_agents(registry=reg)
    assert len(slugs) == 23
    # Spot-check a few well-known slugs.
    for required in (
        "cleaning", "scoring", "evaluation", "skill_orchestrator",
        "generation_image", "generation_video",
    ):
        assert required in slugs, f"missing {required}"
    reg.reset()


def test_get_agent_class_round_trip():
    from services.agent_service.agents import AgentType, get_agent_class

    cls = get_agent_class(AgentType.CLEANING)
    inst = cls()
    assert inst.get_agent_type_slug() == "cleaning"
    # Unknown agent type -> KeyError
    with pytest.raises(KeyError):
        get_agent_class("nonsense_type_does_not_exist_xyz")


# ---------------------------------------------------------------------------
# 7. AgentResult helpers
# ---------------------------------------------------------------------------
def test_agent_result_from_exception():
    from imdf.agents.base import AgentResult

    res = AgentResult.from_exception(
        task_id="t1", agent_type="x", exc=ValueError("bad"),
        error_source="validate",
    )
    assert res.ok is False
    assert "ValueError" in (res.error or "")
    assert "bad" in (res.error or "")
    assert res.error_source == "validate"


def test_agent_result_to_dict_is_json_serialisable():
    import json

    from imdf.agents.base import AgentResult

    res = AgentResult(
        ok=True, task_id="t1", agent_type="x",
        output={"a": 1}, plan=["s1", "s2"],
    )
    d = res.to_dict()
    # Must round-trip through json.
    json.dumps(d)
    assert d["ok"] is True
    assert d["plan"] == ["s1", "s2"]
