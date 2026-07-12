"""P19-V53: Vida action_executor — 主动行动执行器.

V5 第 26 章 § 26.3:
  * 7 种 action_type: summarize / reply / organize / search / remind / draft / analyze
  * 每个 action 是 async 方法, 返回 ActionResult
  * 支持 LLM 注入 (LLM 调用), 也可纯 mock
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol

from .schemas import Action, ActionResult, ActionStatus, ActionType

logger = logging.getLogger(__name__)


class LLMOptional(Protocol):
    """LLM 接口 — 可选; 不注入时用 deterministic mock 输出."""

    async def summarize(self, content: str, length: str = "short") -> str: ...

    async def generate_replies(self, message: str, context: str = "", n: int = 3) -> list: ...


class ActionExecutor:
    """执行 7 种主动行动."""

    def __init__(self, llm: Optional[LLMOptional] = None) -> None:
        self.llm = llm
        self._executions: list[ActionResult] = []

    @property
    def history(self) -> list[ActionResult]:
        """最近执行结果 (read-only snapshot)."""
        return list(self._executions)

    async def execute(self, action: Action) -> ActionResult:
        """分发到对应的 _<action_type> 方法."""
        start = time.perf_counter()
        result_id = f"res_{uuid.uuid4().hex[:8]}"
        result = ActionResult(
            result_id=result_id,
            action_id=action.action_id,
            action_type=action.action_type,
            status=ActionStatus.IN_PROGRESS,
        )

        handler = {
            ActionType.SUMMARIZE: self._summarize,
            ActionType.REPLY: self._suggest_reply,
            ActionType.ORGANIZE: self._organize_files,
            ActionType.SEARCH: self._search,
            ActionType.REMIND: self._set_reminder,
            ActionType.DRAFT: self._draft,
            ActionType.ANALYZE: self._analyze_data,
        }.get(action.action_type)

        if handler is None:
            result.success = False
            result.status = ActionStatus.FAILED
            result.error = f"Unknown action_type: {action.action_type}"
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            self._executions.append(result)
            return result

        try:
            payload = await handler(action.parameters)
            result.success = True
            result.status = ActionStatus.COMPLETED
            result.result = payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("Vida action %s failed: %s", action.action_type, exc)
            result.success = False
            result.status = ActionStatus.FAILED
            result.error = str(exc)

        result.duration_ms = int((time.perf_counter() - start) * 1000)
        self._executions.append(result)
        return result

    # ── 7 action handlers ───────────────────────────────────────────
    async def _summarize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """summarize — 总结当前内容."""
        content = str(params.get("content", ""))
        length = str(params.get("length", "short"))
        if self.llm is not None:
            summary = await self.llm.summarize(content, length)
        else:
            # Deterministic mock — 取首句 + 字数统计
            summary = (content[:120] + "...") if len(content) > 120 else content
            summary = f"[mock-summary | {length}] {summary}"
        return {"summary": summary, "length": length, "src_chars": len(content)}

    async def _suggest_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """reply — 生成回复建议."""
        message = str(params.get("message", ""))
        context = str(params.get("context", ""))
        n = int(params.get("n", 3))
        if self.llm is not None:
            replies = await self.llm.generate_replies(message, context, n=n)
        else:
            replies = [
                f"Mock reply #{i+1} to: {message[:50]}"
                for i in range(n)
            ]
        return {"replies": list(replies), "count": len(replies)}

    async def _organize_files(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """organize — 整理文件 (mock — 不实际移动)."""
        files = list(params.get("files", []))
        # mock 按扩展名分组
        groups: Dict[str, list] = {}
        for f in files:
            ext = f.rsplit(".", 1)[-1] if "." in f else "other"
            groups.setdefault(ext, []).append(f)
        return {"groups": groups, "total": len(files)}

    async def _search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """search — 搜索 (mock — 返回 deterministic 结果)."""
        query = str(params.get("query", ""))
        # mock: 5 条结果, 全部包含 query (lowercased)
        results = [
            {"rank": i + 1, "title": f"Mock result {i+1} for '{query}'",
             "url": f"https://example.com/{i+1}"}
            for i in range(5)
        ]
        return {"query": query, "results": results}

    async def _set_reminder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """remind — 设置提醒 (mock)."""
        when = str(params.get("when", "now"))
        message = str(params.get("message", ""))
        return {"reminder_id": f"rem_{uuid.uuid4().hex[:6]}", "when": when, "message": message}

    async def _draft(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """draft — 起草内容 (邮件/消息)."""
        template = str(params.get("template", "blank"))
        subject = str(params.get("subject", ""))
        body_lines = [
            f"[mock-draft | template={template}]",
            f"Subject: {subject}",
            "",
            "Hi,",
            "",
            "Body auto-generated by Vida engine. Replace with real content.",
            "",
            "Best,",
        ]
        return {"subject": subject, "body": "\n".join(body_lines), "template": template}

    async def _analyze_data(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """analyze — 数据分析 (mock — 返回聚合指标)."""
        data = list(params.get("data", []))
        if not data:
            return {"count": 0, "summary": "empty input"}
        # mock: 简单的统计
        nums = [x for x in data if isinstance(x, (int, float))]
        if nums:
            avg = sum(nums) / len(nums)
            summary = {"count": len(data), "numeric_count": len(nums), "avg": round(avg, 3),
                       "min": min(nums), "max": max(nums)}
        else:
            summary = {"count": len(data), "sample": data[:3]}
        return summary


__all__ = ["ActionExecutor", "LLMOptional"]