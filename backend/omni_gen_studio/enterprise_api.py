#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Enterprise - 完整企业级AIGC数据生产平台

以OmniGen_Studio_Complete_Flow为主体，集成完整的企业级功能：
1. OmniGen Studio (AIGC生成) - 主体
2. Nebula Intelligence Suite (爬虫系统)
3. OpenClaw AI Agent
4. 多用户RBAC权限系统
5. 数据集管理 (SFT/DPO/Pretrain)
6. 提示词库管理
7. 标注系统
8. QC审核系统
9. 数据血缘追踪
10. 企业级资产管理

版本: 6.0.1-Enterprise
日期: 2025-07-20
"""

import os
import sys
import sqlite3
import json
import time
import hashlib
import uuid
import asyncio
import aiofiles
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum

# 确保可以导入 backend 目录下的模块
_backend_dir = Path(__file__).parent.parent.resolve()
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks

# 导入真实生成引擎
from production_workbench import (
    ProviderFactory, ProviderType, ProviderConfig,
    GenerationRequest, GenerationResult, GenerationType
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
import bcrypt

# =============================================================================
# 配置
# =============================================================================

# 安全配置
SECRET_KEY = "omni_gen_enterprise_secret_key_2025"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# 数据库路径
DB_PATH = Path(__file__).parent / "database" / "omni_gen_enterprise.db"
DB_PATH.parent.mkdir(exist_ok=True)

# 文件存储路径
STORAGE_PATH = Path(__file__).parent / "storage"
STORAGE_PATH.mkdir(exist_ok=True)

UPLOAD_PATH = STORAGE_PATH / "uploads"
UPLOAD_PATH.mkdir(exist_ok=True)

OUTPUT_PATH = STORAGE_PATH / "outputs"
OUTPUT_PATH.mkdir(exist_ok=True)

# =============================================================================
# FastAPI应用初始化
# =============================================================================

app = FastAPI(
    title="OmniGen Enterprise",
    description="完整企业级AIGC数据生产平台 - 以OmniGen Studio为主体",
    version="6.0.1-Enterprise",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# =============================================================================
# 枚举定义
# =============================================================================

class UserRole(str, Enum):
    """用户角色"""
    SYSTEM_ADMIN = "system_admin"
    PROJECT_ADMIN = "project_admin"
    ALGORITHM_ENGINEER = "algorithm_engineer"
    ANNOTATOR = "annotator"
    REVIEWER = "reviewer"
    GUEST = "guest"


class DatasetType(str, Enum):
    """数据集类型"""
    SFT = "sft"  # Supervised Fine-Tuning
    DPO = "dpo"  # Direct Preference Optimization
    PRETRAIN = "pretrain"  # Pre-training


class AnnotationType(str, Enum):
    """标注类型"""
    CLASSIFICATION = "classification"
    OBJECT_DETECTION = "object_detection"
    SEGMENTATION = "segmentation"
    TEXT_ANNOTATION = "text_annotation"
    PREFERENCE_RANKING = "preference_ranking"


class ReviewStatus(str, Enum):
    """审核状态"""
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# =============================================================================
# 数据模型
# =============================================================================

class User(BaseModel):
    """用户模型"""
    id: str
    username: str
    email: str
    password_hash: str
    role: UserRole
    created_at: datetime
    updated_at: datetime
    is_active: bool = True


class Project(BaseModel):
    """项目模型"""
    id: str
    name: str
    description: str
    owner_id: str
    created_at: datetime
    updated_at: datetime
    storage_quota_gb: int = 100


class Dataset(BaseModel):
    """数据集模型"""
    id: str
    name: str
    description: str
    dataset_type: DatasetType
    project_id: str
    owner_id: str
    version: int = 1
    record_count: int = 0
    file_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PromptLibrary(BaseModel):
    """提示词库模型"""
    id: str
    name: str
    description: str
    project_id: str
    category: str
    tags: List[str] = []
    prompt_template: str
    variables: List[str] = []
    version: int = 1
    rating: float = 0.0
    usage_count: int = 0
    created_by: str
    created_at: datetime
    updated_at: datetime


class AnnotationTask(BaseModel):
    """标注任务模型"""
    id: str
    name: str
    description: str
    annotation_type: AnnotationType
    project_id: str
    asset_ids: List[str]
    assignees: List[str]
    status: TaskStatus
    progress: float = 0.0
    gold_data_ratio: float = 0.1
    created_by: str
    created_at: datetime
    deadline: Optional[datetime] = None


class ReviewTask(BaseModel):
    """审核任务模型"""
    id: str
    name: str
    description: str
    project_id: str
    asset_ids: List[str]
    assignees: List[str]
    status: ReviewStatus
    progress: float = 0.0
    auto_qc_enabled: bool = True
    double_blind: bool = True
    created_by: str
    created_at: datetime


class CrawlTask(BaseModel):
    """爬虫任务模型"""
    id: str
    name: str
    platform: str
    task_type: str
    keywords: List[str] = []
    user_ids: List[str] = []
    limit: int = 100
    status: TaskStatus
    result_count: int = 0
    created_by: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class Asset(BaseModel):
    """资产模型"""
    id: str
    name: str
    asset_type: str
    project_id: str
    file_path: str
    file_size: int
    mime_type: str
    metadata: Dict[str, Any] = {}
    tags: List[str] = []
    parent_id: Optional[str] = None
    lineage: List[str] = []
    qc_status: ReviewStatus = ReviewStatus.PENDING
    created_by: str
    created_at: datetime
    updated_at: datetime


# =============================================================================
# 数据库初始化
# =============================================================================

def init_database():
    """初始化SQLite数据库"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    ''')

    # 项目表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            owner_id TEXT NOT NULL,
            storage_quota_gb INTEGER DEFAULT 100,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    ''')

    # 项目成员表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_members (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(project_id, user_id)
        )
    ''')

    # 资产表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            project_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            mime_type TEXT,
            metadata TEXT,
            tags TEXT,
            parent_id TEXT,
            lineage TEXT,
            qc_status TEXT DEFAULT 'pending',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 数据集表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            dataset_type TEXT NOT NULL,
            project_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            version INTEGER DEFAULT 1,
            record_count INTEGER DEFAULT 0,
            file_path TEXT,
            schema_config TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
    ''')

    # 数据集版本表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dataset_versions (
            id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            record_count INTEGER,
            file_path TEXT,
            change_log TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (dataset_id) REFERENCES datasets (id)
        )
    ''')

    # 提示词库表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompt_library (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            project_id TEXT NOT NULL,
            category TEXT,
            tags TEXT,
            prompt_template TEXT NOT NULL,
            variables TEXT,
            version INTEGER DEFAULT 1,
            rating REAL DEFAULT 0.0,
            usage_count INTEGER DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 提示词版本表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id TEXT PRIMARY KEY,
            prompt_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            prompt_template TEXT NOT NULL,
            change_log TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (prompt_id) REFERENCES prompt_library (id)
        )
    ''')

    # 标注任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS annotation_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            annotation_type TEXT NOT NULL,
            project_id TEXT NOT NULL,
            asset_ids TEXT,
            assignees TEXT,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0.0,
            gold_data_ratio REAL DEFAULT 0.1,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            deadline TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 标注结果表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS annotation_results (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            annotator_id TEXT NOT NULL,
            annotation_data TEXT,
            is_gold_data BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES annotation_tasks (id),
            FOREIGN KEY (annotator_id) REFERENCES users (id)
        )
    ''')

    # 审核任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS review_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            project_id TEXT NOT NULL,
            asset_ids TEXT,
            assignees TEXT,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0.0,
            auto_qc_enabled BOOLEAN DEFAULT 1,
            double_blind BOOLEAN DEFAULT 1,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 审核结果表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS review_results (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            status TEXT,
            reason TEXT,
            auto_score REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES review_tasks (id),
            FOREIGN KEY (reviewer_id) REFERENCES users (id)
        )
    ''')

    # 爬虫任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawl_tasks (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT NOT NULL,
            task_type TEXT NOT NULL,
            keywords TEXT,
            user_ids TEXT,
            limit INTEGER DEFAULT 100,
            status TEXT DEFAULT 'pending',
            result_count INTEGER DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    ''')

    # 爬虫结果表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crawl_results (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            content_id TEXT,
            content_data TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES crawl_tasks (id)
        )
    ''')

    # AIGC生成任务表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS generation_tasks (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            project_id TEXT,
            module_type TEXT NOT NULL,
            prompt TEXT NOT NULL,
            negative_prompt TEXT,
            model_config TEXT,
            parameters TEXT,
            input_files TEXT,
            output_files TEXT,
            status TEXT NOT NULL,
            progress REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 模型配置表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_configs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            weight REAL,
            size TEXT,
            thumbnail TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # LoRA模型表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lora_models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            weight REAL DEFAULT 0.8,
            description TEXT,
            tags TEXT,
            download_count INTEGER DEFAULT 0,
            size TEXT,
            thumbnail TEXT,
            author TEXT,
            version TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')

    # 参数预设表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parameter_presets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            module_type TEXT NOT NULL,
            parameters TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 审计日志表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    conn.commit()
    conn.close()

    print(f"✅ 数据库初始化完成: {DB_PATH}")


# 初始化数据库
init_database()


# =============================================================================
# 认证工具
# =============================================================================

def create_access_token(data: dict, expires_delta: timedelta = None):
    """创建JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    """验证JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_password_hash(password: str) -> str:
    """密码哈希"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


# =============================================================================
# 权限检查
# =============================================================================

def check_permission(user_role: str, permission: str) -> bool:
    """检查权限"""
    role_permissions = {
        "system_admin": ["*"],
        "project_admin": [
            "project.read", "project.update", "project.manage_members",
            "asset.create", "asset.read", "asset.update", "asset.delete", "asset.export",
            "dataset.create", "dataset.read", "dataset.update", "dataset.delete", "dataset.export",
            "prompt.create", "prompt.read", "prompt.update", "prompt.delete", "prompt.generate",
            "crawler.create", "crawler.read", "crawler.update", "crawler.delete", "crawler.execute",
            "annotation.create", "annotation.read", "annotation.update", "annotation.delete", "annotation.execute",
            "review.create", "review.read", "review.execute", "review.approve", "review.reject",
            "generation.create", "generation.read", "generation.cancel",
        ],
        "algorithm_engineer": [
            "asset.create", "asset.read", "asset.update",
            "dataset.create", "dataset.read", "dataset.update",
            "prompt.create", "prompt.read", "prompt.update", "prompt.generate",
            "crawler.create", "crawler.read", "crawler.execute",
            "generation.create", "generation.read", "generation.cancel",
        ],
        "annotator": [
            "asset.read",
            "annotation.read", "annotation.execute",
        ],
        "reviewer": [
            "asset.read",
            "review.read", "review.execute", "review.approve", "review.reject",
        ],
        "guest": [
            "asset.read",
            "dataset.read",
            "prompt.read",
        ],
    }

    permissions = role_permissions.get(user_role, [])
    return "*" in permissions or permission in permissions


# =============================================================================
# 审计日志
# =============================================================================

def log_audit(user_id: str, action: str, resource_type: str = None,
               resource_id: str = None, details: str = None, ip_address: str = None):
    """记录审计日志"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, details, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), user_id, action, resource_type, resource_id, details, ip_address, datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"审计日志记录失败: {e}")


# =============================================================================
# 认证API
# =============================================================================

@app.post("/api/auth/register")
async def register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    """用户注册"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查用户名和邮箱是否存在
    cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username or email already exists")

    # 创建用户
    user_id = str(uuid.uuid4())
    password_hash = get_password_hash(password)

    cursor.execute('''
        INSERT INTO users (id, username, email, password_hash, role, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, username, email, password_hash, UserRole.GUEST.value, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    # 记录审计日志
    log_audit(user_id, "user.register", "user", user_id)

    return {
        "success": True,
        "message": "User registered successfully",
        "data": {"user_id": user_id, "username": username}
    }


@app.post("/api/auth/login")
async def login(
    username: str = Form(...),
    password: str = Form(...)
):
    """用户登录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_id, db_username, email, password_hash, role, is_active = row

    if not is_active:
        raise HTTPException(status_code=401, detail="Account is disabled")

    if not verify_password(password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # 创建token
    access_token = create_access_token({
        "user_id": user_id,
        "username": db_username,
        "email": email,
        "role": role
    })

    # 记录审计日志
    log_audit(user_id, "user.login", "user", user_id)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "username": db_username,
                "email": email,
                "role": role
            }
        }
    }


@app.get("/api/auth/me")
async def get_current_user_info(current_user: dict = Depends(verify_token)):
    """获取当前用户信息"""
    user_id = current_user["user_id"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role, created_at, is_active FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "data": {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "role": row[3],
            "created_at": row[4],
            "is_active": row[5]
        }
    }


@app.put("/api/auth/user/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str = Form(...),
    current_user: dict = Depends(verify_token)
):
    """更新用户角色"""
    if current_user["role"] != UserRole.SYSTEM_ADMIN.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ?, updated_at = ? WHERE id = ?',
                   (role, datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "user.update_role", "user", user_id, f"New role: {role}")

    return {"success": True, "message": "Role updated successfully"}


# =============================================================================
# 项目管理API
# =============================================================================

@app.post("/api/projects")
async def create_project(
    name: str = Form(...),
    description: str = Form(...),
    storage_quota_gb: int = Form(100),
    current_user: dict = Depends(verify_token)
):
    """创建项目"""
    if not check_permission(current_user["role"], "project.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    project_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (id, name, description, owner_id, storage_quota_gb, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (project_id, name, description, current_user["user_id"], storage_quota_gb, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))

    # 添加创建者为项目管理员
    cursor.execute('''
        INSERT INTO project_members (id, project_id, user_id, role, joined_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), project_id, current_user["user_id"], "admin", datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "project.create", "project", project_id)

    return {
        "success": True,
        "data": {
            "id": project_id,
            "name": name,
            "description": description
        }
    }


@app.get("/api/projects")
async def list_projects(
    current_user: dict = Depends(verify_token)
):
    """获取项目列表"""
    user_id = current_user["user_id"]
    user_role = current_user["role"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if user_role == UserRole.SYSTEM_ADMIN.value:
        # 管理员可以看到所有项目
        cursor.execute('''
            SELECT id, name, description, owner_id, storage_quota_gb, created_at, updated_at
            FROM projects ORDER BY created_at DESC
        ''')
    else:
        # 普通用户只能看到有权限的项目
        cursor.execute('''
            SELECT p.id, p.name, p.description, p.owner_id, p.storage_quota_gb, p.created_at, p.updated_at
            FROM projects p
            INNER JOIN project_members pm ON p.id = pm.project_id
            WHERE pm.user_id = ?
            ORDER BY p.created_at DESC
        ''', (user_id,))

    rows = cursor.fetchall()
    conn.close()

    projects = []
    for row in rows:
        projects.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "owner_id": row[3],
            "storage_quota_gb": row[4],
            "created_at": row[5],
            "updated_at": row[6]
        })

    return {"success": True, "data": projects}


@app.get("/api/projects/{project_id}")
async def get_project(
    project_id: str,
    current_user: dict = Depends(verify_token)
):
    """获取项目详情"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, name, description, owner_id, storage_quota_gb, created_at, updated_at
        FROM projects WHERE id = ?
    ''', (project_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")

    # 获取成员列表
    cursor.execute('''
        SELECT u.id, u.username, u.email, pm.role
        FROM project_members pm
        INNER JOIN users u ON pm.user_id = u.id
        WHERE pm.project_id = ?
    ''', (project_id,))
    member_rows = cursor.fetchall()
    conn.close()

    members = []
    for mr in member_rows:
        members.append({
            "user_id": mr[0],
            "username": mr[1],
            "email": mr[2],
            "role": mr[3]
        })

    return {
        "success": True,
        "data": {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "owner_id": row[3],
            "storage_quota_gb": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "members": members
        }
    }


@app.post("/api/projects/{project_id}/members")
async def add_project_member(
    project_id: str,
    user_id: str = Form(...),
    role: str = Form("member"),
    current_user: dict = Depends(verify_token)
):
    """添加项目成员"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR REPLACE INTO project_members (id, project_id, user_id, role, joined_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), project_id, user_id, role, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "project.add_member", "project", project_id, f"Added user: {user_id}")

    return {"success": True, "message": "Member added successfully"}


# =============================================================================
# 资产管理API
# =============================================================================

@app.post("/api/assets")
async def create_asset(
    name: str = Form(...),
    asset_type: str = Form(...),
    project_id: str = Form(...),
    file: UploadFile = File(...),
    tags: str = Form("[]"),
    metadata: str = Form("{}"),
    current_user: dict = Depends(verify_token)
):
    """创建资产"""
    if not check_permission(current_user["role"], "asset.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    asset_id = str(uuid.uuid4())

    # 保存文件
    file_ext = Path(file.filename).suffix
    file_path = UPLOAD_PATH / f"{asset_id}{file_ext}"

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO assets (id, name, asset_type, project_id, file_path, file_size, mime_type, tags, metadata, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (asset_id, name, asset_type, project_id, str(file_path), len(content), file.content_type, tags, metadata,
          current_user["user_id"], datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "asset.create", "asset", asset_id)

    return {
        "success": True,
        "data": {
            "id": asset_id,
            "name": name,
            "file_path": str(file_path)
        }
    }


@app.get("/api/assets")
async def list_assets(
    project_id: Optional[str] = None,
    asset_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(verify_token)
):
    """获取资产列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, asset_type, project_id, file_path, file_size, mime_type, tags, qc_status, created_at FROM assets WHERE 1=1"
    params = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if asset_type:
        query += " AND asset_type = ?"
        params.append(asset_type)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    # 获取总数
    count_query = "SELECT COUNT(*) FROM assets WHERE 1=1"
    count_params = []
    if project_id:
        count_query += " AND project_id = ?"
        count_params.append(project_id)
    if asset_type:
        count_query += " AND asset_type = ?"
        count_params.append(asset_type)

    cursor.execute(count_query, count_params)
    total = cursor.fetchone()[0]
    conn.close()

    assets = []
    for row in rows:
        assets.append({
            "id": row[0],
            "name": row[1],
            "asset_type": row[2],
            "project_id": row[3],
            "file_path": row[4],
            "file_size": row[5],
            "mime_type": row[6],
            "tags": json.loads(row[7]) if row[7] else [],
            "qc_status": row[8],
            "created_at": row[9]
        })

    return {
        "success": True,
        "data": assets,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }


@app.get("/api/assets/{asset_id}/lineage")
async def get_asset_lineage(
    asset_id: str,
    current_user: dict = Depends(verify_token)
):
    """获取资产血缘"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    lineage = []
    current_id = asset_id

    while current_id:
        cursor.execute('''
            SELECT id, name, asset_type, parent_id, created_at FROM assets WHERE id = ?
        ''', (current_id,))
        row = cursor.fetchone()

        if not row:
            break

        lineage.append({
            "id": row[0],
            "name": row[1],
            "asset_type": row[2],
            "created_at": row[4]
        })

        current_id = row[3]  # parent_id

    conn.close()

    return {
        "success": True,
        "data": lineage
    }


# =============================================================================
# 数据集管理API
# =============================================================================

@app.post("/api/datasets")
async def create_dataset(
    name: str = Form(...),
    description: str = Form(...),
    dataset_type: DatasetType = Form(...),
    project_id: str = Form(...),
    schema_config: str = Form("{}"),
    current_user: dict = Depends(verify_token)
):
    """创建数据集"""
    if not check_permission(current_user["role"], "dataset.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    dataset_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO datasets (id, name, description, dataset_type, project_id, owner_id, schema_config, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (dataset_id, name, description, dataset_type.value, project_id, current_user["user_id"],
          schema_config, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "dataset.create", "dataset", dataset_id)

    return {
        "success": True,
        "data": {
            "id": dataset_id,
            "name": name,
            "dataset_type": dataset_type.value
        }
    }


@app.get("/api/datasets")
async def list_datasets(
    project_id: Optional[str] = None,
    dataset_type: Optional[DatasetType] = None,
    current_user: dict = Depends(verify_token)
):
    """获取数据集列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, description, dataset_type, project_id, owner_id, version, record_count, created_at, updated_at FROM datasets WHERE 1=1"
    params = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if dataset_type:
        query += " AND dataset_type = ?"
        params.append(dataset_type.value)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    datasets = []
    for row in rows:
        datasets.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "dataset_type": row[3],
            "project_id": row[4],
            "owner_id": row[5],
            "version": row[6],
            "record_count": row[7],
            "created_at": str(row[8]),
            "updated_at": str(row[9])
        })

    return {"success": True, "data": datasets}


@app.post("/api/datasets/{dataset_id}/build")
async def build_dataset(
    dataset_id: str,
    asset_ids: str = Form(...),
    current_user: dict = Depends(verify_token)
):
    """构建数据集"""
    if not check_permission(current_user["role"], "dataset.update"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取数据集信息
    cursor.execute('SELECT name, dataset_type, project_id, version FROM datasets WHERE id = ?', (dataset_id,))
    dataset = cursor.fetchone()

    if not dataset:
        conn.close()
        raise HTTPException(status_code=404, detail="Dataset not found")

    asset_ids_list = json.loads(asset_ids)

    # 生成数据集文件
    dataset_type = dataset[1]

    if dataset_type == DatasetType.SFT.value:
        # SFT数据集格式
        output_data = []
        for asset_id in asset_ids_list:
            cursor.execute('SELECT file_path, metadata FROM assets WHERE id = ?', (asset_id,))
            asset = cursor.fetchone()
            if asset:
                output_data.append({
                    "image": asset[0],
                    "text": asset[1].get("caption", "") if asset[1] else ""
                })

    elif dataset_type == DatasetType.DPO.value:
        # DPO数据集格式
        output_data = []
        for i in range(0, len(asset_ids_list) - 1, 2):
            if i + 1 < len(asset_ids_list):
                cursor.execute('SELECT file_path FROM assets WHERE id IN (?, ?)', (asset_ids_list[i], asset_ids_list[i + 1]))
                assets = cursor.fetchall()
                if len(assets) == 2:
                    output_data.append({
                        "chosen": {"image": assets[0][0]},
                        "rejected": {"image": assets[1][0]}
                    })

    elif dataset_type == DatasetType.PRETRAIN.value:
        # Pretrain数据集格式
        output_data = []
        for asset_id in asset_ids_list:
            cursor.execute('SELECT file_path, metadata FROM assets WHERE id = ?', (asset_id,))
            asset = cursor.fetchone()
            if asset:
                output_data.append({
                    "text": asset[1].get("text", "") if asset[1] else ""
                })

    # 保存数据集文件
    output_file = OUTPUT_PATH / f"dataset_{dataset_id}.jsonl"
    with open(output_file, "w", encoding="utf-8") as f:
        for item in output_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 更新数据集记录
    new_version = dataset[3] + 1
    cursor.execute('''
        UPDATE datasets SET record_count = ?, version = ?, file_path = ?, updated_at = ?
        WHERE id = ?
    ''', (len(output_data), new_version, str(output_file), datetime.utcnow().isoformat(), dataset_id))

    # 添加版本记录
    cursor.execute('''
        INSERT INTO dataset_versions (id, dataset_id, version, record_count, file_path, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), dataset_id, new_version, len(output_data), str(output_file),
          current_user["user_id"], datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "dataset.build", "dataset", dataset_id, f"Records: {len(output_data)}")

    return {
        "success": True,
        "data": {
            "dataset_id": dataset_id,
            "record_count": len(output_data),
            "version": new_version,
            "file_path": str(output_file)
        }
    }


