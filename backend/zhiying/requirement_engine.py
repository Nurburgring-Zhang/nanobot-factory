"""需求全生命周期管理引擎

需求状态机: draft → reviewing → approved → in_progress → completed → archived
支持自动拆解、验收标准、依赖关系
"""

from core.requirement_manager import (
    Requirement,
    RequirementType,
    Priority,
    RequirementStatus,
    SubTask,
    RequirementManager,
)

__all__ = [
    "Requirement", "RequirementType", "Priority",
    "RequirementStatus", "SubTask", "RequirementManager",
]
