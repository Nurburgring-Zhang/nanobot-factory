#!/usr/bin/env python3
"""
种子数据脚本 - 为 nanobot-factory 生产数据库填充初始测试数据
目标数据库: backend/imdf/data/imdf.db
审计日志: backend/imdf/data/audit.db
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMDF_DB = os.path.join(BASE_DIR, "imdf", "data", "imdf.db")
AUDIT_DB = os.path.join(BASE_DIR, "imdf", "data", "audit.db")

def get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def clear_existing_data(conn):
    """清理现有种子数据（按依赖顺序）"""
    tables = [
        "eval_records", "deliveries", "stats_snapshots",
        "classification_rules", "taxonomy_nodes",
        "tasks", "datasets", "projects",
        "template_ratings", "template_market",
    ]
    for t in tables:
        try:
            conn.execute(f"DELETE FROM {t}")
        except:
            pass
    # 只删除众包worker，保留admin
    conn.execute("DELETE FROM users WHERE role = 'crowd_worker'")
    conn.commit()

def seed_projects(conn):
    """创建3个示例项目"""
    projects = [
        ("智能标注平台 v2.0", "tenant-001", 10000, "2026-05-01 09:00:00"),
        ("数据治理引擎", "tenant-001", 5000, "2026-05-15 14:30:00"),
        ("AI模型评估系统", "tenant-002", 8000, "2026-06-01 10:00:00"),
    ]
    conn.executemany(
        "INSERT INTO projects (name, tenant_id, quota, created_at) VALUES (?, ?, ?, ?)",
        projects
    )
    conn.commit()
    print(f"  ✓ 插入 3 个项目")

def seed_datasets(conn):
    """创建5个示例数据集"""
    datasets = [
        ("图像分类训练集", "v1.2.0", 15000, "active", "admin"),
        ("文本情感分析语料", "v3.0.1", 50000, "active", "admin"),
        ("语音识别测试集", "v1.0.0", 8000, "review", "zhang_san"),
        ("视频标注基准库", "v2.1.0", 3200, "active", "li_si"),
        ("3D点云分割数据", "v0.9.5-beta", 1200, "draft", "wang_wu"),
    ]
    conn.executemany(
        "INSERT INTO datasets (name, version, files_count, status, created_by) VALUES (?, ?, ?, ?, ?)",
        datasets
    )
    conn.commit()
    print(f"  ✓ 插入 5 个数据集")

def seed_tasks(conn):
    """创建10条标注任务"""
    base_date = datetime(2026, 6, 1)
    tasks = []
    for i in range(10):
        req_id = f"REQ-{2026000 + i}"
        assignee = ["zhang_san", "li_si", "wang_wu", "zhao_liu", "admin"][i % 5]
        status = ["completed", "in_progress", "pending", "completed", "review",
                  "in_progress", "pending", "completed", "in_progress", "pending"][i]
        deadline = base_date + timedelta(days=i * 3)
        tasks.append((req_id, assignee, status, deadline.strftime("%Y-%m-%d %H:%M:%S")))
    
    conn.executemany(
        "INSERT INTO tasks (requirement_id, assignee, status, deadline) VALUES (?, ?, ?, ?)",
        tasks
    )
    conn.commit()
    print(f"  ✓ 插入 10 条标注任务")

def seed_deliveries(conn):
    """创建3条交付记录"""
    deliveries = [
        ("图像分类数据集交付", "v1.2.0-final", "delivered", "reviewer_01", "质量达标，通过验收"),
        ("情感分析语料交付", "v3.0.1-release", "delivered", "reviewer_02", "标注一致性95.2%，批准发布"),
        ("语音识别数据包", "v1.0.0-rc1", "in_review", "reviewer_03", "部分样本需重新标注，待修正"),
    ]
    conn.executemany(
        "INSERT INTO deliveries (name, dataset_version, status, reviewer, comments) VALUES (?, ?, ?, ?, ?)",
        deliveries
    )
    conn.commit()
    print(f"  ✓ 插入 3 条交付记录")

def seed_stats_snapshots(conn):
    """创建7天统计快照"""
    base_date = datetime(2026, 6, 10)
    snapshots = []
    for i in range(7):
        ts = base_date + timedelta(days=i)
        metrics = {
            "total_tasks": 85 + i * 3,
            "completed_tasks": 60 + i * 2,
            "active_users": 12 + (i % 3),
            "datasets_processed": 23 + i,
            "accuracy_avg": round(0.938 + i * 0.005, 3),
            "throughput_per_hour": 156 + i * 8,
        }
        snapshots.append((ts.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(metrics)))
    
    conn.executemany(
        "INSERT INTO stats_snapshots (timestamp, metrics_json) VALUES (?, ?)",
        snapshots
    )
    conn.commit()
    print(f"  ✓ 插入 7 天统计快照")

def seed_classification_rules(conn):
    """创建2条分类规则"""
    rules = [
        ("rule-001", "敏感数据检测", "security", 
         "自动检测并标记包含PII的数据字段",
         10, 1, "content", "contains", "身份证|手机号|银行卡",
         1, "请识别文本中的个人身份信息：姓名、身份证号、电话号码、银行卡号、地址。如发现则标记为敏感。"),
        ("rule-002", "低质量数据过滤", "quality",
         "过滤标注置信度低于阈值的数据",
         5, 1, "confidence", "lt", "0.6",
         0, None),
    ]
    conn.executemany(
        """INSERT INTO classification_rules 
           (id, name, category, description, priority, enabled, field, operator, value, use_ai, ai_prompt) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rules
    )
    conn.commit()
    print(f"  ✓ 插入 2 条分类规则")