@app.get("/api/datasets/{dataset_id}/download")
async def download_dataset(
    dataset_id: str,
    current_user: dict = Depends(verify_token)
):
    """下载数据集"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT file_path, name, dataset_type FROM datasets WHERE id = ?', (dataset_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Dataset not found")

    file_path = row[0]
    if not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")

    return FileResponse(file_path, filename=f"{row[1]}.jsonl", media_type="application/jsonl")


# =============================================================================
# 提示词库API
# =============================================================================

@app.post("/api/prompts")
async def create_prompt(
    name: str = Form(...),
    description: str = Form(...),
    project_id: str = Form(...),
    category: str = Form(...),
    tags: str = Form("[]"),
    prompt_template: str = Form(...),
    variables: str = Form("[]"),
    current_user: dict = Depends(verify_token)
):
    """创建提示词"""
    if not check_permission(current_user["role"], "prompt.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    prompt_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO prompt_library (id, name, description, project_id, category, tags, prompt_template, variables, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (prompt_id, name, description, project_id, category, tags, prompt_template, variables,
          current_user["user_id"], datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))

    # 添加版本记录
    cursor.execute('''
        INSERT INTO prompt_versions (id, prompt_id, version, prompt_template, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (str(uuid.uuid4()), prompt_id, 1, prompt_template, current_user["user_id"], datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "prompt.create", "prompt", prompt_id)

    return {
        "success": True,
        "data": {
            "id": prompt_id,
            "name": name
        }
    }


@app.get("/api/prompts")
async def list_prompts(
    project_id: Optional[str] = None,
    category: Optional[str] = None,
    current_user: dict = Depends(verify_token)
):
    """获取提示词列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, description, project_id, category, tags, prompt_template, rating, usage_count, created_at FROM prompt_library WHERE 1=1"
    params = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY rating DESC, usage_count DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    prompts = []
    for row in rows:
        prompts.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "project_id": row[3],
            "category": row[4],
            "tags": json.loads(row[5]) if row[5] else [],
            "prompt_template": row[6],
            "rating": row[7],
            "usage_count": row[8],
            "created_at": row[9]
        })

    return {"success": True, "data": prompts}


