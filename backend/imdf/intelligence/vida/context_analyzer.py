"""P19-V53: Vida context_analyzer — 屏幕内容 → 结构化上下文.

V5 第 26 章 § 26.2:
  * 6 大场景识别 (code/chat/document/research/email/terminal)
  * 关键字→场景的关键词表
  * 提取 key_info (URL, code_snippet, file_name, recipient 等)
  * 文本截断 500 chars (避免 LLM 输入超长)
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from .schemas import Context, Scenario, ScreenData

logger = logging.getLogger(__name__)


# 6 大场景的关键词表 (lowercase substring match)
SCENARIO_KEYWORDS: Dict[Scenario, List[str]] = {
    Scenario.CODE: [
        "vscode", "pycharm", "cursor", "claude code", "codex", "intellij",
        "sublime", "vim", "emacs", "atom", "webstorm", "rider", "xcode",
    ],
    Scenario.CHAT: [
        "wechat", "微信", "slack", "discord", "telegram", "whatsapp",
        "signal", "line", "messenger", "teams",
    ],
    Scenario.DOCUMENT: [
        "word", "notion", "obsidian", "飞书", "feishu", "google docs",
        "pages", "libreoffice", "wps", "evernote", "onenote",
    ],
    Scenario.RESEARCH: [
        "chrome", "firefox", "safari", "edge", "brave", "browser",
        "opera", "vivaldi",
    ],
    Scenario.EMAIL: [
        "mail", "outlook", "gmail", "thunderbird", "foxmail", "spark",
        "网易邮箱", "qq邮箱", "新浪邮箱",
    ],
    Scenario.TERMINAL: [
        "terminal", "iterm", "cmd", "command", "bash", "zsh", "powershell",
        "windows terminal", "warp", "alacritty", "kitty",
    ],
}


# URL / email / file 正则 (用于 key_info 提取)
URL_RE = re.compile(r"https?://[^\s\"'>]+")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
FILE_RE = re.compile(r"(?:[\w\-./\\]+\.(?:py|js|ts|tsx|jsx|java|go|rs|cpp|c|h|cs|rb|php|sh|sql|md|json|ya?ml|toml))", re.IGNORECASE)


class ContextAnalyzer:
    """上下文分析器 — 6 场景识别 + key_info 提取."""

    TEXT_TRUNCATE = 500

    def __init__(self, *, scenario_overrides: Optional[Dict[str, Scenario]] = None,
                 text_extractor: Optional[Callable[[ScreenData], str]] = None) -> None:
        """scenario_overrides: 测试用 — { "appname": Scenario.X } 强制覆盖.
        text_extractor:     测试用 — 自定义文本提取 (默认从 ScreenData.extra 取).
        """
        self.scenario_overrides: Dict[str, Scenario] = {
            k.lower(): v for k, v in (scenario_overrides or {}).items()
        }
        self._text_extractor = text_extractor or self._default_text_extractor

    async def analyze(self, screen_data: ScreenData, user_id: str) -> Context:
        """分析屏幕抓拍 → Context."""
        text = self._text_extractor(screen_data)
        text = text[: self.TEXT_TRUNCATE]
        scenario = self._identify_scenario(screen_data.active_app, text)
        key_info = self._extract_key_info(text, scenario)
        language = self._detect_language(text)

        return Context(
            screen_id=screen_data.screen_id,
            user_id=user_id,
            app=screen_data.active_app,
            scenario=scenario,
            text=text,
            key_info=key_info,
            language=language,
            timestamp=screen_data.timestamp,
        )

    # ── Scenario identification ─────────────────────────────────────
    def _identify_scenario(self, app: str, text: str) -> Scenario:
        """按 active_app + text 匹配 6 大场景; overrides 优先."""
        app_lower = (app or "").lower()
        text_lower = (text or "").lower()

        # 1. overrides
        if app_lower in self.scenario_overrides:
            return self.scenario_overrides[app_lower]

        # 2. 按 active_app 匹配
        for scenario, keywords in SCENARIO_KEYWORDS.items():
            for kw in keywords:
                if kw in app_lower:
                    return scenario

        # 3. fallback: text 匹配
        for scenario, keywords in SCENARIO_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return scenario

        return Scenario.CODE  # 最常见的兜底

    # ── key_info extraction ─────────────────────────────────────────
    def _extract_key_info(self, text: str, scenario: Scenario) -> Dict[str, Any]:
        """根据场景提取不同的 key_info."""
        urls = URL_RE.findall(text or "")[:5]
        emails = EMAIL_RE.findall(text or "")[:5]
        files = FILE_RE.findall(text or "")[:10]

        info: Dict[str, Any] = {
            "urls": urls,
            "emails": emails,
            "files": files,
        }

        # 场景专属
        if scenario == Scenario.CODE:
            # 找函数定义 / import / class
            code_hints: List[str] = []
            for pat in (r"def\s+(\w+)", r"class\s+(\w+)", r"import\s+([\w.]+)", r"from\s+([\w.]+)\s+import"):
                code_hints.extend(re.findall(pat, text or ""))
            info["code_symbols"] = code_hints[:10]
        elif scenario == Scenario.EMAIL:
            # 简单 subject 启发
            m = re.search(r"Subject:\s*(.+?)(?:\n|$)", text or "", re.IGNORECASE)
            if m:
                info["subject"] = m.group(1).strip()
        elif scenario == Scenario.CHAT:
            # 简单 nickname 启发: "昵称:" 格式
            nicknames = re.findall(r"^([\w\u4e00-\u9fff]{2,20}):", text or "", re.MULTILINE)
            info["participants"] = list(set(nicknames))[:10]
        elif scenario == Scenario.RESEARCH:
            info["page_url"] = urls[0] if urls else ""
        elif scenario == Scenario.TERMINAL:
            # 找最近的命令
            m = re.search(r"\$ ([^\n]+)", text or "")
            if m:
                info["last_command"] = m.group(1).strip()

        return info

    @staticmethod
    def _detect_language(text: str) -> str:
        """粗粒度语言检测 — 中文 vs 英文."""
        if not text:
            return "en"
        cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if cjk > len(text) * 0.3 else "en"

    @staticmethod
    def _default_text_extractor(screen_data: ScreenData) -> str:
        """默认文本提取 — 实际生产环境会用 OCR; 这里从 extra.text 取 (mock)."""
        if isinstance(screen_data.extra, dict):
            return str(screen_data.extra.get("text", ""))
        return ""


__all__ = ["ContextAnalyzer", "SCENARIO_KEYWORDS"]