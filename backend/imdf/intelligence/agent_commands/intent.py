"""智影 V4 — IntentClassifier: 自然语言 → 意图 (12 大类 50+ 意图)"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class IntentCategory(str, Enum):
    """意图分类 — 12 大类"""

    CRAWL = "crawl"  # 爬取/下载
    SEARCH = "search"  # 搜索
    PROCESS = "process"  # 处理
    LABEL = "label"  # 打标
    SCORE = "score"  # 评分
    CLASSIFY = "classify"  # 分类
    STORE = "store"  # 存储
    ANALYZE = "analyze"  # 分析/查询
    MANAGE = "manage"  # 项目/任务管理
    WORKFLOW = "workflow"  # 工作流
    SYSTEM = "system"  # 系统命令
    CHAT = "chat"  # 闲聊/帮助


@dataclass
class Intent:
    """意图"""

    category: IntentCategory
    action: str  # 具体动作
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    matched_patterns: List[str] = field(default_factory=list)


# 意图规则表 — 12 大类 50+ 意图
INTENT_RULES: List[Dict[str, Any]] = [
    # ===== CRAWL =====
    {"cat": "crawl", "action": "deep_crawl", "patterns": [r"深度.{0,5}(?:爬|抓|取)", r"deep\s+crawl", r"BFS|DFS|引用链"], "weight": 1.2},
    {"cat": "crawl", "action": "crawl_url", "patterns": [r"爬(?:取|一下)?\s*https?://", r"抓取\s*https?://", r"下载\s*https?://", r"crawl\s+(?:url|https?)", r"^crawl\b"], "weight": 1.0},
    {"cat": "crawl", "action": "crawl_website", "patterns": [r"爬.{0,10}网站", r"crawl\s+(?:website|site)", r"全站爬", r"遍历.{0,10}网站"], "weight": 1.0},
    {"cat": "crawl", "action": "crawl_search", "patterns": [r"(?:搜索|搜|检索).{0,20}(?:并|然后)?.{0,10}(?:爬|抓|下载)", r"search.{0,20}crawl"], "weight": 0.9},
    {"cat": "crawl", "action": "batch_crawl", "patterns": [r"批量.{0,5}(?:爬|抓|下)", r"batch\s+crawl", r"多URL"], "weight": 0.9},
    {"cat": "crawl", "action": "academic_crawl", "patterns": [r"(?:从|抓).{0,10}(?:arxiv|pubmed|学术)", r"academic", r"论文.{0,5}(?:爬|下|搜)"], "weight": 0.95},
    {"cat": "crawl", "action": "social_crawl", "patterns": [r"(?:抓|爬).{0,10}(?:reddit|twitter|hacker|hackernews|devto)", r"社交媒体.{0,5}(?:抓|爬)"], "weight": 0.95},
    {"cat": "crawl", "action": "rss_subscribe", "patterns": [r"订阅.{0,10}RSS", r"rss.{0,5}订阅", r"关注.{0,10}(?:订阅源|feed)"], "weight": 0.95},
    {"cat": "crawl", "action": "file_download", "patterns": [r"下载.{0,20}(?:s3|oss|minio|ftp|文件)", r"download.{0,10}file"], "weight": 0.9},
    # ===== SEARCH =====
    {"cat": "search", "action": "web_search", "patterns": [r"(?:搜|检索|搜索).{0,5}(?:一下|下)?", r"search", r"查找", r"找(?:一|几|些)?"], "weight": 0.8},
    {"cat": "search", "action": "image_search", "patterns": [r"(?:搜|找).{0,5}图", r"image\s+search", r"图片搜索"], "weight": 0.95},
    {"cat": "search", "action": "video_search", "patterns": [r"(?:搜|找).{0,5}视频", r"video\s+search", r"youtobe|b站"], "weight": 0.95},
    {"cat": "search", "action": "academic_search", "patterns": [r"(?:搜|找).{0,5}论文", r"academic\s+search", r"arXiv"], "weight": 0.95},
    {"cat": "search", "action": "code_search", "patterns": [r"(?:搜|找).{0,5}代码", r"code\s+search", r"github\s+搜"], "weight": 0.9},
    # ===== PROCESS =====
    {"cat": "process", "action": "dedupe", "patterns": [r"去重", r"去除重复", r"删除重复", r"dedupe", r"重复数据"], "weight": 1.0},
    {"cat": "process", "action": "clean", "patterns": [r"清洗", r"清理", r"过滤.{0,5}(?:内容|数据)", r"clean", r"去除.{0,5}噪声"], "weight": 1.0},
    {"cat": "process", "action": "remove_pii", "patterns": [r"脱敏", r"去.{0,5}PII", r"remove\s+PII", r"去除.{0,5}(?:敏感|隐私)信息"], "weight": 1.0},
    {"cat": "process", "action": "extract_content", "patterns": [r"提取.{0,5}(?:内容|正文|文本)", r"extract", r"抽取"], "weight": 0.9},
    # ===== LABEL =====
    {"cat": "label", "action": "manual_label", "patterns": [r"手工.{0,5}标", r"手动打标", r"人工标注", r"人工.{0,3}标"], "weight": 1.0},
    {"cat": "label", "action": "auto_label", "patterns": [r"自动.{0,3}标", r"打标", r"打标签", r"标注", r"label", r"tag"], "weight": 0.95},
    {"cat": "label", "action": "label_review", "patterns": [r"(?:审|检|复)查.{0,5}标签", r"label\s+review", r"标签审核"], "weight": 1.0},
    # ===== SCORE =====
    {"cat": "score", "action": "score_quality", "patterns": [r"评.{0,5}分", r"质量分", r"quality\s+score", r"打分"], "weight": 1.0},
    {"cat": "score", "action": "score_aesthetic", "patterns": [r"美.{0,5}分", r"美学分", r"aesthetic", r"颜值分"], "weight": 1.0},
    {"cat": "score", "action": "filter_by_score", "patterns": [r"(?:筛|过)选.{0,5}(?:高|低|优|差)分", r"按.{0,5}分.{0,5}(?:筛|过|选)"], "weight": 0.95},
    # ===== CLASSIFY =====
    {"cat": "classify", "action": "classify_modality", "patterns": [r"分类", r"分(?:个|几|一下)?.{0,3}类", r"classify", r"归类"], "weight": 0.85},
    {"cat": "classify", "action": "filter_by_class", "patterns": [r"筛选.{0,10}(?:类型|类|模态)", r"只.{0,5}要.{0,10}(?:图|视频|音频)"], "weight": 0.9},
    # ===== STORE =====
    {"cat": "store", "action": "upload", "patterns": [r"上传", r"upload", r"导入"], "weight": 0.85},
    {"cat": "store", "action": "export", "patterns": [r"导出", r"export", r"下载到本地"], "weight": 0.85},
    # ===== ANALYZE =====
    {"cat": "analyze", "action": "stats", "patterns": [r"统计", r"stats", r"数量", r"分布", r"占比"], "weight": 0.85},
    {"cat": "analyze", "action": "report", "patterns": [r"报告", r"report", r"汇总", r"总览"], "weight": 0.9},
    {"cat": "analyze", "action": "query_data", "patterns": [r"查(?:看|询)?", r"list", r"显示.{0,5}数据"], "weight": 0.7},
    {"cat": "analyze", "action": "compare", "patterns": [r"对比", r"比较", r"compare"], "weight": 0.9},
    # ===== MANAGE =====
    {"cat": "manage", "action": "create_project", "patterns": [r"创建.{0,5}项目", r"新建项目", r"create\s+project"], "weight": 1.0},
    {"cat": "manage", "action": "create_requirement", "patterns": [r"创建.{0,5}(?:需求|任务)", r"新建.{0,5}(?:需求|任务)", r"create\s+(?:requirement|task)"], "weight": 1.0},
    {"cat": "manage", "action": "assign_task", "patterns": [r"分配.{0,5}(?:任务|标注员)", r"指派", r"assign"], "weight": 1.0},
    {"cat": "manage", "action": "approve", "patterns": [r"审核通过", r"通过.{0,3}审核", r"通过.{0,3}验收", r"批准", r"approve", r"接受", r"准许"], "weight": 0.95},
    {"cat": "manage", "action": "reject", "patterns": [r"拒绝", r"驳回", r"reject"], "weight": 0.95},
    # ===== WORKFLOW =====
    {"cat": "workflow", "action": "start_workflow", "patterns": [r"(?:启动|开始|运行).{0,5}工作流", r"start\s+workflow", r"run\s+workflow"], "weight": 1.0},
    {"cat": "workflow", "action": "stop_workflow", "patterns": [r"停止.{0,5}工作流", r"终止", r"stop\s+workflow"], "weight": 1.0},
    {"cat": "workflow", "action": "design_workflow", "patterns": [r"设计.{0,5}工作流", r"design\s+workflow"], "weight": 1.0},
    # ===== SYSTEM =====
    {"cat": "system", "action": "help", "patterns": [r"帮助", r"help", r"怎么用", r"使用说明"], "weight": 0.95},
    {"cat": "system", "action": "status", "patterns": [r"状态", r"status", r"健康检查", r"health"], "weight": 0.9},
    {"cat": "system", "action": "config", "patterns": [r"配置", r"config", r"设置"], "weight": 0.85},
    # ===== CHAT =====
    {"cat": "chat", "action": "greeting", "patterns": [r"^你好", r"hello", r"hi\b", r"在吗"], "weight": 0.95},
    {"cat": "chat", "action": "thanks", "patterns": [r"谢谢", r"thanks", r"thank\s+you"], "weight": 0.95},
]


class IntentClassifier:
    """意图分类器 — 规则 + 关键词 + 上下文"""

    def __init__(self, custom_rules: Optional[List[Dict[str, Any]]] = None):
        self.rules = custom_rules or INTENT_RULES

    def classify(self, text: str, context: Optional[Dict[str, Any]] = None) -> List[Intent]:
        """返回所有匹配意图 (按 confidence 倒序)"""
        text_clean = (text or "").strip().lower()
        if not text_clean:
            return [Intent(category=IntentCategory.CHAT, action="unknown", confidence=0.0, raw_text=text)]
        matches: List[Intent] = []
        for rule in self.rules:
            cat = IntentCategory(rule["cat"])
            action = rule["action"]
            for pat in rule["patterns"]:
                if re.search(pat, text_clean, re.IGNORECASE):
                    conf = self._compute_confidence(pat, text_clean, rule["weight"], context)
                    matches.append(
                        Intent(
                            category=cat,
                            action=action,
                            confidence=conf,
                            raw_text=text,
                            matched_patterns=[pat],
                            entities=self._extract_entities(text, cat, action),
                        )
                    )
                    break
        if not matches:
            # 兜底: 闲聊
            matches.append(Intent(category=IntentCategory.CHAT, action="unknown", confidence=0.5, raw_text=text))
        # 倒序
        matches.sort(key=lambda x: x.confidence, reverse=True)
        return matches

    def classify_top1(self, text: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        results = self.classify(text, context)
        return results[0] if results else Intent(IntentCategory.CHAT, "unknown", 0.0, raw_text=text)

    def _compute_confidence(self, pattern: str, text: str, base_weight: float, context: Optional[Dict[str, Any]]) -> float:
        conf = base_weight
        # 关键词越具体 → 越高
        if any(specific in text for specific in ["arxiv", "reddit", "twitter", "s3", "oss"]):
            conf += 0.05
        # 上下文增强
        if context and context.get("last_intent"):
            last = context["last_intent"]
            # 同类意图 → 加分
            if last.get("category") == _pattern_to_category(pattern):
                conf += 0.1
        return min(conf, 1.0)

    def _extract_entities(self, text: str, cat: IntentCategory, action: str) -> Dict[str, Any]:
        entities: Dict[str, Any] = {}
        # URL
        urls = re.findall(r"https?://[^\s\]\)\,，。]+", text)
        if urls:
            entities["urls"] = urls
        # 数字
        nums = re.findall(r"\b\d+\b", text)
        if nums:
            entities["numbers"] = [int(n) for n in nums]
        # 关键词引号提取
        quoted = re.findall(r"[\"'「」『』](.+?)[\"'「」『』]", text)
        if quoted:
            entities["keywords"] = quoted
        # 渠道识别
        channels = {
            "arxiv": "academic_arxiv",
            "reddit": "social_reddit",
            "twitter": "social_twitter",
            "hackernews": "social_hackernews",
            "github": "source_github",
            "huggingface": "source_huggingface",
            "wikipedia": "source_wikipedia",
            "youtube": "rss_youtube_channel",
            "s3": "file_s3",
            "minio": "file_minio",
        }
        for k, v in channels.items():
            if k in text.lower():
                entities.setdefault("channels", []).append(v)
        return entities


def _pattern_to_category(pattern: str) -> str:
    """简化: 从 pattern 反推 category (粗略)"""
    if "arxiv" in pattern or "academic" in pattern:
        return "academic"
    if "reddit" in pattern or "twitter" in pattern:
        return "social"
    if "crawl" in pattern or "抓" in pattern or "爬" in pattern:
        return "crawl"
    return "unknown"
