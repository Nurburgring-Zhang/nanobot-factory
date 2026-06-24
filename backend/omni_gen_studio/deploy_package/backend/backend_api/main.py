#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC批处理工具 v5.4 本地API服务器
替代Supabase Edge Functions，提供完整的本地化后端服务
"""

import os
import sys
import sqlite3
import json
import time
import hashlib
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import aiofiles
import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

# 导入本地AI工具集成模块
sys.path.append(str(Path(__file__).parent.parent))
from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
from backend_modules.backend_integration import get_backend_manager
from main import (
    ModelRegistry, GenerationTask, EnvironmentManager, 
    ComfyUICompatibility, GGUFCompatibility,
    LocalLLMTranslator, TaskScheduler
)

# FastAPI应用初始化
app = FastAPI(
    title="AIGC本地API服务",
    description="替代Supabase的完整本地化后端服务",
    version="5.4.0"
)

# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全配置
SECRET_KEY = "aigc_local_secret_key_2024"
ALGORITHM = "HS256"

# 数据库初始化
DB_PATH = Path(__file__).parent / "database" / "aigc.db"
DB_PATH.parent.mkdir(exist_ok=True)

# 文件存储路径
STORAGE_PATH = Path(__file__).parent / "storage"
STORAGE_PATH.mkdir(exist_ok=True)

# 全局组件初始化
model_registry = ModelRegistry()
environment_manager = EnvironmentManager()
comfyui_webui_integration = ComfyUIWebUIIntegration()
task_scheduler = TaskScheduler(max_concurrent=2)
active_generations = {}  # 存储活跃的生成任务

# ==================== 数据库工具 ====================

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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # 项目表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            module_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # 生成任务表
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
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (project_id) REFERENCES projects (id)
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
    
    # 优化预设表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS optimization_presets (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            module_type TEXT NOT NULL,
            settings TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# ==================== 认证工具 ====================

def create_access_token(data: dict):
    """创建JWT token"""
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """验证JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="无效的token")

# ==================== AI生成相关API ====================

