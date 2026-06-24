#!/usr/bin/env python3
"""
IMDF Backup Script — 全量备份工具
==================================
备份范围:
  - SQLite数据库 (*.db in data/)
  - 配置文件 (config/, .env)
  - 用户上传文件 (data/uploads/, data/audio/, data/books/)
  - 调度器状态 (data/scheduler*.json)

输出: data/backups/imdf_backup_YYYYMMDD_HHMMSS.tar.gz

用法:
  python scripts/backup.py                        # 全量备份
  python scripts/backup.py --no-compress           # 仅打包不压缩
  python scripts/backup.py --output /path/to/dir   # 指定输出目录
  python scripts/backup.py --db-only               # 仅备份数据库
  python scripts/backup.py --list                  # 列出已有备份
"""

import os
import sys
import shutil
import tarfile
import argparse
import sqlite3
import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any


# ── Project root discovery ────────────────────────────────────────────────
def find_project_root() -> Path:
    """Walk upward from this script to find project root."""
    anchor = Path(__file__).resolve().parent.parent
    if (anchor / "api" / "canvas_web.py").exists():
        return anchor
    return Path.cwd()


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
CONFIG_DIR = PROJECT_ROOT / "config"


def ensure_backup_dir() -> Path:
    """确保备份目录存在"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def get_db_files() -> List[Path]:
    """获取所有SQLite数据库文件"""
    if not DATA_DIR.exists():
        return []
    db_files = sorted(DATA_DIR.glob("*.db"))
    return [f for f in db_files if f.is_file()]


def get_config_files() -> List[Path]:
    """获取配置文件"""
    configs = []
    # .env
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        configs.append(env_file)
    # config/ directory
    if CONFIG_DIR.exists():
        for f in CONFIG_DIR.rglob("*.py"):
            configs.append(f)
        for f in CONFIG_DIR.rglob("*.yaml"):
            configs.append(f)
        for f in CONFIG_DIR.rglob("*.yml"):
            configs.append(f)
        for f in CONFIG_DIR.rglob("*.json"):
            configs.append(f)
    # deploy/
    deploy_dir = PROJECT_ROOT / "deploy"
    if deploy_dir.exists():
        for f in deploy_dir.rglob("*"):
            if f.is_file():
                configs.append(f)
    return configs


def get_user_upload_dirs() -> List[Path]:
    """获取用户上传文件目录"""
    upload_dirs = []
    candidates = [
        DATA_DIR / "uploads",
        DATA_DIR / "audio",
        DATA_DIR / "books",
        DATA_DIR / "images",
    ]
    for d in candidates:
        if d.exists() and d.is_dir():
            upload_dirs.append(d)
    return upload_dirs


def verify_db_integrity(db_path: Path) -> Dict[str, Any]:
    """验证SQLite数据库完整性"""
    result = {"path": str(db_path.relative_to(PROJECT_ROOT)), "size_bytes": 0, "tables": [], "ok": False}
    try:
        result["size_bytes"] = db_path.stat().st_size
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        result["tables"] = tables
        cursor = conn.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()
        result["ok"] = integrity[0] == "ok"
        result["integrity"] = integrity[0]
        conn.close()
    except Exception as e:
        result["ok"] = False
        result["integrity"] = str(e)
    return result


def compute_checksum(filepath: Path, algorithm: str = "sha256") -> str:
    """计算文件校验和"""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_backup(
    compress: bool = True,
    output_dir: Optional[Path] = None,
    db_only: bool = False,
) -> Dict[str, Any]:
    """
    创建备份包

    返回: 备份报告 dict
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"imdf_backup_{timestamp}"
    backup_dir = ensure_backup_dir() if output_dir is None else Path(output_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "backup_name": backup_name,
        "timestamp": datetime.now().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "components": {},
        "db_integrity": [],
        "checksums": {},
    }

    # ── 收集待备份文件 ──────────────────────────────────────────────────
    files_to_backup: List[Path] = []
    db_files = get_db_files()
    files_to_backup.extend(db_files)

    # 数据库完整性校验
    for db in db_files:
        integrity = verify_db_integrity(db)
        manifest["db_integrity"].append(integrity)

    if not db_only:
        config_files = get_config_files()
        files_to_backup.extend(config_files)
        manifest["components"]["config_files"] = [str(f.relative_to(PROJECT_ROOT)) for f in config_files]

        # 用户上传文件
        upload_dirs = get_user_upload_dirs()
        for ud in upload_dirs:
            for f in ud.rglob("*"):
                if f.is_file():
                    files_to_backup.append(f)
            manifest["components"][ud.name] = f"{ud.name}/ (包含文件)"

        # 调度器状态JSON
        for jf in DATA_DIR.glob("*.json"):
            if jf.is_file():
                files_to_backup.append(jf)

    manifest["components"]["database_files"] = [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "md5": compute_checksum(f, "md5")[:16] + "...",
        }
        for f in db_files
    ]
    manifest["total_files"] = len(files_to_backup)
    manifest["total_size_bytes"] = sum(f.stat().st_size for f in files_to_backup if f.exists())

    # ── 创建tar.gz ──────────────────────────────────────────────────────
    ext = ".tar.gz" if compress else ".tar"
    backup_path = backup_dir / f"{backup_name}{ext}"

    mode = "w:gz" if compress else "w"
    with tarfile.open(str(backup_path), mode) as tar:
        for filepath in files_to_backup:
            if not filepath.exists():
                continue
            arcname = str(filepath.relative_to(PROJECT_ROOT))
            tar.add(str(filepath), arcname=arcname)

        # 写入manifest
        manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
        import io
        manifest_tarinfo = tarfile.TarInfo(name="backup_manifest.json")
        manifest_tarinfo.size = len(manifest_bytes)
        manifest_tarinfo.mtime = int(datetime.now().timestamp())
        tar.addfile(manifest_tarinfo, io.BytesIO(manifest_bytes))

    backup_size = backup_path.stat().st_size
    manifest["backup_path"] = str(backup_path)
    manifest["backup_size_bytes"] = backup_size
    manifest["compression"] = "gzip" if compress else "none"

    # ── 清理旧备份（保留最近10个）──────────────────────────────────────
    cleanup_old_backups(backup_dir, keep=10)

    return manifest