def seed_crowd_workers(conn):
    """创建3个众包workers（users表）"""
    import hashlib
    workers = [
        ("crowd_worker_01", hashlib.sha256("worker01!Pass".encode()).hexdigest(), 
         "crowd_worker", 1, 100, 500, 1000, "2026-05-01 08:00:00"),
        ("crowd_worker_02", hashlib.sha256("worker02!Pass".encode()).hexdigest(),
         "crowd_worker", 1, 100, 500, 1000, "2026-05-10 09:30:00"),
        ("crowd_worker_03", hashlib.sha256("worker03!Pass".encode()).hexdigest(),
         "crowd_worker", 1, 100, 500, 1000, "2026-06-01 10:00:00"),
    ]
    conn.executemany(
        """INSERT INTO users 
           (username, password_hash, role, enabled, max_datasets, max_storage_mb, max_api_calls_per_day, created_at) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        workers
    )
    conn.commit()
    print(f"  ✓ 插入 3 个众包workers")

def seed_audit_logs():
    """创建10条审计日志（写入audit.db）"""
    conn = get_conn(AUDIT_DB)
    
    # 确保audit_logs表存在
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            ip_address TEXT,
            result TEXT DEFAULT 'success'
        )
    """)
    conn.commit()
    
    base_date = datetime(2026, 6, 10, 8, 0, 0)
    audit_entries = [
        ("admin", "login", "session", None, "管理员登录系统", "192.168.1.100", "success"),
        ("admin", "create_project", "project", "1", "创建项目: 智能标注平台 v2.0", "192.168.1.100", "success"),
        ("zhang_san", "upload_dataset", "dataset", "2", "上传数据集: 文本情感分析语料", "10.0.0.55", "success"),
        ("admin", "assign_task", "task", "REQ-2026001", "分配标注任务给 li_si", "192.168.1.100", "success"),
        ("li_si", "complete_task", "task", "REQ-2026001", "完成标注任务", "10.0.0.66", "success"),
        ("admin", "review_delivery", "delivery", "1", "审核通过图像分类数据集交付", "192.168.1.100", "success"),
        ("crowd_worker_01", "claim_task", "task", "REQ-2026003", "领取众包标注任务", "172.16.0.10", "success"),
        ("wang_wu", "export_data", "dataset", "1", "导出图像分类训练集", "10.0.0.77", "success"),
        ("admin", "update_rule", "classification_rule", "rule-001", "更新敏感数据检测规则", "192.168.1.100", "success"),
        ("zhao_liu", "login_failed", "session", None, "密码错误登录失败(第3次)", "10.0.0.88", "failure"),
    ]
    
    for i, (user, action, res_type, res_id, details, ip, result) in enumerate(audit_entries):
        ts = base_date + timedelta(hours=i * 2, minutes=i * 15)
        conn.execute(
            """INSERT INTO audit_logs 
               (timestamp, user_id, action, resource_type, resource_id, details, ip_address, result) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts.strftime("%Y-%m-%d %H:%M:%S"), user, action, res_type, res_id, details, ip, result)
        )
    
    conn.commit()
    conn.close()
    print(f"  ✓ 插入 10 条审计日志 (audit.db)")

def verify_data(conn):
    """验证数据已写入"""
    print("\n=== 数据验证 ===")
    tables = [
        "projects", "datasets", "tasks", "deliveries",
        "stats_snapshots", "classification_rules", "users"
    ]
    for t in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {count} rows")
    
    # 验证审计日志
    audit_conn = get_conn(AUDIT_DB)
    audit_count = audit_conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    print(f"  audit_logs (audit.db): {audit_count} rows")
    audit_conn.close()

def main():
    print("=" * 60)
    print("  Nanobot Factory - 种子数据脚本")
    print("=" * 60)
    print(f"\n  目标数据库: {IMDF_DB}")
    print(f"  审计数据库: {AUDIT_DB}\n")
    
    if not os.path.exists(IMDF_DB):
        print(f"❌ 错误: 找不到数据库文件 {IMDF_DB}")
        return 1
    
    conn = get_conn(IMDF_DB)
    
    try:
        print("→ 清理现有种子数据...")
        clear_existing_data(conn)
        
        print("\n→ 插入种子数据...")
        seed_projects(conn)
        seed_datasets(conn)
        seed_tasks(conn)
        seed_deliveries(conn)
        seed_stats_snapshots(conn)
        seed_classification_rules(conn)
        seed_crowd_workers(conn)
        seed_audit_logs()
        
        conn.commit()
        verify_data(conn)
        
        print("\n✅ 种子数据插入完成！")
        return 0
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        conn.rollback()
        return 1
    finally:
        conn.close()

if __name__ == "__main__":
    exit(main())
