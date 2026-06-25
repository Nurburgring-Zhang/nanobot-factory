"""P1-9: 客户细分 (Customer Segment) 引擎.

业务背景:
- 营销/销售需要按规则对客户分群, 进行差异化运营.
- Segment 是一组规则 (predicates), 客户满足规则 → 命中 segment.
- 与 lead scoring 不同: lead_score 是数值评分, segment 是布尔命中/不命中.
- 典型 segment: 高价值客户 (LTV > 50k + tier >= mid_market) / 即将流失
  (30 天无活动 + 投诉 ≥ 1) / 待跟进 (新注册 7 天内未联系) / 月度复购潜力.

公开 API:
  - define_segment(name, rules, description)   → Segment
  - evaluate_segment(segment, customer)         → bool
  - match_customers(segment)                     → List[Customer]
  - list_segments()                              → [Segment]
  - delete_segment(segment_id)                   → bool
  - evaluate_all_segments(customer)              → Dict[segment_id, bool]
  - get_segment_stats()                          → Dict

规则语法 (DSL):
  field path + operator + value, 多规则 AND/OR 组合
  - field: tier / industry / size / tags / lifetime_value / followup_count /
           days_since_last_activity / complaint_count / days_since_signup
  - operator: eq / ne / gt / gte / lt / lte / in / contains
  - value: scalar or list
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule DSL
# ---------------------------------------------------------------------------
# 支持字段
SUPPORTED_FIELDS = {
    "tier", "industry", "size", "tags", "lifetime_value",
    "followup_count", "days_since_last_activity",
    "complaint_count", "days_since_signup", "status",
    "lead_score", "lead_grade",
}
SUPPORTED_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "not_in"}
# 组合方式
COMBINATORS = {"and", "or"}


@dataclass
class Segment:
    segment_id: str
    name: str
    description: str
    rules: Dict[str, Any]              # rule tree (DSL)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    customer_count: int = 0             # 缓存 (recompute 时更新)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 存储
_SEGMENTS: Dict[str, Segment] = {}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def _extract_field(customer: Any, field_name: str) -> Any:
    """从 Customer 实例/字典提取字段值."""
    # 优先属性, fallback to dict
    if hasattr(customer, field_name):
        v = getattr(customer, field_name)
        if v is not None:
            return v
    if isinstance(customer, dict):
        return customer.get(field_name)
    return None


def _compute_derived(customer: Any, field_name: str) -> Any:
    """计算派生字段: followup_count / complaint_count / days_since_*."""
    if field_name == "followup_count":
        fus = _extract_field(customer, "followups") or []
        return len(fus)
    if field_name == "complaint_count":
        fus = _extract_field(customer, "followups") or []
        return sum(1 for f in fus if (f.get("type") if isinstance(f, dict) else getattr(f, "type", None)) == "complaint")
    if field_name == "days_since_last_activity":
        ua = _extract_field(customer, "updated_at")
        if not ua:
            return 9999
        dt = _parse_dt(ua)
        if dt is None:
            return 9999
        return (datetime.utcnow() - dt).days
    if field_name == "days_since_signup":
        ca = _extract_field(customer, "created_at")
        if not ca:
            return 9999
        dt = _parse_dt(ca)
        if dt is None:
            return 9999
        return (datetime.utcnow() - dt).days
    return None


def _eval_simple(rule: Dict[str, Any], customer: Any) -> bool:
    """评估单条规则 {field, op, value}."""
    field_name = rule.get("field", "")
    op = rule.get("op", "eq")
    value = rule.get("value")
    if field_name not in SUPPORTED_FIELDS:
        return False
    if op not in SUPPORTED_OPS:
        return False
    # 提取值
    actual = _extract_field(customer, field_name)
    if actual is None:
        actual = _compute_derived(customer, field_name)
    if actual is None:
        return False
    # 评估
    try:
        if op == "eq":
            return actual == value
        if op == "ne":
            return actual != value
        if op == "gt":
            return float(actual) > float(value)
        if op == "gte":
            return float(actual) >= float(value)
        if op == "lt":
            return float(actual) < float(value)
        if op == "lte":
            return float(actual) <= float(value)
        if op == "in":
            return actual in (value or [])
        if op == "not_in":
            return actual not in (value or [])
        if op == "contains":
            if isinstance(actual, (list, tuple, set)):
                return value in actual
            return str(value) in str(actual)
    except (TypeError, ValueError):
        return False
    return False


def _eval_rule_tree(rules: Dict[str, Any], customer: Any) -> bool:
    """递归评估规则树."""
    if "field" in rules:
        return _eval_simple(rules, customer)
    combinator = rules.get("combinator", "and")
    sub_rules = rules.get("rules", [])
    if combinator == "and":
        return all(_eval_rule_tree(r, customer) for r in sub_rules)
    if combinator == "or":
        return any(_eval_rule_tree(r, customer) for r in sub_rules)
    return False


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------
def define_segment(
    name: str,
    rules: Dict[str, Any],
    description: str = "",
) -> Segment:
    """定义一个 segment."""
    if not name:
        raise ValueError("name is required")
    if not rules:
        raise ValueError("rules is required")
    # 简单校验
    if "field" not in rules and "rules" not in rules:
        raise ValueError("rules must have either 'field' (simple) or 'rules' (composite)")
    sid = f"SG-{uuid.uuid4().hex[:8].upper()}"
    s = Segment(segment_id=sid, name=name, description=description, rules=rules)
    _SEGMENTS[sid] = s
    logger.info("segment defined: %s name=%s", sid, name)
    return s


def evaluate_segment(segment: Segment, customer: Any) -> bool:
    return _eval_rule_tree(segment.rules, customer)


def match_customers(segment: Segment, customers: Optional[List[Any]] = None) -> List[Any]:
    """返回所有命中该 segment 的客户. 接受外部 customer 列表 (便于测试)."""
    if customers is None:
        from . import _CUSTOMERS  # type: ignore
        customers = list(_CUSTOMERS.values())
    return [c for c in customers if _eval_rule_tree(segment.rules, c)]


def list_segments() -> List[Segment]:
    return list(_SEGMENTS.values())


def get_segment(segment_id: str) -> Optional[Segment]:
    return _SEGMENTS.get(segment_id)


def delete_segment(segment_id: str) -> bool:
    return _SEGMENTS.pop(segment_id, None) is not None


def update_segment_count() -> Dict[str, int]:
    """重算所有 segment 的 customer_count. 返回 {segment_id: count}."""
    from . import _CUSTOMERS  # type: ignore
    customers = list(_CUSTOMERS.values())
    out = {}
    for s in _SEGMENTS.values():
        cnt = sum(1 for c in customers if _eval_rule_tree(s.rules, c))
        s.customer_count = cnt
        out[s.segment_id] = cnt
    return out


def evaluate_all_segments(customer: Any) -> Dict[str, bool]:
    """对单个客户评估所有 segment, 返回 {segment_id: matched}."""
    return {s.segment_id: _eval_rule_tree(s.rules, customer) for s in _SEGMENTS.values()}


def get_segment_stats() -> Dict[str, Any]:
    counts = update_segment_count()
    return {
        "total_segments": len(_SEGMENTS),
        "by_id": counts,
    }


# ---------------------------------------------------------------------------
# 预置 segment 模板
# ---------------------------------------------------------------------------
PRESET_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "high_value": {
        "name": "高价值客户",
        "description": "tier >= mid_market + LTV > 50k + 30 天内有活动",
        "rules": {
            "combinator": "and",
            "rules": [
                {"field": "tier", "op": "in", "value": ["mid_market", "large", "strategic"]},
                {"field": "lifetime_value", "op": "gt", "value": 50000},
                {"field": "days_since_last_activity", "op": "lt", "value": 30},
            ],
        },
    },
    "at_risk_churn": {
        "name": "流失风险",
        "description": "30 天无活动 + 投诉 ≥ 1",
        "rules": {
            "combinator": "and",
            "rules": [
                {"field": "days_since_last_activity", "op": "gt", "value": 30},
                {"field": "complaint_count", "op": "gte", "value": 1},
            ],
        },
    },
    "new_lead": {
        "name": "新潜客 (待跟进)",
        "description": "注册 ≤ 7 天 + 无跟进",
        "rules": {
            "combinator": "and",
            "rules": [
                {"field": "days_since_signup", "op": "lte", "value": 7},
                {"field": "followup_count", "op": "eq", "value": 0},
            ],
        },
    },
    "grade_a_leads": {
        "name": "A 级潜客",
        "description": "lead_grade == A",
        "rules": {"field": "lead_grade", "op": "eq", "value": "A"},
    },
}


def create_preset(preset_key: str) -> Segment:
    """从模板创建 segment."""
    if preset_key not in PRESET_TEMPLATES:
        raise ValueError(f"unknown preset: {preset_key!r}. valid: {list(PRESET_TEMPLATES)}")
    t = PRESET_TEMPLATES[preset_key]
    return define_segment(name=t["name"], description=t["description"], rules=t["rules"])


# ---------------------------------------------------------------------------
# 测试用 — 重置
# ---------------------------------------------------------------------------
def _reset_segments() -> None:
    _SEGMENTS.clear()


__all__ = [
    "SUPPORTED_FIELDS", "SUPPORTED_OPS", "COMBINATORS", "PRESET_TEMPLATES",
    "Segment",
    "define_segment", "evaluate_segment", "match_customers",
    "list_segments", "get_segment", "delete_segment", "update_segment_count",
    "evaluate_all_segments", "get_segment_stats", "create_preset",
    "_reset_segments",
]
