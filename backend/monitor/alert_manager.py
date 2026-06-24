"""
NanoBot Factory - Alert Manager Module
告警管理器模块 - 统一管理和处理系统告警

@author MiniMax Agent
@date 2026-04-10
"""

import os
import json
import asyncio
import logging
import hashlib
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    EMERGENCY = 60


class AlertCategory(Enum):
    SYSTEM = "system"
    SECURITY = "security"
    PERFORMANCE = "performance"
    RESOURCE = "resource"
    BUSINESS = "business"
    DATABASE = "database"
    NETWORK = "network"


class AlertStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


@dataclass
class Alert:
    id: str
    level: AlertLevel
    category: AlertCategory
    title: str
    message: str
    source: str
    timestamp: datetime
    status: AlertStatus = AlertStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    occurrence_count: int = 1


class AlertHandler:
    async def send(self, alert: Alert) -> bool:
        raise NotImplementedError


class LogAlertHandler(AlertHandler):
    def __init__(self, min_level: AlertLevel = AlertLevel.WARNING):
        self.min_level = min_level
        self.logger = logging.getLogger("alert")
    
    async def send(self, alert: Alert) -> bool:
        if alert.level.value < self.min_level.value:
            return True
        self.logger.warning(f"[{alert.level.name}] [{alert.category.value}] {alert.title}: {alert.message}")
        return True


class ConsoleAlertHandler(AlertHandler):
    async def send(self, alert: Alert) -> bool:
        print(f"[{alert.level.name}] {alert.title}: {alert.message}")
        return True


