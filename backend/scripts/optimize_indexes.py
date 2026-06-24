#!/usr/bin/env python3
"""
Nanobot Factory - Database Index Optimization Script

分析当前数据库索引状况并添加缺失的索引以优化查询性能。

Usage:
    python scripts/optimize_indexes.py                     # SQLite (default: data/nanobot.db)
    python scripts/optimize_indexes.py --db path/to/db.db  # 指定数据库路径
    python scripts/optimize_indexes.py --analyze           # 仅分析，不创建索引
    python scripts/optimize_indexes.py --postgres          # PostgreSQL模式

@author MiniMax Agent
@date 2026-06-15
"""

import os
import sys
import json
import sqlite3
import logging
import argparse
from datetime import datetime
from typing import List, Tuple, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# 索引定义
# =============================================================================

# 缺失的关键索引（当前数据库中存在的索引见下面 analysis 输出）
MISSING_INDEXES = [
    # asset_tags 关联查询（搜索资产时需JOIN asset_tags）
    "CREATE INDEX IF NOT EXISTS idx_asset_tags_asset ON asset_tags(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_asset_tags_tag ON asset_tags(tag_id)",

    # dataset_assets 关联查询（获取数据集中的资产）
    "CREATE INDEX IF NOT EXISTS idx_dataset_assets_dataset ON dataset_assets(dataset_id)",
    "CREATE INDEX IF NOT EXISTS idx_dataset_assets_asset ON dataset_assets(asset_id)",

    # metadata 关联查询（获取资产元数据）
    "CREATE INDEX IF NOT EXISTS idx_metadata_asset ON metadata(asset_id)",

    # asset_folders 关联查询（获取文件夹中的资产）
    "CREATE INDEX IF NOT EXISTS idx_asset_folders_asset ON asset_folders(asset_id)",
    "CREATE INDEX IF NOT EXISTS idx_asset_folders_folder ON asset_folders(folder_id)",

    # assets 常用过滤字段（高级搜索优化）
    "CREATE INDEX IF NOT EXISTS idx_assets_quality ON assets(quality_score)",
    "CREATE INDEX IF NOT EXISTS idx_assets_aesthetic ON assets(aesthetic_score)",
    "CREATE INDEX IF NOT EXISTS idx_assets_format ON assets(format)",
    "CREATE INDEX IF NOT EXISTS idx_assets_updated ON assets(updated_at)",
]

# =============================================================================
# 复合索引（覆盖常见查询组合）
# =============================================================================
COMPOSITE_INDEXES = [
    # 类型+名称搜索（按类型过滤后按名称排序）
    "CREATE INDEX IF NOT EXISTS idx_assets_type_name ON assets(type, name)",

    # 评分+创建时间（按评分筛选后按时间排序）
    "CREATE INDEX IF NOT EXISTS idx_assets_rating_created ON assets(rating, created_at)",

    # 收藏+更新时间（收藏列表按时间排序）
    "CREATE INDEX IF NOT EXISTS idx_assets_favorite_updated ON assets(favorite, updated_at)",
]


def get_current_indexes(cursor) -> List[str]:
    """获取数据库中当前索引列表"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_auto%' ORDER BY name"
    )
    return [r[0] for r in cursor.fetchall()]


def get_table_stats(cursor) -> Dict[str, int]:
    """获取各表行数统计"""
    tables = [
        'assets', 'asset_tags', 'asset_folders', 'dataset_assets',
        'metadata', 'datasets', 'folders', 'tags', 'tag_groups', 'smart_folders'
    ]
    stats = {}
    for t in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {t}")
            stats[t] = cursor.fetchone()[0]
        except Exception as e:
            stats[t] = f"ERROR: {e}"
    return stats


def get_schema_info(cursor) -> List[Dict]:
    """获取所有表的schema信息"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_auto%' AND name NOT LIKE '%_fts%' "
        "ORDER BY name"
    )
    schemas = []
    for (tname,) in cursor.fetchall():
        cursor.execute(f"PRAGMA table_info({tname})")
        cols = cursor.fetchall()
        schemas.append({
            'table': tname,
            'columns': [
                {'name': c[1], 'type': c[2], 'notnull': c[3], 'pk': c[5]}
                for c in cols
            ]
        })
    return schemas


