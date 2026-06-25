"""Collect per-process CPU/mem/disk/network metrics for the 12 services + gateway.

Run in a background thread or subprocess during the load test.
Outputs a JSON file with snapshots every N seconds.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import psutil

LOG_DIR = Path(__file__).resolve().parent / "services"
OUTPUT = Path(__file__).resolve().parent / "metrics_snapshots.json"

# Service name -> port
SERVICES = {
    "gateway":      8000,
    "user":         8001,
    "asset":        8002,
    "annotation":   8003,
    "cleaning":     8004,
    "scoring":      8005,
    "dataset":      8006,
    "evaluation":   8007,
    "agent":        8008,
    "workflow":     8009,
    "notification": 8010,
    "search":       8011,
    "collection":   8012,
}


def _find_pid_by_port(port: int) -> int | None:
    for c in psutil.net_connections(kind="inet"):
        if c.laddr and c.laddr.port == port and c.status == "LISTEN" and c.pid:
            return c.pid
    return None


def _snapshot() -> dict:
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    procs = {}
    for name, port in SERVICES.items():
        pid = _find_pid_by_port(port)
        if not pid:
            procs[name] = {"port": port, "pid": None, "status": "no-pid"}
            continue
        try:
            p = psutil.Process(pid)
            mem = p.memory_info()
            cpu = p.cpu_percent(interval=0.1)  # 100ms sample
            procs[name] = {
                "port": port,
                "pid": pid,
                "status": p.status(),
                "cpu_pct": cpu,
                "rss_mb": mem.rss / 1024 / 1024,
                "vms_mb": mem.vms / 1024 / 1024,
                "num_threads": p.num_threads(),
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            procs[name] = {"port": port, "pid": pid, "status": "gone"}
    return {
        "ts": time.time(),
        "host": {
            "cpu_pct": psutil.cpu_percent(interval=0.1),
            "cpu_count": psutil.cpu_count(),
            "mem_pct": psutil.virtual_memory().percent,
            "mem_used_mb": psutil.virtual_memory().used / 1024 / 1024,
            "mem_total_mb": psutil.virtual_memory().total / 1024 / 1024,
            "disk_used_pct": disk.percent,
            "net_bytes_sent_mb": net.bytes_sent / 1024 / 1024,
            "net_bytes_recv_mb": net.bytes_recv / 1024 / 1024,
        },
        "processes": procs,
    }


def main():
    interval_s = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    duration_s = float(sys.argv[2]) if len(sys.argv) > 2 else 360.0
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else OUTPUT

    print(f"Collecting metrics every {interval_s}s for {duration_s}s -> {out_path}")
    snaps = []
    t0 = time.time()
    while time.time() - t0 < duration_s:
        try:
            snap = _snapshot()
            snaps.append(snap)
            host = snap["host"]
            top_cpu = max(
                ((n, p.get("cpu_pct", 0)) for n, p in snap["processes"].items() if "cpu_pct" in p),
                key=lambda x: x[1], default=("?", 0),
            )
            top_mem = max(
                ((n, p.get("rss_mb", 0)) for n, p in snap["processes"].items() if "rss_mb" in p),
                key=lambda x: x[1], default=("?", 0),
            )
            print(
                f"  t+{snap['ts']-t0:5.1f}s | host cpu {host['cpu_pct']:5.1f}% mem {host['mem_pct']:5.1f}% | "
                f"top svc cpu {top_cpu[0]}={top_cpu[1]:.1f}% mem {top_mem[0]}={top_mem[1]:.1f}MB"
            )
        except Exception as e:
            print(f"  snapshot err: {e}")
        time.sleep(interval_s)

    out_path.write_text(json.dumps(snaps, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(snaps)} snapshots to {out_path}")


if __name__ == "__main__":
    main()
