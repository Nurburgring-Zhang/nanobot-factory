"""智影 V5 — Monitor 子包: Bugu 风格状态监控

迁移自 Bugu (macOS 菜单栏):
- 心跳音效 (5 状态: Accept/Running/Done/Interrupted/Permission)
- Keep Mac awake
- Watch coding agents
- 跳转到对话窗口
"""
from .status import (
    AgentStatus,
    TaskMonitor,
    HeartbeatEvent,
    HeartbeatSound,
    StatusMonitor,
    status_monitor,
)

__all__ = [
    "AgentStatus",
    "TaskMonitor",
    "HeartbeatEvent",
    "HeartbeatSound",
    "StatusMonitor",
    "status_monitor",
]
