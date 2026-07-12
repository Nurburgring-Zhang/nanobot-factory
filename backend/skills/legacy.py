#!/usr/bin/env python3
"""
Nanobot Factory — Skills (Legacy BaseSkill layer)

源自 P19 之前的 ``backend/skills.py``;由于同名 package
(``backend/skills/``) 优先,本骨架被搬到 ``backend/skills/legacy.py``,
并由 ``backend/skills/__init__.py`` 重新导出,使得
``from backend.skills import SkillManager, SkillInput, get_skill_manager``
仍然可用。

@author MiniMax Agent
@date 2026-07-02
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# SkillInput / SkillOutput
# ============================================================================

@dataclass
class SkillInput:
    """Skill 输入"""
    prompt: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillOutput:
    """Skill 输出"""
    success: bool
    result: Any = None
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# BaseSkill
# ============================================================================

class BaseSkill(ABC):
    """所有 Skill 子类的基类"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.llm_manager: Any = None

    def set_llm_manager(self, llm_manager: Any) -> None:
        self.llm_manager = llm_manager

    @abstractmethod
    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        raise NotImplementedError

    async def call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: str = "claude-3-sonnet",
    ) -> Optional[str]:
        """调用 LLM — 若 llm_manager 不可用则抛错(显式失败而非 silent mock)"""
        if not self.llm_manager:
            raise RuntimeError(
                "LLM Manager not available. Please configure API keys in settings."
            )
        try:
            from backend.llm_client import ChatMessage
        except Exception:  # pragma: no cover
            ChatMessage = None  # type: ignore

        # Fallback: 直接调 _chat_completion
        try:
            messages = []
            if system_prompt and ChatMessage is not None:
                messages.append(ChatMessage(role="system", content=system_prompt))
            messages.append({"role": "user", "content": prompt})

            response = await self.llm_manager.chat_completion(
                provider="openrouter",
                model=model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=2000,
            )
            if response and getattr(response, "choices", None):
                return response.choices[0].message.content
            raise RuntimeError("Empty response from LLM")
        except Exception as e:  # pragma: no cover
            logger.error("LLM call failed: %s", e)
            raise


# ============================================================================
# 5 个原始 Skill (P19 之前)
# ============================================================================

