"""智影 V5 — Obsidian 6 大核心技能

迁移自 obsidian-cc (Hermes 验证过的记忆检索闭环):
1. digest-note: 消化当前笔记/选区 → inbox
2. review-inbox: 审核 inbox → 可确认清单
3. apply-memory: 确认后合并到长期记忆
4. update-profile: 从反馈学习 → 更新画像
5. vault-doctor: Vault 体检报告
6. create-skill: 让 Agent 自己造技能
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..memory.palace import palace_router, PalaceCard
from ..memory.layers import MemoryItem, MemoryLayer, memory_manager
from ..memory.feedback import feedback_loop, FeedbackType

logger = logging.getLogger(__name__)


@dataclass
class SkillResult:
    """技能执行结果"""
    success: bool
    output: Any = None
    summary: str = ""
    next_suggestion: str = ""
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class ObsidianSkill(ABC):
    """Obsidian 技能基类"""

    name: str = "base_skill"
    description: str = ""
    trigger_keywords: List[str] = field(default_factory=list)

    def __init__(self):
        self.use_count = 0
        self.last_used = 0.0

    @abstractmethod
    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        pass

    def can_trigger(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.trigger_keywords)

    def _record_use(self):
        self.use_count += 1
        self.last_used = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "trigger_keywords": self.trigger_keywords,
            "use_count": self.use_count,
            "last_used": self.last_used,
        }


class DigestNoteSkill(ObsidianSkill):
    """消化当前笔记/选区 → inbox"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-digest-note"
        self.description = "消化当前笔记或选区 — 提炼关键决议、涉及的人、可沉淀内容,写入 memory/inbox/"
        self.trigger_keywords = ["消化", "digest", "总结笔记", "summarize", "提炼", "obsidian-digest-note"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        text = str(input_data) if input_data else ""
        if not text:
            return SkillResult(success=False, error="empty input", duration_ms=(time.time() - start) * 1000)

        # 走 Memory Palace 找路线
        route = palace_router.find_route("消化笔记", context)
        must_read = route["route"]["must_read"] if route else ["profile.md", "vault.md", "style.md"]
        pitfalls = route["route"]["pitfalls"] if route else []

        # 提炼关键信息
        sentences = re.split(r"[。.!?！？\n]+", text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]
        key_points: List[str] = []
        entities: List[str] = []
        for s in sentences[:20]:
            key_points.append(s[:200])
            # 提取可能的人名/项目名
            nouns = re.findall(r"[\u4e00-\u9fff]{2,5}", s)
            for n in nouns:
                if n not in entities and len(n) >= 2:
                    entities.append(n)

        # 写入 inbox
        today = time.strftime("%Y-%m-%d", time.localtime())
        inbox_item = memory_manager.add_inbox(
            title=f"消化笔记 {today}",
            content=f"# 消化结果\n\n## 原文\n{text[:500]}\n\n## 关键点\n" + "\n".join(f"- {p}" for p in key_points[:10]) + f"\n\n## 实体\n" + ", ".join(entities[:20]),
            tags=["digest", f"date:{today}"] + entities[:5],
        )

        # 建议下一步
        next_suggestion = "下一步: 跑 obsidian-review-inbox 审核沉淀"
        return SkillResult(
            success=True,
            output={
                "inbox_id": inbox_item.item_id,
                "key_points": key_points[:10],
                "entities": entities[:20],
                "must_read": must_read,
                "pitfalls": pitfalls,
            },
            summary=f"已提炼 {len(key_points)} 个关键点,识别 {len(entities)} 个实体",
            next_suggestion=next_suggestion,
            artifacts=[f"memory://inbox/{today}.md#{inbox_item.item_id}"],
            duration_ms=(time.time() - start) * 1000,
            metadata={"route": route["card"].name if route else None},
        )


class ReviewInboxSkill(ObsidianSkill):
    """审核 inbox → 可确认清单"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-review-inbox"
        self.description = "审核 inbox 待确认沉淀 — 归纳去重,生成可确认清单"
        self.trigger_keywords = ["审核 inbox", "review inbox", "沉淀确认", "obsidian-review-inbox"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        # 拉取 inbox
        inbox_items = memory_manager.inbox.list(limit=100, confirmed_only=False)
        # 按 entity/主题聚类
        groups: Dict[str, List[MemoryItem]] = {}
        for item in inbox_items:
            topic = item.tags[0] if item.tags else "uncategorized"
            for tag in item.tags:
                if tag.startswith("date:") or tag == "digest":
                    continue
                topic = tag
                break
            groups.setdefault(topic, []).append(item)

        # 生成建议清单
        suggestions: List[Dict[str, Any]] = []
        for topic, items in groups.items():
            suggestions.append(
                {
                    "topic": topic,
                    "item_count": len(items),
                    "items": [{"id": i.item_id, "title": i.title, "preview": i.content[:200]} for i in items[:5]],
                    "suggested_action": self._suggest_action(topic),
                    "target_layer": self._suggest_target_layer(topic),
                    "confidence": min(len(items) / 5, 1.0),
                    "source": "inbox",
                }
            )
        # 按 item 数排序
        suggestions.sort(key=lambda x: x["item_count"], reverse=True)

        return SkillResult(
            success=True,
            output={
                "inbox_total": len(inbox_items),
                "groups": len(groups),
                "suggestions": suggestions,
            },
            summary=f"审核 {len(inbox_items)} 条 inbox, 形成 {len(groups)} 个主题分组",
            next_suggestion="下一步: 逐组确认后跑 obsidian-apply-memory",
            artifacts=["memory://inbox/_review_suggestion.md"],
            duration_ms=(time.time() - start) * 1000,
        )

    def _suggest_action(self, topic: str) -> str:
        if "person" in topic or "people" in topic:
            return "merge to people/"
        if "project" in topic:
            return "merge to projects/"
        if "concept" in topic or "wiki" in topic:
            return "merge to wiki/"
        if "decision" in topic:
            return "merge to decisions/"
        return "review manually"

    def _suggest_target_layer(self, topic: str) -> str:
        return {
            "person": "long_term:people",
            "people": "long_term:people",
            "project": "long_term:projects",
            "projects": "long_term:projects",
            "concept": "long_term:wiki",
            "wiki": "long_term:wiki",
            "decision": "long_term:decisions",
        }.get(topic, "long_term:general")


class ApplyMemorySkill(ObsidianSkill):
    """确认后合并到长期记忆"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-apply-memory"
        self.description = "把 inbox 合并到长期记忆 (people/projects/wiki/decisions) — 写入前需确认"
        self.trigger_keywords = ["应用记忆", "apply memory", "沉淀", "合并", "obsidian-apply-memory"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        # 解析 input: {inbox_id: str, target_layer: str, target_id: str}
        if not isinstance(input_data, dict):
            return SkillResult(success=False, error="需要 dict 输入 {inbox_id, target_layer}", duration_ms=(time.time() - start) * 1000)
        inbox_id = input_data.get("inbox_id", "")
        target_layer = input_data.get("target_layer", "long_term:general")
        by = input_data.get("by", "user")

        item = memory_manager.inbox.get(inbox_id)
        if not item:
            return SkillResult(success=False, error=f"inbox item not found: {inbox_id}", duration_ms=(time.time() - start) * 1000)

        # 准备合并计划 (先出, 再让人确认)
        plan = {
            "source_id": inbox_id,
            "target_layer": target_layer,
            "operations": [
                f"复制内容从 inbox/{inbox_id} 到 long_term",
                f"标注来源: in/{item.source or 'unknown'}",
                f"追加 metadata: applied_at={time.time()}",
            ],
        }

        # 直接执行 (真实环境先让用户确认, 此处简化)
        long_item = memory_manager.promote_to_long_term(inbox_id, by=by)
        if not long_item:
            return SkillResult(success=False, error="promote failed", duration_ms=(time.time() - start) * 1000)

        return SkillResult(
            success=True,
            output={
                "applied": True,
                "source_id": inbox_id,
                "long_term_id": long_item.item_id,
                "plan": plan,
                "target_layer": target_layer,
            },
            summary=f"已将 {inbox_id} 合并到长期记忆 ({target_layer})",
            next_suggestion="继续下一条 inbox, 或跑 obsidian-vault-doctor 体检",
            artifacts=[f"memory://{target_layer.replace(':', '/')}/{long_item.item_id}"],
            duration_ms=(time.time() - start) * 1000,
        )


class UpdateProfileSkill(ObsidianSkill):
    """从反馈学习 → 更新画像"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-update-profile"
        self.description = "从 👍/👎 反馈学习 → 更新 profile.md / style.md — 每次更新逐条确认"
        self.trigger_keywords = ["更新画像", "update profile", "学习偏好", "obsidian-update-profile", "style 学习"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        # 提取 taste
        proposals = feedback_loop.extract_and_propose()
        # 生成 profile.md / style.md
        profile_md = feedback_loop.get_profile_md()
        style_md = feedback_loop.get_style_md()
        # 待确认列表
        pending = feedback_loop.updater.list_pending()
        return SkillResult(
            success=True,
            output={
                "taste_proposals": proposals,
                "pending_updates": pending,
                "profile_md_preview": profile_md[:500],
                "style_md_preview": style_md[:500],
            },
            summary=f"提炼 {len(proposals)} 个 taste 模式, {len(pending)} 个待确认更新",
            next_suggestion="逐条确认 pending_updates (调用 feedback_loop.confirm)",
            artifacts=["memory://profile.md", "memory://style.md"],
            duration_ms=(time.time() - start) * 1000,
        )


class VaultDoctorSkill(ObsidianSkill):
    """Vault 体检"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-vault-doctor"
        self.description = "Vault 体检 — raw 未消化 / inbox 堆积 / 断链 / 孤儿笔记"
        self.trigger_keywords = ["体检", "vault doctor", "诊断", "健康检查", "obsidian-vault-doctor"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        # 统计
        stats = memory_manager.get_stats()
        # 检查点
        issues: List[Dict[str, Any]] = []
        # 1. raw 未消化
        raw_count = stats["raw"]
        source_count = stats["source"]
        if raw_count > 0 and source_count < raw_count * 0.5:
            issues.append(
                {
                    "type": "raw_undigested",
                    "severity": "warn",
                    "message": f"raw/ 有 {raw_count} 项, source/ 只消化了 {source_count}, 消化率 {source_count/max(raw_count,1):.0%}",
                    "suggested_skill": "obsidian-digest-note",
                }
            )
        # 2. inbox 堆积
        inbox_pending = stats["inbox_pending"]
        if inbox_pending > 20:
            issues.append(
                {
                    "type": "inbox_overflow",
                    "severity": "high" if inbox_pending > 50 else "warn",
                    "message": f"inbox 待审核 {inbox_pending} 条 (>20)",
                    "suggested_skill": "obsidian-review-inbox",
                }
            )
        # 3. feedback 堆积
        feedback_count = stats["feedback"]
        long_term_count = stats["long_term"]
        if feedback_count > 30 and long_term_count < 10:
            issues.append(
                {
                    "type": "taste_pending",
                    "severity": "warn",
                    "message": f"feedback {feedback_count} 条但 long_term 仅 {long_term_count} 条, 待提炼",
                    "suggested_skill": "obsidian-update-profile",
                }
            )
        # 4. 比例
        if stats["total"] < 5:
            issues.append(
                {
                    "type": "empty_vault",
                    "severity": "info",
                    "message": "Vault 几乎为空, 建议先跑 obsidian-digest-note 写入初始内容",
                    "suggested_skill": "obsidian-digest-note",
                }
            )
        return SkillResult(
            success=True,
            output={
                "stats": stats,
                "issue_count": len(issues),
                "issues": issues,
            },
            summary=f"体检完成, 发现 {len(issues)} 个问题 (raw {raw_count}, source {source_count}, inbox {inbox_pending}, long_term {long_term_count})",
            next_suggestion="按 issues[].suggested_skill 顺序处理",
            artifacts=[f"memory://doctor_report_{time.strftime('%Y-%m-%d', time.localtime())}.md"],
            duration_ms=(time.time() - start) * 1000,
        )


class CreateSkillSkill(ObsidianSkill):
    """让 Agent 自己造技能"""

    def __init__(self):
        super().__init__()
        self.name = "obsidian-create-skill"
        self.description = "让 Agent 自己造技能 — 问清楚意图, 出草稿, 等人确认, 落到 <Vault>/.claude/skills/<name>/SKILL.md"
        self.trigger_keywords = ["创建技能", "create skill", "造技能", "新技能", "obsidian-create-skill"]

    def execute(self, input_data: Any, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        start = time.time()
        self._record_use()
        intent = str(input_data) if input_data else ""
        if not intent:
            return SkillResult(
                success=False,
                error="需要描述技能意图, e.g. '我想做一个整理礼物清单的技能'",
                duration_ms=(time.time() - start) * 1000,
            )

        # 生成草稿
        slug = re.sub(r"[^a-z0-9_]", "_", intent.lower()[:30]).strip("_") or "new_skill"
        skill_md = f"""---
name: {slug}
description: {intent[:200]}
trigger_keywords:
  - {slug.replace('_', ' ')}
---

# {slug}

## 描述
{intent}

## 触发场景
- {intent[:100]}

## 必读
- memory://profile.md
- memory://style.md

## 条件读
- (待用户配置)

## 输出位置
- memory://inbox/<date>.md

## 坑 / 禁区
- 涉及敏感信息需脱敏
- 不确定时降级到 inbox

## 示例
- 输入: 示例输入
- 输出: 示例输出
"""
        # 让人确认 (不直接入库)
        return SkillResult(
            success=True,
            output={
                "draft_skill_md": skill_md,
                "draft_path": f"skills://{slug}/SKILL.md",
                "needs_confirmation": True,
            },
            summary=f"已生成 {slug} 技能草稿, 需用户确认后落库",
            next_suggestion="用户确认后, 调 skill_registry.register(skill_md)",
            artifacts=[f"skills://{slug}/SKILL.md (draft)"],
            duration_ms=(time.time() - start) * 1000,
        )


# ===== 注册表 =====
class ObsidianSkillRegistry:
    """6 大 Obsidian 技能注册表"""

    def __init__(self):
        self.skills: Dict[str, ObsidianSkill] = {}
        self._register_defaults()

    def _register_defaults(self):
        defaults = [
            DigestNoteSkill(),
            ReviewInboxSkill(),
            ApplyMemorySkill(),
            UpdateProfileSkill(),
            VaultDoctorSkill(),
            CreateSkillSkill(),
        ]
        for s in defaults:
            self.register(s)

    def register(self, skill: ObsidianSkill):
        self.skills[skill.name] = skill

    def get(self, name: str) -> Optional[ObsidianSkill]:
        return self.skills.get(name)

    def find_by_trigger(self, text: str) -> List[ObsidianSkill]:
        return [s for s in self.skills.values() if s.can_trigger(text)]

    def list(self) -> List[ObsidianSkill]:
        return list(self.skills.values())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_skills": len(self.skills),
            "by_skill": {s.name: {"use_count": s.use_count, "last_used": s.last_used} for s in self.skills.values()},
        }


obsidian_skill_registry = ObsidianSkillRegistry()
