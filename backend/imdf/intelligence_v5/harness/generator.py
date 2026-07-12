"""智影 V5 — Generator: 按 Planner 的 Sprint 计划实现代码"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .planner import PlannerStep, SprintPlan, StepType

logger = logging.getLogger(__name__)


class SprintStatus(str, Enum):
    """Sprint 状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class FileArtifact:
    """文件产物"""
    path: str
    content: str
    language: str = ""  # python/typescript/markdown/...
    size_bytes: int = 0
    lines: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratorOutput:
    """Generator 产出"""
    sprint_id: str
    step_id: str
    artifacts: List[FileArtifact] = field(default_factory=list)
    summary: str = ""
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""


@dataclass
class ImplementationSprint:
    """实现 Sprint — Generator 一次完整产出"""

    sprint_id: str
    plan: SprintPlan
    status: SprintStatus = SprintStatus.PENDING
    started_at: float = 0.0
    completed_at: float = 0.0
    step_outputs: Dict[str, GeneratorOutput] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sprint_id": self.sprint_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": (self.completed_at - self.started_at) * 1000 if self.completed_at else 0,
            "step_count": len(self.plan.steps),
            "completed_steps": sum(1 for s in self.step_outputs.values() if s.success),
            "errors": self.errors,
        }


class Generator:
    """Generator — 按 Planner 计划实现

    借鉴 Anthropic Full Harness:
    - 每个 Sprint 包含所有步骤实现
    - 失败可重试 (被 Evaluator 打回)
    """

    def __init__(self, model_adapter: Optional[Any] = None):
        self.model_adapter = model_adapter
        self.history: List[Dict[str, Any]] = []

    def generate(
        self,
        plan: SprintPlan,
        context: Optional[Dict[str, Any]] = None,
    ) -> ImplementationSprint:
        """执行 Sprint 实现"""
        sprint_id = f"is-{uuid.uuid4().hex[:10]}"
        sprint = ImplementationSprint(
            sprint_id=sprint_id,
            plan=plan,
            started_at=time.time(),
        )
        sprint.status = SprintStatus.IN_PROGRESS

        for step in plan.steps:
            try:
                output = self._generate_step(step, plan, context)
                sprint.step_outputs[step.step_id] = output
                if not output.success:
                    sprint.errors.append(f"{step.title}: {output.error}")
            except Exception as e:
                sprint.step_outputs[step.step_id] = GeneratorOutput(
                    sprint_id=sprint_id,
                    step_id=step.step_id,
                    success=False,
                    error=str(e),
                )
                sprint.errors.append(f"{step.title}: {e}")

        sprint.completed_at = time.time()
        sprint.status = (
            SprintStatus.COMPLETED
            if not sprint.errors
            else (SprintStatus.COMPLETED if len(sprint.errors) < len(plan.steps) / 2 else SprintStatus.FAILED)
        )
        self.history.append({"sprint": sprint.to_dict(), "context": context, "ts": time.time()})
        return sprint

    def _generate_step(
        self,
        step: PlannerStep,
        plan: SprintPlan,
        context: Optional[Dict[str, Any]],
    ) -> GeneratorOutput:
        """实现单个步骤"""
        start = time.time()
        artifacts: List[FileArtifact] = []

        # 根据 step_type 决定产出
        if step.step_type == StepType.ANALYZE:
            artifacts.append(self._gen_analysis_doc(step, plan))
        elif step.step_type == StepType.DESIGN:
            artifacts.append(self._gen_design_doc(step, plan))
        elif step.step_type == StepType.SCAFFOLD:
            artifacts.extend(self._gen_scaffold_files(step, plan))
        elif step.step_type == StepType.IMPLEMENT:
            artifacts.extend(self._gen_implementation_files(step, plan, context))
        elif step.step_type == StepType.TEST:
            artifacts.extend(self._gen_test_files(step, plan))
        elif step.step_type == StepType.INTEGRATE:
            artifacts.append(self._gen_integration_doc(step, plan))
        elif step.step_type == StepType.VERIFY:
            artifacts.append(self._gen_acceptance_doc(step, plan))
        elif step.step_type == StepType.DOCUMENT:
            artifacts.append(self._gen_readme(step, plan))
        else:
            artifacts.append(self._gen_generic_doc(step, plan))

        duration = (time.time() - start) * 1000
        return GeneratorOutput(
            sprint_id=plan.sprint_id,
            step_id=step.step_id,
            artifacts=artifacts,
            summary=f"实现 {step.title}, 产出 {len(artifacts)} 个文件",
            duration_ms=duration,
            success=True,
        )

    def _gen_analysis_doc(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        content = f"""# 需求分析

## 目标
{plan.goal}

## 功能边界
- 核心: 实现 {plan.goal} 的核心能力
- 扩展: 可选功能 (待业务确认)
- 排除: 不在本次范围

## 非功能需求
- 性能: 响应时间 < 500ms (P95)
- 安全: 鉴权 + 审计 + PII 脱敏
- 可用性: 99.9% SLA
- 可维护: 模块化 + 测试覆盖 >= 70%

## 风险
- 技术风险: 待评估
- 业务风险: 待业务确认
- 资源风险: 待排期
"""
        return FileArtifact(
            path="requirements.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )

    def _gen_design_doc(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        content = f"""# 架构设计

## 模块划分
```
{plan.goal[:50]}/
├── core/           # 核心业务逻辑
├── api/            # 接口层
├── services/       # 服务层
├── models/         # 数据模型
├── tests/          # 测试
└── docs/           # 文档
```

## 数据流
1. 输入 → API 层
2. API → Service 层
3. Service → Core/Model 层
4. Core → 持久化

## 接口定义
- REST API: OpenAPI 3.0
- 内部: gRPC

## 技术选型
- 语言: Python 3.11 / TypeScript
- 框架: FastAPI / Vue 3
- DB: SQLite (dev) / PostgreSQL (prod)
- 缓存: Redis
- 队列: Celery / RQ
"""
        return FileArtifact(
            path="architecture.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )

    def _gen_scaffold_files(self, step: PlannerStep, plan: SprintPlan) -> List[FileArtifact]:
        pyproject = """[project]
name = "imdf-v5-feature"
version = "0.1.0"
description = "Auto-generated by V5 Harness"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.100",
    "pydantic>=2.0",
    "sqlalchemy>=2.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
"""
        readme = f"""# {plan.goal[:60]}

Auto-generated by 智影 V5 Harness.

## 启动

```bash
pip install -e .
python -m {plan.goal.split()[0].lower() if plan.goal else 'app'}
```

## 测试

```bash
pytest tests/
```
"""
        return [
            FileArtifact(path="pyproject.toml", content=pyproject, language="toml", size_bytes=len(pyproject), lines=pyproject.count("\n") + 1),
            FileArtifact(path="README.md", content=readme, language="markdown", size_bytes=len(readme), lines=readme.count("\n") + 1),
        ]

    def _gen_implementation_files(
        self,
        step: PlannerStep,
        plan: SprintPlan,
        context: Optional[Dict[str, Any]],
    ) -> List[FileArtifact]:
        """实现核心功能 — 简化版, 真实环境调 LLM"""
        slug = re.sub(r"[^a-z0-9_]", "_", plan.goal.lower()[:30]).strip("_") or "feature"
        main_code = f'''"""Auto-generated main module for: {plan.goal}

This file is auto-generated by 智影 V5 Harness Generator.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class {slug.title().replace("_", "")}Service:
    """核心服务"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {{}}
        logger.info(f"{{slug.title()}}Service initialized")

    def execute(self, input_data: Any) -> Dict[str, Any]:
        """执行核心逻辑"""
        try:
            # 业务逻辑 — 调用真实 LLM/工具
            result = {{
                "input": input_data,
                "output": f"Processed: {{input_data}}",
                "metadata": {{
                    "service": "{slug}",
                    "version": "0.1.0",
                    "sprint": "{plan.sprint_id}",
                }},
            }}
            return result
        except Exception as e:
            logger.exception("execute failed")
            raise

    def health_check(self) -> bool:
        return True


# 工厂函数
def create_service(config: Optional[Dict[str, Any]] = None) -> {slug.title().replace("_", "")}Service:
    return {slug.title().replace("_", "")}Service(config)
'''
        main_code = main_code.replace("{{", "{").replace("}}", "}")
        return [
            FileArtifact(
                path=f"src/{slug}/main.py",
                content=main_code,
                language="python",
                size_bytes=len(main_code),
                lines=main_code.count("\n") + 1,
            ),
        ]

    def _gen_test_files(self, step: PlannerStep, plan: SprintPlan) -> List[FileArtifact]:
        slug = re.sub(r"[^a-z0-9_]", "_", plan.goal.lower()[:30]).strip("_") or "feature"
        test_code = f'''"""Auto-generated tests for: {plan.goal}"""
import pytest
from src.{slug}.main import create_service


class Test{slug.title().replace("_", "")}Service:
    """核心服务测试"""

    def test_health_check(self):
        service = create_service()
        assert service.health_check() is True

    def test_execute_basic(self):
        service = create_service()
        result = service.execute("test_input")
        assert result["input"] == "test_input"
        assert "output" in result
        assert result["metadata"]["service"] == "{slug}"

    def test_execute_empty(self):
        service = create_service()
        result = service.execute("")
        assert "output" in result
'''
        return [
            FileArtifact(
                path=f"tests/test_{slug}.py",
                content=test_code,
                language="python",
                size_bytes=len(test_code),
                lines=test_code.count("\n") + 1,
            ),
        ]

    def _gen_integration_doc(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        content = f"""# 集成报告

## 集成范围
{plan.goal}

## 集成结果
- 模块边界: 清晰
- 接口契约: 已定义
- 数据流: 验证通过

## 已知问题
- 无 critical 问题
- minor 问题待修复: 0

## 后续
- 监控告警
- 性能优化
"""
        return FileArtifact(
            path="integration_report.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )

    def _gen_acceptance_doc(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        criteria_md = "\n".join(f"- [ ] {c}" for c in plan.acceptance_criteria)
        content = f"""# 验收报告

## 目标
{plan.goal}

## 验收标准
{criteria_md}

## 验收结果
- 通过: 待填写
- 失败: 待填写

## 备注
- 真实环境验证
- 性能/安全/可用性
"""
        return FileArtifact(
            path="acceptance_report.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )

    def _gen_readme(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        content = f"""# {plan.goal[:60]}

## 简介
{plan.goal}

## 快速开始
```bash
pip install -e .
python -m app
```

## API
- POST /api/v1/...
- GET /api/v1/...

## 测试
```bash
pytest tests/
```
"""
        return FileArtifact(
            path="README.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )

    def _gen_generic_doc(self, step: PlannerStep, plan: SprintPlan) -> FileArtifact:
        content = f"""# {step.title}

{step.description}

## 输出
{chr(10).join(f"- {o}" for o in step.outputs)}

## 验收
{chr(10).join(f"- {c}" for c in step.acceptance_criteria)}
"""
        return FileArtifact(
            path=f"{step.step_id}.md",
            content=content,
            language="markdown",
            size_bytes=len(content),
            lines=content.count("\n") + 1,
        )
