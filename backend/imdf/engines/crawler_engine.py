"""P19-B4: CrawlerEngine — 83 渠道爬虫统一调度引擎 (V5 第 15 章)

Wraps :mod:`data_collection_engine` (the in-process crawler/RSS/API job store)
and exposes a stateful, lifecycle-aware façade:

  * :meth:`start_crawl` / :meth:`stop` / :meth:`pause` / :meth:`resume`
  * :meth:`status` returns a uniform :class:`CrawlStatus` envelope
  * :meth:`metrics` returns jobs / pages / errors / throughput

Channel coverage reuses the existing helpers in ``data_collection_engine``:
``create_crawler_job``, ``update_crawler_job_status``, ``add_crawler_pages``,
``log_history``.  BaseCrawler protocol from P19-B3 plugs in via the
``channels`` registry — a channel is any object exposing
``async def crawl() -> AsyncIterator[Page]``.

This module is **stateless** across processes (the underlying state lives in
``collection_state.json`` + ``imdf.db``), but a single :class:`CrawlerEngine`
instance is **stateful** in the sense that it tracks the live ``running`` /
``paused`` set of job ids in memory.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

# Wrap the existing engine — we don't re-implement the JSON / SQLite layer.
from . import data_collection_engine as _dce

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
#  Enums + dataclasses
# --------------------------------------------------------------------------- #
class CrawlJobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CrawlStatus:
    """Uniform status envelope for a single job."""

    job_id: str
    state: CrawlJobState
    name: str = ""
    source: str = ""
    pages_collected: int = 0
    errors: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "name": self.name,
            "source": self.source,
            "pages_collected": self.pages_collected,
            "errors": self.errors,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "extra": self.extra,
        }


@dataclass
class CrawlerMetrics:
    """Aggregate metrics across all crawler jobs."""

    jobs_total: int = 0
    jobs_running: int = 0
    jobs_paused: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    pages_total: int = 0
    errors_total: int = 0
    throughput_pages_per_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# --------------------------------------------------------------------------- #
#  BaseCrawler protocol (compatible with P19-B3)
# --------------------------------------------------------------------------- #
class BaseCrawler:
    """Lightweight protocol — any subclass with ``async def crawl`` works."""

    name: str = "base"

    async def crawl(self, config: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        """Yield ``Page`` dicts.  Override in concrete subclasses."""
        raise NotImplementedError
        yield {}  # pragma: no cover — keeps this an AsyncIterator for type-checkers


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class CrawlerEngine:
    """Stateful façade around :mod:`data_collection_engine`.

    The engine is **process-singleton-safe** but intentionally NOT a
    module-level singleton — callers control the lifetime::

        engine = CrawlerEngine()
        engine.register_channel("web", WebCrawler())
        job_id = engine.start_crawl(name="hn", url="https://news.ycombinator.com")
        ...
        engine.stop(job_id)
    """

    # Five well-known channels — P19-B3 wires concrete subclasses here.
    DEFAULT_CHANNELS = ("web", "api", "rss", "search", "social")

    def __init__(self) -> None:
        self._channels: Dict[str, BaseCrawler] = {}
        self._live_jobs: Dict[str, CrawlJobState] = {}
        self._lock = threading.RLock()
        self._started_at = datetime.now().isoformat()
        self._state: str = "idle"  # idle / running / paused / stopped

    # ── Lifecycle (matches the other V5 engines) ────────────────────
    def start(self) -> None:
        with self._lock:
            self._state = "running"

    def stop(self) -> None:
        """Mark the engine stopped and stop every live job."""
        with self._lock:
            self._state = "stopped"
            live = list(self._live_jobs.items())
        for job_id, _ in live:
            try:
                self.stop_job(job_id)
            except Exception:
                # Best-effort shutdown — never raise out of stop().
                pass

    def pause(self) -> None:
        with self._lock:
            if self._state == "running":
                self._state = "paused"

    def resume(self) -> None:
        with self._lock:
            if self._state == "paused":
                self._state = "running"

    def status(self, job_id: Optional[str] = None) -> Any:
        """Return the engine-level status (when called without args) or
        a per-job :class:`CrawlStatus` (when ``job_id`` is given)."""
        if job_id is None:
            with self._lock:
                running = any(
                    s == CrawlJobState.RUNNING for s in self._live_jobs.values()
                )
                paused = any(
                    s == CrawlJobState.PAUSED for s in self._live_jobs.values()
                )
                # The engine-level state wins when no live jobs are running.
                if running:
                    state = "running"
                elif paused:
                    state = "paused"
                elif self._live_jobs:
                    state = "stopped"
                else:
                    state = self._state
                return {
                    "state": state,
                    "engine_state": self._state,
                    "channels": sorted(self._channels.keys()),
                    "live_jobs": len(self._live_jobs),
                }

        state = _dce._load_state()
        job: Optional[Dict[str, Any]] = None
        for j in state.get("crawler_jobs", []):
            if j.get("id") == job_id:
                job = j
                break

        with self._lock:
            live_state = self._live_jobs.get(job_id, CrawlJobState.PENDING)

        if job is None:
            return CrawlStatus(
                job_id=job_id,
                state=live_state,
                extra={"note": "job not persisted yet"},
            )

        raw_state = (job.get("status") or "pending").lower()
        try:
            persisted_state = CrawlJobState(raw_state)
        except ValueError:
            persisted_state = CrawlJobState.PENDING

        # The in-memory state is authoritative for RUNNING/PAUSED/STOPPED.
        effective = live_state if live_state in (
            CrawlJobState.RUNNING,
            CrawlJobState.PAUSED,
            CrawlJobState.STOPPED,
        ) else persisted_state

        return CrawlStatus(
            job_id=job_id,
            state=effective,
            name=job.get("name", ""),
            source=job.get("url", job.get("source", "")),
            pages_collected=int(job.get("items_collected", job.get("pages_collected", 0))),
            errors=int(job.get("errors", 0)),
            started_at=job.get("started_at"),
            finished_at=job.get("finished_at"),
            extra={"channel": job.get("channel", "")},
        )

    # ── Channel registry ────────────────────────────────────────────
    def register_channel(self, name: str, crawler: BaseCrawler) -> None:
        """Bind a :class:`BaseCrawler` under ``name``.

        The registry is in-memory; reload it per-process.  The JSON /
        SQLite layer in :mod:`data_collection_engine` persists the
        *job* state, not the channel implementations.
        """
        if not name or not isinstance(name, str):
            raise ValueError(f"channel name must be a non-empty string, got {name!r}")
        if not isinstance(crawler, BaseCrawler):
            raise TypeError(
                f"crawler must subclass BaseCrawler, got {type(crawler).__name__}"
            )
        with self._lock:
            self._channels[name] = crawler
        logger.info("CrawlerEngine registered channel %s (%s)", name, type(crawler).__name__)

    def list_channels(self) -> List[str]:
        with self._lock:
            return sorted(self._channels.keys())

    # ── Job lifecycle ───────────────────────────────────────────────
    def start_crawl(
        self,
        name: str,
        url: str = "",
        channel: str = "web",
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Create + start a crawl job.  Returns the job id.

        Uses :func:`data_collection_engine.create_crawler_job` for
        persistence, then transitions the in-memory state to RUNNING.
        """
        if channel not in self._channels and channel not in self.DEFAULT_CHANNELS:
            # Allow starting jobs against not-yet-registered channels —
            # the channel will be looked up by the executor at runtime.
            logger.debug("channel %s not pre-registered; job will queue", channel)

        job = _dce.create_crawler_job(
            {
                "name": name,
                "url": url,
                "channel": channel,
                "config": config or {},
                **kwargs,
            }
        )
        job_id = job["job_id"]

        with self._lock:
            self._live_jobs[job_id] = CrawlJobState.RUNNING

        self._update_job_status(job_id, "running")
        _dce._log_history(
            {
                "type": "crawler_start",
                "source": name,
                "status": "running",
                "items_collected": 0,
                "duration": "",
                "job_id": job_id,
                "channel": channel,
            }
        )
        return job_id

    def pause_job(self, job_id: str) -> bool:
        """Pause a single running crawl job."""
        with self._lock:
            state = self._live_jobs.get(job_id)
            if state != CrawlJobState.RUNNING:
                return False
            self._live_jobs[job_id] = CrawlJobState.PAUSED
        self._update_job_status(job_id, "paused")
        _dce._log_history(
            {
                "type": "crawler_pause",
                "source": job_id,
                "status": "paused",
                "items_collected": 0,
                "duration": "",
                "job_id": job_id,
            }
        )
        return True

    def resume_job(self, job_id: str) -> bool:
        """Resume a single paused crawl job."""
        with self._lock:
            state = self._live_jobs.get(job_id)
            if state != CrawlJobState.PAUSED:
                return False
            self._live_jobs[job_id] = CrawlJobState.RUNNING
        self._update_job_status(job_id, "running")
        return True

    def stop_job(self, job_id: str) -> bool:
        """Stop a single crawl job."""
        with self._lock:
            state = self._live_jobs.get(job_id)
            if state not in (CrawlJobState.RUNNING, CrawlJobState.PAUSED):
                # Allow stopping already-finished jobs as a no-op.
                return state is not None
            self._live_jobs[job_id] = CrawlJobState.STOPPED
        self._update_job_status(job_id, "stopped")
        _dce._log_history(
            {
                "type": "crawler_stop",
                "source": job_id,
                "status": "stopped",
                "items_collected": 0,
                "duration": "",
                "job_id": job_id,
            }
        )
        return True

    def metrics(self) -> CrawlerMetrics:
        """Aggregate metrics across all known jobs."""
        state = _dce._load_state()
        jobs = state.get("crawler_jobs", [])
        history = state.get("history", [])

        m = CrawlerMetrics(jobs_total=len(jobs))
        for j in jobs:
            s = (j.get("status") or "pending").lower()
            if s == "running":
                m.jobs_running += 1
            elif s == "paused":
                m.jobs_paused += 1
            elif s in ("completed", "done"):
                m.jobs_completed += 1
            elif s == "failed":
                m.jobs_failed += 1
            m.pages_total += int(j.get("items_collected", j.get("pages_collected", 0)) or 0)
            m.errors_total += int(j.get("errors", 0) or 0)

        # Lightweight throughput: pages per sec over the engine's lifetime.
        # When 0 jobs ran, throughput is 0 (no fake division).
        if m.pages_total:
            started = datetime.fromisoformat(self._started_at)
            elapsed = max((datetime.now() - started).total_seconds(), 1.0)
            m.throughput_pages_per_sec = round(m.pages_total / elapsed, 4)

        # Use the live in-memory map to refine the running/paused counts.
        with self._lock:
            for state in self._live_jobs.values():
                if state == CrawlJobState.RUNNING:
                    m.jobs_running += 1
                elif state == CrawlJobState.PAUSED:
                    m.jobs_paused += 1

        return m

    # ── Convenience helpers ─────────────────────────────────────────
    def record_pages(self, job_id: str, count: int, errors: int = 0) -> None:
        """Update a job's page count + error count.

        Writes through to the underlying JSON state via
        ``_load_state`` / ``_save_state`` (private helpers re-used
        intentionally so we don't fork the persistence layer).
        """
        if count <= 0 and errors <= 0:
            return
        state = _dce._load_state()
        for j in state.get("crawler_jobs", []):
            if j.get("id") == job_id:
                j["items_collected"] = int(j.get("items_collected", 0)) + count
                j["errors"] = int(j.get("errors", 0)) + errors
                break
        _dce._save_state(state)

    def _update_job_status(self, job_id: str, status: str) -> None:
        """Internal: persist status change in the JSON store."""
        state = _dce._load_state()
        for j in state.get("crawler_jobs", []):
            if j.get("id") == job_id:
                j["status"] = status
                if status in ("running",) and not j.get("started_at"):
                    j["started_at"] = datetime.now().isoformat()
                if status in ("completed", "stopped", "failed"):
                    j["finished_at"] = datetime.now().isoformat()
                break
        _dce._save_state(state)

    def shutdown(self) -> None:
        """Stop every RUNNING / PAUSED job.  Idempotent."""
        with self._lock:
            live = list(self._live_jobs.items())
        for job_id, state in live:
            if state in (CrawlJobState.RUNNING, CrawlJobState.PAUSED):
                self.stop_job(job_id)


__all__ = [
    "CrawlerEngine",
    "CrawlJobState",
    "CrawlStatus",
    "CrawlerMetrics",
    "BaseCrawler",
]