"""智影 V5 — Memory Palace (不存知识, 存路线)"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PalaceCard:
    """房间卡 — 一类任务的执行路线

    每张房间卡固定 5 段:
    ## 触发场景
    ## 必读 (按顺序)
    ## 条件读
    ## 输出位置
    ## 坑 / 禁区
    """

    name: str
    trigger_scenarios: List[str] = field(default_factory=list)
    must_read: List[str] = field(default_factory=list)  # 按顺序的文件路径 / memory ids / people ids
    conditional_read: List[str] = field(default_factory=list)  # 触发条件 + 文件
    output_location: str = ""  # 输出到哪里
    pitfalls: List[str] = field(default_factory=list)  # 坑/禁区
    card_id: str = field(default_factory=lambda: f"pc-{uuid.uuid4().hex[:8]}")
    description: str = ""

    # 元数据
    created_at: float = 0.0
    updated_at: float = 0.0
    use_count: int = 0
    last_used: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "trigger_scenarios": self.trigger_scenarios,
            "must_read": self.must_read,
            "conditional_read": self.conditional_read,
            "output_location": self.output_location,
            "pitfalls": self.pitfalls,
            "description": self.description,
            "use_count": self.use_count,
            "last_used": self.last_used,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class PalaceRoom:
    """一个房间 (任务大类)"""

    name: str
    description: str = ""
    room_id: str = field(default_factory=lambda: f"pr-{uuid.uuid4().hex[:8]}")
    cards: Dict[str, PalaceCard] = field(default_factory=dict)
    created_at: float = 0.0

    def add_card(self, card: PalaceCard) -> str:
        self.cards[card.card_id] = card
        return card.card_id

    def remove_card(self, card_id: str) -> bool:
        if card_id in self.cards:
            del self.cards[card_id]
            return True
        return False

    def find_card(self, scenario: str) -> Optional[PalaceCard]:
        """按场景查最匹配 card"""
        scenario_lower = scenario.lower()
        for card in self.cards.values():
            for trig in card.trigger_scenarios:
                if trig.lower() in scenario_lower or scenario_lower in trig.lower():
                    return card
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "room_id": self.room_id,
            "name": self.name,
            "description": self.description,
            "cards": [c.to_dict() for c in self.cards.values()],
            "card_count": len(self.cards),
            "created_at": self.created_at,
        }


class PalaceRouter:
    """Memory Palace 路由器 — 给定任务, 返回执行路线"""

    def __init__(self):
        self.rooms: Dict[str, PalaceRoom] = {}

    def create_room(self, name: str, description: str = "") -> PalaceRoom:
        room = PalaceRoom(
            name=name,
            description=description,
            created_at=time.time(),
        )
        self.rooms[room.room_id] = room
        logger.info(f"Palace room created: {name} [{room.room_id}]")
        return room

    def delete_room(self, room_id: str) -> bool:
        if room_id in self.rooms:
            del self.rooms[room_id]
            return True
        return False

    def get_room(self, room_id: str) -> Optional[PalaceRoom]:
        return self.rooms.get(room_id)

    def find_route(
        self,
        task_description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """根据任务描述, 找到执行路线

        Returns: {
            "card": PalaceCard,
            "route": {
                "must_read": [...],
                "conditional_read": [...],
                "output_location": "...",
                "pitfalls": [...],
            },
            "matched_room": str,
            "match_score": float,
        }
        """
        best_match: Tuple[float, PalaceRoom, PalaceCard] = (0.0, None, None)  # type: ignore
        desc_lower = task_description.lower()
        for room in self.rooms.values():
            for card in room.cards.values():
                score = self._match_score(desc_lower, card)
                if score > best_match[0]:
                    best_match = (score, room, card)
        if best_match[0] < 0.1:
            return None
        score, room, card = best_match
        card.use_count += 1
        card.last_used = time.time()
        return {
            "card": card,
            "room": room,
            "route": {
                "must_read": card.must_read,
                "conditional_read": card.conditional_read,
                "output_location": card.output_location,
                "pitfalls": card.pitfalls,
            },
            "match_score": score,
        }

    def _match_score(self, task_lower: str, card: PalaceCard) -> float:
        """匹配分数 0-1"""
        if not card.trigger_scenarios:
            return 0.0
        matched = 0
        for trig in card.trigger_scenarios:
            t = trig.lower()
            if t in task_lower or task_lower in t:
                matched += 1
            else:
                # token 重叠
                trig_tokens = set(t.split())
                task_tokens = set(task_lower.split())
                if trig_tokens and task_tokens:
                    overlap = len(trig_tokens & task_tokens) / max(len(trig_tokens), 1)
                    if overlap > 0.5:
                        matched += overlap
        return min(matched / max(len(card.trigger_scenarios), 1), 1.0)

    def install_default_palace(self):
        """安装默认的 6 大房间 (obsidian-cc 模式)"""
        # Room 1: digest_note
        r1 = self.create_room("digest_note", "消化笔记/选区 → inbox")
        r1.add_card(PalaceCard(
            name="digest_note",
            description="消化当前笔记或选区",
            trigger_scenarios=["消化笔记", "总结笔记", "digest note", "summarize note", "提炼内容"],
            must_read=[
                "memory://profile.md",
                "memory://vault.md",
                "memory://style.md",
                "current_note",
            ],
            conditional_read=[
                "涉及人 → memory://people/<谁>.md",
                "涉及项目 → memory://projects/<什么>.md",
            ],
            output_location="memory://inbox/<today>.md",
            pitfalls=[
                "不要直接写长期记忆",
                "涉及敏感信息需脱敏",
                "无法理解时降级到 inbox 待人工",
            ],
        ))

        # Room 2: review_inbox
        r2 = self.create_room("review_inbox", "审核 inbox 待确认沉淀")
        r2.add_card(PalaceCard(
            name="review_inbox",
            description="审核 inbox → 可确认清单",
            trigger_scenarios=["审核 inbox", "review inbox", "沉淀确认", "inbox 整理"],
            must_read=[
                "memory://inbox/*",
                "memory://profile.md",
            ],
            conditional_read=[
                "高频主题 → memory://projects/<主题>.md",
            ],
            output_location="memory://inbox/_review_suggestion.md",
            pitfalls=[
                "不要批量确认",
                "每条标置信度 + 来源",
                "超过 100 条时分页",
            ],
        ))

        # Room 3: apply_memory
        r3 = self.create_room("apply_memory", "合并 inbox 到长期记忆")
        r3.add_card(PalaceCard(
            name="apply_memory",
            description="确认后合并到长期记忆",
            trigger_scenarios=["应用记忆", "apply memory", "沉淀", "合并到长期"],
            must_read=[
                "memory://inbox/_review_suggestion.md",
                "memory://profile.md",
            ],
            conditional_read=[
                "涉及人 → memory://people/<谁>.md",
                "涉及项目 → memory://projects/<什么>.md",
                "涉及概念 → memory://wiki/<概念>.md",
            ],
            output_location="memory://{people,projects,wiki,decisions}/...",
            pitfalls=[
                "必须先出合并计划 + 等人确认",
                "不覆盖已有内容 (append-only)",
                "标注来源 (Brief / Thread / Matter)",
            ],
        ))

        # Room 4: update_profile
        r4 = self.create_room("update_profile", "从反馈学习更新画像")
        r4.add_card(PalaceCard(
            name="update_profile",
            description="从 👍/👎 反馈 → 更新 profile/style",
            trigger_scenarios=["更新画像", "update profile", "学习偏好", "风格学习"],
            must_read=[
                "memory://feedback/*",
                "memory://profile.md",
                "memory://style.md",
            ],
            conditional_read=[],
            output_location="memory://profile.md + memory://style.md",
            pitfalls=[
                "不学一次性偏好",
                "至少 3 次反馈才提炼",
                "更新需逐条确认",
            ],
        ))

        # Room 5: vault_doctor
        r5 = self.create_room("vault_doctor", "Vault 体检")
        r5.add_card(PalaceCard(
            name="vault_doctor",
            description="Vault 体检报告",
            trigger_scenarios=["体检", "vault doctor", "诊断", "健康检查"],
            must_read=[
                "memory://raw/*",
                "memory://source/*",
                "memory://inbox/*",
            ],
            conditional_read=[],
            output_location="memory://doctor_report_<date>.md",
            pitfalls=[
                "不要随便删除",
                "列出每类问题的下一步建议",
                "raw 未消化提示",
            ],
        ))

        # Room 6: create_skill
        r6 = self.create_room("create_skill", "创建新技能")
        r6.add_card(PalaceCard(
            name="create_skill",
            description="让 Agent 自己造技能",
            trigger_scenarios=["创建技能", "create skill", "造技能", "新技能"],
            must_read=[
                "memory://style.md",
                "memory://profile.md",
                "skills://current",
            ],
            conditional_read=[
                "复用现有 → skills://<类似>/SKILL.md",
            ],
            output_location="skills://<name>/SKILL.md",
            pitfalls=[
                "必须问清楚意图",
                "先出草稿 + 等人确认",
                "描述触发词要明确",
            ],
        ))

        # 额外: V4 智影特定 rooms
        r7 = self.create_room("crawl_data", "智影 V4 数据采集")
        r7.add_card(PalaceCard(
            name="crawl_data",
            description="多渠道爬取 + 流水线处理",
            trigger_scenarios=["爬取", "crawl", "采集数据", "抓取", "搜索"],
            must_read=[
                "memory://profile.md",
                "memory://style.md",
            ],
            conditional_read=[
                "学术 → academic_*_crawler",
                "社交 → social_*_crawler",
                "深度 → deep_crawler",
            ],
            output_location="memory://raw/ + processed via pipeline",
            pitfalls=[
                "默认 strict 合规",
                "域名白/黑名单",
                "速率限制 1 rps",
            ],
        ))

        r8 = self.create_room("auto_label", "自动打标")
        r8.add_card(PalaceCard(
            name="auto_label",
            description="多模型投票打标",
            trigger_scenarios=["打标", "标注", "label", "tag"],
            must_read=[
                "memory://profile.md (用户偏好标签)",
            ],
            conditional_read=[],
            output_location="memory://labels/<dataset>.json",
            pitfalls=[
                "至少 2 模型共识",
                "置信度 < 0.5 进 inbox",
                "保留模型来源",
            ],
        ))

    def get_stats(self) -> Dict[str, Any]:
        return {
            "room_count": len(self.rooms),
            "card_count": sum(len(r.cards) for r in self.rooms.values()),
            "rooms": [
                {
                    "room_id": r.room_id,
                    "name": r.name,
                    "card_count": len(r.cards),
                }
                for r in self.rooms.values()
            ],
        }


palace_router = PalaceRouter()