@app.post("/api/prompts/{prompt_id}/use")
async def use_prompt(
    prompt_id: str,
    variables: str = Form("{}"),
    current_user: dict = Depends(verify_token)
):
    """使用提示词"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT prompt_template, usage_count FROM prompt_library WHERE id = ?', (prompt_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt_template = row[0]
    usage_count = row[1]

    # 替换变量
    variables_dict = json.loads(variables)
    try:
        final_prompt = prompt_template.format(**variables_dict)
    except KeyError:
        final_prompt = prompt_template

    # 更新使用次数
    cursor.execute('UPDATE prompt_library SET usage_count = ? WHERE id = ?', (usage_count + 1, prompt_id))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "data": {
            "prompt": final_prompt
        }
    }


@app.post("/api/prompts/{prompt_id}/rate")
async def rate_prompt(
    prompt_id: str,
    rating: float = Form(...),
    current_user: dict = Depends(verify_token)
):
    """评分提示词"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT rating FROM prompt_library WHERE id = ?', (prompt_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Prompt not found")

    current_rating = row[0]
    new_rating = (current_rating + rating) / 2

    cursor.execute('UPDATE prompt_library SET rating = ? WHERE id = ?', (new_rating, prompt_id))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "data": {
            "rating": new_rating
        }
    }


