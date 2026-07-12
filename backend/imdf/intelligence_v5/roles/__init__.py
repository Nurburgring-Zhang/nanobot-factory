"""智影 V5 — Roles 子包: The Agency 232 角色 16 部门

迁移自 The Agency (msitarzewski/agency-agents, 11.9万 Star):
- 16 部门 (开发/设计/产品/营销/测试/...)
- 232 个 Agent 角色
- 每个角色含: 表达语气 + 工作流 + 交付物 + 硬核指标
"""
from .departments import (
    Department,
    DEPARTMENTS,
)
from .roles_definitions import (
    ROLES_DATABASE,
    RoleDefinition,
    RoleCategory,
    RoleExpressionTone,
    RoleWorkflow,
    RoleDeliverable,
    RoleMetrics,
    role_registry,
)

__all__ = [
    "Department",
    "DEPARTMENTS",
    "ROLES_DATABASE",
    "RoleDefinition",
    "RoleCategory",
    "RoleExpressionTone",
    "RoleWorkflow",
    "RoleDeliverable",
    "RoleMetrics",
    "role_registry",
]