def cleanup_old_backups(backup_dir: Path, keep: int = 10):
    """保留最近N个备份，删除更旧的"""
    backups = sorted(backup_dir.glob("imdf_backup_*.tar*"), key=os.path.getmtime, reverse=True)
    for old in backups[keep:]:
        try:
            old.unlink()
            print(f"  清理旧备份: {old.name}")
        except OSError:
            pass


def list_backups(backup_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """列出所有备份"""
    bd = backup_dir or BACKUP_DIR
    if not bd.exists():
        return []
    backups = []
    for f in sorted(bd.glob("imdf_backup_*.tar*"), key=os.path.getmtime, reverse=True):
        backups.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": f.stat().st_size,
            "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return backups


def print_report(manifest: Dict[str, Any]):
    """打印备份报告"""
    print(f"\n{'='*60}")
    print(f"  IMDF 备份报告")
    print(f"{'='*60}")
    print(f"  备份名称:  {manifest['backup_name']}")
    print(f"  创建时间:  {manifest['timestamp']}")
    print(f"  总文件数:  {manifest['total_files']}")
    print(f"  总大小:    {manifest['total_size_bytes'] / (1024*1024):.2f} MB")
    print(f"  备份大小:  {manifest['backup_size_bytes'] / (1024*1024):.2f} MB")
    print(f"  压缩方式:  {manifest['compression']}")
    print(f"  备份路径:  {manifest['backup_path']}")
    print(f"\n  数据库完整性:")
    all_db_ok = True
    for db in manifest.get("db_integrity", []):
        status = "OK" if db["ok"] else "FAIL"
        if not db["ok"]:
            all_db_ok = False
        print(f"    [{status}] {db['path']} ({db['size_bytes']} bytes, {len(db['tables'])} tables)")
    print(f"{'='*60}")
    if not all_db_ok:
        print("  警告: 部分数据库完整性校验失败！")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="IMDF 备份工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/backup.py                     # 全量备份
  python scripts/backup.py --no-compress        # 仅打包不压缩
  python scripts/backup.py --output /mnt/backups # 指定输出目录
  python scripts/backup.py --db-only            # 仅备份数据库
  python scripts/backup.py --list               # 列出已有备份
        """,
    )
    parser.add_argument("--no-compress", action="store_true", help="不压缩(仅tar)")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--db-only", action="store_true", help="仅备份数据库")
    parser.add_argument("--list", action="store_true", help="列出已有备份")
    parser.add_argument("--keep", type=int, default=10, help="保留最近N个备份 (默认: 10)")

    args = parser.parse_args()

    # Ensure we run from project root
    os.chdir(PROJECT_ROOT)

    if args.list:
        backups = list_backups()
        if not backups:
            print("暂无备份文件")
        else:
            print(f"\n已有备份 ({len(backups)} 个):")
            print(f"{'─'*60}")
            for b in backups:
                print(f"  {b['name']:<50s} {b['size_mb']:>7.2f} MB  {b['created']}")
            print(f"{'─'*60}\n")
        return

    print(f"\n开始备份 IMDF 项目...")
    print(f"  项目根目录: {PROJECT_ROOT}")

    output_dir = Path(args.output) if args.output else None
    try:
        manifest = create_backup(
            compress=not args.no_compress,
            output_dir=output_dir,
            db_only=args.db_only,
        )
    except Exception as e:
        print(f"\n备份失败: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print_report(manifest)
    print(f"备份完成! 文件: {manifest['backup_path']}")


if __name__ == "__main__":
    main()
