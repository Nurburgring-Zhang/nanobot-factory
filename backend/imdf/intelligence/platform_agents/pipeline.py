"""智影 V4 — PipelineAgent: 接管处理流水线 (dedupe/clean/classify/filter)"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..agent_commands.parser import ParsedCommand
from ..processing.classify import ClassifyEngine, ClassifyTaxonomy
from ..processing.cleaning import CleanStep, CleaningEngine
from ..processing.dedupe import DedupeEngine, DedupStrategy
from .base import AgentCapability, PlatformAgent

logger = logging.getLogger(__name__)


class PipelineAgent(PlatformAgent):
    """流水线 Agent — dedupe / clean / classify / filter / batch"""

    def __init__(self):
        super().__init__(
            name="PipelineAgent",
            description="流水线 Agent: 去重 / 清洗 / 分类 / 过滤 / 批处理",
            capabilities=[AgentCapability.DEDUPE, AgentCapability.CLEAN, AgentCapability.CLASSIFY],
        )
        # 复用模块
        self.dedupe_engine = DedupeEngine()
        self.clean_engine = CleaningEngine()
        self.classify_engine = ClassifyEngine()

    def handle(self, cmd: ParsedCommand) -> Any:
        action = cmd.action
        if action == "dedupe":
            return self.dedupe(cmd)
        if action == "clean":
            return self.clean(cmd)
        if action == "remove_pii":
            return self.remove_pii(cmd)
        if action == "extract_content":
            return self.extract_content(cmd)
        if action == "classify_modality":
            return self.classify(cmd)
        if action == "filter_by_class":
            return self.filter_by_class(cmd)
        return {"error": f"unknown action: {action}"}

    def dedupe(self, cmd: ParsedCommand) -> Dict[str, Any]:
        strategies_val = cmd.get("strategies", "url,sha256,simhash")
        if isinstance(strategies_val, str):
            try:
                strategies = [DedupStrategy(s.strip()) for s in strategies_val.split(",") if s.strip()]
            except ValueError:
                strategies = [DedupStrategy.URL, DedupStrategy.SHA256]
        elif isinstance(strategies_val, list):
            strategies = []
            for s in strategies_val:
                if isinstance(s, DedupStrategy):
                    strategies.append(s)
                elif isinstance(s, str):
                    try:
                        strategies.append(DedupStrategy(s))
                    except ValueError:
                        pass
            if not strategies:
                strategies = [DedupStrategy.URL, DedupStrategy.SHA256]
        else:
            strategies = [DedupStrategy.URL, DedupStrategy.SHA256]
        threshold = cmd.get("embedding_threshold", 0.92)
        engine = DedupeEngine(strategies=strategies, embedding_threshold=float(threshold))
        self._record("dedupe")
        return {
            "success": True,
            "action": "dedupe",
            "strategies": [s.value for s in strategies],
            "embedding_threshold": threshold,
            "engine": "DedupeEngine",
            "message": "就绪 — 可对 ProcessedItem 列表调用 engine.process(items)",
        }

    def clean(self, cmd: ParsedCommand) -> Dict[str, Any]:
        steps_val = cmd.get("steps", "unicode_normalize,html_strip,whitespace_fix")
        if isinstance(steps_val, str):
            try:
                steps = [CleanStep(s.strip()) for s in steps_val.split(",") if s.strip()]
            except ValueError:
                steps = list(CleanStep)
        elif isinstance(steps_val, list):
            steps = []
            for s in steps_val:
                if isinstance(s, CleanStep):
                    steps.append(s)
                elif isinstance(s, str):
                    try:
                        steps.append(CleanStep(s))
                    except ValueError:
                        pass
            if not steps:
                steps = list(CleanStep)
        else:
            steps = list(CleanStep)
        remove_pii = cmd.get("remove_pii", True)
        min_length = cmd.get("min_length", 50)
        engine = CleaningEngine(steps=steps, remove_pii=remove_pii, min_length=int(min_length))
        self._record("clean")
        return {
            "success": True,
            "action": "clean",
            "steps": [s.value for s in steps],
            "remove_pii": remove_pii,
            "min_length": min_length,
            "engine": "CleaningEngine",
        }

    def remove_pii(self, cmd: ParsedCommand) -> Dict[str, Any]:
        return self.clean(cmd)

    def extract_content(self, cmd: ParsedCommand) -> Dict[str, Any]:
        url = cmd.get("url", "")
        if not url:
            self._record("extract_content", False)
            return {"error": "missing url"}
        self._record("extract_content")
        return {
            "success": True,
            "action": "extract_content",
            "url": url,
            "message": "内容提取 — 真实环境调 WebCrawler + BS4 + trafilatura",
        }

    def classify(self, cmd: ParsedCommand) -> Dict[str, Any]:
        primary_only = cmd.get("primary_only", False)
        engine = ClassifyEngine(primary_only=bool(primary_only))
        self._record("classify")
        return {
            "success": True,
            "action": "classify",
            "primary_only": primary_only,
            "modalities": [m.value for m in ClassifyTaxonomy],
            "engine": "ClassifyEngine",
        }

    def filter_by_class(self, cmd: ParsedCommand) -> Dict[str, Any]:
        cls = cmd.get("class", "")
        if not cls:
            self._record("filter_by_class", False)
            return {"error": "missing class"}
        self._record("filter_by_class")
        return {
            "success": True,
            "action": "filter_by_class",
            "class": cls,
            "message": f"按模态/类 {cls} 过滤",
        }

    def run_full_pipeline(self, items: List, stages: Optional[List[str]] = None) -> Dict[str, Any]:
        """全流水线运行 — dedupe → clean → label → score → classify → store"""
        from ..processing.auto_label import AutoLabelEngine, LabelModel
        from ..processing.scoring import ScoringEngine, ScoreDimension
        from ..processing.store import StorageEngine, StorageBackend

        stages = stages or ["dedupe", "clean", "label", "score", "classify", "store"]
        engines = {
            "dedupe": self.dedupe_engine,
            "clean": self.clean_engine,
            "classify": self.classify_engine,
            "label": AutoLabelEngine(models=[LabelModel.RULES, LabelModel.KEYWORDS]),
            "score": ScoringEngine(dimensions=list(ScoreDimension)),
            "store": StorageEngine(content_backend=StorageBackend.LOCAL),
        }
        results: Dict[str, Any] = {}
        current = items
        for s in stages:
            eng = engines.get(s)
            if eng is None:
                continue
            try:
                current = eng.process(current)
                results[s] = eng.get_metrics()
            except Exception as e:
                results[s] = {"error": str(e)}
        return {
            "items": current,
            "stage_metrics": results,
            "final_count": len(current),
        }