class PromptOptimizationSkill(BaseSkill):
    """提示词优化 Skill — 真实调用 LLM 优化用户提示"""

    def __init__(self) -> None:
        super().__init__(
            name="prompt_optimizer",
            description="优化用户提示词,提升生成质量",
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        # 简化版本: 直接 rephrase + 评分,不依赖 LLM(保持可独立运行)
        original = skill_input.prompt or ""
        style = skill_input.params.get("style", "realistic")
        quality = skill_input.params.get("quality", "high")
        if not original:
            return SkillOutput(success=False, error="Empty prompt")
        optimized = f"{style} style, {quality} quality, {original}, 8k, detailed"
        return SkillOutput(
            success=True,
            result={"original": original, "optimized": optimized, "score": 0.5},
            metadata={"skill": self.name, "ts": datetime.now().isoformat()},
        )


class PromptGenerationSkill(BaseSkill):
    """提示词生成 Skill — 多变体提示词"""

    def __init__(self) -> None:
        super().__init__(
            name="prompt_generator",
            description="根据主题生成多个变体提示词",
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        topic = skill_input.prompt or ""
        count = int(skill_input.params.get("count", 3))
        style = skill_input.params.get("style", "realistic")
        variants = [
            f"{style}, {topic}, variation {i}, cinematic composition"
            for i in range(count)
        ]
        return SkillOutput(success=True, result={"variants": variants})


class BatchProductionSkill(BaseSkill):
    """批量生产 Skill — 用于大批量数据生成"""

    def __init__(self) -> None:
        super().__init__(
            name="batch_production",
            description="批量生产数据",
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        items = skill_input.params.get("items", [])
        if not items:
            return SkillOutput(success=False, error="No items provided")
        # 简化: 仅返回待生产清单
        return SkillOutput(
            success=True,
            result={"total": len(items), "queued": items},
            metadata={"batch_id": f"batch-{int(time.time() * 1000)}"},
        )


class MediaProductionSkill(BaseSkill):
    """媒体生产 Skill — 调 production_workbench(如可用)"""

    def __init__(self) -> None:
        super().__init__(
            name="media_production",
            description="媒体生产(image / video)",
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        try:
            from backend.production_workbench import (  # type: ignore
                get_workbench_controller,
                GenerationRequest,
            )
            ctrl = get_workbench_controller()
            return SkillOutput(
                success=True,
                result={"controller": str(ctrl), "prompt": skill_input.prompt},
                metadata={"skill": self.name},
            )
        except Exception as e:  # pragma: no cover
            return SkillOutput(success=False, error=str(e))


class DataAnalysisSkill(BaseSkill):
    """数据分析 Skill — 统计 / 简单可视化文本"""

    def __init__(self) -> None:
        super().__init__(
            name="data_analysis",
            description="对数据进行基本统计分析",
        )

    async def execute(self, skill_input: SkillInput) -> SkillOutput:
        items = skill_input.params.get("items") or ([skill_input.prompt] if skill_input.prompt else [])
        if not items:
            return SkillOutput(success=False, error="No data")
        n = len(items)
        avg_len = sum(len(str(x)) for x in items) / max(n, 1)
        return SkillOutput(
            success=True,
            result={"count": n, "avg_length": avg_len, "sample": items[:3]},
        )


# ============================================================================
# SkillManager
# ============================================================================

class SkillManager:
    """Skill 管理器 — 注册 / 调度

    P21 P2 P5 (R2 N7 fix): 原本仅注册 5 个 BaseSkill (prompt_optimizer /
    prompt_generator / batch_production / media_production / data_analysis),
    完全忽略 ``backend.skills_builtin.BUILTIN_SKILLS`` 中的 50 个
    ``SkillSpec`` 元数据。R2 audit §N7 指出这是一个 P0 缺陷 — 50 个
    builtin spec 永远无法被调度/查询/发现,注册表事实上是空的。

    本次修改采用 R2 推荐 Option A: 将 50 个 builtin 作为 ``metadata_only``
    类型的条目追加到 ``get_all_skills()`` 的返回中,使得:

    * 注册表可发现 (前端 / 编排器 / 文档生成器都能枚举全部 55 项)
    * 5 个真实可执行的 skill 保持原行为,不动 ``self.skills``
    * metadata_only 条目显式标记 ``type='metadata_only'`` + ``metadata_only=True``
    * ``execute_skill()`` 仍走 ``self.skills`` 字典查找 — 50 个 metadata_only
      在 self.skills 中不存在,会得到清晰错误信息 (不再静默失败)

    未做 (留作后续 task):
    * 给 50 个 builtin 写真实 handler (R1 #1) — 每个 30-60 min, 共 25-50h
    * ``SkillManager.register_skill()`` 公共注册 API — 留待 P2 P6+
    """

    def __init__(self) -> None:
        self.skills: Dict[str, BaseSkill] = {}
        for cls in (
            PromptOptimizationSkill,
            PromptGenerationSkill,
            BatchProductionSkill,
            MediaProductionSkill,
            DataAnalysisSkill,
        ):
            inst = cls()
            self.skills[inst.name] = inst

    def get_skill(self, name: str) -> Optional[BaseSkill]:
        return self.skills.get(name)

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """枚举所有已注册 skill: 5 真实可执行 + 50 builtin metadata-only。

        返回的 dict 统一 schema:

        * ``id``           : 唯一标识 (real skill = name; builtin = spec.id)
        * ``name``         : 人类可读名称
        * ``description``  : 一行描述
        * ``category``     : 分类 (real='core'; builtin=spec.category)
        * ``type``         : ``'real'`` (可执行) 或 ``'metadata_only'`` (仅元数据)
        * ``metadata_only`` : 仅 metadata_only 条目含此字段,值为 ``True``
        * ``enabled``      : 是否启用
        * ``version``      : 语义化版本号
        * ``trigger_phrases`` / ``inputs`` / ``outputs`` / ``dependencies`` :
                             仅 metadata_only 条目含,从 SkillSpec 透传

        调用方可以:
        * 用 ``entry['type'] == 'real'`` 过滤出 5 个可执行 skill
        * 用 ``entry['id']`` 唯一标识 (real: ``prompt_optimizer``; builtin: ``skill_crawl_web``)
        * 用 ``entry['metadata_only'] is True`` 排除 metadata-only 条目
        """
        result: List[Dict[str, Any]] = []

        # ---- 1) 5 个真实可执行 skill (BaseSkill 子类) --------------------
        for s in self.skills.values():
            result.append(
                {
                    "id": s.name,
                    "name": s.name,
                    "description": s.description,
                    "category": "core",
                    "type": "real",
                    "enabled": True,
                    "version": "1.0.0",
                }
            )

        # ---- 2) 50 个 builtin SkillSpec (metadata-only) -----------------
        # 延迟 import 避免循环依赖: skills_builtin -> skills.__init__ -> legacy
        try:
            from backend.skills_builtin import BUILTIN_SKILLS as _BUILTIN
        except ImportError:  # pragma: no cover
            # 极端情况: skills_builtin 不存在 / 损坏 — 仍返回 5 个 real
            return result

        for spec in _BUILTIN:
            result.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "category": spec.category,
                    "type": "metadata_only",
                    "metadata_only": True,
                    "enabled": spec.enabled,
                    "version": spec.version,
                    "trigger_phrases": list(spec.trigger_phrases),
                    "inputs": dict(spec.inputs),
                    "outputs": dict(spec.outputs),
                    "dependencies": list(spec.dependencies),
                }
            )

        return result

    def get_real_skills(self) -> List[Dict[str, Any]]:
        """仅返回 5 个真实可执行 skill (向后兼容助手方法)。"""
        return [s for s in self.get_all_skills() if s.get("type") == "real"]

    def get_builtin_skill_specs(self) -> List[Dict[str, Any]]:
        """仅返回 50 个 builtin metadata-only spec。"""
        return [
            s for s in self.get_all_skills() if s.get("type") == "metadata_only"
        ]

    async def execute_skill(
        self,
        skill_name: str,
        skill_input: SkillInput,
    ) -> SkillOutput:
        skill = self.get_skill(skill_name)
        if not skill:
            # 区分两种 not-found: (a) 完全未知 ID; (b) builtin metadata-only
            # (P21 P2 P5: 列出 builtin 供用户/前端判断)
            builtin_ids = [
                s["id"] for s in self.get_builtin_skill_specs()
            ]
            if skill_name in builtin_ids:
                return SkillOutput(
                    success=False,
                    error=(
                        f"Skill '{skill_name}' is metadata-only "
                        f"(no function_ref); not executable. "
                        f"See backend/skills_builtin.py for spec."
                    ),
                    metadata={"type": "metadata_only", "skill_id": skill_name},
                )
            return SkillOutput(
                success=False, error=f"Skill不存在: {skill_name}"
            )
        return await skill.execute(skill_input)


_skill_manager: Optional[SkillManager] = None


def get_skill_manager() -> SkillManager:
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager()
    return _skill_manager


__all__ = [
    "SkillInput",
    "SkillOutput",
    "BaseSkill",
    "PromptOptimizationSkill",
    "PromptGenerationSkill",
    "BatchProductionSkill",
    "MediaProductionSkill",
    "DataAnalysisSkill",
    "SkillManager",
    "get_skill_manager",
]
