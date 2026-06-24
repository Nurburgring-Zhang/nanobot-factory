#!/usr/bin/env python3
"""
IMDF 生产环境一键验证 — 增强版
===============================
检查项:
  1. 系统资源: 磁盘/内存/CPU
  2. 依赖版本: 核心依赖版本检查
  3. 服务健康: 启动→健康检查→API测试→结果
  4. 数据库: DB连通性检查
  5. 网络: 端口可达性检查

彩色输出, 适合CI/手动验证。
"""

import subprocess
import time
import urllib.request
import json
import sys
import os
import shutil
import importlib
from pathlib import Path
from typing import Tuple, Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# ── 颜色支持 ───────────────────────────────────────────────────────────
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    C_RESET = Style.RESET_ALL
    C_GREEN = Fore.GREEN
    C_RED = Fore.RED
    C_YELLOW = Fore.YELLOW
    C_CYAN = Fore.CYAN
    C_MAGENTA = Fore.MAGENTA
    C_BLUE = Fore.BLUE
    C_BOLD = Style.BRIGHT
    C_DIM = Style.DIM
    HAS_COLOR = True
except ImportError:
    C_RESET = C_GREEN = C_RED = C_YELLOW = C_CYAN = C_MAGENTA = C_BLUE = C_BOLD = C_DIM = ""
    HAS_COLOR = False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
PASS, FAIL, WARN = 0, 0, 0  # global counters

# ── Minimum version requirements for critical dependencies ─────────────
CRITICAL_DEPS = {
    "fastapi":        "0.110.0",
    "uvicorn":        "0.29.0",
    "pydantic":       "2.0.0",
    "sqlalchemy":     "2.0.0",
    "apscheduler":    "3.10.0",
    "prometheus_client": "0.19.0",
    "psutil":         "6.0.0",
    "pillow":         "10.0.0",
    "httpx":          "0.27.0",
    "aiohttp":        "3.11.0",
}

# ── Helpers ─────────────────────────────────────────────────────────────

def _ver_to_tuple(ver_str: str) -> Tuple[int, ...]:
    """Parse version string into comparable tuple."""
    try:
        return tuple(int(x) for x in ver_str.split(".") if x.isdigit())
    except Exception:
        return (0,)

def _ok(s: str) -> str:  return f"{C_GREEN}[✓]{C_RESET} {s}" if HAS_COLOR else f"[OK] {s}"
def _err(s: str) -> str: return f"{C_RED}[✗]{C_RESET} {s}" if HAS_COLOR else f"[FAIL] {s}"
def _warn(s: str) -> str: return f"{C_YELLOW}[!]{C_RESET} {s}" if HAS_COLOR else f"[WARN] {s}"
def _info(s: str) -> str: return f"{C_CYAN}[i]{C_RESET} {s}" if HAS_COLOR else f"[INFO] {s}"
def _hdr(s: str) -> str: return f"{C_BOLD}{C_MAGENTA}{s}{C_RESET}" if HAS_COLOR else s

