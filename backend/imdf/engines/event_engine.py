"""
Phase3: Event Engine — 事件触发引擎
=================================
响应系统事件的自动化流水线:
  - 文件上传完成 → 自动触发AI打标
  - 标注完成 → 自动触发质量评分
  - 数据导入 → 自动触发分类规则

事件驱动架构: 发布/订阅模式, 异步回调链.
"""

from __future__ import annotations

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Event Types
# ─────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """系统事件类型"""
    FILE_UPLOADED = "file_uploaded"               # 文件上传完成
    FILE_DELETED = "file_deleted"                  # 文件删除
    ANNOTATION_COMPLETED = "annotation_completed"  # 标注完成
    ANNOTATION_UPDATED = "annotation_updated"      # 标注更新
    DATA_IMPORTED = "data_imported"                # 数据导入完成
    DATA_EXPORTED = "data_exported"                # 数据导出完成
    CLASSIFICATION_UPDATED = "classification_updated"  # 分类规则更新
    SHARING_CREATED = "sharing_created"            # 分享链接创建
    SHARING_EXPIRED = "sharing_expired"            # 分享链接过期
    QUALITY_SCORE_UPDATED = "quality_score_updated"  # 质量评分更新
    VECTOR_INDEX_UPDATED = "vector_index_updated"  # 向量索引更新
    PIPELINE_COMPLETED = "pipeline_completed"      # 管线完成
    CUSTOM = "custom"                              # 自定义事件


# ─────────────────────────────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Event:
    """事件"""
    type: EventType
    source: str = ""               # 事件来源 (模块名)
    payload: Dict[str, Any] = field(default_factory=dict)  # 事件负载
    timestamp: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.id:
            import uuid
            self.id = str(uuid.uuid4())


@dataclass
class EventHandler:
    """事件处理器注册项"""
    event_type: EventType
    callback: Callable[[Event], Awaitable[None]]
    handler_id: str = ""
    priority: int = 0               # 优先级 (数字越小越先执行)
    condition: Optional[str] = None # 条件表达式 (e.g. "payload.size > 1024")
    async_exec: bool = True         # 是否异步执行

    def __post_init__(self):
        if not self.handler_id:
            import uuid
            self.handler_id = str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────
# Event Engine
# ─────────────────────────────────────────────────────────────────────