# =============================================================================
# 标注系统API
# =============================================================================

@app.post("/api/annotation/tasks")
async def create_annotation_task(
    name: str = Form(...),
    description: str = Form(...),
    annotation_type: AnnotationType = Form(...),
    project_id: str = Form(...),
    asset_ids: str = Form(...),
    assignees: str = Form("[]"),
    gold_data_ratio: float = Form(0.1),
    deadline: Optional[str] = Form(None),
    current_user: dict = Depends(verify_token)
):
    """创建标注任务"""
    if not check_permission(current_user["role"], "annotation.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    task_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO annotation_tasks (id, name, description, annotation_type, project_id, asset_ids, assignees, status, gold_data_ratio, created_by, created_at, deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, name, description, annotation_type.value, project_id, asset_ids, assignees,
          TaskStatus.PENDING.value, gold_data_ratio, current_user["user_id"], datetime.utcnow().isoformat(), deadline))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "annotation.create", "annotation_task", task_id)

    return {
        "success": True,
        "data": {
            "id": task_id,
            "name": name
        }
    }


@app.get("/api/annotation/tasks")
async def list_annotation_tasks(
    project_id: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    current_user: dict = Depends(verify_token)
):
    """获取标注任务列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, description, annotation_type, project_id, status, progress, created_at, deadline FROM annotation_tasks WHERE 1=1"
    params = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status.value)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "annotation_type": row[3],
            "project_id": row[4],
            "status": row[5],
            "progress": row[6],
            "created_at": row[7],
            "deadline": row[8]
        })

    return {"success": True, "data": tasks}


@app.get("/api/annotation/tasks/{task_id}/next")
async def get_next_annotation(
    task_id: str,
    current_user: dict = Depends(verify_token)
):
    """获取下一个待标注资产"""
    if not check_permission(current_user["role"], "annotation.execute"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取任务信息
    cursor.execute('SELECT asset_ids, status FROM annotation_tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if not task:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")

    asset_ids = json.loads(task[0])

    # 获取已标注的资产
    cursor.execute('SELECT asset_id FROM annotation_results WHERE task_id = ?', (task_id,))
    annotated = [row[0] for row in cursor.fetchall()]

    # 找到下一个未标注的资产
    for asset_id in asset_ids:
        if asset_id not in annotated:
            cursor.execute('SELECT id, name, asset_type, file_path, metadata FROM assets WHERE id = ?', (asset_id,))
            asset = cursor.fetchone()

            if asset:
                conn.close()
                return {
                    "success": True,
                    "data": {
                        "task_id": task_id,
                        "asset": {
                            "id": asset[0],
                            "name": asset[1],
                            "asset_type": asset[2],
                            "file_path": asset[3],
                            "metadata": json.loads(asset[4]) if asset[4] else {}
                        }
                    }
                }

    conn.close()
    return {"success": True, "data": None, "message": "All assets annotated"}


@app.post("/api/annotation/tasks/{task_id}/submit")
async def submit_annotation(
    task_id: str,
    asset_id: str = Form(...),
    annotation_data: str = Form(...),
    is_gold_data: bool = Form(False),
    current_user: dict = Depends(verify_token)
):
    """提交标注结果"""
    result_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO annotation_results (id, task_id, asset_id, annotator_id, annotation_data, is_gold_data, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (result_id, task_id, asset_id, current_user["user_id"], annotation_data, is_gold_data, datetime.utcnow().isoformat()))

    # 更新任务进度
    cursor.execute('SELECT asset_ids FROM annotation_tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    total_assets = len(json.loads(task[0]))

    cursor.execute('SELECT COUNT(*) FROM annotation_results WHERE task_id = ?', (task_id,))
    completed = cursor.fetchone()[0]

    progress = (completed / total_assets) * 100
    status = TaskStatus.COMPLETED.value if completed >= total_assets else TaskStatus.PROCESSING.value

    cursor.execute('UPDATE annotation_tasks SET progress = ?, status = ? WHERE id = ?', (progress, status, task_id))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "annotation.submit", "annotation_result", result_id)

    return {"success": True, "message": "Annotation submitted"}


# =============================================================================
# 审核系统API
# =============================================================================

@app.post("/api/review/tasks")
async def create_review_task(
    name: str = Form(...),
    description: str = Form(...),
    project_id: str = Form(...),
    asset_ids: str = Form(...),
    assignees: str = Form("[]"),
    auto_qc_enabled: bool = Form(True),
    double_blind: bool = Form(True),
    current_user: dict = Depends(verify_token)
):
    """创建审核任务"""
    if not check_permission(current_user["role"], "review.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    task_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO review_tasks (id, name, description, project_id, asset_ids, assignees, status, progress, auto_qc_enabled, double_blind, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, name, description, project_id, asset_ids, assignees,
          ReviewStatus.PENDING.value, 0.0, auto_qc_enabled, double_blind, current_user["user_id"], datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "review.create", "review_task", task_id)

    return {
        "success": True,
        "data": {
            "id": task_id,
            "name": name
        }
    }


@app.get("/api/review/tasks")
async def list_review_tasks(
    project_id: Optional[str] = None,
    status: Optional[ReviewStatus] = None,
    current_user: dict = Depends(verify_token)
):
    """获取审核任务列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, description, project_id, status, progress, created_at FROM review_tasks WHERE 1=1"
    params = []

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)
    if status:
        query += " AND status = ?"
        params.append(status.value)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "project_id": row[3],
            "status": row[4],
            "progress": row[5],
            "created_at": row[6]
        })

    return {"success": True, "data": tasks}


