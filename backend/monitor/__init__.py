"""
NanoBot Factory - Monitor Package
监控系统模块

@author MiniMax Agent
@date 2026-04-11
"""

# 从monitor.py导入GPU监控
import sys
from pathlib import Path
_monitor_path = Path(__file__).parent.parent / "monitor.py"
if _monitor_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gpu_monitor", _monitor_path)
    if spec and spec.loader:
        _gpu_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_gpu_module)
        GPUMonitor = _gpu_module.GPUMonitor
        get_gpu_monitor = _gpu_module.get_gpu_monitor
        SystemStats = _gpu_module.SystemStats
        GPUInfo = _gpu_module.GPUInfo

from .alert_manager import (
    AlertManager,
    Alert,
    AlertLevel,
    AlertCategory,
    AlertStatus,
    AlertHandler,
    LogAlertHandler,
    ConsoleAlertHandler,
    WebhookAlertHandler,
    AlertAggregator,
    AlertEscalator,
    get_alert_manager,
    send_alert,
    send_error,
    send_warning
)

__all__ = [
    'GPUMonitor',
    'get_gpu_monitor',
    'SystemStats',
    'GPUInfo',
    'AlertManager',
    'Alert',
    'AlertLevel',
    'AlertCategory',
    'AlertStatus',
    'AlertHandler',
    'LogAlertHandler',
    'ConsoleAlertHandler',
    'WebhookAlertHandler',
    'AlertAggregator',
    'AlertEscalator',
    'get_alert_manager',
    'send_alert',
    'send_error',
    'send_warning'
]
