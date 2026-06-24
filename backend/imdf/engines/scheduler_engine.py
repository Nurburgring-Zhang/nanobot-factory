"""
Phase3: Scheduler Engine — Agent主动驱动 (Cron/定时任务)
===================================================
基于APScheduler的定时任务管理:
  - 支持cron表达式 (APScheduler CronTrigger)
  - 任务持久化: SQLite (SQLAlchemyJobStore) + JSON定义备份
  - 任务执行历史 + 重试次数追踪
  - 失败通知回调
  - 预置Agent任务 (数据清理/向量刷新/审美更新/健康自检)

Singleton via get_scheduler().

APScheduler job callable 必须可pickle → 使用模块级函数 _run_scheduled_job.
"""

from __future__ import annotations

import uuid
import json
import sqlite3
import logging
import traceback
import asyncio
import time as _time
import importlib
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ============================================================================
# Module-level registry for APScheduler (picklable)
# ============================================================================
# APScheduler需要可pickle的callable → 模块级函数+字符串引用
# Job definitions are stored here so the module-level wrapper can find them.

_JOB_REGISTRY: Dict[str, JobDefinition] = {}
_FAILURE_CALLBACKS: List[Callable] = []  # (will fire on failure, best-effort)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class JobDefinition:
    """定时任务定义"""
    id: str = ""
    name: str = ""
    func_path: str = ""
    trigger_type: str = "cron"
    trigger_config: dict = field(default_factory=dict)
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60
    notify_on_failure: bool = True
    created_at: str = ""
    last_run: Optional[str] = None
    last_status: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "func_path": self.func_path,
            "trigger_type": self.trigger_type,
            "trigger_config": self.trigger_config,
            "args": self.args,
            "kwargs": self.kwargs,
            "enabled": self.enabled,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "notify_on_failure": self.notify_on_failure,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "last_status": self.last_status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> JobDefinition:
        return cls(**{k: d.get(k, v.default if v.default is not field(default_factory=dict) else ({} if k == "trigger_config" else ([] if k in ("args",) else {})))
                       for k, v in cls.__dataclass_fields__.items()})


@dataclass
class JobHistory:
    """任务执行历史记录"""
    id: str = ""
    job_id: str = ""
    job_name: str = ""
    run_at: str = ""
    status: str = "running"
    result: str = ""
    error: str = ""
    retry_count: int = 0
    duration_ms: int = 0


# ============================================================================
# Module-level APScheduler Job Callable (MUST be picklable!)
# ============================================================================

async def _run_scheduled_job(job_id: str):
    """模块级函数 — APScheduler使用的可pickle的job callable.

    从 _JOB_REGISTRY 查找任务定义, 执行重试逻辑, 写入历史记录.
    """
    from engines.scheduler_engine import _JOB_REGISTRY, _FAILURE_CALLBACKS

    job_def = _JOB_REGISTRY.get(job_id)
    if not job_def:
        logger.error(f"Job not found in registry: {job_id}")
        return

    history_id = str(uuid.uuid4())
    run_at = datetime.now().isoformat()
    start_time = _time.time()

    history = JobHistory(
        id=history_id,
        job_id=job_def.id,
        job_name=job_def.name,
        run_at=run_at,
        status="running",
    )
    _record_history_sync(history)

    attempts = 0
    last_error = ""

    while attempts <= job_def.max_retries:
        try:
            # Resolve function path → callable
            parts = job_def.func_path.split(".")
            if len(parts) < 2:
                raise ValueError(f"Invalid func_path: {job_def.func_path}")
            module_path = ".".join(parts[:-1])
            attr_name = parts[-1]
            module = importlib.import_module(module_path)
            func = getattr(module, attr_name)

            # Execute
            result = func(*job_def.args, **job_def.kwargs)
            # If result is a coroutine, await it
            if asyncio.iscoroutine(result):
                result = await result
            result_str = str(result)[:1000] if result is not None else "ok"

            elapsed_ms = int((_time.time() - start_time) * 1000)
            history.status = "success"
            history.result = result_str
            history.retry_count = attempts
            history.duration_ms = elapsed_ms
            _record_history_sync(history)

            job_def.last_run = run_at
            job_def.last_status = "success"
            _save_job_defs()

            logger.info(f"Job '{job_def.name}' completed (attempt={attempts+1}, {elapsed_ms}ms)")
            return

        except Exception as e:
            attempts += 1
            last_error = f"{type(e).__name__}: {str(e)}"

            if attempts <= job_def.max_retries:
                logger.warning(
                    f"Job '{job_def.name}' failed (attempt {attempts}/{job_def.max_retries+1}), "
                    f"retrying in {job_def.retry_delay}s: {e}"
                )
                await asyncio.sleep(job_def.retry_delay)
            else:
                logger.error(f"Job '{job_def.name}' failed after {attempts} attempts: {e}")

    # All retries exhausted
    elapsed_ms = int((_time.time() - start_time) * 1000)
    history.status = "failed"
    history.error = last_error[:2000]
    history.retry_count = attempts - 1
    history.duration_ms = elapsed_ms
    _record_history_sync(history)

    job_def.last_run = run_at
    job_def.last_status = "failed"
    _save_job_defs()

    # Failure notifications (best-effort)
    if job_def.notify_on_failure:
        for cb in _FAILURE_CALLBACKS:
            try:
                cb(history)
            except Exception as e:
                logger.error(f"Operation failed: {e}")


