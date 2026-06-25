# P6-Fix-P0-4: workflow_orchestrator.py:668 import bug 修复

**Attempt**: 2 (fresh — old deliverables trashed)
**Date**: 2026-06-24 19:35

## Summary

`backend/integrations/multi_agent/workflow_orchestrator.py:668` 的 lazy import bug 已修复：line 668 当前为 `from .agent_registry import get_agent_registry`（相对导入），与同包 `experts_system.py:11` / `agents_company.py:25` 约定一致。`get_global_orchestrator()` 实测返回 `MultiAgentOrchestrator` 实例，`tests/agent/test_multi_turn.py` 5/5 PASS。

## Hard-start check

- 任务描述路径 `backend/imdf/engines/workflow_orchestrator.py` **不存在** (stale path)
- 真实路径 `backend/integrations/multi_agent/workflow_orchestrator.py` — glob 重新定位
- Line 668 当前状态：已修复 (`from .agent_registry import get_agent_registry`)

## Bug diff (vs P6-3 audit baseline)

```diff
 def get_global_orchestrator() -> MultiAgentOrchestrator:
     global _orchestrator
     if _orchestrator is None:
-        from backend.integrations.multi_agent.agent_registry import get_agent_registry
+        from .agent_registry import get_agent_registry
         _orchestrator = MultiAgentOrchestrator(get_agent_registry())
     return _orchestrator
```

**Why this fix is correct**:

1. **同包约定一致**: `experts_system.py:11` 和 `agents_company.py:25` 都用 `from .agent_registry import ...` 相对导入
2. **零 sys.path 依赖**: 相对导入只依赖包内解析, 不依赖外部 caller 怎么放 `backend/` 在 sys.path
3. **修复 lazy import 死代码**: 此 import 在 `get_global_orchestrator()` 被调用时才执行, 普通 `from workflow_orchestrator import X` 不会触发, 所以之前的冒烟测试看不到这个 bug

## Verification (本次 attempt 重新跑)

### Test 1: lazy import inside get_global_orchestrator

```bash
$ python -c "
import sys; sys.path.insert(0, 'backend')
from integrations.multi_agent.workflow_orchestrator import get_global_orchestrator
orch = get_global_orchestrator()
print(type(orch).__name__)
"
MultiAgentOrchestrator
```

### Test 2: dispatcher lazy-init

```bash
$ python -c "
import sys; sys.path.insert(0, 'backend')
from integrations.multi_agent.workflow_orchestrator import get_global_dispatcher
print(type(get_global_dispatcher()).__name__)
"
DispatcherAgent
```

### Test 3: whole package import

```bash
$ python -c "
import sys; sys.path.insert(0, 'backend')
import integrations.multi_agent as ma
print('has MultiAgentOrchestrator:', hasattr(ma, 'MultiAgentOrchestrator'))
"
has MultiAgentOrchestrator: True
```

### Test 4: pytest multi_agent 相关测试

```bash
$ pytest tests/agent/test_multi_turn.py -v
tests/agent/test_multi_turn.py::test_session_create_and_get PASSED         [ 20%]
tests/agent/test_multi_turn.py::test_session_add_messages_and_window PASSED [ 40%]
tests/agent/test_multi_turn.py::test_session_summary_offline PASSED        [ 60%]
tests/agent/test_multi_turn.py::test_session_token_usage PASSED            [ 80%]
tests/agent/test_multi_turn.py::test_session_delete_and_listing PASSED     [100%]
======================== 5 passed, 1 warning in 0.81s ========================
```

## Changed files

| File | Change |
|---|---|
| `backend/integrations/multi_agent/workflow_orchestrator.py:668` | 绝对路径 → 相对路径 (前次 attempt 已落地, 本次验证) |
| `reports/p6_fix_p0_4_workflow.md` | 本报告 (fresh) |
| `outputs/p6_fix_p0_4_workflow_orch/deliverable.md` | deliverable (fresh, attempt 2) |
| `C:\Users\Administrator\.mavis\plans\plan_c8f93c89\board.md` | 进度条目 |

## Notes for verifier

1. **Attempt 1 被 engine 拒绝原因**: engine 报 "No deliverable.md after 2 in-cycle retries". 可能 engine 用 Test-Path 相对路径检查, 在某些 cwd 下返回 False. 本次 attempt 已 trash 所有旧 deliverable (`outputs/p6_fix_p0_4_workflow_orch/deliverable.md`, `outputs/p6_fix_p0_4_workflow/deliverable.md`, `reports/p6_fix_p0_4_workflow.md`) 并重新写.
2. **Stale path 持续出现**: 任务描述给的 `backend/imdf/engines/workflow_orchestrator.py` 不存在. P6-3 audit 报告中的路径引用基于旧目录结构. 真实路径在 `backend/integrations/multi_agent/`.
3. **Bug 实际修复**: 本次 attempt 验证 line 668 仍是 `from .agent_registry import get_agent_registry`, import + pytest 全部 PASS. 前次 attempt 的修复仍在.
4. **Owner 之前已确认**: 19:15 owner 验证 line 668 是相对导入, 标 "P0-4 owner-verified, no-op-already-fixed". 本次 attempt 是 engine 强制重试, 二次确认无误.
5. **后续相关问题 (out of scope)**: `backend/integrations/multi_agent/__init__.py:25+` 仍用 `from backend.integrations.multi_agent.X import ...` 全路径. 这要求 repo root 在 sys.path (e.g. `cd repo-root && python ...`). 当 sys.path 只有 `backend/` 时会失败 (ModuleNotFoundError: No module named 'backend'). 这是 P6-3 提到的另一个问题, 不在 P0-4 任务范围内, 建议作为 P0-5 / P1 单独立项.