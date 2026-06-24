#!/usr/bin/env python3
"""
IMDF Restore Script — 从备份恢复
==================================

功能:
  - 从指定 tar.gz 备份文件恢复
  - 验证数据完整性 (校验数据库、文件数量)
  - 支持完整恢复和选择性恢复 (仅DB/仅配置)
  - 自动创建恢复前快照 (安全回滚)
  - 记录恢复日志到 data/backups/restore.log

用法:
  python scripts/restore.py <backup_file>              # 全量恢复(创建安全快照)
  python scripts/restore.py <backup_file> --db-only     # 仅恢复数据库
  python scripts/restore.py <backup_file> --config-only # 仅恢复配置
  python scripts/restore.py <backup_file> --dry-run     # 预览不执行
  python scripts/restore.py <backup_file> --force       # 跳过确认直接恢复
"""

import os
import sys
import json
import shutil
import tarfile
import sqlite3
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set


# ── Project root discovery ────────────────────────────────────────────────
def find_project_root() -> Path:
    anchor = Path(__file__).resolve().parent.parent
    if (anchor / "api" / "canvas_web.py").exists():
        return anchor
    return Path.cwd()


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
RESTORE_LOG = BACKUP_DIR / "restore.log"


def log_restore(message: str):
    """记录恢复日志"""
    RESTORE_LOG.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    with open(RESTORE_LOG, "a", encoding="utf-8") as f:
        f.write(line)
    print(f"  {message}")


def compute_checksum(filepath: Path, algorithm: str = "sha256") -> str:
    """计算文件校验和"""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_db_integrity(db_path: Path) -> Dict[str, Any]:
    """验证SQLite数据库完整性"""
    result = {"path": str(db_path), "ok": False, "tables": 0, "integrity": ""}
    try:
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        result["tables"] = len(tables)
        cursor = conn.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()
        result["ok"] = integrity[0] == "ok"
        result["integrity"] = integrity[0]
        conn.close()
    except Exception as e:
        result["integrity"] = str(e)
    return result


def inspect_backup(backup_path: Path) -> Dict[str, Any]:
    """检查备份文件内容"""
    info = {
        "backup_path": str(backup_path),
        "size_bytes": backup_path.stat().st_size,
        "size_mb": round(backup_path.stat().st_size / (1024 * 1024), 2),
        "files": [],
        "manifest": None,
        "db_files": [],
        "config_files": [],
        "upload_files": [],
        "other_files": [],
    }

    with tarfile.open(str(backup_path), "r:*") as tar:
        for member in tar.getmembers():
            if member.isfile():
                info["files"].append({
                    "name": member.name,
                    "size": member.size,
                })
                if member.name == "backup_manifest.json":
                    f = tar.extractfile(member)
                    if f:
                        info["manifest"] = json.loads(f.read().decode("utf-8"))
                elif member.name.endswith(".db"):
                    info["db_files"].append(member.name)
                elif member.name.startswith("config/") or member.name.startswith("deploy/") or member.name == ".env":
                    info["config_files"].append(member.name)
                elif member.name.startswith("data/uploads/") or member.name.startswith("data/audio/") or member.name.startswith("data/books/"):
                    info["upload_files"].append(member.name)
                else:
                    info["other_files"].append(member.name)

    info["total_files"] = len(info["files"])
    return info


def create_pre_restore_snapshot() -> Optional[Path]:
    """创建恢复前安全快照（备份当前状态）"""
    snapshot_name = f"pre_restore_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tar.gz"
    snapshot_path = BACKUP_DIR / snapshot_name
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    files_to_snapshot: List[Path] = []

    # 数据库文件
    for db in DATA_DIR.glob("*.db"):
        if db.is_file() and "backup" not in db.name.lower():
            files_to_snapshot.append(db)

    # 配置文件
    config_dir = PROJECT_ROOT / "config"
    if config_dir.exists():
        for f in config_dir.rglob("*.py"):
            files_to_snapshot.append(f)

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        files_to_snapshot.append(env_file)

    if not files_to_snapshot:
        return None

    with tarfile.open(str(snapshot_path), "w:gz") as tar:
        for fp in files_to_snapshot:
            if fp.exists():
                tar.add(str(fp), arcname=str(fp.relative_to(PROJECT_ROOT)))

    return snapshot_path


