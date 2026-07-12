"""智影 V5 — 状态监控器 (Bugu 风格)"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent 状态 (5 状态 — Bugu 模式)"""
    ACCEPT = "accept"            # 接收新任务
    RUNNING = "running"          # 运行中
    DONE = "done"                # 完成
    INTERRUPTED = "interrupted"  # 意外中断
    PERMISSION = "permission"    # 需授权


class HeartbeatSound(str, Enum):
    """心跳音效 (Bugu 5 种)"""
    SILENT = "silent"             # 静音
    SYSTEM = "system"             # 系统音
    BUGU_PACK = "bugu_pack"       # Bugu Pack
    SUBTLE = "subtle"             # 微妙
    CUSTOM = "custom"             # 自定义


@dataclass
class TaskMonitor:
    """任务监控 — 单个任务的实时状态"""

    task_id: str = field(default_factory=lambda: f"tm-{uuid.uuid4().hex[:10]}")
    title: str = ""
    agent_id: str = ""
    agent_name: str = ""
    status: AgentStatus = AgentStatus.ACCEPT
    started_at: float = 0.0
    ended_at: float = 0.0
    last_heartbeat: float = 0.0
    duration_sec: float = 0.0
    progress: float = 0.0
    input_prompt: str = ""
    output: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update(self, status: AgentStatus, progress: float = 0.0):
        self.status = status
        self.progress = progress
        self.last_heartbeat = time.time()
        if self.started_at == 0:
            self.started_at = time.time()
        if status in (AgentStatus.DONE, AgentStatus.INTERRUPTED):
            self.ended_at = time.time()
            self.duration_sec = self.ended_at - self.started_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_heartbeat": self.last_heartbeat,
            "duration_sec": self.duration_sec,
            "progress": self.progress,
            "input_prompt": self.input_prompt[:100],
            "output_preview": self.output[:200] if self.output else "",
        }


@dataclass
class HeartbeatEvent:
    """心跳事件"""

    event_id: str = field(default_factory=lambda: f"he-{uuid.uuid4().hex[:8]}")
    task_id: str = ""
    agent_id: str = ""
    status: AgentStatus = AgentStatus.RUNNING
    timestamp: float = 0.0
    sound: HeartbeatSound = HeartbeatSound.SYSTEM
    message: str = ""


class StatusMonitor:
    """状态监控器 — Bugu 模式"""

    def __init__(self):
        self.tasks: Dict[str, TaskMonitor] = {}
        self.events: List[HeartbeatEvent] = []
        self.heartbeat_interval_sec: float = 300.0  # 5 分钟
        self.sound_enabled: bool = True
        self.keep_awake: bool = False
        self.sound: HeartbeatSound = HeartbeatSound.SYSTEM
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._active_loops: Dict[str, bool] = {}
        self.metrics: Dict[str, int] = {"heartbeats": 0, "status_changes": 0}

    def register_task(
        self,
        title: str,
        agent_id: str = "",
        agent_name: str = "",
        input_prompt: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskMonitor:
        """注册新任务"""
        tm = TaskMonitor(
            title=title,
            agent_id=agent_id,
            agent_name=agent_name,
            input_prompt=input_prompt,
            metadata=metadata or {},
        )
        self.tasks[tm.task_id] = tm
        self._emit_heartbeat(tm, AgentStatus.ACCEPT, "任务已接收")
        return tm

    def update_task(
        self,
        task_id: str,
        status: Optional[AgentStatus] = None,
        progress: Optional[float] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Optional[TaskMonitor]:
        """更新任务状态"""
        tm = self.tasks.get(task_id)
        if not tm:
            return None
        if status:
            old_status = tm.status
            tm.status = status
            if old_status != status:
                self.metrics["status_changes"] += 1
                self._emit_heartbeat(tm, status, self._status_message(status))
        if progress is not None:
            tm.progress = progress
        if output is not None:
            tm.output = output
        if error:
            tm.error = error
        tm.last_heartbeat = time.time()
        if status in (AgentStatus.DONE, AgentStatus.INTERRUPTED):
            tm.ended_at = time.time()
            tm.duration_sec = tm.ended_at - tm.started_at
        return tm

    def get_task(self, task_id: str) -> Optional[TaskMonitor]:
        return self.tasks.get(task_id)

    def list_tasks(
        self,
        status: Optional[AgentStatus] = None,
        agent_id: Optional[str] = None,
    ) -> List[TaskMonitor]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        if agent_id:
            tasks = [t for t in tasks if t.agent_id == agent_id]
        return tasks

    def get_running_tasks(self) -> List[TaskMonitor]:
        return self.list_tasks(status=AgentStatus.RUNNING)

    def start_heartbeat_loop(self, task_id: str):
        """启动心跳循环 (Bugu 风格)"""
        if task_id in self._running_tasks:
            return
        self._active_loops[task_id] = True

        async def loop():
            while self._active_loops.get(task_id, False):
                await asyncio.sleep(self.heartbeat_interval_sec)
                tm = self.tasks.get(task_id)
                if not tm or tm.status in (AgentStatus.DONE, AgentStatus.INTERRUPTED):
                    break
                self._emit_heartbeat(tm, AgentStatus.RUNNING, f"运行中 ({tm.progress*100:.0f}%)")
        try:
            self._running_tasks[task_id] = asyncio.create_task(loop())
        except RuntimeError:
            pass

    def stop_heartbeat_loop(self, task_id: str):
        self._active_loops[task_id] = False
        if task_id in self._running_tasks:
            self._running_tasks[task_id].cancel()
            del self._running_tasks[task_id]

    def _emit_heartbeat(self, tm: TaskMonitor, status: AgentStatus, message: str):
        """触发心跳事件"""
        ev = HeartbeatEvent(
            task_id=tm.task_id,
            agent_id=tm.agent_id,
            status=status,
            timestamp=time.time(),
            sound=self.sound if self.sound_enabled else HeartbeatSound.SILENT,
            message=message,
        )
        self.events.append(ev)
        self.metrics["heartbeats"] += 1
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
        logger.info(f"[{status.value}] {tm.title}: {message}")

    def _status_message(self, status: AgentStatus) -> str:
        return {
            AgentStatus.ACCEPT: "任务已接收",
            AgentStatus.RUNNING: "运行中",
            AgentStatus.DONE: "任务完成",
            AgentStatus.INTERRUPTED: "任务被中断",
            AgentStatus.PERMISSION: "需要授权",
        }.get(status, "未知状态")

    def set_sound(self, sound: HeartbeatSound, enabled: bool = True):
        self.sound = sound
        self.sound_enabled = enabled

    def set_heartbeat_interval(self, seconds: float):
        self.heartbeat_interval_sec = seconds

    def set_keep_awake(self, enabled: bool):
        self.keep_awake = enabled

    def get_stats(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        for t in self.tasks.values():
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
        return {
            "total_tasks": len(self.tasks),
            "by_status": by_status,
            "running": sum(1 for t in self.tasks.values() if t.status == AgentStatus.RUNNING),
            "heartbeats": self.metrics["heartbeats"],
            "status_changes": self.metrics["status_changes"],
            "sound": self.sound.value,
            "heartbeat_interval_sec": self.heartbeat_interval_sec,
            "keep_awake": self.keep_awake,
        }


status_monitor = StatusMonitor()