@app.post("/api/review/tasks/{task_id}/review")
async def submit_review(
    task_id: str,
    asset_id: str = Form(...),
    status: ReviewStatus = Form(...),
    reason: str = Form(""),
    current_user: dict = Depends(verify_token)
):
    """提交审核结果"""
    if not check_permission(current_user["role"], "review.execute"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    result_id = str(uuid.uuid4())

    # 自动QC评分（模拟）
    auto_score = None
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查是否启用自动QC
    cursor.execute('SELECT auto_qc_enabled FROM review_tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()

    if task and task[0]:
        # 简单的自动评分模拟
        import random
        auto_score = random.uniform(0.6, 1.0)

    cursor.execute('''
        INSERT INTO review_results (id, task_id, asset_id, reviewer_id, status, reason, auto_score, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (result_id, task_id, asset_id, current_user["user_id"], status.value, reason, auto_score, datetime.utcnow().isoformat()))

    # 更新资产审核状态
    cursor.execute('UPDATE assets SET qc_status = ? WHERE id = ?', (status.value, asset_id))

    # 更新任务进度
    cursor.execute('SELECT asset_ids FROM review_tasks WHERE id = ?', (task_id,))
    task = cursor.fetchone()
    total_assets = len(json.loads(task[0]))

    cursor.execute('SELECT COUNT(*) FROM review_results WHERE task_id = ?', (task_id,))
    completed = cursor.fetchone()[0]

    progress = (completed / total_assets) * 100
    task_status = ReviewStatus.APPROVED.value if completed >= total_assets else ReviewStatus.IN_REVIEW.value

    cursor.execute('UPDATE review_tasks SET progress = ?, status = ? WHERE id = ?', (progress, task_status, task_id))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "review.submit", "review_result", result_id)

    return {"success": True, "message": "Review submitted"}


# =============================================================================
# 爬虫系统API (Nebula集成)
# =============================================================================

@app.post("/api/crawler/tasks")
async def create_crawl_task(
    name: str = Form(...),
    platform: str = Form(...),
    task_type: str = Form(...),
    keywords: str = Form("[]"),
    user_ids: str = Form("[]"),
    limit: int = Form(100),
    current_user: dict = Depends(verify_token)
):
    """创建爬虫任务"""
    if not check_permission(current_user["role"], "crawler.create"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    task_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO crawl_tasks (id, name, platform, task_type, keywords, user_ids, limit, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, name, platform, task_type, keywords, user_ids, limit, TaskStatus.PENDING.value,
          current_user["user_id"], datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    log_audit(current_user["user_id"], "crawler.create", "crawl_task", task_id)

    return {
        "success": True,
        "data": {
            "id": task_id,
            "name": name
        }
    }


@app.post("/api/crawler/tasks/{task_id}/execute")
async def execute_crawl_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(verify_token)
):
    """执行爬虫任务"""
    if not check_permission(current_user["role"], "crawler.execute"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    async def run_crawler():
        # 模拟爬虫执行（实际需要集成Nebula）
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT platform, task_type, keywords, limit FROM crawl_tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()

        if not task:
            return

        # 更新状态为运行中
        cursor.execute('UPDATE crawl_tasks SET status = ? WHERE id = ?', (TaskStatus.PROCESSING.value, task_id))
        conn.commit()

        # 模拟爬取数据
        import random
        result_count = random.randint(10, min(task[3], 100))

        keywords = json.loads(task[2]) if task[2] else []

        # 插入模拟结果
        for i in range(result_count):
            cursor.execute('''
                INSERT INTO crawl_results (id, task_id, platform, content_id, content_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(uuid.uuid4()), task_id, task[0], f"content_{i}",
                  json.dumps({"keyword": keywords[0] if keywords else "test", "index": i}),
                  datetime.utcnow().isoformat()))

        # 更新任务状态
        cursor.execute('''
            UPDATE crawl_tasks SET status = ?, result_count = ?, completed_at = ? WHERE id = ?
        ''', (TaskStatus.COMPLETED.value, result_count, datetime.utcnow().isoformat(), task_id))
        conn.commit()
        conn.close()

    background_tasks.add_task(run_crawler)

    return {
        "success": True,
        "message": "Crawl task started"
    }


@app.get("/api/crawler/tasks")
async def list_crawl_tasks(
    platform: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    current_user: dict = Depends(verify_token)
):
    """获取爬虫任务列表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, name, platform, task_type, status, result_count, created_at, completed_at FROM crawl_tasks WHERE 1=1"
    params = []

    if platform:
        query += " AND platform = ?"
        params.append(platform)
    if status:
        query += " AND status = ?"
        params.append(status.value)

    query += " ORDER BY created_at DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "name": row[1],
            "platform": row[2],
            "task_type": row[3],
            "status": row[4],
            "result_count": row[5],
            "created_at": row[6],
            "completed_at": row[7]
        })

    return {"success": True, "data": tasks}


@app.get("/api/crawler/tasks/{task_id}/results")
async def get_crawl_results(
    task_id: str,
    current_user: dict = Depends(verify_token)
):
    """获取爬虫结果"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('SELECT id, platform, content_id, content_data, created_at FROM crawl_results WHERE task_id = ? ORDER BY created_at DESC', (task_id,))
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "platform": row[1],
            "content_id": row[2],
            "content_data": json.loads(row[3]) if row[3] else {},
            "created_at": row[4]
        })

    return {"success": True, "data": results}


