"""
R7-W1: SQLAlchemy Slow Query Logger (api/_common/slow_query.py)
===============================================================

通过 SQLAlchemy `before_cursor_execute` / `after_cursor_execute` event listener,
记录所有超过阈值的 SQL 查询。

特性:
  1. 阈值可配置 (默认 200ms)
  2. 输出到:
     - Python logging (WARNING 级别, logger name = imdf.slow_query)
     - JSONL 文件 (logs/slow_queries.jsonl), 便于事后聚合
     - Prometheus Counter (通过 api._common.metrics.observe_db_query)
  3. 参数化查询脱敏: 不输出明文参数, 避免敏感数据落盘
  4. 线程安全

用法:
    from api._common.slow_query import install_slow_query_listener
    from api.db_models import engine
    install_slow_query_listener(engine, threshold_ms=200)
"""

from __future__ import annotations

import os
import json
import time
import threading
import logging
from datetime import datetime, timezone
from typing import Optional, Any

logger = logging.getLogger("imdf.slow_query")


# ═══════════════════════════════════════════════════════════════════════════
# 路径与文件句柄
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
)


def _default_log_path() -> str:
    log_dir = os.environ.get("IMDF_LOGS_DIR", _DEFAULT_LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    return os.path.join(log_dir, "slow_queries.jsonl")


# ═══════════════════════════════════════════════════════════════════════════
# 状态: 同一 Engine 只能装一次
# ═══════════════════════════════════════════════════════════════════════════

_installed_engines: dict = {}
_install_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════
# 核心: 监听器
# ═══════════════════════════════════════════════════════════════════════════

class SlowQueryListener:
    """SQLAlchemy event listener, 记录执行时间超过阈值的查询。"""

    def __init__(self, threshold_ms: int = 200,
                 log_path: Optional[str] = None,
                 max_statement_chars: int = 500):
        self.threshold_ms = threshold_ms
        self.threshold_seconds = threshold_ms / 1000.0
        self.log_path = log_path or _default_log_path()
        self.max_statement_chars = max_statement_chars
        self._start_times: dict = {}
        self._lock = threading.Lock()
        # 累计统计 (进程级)
        self.total_slow = 0
        self.total_queries = 0
        self.total_query_time = 0.0
        self.max_query_time = 0.0

    # ── SQLAlchemy events ─────────────────────────────────────────────────

    def before_cursor_execute(self, conn, cursor, statement, parameters,
                               context, executemany):
        """before_cursor_execute 事件 — 记录开始时间。"""
        try:
            ident = self._conn_ident(conn)
            with self._lock:
                self._start_times[ident] = time.perf_counter()
        except Exception:
            logger.debug("slow_query_before_failed", exc_info=True)

    def after_cursor_execute(self, conn, cursor, statement, parameters,
                              context, executemany):
        """after_cursor_execute 事件 — 计算耗时并判定是否慢查询。"""
        try:
            ident = self._conn_ident(conn)
            with self._lock:
                start = self._start_times.pop(ident, None)
            if start is None:
                return
            duration = time.perf_counter() - start
            with self._lock:
                self.total_queries += 1
                self.total_query_time += duration
                if duration > self.max_query_time:
                    self.max_query_time = duration

            # 上报 Prometheus 指标 (任何查询都报)
            try:
                from api._common.metrics import observe_db_query
                op = self._infer_operation(statement)
                observe_db_query(op, duration,
                                 slow_threshold=self.threshold_seconds)
            except Exception:
                logger.debug("slow_query_metrics_failed", exc_info=True)

            # 超过阈值才写慢日志
            if duration < self.threshold_seconds:
                return

            self._write_slow_record(statement, parameters, duration, context)
        except Exception:
            # 慢查询监听绝不能影响主查询
            logger.debug("slow_query_after_failed", exc_info=True)

    # ── 工具方法 ──────────────────────────────────────────────────────────

    @staticmethod
    def _conn_ident(conn) -> int:
        return id(conn)

    @staticmethod
    def _infer_operation(statement: str) -> str:
        s = (statement or "").lstrip().lower()
        if s.startswith("select"):
            return "select"
        if s.startswith("insert"):
            return "insert"
        if s.startswith("update"):
            return "update"
        if s.startswith("delete"):
            return "delete"
        return "other"

    def _write_slow_record(self, statement: str, parameters: Any,
                            duration: float, context: Any) -> None:
        """写一条慢查询记录 (logging + JSONL file)。"""
        with self._lock:
            self.total_slow += 1

        stmt_truncated = (statement or "")[:self.max_statement_chars]
        # 参数脱敏: 只记录类型与个数, 不记录值
        param_summary = self._summarize_params(parameters)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round(duration * 1000, 2),
            "operation": self._infer_operation(statement),
            "statement": stmt_truncated,
            "parameters_summary": param_summary,
        }

        # 1) logging 输出
        logger.warning(
            "slow_query",
            extra=record,
            duration_ms=record["duration_ms"],
            operation=record["operation"],
        )

        # 2) JSONL 文件
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("slow_query_write_failed", exc_info=True)

    @staticmethod
    def _summarize_params(parameters: Any) -> dict:
        """生成参数的脱敏摘要。"""
        if parameters is None:
            return {"count": 0}
        try:
            params_list = (
                list(parameters) if not isinstance(parameters, dict)
                else [parameters]
            )
            return {
                "count": len(params_list),
                "types": [
                    type(p).__name__ for p in params_list[:5]
                ],
            }
        except Exception:
            return {"count": -1, "error": "unparseable"}

    # ── 统计接口 ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """返回进程级累计统计。"""
        with self._lock:
            return {
                "total_queries": self.total_queries,
                "total_slow": self.total_slow,
                "slow_ratio": (
                    round(self.total_slow / self.total_queries, 4)
                    if self.total_queries else 0.0
                ),
                "total_query_time_s": round(self.total_query_time, 4),
                "avg_query_time_ms": (
                    round(self.total_query_time / self.total_queries * 1000, 3)
                    if self.total_queries else 0.0
                ),
                "max_query_time_ms": round(self.max_query_time * 1000, 3),
                "threshold_ms": self.threshold_ms,
                "log_path": self.log_path,
            }


