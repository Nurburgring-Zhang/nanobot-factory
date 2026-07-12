"""
P19 v5.1-B — test_skills_executor

验证 SkillExecutorV51 的:
1. 异步执行
2. 超时控制
3. 重试逻辑
4. 审计日志
"""

import asyncio

import pytest

from backend.external_skills import (
    SkillExecutionRecord,
    SkillExecutor,
    SkillExecutorV51,
)
from backend.skills import SkillSpec
from backend.skills_manager import SkillRegistry, SkillRegistryV51


def _run(coro):
    """py3.6+ 兼容运行入口"""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture
def fast_executor():
    """timeout=1s, retries=2, backoff=0.01s (测试快)"""
    reg = SkillRegistryV51()
    return SkillExecutorV51(
        registry=reg,
        default_timeout_sec=1.0,
        max_retries=2,
        retry_backoff_sec=0.01,
    )


@pytest.fixture
def builtin_executor():
    reg = SkillRegistryV51.from_builtin([
        SkillSpec(id="skill_dummy", name="Dummy", category="process")
    ])
    return SkillExecutorV51(
        registry=reg,
        default_timeout_sec=2.0,
        max_retries=3,
        retry_backoff_sec=0.001,
    )


class TestAsyncExecute:
    def test_execute_skill_success(self, builtin_executor):
        # 用 metadata.handler_coro 注入一个 dummy coro
        async def handler(inputs):
            return {"echo": dict(inputs), "ok": True}

        builtin_executor.registry.get("skill_dummy").metadata = {
            "handler_coro": handler,
        }
        r = _run(builtin_executor.execute(
            "skill_dummy", {"a": 1, "b": "x"},
        ))
        assert r["ok"] is True
        assert r["skill_id"] == "skill_dummy"
        assert r["result"]["echo"] == {"a": 1, "b": "x"}
        assert r["attempts"] == 1

    def test_execute_unknown_skill(self, builtin_executor):
        r = _run(builtin_executor.execute("not_registered", {}))
        assert r["ok"] is False
        assert "not found" in r["error"]
        assert r["attempts"] == 0

    def test_execute_disabled_skill(self, builtin_executor):
        async def h(i):
            return {"ok": True}
        builtin_executor.registry.get("skill_dummy").metadata = {"handler_coro": h}
        builtin_executor.registry.get("skill_dummy").enabled = False
        r = _run(builtin_executor.execute("skill_dummy", {}))
        assert r["ok"] is False
        assert "disabled" in r["error"]


class TestTimeout:
    def test_timeout_triggers_retries(self):
        reg = SkillRegistryV51()
        calls = {"n": 0}

        async def slow_handler(inputs):
            calls["n"] += 1
            await asyncio.sleep(0.5)  # > 0.1s timeout
            return {"ok": True}

        skill = SkillSpec(
            id="skill_slow", name="Slow", category="process",
        )
        skill.metadata = {"handler_coro": slow_handler}
        reg.register(skill)

        ex = SkillExecutorV51(
            registry=reg, default_timeout_sec=0.1,
            max_retries=3, retry_backoff_sec=0.001,
        )
        r = _run(ex.execute("skill_slow", {}))
        assert r["ok"] is False
        assert "timeout" in r["error"].lower()
        assert r["attempts"] == 3
        assert calls["n"] == 3  # 触发了 3 次调用


class TestRetry:
    def test_retry_until_success(self):
        reg = SkillRegistryV51()
        calls = {"n": 0}

        async def flaky_handler(inputs):
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("transient")
            return {"ok": True, "calls": calls["n"]}

        skill = SkillSpec(
            id="skill_flaky", name="Flaky", category="process",
        )
        skill.metadata = {"handler_coro": flaky_handler}
        reg.register(skill)

        ex = SkillExecutorV51(
            registry=reg, default_timeout_sec=2.0,
            max_retries=3, retry_backoff_sec=0.001,
        )
        r = _run(ex.execute("skill_flaky", {}))
        assert r["ok"] is True
        assert r["attempts"] == 2  # 第二次成功
        assert calls["n"] == 2

    def test_retry_exhausted_returns_failure(self):
        reg = SkillRegistryV51()
        calls = {"n": 0}

        async def always_fail(inputs):
            calls["n"] += 1
            raise RuntimeError("always fail")

        skill = SkillSpec(
            id="skill_dead", name="Dead", category="process",
        )
        skill.metadata = {"handler_coro": always_fail}
        reg.register(skill)

        ex = SkillExecutorV51(
            registry=reg, default_timeout_sec=2.0,
            max_retries=3, retry_backoff_sec=0.001,
        )
        r = _run(ex.execute("skill_dead", {}))
        assert r["ok"] is False
        assert r["attempts"] == 3
        assert calls["n"] == 3
        assert "always fail" in r["error"]


class TestAuditLog:
    def test_audit_record_per_call(self, builtin_executor):
        async def h(i):
            return {"ok": True}
        builtin_executor.registry.get("skill_dummy").metadata = {"handler_coro": h}

        _run(builtin_executor.execute("skill_dummy", {"x": 1}))
        _run(builtin_executor.execute("skill_dummy", {"y": 2}))
        _run(builtin_executor.execute("skill_dummy", {}))

        log = builtin_executor.get_audit_log()
        assert len(log) == 3
        assert all(isinstance(r, SkillExecutionRecord) for r in log)
        assert all(r.skill_id == "skill_dummy" for r in log)
        assert all(r.success for r in log)

    def test_audit_filter_by_skill_id(self, builtin_executor):
        async def h(i):
            return {"ok": True}
        builtin_executor.registry.get("skill_dummy").metadata = {"handler_coro": h}
        _run(builtin_executor.execute("skill_dummy", {}))
        _run(builtin_executor.execute("not_found", {}))
        log = builtin_executor.get_audit_log("skill_dummy")
        assert len(log) == 1
        assert log[0].skill_id == "skill_dummy"

    def test_clear_audit_log(self, builtin_executor):
        async def h(i):
            return {"ok": True}
        builtin_executor.registry.get("skill_dummy").metadata = {"handler_coro": h}
        _run(builtin_executor.execute("skill_dummy", {}))
        n = builtin_executor.clear_audit_log()
        assert n == 1
        assert builtin_executor.get_audit_log() == []


class TestAlias:
    def test_executor_alias(self):
        assert SkillExecutor is SkillExecutorV51