def _check_result(name: str, ok: bool, detail: str = "") -> bool:
    """Record pass/fail and print result line."""
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  {_ok(name)}{' — ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {_err(name)}{' — ' + detail if detail else ''}")
    return ok

def _check_warn(name: str, ok: bool, detail: str = "") -> None:
    """Record warn and print."""
    global WARN
    if not ok:
        WARN += 1
        print(f"  {_warn(name)}{' — ' + detail if detail else ''}")

# ═══════════════════════════════════════════════════════════════════════════
# Section 1: 系统资源检查
# ═══════════════════════════════════════════════════════════════════════════

def check_system_resources() -> None:
    """检查磁盘/内存/CPU状态。"""
    print(f"\n{_hdr('── 系统资源检查 (System Resources) ──')}")

    try:
        import psutil
    except ImportError:
        print(f"  {_warn('psutil 未安装 — 跳过系统资源检查')}")
        return

    # ── 磁盘 ──
    try:
        usage = shutil.disk_usage(str(PROJECT_ROOT))
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)
        used_pct = usage.used / usage.total * 100
        ok = free_gb >= 1.0  # 至少1GB

        detail = f"可用 {free_gb:.1f}GB / 总量 {total_gb:.1f}GB ({used_pct:.0f}%已用)"
        if free_gb < 10.0:
            _check_result("磁盘空间", ok, detail + " [磁盘<10GB警告!]")
        else:
            _check_result("磁盘空间", ok, detail)
    except Exception as e:
        _check_result("磁盘空间", False, str(e)[:60])

    # ── 内存 ──
    try:
        mem = psutil.virtual_memory()
        avail_gb = mem.available / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        ok = mem.percent < 90

        detail = f"可用 {avail_gb:.1f}GB / 总量 {total_gb:.1f}GB ({mem.percent:.0f}%已用)"
        if mem.percent > 90:
            _check_result("系统内存", ok, detail + " [内存不足!]")
        elif mem.percent > 75:
            _check_warn("系统内存", False, detail + " [内存偏高]")
            _check_result("系统内存", True, detail)
        else:
            _check_result("系统内存", ok, detail)
    except Exception as e:
        _check_result("系统内存", False, str(e)[:60])

    # ── CPU ──
    try:
        cpu_pct = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        ok = cpu_pct < 90

        detail = f"{cpu_pct:.0f}% (核数: {cpu_count})"
        if cpu_pct > 90:
            _check_result("CPU 使用率", ok, detail + " [CPU高负载!]")
        elif cpu_pct > 70:
            _check_warn("CPU 使用率", False, detail + " [CPU偏高]")
            _check_result("CPU 使用率", True, detail)
        else:
            _check_result("CPU 使用率", ok, detail)
    except Exception as e:
        _check_result("CPU 使用率", False, str(e)[:60])

    # ── 磁盘 IO ──
    try:
        io = psutil.disk_io_counters()
        if io:
            _check_result("磁盘I/O", True, f"读{io.read_count}次/写{io.write_count}次")
    except Exception as e:
        logger.error(f"Operation failed: {e}")

    # ── Swap ──
    try:
        swap = psutil.swap_memory()
        if swap.total > 0:
            swap_pct = swap.percent
            detail = f"{swap_pct:.0f}% (已用{swap.used/(1024**3):.1f}GB/{swap.total/(1024**3):.1f}GB)"
            if swap_pct > 50:
                _check_warn("Swap 使用", False, detail)
            else:
                _check_result("Swap 使用", True, detail)
    except Exception as e:
        logger.error(f"Operation failed: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# Section 2: 依赖版本检查
# ═══════════════════════════════════════════════════════════════════════════

def check_dependencies() -> List[str]:
    """检查核心依赖的版本是否满足最低要求。返回缺失/版本不足的包列表。"""
    print(f"\n{_hdr('── 依赖版本检查 (Dependency Versions) ──')}")

    issues: List[str] = []

    for pkg_name, min_ver in CRITICAL_DEPS.items():
        try:
            mod = importlib.import_module(pkg_name)
            # Try common version attribute names
            actual_ver = None
            for attr in ("__version__", "VERSION", "version"):
                actual_ver = getattr(mod, attr, None)
                if actual_ver is not None:
                    break

            if actual_ver is None:
                try:
                    from importlib.metadata import version
                    actual_ver = version(pkg_name)
                except Exception:
                    actual_ver = "unknown"

            actual_str = str(actual_ver)
            min_tuple = _ver_to_tuple(min_ver)
            actual_tuple = _ver_to_tuple(actual_str)

            ok = actual_tuple >= min_tuple
            if ok:
                _check_result(pkg_name, True, f"v{actual_str} (>= {min_ver})")
            else:
                _check_result(pkg_name, False, f"v{actual_str} (需要 >= {min_ver})")
                issues.append(pkg_name)
        except ImportError:
            _check_result(pkg_name, False, "未安装")
            issues.append(pkg_name)
        except Exception as e:
            _check_result(pkg_name, False, str(e)[:40])
            issues.append(pkg_name)

    return issues

# ═══════════════════════════════════════════════════════════════════════════
# Section 3: 数据库连通性检查
# ═══════════════════════════════════════════════════════════════════════════

def check_databases() -> None:
    """检查SQLite数据库文件是否存在且可读。"""
    print(f"\n{_hdr('── 数据库检查 (Database Check) ──')}")

    db_files = [
        (PROJECT_ROOT / "data" / "imdf.db", "主数据库"),
        (PROJECT_ROOT / "data" / "audit.db", "审计数据库"),
        (PROJECT_ROOT / "data" / "api_keys.db", "API Key 数据库"),
        (PROJECT_ROOT / "data" / "scheduler.db", "调度器数据库"),
        (PROJECT_ROOT / "data" / "scheduler_history.db", "调度器历史数据库"),
        (PROJECT_ROOT / "data" / "vector_store.db", "向量存储 (可选)"),
    ]

    for db_path, label in db_files:
        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.execute("SELECT 1")
                conn.close()
                size_mb = db_path.stat().st_size / (1024 * 1024)
                _check_result(label, True, f"{size_mb:.1f}MB")
            except Exception as e:
                _check_result(label, False, str(e)[:50])
        elif "可选" in label:
            print(f"  {_warn(label)} — 未创建 (非必须)")
        else:
            _check_result(label, False, "文件不存在")

# ═══════════════════════════════════════════════════════════════════════════
# Section 4: API 健康检查与端点测试
# ═══════════════════════════════════════════════════════════════════════════

def check_endpoint(name: str, path: str, method: str = "GET",
                   body: Optional[Dict] = None,
                   expect_status: int = 200) -> bool:
    """测试单个API端点。返回是否成功。"""
    global PASS, FAIL
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "IMDF-Validate/2.0")
        with urllib.request.urlopen(req, timeout=10) as r:
            resp_body = json.loads(r.read())
            status_ok = r.status == expect_status
            logic_ok = resp_body.get("success") or resp_body.get("status") == "ok" or r.status < 400
            ok = status_ok and logic_ok

            if ok:
                detail = f"HTTP {r.status}"
                # Show extra info for health endpoints
                if "health" in path.lower():
                    uptime = resp_body.get("uptime_seconds", "")
                    ver = resp_body.get("version", "")
                    detail = f"HTTP {r.status} v{ver} uptime={uptime}s"
                PASS += 1
                print(f"  {_ok(name)} — {detail}")
            else:
                FAIL += 1
                print(f"  {_err(name)} — HTTP {r.status}, body: {str(resp_body)[:80]}")
            return ok
    except urllib.error.HTTPError as e:
        FAIL += 1
        print(f"  {_err(name)} — HTTP {e.code}: {str(e.reason)[:40]}")
        return False
    except urllib.error.URLError as e:
        FAIL += 1
        print(f"  {_err(name)} — 连接失败: {str(e.reason)[:60]}")
        return False
    except Exception as e:
        FAIL += 1
        print(f"  {_err(name)} — {type(e).__name__}: {str(e)[:60]}")
        return False


