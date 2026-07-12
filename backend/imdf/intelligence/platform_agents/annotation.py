"""智影 V4 — AnnotationAgent: 接管所有标注 (auto_label / manual_label / label_review)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from ..processing.auto_label import AutoLabelEngine, LabelModel
from ..processing.base import ProcessedItem
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class AnnotationAgent(PlatformAgent):
    """标注 Agent — 自动 + 手工 + 审核"""

    def __init__(self, auto_engine: Optional[AutoLabelEngine] = None):
        super().__init__(
            name="AnnotationAgent",
            description="标注 Agent: 自动打标 / 手工标注 / 标注审核 — 多模型投票",
            capabilities=[AgentCapability.LABEL],
        )
        self.auto_engine = auto_engine or AutoLabelEngine(
            models=[LabelModel.RULES, LabelModel.KEYWORDS],
            consensus_threshold=2,
        )

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "auto_label":
            return self.auto_label(cmd)
        if action == "manual_label":
            return self.manual_label(cmd)
        if action == "label_review":
            return self.label_review(cmd)
        return {"error": f"unknown action: {action}"}

    def auto_label(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """自动打标 — 复用 AutoLabelEngine"""
        models_val = cmd.get("models", "rules,keywords")
        if isinstance(models_val, str):
            try:
                models = [LabelModel(m.strip()) for m in models_val.split(",") if m.strip()]
            except ValueError:
                models = [LabelModel.RULES, LabelModel.KEYWORDS]
        elif isinstance(models_val, list):
            models = []
            for m in models_val:
                if isinstance(m, LabelModel):
                    models.append(m)
                elif isinstance(m, str):
                    try:
                        models.append(LabelModel(m))
                    except ValueError:
                        pass
            if not models:
                models = [LabelModel.RULES, LabelModel.KEYWORDS]
        else:
            models = [LabelModel.RULES, LabelModel.KEYWORDS]
        consensus = cmd.get("consensus_threshold", 2)
        engine = AutoLabelEngine(models=models, consensus_threshold=int(consensus))
        self._record("auto_label")
        return {
            "success": True,
            "action": "auto_label",
            "models": [m.value for m in models],
            "consensus_threshold": consensus,
            "engine": "AutoLabelEngine",
            "message": "就绪: 可对 ProcessedItem 列表调用 engine.process(items)",
        }

    def manual_label(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """手工标注 — 平台 workbench 接入"""
        item_id = cmd.get("item_id", "")
        labels = cmd.get("labels", [])
        if not item_id or not labels:
            self._record("manual_label", False)
            return {"error": "missing item_id or labels", "action": "manual_label"}
        # 真实环境: 调 workbench_engine.save_annotation
        self._record("manual_label")
        return {
            "success": True,
            "action": "manual_label",
            "item_id": item_id,
            "labels": labels,
            "message": "已记录 — 真实环境调用 workbench_engine.save_annotation",
        }

    def label_review(self, cmd: ParsedCommand) -> Dict[str, Any]:
        """标注审核"""
        item_id = cmd.get("item_id", "")
        if not item_id:
            self._record("label_review", False)
            return {"error": "missing item_id", "action": "label_review"}
        self._record("label_review")
        return {
            "success": True,
            "action": "label_review",
            "item_id": item_id,
            "message": "已提交审核 — 真实环境调用 review_engine.submit_review",
        }

    def get_candidate_labels(self) -> List[str]:
        """返回所有候选标签 — 给前端下拉用"""
        from ..processing.auto_label import _default_label_taxonomy
        return list(_default_label_taxonomy().keys())
