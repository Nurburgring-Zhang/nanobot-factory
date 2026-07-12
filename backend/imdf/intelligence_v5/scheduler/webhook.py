"""智影 V5 — Webhook 接收器 + Goal 运行器 + 看板

迁移自 Hermes Agent:
- Webhook 接收外部 HTTP 触发 /goal
- Goal = 完整任务边界 (结果/来源/约束/可交付物)
- 看板追踪任务状态
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ===== Goal =====
class GoalStatus(str, Enum):
    """Goal 状态"""
    DRAFT = "draft"
    ACTIVE = "active"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class GoalDefinition:
    """Goal 定义 — 4 块: 结果/来源/约束/可交付物"""

    name: str
    goal_id: str = field(default_factory=lambda: f"goal-{uuid.uuid4().hex[:10]}")
    # 4 块
    result: str = ""               # 做成了什么样才算完
    sources: List[str] = field(default_factory=list)   # 工具/文件/URL, 不依赖记忆
    constraints: List[str] = field(default_factory=list)  # 格式/调用次数/风格
    deliverables: List[str] = field(default_factory=list)  # 文件名/JSON schema/提交地点
    # 可选
    deadline: float = 0.0
    priority: str = "medium"
    tags: List[str] = field(default_factory=list)
    # 状态
    status: GoalStatus = GoalStatus.DRAFT
    progress: float = 0.0  # 0-1
    current_step: str = ""
    # 触发
    trigger_source: str = ""  # "cron" | "webhook" | "manual"
    trigger_metadata: Dict[str, Any] = field(default_factory=dict)
    # 时间
    started_at: float = 0.0
    completed_at: float = 0.0
    created_at: float = 0.0
    # 产出
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "status": self.status.value,
            "result": self.result,
            "sources": self.sources,
            "constraints": self.constraints,
            "deliverables": self.deliverables,
            "progress": round(self.progress, 3),
            "current_step": self.current_step,
            "trigger_source": self.trigger_source,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "output_count": len(self.outputs),
            "metadata": self.metadata,
        }


class GoalRunner:
    """Goal 运行器"""

    def __init__(self):
        self.goals: Dict[str, GoalDefinition] = {}
        self.handlers: Dict[str, Callable] = {}
        self.metrics: Dict[str, int] = {"total": 0, "completed": 0, "failed": 0}

    def create(
        self,
        name: str,
        result: str,
        sources: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        deliverables: Optional[List[str]] = None,
        deadline: float = 0.0,
        priority: str = "medium",
        tags: Optional[List[str]] = None,
        trigger_source: str = "manual",
        trigger_metadata: Optional[Dict[str, Any]] = None,
    ) -> GoalDefinition:
        goal = GoalDefinition(
            name=name,
            result=result,
            sources=sources or [],
            constraints=constraints or [],
            deliverables=deliverables or [],
            deadline=deadline,
            priority=priority,
            tags=tags or [],
            trigger_source=trigger_source,
            trigger_metadata=trigger_metadata or {},
            created_at=time.time(),
        )
        self.goals[goal.goal_id] = goal
        self.metrics["total"] += 1
        logger.info(f"Goal created: {name} [{goal.goal_id}] trigger={trigger_source}")
        return goal

    def register_handler(self, action: str, handler: Callable):
        self.handlers[action] = handler

    async def execute(self, goal: GoalDefinition) -> GoalDefinition:
        """执行 Goal"""
        goal.status = GoalStatus.IN_PROGRESS
        goal.started_at = time.time()
        try:
            # 简化: 模拟执行步骤
            steps = ["收集来源数据", "应用约束", "产出可交付物", "验证"]
            for i, step in enumerate(steps):
                goal.current_step = step
                goal.progress = (i + 1) / len(steps)
                await asyncio.sleep(0.1)
            # 调用 handler (如果有)
            for action, handler in self.handlers.items():
                if asyncio.iscoroutinefunction(handler):
                    output = await handler(goal)
                else:
                    output = handler(goal)
                goal.outputs.append({"action": action, "output": str(output)[:500]})
            goal.status = GoalStatus.COMPLETED
            goal.completed_at = time.time()
            goal.progress = 1.0
            self.metrics["completed"] += 1
        except Exception as e:
            goal.status = GoalStatus.FAILED
            goal.completed_at = time.time()
            self.metrics["failed"] += 1
            logger.exception(f"Goal {goal.goal_id} failed: {e}")
        return goal

    def get(self, goal_id: str) -> Optional[GoalDefinition]:
        return self.goals.get(goal_id)

    def list(
        self,
        status: Optional[GoalStatus] = None,
        trigger_source: Optional[str] = None,
    ) -> List[GoalDefinition]:
        goals = list(self.goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        if trigger_source:
            goals = [g for g in goals if g.trigger_source == trigger_source]
        return goals

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_goals": self.metrics["total"],
            "completed": self.metrics["completed"],
            "failed": self.metrics["failed"],
            "active": sum(1 for g in self.goals.values() if g.status == GoalStatus.IN_PROGRESS),
            "by_status": {s.value: sum(1 for g in self.goals.values() if g.status == s) for s in GoalStatus},
            "by_trigger": {t: sum(1 for g in self.goals.values() if g.trigger_source == t) for t in set(g.trigger_source for g in self.goals.values())},
        }


goal_runner = GoalRunner()


# ===== Webhook =====
@dataclass
class WebhookEvent:
    """Webhook 事件"""

    event_id: str = field(default_factory=lambda: f"we-{uuid.uuid4().hex[:10]}")
    source: str = ""  # "github" | "notion" | "telegram" | ...
    event_type: str = ""  # "pr.opened" | "issue.created" | ...
    payload: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    received_at: float = 0.0
    processed: bool = False
    goal_id: str = ""  # 关联的 Goal


@dataclass
class WebhookEndpoint:
    """Webhook 端点 — URL → Goal 模板"""

    path: str  # "/api/v1/webhook/github"
    name: str
    source: str
    event_type: str = "*"  # 监听的事件类型, * = 全部
    goal_template: Dict[str, Any] = field(default_factory=dict)
    # 自动从 payload 提取 goal 参数
    extract: Dict[str, str] = field(default_factory=dict)  # payload_key → goal_field
    enabled: bool = True
    description: str = ""
    auth_token: str = ""  # 简单 token 鉴权
    created_at: float = 0.0
    event_count: int = 0


class WebhookServer:
    """Webhook 服务器 (内存版)"""

    def __init__(self):
        self.endpoints: Dict[str, WebhookEndpoint] = {}
        self.events: List[WebhookEvent] = []
        self._lock = False

    def register_endpoint(
        self,
        path: str,
        name: str,
        source: str,
        event_type: str = "*",
        goal_template: Optional[Dict[str, Any]] = None,
        extract: Optional[Dict[str, str]] = None,
        auth_token: str = "",
        description: str = "",
    ) -> WebhookEndpoint:
        ep = WebhookEndpoint(
            path=path,
            name=name,
            source=source,
            event_type=event_type,
            goal_template=goal_template or {},
            extract=extract or {},
            auth_token=auth_token,
            description=description,
            created_at=time.time(),
        )
        self.endpoints[path] = ep
        logger.info(f"Webhook endpoint registered: {path} -> {name} ({source})")
        return ep

    def unregister(self, path: str) -> bool:
        if path in self.endpoints:
            del self.endpoints[path]
            return True
        return False

    async def receive(
        self,
        path: str,
        payload: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """接收 webhook"""
        ep = self.endpoints.get(path)
        if not ep:
            return {"success": False, "error": f"endpoint not found: {path}"}
        if not ep.enabled:
            return {"success": False, "error": "endpoint disabled"}
        # 鉴权
        if ep.auth_token:
            token = (headers or {}).get("authorization", "").replace("Bearer ", "")
            if token != ep.auth_token:
                return {"success": False, "error": "unauthorized"}
        # 事件类型匹配
        event_type = payload.get("event_type", payload.get("type", "unknown"))
        if ep.event_type != "*" and event_type != ep.event_type:
            return {"success": False, "error": f"event type mismatch: {event_type}"}
        # 构造 Goal
        goal_params = dict(ep.goal_template)
        for payload_key, goal_field in ep.extract.items():
            if payload_key in payload:
                goal_params[goal_field] = payload[payload_key]
        # 创建 Goal
        goal = goal_runner.create(
            name=ep.goal_template.get("name", f"webhook_{ep.name}"),
            result=goal_params.get("result", ""),
            sources=goal_params.get("sources", []),
            constraints=goal_params.get("constraints", []),
            deliverables=goal_params.get("deliverables", []),
            priority=goal_params.get("priority", "medium"),
            tags=goal_params.get("tags", []) + [f"webhook:{ep.source}"],
            trigger_source="webhook",
            trigger_metadata={"endpoint": path, "event_type": event_type, "payload_keys": list(payload.keys())},
        )
        # 记录事件
        event = WebhookEvent(
            source=ep.source,
            event_type=event_type,
            payload=payload,
            headers=headers or {},
            received_at=time.time(),
            goal_id=goal.goal_id,
        )
        self.events.append(event)
        ep.event_count += 1
        logger.info(f"Webhook {path} received -> Goal {goal.goal_id}")
        return {
            "success": True,
            "event_id": event.event_id,
            "goal_id": goal.goal_id,
            "goal_name": goal.name,
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_endpoints": len(self.endpoints),
            "total_events": len(self.events),
            "by_source": {ep.source: ep.event_count for ep in self.endpoints.values()},
        }


webhook_server = WebhookServer()


# ===== 看板 =====
class BoardStatus(str, Enum):
    """看板列状态"""
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    BLOCKED = "blocked"
    DONE = "done"


@dataclass
class BoardItem:
    """看板项"""

    title: str
    item_id: str = field(default_factory=lambda: f"bi-{uuid.uuid4().hex[:10]}")
    description: str = ""
    status: BoardStatus = BoardStatus.BACKLOG
    assignee: str = ""  # bot or user
    priority: str = "medium"
    due_at: float = 0.0
    tags: List[str] = field(default_factory=list)
    related_goal_id: str = ""
    related_matter_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    history: List[Dict[str, Any]] = field(default_factory=list)

    def move_to(self, new_status: BoardStatus, by: str = ""):
        old = self.status
        self.status = new_status
        self.history.append(
            {"action": "move", "from": old.value, "to": new_status.value, "by": by, "ts": time.time()}
        )
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assignee": self.assignee,
            "priority": self.priority,
            "due_at": self.due_at,
            "tags": self.tags,
            "related_goal_id": self.related_goal_id,
            "related_matter_id": self.related_matter_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BoardColumn:
    """看板列"""

    def __init__(self, status: BoardStatus, name: str = "", wip_limit: int = 0):
        self.status = status
        self.name = name or status.value
        self.wip_limit = wip_limit  # 0 = 无限制
        self.items: List[BoardItem] = []

    def add(self, item: BoardItem):
        if self.wip_limit > 0 and len(self.items) >= self.wip_limit:
            raise ValueError(f"WIP limit reached for column {self.name} (limit {self.wip_limit})")
        item.status = self.status
        self.items.append(item)

    def remove(self, item_id: str) -> bool:
        for i, item in enumerate(self.items):
            if item.item_id == item_id:
                self.items.pop(i)
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "name": self.name,
            "wip_limit": self.wip_limit,
            "item_count": len(self.items),
            "items": [i.to_dict() for i in self.items],
        }


class Board:
    """看板 — 任务状态可视化"""

    def __init__(self, name: str = "main"):
        self.name = name
        self.columns: Dict[BoardStatus, BoardColumn] = {}
        # 默认 6 列
        for s in BoardStatus:
            self.columns[s] = BoardColumn(s)

    def add_item(
        self,
        title: str,
        description: str = "",
        status: BoardStatus = BoardStatus.BACKLOG,
        assignee: str = "",
        priority: str = "medium",
        due_at: float = 0.0,
        tags: Optional[List[str]] = None,
        related_goal_id: str = "",
        related_matter_id: str = "",
    ) -> BoardItem:
        item = BoardItem(
            title=title,
            description=description,
            assignee=assignee,
            priority=priority,
            due_at=due_at,
            tags=tags or [],
            related_goal_id=related_goal_id,
            related_matter_id=related_matter_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        col = self.columns[status]
        col.add(item)
        return item

    def move_item(self, item_id: str, new_status: BoardStatus, by: str = "") -> bool:
        for col in self.columns.values():
            if col.remove(item_id):
                item_idx = None
                for col2 in self.columns.values():
                    for i, it in enumerate(col2.items):
                        if it.item_id == item_id:
                            item_idx = (col2, i)
                            break
                # 找原 item
                item = None
                for col2 in self.columns.values():
                    for it in col2.items:
                        if it.item_id == item_id:
                            item = it
                            break
                if item is None:
                    # 重新构造
                    pass
                # 实际更简单: 重建
                for col2 in list(self.columns.values()):
                    for it in col2.items:
                        if it.item_id == item_id:
                            item = it
                            col2.items.remove(it)
                            break
                    if item:
                        break
                if item:
                    item.move_to(new_status, by)
                    self.columns[new_status].items.append(item)
                return True
        return False

    def get(self, item_id: str) -> Optional[BoardItem]:
        for col in self.columns.values():
            for it in col.items:
                if it.item_id == item_id:
                    return it
        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "by_status": {s.value: len(self.columns[s].items) for s in BoardStatus},
            "total": sum(len(c.items) for c in self.columns.values()),
            "blocked": len(self.columns[BoardStatus.BLOCKED].items),
            "in_progress": len(self.columns[BoardStatus.IN_PROGRESS].items),
            "done": len(self.columns[BoardStatus.DONE].items),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "columns": [c.to_dict() for c in self.columns.values()],
            "stats": self.get_stats(),
        }
