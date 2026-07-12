"""VDP-2026 R5 — Plugin ecosystem public API."""
from .manager import (
    PluginManager, Plugin, PluginStatus, TrustLevel,
    get_manager, reset_manager_for_test, configure_db,
    SAMPLE_PLUGINS,
)
from .routes import router

__all__ = [
    "PluginManager", "Plugin", "PluginStatus", "TrustLevel",
    "get_manager", "reset_manager_for_test", "configure_db",
    "SAMPLE_PLUGINS", "router",
]
