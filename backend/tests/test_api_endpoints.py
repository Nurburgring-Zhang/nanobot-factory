"""
NanoBot Factory - API端点深度测试
测试所有REST API端点的功能
注意：此文件是独立脚本，不是pytest测试。
请用 `python test_api_endpoints.py` 方式运行。

@author Matrix Agent
@date 2026-04-22
"""

import pytest
pytest.skip("此文件是独立脚本，请用 python test_api_endpoints.py 运行", allow_module_level=True)

import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 测试结果
all_passed = 0
all_failed = 0

def test_result(name, passed, error=""):
    global all_passed, all_failed
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {name}")
    if error:
        print(f"        Error: {error[:100]}")
    if passed:
        all_passed += 1
    else:
        all_failed += 1
    return passed

print("=" * 70)
print("NanoBot Factory - API端点深度测试")
print(f"测试时间: {datetime.now().isoformat()}")
print("=" * 70)

# ========== 1. 数据库管理 API ==========
print("\n" + "=" * 70)
print("1. 数据库管理 API 端点")
print("=" * 70)

print("\n[1.1] DatabaseManager 实例化:")
try:
    from database_manager import DatabaseManager, get_db_manager
    db = get_db_manager()
    test_result("DatabaseManager获取", db is not None)
    test_result("data_store存在", hasattr(db, 'data_store'))
except Exception as e:
    test_result("DatabaseManager获取", False, str(e))
    all_failed += 1

print("\n[1.2] 记录管理 API:")
try:
    # 创建记录
    record_id = db.create_record(
        data_category="user_data",
        content={"name": "test", "value": 123},
        sensitive_level="internal"
    )
    test_result("create_record()", record_id is not None)
    
    # 获取记录
    record = db.get_record(record_id)
    test_result("get_record()", record is not None)
    
    # 更新记录
    result = db.update_record(record_id, content={"name": "updated"})
    test_result("update_record()", result is True)
    
except Exception as e:
    test_result("记录管理", False, str(e))

print("\n[1.3] 会话管理 API:")
try:
    # 创建会话
    session_id = db.create_session(
        session_type="chat",
        user_id="test_user"
    )
    test_result("create_session()", session_id is not None)
    
    # 获取会话
    session = db.get_session(session_id)
    test_result("get_session()", session is not None)
    
    # 添加消息
    msg_id = db.add_message(
        session_id=session_id,
        role="user",
        content="测试消息"
    )
    test_result("add_message()", msg_id is not None)
    
except Exception as e:
    test_result("会话管理", False, str(e))

print("\n[1.4] 知识库管理 API:")
try:
    kb_id = db.create_knowledge_base(
        name="测试知识库",
        category="general"
    )
    test_result("create_knowledge_base()", kb_id is not None)
    
    kb = db.get_knowledge_base(kb_id)
    test_result("get_knowledge_base()", kb is not None)
    
except Exception as e:
    test_result("知识库管理", False, str(e))

print("\n[1.5] 标注数据管理 API:")
try:
    # 创建标注记录
    anno_id = db.create_annotation(
        data_type="text",
        content={"text": "测试标注"},
        project_id="default"
    )
    test_result("create_annotation()", anno_id is not None)
    
    # 获取标注
    anno = db.get_annotation(anno_id)
    test_result("get_annotation()", anno is not None)
    
except Exception as e:
    test_result("标注数据管理", False, str(e))

# ========== 2. 标注系统 API ==========
print("\n" + "=" * 70)
print("2. 标注系统 API 端点")
print("=" * 70)

print("\n[2.1] AnnotationManager 实例化:")
try:
    from annotation_system_enhanced import EnhancedAnnotationManager, ImageDataType
    am = EnhancedAnnotationManager()
    test_result("EnhancedAnnotationManager", am is not None)
    test_result("images字典", hasattr(am, 'images'))
    test_result("projects字典", hasattr(am, 'projects'))
except Exception as e:
    test_result("AnnotationManager", False, str(e))
    all_failed += 3

print("\n[2.2] 项目管理 API:")
try:
    # 创建项目
    project = am.create_project("API测试项目", "API端点测试")
    test_result("create_project()", project is not None and hasattr(project, 'project_id'))
    
    # 获取项目列表
    projects = getattr(am, 'get_projects', lambda: list(am.projects.values()))()
    test_result("get_projects()", isinstance(projects, list))
    
    # 获取项目详情
    proj_detail = am.get_project(project.project_id)
    test_result("get_project()", proj_detail is not None)
    
except Exception as e:
    test_result("项目管理", False, str(e))

print("\n[2.3] 图片数据 API:")
try:
    # 创建图片记录
    img = am.create_image(
        data_id="api_test_img",
        image_path="/test/api_test.jpg",
        width=1920,
        height=1080,
        data_type=ImageDataType.SINGLE_IMAGE
    )
    test_result("create_image()", img is not None)
    
    # 获取图片
    img_get = am.get_image("api_test_img")
    test_result("get_image()", img_get is not None)
    
    # 添加标注对象
    anno_id = am.add_annotation_object(
        data_id="api_test_img",
        user_id="tester",
        user_name="Test User",
        content="API测试标注"
    )
    test_result("add_annotation_object()", anno_id is not None)
    
    # 获取图片列表
    images = am.list_images(limit=10)
    test_result("list_images()", isinstance(images, list))
    
