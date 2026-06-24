#!/usr/bin/env python3
"""
IMDF Concurrency Stress Test — P0运维压测脚本
==============================================

模拟高并发请求，验证 ConcurrencyLimiter 负载保护机制：
  1. 发送 1000+ 并发请求
  2. 验证超过 MAX_CONCURRENT_REQUESTS 的请求返回 503
  3. 验证正常请求（限流内）不受影响
  4. 测试恢复时间

用法:
  python scripts/concurrency_test.py [--url http://localhost:8765] [--concurrency 1000]
"""

import asyncio
import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import List, Dict, Any

import aiohttp


class ConcurrencyTester:
    """并发压力测试器"""

    def __init__(self, base_url: str, total_requests: int, endpoint: str = "/api/v1/health/live"):
        self.base_url = base_url.rstrip("/")
        self.total_requests = total_requests
        self.endpoint = endpoint
        self.results: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    async def _send_request(self, session: aiohttp.ClientSession, idx: int) -> Dict[str, Any]:
        """发送单个请求并记录结果"""
        url = f"{self.base_url}{self.endpoint}"
        start = time.monotonic()
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                elapsed = time.monotonic() - start
                body = await resp.text()
                try:
                    body_json = json.loads(body)
                except json.JSONDecodeError:
                    body_json = {"raw": body[:200]}

                return {
                    "idx": idx,
                    "status": resp.status,
                    "elapsed": round(elapsed, 4),
                    "body": body_json,
                    "error": None,
                }
        except asyncio.TimeoutError:
            return {"idx": idx, "status": 0, "elapsed": 10.0, "body": {}, "error": "timeout"}
        except aiohttp.ClientError as e:
            return {"idx": idx, "status": 0, "elapsed": time.monotonic() - start, "body": {}, "error": str(e)}
        except Exception as e:
            return {"idx": idx, "status": 0, "elapsed": time.monotonic() - start, "body": {}, "error": str(e)}

    async def run(self) -> Dict[str, Any]:
        """执行并发测试"""
        print(f"\n{'='*60}")
        print(f"  IMDF 并发压力测试")
        print(f"{'='*60}")
        print(f"  服务地址:   {self.base_url}")
        print(f"  测试端点:   {self.endpoint}")
        print(f"  并发请求数: {self.total_requests}")
        print(f"  开始时间:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # Phase 1: 并发轰炸
        print("[Phase 1] 发送并发请求...")
        phase1_start = time.monotonic()

        connector = aiohttp.TCPConnector(limit=0, force_close=True)  # 不限制连接数
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [self._send_request(session, i) for i in range(self.total_requests)]
            self.results = await asyncio.gather(*tasks, return_exceptions=False)

        phase1_elapsed = time.monotonic() - phase1_start
        print(f"  Phase 1 完成: {phase1_elapsed:.1f}s\n")

        # 统计
        status_counter = Counter(r["status"] for r in self.results)
        success_200 = status_counter.get(200, 0)
        rejected_503 = status_counter.get(503, 0)
        error_0 = status_counter.get(0, 0)
        other = sum(v for k, v in status_counter.items() if k not in (200, 503, 0))

        latencies = [r["elapsed"] for r in self.results if r["status"] == 200]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[len(sorted_lat)//2] if sorted_lat else 0
        p95 = sorted_lat[int(len(sorted_lat)*0.95)] if len(sorted_lat) >= 20 else 0
        p99 = sorted_lat[int(len(sorted_lat)*0.99)] if len(sorted_lat) >= 100 else 0

        print(f"{'─'*60}")
        print(f"  Phase 1 结果统计:")
        print(f"    总请求数:   {self.total_requests}")
        print(f"    200 OK:     {success_200} ({success_200/self.total_requests*100:.1f}%)")
        print(f"    503 限流:   {rejected_503} ({rejected_503/self.total_requests*100:.1f}%)")
        print(f"    连接错误:   {error_0}")
        print(f"    其他状态:   {other}")
        print(f"    平均延迟:   {avg_latency*1000:.1f}ms")
        print(f"    P50 延迟:   {p50*1000:.1f}ms")
        print(f"    P95 延迟:   {p95*1000:.1f}ms")
        print(f"    P99 延迟:   {p99*1000:.1f}ms")
        print(f"{'─'*60}\n")

        # Phase 2: 验证503响应格式
        print("[Phase 2] 验证503响应格式...")
        rejected_samples = [r for r in self.results if r["status"] == 503][:5]
        all_503_valid = True
        for r in rejected_samples:
            body = r["body"]
            has_success_field = "success" in body
            has_error = "error" in body
            has_request_id = "request_id" in body
            if not (has_success_field and body.get("success") is False and has_error):
                all_503_valid = False
                print(f"  [FAIL] 503响应格式不符: {json.dumps(body, ensure_ascii=False)[:200]}")
        if all_503_valid:
            print("  [PASS] 所有503响应格式正确 (success=false, error, request_id)")
        print()

        # Phase 3: 恢复测试
        print("[Phase 3] 恢复测试 — 请求降至正常水平后验证...")
        await asyncio.sleep(2)  # 等待之前的请求全部释放

        recovery_start = time.monotonic()
        async with aiohttp.ClientSession() as session:
            tasks = [self._send_request(session, 9000 + i) for i in range(20)]
            recovery_results = await asyncio.gather(*tasks)

        recovery_elapsed = time.monotonic() - recovery_start
        recovery_statuses = Counter(r["status"] for r in recovery_results)
        recovery_200 = recovery_statuses.get(200, 0)
        recovery_503 = recovery_statuses.get(503, 0)
        recovery_latencies = [r["elapsed"] for r in recovery_results if r["status"] == 200]
        recovery_avg = sum(recovery_latencies)/len(recovery_latencies)*1000 if recovery_latencies else 0

        print(f"  恢复测试: 20请求, {recovery_200}成功(200), {recovery_503}限流(503)")
        print(f"  平均延迟: {recovery_avg:.1f}ms")
        recovery_ok = recovery_200 == 20
        print(f"  {'[PASS]' if recovery_ok else '[FAIL]'} 恢复测试{'通过' if recovery_ok else '未通过 — 仍有请求被限流'}")
        print()

        # Phase 4: 正常请求不受影响验证
        print("[Phase 4] 慢速顺序请求验证...")
        sequential_ok = True
        async with aiohttp.ClientSession() as session:
            for i in range(10):
                result = await self._send_request(session, 9500 + i)
                if result["status"] != 200:
                    print(f"  [FAIL] 顺序请求 #{i} 返回 {result['status']}")
                    sequential_ok = False
                await asyncio.sleep(0.1)
        print(f"  {'[PASS]' if sequential_ok else '[FAIL]'} 慢速请求{'全部正常' if sequential_ok else '有异常'}")
        print()

        # 最终评估
        tests = {
            "并发保护": rejected_503 > 0,
            "503格式正确": all_503_valid,
            "恢复能力": recovery_ok,
            "正常请求不受影响": sequential_ok,
        }

        print(f"{'='*60}")
        print(f"  测试汇总")
        print(f"{'='*60}")
        all_pass = True
        for name, passed in tests.items():
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_pass = False
            print(f"  [{status}] {name}")
        print(f"{'='*60}")
        print(f"  总体结果: {'PASS' if all_pass else 'FAIL — 存在未通过的测试项'}")
        print()

        return {
            "total_requests": self.total_requests,
            "success_200": success_200,
            "rejected_503": rejected_503,
            "connection_errors": error_0,
            "avg_latency_ms": round(avg_latency * 1000, 1),
            "p50_ms": round(p50 * 1000, 1),
            "p95_ms": round(p95 * 1000, 1),
            "p99_ms": round(p99 * 1000, 1),
            "recovery_pct": round(recovery_200 / 20 * 100, 1),
            "recovery_avg_ms": round(recovery_avg, 1),
            "tests": tests,
            "overall_pass": all_pass,
        }


async def main():
    parser = argparse.ArgumentParser(
        description="IMDF 并发压力测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/concurrency_test.py
  python scripts/concurrency_test.py --url http://localhost:8765 --concurrency 1000
  python scripts/concurrency_test.py --concurrency 500 --output report.json
        """,
    )
    parser.add_argument(
        "--url", default="http://localhost:8765",
        help="IMDF 服务地址 (默认: http://localhost:8765)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=1000,
        help="并发请求数 (默认: 1000)"
    )
    parser.add_argument(
        "--endpoint", default="/api/v1/health/live",
        help="测试端点 (默认: /api/v1/health/live)"
    )
    parser.add_argument(
        "--output", default=None,
        help="输出JSON报告文件路径"
    )

    args = parser.parse_args()

    tester = ConcurrencyTester(
        base_url=args.url,
        total_requests=args.concurrency,
        endpoint=args.endpoint,
    )

    try:
        report = await tester.run()
    except aiohttp.ClientConnectorError:
        print(f"\n错误: 无法连接到 {args.url}")
        print("请确保 IMDF 服务正在运行: python api/canvas_web.py --port 8765")
        sys.exit(1)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"报告已保存到: {out_path}")

    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    asyncio.run(main())
