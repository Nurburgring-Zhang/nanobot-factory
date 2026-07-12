"""智影 V5 — Bot + AgentCard (Octo 模型)

Bot 不是临时调用的功能按钮,而是有身份、有名片、有能力、有工作履历的数字同事。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BotStatus(str, Enum):
    """Bot 状态"""
    IDLE = "idle"           # 空闲
    BUSY = "busy"           # 处理任务中
    PAUSED = "paused"       # 暂停
    OFFLINE = "offline"     # 离线
    ERROR = "error"         # 错误


class BotRole(str, Enum):
    """Bot 角色分类 — 对接 The Agency 232 角色"""
    PLANNER = "planner"             # 计划 (Harness Planner)
    GENERATOR = "generator"         # 生成 (Harness Generator)
    EVALUATOR = "evaluator"         # 评估 (Harness Evaluator)
    RESEARCHER = "researcher"       # 研究员
    DEVELOPER = "developer"         # 开发者
    DESIGNER = "designer"           # 设计师
    PRODUCT_MANAGER = "product_manager"  # 产品经理
    MARKETER = "marketer"           # 营销
    QA = "qa"                       # 测试
    CRITIC = "critic"               # 审核
    AGGREGATOR = "aggregator"       # MoA 聚合
    DATA_ANALYST = "data_analyst"   # 数据分析
    ARCHITECT = "architect"         # 架构
    OPERATIONS = "operations"       # 运维
    SECURITY = "security"           # 安全
    CUSTOM = "custom"               # 自定义


@dataclass
class Capability:
    """Bot 单项能力"""
    name: str
    description: str = ""
    confidence: float = 1.0  # 0-1
    input_types: List[str] = field(default_factory=list)
    output_types: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass
class AgentCard:
    """Bot 名片 — 公开的能力/归属/履历摘要

    类似 AGENT Card (Anthropic 协议) 扩展:
    - identity: 身份信息
    - capabilities: 能力清单
    - ownership: 归属 (团队/部门/owner)
    - work_history: 工作履历
    - contact: 联系方式
    - performance: 性能指标
    """
    name: str
    role: BotRole
    description: str = ""
    version: str = "1.0.0"
    avatar: str = ""  # emoji or url
    tags: List[str] = field(default_factory=list)

    # 能力
    capabilities: List[Capability] = field(default_factory=list)

    # 归属
    team: str = ""           # 所属团队 (e.g., "数据采集组", "前端开发组")
    department: str = ""     # 所属部门 (e.g., "研发部", "市场部")
    owner: str = ""          # 维护人/创建人

    # 联系
    email: str = ""
    homepage: str = ""

    # 性能指标 (实时更新)
    total_tasks: int = 0
    success_tasks: int = 0
    failed_tasks: int = 0
    avg_duration_ms: float = 0.0
    last_active: float = 0.0

    # 限制
    max_concurrent_tasks: int = 1
    requires_approval_for: List[str] = field(default_factory=list)  # 操作需确认的

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "version": self.version,
            "avatar": self.avatar,
            "tags": self.tags,
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "confidence": c.confidence,
                    "input_types": c.input_types,
                    "output_types": c.output_types,
                    "examples": c.examples,
                }
                for c in self.capabilities
            ],
            "ownership": {
                "team": self.team,
                "department": self.department,
                "owner": self.owner,
            },
            "contact": {
                "email": self.email,
                "homepage": self.homepage,
            },
            "performance": {
                "total_tasks": self.total_tasks,
                "success_tasks": self.success_tasks,
                "failed_tasks": self.failed_tasks,
                "success_rate": round(self.success_tasks / max(self.total_tasks, 1), 3),
                "avg_duration_ms": round(self.avg_duration_ms, 2),
                "last_active": self.last_active,
            },
            "limits": {
                "max_concurrent": self.max_concurrent_tasks,
                "requires_approval_for": self.requires_approval_for,
            },
        }


@dataclass
class Bot:
    """Bot 实例 — 带运行状态 + 实际处理函数"""

    card: AgentCard
    bot_id: str = field(default_factory=lambda: f"bot-{uuid.uuid4().hex[:12]}")
    status: BotStatus = BotStatus.IDLE
    current_tasks: List[str] = field(default_factory=list)  # task ids
    handler: Optional[Callable] = None  # 实际调用函数

    # 运行时
    handler_module: str = ""  # e.g., "imdf.intelligence_v5.platform_agents.workflow"
    handler_method: str = ""  # e.g., "WorkflowAgent.start"

    def update_performance(self, success: bool, duration_ms: float):
        """更新性能指标"""
        self.card.total_tasks += 1
        if success:
            self.card.success_tasks += 1
        else:
            self.card.failed_tasks += 1
        # 指数移动平均
        alpha = 0.3
        if self.card.avg_duration_ms == 0:
            self.card.avg_duration_ms = duration_ms
        else:
            self.card.avg_duration_ms = alpha * duration_ms + (1 - alpha) * self.card.avg_duration_ms
        self.card.last_active = time.time()
        self.card.updated_at = time.time()

    def can_accept_task(self) -> bool:
        return (
            self.status == BotStatus.IDLE
            and len(self.current_tasks) < self.card.max_concurrent_tasks
        )

    def add_task(self, task_id: str) -> bool:
        if not self.can_accept_task():
            return False
        self.current_tasks.append(task_id)
        if self.status == BotStatus.IDLE:
            self.status = BotStatus.BUSY
        return True

    def complete_task(self, task_id: str):
        if task_id in self.current_tasks:
            self.current_tasks.remove(task_id)
        if not self.current_tasks:
            self.status = BotStatus.IDLE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bot_id": self.bot_id,
            "status": self.status.value,
            "current_tasks": self.current_tasks,
            "card": self.card.to_dict(),
        }


class BotRegistry:
    """Bot 注册中心 — 全平台 Bot 统一管理

    借鉴 Octo 思想:Bot 不再是临时功能,而是有身份的数字同事。
    支持:
    - 注册/注销
    - 按 role / capability / team 检索
    - 性能追踪
    - 工作分配 (按 load/role/capability)
    """

    def __init__(self):
        self._bots: Dict[str, Bot] = {}
        self._by_role: Dict[BotRole, List[str]] = {}
        self._by_team: Dict[str, List[str]] = {}
        self._by_capability: Dict[str, List[str]] = {}  # capability_name → bot_ids
        self._lock = False  # 简化:用 GIL 即可

    def register(
        self,
        name: str,
        role: BotRole,
        description: str = "",
        capabilities: Optional[List[Capability]] = None,
        team: str = "",
        department: str = "",
        owner: str = "",
        avatar: str = "",
        tags: Optional[List[str]] = None,
        max_concurrent: int = 1,
        requires_approval_for: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
        handler_module: str = "",
        handler_method: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Bot:
        """注册新 Bot"""
        card = AgentCard(
            name=name,
            role=role,
            description=description,
            capabilities=capabilities or [],
            team=team,
            department=department,
            owner=owner,
            avatar=avatar,
            tags=tags or [],
            max_concurrent_tasks=max_concurrent,
            requires_approval_for=requires_approval_for or [],
            metadata=metadata or {},
            created_at=time.time(),
            updated_at=time.time(),
        )
        bot = Bot(
            card=card,
            handler=handler,
            handler_module=handler_module,
            handler_method=handler_method,
        )
        self._bots[bot.bot_id] = bot
        self._by_role.setdefault(role, []).append(bot.bot_id)
        if team:
            self._by_team.setdefault(team, []).append(bot.bot_id)
        for cap in card.capabilities:
            self._by_capability.setdefault(cap.name, []).append(bot.bot_id)
        logger.info(f"Bot registered: {name} ({role.value}) [{bot.bot_id}]")
        return bot

    def unregister(self, bot_id: str) -> bool:
        if bot_id not in self._bots:
            return False
        bot = self._bots[bot_id]
        # 清理索引
        if bot.bot_id in self._by_role.get(bot.card.role, []):
            self._by_role[bot.card.role].remove(bot.bot_id)
        if bot.card.team and bot.bot_id in self._by_team.get(bot.card.team, []):
            self._by_team[bot.card.team].remove(bot.bot_id)
        for cap in bot.card.capabilities:
            if cap.name in self._by_capability and bot.bot_id in self._by_capability[cap.name]:
                self._by_capability[cap.name].remove(bot.bot_id)
        del self._bots[bot_id]
        return True

    def get_bot(self, bot_id: str) -> Optional[Bot]:
        return self._bots.get(bot_id)

    def list_bots(
        self,
        role: Optional[BotRole] = None,
        team: Optional[str] = None,
        capability: Optional[str] = None,
        status: Optional[BotStatus] = None,
        available_only: bool = False,
    ) -> List[Bot]:
        """列出 Bot — 多维过滤"""
        candidates = list(self._bots.values())
        if role:
            candidates = [b for b in candidates if b.card.role == role]
        if team:
            candidates = [b for b in candidates if b.card.team == team]
        if capability:
            candidates = [b for b in candidates if any(c.name == capability for c in b.card.capabilities)]
        if status:
            candidates = [b for b in candidates if b.status == status]
        if available_only:
            candidates = [b for b in candidates if b.can_accept_task()]
        return candidates

    def find_best_match(
        self,
        capability: str,
        role: Optional[BotRole] = None,
        min_confidence: float = 0.5,
    ) -> Optional[Bot]:
        """找最佳匹配 Bot"""
        candidates = self.list_bots(capability=capability, role=role, available_only=True)
        # 按 confidence + success_rate + load 评分
        scored = []
        for b in candidates:
            cap = next((c for c in b.card.capabilities if c.name == capability), None)
            if not cap or cap.confidence < min_confidence:
                continue
            success_rate = b.card.success_tasks / max(b.card.total_tasks, 1)
            load = len(b.current_tasks) / max(b.card.max_concurrent_tasks, 1)
            score = cap.confidence * 0.4 + success_rate * 0.4 + (1 - load) * 0.2
            scored.append((score, b))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def export_cards(self) -> List[Dict[str, Any]]:
        """导出所有 Bot AgentCard (JSON)"""
        return [b.card.to_dict() for b in self._bots.values()]

    def get_stats(self) -> Dict[str, Any]:
        """注册中心统计"""
        by_role: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for b in self._bots.values():
            by_role[b.card.role.value] = by_role.get(b.card.role.value, 0) + 1
            by_status[b.status.value] = by_status.get(b.status.value, 0) + 1
        return {
            "total_bots": len(self._bots),
            "by_role": by_role,
            "by_status": by_status,
            "by_team": {t: len(bots) for t, bots in self._by_team.items()},
            "by_capability": {c: len(bots) for c, bots in self._by_capability.items()},
        }


# 全局注册中心
bot_registry = BotRegistry()
