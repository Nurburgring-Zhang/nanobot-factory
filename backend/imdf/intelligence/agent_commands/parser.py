"""智影 V4 — CommandParser: NL → 结构化 ParsedCommand"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .intent import Intent, IntentClassifier

logger = logging.getLogger(__name__)


@dataclass
class CommandParameter:
    """命令参数"""

    name: str
    value: Any
    type: str = "string"  # string / int / list / dict / url
    required: bool = False
    source: str = "explicit"  # explicit / default / inferred


@dataclass
class ParsedCommand:
    """解析后的命令"""

    intent: Intent
    action: str
    parameters: List[CommandParameter] = field(default_factory=list)
    pipeline: List[str] = field(default_factory=list)  # 处理流水线步骤
    confidence: float = 0.0
    requires_confirmation: bool = False
    raw_text: str = ""
    notes: List[str] = field(default_factory=list)

    def get(self, name: str, default: Any = None) -> Any:
        for p in self.parameters:
            if p.name == name:
                return p.value
        return default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.category.value,
            "action": self.action,
            "parameters": {p.name: p.value for p in self.parameters},
            "pipeline": self.pipeline,
            "confidence": self.confidence,
            "requires_confirmation": self.requires_confirmation,
            "raw_text": self.raw_text,
            "notes": self.notes,
        }


class CommandParser:
    """自然语言 → ParsedCommand"""

    # 每个 action 的必填 + 可选参数 schema
    PARAM_SCHEMAS: Dict[str, Dict[str, Any]] = {
        # Crawl
        "crawl_url": {"required": ["url"], "optional": ["depth", "max_pages", "channel", "compliance_mode"]},
        "crawl_website": {"required": ["url"], "optional": ["max_depth", "max_pages", "strategy", "same_domain"]},
        "crawl_search": {"required": ["query"], "optional": ["channel", "max_results", "provider"]},
        "deep_crawl": {"required": ["url"], "optional": ["strategy", "max_depth", "max_pages"]},
        "batch_crawl": {"required": ["urls"], "optional": ["channel", "max_concurrent"]},
        "academic_crawl": {"required": ["query"], "optional": ["source", "max_results"]},
        "social_crawl": {"required": ["url"], "optional": ["platform", "max_items"]},
        "rss_subscribe": {"required": ["url"], "optional": ["max_entries"]},
        "file_download": {"required": ["url"], "optional": ["destination"]},
        # Search
        "web_search": {"required": ["query"], "optional": ["provider", "max_results"]},
        "image_search": {"required": ["query"], "optional": ["provider", "max_results"]},
        "video_search": {"required": ["query"], "optional": ["provider", "max_results"]},
        "academic_search": {"required": ["query"], "optional": ["source", "max_results"]},
        "code_search": {"required": ["query"], "optional": ["platform", "language"]},
        # Process
        "dedupe": {"required": [], "optional": ["strategies", "embedding_threshold"]},
        "clean": {"required": [], "optional": ["steps", "remove_pii", "min_length"]},
        "remove_pii": {"required": [], "optional": ["patterns"]},
        "extract_content": {"required": ["url"], "optional": ["selectors"]},
        # Label
        "auto_label": {"required": [], "optional": ["models", "consensus_threshold", "max_labels"]},
        "manual_label": {"required": ["item_id", "labels"], "optional": []},
        "label_review": {"required": ["item_id"], "optional": []},
        # Score
        "score_quality": {"required": [], "optional": ["model", "min_score"]},
        "score_aesthetic": {"required": [], "optional": ["model", "min_score"]},
        "filter_by_score": {"required": ["min_score"], "optional": ["dimension"]},
        # Classify
        "classify_modality": {"required": [], "optional": ["primary_only"]},
        "filter_by_class": {"required": ["class"], "optional": []},
        # Store
        "upload": {"required": ["source"], "optional": ["destination", "backend"]},
        "export": {"required": ["filter"], "optional": ["format", "destination"]},
        # Analyze
        "stats": {"required": [], "optional": ["group_by"]},
        "report": {"required": [], "optional": ["type", "period"]},
        "query_data": {"required": ["filter"], "optional": ["limit", "offset"]},
        "compare": {"required": ["items"], "optional": ["dimension"]},
        # Manage
        "create_project": {"required": ["name"], "optional": ["description", "priority"]},
        "create_requirement": {"required": ["title"], "optional": ["type", "priority", "description"]},
        "assign_task": {"required": ["task_id", "assignee"], "optional": []},
        "approve": {"required": ["item_id"], "optional": []},
        "reject": {"required": ["item_id"], "optional": ["reason"]},
        # Workflow
        "start_workflow": {"required": ["workflow_id"], "optional": ["input"]},
        "stop_workflow": {"required": ["workflow_id"], "optional": []},
        "design_workflow": {"required": ["description"], "optional": []},
        # System
        "help": {"required": [], "optional": ["topic"]},
        "status": {"required": [], "optional": ["component"]},
        "config": {"required": ["key", "value"], "optional": []},
    }

    def __init__(self, intent_classifier: Optional[IntentClassifier] = None):
        self.intent_classifier = intent_classifier or IntentClassifier()

    def parse(self, text: str, context: Optional[Dict[str, Any]] = None) -> ParsedCommand:
        """主解析函数"""
        intent = self.intent_classifier.classify_top1(text, context)
        schema = self.PARAM_SCHEMAS.get(intent.action, {"required": [], "optional": []})
        params = self._extract_params(text, intent, schema)
        # 自动补流水线
        pipeline = self._infer_pipeline(intent, params)
        # 是否需要二次确认 (destructive / 范围广)
        needs_confirm = self._needs_confirmation(intent, params)
        notes = self._build_notes(intent, params, schema)
        return ParsedCommand(
            intent=intent,
            action=intent.action,
            parameters=params,
            pipeline=pipeline,
            confidence=intent.confidence,
            requires_confirmation=needs_confirm,
            raw_text=text,
            notes=notes,
        )

    def _extract_params(self, text: str, intent: Intent, schema: Dict[str, Any]) -> List[CommandParameter]:
        params: List[CommandParameter] = []
        entities = intent.entities or {}
        # 1. URL
        if "url" in schema["required"] or "url" in schema["optional"]:
            urls = entities.get("urls", [])
            if urls:
                params.append(CommandParameter("url", urls[0], "url", "url" in schema["required"]))
            else:
                # 从 context 取
                params.append(CommandParameter("url", None, "url", "url" in schema["required"]))
        # 2. URLs (list)
        if "urls" in schema["required"]:
            urls = entities.get("urls", [])
            params.append(CommandParameter("urls", urls, "list", True))
        # 3. query
        if "query" in schema["required"]:
            keywords = entities.get("keywords", [])
            if keywords:
                params.append(CommandParameter("query", keywords[0], "string", True))
            else:
                # 兜底: 提取意图相关短语
                query = self._extract_query(text, intent)
                params.append(CommandParameter("query", query, "string", True))
        # 4. 数字
        if "max_results" in schema["optional"] or "max_pages" in schema["optional"]:
            numbers = entities.get("numbers", [])
            for n in numbers:
                if n > 1 and n < 10000:
                    params.append(CommandParameter("max_results", n, "int", False))
                    params.append(CommandParameter("max_pages", n, "int", False))
                    break
            else:
                params.append(CommandParameter("max_results", 100, "int", False))
                params.append(CommandParameter("max_pages", 100, "int", False))
        # 5. channel
        if "channel" in schema["optional"]:
            channels = entities.get("channels", [])
            if channels:
                params.append(CommandParameter("channel", channels[0], "string", False))
            else:
                # 推断
                ch = self._infer_channel(text, intent)
                params.append(CommandParameter("channel", ch, "string", False))
        # 6. item_id
        if "item_id" in schema["required"]:
            params.append(CommandParameter("item_id", None, "string", True))
        # 7. 其他
        for k in schema.get("optional", []):
            if not any(p.name == k for p in params):
                v = self._extract_optional_param(k, text)
                params.append(CommandParameter(k, v, "string", False))
        return params

    def _extract_query(self, text: str, intent: Intent) -> str:
        """提取搜索词 — 去掉前缀动词"""
        patterns_to_strip = [
            r"^(?:帮|请)?(?:我)?(?:搜索?|搜|找|爬|抓|下载|看看|看看?下?|检索|查(?:看|询)?)",
            r"^(?:一下|下)?",
            r"(?:的)?(?:一下|下)?$",
        ]
        result = text
        for pat in patterns_to_strip:
            result = re.sub(pat, "", result, flags=re.IGNORECASE)
        return result.strip() or text

    def _infer_channel(self, text: str, intent: Intent) -> str:
        """推断渠道"""
        text_l = text.lower()
        if "arxiv" in text_l or "论文" in text:
            return "academic_arxiv"
        if "reddit" in text_l:
            return "social_reddit"
        if "twitter" in text_l or "x.com" in text_l:
            return "social_twitter"
        if "hackernews" in text_l or "hacker news" in text_l:
            return "social_hackernews"
        if "github" in text_l:
            return "source_github"
        if "wikipedia" in text_l:
            return "source_wikipedia"
        if intent.category.value == "search":
            return "search_duckduckgo"
        if intent.category.value == "crawl":
            return "web_generic"
        return "web_generic"

    def _extract_optional_param(self, name: str, text: str) -> Any:
        """提取可选参数"""
        if name in ("depth", "max_depth"):
            # 多种深度表述
            m = re.search(r"深度\s*(\d+)", text)
            if m:
                return int(m.group(1))
            m = re.search(r"(\d+)\s*层", text)
            if m:
                return int(m.group(1))
            return 2
        if name == "strategy":
            if "BFS" in text or "广度" in text:
                return "bfs"
            if "DFS" in text or "深度" in text:
                return "dfs"
            if "引用" in text or "citation" in text.lower():
                return "citation"
            return "bfs"
        if name == "min_score":
            m = re.search(r"(?:大于|高于|至少|>=?|min)\s*([\d.]+)", text)
            if m:
                return float(m.group(1))
            return 0.7
        if name == "dimension":
            if "美学" in text or "颜值" in text:
                return "aesthetic"
            if "质量" in text:
                return "quality"
            return "quality"
        if name == "compliance_mode":
            if "内部" in text or "internal" in text.lower():
                return "internal"
            if "审计" in text or "audit" in text.lower():
                return "audit"
            if "研究" in text or "research" in text.lower():
                return "research"
            return "strict"
        if name == "max_concurrent":
            return 4
        if name == "platform":
            if "reddit" in text.lower():
                return "reddit"
            if "twitter" in text.lower():
                return "twitter"
            return "auto"
        if name == "source":
            if "arxiv" in text.lower():
                return "arxiv"
            if "pubmed" in text.lower():
                return "pubmed"
            if "semantic" in text.lower():
                return "semantic_scholar"
            return "arxiv"
        if name == "min_length":
            m = re.search(r"长度.{0,5}大于\s*(\d+)", text)
            if m:
                return int(m.group(1))
            return 50
        if name == "remove_pii":
            if "保留" in text or "不" in text:
                return False
            return True
        if name == "max_items":
            m = re.search(r"(?:前|最近)\s*(\d+)", text)
            if m:
                return int(m.group(1))
            return 50
        if name == "max_entries":
            m = re.search(r"(?:前|最近)\s*(\d+)", text)
            if m:
                return int(m.group(1))
            return 50
        if name == "primary_only":
            return True
        if name == "consensus_threshold":
            return 2
        if name == "max_labels":
            return 10
        if name == "embedding_threshold":
            return 0.92
        if name == "filter":
            return {}
        if name == "items":
            return []
        if name == "destination":
            return ""
        if name == "backend":
            return "minio"
        if name == "type":
            if "需求" in text or "requirement" in text.lower():
                return "requirement"
            return "task"
        if name == "priority":
            if "高" in text:
                return "high"
            if "低" in text:
                return "low"
            return "medium"
        if name == "description":
            return ""
        if name == "name":
            m = re.search(r"名叫\s*[\"']?([^\"']+)[\"']?", text)
            if m:
                return m.group(1)
            m = re.search(r"创建.{0,5}项目\s*[\"']?([^\"']+)[\"']?", text)
            if m:
                return m.group(1)
            return ""
        if name == "title":
            m = re.search(r"(?:标题|名为|叫做)\s*[\"']?([^\"']+)[\"']?", text)
            if m:
                return m.group(1)
            return ""
        if name == "reason":
            return ""
        if name == "workflow_id":
            return ""
        if name == "input":
            return {}
        if name == "topic":
            return "general"
        if name == "component":
            return "all"
        if name == "key":
            return ""
        if name == "value":
            return ""
        if name == "format":
            return "jsonl"
        if name == "period":
            return "last_7_days"
        if name == "limit":
            return 100
        if name == "offset":
            return 0
        if name == "group_by":
            if "渠道" in text:
                return "source_channel"
            if "类型" in text or "模态" in text:
                return "modality"
            return "modality"
        if name == "strategies":
            return ["url", "sha256", "simhash"]
        if name == "steps":
            return ["unicode_normalize", "html_strip", "whitespace_fix"]
        if name == "patterns":
            return list(["email", "phone", "id_card"])
        if name == "selectors":
            return {}
        if name == "models":
            return ["rules", "keywords"]
        if name == "model":
            return "rule"
        if name == "class":
            return ""
        if name == "language":
            return ""
        if name == "same_domain":
            return True
        if name == "provider":
            return "duckduckgo"
        if name == "assignee":
            return ""
        if name == "labels":
            return []
        return None

    def _infer_pipeline(self, intent: Intent, params: List[CommandParameter]) -> List[str]:
        """推断处理流水线"""
        cat = intent.category.value
        if cat == "crawl":
            # crawl 通常跟 dedupe + clean + label + score
            return ["crawl", "dedupe", "clean", "label", "score", "classify", "store"]
        if cat == "search":
            return ["search", "crawl", "dedupe", "clean", "label", "score", "classify", "store"]
        if cat == "process":
            action = intent.action
            if action == "dedupe":
                return ["dedupe"]
            if action == "clean":
                return ["clean"]
            return [action]
        if cat == "label":
            return ["label"]
        if cat == "score":
            return ["score"]
        if cat == "classify":
            return ["classify"]
        if cat == "store":
            return ["store"]
        return [cat]

    def _needs_confirmation(self, intent: Intent, params: List[CommandParameter]) -> bool:
        """是否需要二次确认"""
        action = intent.action
        if action in ("upload", "export", "approve", "reject", "start_workflow", "stop_workflow", "create_project", "create_requirement"):
            return True
        # crawl 数量大时需确认
        max_results = next((p.value for p in params if p.name == "max_results"), 0)
        if max_results and max_results > 500:
            return True
        return False

    def _build_notes(self, intent: Intent, params: List[CommandParameter], schema: Dict[str, Any]) -> List[str]:
        notes: List[str] = []
        # 必填参数缺失
        for required_name in schema.get("required", []):
            p = next((x for x in params if x.name == required_name), None)
            if not p or p.value is None or p.value == "" or p.value == []:
                notes.append(f"missing required param: {required_name}")
        # 建议
        if intent.confidence < 0.7:
            notes.append(f"low confidence: {intent.confidence:.2f}, please confirm intent")
        return notes
