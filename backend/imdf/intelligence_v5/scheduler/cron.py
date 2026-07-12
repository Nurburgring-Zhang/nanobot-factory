"""智影 V5 — Cron 定时调度器

迁移自 Hermes Agent:
- 普通英语描述周期
- 任务短小可中断
- 输出固定目的地
- 兜底 Cron 做健康巡检
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    """Cron 任务"""

    name: str
    schedule: str  # cron 表达式 或 英语描述
    action: str  # "run_skill" | "send_message" | "check_health" | ...
    params: Dict[str, Any] = field(default_factory=dict)
    job_id: str = field(default_factory=lambda: f"cj-{uuid.uuid4().hex[:10]}")
    enabled: bool = True
    description: str = ""
    last_run: float = 0.0
    last_status: str = ""  # success/failed/skipped
    next_run: float = 0.0
    run_count: int = 0
    fail_count: int = 0
    created_at: float = 0.0


class CronParser:
    """Cron 解析 — 支持 cron 表达式 + 英语自然语言"""

    # 5 段 cron: minute hour day-of-month month day-of-week
    CRON_RE = re.compile(
        r"^\s*(?P<minute>\S+)\s+(?P<hour>\S+)\s+(?P<dom>\S+)\s+(?P<month>\S+)\s+(?P<dow>\S+)\s*$"
    )

    # 英语自然语言映射
    NL_PATTERNS: List[Tuple[re.Pattern, str]] = [
        (re.compile(r"every\s+(\d+)\s*minute", re.I), "*/{0} * * * *"),
        (re.compile(r"every\s+(\d+)\s*hour", re.I), "0 */{0} * * *"),
        (re.compile(r"every\s+hour", re.I), "0 * * * *"),
        (re.compile(r"every\s+day\s+at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.I), "{hour} {minute} * * *"),
        (re.compile(r"every\s+morning", re.I), "0 8 * * *"),
        (re.compile(r"every\s+evening", re.I), "0 18 * * *"),
        (re.compile(r"every\s+midnight", re.I), "0 0 * * *"),
        (re.compile(r"every\s+(\d+)\s*day", re.I), "0 0 */{0} * *"),
        (re.compile(r"every\s+week", re.I), "0 0 * * 0"),
        (re.compile(r"every\s+monday", re.I), "0 9 * * 1"),
        (re.compile(r"every\s+friday", re.I), "0 17 * * 5"),
        (re.compile(r"every\s+month", re.I), "0 0 1 * *"),
    ]

    @classmethod
    def parse(cls, schedule: str) -> str:
        """自然语言 → cron 表达式"""
        s = schedule.strip()
        # 已是 cron 表达式?
        if cls.CRON_RE.match(s):
            return s
        # 试 NL 匹配
        for pat, tmpl in cls.NL_PATTERNS:
            m = pat.search(s)
            if m:
                groups = m.groups()
                if "{0}" in tmpl and groups:
                    return tmpl.format(*groups)
                # 特殊: 每天 HH:MM
                if "every day at" in s.lower():
                    h = int(groups[0])
                    m_min = int(groups[1] or 0)
                    am_pm = (groups[2] or "").lower()
                    if am_pm == "pm" and h < 12:
                        h += 12
                    if am_pm == "am" and h == 12:
                        h = 0
                    return f"{m_min} {h} * * *"
                return tmpl
        # 默认 1 小时
        return "0 * * * *"

    @classmethod
    def next_run_after(cls, cron_expr: str, after_ts: float) -> float:
        """计算下一次执行时间"""
        parsed = cls._parse_cron(cron_expr)
        if not parsed:
            return after_ts + 3600
        minute, hour, dom, month, dow = parsed
        # 简化: 不严格按 cron 算法, 而是匹配下一个匹配的 hour:minute
        now = datetime.fromtimestamp(after_ts, tz=timezone.utc)
        for delta_minutes in range(60 * 24 + 1):  # 最多找 24h
            candidate = now.timestamp() + delta_minutes * 60
            dt = datetime.fromtimestamp(candidate, tz=timezone.utc)
            if cls._matches(dt, minute, hour, dom, month, dow):
                return candidate
        return after_ts + 86400  # 24h 后

    @classmethod
    def _parse_cron(cls, expr: str) -> Optional[Tuple[Any, Any, Any, Any, Any]]:
        m = cls.CRON_RE.match(expr)
        if not m:
            return None
        return (
            cls._parse_field(m.group("minute"), 0, 59),
            cls._parse_field(m.group("hour"), 0, 23),
            cls._parse_field(m.group("dom"), 1, 31),
            cls._parse_field(m.group("month"), 1, 12),
            cls._parse_field(m.group("dow"), 0, 6),
        )

    @classmethod
    def _parse_field(cls, field: str, min_v: int, max_v: int) -> Any:
        """解析单个字段 — 支持 * / N / N-M / N,M / */N"""
        if field == "*":
            return list(range(min_v, max_v + 1))
        if field.startswith("*/"):
            step = int(field[2:])
            return list(range(min_v, max_v + 1, step))
        if "-" in field:
            a, b = field.split("-")
            return list(range(int(a), int(b) + 1))
        if "," in field:
            return [int(x) for x in field.split(",")]
        return [int(field)]

    @classmethod
    def _matches(cls, dt: datetime, minute: Any, hour: Any, dom: Any, month: Any, dow: Any) -> bool:
        if minute != "*" and isinstance(minute, list) and dt.minute not in minute:
            return False
        if hour != "*" and isinstance(hour, list) and dt.hour not in hour:
            return False
        if dom != "*" and isinstance(dom, list) and dt.day not in dom:
            return False
        if month != "*" and isinstance(month, list) and dt.month not in month:
            return False
        if dow != "*" and isinstance(dow, list) and dt.weekday() not in dow:
            return False
        return True


class CronScheduler:
    """Cron 调度器"""

    def __init__(self):
        self.jobs: Dict[str, CronJob] = {}
        self.handlers: Dict[str, Callable] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.metrics: Dict[str, int] = {"total": 0, "success": 0, "failed": 0}

    def add_job(
        self,
        name: str,
        schedule: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        description: str = "",
    ) -> CronJob:
        cron_expr = CronParser.parse(schedule)
        job = CronJob(
            name=name,
            schedule=schedule,
            action=action,
            params=params or {},
            description=description,
            created_at=time.time(),
            next_run=CronParser.next_run_after(cron_expr, time.time()),
        )
        self.jobs[job.job_id] = job
        logger.info(f"Cron job added: {name} [{job.job_id}] schedule='{schedule}' (cron: '{cron_expr}') next_run={job.next_run}")
        return job

    def add_nl_job(self, name: str, english_schedule: str, action: str, params: Optional[Dict[str, Any]] = None) -> CronJob:
        """英语自然语言 schedule"""
        return self.add_job(name, english_schedule, action, params)

    def remove_job(self, job_id: str) -> bool:
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False

    def list_jobs(self) -> List[CronJob]:
        return list(self.jobs.values())

    def register_handler(self, action: str, handler: Callable):
        self.handlers[action] = handler

    async def start(self):
        """启动调度循环"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Cron scheduler started")

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Cron scheduler stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.exception(f"Cron loop error: {e}")
            await asyncio.sleep(30)  # 30 秒检查一次

    async def _tick(self):
        now = time.time()
        for job in list(self.jobs.values()):
            if not job.enabled:
                continue
            if job.next_run > 0 and now >= job.next_run:
                await self._run_job(job)

    async def _run_job(self, job: CronJob):
        """执行单个 job"""
        self.metrics["total"] += 1
        try:
            handler = self.handlers.get(job.action)
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    await handler(job.params)
                else:
                    handler(job.params)
                job.last_status = "success"
                self.metrics["success"] += 1
            else:
                logger.warning(f"No handler for action: {job.action}")
                job.last_status = "skipped"
            job.run_count += 1
        except Exception as e:
            self.metrics["failed"] += 1
            job.fail_count += 1
            job.last_status = f"failed: {e}"
            logger.exception(f"Cron job {job.name} failed: {e}")
        finally:
            job.last_run = time.time()
            cron_expr = CronParser.parse(job.schedule)
            job.next_run = CronParser.next_run_after(cron_expr, time.time())

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_jobs": len(self.jobs),
            "enabled_jobs": sum(1 for j in self.jobs.values() if j.enabled),
            "metrics": self.metrics,
        }


cron_scheduler = CronScheduler()