# ============================================================================
# History persistence (module-level helpers)
# ============================================================================

_HISTORY_DB_PATH = "data/scheduler_history.db"

def _get_history_db_path() -> str:
    return _HISTORY_DB_PATH

def _set_history_db_path(p: str):
    global _HISTORY_DB_PATH
    _HISTORY_DB_PATH = p

def _init_history_db():
    conn = sqlite3.connect(_HISTORY_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_history (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            job_name TEXT NOT NULL,
            run_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            result TEXT DEFAULT '',
            error TEXT DEFAULT '',
            retry_count INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_job_id ON job_history(job_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_history_run_at ON job_history(run_at)")
    conn.commit()
    conn.close()

def _record_history_sync(history: JobHistory):
    try:
        conn = sqlite3.connect(_HISTORY_DB_PATH)
        conn.execute("""
            INSERT OR REPLACE INTO job_history
            (id, job_id, job_name, run_at, status, result, error, retry_count, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (history.id, history.job_id, history.job_name, history.run_at,
              history.status, history.result[:1000], history.error[:2000],
              history.retry_count, history.duration_ms))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to record history: {e}")

# ============================================================================
# Job definition persistence (JSON)
# ============================================================================

_DEFS_FILE = "data/scheduler_jobs.json"

def _load_job_defs() -> Dict[str, JobDefinition]:
    global _DEFS_FILE
    path = Path(_DEFS_FILE)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return {jid: JobDefinition.from_dict(d) for jid, d in data.items()}
    except Exception as e:
        logger.warning(f"Failed to load job definitions: {e}")
        return {}

def _save_job_defs():
    global _DEFS_FILE, _JOB_REGISTRY
    path = Path(_DEFS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = {jid: jd.to_dict() for jid, jd in _JOB_REGISTRY.items()}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error(f"Failed to save job definitions: {e}")


# ============================================================================
# Scheduler Engine
# ============================================================================

class SchedulerEngine:
    """定时任务调度引擎"""

    def __init__(self, db_path: str = "data/scheduler.db",
                 history_db_path: str = "data/scheduler_history.db"):
        global _DEFS_FILE, _HISTORY_DB_PATH

        self._db_path = db_path
        _HISTORY_DB_PATH = history_db_path
        _DEFS_FILE = db_path.replace(".db", "_jobs.json")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _init_history_db()

        # Load saved job definitions
        saved = _load_job_defs()
        for jid, jd in saved.items():
            _JOB_REGISTRY[jid] = jd

        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{db_path}')
        }
        executors = {
            'default': ThreadPoolExecutor(10),
        }
        job_defaults = {
            'coalesce': True,
            'max_instances': 3,
            'misfire_grace_time': 300,
        }

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )

        # Re-register saved jobs in APScheduler
        self._restore_jobs(saved)

        logger.info(f"SchedulerEngine created (db={db_path}, saved_jobs={len(saved)})")

    def _restore_jobs(self, saved: Dict[str, JobDefinition]):
        """在APScheduler中恢复已持久化的任务"""
        for jid, jd in saved.items():
            if not jd.enabled:
                continue
            try:
                trigger = self._build_trigger(jd)
                self._scheduler.add_job(
                    _run_scheduled_job,
                    trigger=trigger,
                    id=jd.id,
                    name=jd.name,
                    args=[jd.id],
                    replace_existing=True,
                )
                if not jd.enabled:
                    self._scheduler.pause_job(jd.id)
            except Exception as e:
                logger.warning(f"Failed to restore job '{jd.name}': {e}")

    @staticmethod
    def _build_trigger(job_def: JobDefinition):
        if job_def.trigger_type == "cron":
            cfg = dict(job_def.trigger_config or {})
            # R2.5-W4 兼容: 若传入了 "cron_expression" 字符串, 解析成 CronTrigger 字段
            if "cron_expression" in cfg and isinstance(cfg["cron_expression"], str):
                expr = cfg.pop("cron_expression").strip()
                parts = expr.split()
                if len(parts) != 5:
                    raise ValueError(f"cron_expression 必须 5 字段, 实得: {len(parts)}")
                minute, hour, day, month, dow = parts
                # 通配符 * 替换为 None 让 CronTrigger 走通配
                cfg.setdefault("minute", None if minute == "*" else minute)
                cfg.setdefault("hour", None if hour == "*" else hour)
                cfg.setdefault("day", None if day == "*" else day)
                cfg.setdefault("month", None if month == "*" else month)
                cfg.setdefault("day_of_week", None if dow == "*" else dow)
            return CronTrigger(**cfg)
        elif job_def.trigger_type == "interval":
            return IntervalTrigger(**job_def.trigger_config)
        elif job_def.trigger_type == "date":
            return DateTrigger(**job_def.trigger_config)
        else:
            raise ValueError(f"Unknown trigger_type: {job_def.trigger_type}")

    # ── Job Management ──────────────────────────────────────────────

    def add_job(self, job_def: JobDefinition) -> str:
        global _JOB_REGISTRY

        if not job_def.id:
            job_def.id = str(uuid.uuid4())
        if not job_def.created_at:
            job_def.created_at = datetime.now().isoformat()

        trigger = self._build_trigger(job_def)

        self._scheduler.add_job(
            _run_scheduled_job,
            trigger=trigger,
            id=job_def.id,
            name=job_def.name,
            args=[job_def.id],
            replace_existing=True,
        )

        if not job_def.enabled:
            self._scheduler.pause_job(job_def.id)

        _JOB_REGISTRY[job_def.id] = job_def
        _save_job_defs()

        logger.info(f"Job '{job_def.name}' added (id={job_def.id}, trigger={job_def.trigger_type})")
        return job_def.id

    def remove_job(self, job_id: str) -> bool:
        global _JOB_REGISTRY
        try:
            self._scheduler.remove_job(job_id)
        except Exception as e:
            logger.error(f"Operation failed: {e}")
        _JOB_REGISTRY.pop(job_id, None)
        _save_job_defs()
        logger.info(f"Job removed: {job_id}")
        return True

    def pause_job(self, job_id: str) -> bool:
        try:
            self._scheduler.pause_job(job_id)
            if job_id in _JOB_REGISTRY:
                _JOB_REGISTRY[job_id].enabled = False
                _save_job_defs()
            return True
        except Exception as e:
            logger.error(f"Failed to pause job {job_id}: {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        try:
            self._scheduler.resume_job(job_id)
            if job_id in _JOB_REGISTRY:
                _JOB_REGISTRY[job_id].enabled = True
                _save_job_defs()
            return True
        except Exception as e:
            logger.error(f"Failed to resume job {job_id}: {e}")
            return False

    def run_job_now(self, job_id: str) -> Optional[str]:
        """手动触发任务 (在后台创建asyncio task)"""
        if job_id not in _JOB_REGISTRY:
            return None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(_run_scheduled_job(job_id))
            else:
                loop.run_until_complete(_run_scheduled_job(job_id))
        except RuntimeError:
            asyncio.run(_run_scheduled_job(job_id))
        logger.info(f"Job triggered manually: {job_id}")
        return job_id

    def list_jobs(self) -> List[dict]:
        jobs = self._scheduler.get_jobs()
        result = []
        for j in jobs:
            jd = _JOB_REGISTRY.get(j.id)
            result.append({
                "id": j.id,
                "name": j.name,
                "next_run": str(j.next_run_time) if j.next_run_time else None,
                "trigger": jd.trigger_type if jd else "unknown",
                "trigger_config": jd.trigger_config if jd else {},
                "enabled": jd.enabled if jd else True,
                "max_retries": jd.max_retries if jd else 3,
                "last_run": jd.last_run if jd else None,
                "last_status": jd.last_status if jd else None,
                "func_path": jd.func_path if jd else "",
                "created_at": jd.created_at if jd else "",
            })
        return result

    def get_job(self, job_id: str) -> Optional[dict]:
        job = self._scheduler.get_job(job_id)
        if not job:
            return None
        jd = _JOB_REGISTRY.get(job_id)
        return {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else None,
            "trigger": jd.trigger_type if jd else "unknown",
            "trigger_config": jd.trigger_config if jd else {},
            "enabled": jd.enabled if jd else True,
            "max_retries": jd.max_retries if jd else 3,
            "retry_delay": jd.retry_delay if jd else 60,
            "notify_on_failure": jd.notify_on_failure if jd else True,
            "last_run": jd.last_run if jd else None,
            "last_status": jd.last_status if jd else None,
            "func_path": jd.func_path if jd else "",
            "args": jd.args if jd else [],
            "kwargs": jd.kwargs if jd else {},
            "created_at": jd.created_at if jd else "",
        }

    def get_history(self, job_id: Optional[str] = None,
                    limit: int = 50, offset: int = 0,
                    start: Optional[str] = None,
                    end: Optional[str] = None,
                    status: Optional[str] = None) -> List[dict]:
        """获取任务执行历史 — R2.5-W4: 支持 start/end/status 过滤

        参数:
            job_id:  按任务 ID 过滤
            limit:   每页条数 (默认 50)
            offset:  偏移量
            start:   ISO 日期字符串 (含), e.g. "2024-01-01"
            end:     ISO 日期字符串 (含), e.g. "2024-12-31"
            status:  success/failed/running/pending
        """
        conn = sqlite3.connect(_HISTORY_DB_PATH)
        conn.row_factory = sqlite3.Row

        # 动态构造 WHERE 子句
        where_clauses = []
        params: list = []
        if job_id:
            where_clauses.append("job_id = ?")
            params.append(job_id)
        if start:
            where_clauses.append("run_at >= ?")
            params.append(start)
        if end:
            # end 取 +1 天, 含 end 当天
            where_clauses.append("run_at < ?")
            params.append(end + "T23:59:59" if "T" not in end else end)
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"SELECT * FROM job_history {where_sql} ORDER BY run_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_history_count(self, job_id: Optional[str] = None) -> int:
        conn = sqlite3.connect(_HISTORY_DB_PATH)
        if job_id:
            count = conn.execute(
                "SELECT COUNT(*) FROM job_history WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
        else:
            count = conn.execute("SELECT COUNT(*) FROM job_history").fetchone()[0]
        conn.close()
        return count

    def add_failure_callback(self, callback: Callable):
        global _FAILURE_CALLBACKS
        _FAILURE_CALLBACKS.append(callback)

    # ── Lifecycle ───────────────────────────────────────────────────

    def start(self):
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("SchedulerEngine started")

    def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("SchedulerEngine stopped")

    @property
    def running(self) -> bool:
        return self._scheduler.running if self._scheduler else False


# ============================================================================
# Pre-built Agent Tasks (无参/少参可调用函数)
# ============================================================================

def task_data_cleanup():
    """预置任务: 数据清理 — 清理过期分享/临时文件 (每日凌晨3点)"""
    import os
    import shutil as _shutil

    cleaned = 0
    errors = 0

    sharing_dir = Path("data/sharing")
    if sharing_dir.exists():
        shares_file = sharing_dir / "shares.json"
        if shares_file.exists():
            try:
                shares = json.loads(shares_file.read_text())
                now = datetime.now()
                active = {}
                for token, share in shares.items():
                    expires_at = share.get("expires_at", "")
                    if expires_at:
                        try:
                            exp = datetime.fromisoformat(expires_at)
                            if exp < now:
                                cleaned += 1
                                continue
                        except Exception as e:
                            logger.error(f"Operation failed: {e}")
                    active[token] = share
                if cleaned > 0:
                    shares_file.write_text(json.dumps(active, ensure_ascii=False, indent=2))
            except Exception as e:
                errors += 1
                logger.error(f"Share cleanup error: {e}")

    tmp_dir = Path("data/tmp")
    if tmp_dir.exists():
        cutoff = datetime.now() - timedelta(hours=24)
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime)
                    if mtime < cutoff:
                        f.unlink()
                        cleaned += 1
                except Exception as e:
                    errors += 1
        for d in sorted(tmp_dir.rglob("*"), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                try:
                    d.rmdir()
                except Exception as e:
                    logger.error(f"Operation failed: {e}")

    result = {"cleaned_items": cleaned, "errors": errors}
    logger.info(f"Data cleanup completed: {result}")
    return result


def task_refresh_vector_index():
    """预置任务: 向量索引刷新 (每30分钟)"""
    try:
        from engines.vector_retrieval import MultimodalVectorEngine
        engine = MultimodalVectorEngine()
        stats = engine.get_index_stats()
        logger.info(f"Vector index refreshed: {stats}")
        return {"status": "ok", "stats": stats}
    except ImportError:
        logger.warning("Vector retrieval engine not available")
        return {"status": "skipped", "reason": "engine not available"}
    except Exception as e:
        logger.error(f"Vector index refresh failed: {e}")
        return {"status": "error", "error": str(e)}


def task_update_aesthetic_ranking():
    """预置任务: 审美评分排行榜更新 (每6小时)"""
    try:
        from engines.aesthetic_scorer import get_aesthetic_scorer
        scorer = get_aesthetic_scorer()
        stats = scorer.get_summary()
        logger.info(f"Aesthetic ranking updated: total={stats.get('total', 0)}")
        return {"status": "ok", "stats": stats}
    except ImportError:
        logger.warning("Aesthetic scorer not available")
        return {"status": "skipped", "reason": "engine not available"}
    except Exception as e:
        logger.error(f"Aesthetic ranking update failed: {e}")
        return {"status": "error", "error": str(e)}


def task_health_check():
    """预置任务: 系统健康自检 (每10分钟)"""
    import os
    import psutil
    import shutil as _shutil

    checks = {}

    try:
        usage = _shutil.disk_usage(".")
        disk_pct = usage.used / usage.total * 100
        checks["disk"] = {
            "status": "ok" if disk_pct < 90 else "warning",
            "used_percent": round(disk_pct, 1),
            "free_gb": round(usage.free / (1024**3), 1),
        }
    except Exception as e:
        checks["disk"] = {"status": "error", "error": str(e)}

    try:
        mem = psutil.virtual_memory()
        checks["memory"] = {
            "status": "ok" if mem.percent < 90 else "warning",
            "used_percent": mem.percent,
            "available_gb": round(mem.available / (1024**3), 1),
        }
    except Exception as e:
        checks["memory"] = {"status": "error", "error": str(e)}

    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        checks["cpu"] = {
            "status": "ok" if cpu_percent < 90 else "warning",
            "percent": cpu_percent,
        }
    except Exception as e:
        checks["cpu"] = {"status": "error", "error": str(e)}

    try:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        test_file = data_dir / ".health_check_test"
        test_file.write_text("ok")
        test_file.unlink()
        checks["data_dir"] = {"status": "ok"}
    except Exception as e:
        checks["data_dir"] = {"status": "error", "error": str(e)}

    statuses = [c.get("status", "unknown") for c in checks.values()]
    overall = "error" if "error" in statuses else ("warning" if "warning" in statuses else "ok")

    result = {"overall": overall, "checks": checks, "timestamp": datetime.now().isoformat()}
    logger.info(f"Health check: overall={overall}")
    return result


# ============================================================================
# 预置任务定义
# ============================================================================

PRESET_JOBS: List[JobDefinition] = [
    JobDefinition(
        id="preset_data_cleanup",
        name="数据清理 (过期分享/临时文件)",
        func_path="engines.scheduler_engine.task_data_cleanup",
        trigger_type="cron",
        trigger_config={"hour": 3, "minute": 0},
        max_retries=1,
        retry_delay=300,
        notify_on_failure=True,
    ),
    JobDefinition(
        id="preset_vector_refresh",
        name="向量索引刷新",
        func_path="engines.scheduler_engine.task_refresh_vector_index",
        trigger_type="interval",
        trigger_config={"minutes": 30},
        max_retries=2,
        retry_delay=60,
        notify_on_failure=True,
    ),
    JobDefinition(
        id="preset_aesthetic_ranking",
        name="审美评分排行榜更新",
        func_path="engines.scheduler_engine.task_update_aesthetic_ranking",
        trigger_type="interval",
        trigger_config={"hours": 6},
        max_retries=2,
        retry_delay=120,
        notify_on_failure=True,
    ),
    JobDefinition(
        id="preset_health_check",
        name="系统健康自检",
        func_path="engines.scheduler_engine.task_health_check",
        trigger_type="interval",
        trigger_config={"minutes": 10},
        max_retries=1,
        retry_delay=30,
        notify_on_failure=True,
    ),
]


# ============================================================================
# Singleton
# ============================================================================

_scheduler: Optional[SchedulerEngine] = None

def get_scheduler() -> SchedulerEngine:
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerEngine()
    return _scheduler

def init_preset_jobs():
    """初始化预置Agent任务 (幂等: 已存在则跳过)"""
    scheduler = get_scheduler()
    existing_ids = {j.id for j in scheduler._scheduler.get_jobs()}
    for job_def in PRESET_JOBS:
        if job_def.id not in existing_ids:
            scheduler.add_job(job_def)
            logger.info(f"Preset job registered: {job_def.name}")
        else:
            logger.debug(f"Preset job already exists: {job_def.id}")
