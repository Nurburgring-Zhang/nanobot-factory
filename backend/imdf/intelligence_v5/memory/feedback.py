"""智影 V5 — 反馈闭环 (Feedback → Taste → Profile/Style)"""
from __future__ import annotations

import logging
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .layers import (
    MemoryItem,
    MemoryLayer,
    feedback_store_default,
    long_term_store_default,
)

logger = logging.getLogger(__name__)


class FeedbackType(str, Enum):
    """反馈类型"""
    APPROVE = "approve"     # 👍 通过
    REJECT = "reject"       # 👎 拒绝
    EDIT = "edit"           # ✏️ 编辑
    SELECT = "select"       # 选中某项
    PREFER = "prefer"       # 偏好某项
    COMMENT = "comment"     # 评论
    RATE = "rate"           # 评分 (1-5)


@dataclass
class FeedbackSignal:
    """单条反馈信号"""
    signal_id: str = field(default_factory=lambda: f"fs-{uuid.uuid4().hex[:10]}")
    target_id: str = ""        # 哪个产出/动作
    target_type: str = ""      # "matter" | "message" | "deliverable" | "label" | "score"
    feedback_type: FeedbackType = FeedbackType.APPROVE
    source: str = ""           # 谁给的反馈
    comment: str = ""
    delta: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FeedbackCollector:
    """反馈收集器 — 收集 👍/👎/编辑/选择 等所有信号"""

    def __init__(self):
        self.signals: List[FeedbackSignal] = []
        self._by_target: Dict[str, List[str]] = {}  # target_id → signal_ids
        self._by_type: Dict[FeedbackType, List[str]] = {}

    def record(
        self,
        target_id: str,
        feedback_type: FeedbackType,
        source: str = "user",
        comment: str = "",
        target_type: str = "",
        delta: Optional[Dict[str, Any]] = None,
    ) -> FeedbackSignal:
        signal = FeedbackSignal(
            target_id=target_id,
            target_type=target_type,
            feedback_type=feedback_type,
            source=source,
            comment=comment,
            delta=delta or {},
            timestamp=time.time(),
        )
        self.signals.append(signal)
        self._by_target.setdefault(target_id, []).append(signal.signal_id)
        self._by_type.setdefault(feedback_type, []).append(signal.signal_id)
        logger.info(f"Feedback recorded: {feedback_type.value} on {target_id} from {source}")
        return signal

    def get_signals_for_target(self, target_id: str) -> List[FeedbackSignal]:
        ids = self._by_target.get(target_id, [])
        return [s for s in self.signals if s.signal_id in ids]

    def get_signals_by_type(self, feedback_type: FeedbackType) -> List[FeedbackSignal]:
        ids = self._by_type.get(feedback_type, [])
        return [s for s in self.signals if s.signal_id in ids]

    def get_approval_rate(self, target_ids: Optional[List[str]] = None) -> float:
        """批准率"""
        if target_ids is None:
            signals = self.signals
        else:
            signals = [s for s in self.signals if s.target_id in target_ids]
        if not signals:
            return 0.0
        approved = sum(1 for s in signals if s.feedback_type == FeedbackType.APPROVE)
        rejected = sum(1 for s in signals if s.feedback_type == FeedbackType.REJECT)
        total = approved + rejected
        if total == 0:
            return 0.0
        return approved / total

    def get_stats(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for s in self.signals:
            t = s.feedback_type.value
            by_type[t] = by_type.get(t, 0) + 1
        return {
            "total_signals": len(self.signals),
            "by_type": by_type,
            "unique_targets": len(self._by_target),
            "approval_rate": self.get_approval_rate(),
        }


class TasteExtractor:
    """Taste 提炼器 — 从反馈中提炼稳定偏好模式

    借鉴 obsidian-cc 思想:不学一次性偏好, 至少 3 次反馈才提炼。
    """

    def __init__(self, collector: FeedbackCollector, min_signals: int = 3):
        self.collector = collector
        self.min_signals = min_signals
        # 提炼的 taste 模式
        self.taste_patterns: List[Dict[str, Any]] = []

    def extract_taste(self) -> List[Dict[str, Any]]:
        """从反馈数据中提炼 taste 模式"""
        patterns: List[Dict[str, Any]] = []

        # 1. 按 target_type 聚合
        by_target_type: Dict[str, List[FeedbackSignal]] = {}
        for s in self.collector.signals:
            by_target_type.setdefault(s.target_type, []).append(s)

        for target_type, signals in by_target_type.items():
            if not target_type or len(signals) < self.min_signals:
                continue
            # 拒绝模式
            rejects = [s for s in signals if s.feedback_type == FeedbackType.REJECT]
            if len(rejects) >= self.min_signals:
                # 提取被拒的共同特征
                rejected_keywords = Counter()
                for s in rejects:
                    if s.comment:
                        for w in re.findall(r"\w+", s.comment):
                            if len(w) > 2:
                                rejected_keywords[w] += 1
                top_rejected = [w for w, c in rejected_keywords.most_common(10) if c >= 2]
                if top_rejected:
                    patterns.append(
                        {
                            "type": "rejection_pattern",
                            "target_type": target_type,
                            "keywords": top_rejected,
                            "evidence_count": len(rejects),
                            "confidence": min(len(rejects) / 10, 1.0),
                        }
                    )
            # 偏好模式
            approves = [s for s in signals if s.feedback_type == FeedbackType.APPROVE]
            if len(approves) >= self.min_signals:
                approved_keywords = Counter()
                for s in approves:
                    if s.comment:
                        for w in re.findall(r"\w+", s.comment):
                            if len(w) > 2:
                                approved_keywords[w] += 1
                top_approved = [w for w, c in approved_keywords.most_common(10) if c >= 2]
                if top_approved:
                    patterns.append(
                        {
                            "type": "preference_pattern",
                            "target_type": target_type,
                            "keywords": top_approved,
                            "evidence_count": len(approves),
                            "confidence": min(len(approves) / 10, 1.0),
                        }
                    )
            # 编辑模式
            edits = [s for s in signals if s.feedback_type == FeedbackType.EDIT]
            if len(edits) >= self.min_signals:
                # 从 delta 提取编辑方向
                edit_deltas = [s.delta for s in edits if s.delta]
                common_changes = Counter()
                for d in edit_deltas:
                    for k, v in d.items():
                        common_changes[f"{k}={v}"] += 1
                top_edits = [c for c, n in common_changes.most_common(5) if n >= 2]
                if top_edits:
                    patterns.append(
                        {
                            "type": "edit_pattern",
                            "target_type": target_type,
                            "changes": top_edits,
                            "evidence_count": len(edits),
                            "confidence": min(len(edits) / 10, 1.0),
                        }
                    )

        # 评分模式
        rates = [s for s in self.collector.signals if s.feedback_type == FeedbackType.RATE and "score" in s.delta]
        if rates:
            avg = sum(s.delta.get("score", 0) for s in rates) / len(rates)
            patterns.append(
                {
                    "type": "rating_average",
                    "avg_score": round(avg, 2),
                    "count": len(rates),
                    "confidence": min(len(rates) / 20, 1.0),
                }
            )

        self.taste_patterns = patterns
        return patterns

    def get_taste_for_type(self, target_type: str) -> List[Dict[str, Any]]:
        """获取某类型的偏好"""
        return [p for p in self.taste_patterns if p.get("target_type") == target_type]


class ProfileUpdater:
    """画像/风格更新器 — 应用 taste 模式到 profile/style

    每次更新都需要逐条确认 (obsidian-cc 强调)。
    """

    def __init__(self):
        self.profile: Dict[str, Any] = {
            "identity": "我是一名数据/AI 工程师",
            "preferences": [],
            "constraints": [],
            "communication_style": "简洁, 直接, 中文优先",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.style: Dict[str, Any] = {
            "tone": "professional",
            "length": "concise",
            "format": "structured",
            "language": "zh-CN",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.pending_updates: List[Dict[str, Any]] = []  # 待用户确认

    def propose_update(
        self,
        update_type: str,  # "profile" | "style"
        key: str,
        value: Any,
        evidence: str = "",
        source_pattern: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """提议更新 — 等待用户确认"""
        proposal = {
            "update_id": f"upd-{uuid.uuid4().hex[:8]}",
            "update_type": update_type,
            "key": key,
            "value": value,
            "evidence": evidence,
            "source_pattern": source_pattern,
            "proposed_at": time.time(),
            "status": "pending",  # pending/accepted/rejected
        }
        self.pending_updates.append(proposal)
        return proposal

    def confirm_update(self, update_id: str, accepted: bool) -> Optional[Dict[str, Any]]:
        """用户确认更新"""
        for upd in self.pending_updates:
            if upd["update_id"] == update_id:
                upd["status"] = "accepted" if accepted else "rejected"
                if accepted:
                    target = self.profile if upd["update_type"] == "profile" else self.style
                    target[upd["key"]] = upd["value"]
                    target["updated_at"] = time.time()
                return upd
        return None

    def list_pending(self) -> List[Dict[str, Any]]:
        return [u for u in self.pending_updates if u["status"] == "pending"]

    def get_profile(self) -> Dict[str, Any]:
        return self.profile

    def get_style(self) -> Dict[str, Any]:
        return self.style

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile,
            "style": self.style,
            "pending_updates": self.list_pending(),
            "update_history": [u for u in self.pending_updates if u["status"] != "pending"],
        }


class FeedbackLoop:
    """反馈闭环 — 收集 → 提炼 → 提议 → 确认 → 应用"""

    def __init__(self):
        self.collector = FeedbackCollector()
        self.extractor = TasteExtractor(self.collector)
        self.updater = ProfileUpdater()

    def record_feedback(
        self,
        target_id: str,
        feedback_type: str,  # "approve" | "reject" | "edit" | ...
        comment: str = "",
        target_type: str = "",
        source: str = "user",
        delta: Optional[Dict[str, Any]] = None,
    ) -> FeedbackSignal:
        try:
            ft = FeedbackType(feedback_type)
        except ValueError:
            ft = FeedbackType.COMMENT
        signal = self.collector.record(
            target_id=target_id,
            feedback_type=ft,
            source=source,
            comment=comment,
            target_type=target_type,
            delta=delta,
        )
        return signal

    def extract_and_propose(self) -> List[Dict[str, Any]]:
        """提炼 + 提议更新"""
        patterns = self.extractor.extract_taste()
        proposals: List[Dict[str, Any]] = []
        for p in patterns:
            if p["type"] == "rejection_pattern":
                proposals.append(
                    self.updater.propose_update(
                        update_type="profile",
                        key=f"avoid_{p['target_type']}",
                        value=p["keywords"],
                        evidence=f"用户在 {p['target_type']} 类型 {p['evidence_count']} 次拒绝: {p['keywords'][:5]}",
                        source_pattern=p,
                    )
                )
            elif p["type"] == "preference_pattern":
                proposals.append(
                    self.updater.propose_update(
                        update_type="profile",
                        key=f"prefer_{p['target_type']}",
                        value=p["keywords"],
                        evidence=f"用户在 {p['target_type']} 类型 {p['evidence_count']} 次偏好: {p['keywords'][:5]}",
                        source_pattern=p,
                    )
                )
            elif p["type"] == "edit_pattern":
                proposals.append(
                    self.updater.propose_update(
                        update_type="style",
                        key=f"edit_{p['target_type']}",
                        value=p["changes"],
                        evidence=f"用户在 {p['target_type']} 类型 {p['evidence_count']} 次编辑",
                        source_pattern=p,
                    )
                )
        return proposals

    def confirm(self, update_id: str, accepted: bool) -> Optional[Dict[str, Any]]:
        return self.updater.confirm_update(update_id, accepted)

    def get_profile_md(self) -> str:
        """生成 profile.md"""
        p = self.updater.get_profile()
        lines = [
            "# profile.md",
            "",
            f"> 自动生成: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(p['updated_at']))}",
            "",
            f"## 我是谁",
            p.get("identity", ""),
            "",
            f"## 偏好",
        ]
        for pref in p.get("preferences", []):
            lines.append(f"- {pref}")
        lines.extend(["", "## 约束"])
        for c in p.get("constraints", []):
            lines.append(f"- {c}")
        lines.append("")
        return "\n".join(lines)

    def get_style_md(self) -> str:
        s = self.updater.get_style()
        lines = [
            "# style.md",
            "",
            f"> 自动生成: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s['updated_at']))}",
            "",
            f"- **tone**: {s.get('tone', '')}",
            f"- **length**: {s.get('length', '')}",
            f"- **format**: {s.get('format', '')}",
            f"- **language**: {s.get('language', '')}",
            "",
        ]
        return "\n".join(lines)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "feedback": self.collector.get_stats(),
            "taste_patterns": len(self.extractor.taste_patterns),
            "pending_updates": len(self.updater.list_pending()),
            "profile": self.updater.get_profile(),
            "style": self.updater.get_style(),
        }


feedback_loop = FeedbackLoop()
