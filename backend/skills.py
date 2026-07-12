#!/usr/bin/env python3
"""
Nanobot Factory - Skills (V5.1 规格层)

⚠️ 物理文件 ``backend/skills.py`` 与同名 package ``backend/skills/`` 同时存在,
   Python 优先解析后者,因此本文件**不会被 import** (它是源副本/参考)。

要使用 ``SkillSpec`` / ``Skill``:
    from backend.skills import SkillSpec, Skill

完整 V5.1 文档:
  * Skill dataclass    — backend/skills.py         (本文件,含 SkillSpec)
  * 50 builtin         — backend/skills_builtin.py
  * SkillRegistry      — backend/skills_manager.py (追加)
  * SkillExecutor      — backend/external_skills.py (追加)

@author MiniMax Agent
@date 2026-07-02
@task P19 v5.1-B
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillSpec:
    """
    V5.1 附录 D — Skill 规格描述

    与 ``backend.skills.legacy.SkillInput/SkillOutput`` 不同,这里只描述
    元数据/接口契约,不涉及具体执行逻辑。便于 registry / executor / builtin
    工厂统一管理。

    Fields:
        id: 全局唯一标识,例如 ``skill_crawl_web``
        name: 中英双语友好名称
        category: 分类标签 (crawl/clean/agent/octo/vida/meta_kim/...)
        trigger_phrases: 触发短语列表 (用于 trigger_match)
        inputs: 输入字段 schema (Dict[str, str], 例如 ``{"url": "string"}``)
        outputs: 输出字段 schema
        description: 中英双语描述
        enabled: 是否启用,默认 True
        version: semver 版本号
        dependencies: 依赖的其它 Skill id 列表
    """
    id: str
    name: str
    category: str
    trigger_phrases: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    enabled: bool = True
    version: str = "1.0.0"
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "trigger_phrases": list(self.trigger_phrases),
            "inputs": dict(self.inputs),
            "outputs": dict(self.outputs),
            "description": self.description,
            "enabled": self.enabled,
            "version": self.version,
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillSpec":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            category=data.get("category", "general"),
            trigger_phrases=list(data.get("trigger_phrases", [])),
            inputs=dict(data.get("inputs", {})),
            outputs=dict(data.get("outputs", {})),
            description=data.get("description", ""),
            enabled=bool(data.get("enabled", True)),
            version=data.get("version", "1.0.0"),
            dependencies=list(data.get("dependencies", [])),
        )


# Alias: 任务要求 class 名 `Skill`,但已有 SkillManager, 为避免冲突,
# 默认导出 SkillSpec 作为 Skill 的等价物(同一 dataclass)
Skill = SkillSpec


__all__ = ["SkillSpec", "Skill"]