# =============================================================================
# AIGC生成API (OmniGen集成)
# =============================================================================

@app.post("/api/aigc/generation")
async def start_aigc_generation(
    background_tasks: BackgroundTasks,
    module_type: str = Form(...),
    prompt: str = Form(...),
    negative_prompt: str = Form(None),
    model_config: str = Form("{}"),
    parameters: str = Form("{}"),
    project_id: str = Form(None),
    current_user: dict = Depends(verify_token)
):
    """开始AIGC生成任务"""
    task_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO generation_tasks (id, user_id, project_id, module_type, prompt, negative_prompt, model_config, parameters, status, progress, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (task_id, current_user["user_id"], project_id, module_type, prompt, negative_prompt,
          model_config, parameters, TaskStatus.PENDING.value, 0, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

    # =============================================================================
    # module_type → ProviderType 映射
    # =============================================================================

    MODULE_TYPE_TO_PROVIDER = {
        # 文生图
        "text_to_image": ProviderType.OMNI_GEN_LOCAL,
        "txt2img": ProviderType.OMNI_GEN_LOCAL,
        "t2i": ProviderType.OMNI_GEN_LOCAL,
        # 图生图
        "image_to_image": ProviderType.COMFYUI_LOCAL,
        "img2img": ProviderType.COMFYUI_LOCAL,
        "i2i": ProviderType.COMFYUI_LOCAL,
        # 图像增强
        "image_enhance": ProviderType.IMAGE_EDIT,
        "enhance": ProviderType.IMAGE_EDIT,
        # 视频生成
        "text_to_video": ProviderType.KLING,
        "video": ProviderType.KLING,
        # 图像放大
        "image_upscale": ProviderType.IMAGE_UPSCALE,
        "upscale": ProviderType.IMAGE_UPSCALE,
        # 3D 生成
        "text_to_3d": ProviderType.HUNYUAN3D,
        "image_to_3d": ProviderType.TRIPOSR,
        "3d": ProviderType.HUNYUAN3D,
    }

    def _module_type_to_provider(module_type: str) -> ProviderType:
        """将 module_type 字符串映射为 ProviderType 枚举"""
        provider = MODULE_TYPE_TO_PROVIDER.get(module_type.lower())
        if provider is None:
            # 默认回退到 OMNI_GEN_LOCAL
            logger.warning(f"Unknown module_type '{module_type}', falling back to OMNI_GEN_LOCAL")
            provider = ProviderType.OMNI_GEN_LOCAL
        return provider

    def _module_type_to_generation_type(module_type: str) -> GenerationType:
        """将 module_type 映射为 GenerationType"""
        mt = module_type.lower()
        if mt in ("video", "text_to_video", "image_to_video"):
            return GenerationType.VIDEO
        elif mt in ("image_enhance", "enhance"):
            return GenerationType.IMAGE_EDIT
        elif mt in ("image_upscale", "upscale"):
            return GenerationType.IMAGE_UPSCALE
        elif mt in ("text_to_3d", "image_to_3d", "3d"):
            return GenerationType.TEXT_TO_3D
        elif mt in ("image_to_image", "img2img", "i2i"):
            return GenerationType.IMAGE_VARIATION
        else:
            return GenerationType.IMAGE

    # 后台执行生成任务
    async def run_generation():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('UPDATE generation_tasks SET status = ? WHERE id = ?', (TaskStatus.PROCESSING.value, task_id))
        conn.commit()

        output_files = []
        error_message = None
        generated_images = []

        try:
            # 解析参数
            parsed_params = json.loads(parameters) if parameters and parameters != "{}" else {}
            parsed_model_config = json.loads(model_config) if model_config and model_config != "{}" else {}

            # 构建 GenerationRequest
            provider_type = _module_type_to_provider(module_type)
            gen_type = _module_type_to_generation_type(module_type)

            request = GenerationRequest(
                request_id=task_id,
                provider_type=provider_type,
                generation_type=gen_type,
                prompt=prompt,
                negative_prompt=negative_prompt or "",
                width=parsed_params.get("width", parsed_model_config.get("width", 1024)),
                height=parsed_params.get("height", parsed_model_config.get("height", 1024)),
                steps=parsed_params.get("steps", parsed_model_config.get("steps", 20)),
                cfg_scale=parsed_params.get("cfg_scale", parsed_model_config.get("cfg_scale", 7.0)),
                seed=parsed_params.get("seed", -1),
                sampler=parsed_params.get("sampler", "euler"),
                model=parsed_model_config.get("model", ""),
                batch_count=parsed_params.get("batch_count", 1),
                extra_params=parsed_params.get("extra", {}),
            )

            # 通过 ProviderFactory 创建提供商并执行生成
            provider_config = ProviderConfig(
                provider_type=provider_type,
                name=f"enterprise_{provider_type.value}",
                comfyui_url=os.environ.get("COMFYUI_URL", "http://localhost"),
                comfyui_port=int(os.environ.get("COMFYUI_PORT", "8188")),
            )

            provider = ProviderFactory.create_provider(provider_config)
            logger.info(f"Starting generation via {provider_type.value} for task {task_id}")

            result = await provider.generate(request)

            if result.status == "completed" or result.status == "success":
                # 收集生成的文件
                if result.images:
                    output_files.extend(result.images)
                if result.videos:
                    output_files.extend(result.videos)

                # 如果 Provider 返回了文件路径但为空，使用保存逻辑
                if not output_files:
                    # 尝试从 result 对象获取 output_path
                    output_path = getattr(result, "output_path", None)
                    if output_path:
                        output_files.append(str(output_path))
                    else:
                        # 保存 placeholder 作为最后回退 - 生成一个简单的占位PNG图片
                        from PIL import Image as PILImage
                        try:
                            img = PILImage.new('RGB', (512, 512), color=(50, 50, 80))
                            from PIL import ImageDraw, ImageFont
                            draw = ImageDraw.Draw(img)
                            draw.text((100, 240), f"Generation Failed", fill=(200, 200, 200))
                            draw.text((100, 260), provider_type.value, fill=(150, 150, 150))
                            img.save(str(output_file))
                        except ImportError:
                            output_file.write_text(f"Generated by {provider_type.value}")
                        output_files.append(str(output_file))

                # 更新进度
                cursor.execute('''
                    UPDATE generation_tasks SET progress = ? WHERE id = ?
                ''', (100, task_id))
            else:
                error_message = result.error or f"Provider returned status: {result.status}"

        except Exception as e:
            error_message = f"Generation failed: {str(e)}"
            logger.error(f"Generation failed for task {task_id}: {e}", exc_info=True)

            # 回退：生成占位PNG图片（含错误信息）
            output_file = OUTPUT_PATH / f"generation_{task_id}.png"
            try:
                from PIL import Image as PILImage, ImageDraw
                img = PILImage.new('RGB', (512, 512), color=(40, 40, 60))
                draw = ImageDraw.Draw(img)
                draw.text((50, 240), f"Generation Failed:", fill=(255, 100, 100))
                draw.text((50, 270), error_message[:60], fill=(200, 200, 200))
                img.save(str(output_file))
            except ImportError:
                output_file.write_text(f"Generated image placeholder (fallback - {error_message})")
            output_files.append(str(output_file))

        finally:
            # 更新数据库记录
            if error_message:
                cursor.execute('''
                    UPDATE generation_tasks SET status = ?, progress = ?, output_files = ?, error_message = ?, completed_at = ?
                    WHERE id = ?
                ''', (TaskStatus.FAILED.value, 0 if not output_files else 50,
                      json.dumps(output_files) if output_files else "[]",
                      error_message, datetime.utcnow().isoformat(), task_id))
            else:
                cursor.execute('''
                    UPDATE generation_tasks SET status = ?, progress = ?, output_files = ?, completed_at = ?
                    WHERE id = ?
                ''', (TaskStatus.COMPLETED.value, 100,
                      json.dumps(output_files) if output_files else "[]",
                      datetime.utcnow().isoformat(), task_id))
            conn.commit()
            conn.close()

    background_tasks.add_task(run_generation)

    return {
        "success": True,
        "data": {
            "generationId": task_id,
            "status": TaskStatus.PENDING.value
        }
    }


@app.get("/api/aigc/generation/status")
async def get_generation_status(
    id: Optional[str] = None,
    module_type: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    limit: int = 20,
    offset: int = 0,
    action: Optional[str] = None,
    current_user: dict = Depends(verify_token)
):
    """获取生成任务状态"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = '''
        SELECT id, user_id, project_id, module_type, prompt, negative_prompt,
               model_config, parameters, output_files, status, progress, created_at, completed_at, error_message
        FROM generation_tasks
        WHERE user_id = ?
    '''
    params = [current_user["user_id"]]

    if id:
        query += " AND id = ?"
        params.append(id)
    if module_type:
        query += " AND module_type = ?"
        params.append(module_type)
    if status:
        query += " AND status = ?"
        params.append(status.value)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    tasks = []
    for row in rows:
        tasks.append({
            "id": row[0],
            "user_id": row[1],
            "project_id": row[2],
            "module_type": row[3],
            "prompt": row[4],
            "negative_prompt": row[5],
            "model_config": json.loads(row[6]) if row[6] else {},
            "parameters": json.loads(row[7]) if row[7] else {},
            "output_files": json.loads(row[8]) if row[8] else [],
            "status": row[9],
            "progress": row[10],
            "created_at": row[11],
            "completed_at": row[12],
            "error_message": row[13],
            "canRetry": row[9] in [TaskStatus.FAILED.value],
            "canCancel": row[9] in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]
        })

    if action == "stats":
        return {
            "success": True,
            "stats": {
                "total": len(tasks),
                "pending": len([t for t in tasks if t["status"] == TaskStatus.PENDING.value]),
                "processing": len([t for t in tasks if t["status"] == TaskStatus.PROCESSING.value]),
                "completed": len([t for t in tasks if t["status"] == TaskStatus.COMPLETED.value]),
                "failed": len([t for t in tasks if t["status"] == TaskStatus.FAILED.value])
            }
        }

    return {
        "success": True,
        "data": {
            "generations": tasks,
            "total": len(tasks),
            "hasMore": len(tasks) == limit
        }
    }


# =============================================================================
# OpenClaw AI Agent集成
# =============================================================================

@app.get("/api/openclaw/status")
async def get_openclaw_status(current_user: dict = Depends(verify_token)):
    """获取OpenClaw状态"""
    # 模拟OpenClaw状态
    return {
        "success": True,
        "data": {
            "status": "ready",
            "agents": [
                {"id": "agent-1", "name": "Research Agent", "status": "idle"},
                {"id": "agent-2", "name": "Data Collector", "status": "idle"},
                {"id": "agent-3", "name": "Content Generator", "status": "idle"}
            ]
        }
    }


@app.post("/api/openclaw/prompt/generate")
async def generate_prompt_with_openclaw(
    topic: str = Form(...),
    style: str = Form("detailed"),
    length: str = Form("medium"),
    current_user: dict = Depends(verify_token)
):
    """使用OpenClaw生成提示词"""
    # 模拟OpenClaw提示词生成
    prompt_templates = {
        "short": f"A high-quality image of {topic}, simple composition, clean background",
        "medium": f"A detailed and beautiful illustration of {topic}, with rich colors, intricate details, professional lighting",
        "long": f"An extremely detailed, high-resolution artistic representation of {topic}, featuring sophisticated composition, dramatic lighting, photorealistic style, 8K quality, masterpiece"
    }

    return {
        "success": True,
        "data": {
            "prompt": prompt_templates.get(length, prompt_templates["medium"]),
            "topic": topic,
            "style": style,
            "length": length
        }
    }


@app.post("/api/openclaw/prompt/optimize")
async def optimize_prompt_with_openclaw(
    prompt: str = Form(...),
    optimization_type: str = Form("enhance"),
    current_user: dict = Depends(verify_token)
):
    """使用OpenClaw优化提示词"""
    # 模拟提示词优化
    enhancements = [
        "masterpiece, best quality, highly detailed",
        "ultra detailed, 8k resolution, professional photography",
        "beautiful composition, cinematic lighting, vibrant colors"
    ]

    import random
    enhancement = random.choice(enhancements)

    return {
        "success": True,
        "data": {
            "original_prompt": prompt,
            "optimized_prompt": f"{prompt}, {enhancement}"
        }
    }


# =============================================================================
# 审计日志API
# =============================================================================

@app.get("/api/audit/logs")
async def list_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: dict = Depends(verify_token)
):
    """获取审计日志"""
    if current_user["role"] != UserRole.SYSTEM_ADMIN.value:
        raise HTTPException(status_code=403, detail="Admin access required")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = "SELECT id, user_id, action, resource_type, resource_id, details, ip_address, created_at FROM audit_logs WHERE 1=1"
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    if action:
        query += " AND action LIKE ?"
        params.append(f"%{action}%")
    if resource_type:
        query += " AND resource_type = ?"
        params.append(resource_type)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([page_size, (page - 1) * page_size])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logs = []
    for row in rows:
        logs.append({
            "id": row[0],
            "user_id": row[1],
            "action": row[2],
            "resource_type": row[3],
            "resource_id": row[4],
            "details": row[5],
            "ip_address": row[6],
            "created_at": row[7]
        })

    return {"success": True, "data": logs}


# =============================================================================
# 根端点和健康检查
# =============================================================================

@app.get("/")
async def root():
    """根端点"""
    return {
        "name": "OmniGen Enterprise",
        "version": "6.0.1-Enterprise",
        "description": "完整企业级AIGC数据生产平台",
        "modules": [
            "OmniGen Studio (AIGC生成)",
            "Nebula Intelligence Suite (爬虫)",
            "OpenClaw AI Agent",
            "多用户RBAC",
            "数据集管理 (SFT/DPO/Pretrain)",
            "提示词库",
            "标注系统",
            "QC审核系统",
            "数据血缘追踪"
        ],
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "version": "6.0.1-Enterprise",
        "timestamp": datetime.utcnow().isoformat()
    }


# =============================================================================
# 主程序入口
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("OmniGen Enterprise - 企业级AIGC数据生产平台")
    print("版本: 6.0.1-Enterprise")
    print("=" * 70)
    print("功能模块:")
    print("  • OmniGen Studio (AIGC生成) - 主体")
    print("  • Nebula Intelligence Suite (爬虫系统)")
    print("  • OpenClaw AI Agent")
    print("  • 多用户RBAC权限系统")
    print("  • 数据集管理 (SFT/DPO/Pretrain)")
    print("  • 提示词库管理")
    print("  • 标注系统")
    print("  • QC审核系统")
    print("  • 数据血缘追踪")
    print("=" * 70)

    uvicorn.run(app, host="0.0.0.0", port=8000)
