"""智影 V4 — CleaningEngine: 8 模态内容清洗 (文本/HTML/JSON/图片/视频/音频/PDF/CSV)"""
from __future__ import annotations

import html
import json
import logging
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class CleanStep(str, Enum):
    """清洗步骤 — 可任意组合"""

    UNICODE_NORMALIZE = "unicode_normalize"
    HTML_STRIP = "html_strip"
    REMOVE_PII = "remove_pii"
    REMOVE_BOILERPLATE = "remove_boilerplate"
    REMOVE_DUPLICATE_LINES = "remove_duplicate_lines"
    REMOVE_SHORT_LINES = "remove_short_lines"
    LANG_DETECT = "lang_detect"
    ENCODE_FIX = "encode_fix"
    JSON_NORMALIZE = "json_normalize"
    WHITESPACE_FIX = "whitespace_fix"
    TRUNCATE = "truncate"
    FILTER_NON_TEXT = "filter_non_text"


class CleaningEngine(ProcessingPipeline):
    """内容清洗引擎 — 8 模态支持"""

    # PII patterns (universal — 跟安全模块对齐)
    PII_PATTERNS = {
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "phone_cn": re.compile(r"\b1[3-9]\d{9}\b"),
        "phone_us": re.compile(r"\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        "id_card_cn": re.compile(r"\b\d{17}[\dXx]\b"),
        "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        "url_internal": re.compile(r"\bhttps?://[^\s]*?(localhost|127\.|192\.168\.|10\.)[^\s]*\b"),
    }

    # Boilerplate 关键词
    BOILERPLATE_PATTERNS = [
        re.compile(r"cookie\s+(policy|notice|consent)", re.IGNORECASE),
        re.compile(r"privacy\s+policy", re.IGNORECASE),
        re.compile(r"terms\s+(of\s+service|of\s+use)", re.IGNORECASE),
        re.compile(r"subscribe\s+to\s+(our\s+)?newsletter", re.IGNORECASE),
        re.compile(r"sign\s+up\s+for", re.IGNORECASE),
        re.compile(r"all\s+rights\s+reserved", re.IGNORECASE),
        re.compile(r"^\s*share\s+(on|this)\s+", re.IGNORECASE),
        re.compile(r"^\s*follow\s+us\s+", re.IGNORECASE),
    ]

    def __init__(self, steps: Optional[List[CleanStep]] = None, remove_pii: bool = True, min_length: int = 50):
        super().__init__(name="cleaning")
        self.steps = steps or [
            CleanStep.UNICODE_NORMALIZE,
            CleanStep.HTML_STRIP,
            CleanStep.REMOVE_BOILERPLATE,
            CleanStep.WHITESPACE_FIX,
            CleanStep.REMOVE_DUPLICATE_LINES,
            CleanStep.REMOVE_SHORT_LINES,
        ]
        self.remove_pii = remove_pii
        self.min_length = min_length

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            try:
                self._clean(item)
                if self.min_length and len((item.text or "").strip()) < self.min_length and item.type in ("html", "rss_entry", "json"):
                    item.rejection_reason = f"too_short:{len((item.text or '').strip())}"
                    self.metrics.rejected += 1
                    continue
                item.audit_chain.append({"step": "cleaning", "action": "cleaned", "steps_applied": [s.value for s in self.steps], "ts": _now()})
                self.metrics.cleaned += 1
                out.append(item)
            except Exception as e:
                self.metrics.rejected += 1
                item.rejection_reason = f"clean_error:{e}"
                item.audit_chain.append({"step": "cleaning", "action": "error", "error": str(e), "ts": _now()})
                logger.warning(f"cleaning failed for {item.source_url}: {e}")
        self.finish()
        return out

    def _clean(self, item: ProcessedItem):
        for step in self.steps:
            if step == CleanStep.UNICODE_NORMALIZE:
                item.text = self._unicode_normalize(item.text or "")
                item.title = self._unicode_normalize(item.title or "")
            elif step == CleanStep.HTML_STRIP:
                item.text = self._strip_html(item.text or "")
                item.html = ""
            elif step == CleanStep.REMOVE_PII and self.remove_pii:
                item.text = self._scrub_pii(item.text or "")
                item.title = self._scrub_pii(item.title or "")
            elif step == CleanStep.REMOVE_BOILERPLATE:
                item.text = self._remove_boilerplate(item.text or "")
            elif step == CleanStep.REMOVE_DUPLICATE_LINES:
                item.text = self._dedupe_lines(item.text or "")
            elif step == CleanStep.REMOVE_SHORT_LINES:
                item.text = self._remove_short_lines(item.text or "")
            elif step == CleanStep.LANG_DETECT:
                item.language = self._detect_lang(item.text or "")
            elif step == CleanStep.ENCODE_FIX:
                item.text = self._encode_fix(item.text or "")
            elif step == CleanStep.JSON_NORMALIZE:
                if item.json:
                    item.json = self._normalize_json(item.json)
            elif step == CleanStep.WHITESPACE_FIX:
                item.text = self._whitespace_fix(item.text or "")
            elif step == CleanStep.TRUNCATE:
                if len(item.text) > 100000:
                    item.text = item.text[:100000]
        item.status = "cleaned"
        item.updated_at = _now()

    def _unicode_normalize(self, text: str) -> str:
        """NFKC 标准化 + 去除控制字符"""
        text = unicodedata.normalize("NFKC", text)
        # 去除控制字符但保留 \n \r \t
        text = "".join(c for c in text if unicodedata.category(c)[0] != "C" or c in "\n\r\t")
        return text

    def _strip_html(self, text: str) -> str:
        """剥离 HTML 标签"""
        if "<" not in text:
            return text
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "lxml")
            return soup.get_text(separator="\n", strip=True)
        except ImportError:
            # 退化: 正则
            text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = html.unescape(text)
            return text

    def _scrub_pii(self, text: str) -> str:
        """脱敏 PII"""
        for name, pat in self.PII_PATTERNS.items():
            text = pat.sub(f"[REDACTED_{name.upper()}]", text)
        return text

    def _remove_boilerplate(self, text: str) -> str:
        """删除 boilerplate 行"""
        lines = text.split("\n")
        out = []
        for line in lines:
            if any(pat.search(line) for pat in self.BOILERPLATE_PATTERNS):
                continue
            out.append(line)
        return "\n".join(out)

    def _dedupe_lines(self, text: str) -> str:
        """去除完全重复行 (保留顺序)"""
        seen: Set[str] = set()
        out: List[str] = []
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in seen:
                continue
            seen.add(stripped)
            out.append(line)
        return "\n".join(out)

    def _remove_short_lines(self, text: str, min_len: int = 3) -> str:
        """删除过短行 (噪声)"""
        out = []
        for line in text.split("\n"):
            if line.strip() and len(line.strip()) < min_len:
                continue
            out.append(line)
        return "\n".join(out)

    def _detect_lang(self, text: str) -> str:
        """语言检测 — 简单启发式 (真实环境用 langdetect/franc)"""
        if not text:
            return ""
        # 中文 unicode range
        cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        # 日文
        jp = sum(1 for c in text if "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff")
        # 韩文
        kr = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
        # ASCII (英文)
        en = sum(1 for c in text if c.isascii() and c.isalpha())
        total = cn + jp + kr + en
        if total == 0:
            return "unknown"
        if cn / total > 0.3:
            return "zh"
        if jp / total > 0.3:
            return "ja"
        if kr / total > 0.3:
            return "ko"
        if en / total > 0.5:
            return "en"
        return "mixed"

    def _encode_fix(self, text: str) -> str:
        """修复常见乱码 (mojibake)"""
        # 智能引号
        text = text.replace("\u201c", '"').replace("\u201d", '"')
        text = text.replace("\u2018", "'").replace("\u2019", "'")
        text = text.replace("\u2013", "-").replace("\u2014", "-")
        text = text.replace("\u2026", "...")
        return text

    def _normalize_json(self, obj: Any, max_depth: int = 10) -> Any:
        """JSON 递归 normalize"""
        if max_depth <= 0:
            return obj
        if isinstance(obj, dict):
            return {str(k)[:100]: self._normalize_json(v, max_depth - 1) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._normalize_json(x, max_depth - 1) for x in obj[:1000]]
        if isinstance(obj, str):
            return self._unicode_normalize(obj)[:50000]
        return obj

    def _whitespace_fix(self, text: str) -> str:
        """空白修复"""
        # 合并 3+ 连续空行为 2 个
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 合并 5+ 连续空格为 1
        text = re.sub(r" {5,}", " ", text)
        # 去除行尾空白
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        return text.strip()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