class EventEngine:
    """事件引擎 — 发布/订阅模式

    支持:
      - 事件类型注册与监听
      - 多处理器链式执行
      - 条件过滤
      - 异步并行处理
      - 事件历史追踪
    """

    def __init__(self, max_history: int = 1000):
        # Event → List[EventHandler]
        self._handlers: Dict[EventType, List[EventHandler]] = {
            et: [] for et in EventType
        }

        # Event history (ring buffer)
        self._history: List[Event] = []
        self._max_history = max_history

        # Statistics
        self._stats: Dict[str, int] = {
            "events_published": 0,
            "events_processed": 0,
            "events_failed": 0,
        }

        # Custom event types (user-defined strings beyond the enum)
        self._custom_handlers: Dict[str, List[EventHandler]] = {}

        logger.info("EventEngine initialized")

    # ── Handler Registration ─────────────────────────────────────────

    def on(self, event_type: EventType, callback: Callable[[Event], Awaitable[None]],
           priority: int = 0, condition: Optional[str] = None,
           async_exec: bool = True) -> str:
        """注册事件处理器

        Args:
            event_type: 事件类型
            callback: 异步回调函数 async def callback(event: Event) -> None
            priority: 优先级 (越小越先执行, 默认0)
            condition: 可选条件表达式 (暂未实现复杂表达式, 简单key检查)
            async_exec: 是否异步执行

        Returns:
            handler_id: 处理器ID (可用作取消注册)
        """
        handler = EventHandler(
            event_type=event_type,
            callback=callback,
            priority=priority,
            condition=condition,
            async_exec=async_exec,
        )
        self._handlers[event_type].append(handler)
        # Sort by priority
        self._handlers[event_type].sort(key=lambda h: h.priority)
        logger.info(f"Handler registered for {event_type.value}: {handler.handler_id}")
        return handler.handler_id

    def on_custom(self, event_name: str, callback: Callable[[Event], Awaitable[None]],
                  priority: int = 0) -> str:
        """注册自定义事件处理器 (非枚举事件类型)"""
        handler = EventHandler(
            event_type=EventType.CUSTOM,
            callback=callback,
            priority=priority,
        )
        if event_name not in self._custom_handlers:
            self._custom_handlers[event_name] = []
        self._custom_handlers[event_name].append(handler)
        self._custom_handlers[event_name].sort(key=lambda h: h.priority)
        logger.info(f"Custom handler registered for '{event_name}': {handler.handler_id}")
        return handler.handler_id

    def off(self, handler_id: str) -> bool:
        """取消注册事件处理器"""
        for et, handlers in self._handlers.items():
            for h in handlers:
                if h.handler_id == handler_id:
                    handlers.remove(h)
                    logger.info(f"Handler removed: {handler_id}")
                    return True
        for name, handlers in self._custom_handlers.items():
            for h in handlers:
                if h.handler_id == handler_id:
                    handlers.remove(h)
                    logger.info(f"Custom handler removed: {handler_id}")
                    return True
        return False

    # ── Event Publishing ─────────────────────────────────────────────

    async def publish(self, event: Event) -> int:
        """发布事件 — 触发所有注册的处理器

        Args:
            event: 事件对象

        Returns:
            int: 被触发的处理器数量
        """
        self._stats["events_published"] += 1

        # Record in history (ring buffer)
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        handlers = self._handlers.get(event.type, [])
        # Also check custom handlers
        custom_name = event.payload.get("custom_event_name", "")
        if custom_name and custom_name in self._custom_handlers:
            handlers = handlers + self._custom_handlers[custom_name]

        if not handlers:
            logger.debug(f"No handlers for event: {event.type.value}")
            return 0

        # Execute all matching handlers
        tasks = []
        for handler in sorted(handlers, key=lambda h: h.priority):
            if not self._check_condition(handler, event):
                continue
            if handler.async_exec:
                tasks.append(self._execute_handler(handler, event))
            else:
                # Synchronous execution
                try:
                    await handler.callback(event)
                    self._stats["events_processed"] += 1
                except Exception as e:
                    self._stats["events_failed"] += 1
                    logger.error(f"Handler {handler.handler_id} failed for event {event.type.value}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception):
                    self._stats["events_failed"] += 1
                    logger.error(f"Async handler failed: {r}")
                else:
                    self._stats["events_processed"] += 1

        return len(handlers)

    def publish_sync(self, event: Event) -> int:
        """同步发布事件 (在非async上下文中使用)"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a task, but return immediately
                loop.create_task(self.publish(event))
                return len(self._handlers.get(event.type, []))
            else:
                return loop.run_until_complete(self.publish(event))
        except RuntimeError:
            return asyncio.run(self.publish(event))

    async def _execute_handler(self, handler: EventHandler, event: Event):
        """执行单个异步处理器"""
        try:
            await handler.callback(event)
        except Exception as e:
            logger.error(f"Async handler {handler.handler_id} error: {e}")
            raise

    def _check_condition(self, handler: EventHandler, event: Event) -> bool:
        """检查条件表达式 (简单实现)"""
        if not handler.condition:
            return True
        # Simple condition: check if a key exists in payload
        # Format: "payload.key" or "payload.key == value"
        try:
            cond = handler.condition.strip()
            if cond.startswith("payload."):
                key = cond[len("payload."):]
                # Check existence
                if "==" in key:
                    k, v = key.split("==", 1)
                    return str(event.payload.get(k.strip(), "")) == v.strip().strip("'\"")
                if "!=" in key:
                    k, v = key.split("!=", 1)
                    return str(event.payload.get(k.strip(), "")) != v.strip().strip("'\"")
                # Just check key existence
                return key in event.payload
            return True
        except Exception:
            return True

    # ── History & Stats ──────────────────────────────────────────────

    def get_history(self, event_type: Optional[EventType] = None,
                    limit: int = 50) -> List[dict]:
        """获取事件历史"""
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return [
            {
                "id": e.id,
                "type": e.type.value,
                "source": e.source,
                "payload_keys": list(e.payload.keys()),
                "timestamp": e.timestamp,
            }
            for e in events[-limit:]
        ]

    def get_stats(self) -> dict:
        """获取统计信息"""
        handler_counts = {et.value: len(hs) for et, hs in self._handlers.items()}
        custom_counts = {name: len(hs) for name, hs in self._custom_handlers.items()}
        return {
            **self._stats,
            "total_handlers": sum(handler_counts.values()) + sum(custom_counts.values()),
            "handlers_by_type": handler_counts,
            "custom_handlers": custom_counts,
            "history_size": len(self._history),
        }

    def get_handlers(self) -> List[dict]:
        """获取所有注册的处理器"""
        result = []
        for et, handlers in self._handlers.items():
            for h in handlers:
                result.append({
                    "handler_id": h.handler_id,
                    "event_type": et.value,
                    "priority": h.priority,
                    "condition": h.condition,
                    "async_exec": h.async_exec,
                })
        for name, handlers in self._custom_handlers.items():
            for h in handlers:
                result.append({
                    "handler_id": h.handler_id,
                    "event_type": f"custom:{name}",
                    "priority": h.priority,
                    "condition": h.condition,
                    "async_exec": h.async_exec,
                })
        return result


# ─────────────────────────────────────────────────────────────────────
# Pre-built Event Handlers (Agent驱动自动化流水线)
# ─────────────────────────────────────────────────────────────────────

async def _on_file_uploaded_auto_tag(event: Event):
    """文件上传完成 → 自动触发AI打标

    通过DAM引擎对上传的文件进行自动标签识别.
    """
    file_path = event.payload.get("file_path", "")
    file_id = event.payload.get("file_id", "")

    if not file_path and not file_id:
        logger.warning("File uploaded event missing file_path/file_id")
        return

    logger.info(f"Auto-tagging triggered for file: {file_path or file_id}")

    try:
        from engines.dam_engine import get_dam_engine
        dam = get_dam_engine()

        if file_path:
            # Try to auto-tag the file
            import os
            if os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                tags = dam.suggest_tags(file_path) if hasattr(dam, 'suggest_tags') else []
                if tags:
                    logger.info(f"Auto-tagged {file_path}: {tags}")
                    # Publish a follow-up event for quality scoring
                    await event_engine.publish(Event(
                        type=EventType.QUALITY_SCORE_UPDATED,
                        source="event_engine.auto_tag",
                        payload={"file_path": file_path, "tags": tags},
                    ))
            else:
                logger.warning(f"File not found for auto-tag: {file_path}")
    except ImportError:
        logger.debug("DAM engine not available, skipping auto-tag")
    except Exception as e:
        logger.error(f"Auto-tag failed for {file_path}: {e}")


async def _on_annotation_completed_quality_score(event: Event):
    """标注完成 → 自动触发质量评分

    当标注任务完成时, 自动对标注数据进行审美/质量评分.
    """
    annotation_id = event.payload.get("annotation_id", "")
    item_path = event.payload.get("item_path", "")
    item_type = event.payload.get("item_type", "image")

    logger.info(f"Auto quality scoring triggered for annotation: {annotation_id}")

    try:
        if item_type == "image" and item_path:
            from engines.aesthetic_scorer import get_aesthetic_scorer
            import os
            if os.path.exists(item_path):
                scorer = get_aesthetic_scorer()
                scores = scorer.score_image(item_path)
                logger.info(f"Quality scored {item_path}: overall={scores.overall}")
                # Publish score updated event
                await event_engine.publish(Event(
                    type=EventType.QUALITY_SCORE_UPDATED,
                    source="event_engine.quality_score",
                    payload={
                        "item_path": item_path,
                        "annotation_id": annotation_id,
                        "scores": scores.to_dict(),
                    },
                ))
    except ImportError:
        logger.debug("Aesthetic scorer not available, skipping quality score")
    except Exception as e:
        logger.error(f"Quality scoring failed for {item_path}: {e}")


async def _on_data_imported_auto_classify(event: Event):
    """数据导入完成 → 自动触发分类规则

    当新数据导入系统时, 自动应用分类规则引擎.
    """
    import_path = event.payload.get("import_path", "")
    dataset_name = event.payload.get("dataset_name", "")
    item_count = event.payload.get("item_count", 0)

    logger.info(f"Auto-classification triggered for import: {dataset_name or import_path}")

    try:
        from engines.classification_engine import ClassificationEngine
        engine = ClassificationEngine()

        # Classify the imported items
        if import_path:
            import os
            if os.path.isdir(import_path):
                classified = 0
                for root, dirs, files in os.walk(import_path):
                    for f in files:
                        file_path = os.path.join(root, f)
                        try:
                            rules = engine.classify(file_path)
                            if rules:
                                classified += 1
                        except Exception as e:
                            logger.error(f"Operation failed: {e}")
                logger.info(f"Auto-classified {classified}/{item_count} items from {import_path}")
            elif os.path.isfile(import_path):
                rules = engine.classify(import_path)
                logger.info(f"Auto-classified single file {import_path}: {len(rules)} rules matched")

    except ImportError:
        logger.debug("Classification engine not available, skipping auto-classify")
    except Exception as e:
        logger.error(f"Auto-classification failed: {e}")


# ─────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────

event_engine = EventEngine()


def get_event_engine() -> EventEngine:
    """获取事件引擎单例"""
    return event_engine


def init_event_handlers():
    """初始化预置事件处理器 (Agent主动驱动流水线)"""
    ee = get_event_engine()

    # 1. 文件上传完成 → 自动AI打标
    ee.on(EventType.FILE_UPLOADED, _on_file_uploaded_auto_tag, priority=10)

    # 2. 标注完成 → 自动质量评分
    ee.on(EventType.ANNOTATION_COMPLETED, _on_annotation_completed_quality_score, priority=20)

    # 3. 数据导入 → 自动分类规则
    ee.on(EventType.DATA_IMPORTED, _on_data_imported_auto_classify, priority=15)

    logger.info("Event handlers initialized: "
                 "FILE_UPLOADED→auto_tag, "
                 "ANNOTATION_COMPLETED→quality_score, "
                 "DATA_IMPORTED→auto_classify")
