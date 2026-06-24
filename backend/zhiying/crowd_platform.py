"""众包管理平台

人员管理: CrowdWorker (5级) + 技能标签 + 准确率追踪
任务管理: CrowdTask (8状态) + 众包批处理 + 自动分配策略
"""

from core.crowdsource import (
    CrowdWorker,
    CrowdWorkerLevel,
    CrowdTask,
    TaskType,
    TaskStatus,
    CrowdManager,
    crowd,  # 全局单例
)

__all__ = [
    "CrowdWorker", "CrowdWorkerLevel", "CrowdTask",
    "TaskType", "TaskStatus", "CrowdManager", "crowd",
]