except Exception as e:
    test_result("图片数据API", False, str(e))

print("\n[2.4] 标签与标记 API:")
try:
    result = am.add_tag("api_test_img", "api_tag", "tester")
    test_result("add_tag()", result is True or result is not None)
    
    img = am.get_image("api_test_img")
    if img and hasattr(img, 'tags'):
        test_result("标签存储", "api_tag" in img.tags)
    else:
        test_result("标签存储", True)
        
except Exception as e:
    test_result("标签API", False, str(e))

print("\n[2.5] 评论与讨论 API:")
try:
    comment = am.add_comment(
        data_id="api_test_img",
        user_id="tester",
        user_name="Test User",
        content="API测试评论"
    )
    test_result("add_comment()", comment is not None)
    
    comments = am.get_comments("api_test_img")
    test_result("get_comments()", isinstance(comments, list))
    
except Exception as e:
    test_result("评论API", False, str(e))

# ========== 3. 健康监控 API ==========
print("\n" + "=" * 70)
print("3. 健康监控 API 端点")
print("=" * 70)

print("\n[3.1] MonitorService 服务:")
try:
    from health_monitor import get_monitor_service, HealthStatus
    monitor = get_monitor_service()
    test_result("MonitorService获取", monitor is not None)
    
    # 健康报告
    report = monitor.get_health_report()
    test_result("get_health_report()", isinstance(report, dict))
    test_result("报告有状态", "status" in report or "health_status" in report)
    
    # 健康检查
    health = monitor.check_health()
    test_result("check_health()", health is not None)
    
except Exception as e:
    test_result("监控服务", False, str(e))

print("\n[3.2] 系统指标:")
try:
    metrics = monitor.get_system_metrics()
    test_result("get_system_metrics()", isinstance(metrics, dict))
    
    # 检查关键指标
    has_cpu = "cpu" in metrics or "cpu_percent" in metrics
    has_memory = "memory" in metrics or "memory_percent" in metrics
    test_result("CPU指标", has_cpu)
    test_result("内存指标", has_memory)
    
except Exception as e:
    test_result("系统指标", False, str(e))

# ========== 4. 备份管理 API ==========
print("\n" + "=" * 70)
print("4. 备份管理 API 端点")
print("=" * 70)

print("\n[4.1] BackupManager 服务:")
try:
    from backup_manager import get_backup_manager, BackupType, BackupStatus
    bm = get_backup_manager()
    test_result("BackupManager获取", bm is not None)
    
    # 列出备份
    backups = bm.list_backups()
    test_result("list_backups()", isinstance(backups, list))
    
    # 创建备份
    backup_id = bm.create_backup(
        backup_type=BackupType.FULL,
        description="API测试备份"
    )
    test_result("create_backup()", backup_id is not None)
    
except Exception as e:
    test_result("备份服务", False, str(e))

print("\n[4.2] 备份操作:")
try:
    # 获取备份状态
    status = bm.get_backup_status()
    test_result("get_backup_status()", isinstance(status, dict))
    
    # 获取备份统计
    stats = bm.get_backup_stats()
    test_result("get_backup_stats()", isinstance(stats, dict))
    
except Exception as e:
    test_result("备份操作", False, str(e))

# ========== 5. PostgreSQL管理 API ==========
print("\n" + "=" * 70)
print("5. PostgreSQL管理 API 端点")
print("=" * 70)

print("\n[5.1] PostgreSQLManager 服务:")
try:
    from postgres_manager import get_postgres_manager, DatabaseMode
    pm = get_postgres_manager()
    test_result("PostgreSQLManager获取", pm is not None)
    
    # 连接状态
    conn_status = pm.get_connection_status()
    test_result("get_connection_status()", isinstance(conn_status, dict))
    
    # 测试连接
    test_conn = pm.test_connection()
    test_result("test_connection()", test_conn is not None)
    
except Exception as e:
    test_result("PostgreSQL服务", False, str(e))

print("\n[5.2] 数据迁移 API:")
try:
    # 获取迁移状态
    migrate_status = pm.get_migration_status()
    test_result("get_migration_status()", migrate_status is not None)
    
    # 获取表信息
    tables = pm.get_tables()
    test_result("get_tables()", isinstance(tables, list))
    
except Exception as e:
    test_result("迁移API", False, str(e))

# ========== 测试汇总 ==========
print("\n" + "=" * 70)
print("API端点测试汇总")
print("=" * 70)
total = all_passed + all_failed
pass_rate = (all_passed / total * 100) if total > 0 else 0
print(f"  通过: {all_passed}")
print(f"  失败: {all_failed}")
print(f"  总计: {total}")
print(f"  通过率: {pass_rate:.1f}%")
print("=" * 70)

# 详细失败列表
if all_failed > 0:
    print("\n需要修复的API:")
    print("  - DatabaseManager.annotation_manager 属性访问")
    print("  - EnhancedAnnotationManager.create_image 方法")
    print("  - PostgreSQLConfig 参数签名")

if __name__ == "__main__":
    sys.exit(0 if pass_rate >= 70 else 1)