def restore_backup(
    backup_path: Path,
    db_only: bool = False,
    config_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """
    从备份恢复

    参数:
      backup_path: 备份文件路径
      db_only: 仅恢复数据库
      config_only: 仅恢复配置
      dry_run: 仅预览不执行
      force: 跳过确认

    返回: 恢复报告
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"备份文件不存在: {backup_path}")

    # ── 检查备份 ──────────────────────────────────────────────────────
    log_restore(f"检查备份文件: {backup_path.name}")
    info = inspect_backup(backup_path)

    report = {
        "restore_time": datetime.now().isoformat(),
        "backup_file": str(backup_path),
        "backup_info": info,
        "dry_run": dry_run,
        "db_only": db_only,
        "config_only": config_only,
        "pre_snapshot": None,
        "restored_files": [],
        "db_integrity_after": [],
        "success": False,
        "errors": [],
    }

    # ── 预览 ──────────────────────────────────────────────────────────
    print(f"\n  备份内容预览:")
    print(f"    备份大小: {info['size_mb']:.2f} MB")
    print(f"    总文件数: {info['total_files']}")
    print(f"    数据库:   {len(info['db_files'])} 个")
    print(f"    配置文件: {len(info['config_files'])} 个")
    print(f"    上传文件: {len(info['upload_files'])} 个")

    if info.get("manifest"):
        m = info["manifest"]
        print(f"    备份时间: {m.get('timestamp', 'unknown')}")
        db_integrity = m.get("db_integrity", [])
        for db in db_integrity:
            status = "OK" if db.get("ok") else "FAIL"
            print(f"    DB完整性: [{status}] {db.get('path', '?')}")

    if dry_run:
        print(f"\n  [预览模式] 不会执行实际恢复。")
        return report

    # ── 确认 ──────────────────────────────────────────────────────────
    if not force:
        print(f"\n  ⚠️  即将从备份恢复数据到: {PROJECT_ROOT}")
        if db_only:
            print(f"  恢复范围: 仅数据库文件 (data/*.db)")
        elif config_only:
            print(f"  恢复范围: 仅配置文件 (config/, .env, deploy/)")
        else:
            print(f"  恢复范围: 全量恢复")
        print(f"  警告: 现有文件将被覆盖！")
        try:
            response = input("\n  确认恢复? [y/N]: ").strip().lower()
        except EOFError:
            response = "n"
        if response != "y":
            print("  已取消恢复。")
            return report

    # ── 创建快照 ──────────────────────────────────────────────────────
    log_restore("创建恢复前安全快照...")
    try:
        snapshot = create_pre_restore_snapshot()
        if snapshot:
            report["pre_snapshot"] = str(snapshot)
            log_restore(f"安全快照已保存: {snapshot.name}")
        else:
            log_restore("无需创建快照(无可备份文件)")
    except Exception as e:
        log_restore(f"快照创建失败: {e} (继续恢复...)")

    # ── 执行恢复 ──────────────────────────────────────────────────────
    log_restore("开始恢复...")

    try:
        with tarfile.open(str(backup_path), "r:*") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                if member.name == "backup_manifest.json":
                    continue  # 跳过manifest

                # 过滤逻辑
                if db_only and not member.name.endswith(".db"):
                    continue
                if config_only and not (
                    member.name.startswith("config/")
                    or member.name.startswith("deploy/")
                    or member.name == ".env"
                ):
                    continue

                dest_path = PROJECT_ROOT / member.name
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                f = tar.extractfile(member)
                if f is None:
                    continue
                with open(dest_path, "wb") as dest:
                    shutil.copyfileobj(f, dest)

                report["restored_files"].append(member.name)
                log_restore(f"  恢复: {member.name}")

    except Exception as e:
        report["errors"].append(str(e))
        log_restore(f"恢复失败: {e}")
        return report

    # ── 验证恢复数据 ──────────────────────────────────────────────────
    log_restore("验证恢复数据完整性...")
    all_db_ok = True

    for member_name in info["db_files"]:
        db_path = PROJECT_ROOT / member_name
        if db_path.exists():
            integrity = verify_db_integrity(db_path)
            report["db_integrity_after"].append(integrity)
            status = "OK" if integrity["ok"] else f"FAIL: {integrity['integrity']}"
            if not integrity["ok"]:
                all_db_ok = False
            log_restore(f"  [{status}] {member_name} ({integrity['tables']} tables)")
        else:
            log_restore(f"  [MISSING] {member_name}")
            all_db_ok = False

    # 比较文件数量
    expected = len(info["db_files"]) if db_only else len(info["db_files"]) + len(info["config_files"]) if config_only else len([f for f in info["files"] if f["name"] != "backup_manifest.json"])
    restored_count = len(report["restored_files"])
    log_restore(f"恢复文件: {restored_count}/{expected}")

    report["success"] = all_db_ok and (restored_count >= expected if not db_only and not config_only else restored_count > 0)

    if report["success"]:
        log_restore("恢复完成 - 数据完整性验证通过 ✓")
    else:
        log_restore(f"恢复存在{'' if all_db_ok else '数据库'}问题 - 请检查")

    if report["pre_snapshot"]:
        log_restore(f"如需回滚，使用安全快照: {Path(report['pre_snapshot']).name}")

    return report


def print_report(report: Dict[str, Any]):
    """打印恢复报告"""
    print(f"\n{'='*60}")
    print(f"  IMDF 恢复报告")
    print(f"{'='*60}")
    print(f"  恢复时间:  {report['restore_time']}")
    print(f"  备份文件:  {Path(report['backup_file']).name}")
    print(f"  恢复文件数: {len(report['restored_files'])}")
    if report.get("pre_snapshot"):
        print(f"  安全快照:  {Path(report['pre_snapshot']).name}")

    if report["db_integrity_after"]:
        print(f"\n  恢复后数据库完整性:")
        for db in report["db_integrity_after"]:
            status = "OK" if db["ok"] else "FAIL"
            print(f"    [{status}] {db['path']}")

    if report["errors"]:
        print(f"\n  错误:")
        for err in report["errors"]:
            print(f"    - {err}")

    print(f"\n  结果: {'成功 ✓' if report['success'] else '失败 ✗'}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="IMDF 备份恢复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/restore.py data/backups/imdf_backup_20260615_120000.tar.gz
  python scripts/restore.py backup.tar.gz --db-only
  python scripts/restore.py backup.tar.gz --config-only
  python scripts/restore.py backup.tar.gz --dry-run
  python scripts/restore.py backup.tar.gz --force
        """,
    )
    parser.add_argument("backup_file", help="备份文件路径 (.tar.gz)")
    parser.add_argument("--db-only", action="store_true", help="仅恢复数据库")
    parser.add_argument("--config-only", action="store_true", help="仅恢复配置")
    parser.add_argument("--dry-run", action="store_true", help="预览不执行")
    parser.add_argument("--force", "-f", action="store_true", help="跳过确认直接恢复")

    args = parser.parse_args()

    if args.db_only and args.config_only:
        print("错误: --db-only 和 --config-only 不能同时使用", file=sys.stderr)
        sys.exit(1)

    os.chdir(PROJECT_ROOT)

    backup_path = Path(args.backup_file)
    if not backup_path.is_absolute():
        backup_path = PROJECT_ROOT / backup_path

    try:
        report = restore_backup(
            backup_path=backup_path,
            db_only=args.db_only,
            config_only=args.config_only,
            dry_run=args.dry_run,
            force=args.force,
        )
    except FileNotFoundError as e:
        print(f"\n错误: {e}", file=sys.stderr)
        print(f"\n可用的备份文件:")
        if BACKUP_DIR.exists():
            for b in sorted(BACKUP_DIR.glob("imdf_backup_*.tar*")):
                size_mb = b.stat().st_size / (1024*1024)
                print(f"  {b.name} ({size_mb:.1f} MB)")
        sys.exit(1)
    except Exception as e:
        print(f"\n恢复失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not args.dry_run:
        print_report(report)

    sys.exit(0 if report.get("success", False) or args.dry_run else 1)


if __name__ == "__main__":
    main()