# ═══════════════════════════════════════════════════════════════════════════
# 安装入口
# ═══════════════════════════════════════════════════════════════════════════

def install_slow_query_listener(engine, threshold_ms: int = 200,
                                  log_path: Optional[str] = None
                                  ) -> SlowQueryListener:
    """给指定 SQLAlchemy Engine 安装慢查询监听器。

    Args:
        engine: sqlalchemy.Engine
        threshold_ms: 慢查询阈值 (毫秒)
        log_path: JSONL 文件路径; None 时使用 logs/slow_queries.jsonl

    Returns:
        SlowQueryListener 实例 (可调用 .stats() 查看统计)
    """
    engine_id = id(engine)
    with _install_lock:
        if engine_id in _installed_engines:
            logger.info("slow_query_listener_already_installed",
                        engine_id=engine_id)
            return _installed_engines[engine_id]

    listener = SlowQueryListener(
        threshold_ms=threshold_ms,
        log_path=log_path,
    )

    try:
        from sqlalchemy import event
        event.listen(engine, "before_cursor_execute",
                     listener.before_cursor_execute)
        event.listen(engine, "after_cursor_execute",
                     listener.after_cursor_execute)
    except Exception as exc:
        logger.error("slow_query_listener_install_failed", error=str(exc))
        raise

    with _install_lock:
        _installed_engines[engine_id] = listener

    logger.info("slow_query_listener_installed",
                threshold_ms=threshold_ms,
                log_path=listener.log_path)
    return listener


def get_listener_for(engine) -> Optional[SlowQueryListener]:
    """获取已安装的 listener, 没有则返回 None。"""
    with _install_lock:
        return _installed_engines.get(id(engine))


__all__ = [
    "SlowQueryListener",
    "install_slow_query_listener",
    "get_listener_for",
]