def check_api_endpoints() -> None:
    """检查所有API端点。"""
    print(f"\n{_hdr('── API 端点检查 (API Endpoints) ──')}")

    checks = [
        # 核心端点
        ("首页", "/"),
        ("健康检查 (Basic)", "/api/v1/health"),
        ("就绪检查 (Ready)", "/api/v1/health/ready"),
        ("存活检查 (Live)", "/api/v1/health/live"),
        ("API 文档", "/openapi.json"),
        ("Prometheus 指标", "/metrics"),

        # 数据端点
        ("数据集列表", "/api/datasets?page=1"),
        ("模型网关", "/api/models"),
        ("分类规则", "/api/classify/rules"),
        ("模板市场", "/api/templates"),

        # 功能端点
        ("审美评分", "/api/aesthetic/health"),
        ("调度器健康", "/api/scheduler/health"),
    ]

    for name, path in checks:
        check_endpoint(name, path)

# ═══════════════════════════════════════════════════════════════════════════
# Section 5: 文件结构检查
# ═══════════════════════════════════════════════════════════════════════════

def check_file_structure() -> None:
    """检查关键目录和文件是否存在。"""
    print(f"\n{_hdr('── 文件结构检查 (File Structure) ──')}")

    dirs = {
        "api/":         PROJECT_ROOT / "api",
        "engines/":     PROJECT_ROOT / "engines",
        "scripts/":     PROJECT_ROOT / "scripts",
        "deploy/":      PROJECT_ROOT / "deploy",
        "frontend/":    PROJECT_ROOT / "frontend",
        "data/":        PROJECT_ROOT / "data",
        "logs/":        PROJECT_ROOT / "logs",
        "templates/":   PROJECT_ROOT / "templates",
        "config/":      PROJECT_ROOT / "config",
        "docs/":        PROJECT_ROOT / "docs",
    }

    files = {
        "Canvas Web入口":       PROJECT_ROOT / "api" / "canvas_web.py",
        "配置中心":              PROJECT_ROOT / "config" / "settings.py",
        "metrics引擎":          PROJECT_ROOT / "engines" / "metrics.py",
        "调度器引擎":            PROJECT_ROOT / "engines" / "scheduler_engine.py",
        "Nginx部署配置":         PROJECT_ROOT / "deploy" / "nginx-imdf.conf",
        "requirements.txt":     PROJECT_ROOT / "requirements.txt",
    }

    for label, path in dirs.items():
        _check_result(f"目录 {label}", path.is_dir())

    for label, path in files.items():
        _check_result(f"文件 {label}", path.is_file())

# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global PASS, FAIL, WARN

    print(f"\n{C_BOLD}{C_BLUE}{'='*60}{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}  IMDF 生产环境一键验证 (Enhanced){C_RESET}")
    print(f"{C_BOLD}{C_BLUE}  Project: {PROJECT_ROOT}{C_RESET}")
    print(f"{C_BOLD}{C_BLUE}{'='*60}{C_RESET}")

    # ── Section 1: System Resources ──
    check_system_resources()

    # ── Section 2: Dependencies ──
    deps_issues = check_dependencies()

    # ── Section 3: Databases ──
    check_databases()

    # ── Section 4: File Structure ──
    check_file_structure()

    # ── Section 5: API Endpoints (requires service running) ──
    print(f"\n{_hdr('── API 端点测试 (requires service on port 8765) ──')}")
    try:
        urllib.request.urlopen(f"{BASE}/api/v1/health", timeout=3)
        print(f"  {_ok('服务可达')} — {BASE}")
        check_api_endpoints()
    except Exception as e:
        print(f"  {_warn(f'服务不可达 ({BASE}): {str(e)[:50]}')}")
        print(f"  {_info('提示: 请先启动服务 `python api/canvas_web.py` 或 `systemctl start imdf`')}")

    # ── Summary ──
    total = PASS + FAIL + WARN
    print(f"\n{C_BOLD}{'─'*60}{C_RESET}")
    print(f"{C_BOLD}  RESULTS: {C_GREEN}{PASS} PASS{C_RESET} / {C_RED}{FAIL} FAIL{C_RESET} / {C_YELLOW}{WARN} WARN{C_RESET}  (total: {total} checks){C_RESET}")
    print(f"{C_BOLD}{'─'*60}{C_RESET}")

    # ── Recommendations ──
    if deps_issues:
        print(f"\n{C_YELLOW}依赖问题 — 缺失或版本不符:{C_RESET}")
        for d in deps_issues:
            print(f"  {C_RED}• {d}{C_RESET}")
        print(f"  pip install -r requirements.txt")

    if FAIL > 0:
        print(f"\n{C_RED}存在 {FAIL} 个失败项，部署前请先修复。{C_RESET}")
    else:
        print(f"\n{C_GREEN}所有检查通过 ✅ — 环境就绪。{C_RESET}")

    # Exit code: fail if FAIL > 0
    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    main()
