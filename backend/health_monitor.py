import os, json, logging, threading, psutil
from datetime import datetime
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = 'healthy'; DEGRADED = 'degraded'; UNHEALTHY = 'unhealthy'

class MonitorService:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._start_time = datetime.now()
            self._process = psutil.Process()
            self._request_count = 0
            self._error_count = 0
    def get_health_report(self, db_manager=None):
        cpu = self._process.cpu_percent()
        mem = self._process.memory_info().rss / 1024 / 1024
        status = 'healthy' if cpu < 90 and mem < 2048 else 'degraded'
        uptime = (datetime.now() - self._start_time).total_seconds()
        return {'status': status, 'uptime': round(uptime, 2), 'cpu': round(cpu, 1), 'memory_mb': round(mem, 1), 'timestamp': datetime.now().isoformat()}

def get_monitor_service(): return MonitorService()

if __name__ == '__main__':
    print('Health Monitor OK')
    m = get_monitor_service()
    print(m.get_health_report())
