"""V5 第40章 — ABAC (Attribute-Based Access Control) engine.

设计上保留 3 个 built-in policies (owner_delete_own / admin_bypass /
project_member_read) 作为最常见 RBAC 拓展场景,也允许调用方注册自定义策略.

求值语义: 对每个 policy,所有 conditions AND 求值; 多个 policy 之间 first-match
(allow 找到一条立即返回 allow; deny 找到一条立即返回 deny; 都没命中默认 deny).
attribute 路径支持 dot notation (e.g. "user.id", "resource.owner_id", "context.role").
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional

from .sso_mfa_c2pa_schemas import (
    ABACDecision,
    ABACPolicy,
    Condition,
    ConditionOp,
)

logger = logging.getLogger(__name__)


_DOT_PATH_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


def _resolve_attr(obj: Any, path: str) -> Any:
    """从 dict 或 object 中取 dot-path 属性.

    路径每一段都允许访问 dict key 或 object attribute.
    缺失返回 None (避免抛 KeyError/AttributeError,让条件失败更直观).
    """
    cur: Any = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _eval_condition(cond: Condition, ctx: Dict[str, Any]) -> bool:
    val = _resolve_attr(ctx, cond.attribute)
    op = cond.op
    target = cond.value
    try:
        if op == ConditionOp.EQ:
            return val == target
        if op == ConditionOp.NEQ:
            return val != target
        if op == ConditionOp.IN:
            if not isinstance(target, (list, tuple, set)):
                return False
            return val in target
        if op == ConditionOp.NOT_IN:
            if not isinstance(target, (list, tuple, set)):
                return True
            return val not in target
        if op == ConditionOp.GT:
            if val is None or target is None:
                return False
            return val > target
        if op == ConditionOp.LT:
            if val is None or target is None:
                return False
            return val < target
        if op == ConditionOp.CONTAINS:
            if val is None:
                return False
            if isinstance(val, (list, tuple, set, str)):
                return target in val
            return False
        if op == ConditionOp.IN_ATTR:
            # value 是另一个 attribute path,从 ctx 取 list 后判断 val in list
            if val is None or not isinstance(target, str):
                return False
            list_val = _resolve_attr(ctx, target)
            if not isinstance(list_val, (list, tuple, set)):
                return False
            return val in list_val
    except Exception as e:  # noqa: BLE001
        logger.debug("condition eval error %s: %s", cond.attribute, e)
        return False
    return False


class ABACEngine:
    """ABAC 决策引擎 + 内置策略注册表.

    用法:
        engine = ABACEngine()
        engine.add_policy(ABACPolicy(...))
        decision = engine.enforce(user, resource, action, context={})
    """

    def __init__(self) -> None:
        self._policies: List[ABACPolicy] = []
        # 注入 built-in policies
        for p in _BUILTIN_POLICIES:
            self._policies.append(p)

    # ── Policy 管理 ─────────────────────────────────────────────────────
    def add_policy(self, policy: ABACPolicy) -> None:
        self._policies.append(policy)

    def remove_policy(self, name: str) -> bool:
        before = len(self._policies)
        self._policies = [p for p in self._policies if p.name != name]
        return len(self._policies) < before

    def list_policies(self) -> List[ABACPolicy]:
        return list(self._policies)

    def reset_policies(self, keep_builtins: bool = True) -> None:
        """重置策略; 默认保留 built-in."""
        self._policies = list(_BUILTIN_POLICIES) if keep_builtins else []

    # ── 同步 evaluate ──────────────────────────────────────────────────
    def evaluate(
        self,
        user_attrs: Dict[str, Any],
        resource_attrs: Dict[str, Any],
        action: str,
        policy: Optional[ABACPolicy] = None,
    ) -> bool:
        """对单条 policy 求值; 缺省 None 表示用所有 builtin 求值 (any-match)."""
        ctx = {"user": user_attrs, "resource": resource_attrs, "context": {}}
        if policy is not None:
            return all(_eval_condition(c, ctx) for c in policy.conditions)
        # 任意 builtin allow 命中即 True
        for p in self._policies:
            if p.action != action:
                continue
            ctx_match = {
                "user": user_attrs,
                "resource": resource_attrs,
                "context": {},
            }
            if all(_eval_condition(c, ctx_match) for c in p.conditions):
                return True
        return False

    # ── 业务 enforce ───────────────────────────────────────────────────
    def enforce(
        self,
        user_id: str,
        resource: str,
        action: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ABACDecision:
        """公开 enforce 入口 — 业务调用方 use this.

        Args:
            user_id:  发起请求的用户
            resource: 目标资源 (e.g. "project:42", "dataset:abc")
            action:   操作 (e.g. "read", "delete")
            context:  可选上下文 (user 完整 attrs / resource 完整 attrs)
        """
        ctx = context or {}
        user_attrs = dict(ctx.get("user_attrs") or {})
        user_attrs.setdefault("id", user_id)
        # 允许调用方直接传 user_attrs.id, 也允许只用 user_id
        if "role" not in user_attrs and "role" in ctx:
            user_attrs["role"] = ctx["role"]

        resource_attrs = dict(ctx.get("resource_attrs") or {})
        resource_attrs.setdefault("type", resource.split(":")[0] if ":" in resource else resource)
        resource_attrs.setdefault("id", resource.split(":")[1] if ":" in resource else resource)

        env_attrs = dict(ctx.get("env") or {})
        full_ctx = {"user": user_attrs, "resource": resource_attrs, "context": env_attrs}

        # First-match (allow first; deny second; default deny)
        for p in self._policies:
            if p.resource != resource_attrs.get("type") and p.resource != "*":
                continue
            if p.action != action and p.action != "*":
                continue
            if all(_eval_condition(c, full_ctx) for c in p.conditions):
                return ABACDecision(
                    allow=(p.effect == "allow"),
                    matched_policy=p.name,
                    reason=p.description or f"matched policy {p.name}",
                    user_id=user_id,
                    resource=resource,
                    action=action,
                )

        return ABACDecision(
            allow=False,
            matched_policy=None,
            reason="no policy matched; default deny",
            user_id=user_id,
            resource=resource,
            action=action,
        )


# ════════════════════════════════════════════════════════════════════════
# Built-in policies
# ════════════════════════════════════════════════════════════════════════
_BUILTIN_POLICIES: List[ABACPolicy] = [
    ABACPolicy(
        name="admin_bypass",
        resource="*",
        action="*",
        effect="allow",
        description="admin role bypass — admins can do anything",
        conditions=[
            Condition(attribute="user.role", op=ConditionOp.EQ, value="admin"),
        ],
    ),
    ABACPolicy(
        name="owner_delete_own",
        resource="*",
        action="delete",
        effect="allow",
        description="owner can delete own resource",
        conditions=[
            Condition(attribute="user.id", op=ConditionOp.EQ, value=None),  # placeholder
            Condition(attribute="resource.owner_id", op=ConditionOp.EQ, value=None),
        ],
    ).__class__(
        name="owner_delete_own",
        resource="*",
        action="delete",
        effect="allow",
        description="owner can delete own resource (user.id == resource.owner_id)",
        conditions=[
            Condition(
                attribute="user.id",
                op=ConditionOp.EQ,
                value="__SELF__",  # 哨兵: enforce 时替换为 resource.owner_id
            ),
            Condition(
                attribute="resource.owner_id",
                op=ConditionOp.EQ,
                value="__SELF__",
            ),
        ],
    ),
    ABACPolicy(
        name="project_member_read",
        resource="project",
        action="read",
        effect="allow",
        description="member of project (user.id in resource.member_ids) can read project",
        conditions=[
            Condition(
                attribute="user.id",
                op=ConditionOp.IN_ATTR,
                value="resource.member_ids",
            ),
        ],
    ),
]


# ════════════════════════════════════════════════════════════════════════
# 哨兵替换:让 user.id == resource.owner_id 这种"自指"条件能直接表达
# ════════════════════════════════════════════════════════════════════════
def _resolve_self_conditions(
    policy: ABACPolicy,
    full_ctx: Dict[str, Any],
) -> bool:
    """对包含 __SELF__ 哨兵的条件做特殊解析.

    策略:
      * 如果 value == "__SELF__",则用 attribute 指向的 actual value 进行"等值检查";
        两个条件合起来等价于 user.id == resource.owner_id.
      * 如果 value 是 "__SELF__" 且 op == IN,则把 value 替换为 attribute 指向的 list,
        实现 user.id in resource.member_ids.
    """
    user_id = full_ctx["user"].get("id")
    for cond in policy.conditions:
        if cond.value == "__SELF__":
            # 解析另一个条件的 attribute 指向的 actual value
            other_val = _resolve_attr(full_ctx, cond.attribute)
            if cond.op == ConditionOp.EQ:
                if other_val != user_id:
                    return False
            elif cond.op == ConditionOp.IN:
                if not isinstance(other_val, (list, tuple, set)):
                    return False
                if user_id not in other_val:
                    return False
            elif cond.op == ConditionOp.IN_ATTR:
                # attribute = "user.id" (needle), value = "resource.member_ids" (list source)
                list_val = _resolve_attr(full_ctx, cond.value)
                if not isinstance(list_val, (list, tuple, set)):
                    return False
                if user_id not in list_val:
                    return False
            else:
                return False
        else:
            if not _eval_condition(cond, full_ctx):
                return False
    return True


# 覆盖 evaluate / enforce 中 _eval_condition 的求值逻辑以支持 __SELF__
_orig_enforce = ABACEngine.enforce


def _enforce_with_self(
    self: ABACEngine,
    user_id: str,
    resource: str,
    action: str,
    context: Optional[Dict[str, Any]] = None,
) -> ABACDecision:
    ctx = context or {}
    user_attrs = dict(ctx.get("user_attrs") or {})
    user_attrs.setdefault("id", user_id)
    if "role" not in user_attrs and "role" in ctx:
        user_attrs["role"] = ctx["role"]
    resource_attrs = dict(ctx.get("resource_attrs") or {})
    resource_attrs.setdefault("type", resource.split(":")[0] if ":" in resource else resource)
    resource_attrs.setdefault("id", resource.split(":")[1] if ":" in resource else resource)
    env_attrs = dict(ctx.get("env") or {})
    full_ctx = {"user": user_attrs, "resource": resource_attrs, "context": env_attrs}

    # First-match (allow first)
    for p in self._policies:
        if p.resource not in ("*", resource_attrs.get("type")):
            continue
        if p.action not in ("*", action):
            continue
        if any(c.value == "__SELF__" for c in p.conditions):
            ok = _resolve_self_conditions(p, full_ctx)
        else:
            ok = all(_eval_condition(c, full_ctx) for c in p.conditions)
        if ok:
            return ABACDecision(
                allow=(p.effect == "allow"),
                matched_policy=p.name,
                reason=p.description or f"matched policy {p.name}",
                user_id=user_id, resource=resource, action=action,
            )
    return ABACDecision(
        allow=False, matched_policy=None,
        reason="no policy matched; default deny",
        user_id=user_id, resource=resource, action=action,
    )


ABACEngine.enforce = _enforce_with_self  # type: ignore[assignment]


# 同时覆盖 evaluate (单 policy 路径),保持一致
def _evaluate_with_self(
    self: ABACEngine,
    user_attrs: Dict[str, Any],
    resource_attrs: Dict[str, Any],
    action: str,
    policy: Optional[ABACPolicy] = None,
) -> bool:
    full_ctx = {"user": user_attrs, "resource": resource_attrs, "context": {}}
    if policy is not None:
        if any(c.value == "__SELF__" for c in policy.conditions):
            return _resolve_self_conditions(policy, full_ctx)
        return all(_eval_condition(c, full_ctx) for c in policy.conditions)
    for p in self._policies:
        if p.action != action and p.action != "*":
            continue
        if any(c.value == "__SELF__" for c in p.conditions):
            ok = _resolve_self_conditions(p, full_ctx)
        else:
            ok = all(_eval_condition(c, full_ctx) for c in p.conditions)
        if ok:
            return True
    return False


ABACEngine.evaluate = _evaluate_with_self  # type: ignore[assignment]


__all__ = ["ABACEngine"]