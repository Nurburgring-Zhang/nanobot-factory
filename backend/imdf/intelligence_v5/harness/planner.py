"""智影 V5 — Planner: 把模糊需求扩展成详细步骤计划"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    """步骤类型"""
    ANALYZE = "analyze"           # 分析需求
    DESIGN = "design"             # 设计
    SCAFFOLD = "scaffold"         # 搭脚手架
    IMPLEMENT = "implement"       # 实现
    TEST = "test"                 # 测试
    INTEGRATE = "integrate"       # 集成
    REVIEW = "review"             # 评审
    DEPLOY = "deploy"             # 部署
    DOCUMENT = "document"         # 文档
    VERIFY = "verify"             # 验证


@dataclass
class PlannerStep:
    """计划步骤"""
    step_id: str = field(default_factory=lambda: f"ps-{uuid.uuid4().hex[:8]}")
    order: int = 0
    title: str = ""
    description: str = ""
    step_type: StepType = StepType.IMPLEMENT
    estimated_minutes: int = 30
    dependencies: List[str] = field(default_factory=list)  # step_ids
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    suggested_bots: List[str] = field(default_factory=list)  # 角色 hints


@dataclass
class SprintPlan:
    """Sprint 计划 — 一个迭代周期"""

    name: str = "Sprint 1"
    sprint_id: str = field(default_factory=lambda: f"sp-{uuid.uuid4().hex[:8]}")
    goal: str = ""
    steps: List[PlannerStep] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    estimated_total_minutes: int = 0

    def add_step(self, step: PlannerStep):
        step.order = len(self.steps) + 1
        self.steps.append(step)
        self.estimated_total_minutes += step.estimated_minutes

    def get_step(self, step_id: str) -> Optional[PlannerStep]:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sprint_id": self.sprint_id,
            "name": self.name,
            "goal": self.goal,
            "steps": [
                {
                    "step_id": s.step_id,
                    "order": s.order,
                    "title": s.title,
                    "description": s.description,
                    "type": s.step_type.value,
                    "estimated_minutes": s.estimated_minutes,
                    "dependencies": s.dependencies,
                    "inputs": s.inputs,
                    "outputs": s.outputs,
                    "acceptance_criteria": s.acceptance_criteria,
                    "suggested_bots": s.suggested_bots,
                }
                for s in self.steps
            ],
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_total_minutes": self.estimated_total_minutes,
        }


class Planner:
    """Planner — 把模糊需求 → 详细步骤计划

    借鉴 Anthropic Full Harness:
    - 需求 → 规格 → 拆 Sprint → 每 Sprint 步骤
    """

    def __init__(self):
        self.history: List[Dict[str, Any]] = []

    def plan(
        self,
        requirement: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SprintPlan:
        """生成 Sprint 计划"""
        req_lower = requirement.lower()
        plan = SprintPlan(name="Sprint 1", goal=requirement)

        # 启发式拆分:根据需求关键词
        steps = self._decompose_requirement(requirement, req_lower)
        for s in steps:
            plan.add_step(s)

        # 全局验收标准
        plan.acceptance_criteria = self._global_acceptance(requirement)

        # 记录历史
        self.history.append({
            "requirement": requirement,
            "context": context,
            "plan": plan.to_dict(),
            "ts": time.time(),
        })
        return plan

    def _decompose_requirement(self, requirement: str, req_lower: str) -> List[PlannerStep]:
        """需求拆分"""
        steps: List[PlannerStep] = []

        # 1. 分析
        steps.append(PlannerStep(
            title="需求分析",
            description=f"理解需求: {requirement[:200]}",
            step_type=StepType.ANALYZE,
            estimated_minutes=15,
            outputs=["requirements.md", "constraints.md"],
            acceptance_criteria=["明确功能边界", "明确非功能需求 (性能/安全/合规)"],
            suggested_bots=["planner", "product_manager"],
        ))

        # 2. 设计
        steps.append(PlannerStep(
            title="架构设计",
            description="设计技术方案: 模块划分 / 数据流 / 接口",
            step_type=StepType.DESIGN,
            estimated_minutes=30,
            dependencies=[steps[0].step_id],
            outputs=["architecture.md", "interface_spec.md"],
            acceptance_criteria=["模块边界清晰", "接口定义完整"],
            suggested_bots=["architect", "planner"],
        ))

        # 3. 脚手架
        steps.append(PlannerStep(
            title="项目脚手架",
            description="搭建项目结构 + 依赖管理 + 配置文件",
            step_type=StepType.SCAFFOLD,
            estimated_minutes=20,
            dependencies=[steps[1].step_id],
            outputs=["package.json", "pyproject.toml", "目录结构"],
            acceptance_criteria=["项目可启动", "依赖可解析"],
            suggested_bots=["developer"],
        ))

        # 4. 实现 — 根据需求类型
        impl_type = self._infer_impl_type(req_lower)
        steps.append(PlannerStep(
            title=f"核心实现 ({impl_type})",
            description=f"实现 {impl_type} 核心功能",
            step_type=StepType.IMPLEMENT,
            estimated_minutes=120,
            dependencies=[steps[2].step_id],
            outputs=["src/...", "tests/..."],
            acceptance_criteria=["核心功能可运行", "代码通过 lint"],
            suggested_bots=["developer", "data_analyst"],
        ))

        # 5. 测试
        steps.append(PlannerStep(
            title="测试用例",
            description="单元测试 + 集成测试 + 端到端测试",
            step_type=StepType.TEST,
            estimated_minutes=60,
            dependencies=[steps[3].step_id],
            outputs=["test_report.md"],
            acceptance_criteria=["测试通过率 >= 90%", "覆盖率 >= 70%"],
            suggested_bots=["qa"],
        ))

        # 6. 集成
        steps.append(PlannerStep(
            title="集成 + 评审",
            description="集成所有模块 + 代码评审 + 文档",
            step_type=StepType.INTEGRATE,
            estimated_minutes=45,
            dependencies=[steps[4].step_id],
            outputs=["integration_report.md", "code_review.md"],
            acceptance_criteria=["集成测试通过", "无 critical 问题"],
            suggested_bots=["developer", "qa", "critic"],
        ))

        # 7. 验证
        steps.append(PlannerStep(
            title="端到端验证",
            description="真实环境验证 + 验收标准检查",
            step_type=StepType.VERIFY,
            estimated_minutes=30,
            dependencies=[steps[5].step_id],
            outputs=["acceptance_report.md"],
            acceptance_criteria=["所有验收标准 met"],
            suggested_bots=["evaluator", "qa"],
        ))

        return steps

    def _infer_impl_type(self, req_lower: str) -> str:
        """推断实现类型"""
        if any(kw in req_lower for kw in ["api", "rest", "graphql", "endpoint", "服务"]):
            return "API 服务"
        if any(kw in req_lower for kw in ["ui", "前端", "页面", "web", "vue", "react"]):
            return "前端组件"
        if any(kw in req_lower for kw in ["爬", "抓", "crawl", "scrap"]):
            return "数据爬虫"
        if any(kw in req_lower for kw in ["数据", "data", "数据库", "db", "sql"]):
            return "数据处理"
        if any(kw in req_lower for kw in ["ai", "agent", "模型", "llm", "训练"]):
            return "AI/Agent 模块"
        if any(kw in req_lower for kw in ["短剧", "视频", "image", "图像", "video", "图片"]):
            return "多模态生成"
        return "通用功能"

    def _global_acceptance(self, requirement: str) -> List[str]:
        """全局验收标准"""
        return [
            f"实现 {requirement[:80]} 的核心功能",
            "代码通过 lint + 类型检查",
            "测试通过率 >= 90%",
            "无 P0/P1 安全问题",
            "有 README + 使用文档",
        ]