class WebhookAlertHandler(AlertHandler):
    """Webhook通知处理器"""
    def __init__(self, webhook_url: str, headers: Optional[Dict[str, str]] = None, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.headers = headers or {"Content-Type": "application/json"}
        self.timeout = timeout
        self._session = None
    
    async def _get_session(self):
        if self._session is None:
            import aiohttp
            self._session = aiohttp.ClientSession(headers=self.headers, timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session
    
    async def send(self, alert: Alert) -> bool:
        try:
            session = await self._get_session()
            payload = {
                "id": alert.id,
                "level": alert.level.value,
                "level_name": alert.level.name,
                "category": alert.category.value,
                "title": alert.title,
                "message": alert.message,
                "source": alert.source,
                "timestamp": alert.timestamp.isoformat(),
                "occurrence_count": alert.occurrence_count
            }
            async with session.post(self.webhook_url, json=payload) as resp:
                return resp.status < 400
        except Exception as e:
            logger.error(f"Webhook alert failed: {e}")
            return False
    
    async def close(self) -> None:
        if self._session:
            await self._session.close()


class AlertAggregator:
    """告警聚合器 - 合并短时间内重复告警"""
    def __init__(self, window_seconds: int = 60, max_per_window: int = 10):
        self.window_seconds = window_seconds
        self.max_per_window = max_per_window
        self._windows: Dict[str, List[Alert]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def should_send(self, alert: Alert) -> bool:
        key = f"{alert.level.value}:{alert.category.value}:{alert.title}"
        with self._lock:
            now = datetime.now()
            cutoff = now - timedelta(seconds=self.window_seconds)
            self._windows[key] = [a for a in self._windows[key] if a.timestamp > cutoff]
            if len(self._windows[key]) >= self.max_per_window:
                return False
            self._windows[key].append(alert)
            return True


class AlertEscalator:
    """告警升级器 - 支持多级别通知"""
    def __init__(self):
        self._escalation_rules: List[Dict] = []
        self._lock = threading.Lock()
    
    def add_rule(self, level: AlertLevel, wait_seconds: int, target_handler: str):
        with self._lock:
            self._escalation_rules.append({
                "level": level,
                "wait_seconds": wait_seconds,
                "target_handler": target_handler
            })
    
    async def check_escalation(self, alert: Alert) -> Optional[str]:
        """检查是否需要升级"""
        with self._lock:
            for rule in self._escalation_rules:
                if alert.level.value >= rule["level"].value:
                    elapsed = (datetime.now() - alert.timestamp).total_seconds()
                    if elapsed >= rule["wait_seconds"]:
                        return rule["target_handler"]
        return None


class AlertManager:
    def __init__(self, enable_dedup: bool = True, dedup_window: int = 300):
        self.enable_dedup = enable_dedup
        self.dedup_window = dedup_window
        self._handlers: List[AlertHandler] = []
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []
        self._dedup_cache: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        self._max_history = 10000
        self._stats = defaultdict(int)
        self._aggregator = AlertAggregator()
        self._escalator = AlertEscalator()
        self.add_handler(LogAlertHandler())
        logger.info("AlertManager initialized")

    def add_handler(self, handler: AlertHandler) -> None:
        with self._lock:
            self._handlers.append(handler)

    async def send_alert(self, level: AlertLevel, category: AlertCategory,
                         title: str, message: str, source: str = "system",
                         metadata: Optional[Dict[str, Any]] = None,
                         force: bool = False) -> Optional[str]:
        alert_id = self._generate_alert_id(level, category, title, source, metadata)
        
        if self.enable_dedup and not force:
            if self._is_duplicate(alert_id):
                return None
        
        now = datetime.now()
        alert = Alert(
            id=alert_id, level=level, category=category,
            title=title, message=message, source=source,
            timestamp=now, metadata=metadata or {}
        )
        
        with self._lock:
            if alert_id in self._active_alerts:
                existing = self._active_alerts[alert_id]
                existing.occurrence_count += 1
                alert = existing
            else:
                self._active_alerts[alert_id] = alert
            self._alert_history.append(alert)
            if len(self._alert_history) > self._max_history:
                self._alert_history = self._alert_history[-self._max_history:]
        
        self._stats[f"total_{alert.level.name.lower()}"] += 1
        self._stats["total"] += 1
        await self._dispatch(alert)
        return alert_id

    def _generate_alert_id(self, level, category, title, source, metadata) -> str:
        content = f"{level.value}:{category.value}:{title}:{source}"
        if metadata:
            content += f":{json.dumps(metadata, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    def _is_duplicate(self, alert_id: str) -> bool:
        now = datetime.now()
        cutoff = now - timedelta(seconds=self.dedup_window)
        with self._lock:
            if alert_id in self._dedup_cache:
                if self._dedup_cache[alert_id] > cutoff:
                    return True
            self._dedup_cache[alert_id] = now
            expired = [k for k, v in self._dedup_cache.items() if v < cutoff]
            for k in expired:
                del self._dedup_cache[k]
            return False

    async def _dispatch(self, alert: Alert) -> None:
        for handler in self._handlers:
            try:
                await handler.send(alert)
            except Exception as e:
                logger.error(f"Handler failed: {e}")

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        with self._lock:
            if alert_id not in self._active_alerts:
                return False
            self._active_alerts[alert_id].status = AlertStatus.ACKNOWLEDGED
            return True

    async def resolve_alert(self, alert_id: str, user_id: str) -> bool:
        with self._lock:
            if alert_id not in self._active_alerts:
                return False
            del self._active_alerts[alert_id]
            return True

    def get_active_alerts(self) -> List[Alert]:
        with self._lock:
            return list(self._active_alerts.values())

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "total_alerts": self._stats["total"],
            "active_alerts": len(self._active_alerts),
            "handlers_count": len(self._handlers)
        }


_alert_manager: Optional[AlertManager] = None

def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


async def send_alert(level: AlertLevel, category: AlertCategory,
                    title: str, message: str, **kwargs) -> Optional[str]:
    manager = get_alert_manager()
    return await manager.send_alert(level, category, title, message, **kwargs)


async def send_error(category: AlertCategory, title: str, message: str, **kwargs):
    return await send_alert(AlertLevel.ERROR, category, title, message, **kwargs)


async def send_warning(category: AlertCategory, title: str, message: str, **kwargs):
    return await send_alert(AlertLevel.WARNING, category, title, message, **kwargs)
