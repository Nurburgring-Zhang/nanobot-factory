"""R10.5-Worker-3: 性能基线 — 100 健康端点请求 p50/p95/p99

复用 R8 perf_baseline.csv 方法 (test_factories_baseline.py):

  * TestClient 直接 import canvas_web:app, 不起 uvicorn (R8 验证: 起 uvicorn
    要 8-15s, TestClient <1s 启动)
  * 一次 warmup 跳开 first-call costs (imports / JIT)
  * N 次顺序请求, 记每次 wall-clock
  * 输出 CSV 给 report 引用

主要 measurement:
  - /healthz p95 (cheap liveness probe, 框架开销基线)
  - /readyz p95 (DB ping 包含, 中等开销基线)
  - /metrics p95 (Prometheus 抓取开销基线)

阈值 (沿用 R8):
  - /healthz p95 < 500ms
  - /readyz p95 < 800ms
  - /metrics p95 < 1500ms (Prometheus 文本渲染稍重)

不是真负载测试 — 是单请求顺序基线, 100 并发下会高 10-100x, 需要 wrk/k6。
这里只是"回归锚点", 如果哪天 p95 突然涨 50ms, 就是有东西改坏了。
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Path bootstrap — 在 pytest collected 阶段把 backend/imdf 加进 sys.path
# 这样无论 cwd 是 backend/ 还是项目根都能 import api.canvas_web
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve().parent
_PROJ_ROOT = _HERE.parents[2]  # backend/tests/perf -> nanobot-factory
_IMDF = _PROJ_ROOT / "backend" / "imdf"
for p in (str(_IMDF), str(_PROJ_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 强制 test JWT secret (R7/R8 经验: 没这个会 500)
import os  # noqa: E402
os.environ.setdefault(
    "JWT_SECRET",
    "test-jwt-secret-for-pytest-only-do-not-use-in-prod",
)

from fastapi.testclient import TestClient  # noqa: E402

# --------------------------------------------------------------------------- #
# Session-scoped app import — canvas_web.py 注册 ~50 routers, 10-15s 一次
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def canvas_app():
    from api.canvas_web import app
    return app


@pytest.fixture(scope="module")
def client(canvas_app):
    with TestClient(canvas_app) as c:
        yield c


# --------------------------------------------------------------------------- #
# CSV writer — 复用 R8 perf_baseline.csv 的 section 风格
# --------------------------------------------------------------------------- #
def _write_perf_csv(path: Path, sections: list[tuple[str, dict[str, float]]]) -> None:
    """Write a multi-section perf CSV.

    Each section is ("name", {metric: value_ms}). The CSV format::

        metric,value_ms
        min,1.006
        p50,1.146
        ...
        ---<name>---
        ...

    Every section (including the first) gets a `---<name>---` header so
    downstream parsers can reliably identify sections by name.
    """
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for i, (name, metrics) in enumerate(sections):
            if i == 0:
                writer.writerow(["metric", "value_ms"])
            writer.writerow([f"---{name}---"])
            for metric, value in metrics.items():
                if metric == "n":
                    writer.writerow([metric, int(value)])
                else:
                    writer.writerow([metric, f"{value:.3f}"])


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Compute q-th percentile (0 < q < 1) from pre-sorted values."""
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(q * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def _measure_endpoint(client, path: str, n: int) -> dict[str, float]:
    """Sequentially hit ``path`` ``n`` times, return latency stats in ms.

    Returns ``{min, p50, p95, p99, max, n}``. Raises if any response is 5xx.
    """
    # One warm-up to skip first-call costs.
    client.get(path)

    latencies: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = client.get(path)
        dt = (time.perf_counter() - t0) * 1000.0

        # 5xx = something is broken; surface immediately so we don't
        # silently record bogus latency for a failing endpoint.
        assert r.status_code < 500, f"{path} returned {r.status_code}: {r.text[:200]}"

        latencies.append(dt)

    sorted_lat = sorted(latencies)
    return {
        "min": min(sorted_lat),
        "p50": _percentile(sorted_lat, 0.50),
        "p95": _percentile(sorted_lat, 0.95),
        "p99": _percentile(sorted_lat, 0.99),
        "max": max(sorted_lat),
        "n": float(n),
    }


# --------------------------------------------------------------------------- #
# Tests — 一主二辅, 输出一个 combined CSV
# --------------------------------------------------------------------------- #
class TestPerfBaseline:
    """R10.5 perf baseline — 100 sequential /healthz requests, plus /readyz
    and /metrics as secondary signals. p95 thresholds follow R8.
    """

    def test_healthz_100_requests_p95_under_500ms(self, client):
        """Main test: 100 sequential /healthz hits, p95 < 500 ms."""
        N = 100
        stats = _measure_endpoint(client, "/healthz", N)

        # Persist to CSV for the report to pick up.
        out = _HERE / "perf_baseline_r10_5.csv"
        _write_perf_csv(out, [("/healthz", stats)])

        assert stats["p95"] < 500.0, (
            f"/healthz p95 {stats['p95']:.1f}ms exceeds 500ms target; "
            f"p50={stats['p50']:.1f} p99={stats['p99']:.1f} "
            f"max={stats['max']:.1f} (n={int(stats['n'])})"
        )

    def test_readyz_50_requests_p95_under_800ms(self, client):
        """Secondary: /readyz includes DB ping — p95 < 800ms (R8 threshold)."""
        N = 50
        stats = _measure_endpoint(client, "/readyz", N)

        out = _HERE / "perf_baseline_r10_5.csv"
        # Append a section without overwriting /healthz
        with open(out, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["---/readyz---"])
            for k, v in stats.items():
                if k == "n":
                    writer.writerow([k, int(v)])
                else:
                    writer.writerow([k, f"{v:.3f}"])

        # /readyz may legitimately be 503 (DB missing) — we already asserted
        # no 5xx in _measure_endpoint. Re-assert here that p95 is sane.
        assert stats["p95"] < 800.0, (
            f"/readyz p95 {stats['p95']:.1f}ms exceeds 800ms target; "
            f"p50={stats['p50']:.1f} (n={int(stats['n'])})"
        )

    def test_metrics_50_requests_p95_under_1500ms(self, client):
        """Secondary: /metrics is Prometheus text rendering — p95 < 1500ms."""
        N = 50
        stats = _measure_endpoint(client, "/metrics", N)

        out = _HERE / "perf_baseline_r10_5.csv"
        with open(out, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["---/metrics---"])
            for k, v in stats.items():
                if k == "n":
                    writer.writerow([k, int(v)])
                else:
                    writer.writerow([k, f"{v:.3f}"])

        assert stats["p95"] < 1500.0, (
            f"/metrics p95 {stats['p95']:.1f}ms exceeds 1500ms target; "
            f"p50={stats['p50']:.1f} (n={int(stats['n'])})"
        )

    def test_perf_csv_has_three_sections(self):
        """Sanity: the CSV produced above has /healthz, /readyz, /metrics."""
        out = _HERE / "perf_baseline_r10_5.csv"
        assert out.exists(), f"{out} missing — earlier tests should have created it"
        text = out.read_text(encoding="utf-8")
        assert "/healthz" in text
        assert "/readyz" in text
        assert "/metrics" in text
        assert text.count("p95") >= 3


class TestPerfSummary:
    """Single-test summary that prints a tidy table for log / report grep."""

    def test_summary_print(self, client):
        """Print one-line per endpoint summary for `reports/r10_5_w3.md` to cite.

        This is a *display* test — it doesn't fail on any specific threshold,
        it just measures and prints. Marking it informational via no-assert.
        """
        import io
        buf = io.StringIO()

        for path, n in [("/healthz", 100), ("/readyz", 50), ("/metrics", 50)]:
            stats = _measure_endpoint(client, path, n)
            line = (
                f"{path:<12} n={int(stats['n']):>4}  "
                f"min={stats['min']:>6.2f}ms  "
                f"p50={stats['p50']:>6.2f}ms  "
                f"p95={stats['p95']:>6.2f}ms  "
                f"p99={stats['p99']:>6.2f}ms  "
                f"max={stats['max']:>6.2f}ms"
            )
            print(f"\n[PERF] {line}", file=buf)
            print(f"\n[PERF] {line}")

        # Save the captured summary alongside the CSV.
        (out := _HERE / "perf_summary.txt").write_text(
            buf.getvalue(), encoding="utf-8"
        )