def get_tables_without_rowid() -> List[str]:
    """检测没有 rowid 隐式索引的表（复合主键表可能缺少外键索引）"""
    # asset_tags, dataset_assets, asset_folders, metadata 都是复合主键，
    # SQLite 自动创建主键索引，但主键的第一列以外列都没有单独索引。
    return [
        'asset_tags(asset_id, tag_id)',   # 主键是(asset_id, tag_id) → 自动索引asset_id
        'dataset_assets(dataset_id, asset_id)',  # 主键是(dataset_id, asset_id) → 自动索引dataset_id
        'asset_folders(asset_id, folder_id)',    # 主键是(asset_id, folder_id) → 自动索引asset_id
        'metadata(asset_id, key)',        # 主键是(asset_id, key) → 自动索引asset_id
    ]


def analyze_query_patterns() -> List[Tuple[str, str, str]]:
    """
    分析 server.py 和 database.py 中的查询模式，返回
    (表名, 列名, 查询示例) 列表
    """
    patterns = [
        # assets 表的查询模式
        ('assets', 'type', "WHERE type = ?"),
        ('assets', 'name', "WHERE name LIKE ?"),
        ('assets', 'folder_id', "WHERE folder_id = ?"),
        ('assets', 'quality_score', "WHERE quality_score >= ?"),
        ('assets', 'aesthetic_score', "WHERE aesthetic_score >= ?"),
        ('assets', 'rating', "WHERE rating = ?"),
        ('assets', 'color', "WHERE color = ?"),
        ('assets', 'favorite', "WHERE favorite = 1"),
        ('assets', 'hash', "WHERE hash = ?"),
        ('assets', 'created_at', "ORDER BY created_at DESC"),
        ('assets', 'updated_at', "ORDER BY updated_at DESC"),
        # 关联查询
        ('asset_tags', 'asset_id', "JOIN asset_tags ON asset_id"),
        ('asset_tags', 'tag_id', "JOIN asset_tags ON tag_id"),
        ('dataset_assets', 'dataset_id', "JOIN dataset_assets ON dataset_id"),
        ('dataset_assets', 'asset_id', "JOIN dataset_assets ON asset_id"),
        ('metadata', 'asset_id', "JOIN metadata ON asset_id"),
        ('asset_folders', 'asset_id', "JOIN asset_folders ON asset_id"),
        ('asset_folders', 'folder_id', "JOIN asset_folders ON folder_id"),
        # 聚合查询
        ('tags', 'group_id', "WHERE group_id = ?"),
        ('folders', 'parent_id', "WHERE parent_id = ?"),
    ]
    return patterns


def collect_database_stats(cursor) -> Dict[str, Any]:
    """收集数据库性能统计数据"""
    stats = {}

    # 数据库文件大小
    try:
        cursor.execute("PRAGMA page_count")
        pages = cursor.fetchone()[0]
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        stats['db_size_bytes'] = pages * page_size
        stats['db_size_mb'] = round(pages * page_size / 1024 / 1024, 2)
        stats['page_count'] = pages
        stats['page_size'] = page_size
    except:
        pass

    # 缓存/性能设置
    try:
        cursor.execute("PRAGMA cache_size")
        stats['cache_size'] = cursor.fetchone()[0]
        cursor.execute("PRAGMA journal_mode")
        stats['journal_mode'] = cursor.fetchone()[0]
        cursor.execute("PRAGMA synchronous")
        stats['synchronous'] = cursor.fetchone()[0]
    except:
        pass

    return stats


def analyze_index_usage(cursor, current_indexes: List[str]) -> List[Dict]:
    """分析索引覆盖情况，找出缺失的索引"""
    results = []
    existing_set = set(current_indexes)

    # 检查单列索引
    for idx_sql in MISSING_INDEXES:
        name = idx_sql.split()[5]
        if name not in existing_set:
            results.append({
                'name': name,
                'sql': idx_sql,
                'type': 'missing-single-column',
                'exists': False
            })
        else:
            results.append({
                'name': name,
                'sql': idx_sql,
                'type': 'existing-single-column',
                'exists': True
            })

    # 检查复合索引
    for idx_sql in COMPOSITE_INDEXES:
        name = idx_sql.split()[5]
        if name not in existing_set:
            results.append({
                'name': name,
                'sql': idx_sql,
                'type': 'missing-composite',
                'exists': False
            })
        else:
            results.append({
                'name': name,
                'sql': idx_sql,
                'type': 'existing-composite',
                'exists': True
            })

    return results