@app.post("/api/ai-generation")
async def start_generation(
    background_tasks: BackgroundTasks,
    module_type: str = Form(...),
    prompt: str = Form(...),
    negative_prompt: str = Form(None),
    model_config: str = Form(...),
    parameters: str = Form(...),
    project_id: str = Form(None),
    user_info: dict = Depends(verify_token)
):
    """开始AI生成任务"""
    try:
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 解析参数
        model_config_dict = json.loads(model_config)
        parameters_dict = json.loads(parameters)
        
        # 创建GenerationTask对象
        task = GenerationTask(
            task_id=task_id,
            task_type=module_type,
            prompt=prompt,
            negative_prompt=negative_prompt or "",
            model_name=model_config_dict.get("name", "default"),
            parameters=parameters_dict,
            project_id=project_id
        )
        
        # 存储任务信息
        active_generations[task_id] = task
        
        # 添加到数据库
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO generation_tasks (
                id, user_id, project_id, module_type, prompt, negative_prompt,
                model_config, parameters, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            task_id, user_info["user_id"], project_id, module_type, prompt,
            negative_prompt, model_config, parameters, "pending", 
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        # 后台执行生成任务
        background_tasks.add_task(execute_generation_task, task_id, task)
        
        return {
            "success": True,
            "data": {
                "generationId": task_id,
                "status": "pending"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动生成任务失败: {str(e)}")

async def execute_generation_task(task_id: str, task: GenerationTask):
    """执行生成任务"""
    try:
        # 更新任务状态为处理中
        active_generations[task_id].status = "processing"
        update_task_status(task_id, "processing", 0)
        
        # 获取后端管理器
        backend_manager = get_backend_manager()
        
        # 根据任务类型执行不同的生成逻辑
        if task.task_type == "image-gen":
            result = await execute_image_generation(task)
        elif task.task_type == "image-edit":
            result = await execute_image_editing(task)
        elif task.task_type == "video-gen":
            result = await execute_video_generation(task)
        elif task.task_type == "3d-gen":
            result = await execute_3d_generation(task)
        else:
            raise ValueError(f"不支持的任务类型: {task.task_type}")
        
        # 更新任务状态为完成
        active_generations[task_id].status = "completed"
        active_generations[task_id].result_files = result
        update_task_status(task_id, "completed", 100, result)
        
    except Exception as e:
        # 更新任务状态为失败
        active_generations[task_id].status = "failed"
        active_generations[task_id].error_message = str(e)
        update_task_status(task_id, "failed", 0, None, str(e))

async def execute_image_generation(task: GenerationTask) -> List[str]:
    """执行图像生成"""
    # 使用现有的模型注册表
    model_config = model_registry.get_model(task.model_name)
    
    if not model_config:
        raise ValueError(f"模型未找到: {task.model_name}")
    
    # 构建生成配置
    from main import GenerationConfig
    
    config = GenerationConfig(
        model_path=model_config.path,
        model_type=model_config.type,
        task_type="text2image",
        txt_folder="",  # 使用直接prompt
        pos_prompt_1=task.prompt,
        neg_prompt=task.negative_prompt,
        output_folder=str(STORAGE_PATH / "outputs"),
        **task.parameters
    )
    
    # 使用环境管理器执行生成
    from main import EngineFactory
    
    engine = EngineFactory.create_engine(config)
    if not engine:
        raise ValueError("无法创建生成引擎")
    
    # 执行生成
    result = engine.generate(config)
    
    # 返回生成的文件路径
    output_files = []
    if hasattr(result, 'images') and result.images:
        for img_path in result.images:
            output_files.append(str(img_path))
    
    return output_files

async def execute_image_editing(task: GenerationTask) -> List[str]:
    """执行图像编辑"""
    # 图像编辑逻辑（Img2Img, Inpainting等）
    # 这里可以集成现有的图像编辑功能
    pass

async def execute_video_generation(task: GenerationTask) -> List[str]:
    """执行视频生成"""
    # 视频生成逻辑
    # 这里可以集成现有的视频生成功能
    pass

async def execute_3d_generation(task: GenerationTask) -> List[str]:
    """执行3D生成"""
    # 3D生成逻辑
    # 这里可以集成现有的3D生成功能
    pass

def update_task_status(task_id: str, status: str, progress: float, 
                     output_files: List[str] = None, error_message: str = None):
    """更新任务状态到数据库"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        update_data = {
            "status": status,
            "progress": progress
        }
        
        if status == "completed":
            update_data["completed_at"] = datetime.now().isoformat()
            update_data["output_files"] = json.dumps(output_files or [])
        elif status == "failed":
            update_data["error_message"] = error_message
            update_data["completed_at"] = datetime.now().isoformat()
        
        # 构建更新SQL
        set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
        values = list(update_data.values()) + [task_id]
        
        cursor.execute(f'''
            UPDATE generation_tasks 
            SET {set_clause}
            WHERE id = ?
        ''', values)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"更新任务状态失败: {e}")

@app.get("/api/generation-status")
async def get_generation_status(
    id: Optional[str] = None,
    module_type: Optional[str] = None,
    status: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    action: Optional[str] = None,
    user_info: dict = Depends(verify_token)
):
    """获取生成任务状态"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 基础查询
        query = '''
            SELECT id, user_id, project_id, module_type, prompt, negative_prompt,
                   model_config, parameters, input_files, output_files, status,
                   progress, created_at, completed_at, error_message
            FROM generation_tasks 
            WHERE user_id = ?
        '''
        params = [user_info["user_id"]]
        
        # 添加过滤条件
        if id:
            query += " AND id = ?"
            params.append(id)
        if module_type:
            query += " AND module_type = ?"
            params.append(module_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        
        # 添加排序和分页
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # 转换结果
        tasks = []
        for row in rows:
            task = {
                "id": row[0],
                "user_id": row[1],
                "project_id": row[2],
                "module_type": row[3],
                "prompt": row[4],
                "negative_prompt": row[5],
                "model_config": json.loads(row[6]) if row[6] else {},
                "parameters": json.loads(row[7]) if row[7] else {},
                "input_files": json.loads(row[8]) if row[8] else [],
                "output_files": json.loads(row[9]) if row[9] else [],
                "status": row[10],
                "progress": row[11],
                "created_at": row[12],
                "completed_at": row[13],
                "error_message": row[14],
                "canRetry": row[10] in ["failed"],
                "canCancel": row[10] in ["pending", "processing"]
            }
            tasks.append(task)
        
        conn.close()
        
        if action == "stats":
            # 返回统计信息
            return {
                "success": True,
                "stats": {
                    "total": len(tasks),
                    "pending": len([t for t in tasks if t["status"] == "pending"]),
                    "processing": len([t for t in tasks if t["status"] == "processing"]),
                    "completed": len([t for t in tasks if t["status"] == "completed"]),
                    "failed": len([t for t in tasks if t["status"] == "failed"])
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取生成状态失败: {str(e)}")

@app.delete("/api/generation-status")
async def cancel_generation(
    generationId: str,
    user_info: dict = Depends(verify_token)
):
    """取消生成任务"""
    try:
        if generationId in active_generations:
            active_generations[generationId].status = "cancelled"
            update_task_status(generationId, "cancelled", 0)
            del active_generations[generationId]
        
        return {
            "success": True,
            "message": "任务已取消"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")

@app.post("/api/generation-status")
async def retry_generation(
    generationId: str,
    user_info: dict = Depends(verify_token)
):
    """重试生成任务"""
    try:
        # 获取原任务信息
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT module_type, prompt, negative_prompt, model_config, parameters
            FROM generation_tasks WHERE id = ? AND user_id = ?
        ''', (generationId, user_info["user_id"]))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="任务未找到")
        
        # 创建新任务
        new_task_id = str(uuid.uuid4())
        model_config_dict = json.loads(row[3])
        parameters_dict = json.loads(row[4])
        
        # 重用原始逻辑创建新任务
        await start_generation(
            module_type=row[0],
            prompt=row[1],
            negative_prompt=row[2],
            model_config=json.dumps(model_config_dict),
            parameters=json.dumps(parameters_dict),
            user_info=user_info
        )
        
        return {
            "success": True,
            "message": "重试任务已创建"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")

# ==================== 模型管理API ====================

@app.get("/api/model-management")
async def model_management(
    action: str,
    module_type: Optional[str] = None,
    user_info: dict = Depends(verify_token)
):
    """模型管理相关API"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if action == "list":
            # 获取用户模型列表
            cursor.execute('''
                SELECT id, name, type, path, weight, size, thumbnail, is_active, created_at, description
                FROM model_configs WHERE user_id = ?
            ''', (user_info["user_id"],))
            
            models = []
            for row in cursor.fetchall():
                model = {
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "path": row[3],
                    "weight": row[4],
                    "size": row[5],
                    "thumbnail": row[6],
                    "is_active": bool(row[7]),
                    "created_at": row[8],
                    "description": row[9]
                }
                models.append(model)
            
            return {
                "success": True,
                "data": {
                    "models": models,
                    "count": len(models)
                }
            }
            
        elif action == "lora-list":
            # 获取LoRA模型列表
            cursor.execute('SELECT * FROM lora_models ORDER BY created_at DESC')
            
            loras = []
            for row in cursor.fetchall():
                lora = {
                    "id": row[0],
                    "name": row[1],
                    "category": row[2],
                    "weight": row[3],
                    "description": row[4],
                    "tags": json.loads(row[5]) if row[5] else [],
                    "download_count": row[6],
                    "size": row[7],
                    "thumbnail": row[8],
                    "author": row[9],
                    "version": row[10],
                    "created_at": row[11],
                    "updated_at": row[12]
                }
                loras.append(lora)
            
            return {"success": True, "data": {"loras": loras}}
            
        elif action == "samplers":
            # 获取采样器列表
            samplers = [
                {"id": "dpmpp_2m", "name": "DPM++ 2M", "description": "快速稳定", "speed": "fast", "quality": "high", "memory_usage": "medium"},
                {"id": "dpmpp_2m_sde", "name": "DPM++ 2M SDE", "description": "高质量SDE", "speed": "medium", "quality": "high", "memory_usage": "high"},
                {"id": "euler", "name": "Euler", "description": "简单快速", "speed": "fast", "quality": "standard", "memory_usage": "low"},
                {"id": "euler_a", "name": "Euler Ancestral", "description": "更创意", "speed": "fast", "quality": "standard", "memory_usage": "low"},
                {"id": "lcm", "name": "LCM", "description": "潜在一致性模型", "speed": "fast", "quality": "draft", "memory_usage": "low"}
            ]
            return {"success": True, "data": {"samplers": samplers}}
            
        elif action == "schedulers":
            # 获取调度器列表
            schedulers = [
                {"id": "simple", "name": "Simple", "description": "标准调度器", "type": "simple", "stability": "medium"},
                {"id": "karras", "name": "Karras", "description": "Karras噪声调度", "type": "karras", "stability": "high"},
                {"id": "exponential", "name": "Exponential", "description": "指数衰减", "type": "exponential", "stability": "medium"}
            ]
            return {"success": True, "data": {"schedulers": schedulers}}
            
        elif action == "aspect-ratios":
            # 获取宽高比列表
            aspect_ratios = [
                {"id": "1:1", "name": "1:1 (512×512)", "width": 512, "height": 512, "category": "square", "megapixels": 0.26, "usage_frequency": 85},
                {"id": "4:3", "name": "4:3 (640×480)", "width": 640, "height": 480, "category": "landscape", "megapixels": 0.31, "usage_frequency": 70},
                {"id": "3:2", "name": "3:2 (768×512)", "width": 768, "height": 512, "category": "landscape", "megapixels": 0.39, "usage_frequency": 75},
                {"id": "16:9", "name": "16:9 (768×432)", "width": 768, "height": 432, "category": "landscape", "megapixels": 0.33, "usage_frequency": 80},
                {"id": "9:16", "name": "9:16 (512×896)", "width": 512, "height": 896, "category": "portrait", "megapixels": 0.46, "usage_frequency": 90}
            ]
            return {"success": True, "data": {"aspectRatios": aspect_ratios}}
            
        conn.close()
        return {"success": False, "error": "不支持的操作"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型管理操作失败: {str(e)}")

@app.post("/api/model-management")
async def upload_model(
    file: UploadFile = File(...),
    type: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    user_info: dict = Depends(verify_token)
):
    """上传模型文件"""
    try:
        # 生成模型ID
        model_id = str(uuid.uuid4())
        
        # 保存文件
        file_extension = Path(file.filename).suffix
        file_path = STORAGE_PATH / "models" / f"{model_id}{file_extension}"
        file_path.parent.mkdir(exist_ok=True)
        
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # 保存到数据库
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO model_configs (
                id, user_id, name, type, path, size, is_active, created_at, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model_id, user_info["user_id"], name, type, str(file_path),
            f"{len(content) / (1024*1024):.2f}MB", True,
            datetime.now().isoformat(), description
        ))
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "data": {
                "model": {
                    "id": model_id,
                    "name": name,
                    "type": type,
                    "path": str(file_path),
                    "size": f"{len(content) / (1024*1024):.2f}MB"
                }
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传模型失败: {str(e)}")

# ==================== 文件处理API ====================

@app.post("/api/file-processor")
async def process_file(
    action: str,
    file: UploadFile = File(None),
    bucket: str = Form(None),
    folder: str = Form(None),
    project_id: str = Form(None),
    user_info: dict = Depends(verify_token)
):
    """文件处理API"""
    try:
        if action == "upload" and file:
            # 上传文件
            file_id = str(uuid.uuid4())
            file_extension = Path(file.filename).suffix
            
            # 确定存储路径
            bucket_path = STORAGE_PATH / (bucket or "uploads")
            bucket_path.mkdir(exist_ok=True)
            
            if folder:
                bucket_path = bucket_path / folder
                bucket_path.mkdir(parents=True, exist_ok=True)
            
            file_path = bucket_path / f"{file_id}{file_extension}"
            
            # 保存文件
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # 返回文件信息
            file_url = f"/api/files/{file_id}"
            file_info = {
                "id": file_id,
                "name": file.filename,
                "size": len(content),
                "type": file.content_type,
                "path": str(file_path),
                "url": file_url,
                "created_at": datetime.now().isoformat()
            }
            
            return {
                "success": True,
                "data": {
                    "file": file_info,
                    "url": file_url
                }
            }
            
        return {"success": False, "error": "不支持的操作"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")

@app.get("/api/files/{file_id}")
async def download_file(file_id: str):
    """下载文件"""
    try:
        # 查找文件
        for file_path in STORAGE_PATH.rglob(f"{file_id}.*"):
            return FileResponse(
                path=file_path,
                filename=file_path.name,
                media_type='application/octet-stream'
            )
        
        raise HTTPException(status_code=404, detail="文件未找到")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载文件失败: {str(e)}")

# ==================== 用户认证API ====================

@app.post("/api/auth/signup")
async def signup(username: str, email: str, password: str):
    """用户注册"""
    try:
        # 检查用户是否已存在
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ? OR username = ?', (email, username))
        
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="用户已存在")
        
        # 创建用户
        user_id = str(uuid.uuid4())
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        cursor.execute('''
            INSERT INTO users (id, username, email, password_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id, username, email, password_hash,
            datetime.now().isoformat(), datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        
        # 创建token
        token = create_access_token({"user_id": user_id, "username": username})
        
        return {
            "success": True,
            "data": {
                "user": {
                    "id": user_id,
                    "username": username,
                    "email": email
                },
                "token": token
            },
            "message": "注册成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")

@app.post("/api/auth/signin")
async def signin(email: str, password: str):
    """用户登录"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, username, email, password_hash
            FROM users WHERE email = ?
        ''', (email,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row or not bcrypt.checkpw(password.encode('utf-8'), row[3].encode('utf-8')):
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        
        # 创建token
        token = create_access_token({"user_id": row[0], "username": row[1]})
        
        return {
            "success": True,
            "data": {
                "user": {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2]
                },
                "token": token
            },
            "message": "登录成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")

# ==================== 应用启动 ====================

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    print("🚀 启动AIGC本地API服务器...")
    
    # 初始化数据库
    init_database()
    print("✅ 数据库初始化完成")
    
    # 检查环境
    environment_manager.print_environment_info()
    
    # 启动任务调度器
    print("✅ 任务调度器已启动")

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时的清理"""
    print("🛑 正在关闭AIGC本地API服务器...")
    
    # 停止所有活跃任务
    for task_id, task in active_generations.items():
        task.status = "cancelled"
    
    print("✅ API服务器已关闭")

if __name__ == "__main__":
    # 创建数据库目录
    DB_PATH.parent.mkdir(exist_ok=True)
    
    # 启动服务器
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )