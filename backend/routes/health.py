"""健康检查与系统状态路由"""
from fastapi import APIRouter, Request
import time
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/")
async def root():
    """Root endpoint - serve HTML dashboard"""
    import pathlib
    from pathlib import Path
    template_path = Path(__file__).parent.parent / "templates" / "index.html"
    if template_path.exists():
        from fastapi.responses import FileResponse
        return FileResponse(template_path, media_type="text/html")
    else:
        # Fallback to JSON if template not found
        return {
            "name": "Nanobot Factory API",
            "version": "1.0.0",
            "status": "running"
        }


@router.get("/health")
async def health_check():
    """Health check endpoint with detailed service status"""
    from server import state, manager, AIRI_AVAILABLE, get_airi_service_status, db_manager
    from datetime import datetime
    from monitor import get_gpu_monitor

    # 基础健康状态
    health_status = {
        "status": "healthy",
        "agents_count": len(state.agents),
        "skills_count": len(state.skills),
        "assets_count": len(state.assets),
        "active_tasks": len(state.active_tasks),
        "websocket_connections": len(manager.active_connections),
        "timestamp": datetime.now().isoformat(),
    }

    # 添加 AIRI 服务状态（如果可用）
    if AIRI_AVAILABLE:
        try:
            airi_status = get_airi_service_status()
            health_status["airi"] = airi_status
        except Exception as e:
            health_status["airi"] = {
                "error": str(e),
                "available": False
            }

    # 添加 GPU 监控状态（如果可用）
    try:
        gpu_monitor = get_gpu_monitor()
        if gpu_monitor:
            health_status["gpu_monitor"] = {
                "available": True,
                "monitoring": gpu_monitor.is_monitoring() if hasattr(gpu_monitor, 'is_monitoring') else False,
            }
    except Exception:
        pass

    # 添加数据库健康状态
    try:
        if db_manager:
            import sqlite3
            try:
                conn = sqlite3.connect("./nanobot_factory.db")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM assets")
                asset_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM datasets")
                dataset_count = cursor.fetchone()[0]
                conn.close()
                health_status["database"] = {
                    "available": True,
                    "asset_count": asset_count,
                    "dataset_count": dataset_count,
                }
            except Exception as db_e:
                health_status["database"] = {
                    "available": True,
                    "db_error": str(db_e),
                }
    except Exception:
        pass

    # 添加 Nanobot 控制器状态
    try:
        from nanobot_controller import get_nanobot_controller
        controller = get_nanobot_controller()
        health_status["nanobot"] = {
            "available": True,
            "capabilities": len(controller.capabilities) if hasattr(controller, 'capabilities') else 0,
            "agents": len(controller.agents) if hasattr(controller, 'agents') else 0,
        }
    except Exception:
        pass

    return health_status


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    import os
    import platform
    import psutil

    metrics_lines = []
    metrics_lines.append("# HELP nanobot_version Nanobot Factory version info")
    metrics_lines.append("# TYPE nanobot_version gauge")
    metrics_lines.append('nanobot_version{version="1.0.0"} 1')

    # System metrics
    metrics_lines.append("# HELP python_info Python runtime info")
    metrics_lines.append("# TYPE python_info gauge")
    import sys
    metrics_lines.append(f'python_info{{version="{sys.version.split()[0]}"}} 1')

    # OS info
    metrics_lines.append("# HELP os_info OS information")
    metrics_lines.append("# TYPE os_info gauge")
    metrics_lines.append(f'os_info{{name="{platform.system()}",release="{platform.release()}"}} 1')

    # CPU metrics
    metrics_lines.append("# HELP cpu_percent CPU usage percentage")
    metrics_lines.append("# TYPE cpu_percent gauge")
    metrics_lines.append(f"cpu_percent {psutil.cpu_percent()}")

    cpu_count = psutil.cpu_count()
    metrics_lines.append("# HELP cpu_count Number of CPU cores")
    metrics_lines.append("# TYPE cpu_count gauge")
    metrics_lines.append(f"cpu_count {cpu_count}")

    # Memory metrics
    memory = psutil.virtual_memory()
    metrics_lines.append("# HELP memory_total_bytes Total system memory")
    metrics_lines.append("# TYPE memory_total_bytes gauge")
    metrics_lines.append(f"memory_total_bytes {memory.total}")

    metrics_lines.append("# HELP memory_used_bytes Used system memory")
    metrics_lines.append("# TYPE memory_used_bytes gauge")
    metrics_lines.append(f"memory_used_bytes {memory.used}")

    metrics_lines.append("# HELP memory_percent Memory usage percentage")
    metrics_lines.append("# TYPE memory_percent gauge")
    metrics_lines.append(f"memory_percent {memory.percent}")

    # Disk metrics
    disk = psutil.disk_usage("/")
    metrics_lines.append("# HELP disk_total_bytes Total disk space")
    metrics_lines.append("# TYPE disk_total_bytes gauge")
    metrics_lines.append(f"disk_total_bytes {disk.total}")

    metrics_lines.append("# HELP disk_used_bytes Used disk space")
    metrics_lines.append("# TYPE disk_used_bytes gauge")
    metrics_lines.append(f"disk_used_bytes {disk.used}")

    metrics_lines.append("# HELP disk_percent Disk usage percentage")
    metrics_lines.append("# TYPE disk_percent gauge")
    metrics_lines.append(f"disk_percent {disk.percent}")

    # Application metrics
    from server import state
    metrics_lines.append("# HELP active_agents Number of active agents")
    metrics_lines.append("# TYPE active_agents gauge")
    metrics_lines.append(f"active_agents {len(state.agents)}")

    metrics_lines.append("# HELP active_skills Number of registered skills")
    metrics_lines.append("# TYPE active_skills gauge")
    metrics_lines.append(f"active_skills {len(state.skills)}")

    metrics_lines.append("# HELP active_tasks Number of active tasks")
    metrics_lines.append("# TYPE active_tasks gauge")
    metrics_lines.append(f"active_tasks {len(state.active_tasks)}")

    metrics_lines.append("# HELP websocket_connections Number of WebSocket connections")
    metrics_lines.append("# TYPE websocket_connections gauge")
    metrics_lines.append(f"websocket_connections {len(manager.active_connections)}")

    return Response(
        content="\n".join(metrics_lines),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
    )


@router.get("/metrics/json")
async def metrics_json():
    """JSON metrics endpoint"""
    import psutil
    from server import state

    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_mb": round(memory.total / 1024 / 1024, 2),
            "memory_used_mb": round(memory.used / 1024 / 1024, 2),
            "memory_percent": memory.percent,
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
            "disk_percent": disk.percent,
        },
        "application": {
            "active_agents": len(state.agents),
            "active_skills": len(state.skills),
            "active_tasks": len(state.active_tasks),
            "websocket_connections": len(manager.active_connections),
        },
        "timestamp": time.time()
    }