def create_indexes(cursor, index_results: List[Dict]) -> Tuple[int, int]:
    """创建缺失的索引，返回 (创建数, 失败数)"""
    created = 0
    failed = 0

    for idx in index_results:
        if not idx['exists']:
            try:
                cursor.execute(idx['sql'])
                logger.info(f"  ✓ Created index: {idx['name']}")
                created += 1
            except Exception as e:
                logger.error(f"  ✗ Failed to create {idx['name']}: {e}")
                failed += 1

    return created, failed


def run_vacuum_and_analyze(cursor):
    """运行VACUUM和ANALYZE以优化数据库"""
    logger.info("Running ANALYZE to update query planner statistics...")
    try:
        cursor.execute("ANALYZE")
        logger.info("  ✓ ANALYZE completed")
    except Exception as e:
        logger.warning(f"  ✗ ANALYZE failed: {e}")

    logger.info("Running VACUUM to reclaim space...")
    try:
        cursor.execute("VACUUM")
        logger.info("  ✓ VACUUM completed")
    except Exception as e:
        logger.warning(f"  ✗ VACUUM failed: {e}")


def print_report(stats, current_indexes, index_results, table_stats, patterns):
    """打印完整的优化报告"""
    print("\n")
    print("=" * 70)
    print("  Nanobot Factory - 数据库索引优化报告")
    print("=" * 70)
    print(f"\n  报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 数据库基本信息
    print(f"\n  ┌─ 数据库信息")
    print(f"  │   大小: {stats.get('db_size_mb', 'N/A')} MB ({stats.get('page_count', 'N/A')} 页 × {stats.get('page_size', 'N/A')} 字节)")
    print(f"  │   缓存: {stats.get('cache_size', 'N/A')} 页")
    print(f"  │   日志模式: {stats.get('journal_mode', 'N/A')}")
    print(f"  │   同步模式: {stats.get('synchronous', 'N/A')}")
    print(f"  └─")

    # 表行数
    print(f"\n  ┌─ 数据量统计")
    for t, cnt in table_stats.items():
        print(f"  │   {t + ':':20s} {cnt}")
    print(f"  └─")

    # 当前索引
    print(f"\n  ┌─ 当前索引 ({len(current_indexes)} 个)")
    for name in current_indexes:
        print(f"  │   ✓ {name}")
    print(f"  └─")

    # 缺失索引
    missing = [r for r in index_results if not r['exists']]
    single_missing = [r for r in missing if r['type'] == 'missing-single-column']
    comp_missing = [r for r in missing if r['type'] == 'missing-composite']
    existing = [r for r in index_results if r['exists']]

    if single_missing or comp_missing:
        print(f"\n  ┌─ 缺失的索引 ({len(missing)} 个)")
        if single_missing:
            print(f"  │   [单列索引]")
            for r in single_missing:
                print(f"  │   ✗ {r['name']}")
                print(f"  │     {r['sql']}")
        if comp_missing:
            print(f"  │   [复合索引]")
            for r in comp_missing:
                print(f"  │   ✗ {r['name']}")
                print(f"  │     {r['sql']}")
            print(f"  │")
            print(f"  │   💡 复合索引说明:")
            print(f"  │      idx_assets_type_name: WHERE type=? + ORDER BY name 查询")
            print(f"  │      idx_assets_rating_created: WHERE rating=? + ORDER BY created_at 查询")
            print(f"  │      idx_assets_favorite_updated: WHERE favorite=1 + ORDER BY updated_at 查询")
        print(f"  └─")

    # 已存在的索引
    if existing:
        print(f"\n  ┌─ 已存在的索引 ({len(existing)} 个)")
        for r in existing:
            print(f"  │   ✓ {r['name']}")
        print(f"  └─")

    # 查询模式分析
    print(f"\n  ┌─ 检测到的查询模式 ({len(patterns)})")
    for table, column, example in patterns:
        idx_needed = f"idx_{table}_{column}"
        has_idx = any(idx_needed == name for name in current_indexes)
        status = "✓" if has_idx else "✗"
        print(f"  │   {status} {table}.{column:20s} → {example}")
    print(f"  └─")

    print("\n" + "=" * 70)
    if missing:
        print(f"  建议: 缺少 {len(missing)} 个索引，请运行 optimize_indexes.py 创建")
    else:
        print("  所有推荐索引已就绪 ✓")
    print("=" * 70)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Nanobot Factory - 数据库索引优化工具'
    )
    parser.add_argument(
        '--db',
        default=os.environ.get('DATABASE_PATH', 'data/nanobot.db'),
        help='SQLite数据库路径 (默认: data/nanobot.db, 或 DATABASE_PATH 环境变量)'
    )
    parser.add_argument(
        '--analyze',
        action='store_true',
        help='仅分析，不创建索引'
    )
    parser.add_argument(
        '--vacuum',
        action='store_true',
        help='创建索引后运行 VACUUM 和 ANALYZE'
    )
    parser.add_argument(
        '--no-composite',
        action='store_true',
        help='不创建复合索引（仅创建单列缺失索引）'
    )
    parser.add_argument(
        '--postgres',
        action='store_true',
        help='PostgreSQL模式（生成SQL脚本而非直接执行）'
    )
    args = parser.parse_args()

    # 解析数据库路径
    db_path = args.db
    if not os.path.isabs(db_path):
        # 相对路径相对于脚本所在目录的父目录（backend/）
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(script_dir, db_path)
        logger.info(f"Resolved database path: {db_path}")

    if not os.path.exists(db_path) and not args.postgres:
        logger.error(f"数据库不存在: {db_path}")
        sys.exit(1)

    # ────────────────────────────────────────────
    # PostgreSQL 模式：生成 SQL 脚本
    # ────────────────────────────────────────────
    if args.postgres:
        output_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'create_indexes_postgres.sql'
        )
        logger.info(f"PostgreSQL模式: 生成SQL到 {output_path}")

        sql_statements = []
        for idx_sql in MISSING_INDEXES:
            # 转换为PostgreSQL语法 (去除 IF NOT EXISTS)
            pg_sql = idx_sql.replace("IF NOT EXISTS ", "")
            # SQLite "IF NOT EXISTS" in CREATE INDEX is standard SQL, keep it
            sql_statements.append(pg_sql + ";")

        if not args.no_composite:
            for idx_sql in COMPOSITE_INDEXES:
                pg_sql = idx_sql.replace("IF NOT EXISTS ", "")
                sql_statements.append(pg_sql + ";")

        with open(output_path, 'w') as f:
            f.write("-- Nanobot Factory - PostgreSQL Indexes\n")
            f.write(f"-- Generated: {datetime.now().isoformat()}\n")
            f.write("-- Run: psql -d yourdb -f scripts/create_indexes_postgres.sql\n\n")
            f.write("BEGIN;\n\n")
            for stmt in sql_statements:
                f.write(stmt + "\n")
            f.write("\nCOMMIT;\n")

        logger.info(f"SQL脚本已生成: {output_path}")
        print(f"\n生成的SQL脚本 ({len(sql_statements)} 条):")
        for stmt in sql_statements:
            print(f"  {stmt}")
        return

    # ────────────────────────────────────────────
    # SQLite 模式
    # ────────────────────────────────────────────
    logger.info(f"连接数据库: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 收集统计数据
        stats = collect_database_stats(cursor)
        table_stats = get_table_stats(cursor)
        current_indexes = get_current_indexes(cursor)
        index_results = analyze_index_usage(cursor, current_indexes)
        patterns = analyze_query_patterns()

        # 打印报告
        print_report(stats, current_indexes, index_results, table_stats, patterns)

        # 如果需要，创建缺失的索引
        if not args.analyze:
            missing = [r for r in index_results if not r['exists']]
            if args.no_composite:
                missing = [r for r in missing if r['type'] != 'missing-composite']

            if missing:
                logger.info(f"开始创建 {len(missing)} 个缺失索引...")
                created, failed = create_indexes(cursor, missing)
                conn.commit()

                if failed > 0:
                    logger.warning(f"创建完成: {created} 成功, {failed} 失败")
                else:
                    logger.info(f"创建完成: {created} 个索引已创建")

                # 验证
                new_indexes = get_current_indexes(cursor)
                logger.info(f"数据库现在共有 {len(new_indexes)} 个索引")

                if args.vacuum:
                    run_vacuum_and_analyze(cursor)
            else:
                logger.info("所有索引已存在，无需创建")
        else:
            logger.info("仅分析模式，未创建任何索引")

    except Exception as e:
        logger.error(f"执行过程中出错: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    main()
