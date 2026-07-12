"""Crawler Registry — 渠道注册表 (P20-B1)

本模块是渠道注册表的公开 facade, 让上层代码不必直接依赖 CrawlerEngine
的内部状态。注册操作实际委托给全局默认引擎, 但允许传入自定义引擎做隔离。

使用:
    from imdf.crawler.registry import (
        register, get, list_channels, get_default_engine,
    )

    register("baidu_images", BaiduImagesCrawler)
    cw = get("baidu_images", config=cfg)
    print(list_channels())  # 包含 5 首批 + 5 P20 web

设计原则:
- 全局单例: 内部 default_engine 进程级共享, 与 CrawlerEngine._registry
  引用同一份 mapping (通过 ._registry 属性直接共享, 避免双源漂移)
- 显式 override: 调用 register() 时也写入 default_engine._registry
- 安全: list_channels 返回 sorted 副本, 不暴露内部 dict
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Type

from .base import BaseCrawler
from .config import CrawlerConfig, make_default_config

# 全局 lock — 保护 _custom_engine / _custom_registry 修改
_LOCK = threading.Lock()

# 进程级默认引擎 (懒加载, 首次访问时构造)
_default_engine = None
_default_engine_lock = threading.Lock()


def _get_default_engine_lazy():
    """懒加载 CrawlerEngine — 避免循环 import."""
    global _default_engine
    if _default_engine is None:
        with _default_engine_lock:
            if _default_engine is None:
                # 延迟 import 避免循环依赖
                from .engine import CrawlerEngine
                _default_engine = CrawlerEngine()
    return _default_engine


def get_default_engine():
    """返回默认 CrawlerEngine 单例."""
    return _get_default_engine_lazy()


def reset_default_engine() -> None:
    """重置默认引擎 — 主要给测试用, 隔离状态."""
    global _default_engine
    with _default_engine_lock:
        _default_engine = None


def register(channel: str, crawler_class: Type[BaseCrawler]) -> None:
    """注册一个渠道到默认引擎.

    同时确保 crawler_class 在 channels 包里有 __init__ 接受 config/kwargs.
    """
    engine = _get_default_engine_lazy()
    engine.register(channel, crawler_class)


def unregister(channel: str) -> bool:
    """注销一个渠道 — 返回是否原本存在."""
    engine = _get_default_engine_lazy()
    with _LOCK:
        existed = channel in engine._registry
        if existed:
            engine._registry.pop(channel, None)
            engine._crawler_instances.pop(channel, None)
        return existed


def get(channel: str, config: Optional[CrawlerConfig] = None,
        **kwargs: Any) -> BaseCrawler:
    """获取一个 crawler 实例 — 复用引擎缓存 (单例模式).

    额外 kwargs 会传给 __init__ (除 config / mock 外).
    """
    engine = _get_default_engine_lazy()
    if config is None and "config" not in kwargs:
        config = make_default_config(channel=channel)
    # engine.get_crawler 内部已经处理 config 默认值 — 我们只在用户显式传时透传
    # 避免 "got multiple values for keyword argument 'config'" 错误
    if config is not None:
        return engine.get_crawler(channel, config=config, **kwargs)
    return engine.get_crawler(channel, **kwargs)


def list_channels() -> List[str]:
    """返回所有已注册渠道名 (sorted)."""
    engine = _get_default_engine_lazy()
    return sorted(engine.list_channels())


def is_registered(channel: str) -> bool:
    """检查渠道是否已注册."""
    engine = _get_default_engine_lazy()
    return channel in engine._registry


def get_registry_snapshot() -> Dict[str, Type[BaseCrawler]]:
    """返回注册表的浅拷贝 — 调试/审计用."""
    engine = _get_default_engine_lazy()
    return dict(engine._registry)


# 显式导出
__all__ = [
    "register",
    "unregister",
    "get",
    "list_channels",
    "is_registered",
    "get_default_engine",
    "get_registry_snapshot",
    "reset_default_engine",
]
