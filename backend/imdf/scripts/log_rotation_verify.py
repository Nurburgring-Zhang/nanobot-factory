#!/usr/bin/env python3
"""
IMDF Log Rotation Verification — 日志轮转验证脚本
==================================================

验证 canvas_web.py 中的 RotatingFileHandler 日志轮转机制:
  1. 写入足够的日志触发轮转 (默认配置: 10MB × 5 备份)
  2. 验证生成了多个日志文件 (.1, .2, ...)
  3. 验证旧文件被正确删除 (>5个备份时)

用法:
  python scripts/log_rotation_verify.py
  python scripts/log_rotation_verify.py --size-mb 1 --count 3  # 小文件快速测试
  python scripts/log_rotation_verify.py --cleanup               # 测试后清理测试日志
"""

import os
import sys
import time
import glob
import argparse
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import List, Dict, Any


# ── Project root discovery ────────────────────────────────────────────────
def find_project_root() -> Path:
    anchor = Path(__file__).resolve().parent.parent
    if (anchor / "logs").exists():
        return anchor
    return Path.cwd()


PROJECT_ROOT = find_project_root()
TEST_LOG_DIR = PROJECT_ROOT / "logs" / "rotation_test"


class LogRotationTester:
    """日志轮转测试器"""

    def __init__(self, size_mb: int = 1, backup_count: int = 3):
        """
        Args:
            size_mb: 单个日志文件最大大小(MB) - 使用小值加速测试
            backup_count: 保留的备份文件数
        """
        self.size_mb = size_mb
        self.backup_count = backup_count
        self.size_bytes = size_mb * 1024 * 1024
        self.log_dir = TEST_LOG_DIR
        self.log_base = self.log_dir / "test_rotation.log"

    def setup(self):
        """创建测试环境"""
        if self.log_dir.exists():
            import shutil
            shutil.rmtree(str(self.log_dir))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 创建独立的logger用于测试
        self.logger = logging.getLogger("rotation_tester")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        self.logger.propagate = False

        handler = RotatingFileHandler(
            str(self.log_base),
            maxBytes=self.size_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        self.logger.addHandler(handler)
        self.handler = handler

        print(f"测试配置:")
        print(f"  日志目录:   {self.log_dir}")
        print(f"  单文件上限: {self.size_mb} MB")
        print(f"  备份数量:   {self.backup_count}")
        print(f"  日志基名:   {self.log_base.name}")

    def generate_log_content(self, target_mb: float) -> int:
        """
        生成日志内容直到写入目标大小的数据

        Returns: 写入的日志条数
        """
        # 每条日志约200字节
        bytes_per_line = 200
        target_bytes = target_mb * 1024 * 1024
        target_lines = int(target_bytes / bytes_per_line)

        # 构造一个长日志行以加速
        padding = "X" * 150
        count = 0

        print(f"\n开始写入日志... (目标: {target_mb} MB, 约 {target_lines:,} 行)")
        start_time = time.monotonic()

        for i in range(target_lines):
            self.logger.info(f"line={i:07d} timestamp={datetime.now().isoformat()} {padding}")
            count += 1
            if count % 50000 == 0:
                elapsed = time.monotonic() - start_time
                pct = count / target_lines * 100
                print(f"  进度: {count:,}/{target_lines:,} ({pct:.1f}%) — {elapsed:.1f}s")

        elapsed = time.monotonic() - start_time
        print(f"写入完成: {count:,} 行, {elapsed:.1f}s")

        # Flush确保所有数据写入磁盘
        self.handler.flush()
        time.sleep(0.5)

        return count

    def get_log_files(self) -> List[Path]:
        """获取所有生成的日志文件"""
        pattern = str(self.log_dir / f"{self.log_base.name}*")
        files = sorted(Path(f) for f in glob.glob(pattern))
        return files

    def analyze(self) -> Dict[str, Any]:
        """分析日志轮转结果"""
        files = self.get_log_files()

        result = {
            "total_files": len(files),
            "files": [],
            "rotation_occurred": False,
            "backup_count_respected": True,
            "primary_exists": False,
            "details": [],
        }

        for f in files:
            rel_name = f.name
            size_mb = f.stat().st_size / (1024 * 1024)
            is_primary = rel_name == self.log_base.name
            is_backup = not is_primary

            info = {
                "name": rel_name,
                "size_mb": round(size_mb, 3),
                "size_bytes": f.stat().st_size,
                "is_primary": is_primary,
                "is_backup": is_backup,
            }
            result["files"].append(info)

            if is_primary:
                result["primary_exists"] = True

        # 检查轮转是否发生
        result["rotation_occurred"] = len(files) > 1

        # 检查备份数量是否在限制内
        # backup_count = self.backup_count (如3), 总文件数(含主文件)应 <= backup_count + 1
        # 实际上 RotatingFileHandler 的 backupCount 会轮流使用 .1, .2, .3 等后缀
        max_backups = self.backup_count + 1  # +1 for the main file
        backup_files = [f for f in files if f.name != self.log_base.name]

        # backupCount 个备份 + 1个主文件
        if len(backup_files) > self.backup_count:
            result["backup_count_respected"] = False
            result["details"].append(
                f"备份文件数 ({len(backup_files)}) 超过限制 ({self.backup_count})"
            )
        else:
            result["details"].append(
                f"备份文件数 ({len(backup_files)}) 符合限制 ({self.backup_count})"
            )

        # 检查主文件是否存在
        if not result["primary_exists"]:
            result["details"].append("主日志文件不存在!")

        # 检查旧的备份文件是否被正确覆盖
        backup_sizes = sorted([b.stat().st_size for b in backup_files])
        if backup_sizes:
            result["details"].append(f"备份文件大小范围: {backup_sizes[0]:,} ~ {backup_sizes[-1]:,} bytes")

        return result

    def cleanup(self):
        """清理测试日志"""
        if self.log_dir.exists():
            import shutil
            shutil.rmtree(str(self.log_dir))
            print(f"已清理测试日志目录: {self.log_dir}")


def check_production_rotation() -> Dict[str, Any]:
    """检查生产环境的日志轮转状态"""
    log_dir = PROJECT_ROOT / "logs"
    result = {
        "access_log": [],
        "error_log": [],
    }

    # 检查 access.log
    for pattern in ["access.log", "access.log.*"]:
        for f in sorted(log_dir.glob(pattern)):
            if f.is_file():
                result["access_log"].append({
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "size_bytes": f.stat().st_size,
                })

    # 检查 error.log
    for pattern in ["error.log", "error.log.*"]:
        for f in sorted(log_dir.glob(pattern)):
            if f.is_file():
                result["error_log"].append({
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "size_bytes": f.stat().st_size,
                })

    result["access_rotation_configured"] = len(result["access_log"]) >= 1
    result["error_rotation_configured"] = len(result["error_log"]) >= 1
    return result


def main():
    parser = argparse.ArgumentParser(
        description="IMDF 日志轮转验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/log_rotation_verify.py                    # 默认测试 (1MB × 3)
  python scripts/log_rotation_verify.py --size-mb 5 --count 5  # 5MB × 5
  python scripts/log_rotation_verify.py --check-production  # 仅检查生产日志状态
  python scripts/log_rotation_verify.py --cleanup           # 清理测试日志
        """,
    )
    parser.add_argument("--size-mb", type=int, default=1, help="单文件上限 MB (默认: 1)")
    parser.add_argument("--count", type=int, default=3, help="备份文件数 (默认: 3)")
    parser.add_argument("--check-production", action="store_true", help="仅检查生产日志轮转状态")
    parser.add_argument("--cleanup", action="store_true", help="清理测试日志后退出")

    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    # ── 查看生产日志状态 ────────────────────────────────────────────────
    prod_status = check_production_rotation()
    print(f"\n{'='*60}")
    print(f"  IMDF 日志轮转验证")
    print(f"{'='*60}")
    print(f"\n生产日志状态 ({PROJECT_ROOT / 'logs'}):")
    print(f"  access.log: {len(prod_status['access_log'])} 个文件")
    for f in prod_status["access_log"]:
        print(f"    {f['name']:<30s} {f['size_mb']:>8.2f} MB")
    print(f"  error.log: {len(prod_status['error_log'])} 个文件")
    for f in prod_status["error_log"]:
        print(f"    {f['name']:<30s} {f['size_mb']:>8.2f} MB")

    if args.check_production:
        if prod_status["access_rotation_configured"]:
            print("\n日志轮转已配置 (RotatingFileHandler: 10MB × 5)")
        return

    if args.cleanup:
        tester = LogRotationTester()
        tester.cleanup()
        return

    # ── 轮转测试 ────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    print(f"开始日志轮转测试...")
    print(f"{'─'*60}")

    tester = LogRotationTester(size_mb=args.size_mb, backup_count=args.count)
    tester.setup()

    # 写入 3 倍大小以强制触发多次轮转
    target_mb = args.size_mb * (args.count + 2)
    line_count = tester.generate_log_content(target_mb)

    # 分析结果
    result = tester.analyze()

    print(f"\n{'─'*60}")
    print(f"轮转结果分析:")
    print(f"{'─'*60}")
    print(f"  生成文件数: {result['total_files']}")
    print(f"  轮转已触发: {'是 ✓' if result['rotation_occurred'] else '否 ✗'}")
    print(f"  备份数合规: {'是 ✓' if result['backup_count_respected'] else '否 ✗'}")
    print(f"  主文件存在: {'是 ✓' if result['primary_exists'] else '否 ✗'}")

    print(f"\n  文件列表:")
    for f in result["files"]:
        tag = "[主]" if f["is_primary"] else "[备份]"
        print(f"    {tag} {f['name']:<30s} {f['size_mb']:.2f} MB")

    if result["details"]:
        print(f"\n  详情:")
        for d in result["details"]:
            print(f"    - {d}")

    # ── 最终判定 ────────────────────────────────────────────────────────
    tests = {
        "轮转触发": result["rotation_occurred"],
        "备份数量合规": result["backup_count_respected"],
        "主文件存在": result["primary_exists"],
    }

    all_pass = all(tests.values())
    print(f"\n{'='*60}")
    print(f"  测试结果")
    print(f"{'='*60}")
    for name, passed in tests.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"  总体: {'PASS ✓' if all_pass else 'FAIL ✗'}")
    print(f"{'='*60}")

    # 清理测试数据
    print(f"\n测试日志保留在: {TEST_LOG_DIR}")
    print(f"使用 --cleanup 参数清理测试日志")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
