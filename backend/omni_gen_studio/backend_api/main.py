#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC鎵瑰鐞嗗伐鍏?v5.4 鏈湴API鏈嶅姟鍣?鏇夸唬Supabase Edge Functions锛屾彁渚涘畬鏁寸殑鏈湴鍖栧悗绔湇鍔?"""

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

# 瀵煎叆鏈湴AI宸ュ叿闆嗘垚妯″潡
sys.path.append(str(Path(__file__).parent.parent))
from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
from backend_modules.backend_integration import get_backend_manager
from main import (
    ModelRegistry, GenerationTask, EnvironmentManager, 
    ComfyUICompatibility, GGUFCompatibility,
    LocalLLMTranslator, TaskScheduler
)

# FastAPI搴旂敤鍒濆鍖?

app = FastAPI(
    title="AIGC鏈湴API鏈嶅姟",
    description="鏇夸唬Supabase鐨勫畬鏁存湰鍦板寲鍚庣鏈嶅姟",
    version="5.4.0"
)

# CORS璁剧疆
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 瀹夊叏閰嶇疆
SECRET_KEY = "aigc_local_secret_key_2024"
ALGORITHM = "HS256"

# 鏁版嵁搴撳垵濮嬪寲
DB_PATH = Path(__file__).parent / "database" / "aigc.db"
DB_PATH.parent.mkdir(exist_ok=True)

# 鏂囦欢瀛樺偍璺緞
STORAGE_PATH = Path(__file__).parent / "storage"
STORAGE_PATH.mkdir(exist_ok=True)

# 鍏ㄥ眬缁勪欢鍒濆鍖?model_registry = ModelRegistry()
environment_manager = EnvironmentManager()
comfyui_webui_integration = ComfyUIWebUIIntegration()
task_scheduler = TaskScheduler(max_concurrent=2)
active_generations = {}  # 瀛樺偍娲昏穬鐨勭敓鎴愪换鍔?
# ==================== 鏁版嵁搴撳伐鍏?====================

def init_database():
    """鍒濆鍖朣QLite鏁版嵁搴?""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 鐢ㄦ埛琛?    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    
    # 椤圭洰琛?    cursor.execute('''
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
    
    # 鐢熸垚浠诲姟琛?    cursor.execute('''
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
    
    # 妯″瀷閰嶇疆琛?    cursor.execute('''
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
    
    # LoRA妯″瀷琛?    cursor.execute('''
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
    
    # 鍙傛暟棰勮琛?    cursor.execute('''
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
    
    # 浼樺寲棰勮琛?    cursor.execute('''
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

# ==================== 璁よ瘉宸ュ叿 ====================

def create_access_token(data: dict):
    """鍒涘缓JWT token"""
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    """楠岃瘉JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="鏃犳晥鐨則oken")

# ==================== AI鐢熸垚鐩稿叧API ====================

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
    """开启AI生成任务"""
    try:
        # 鐢熸垚浠诲姟ID
        task_id = str(uuid.uuid4())
        
        # 瑙ｆ瀽鍙傛暟
        model_config_dict = json.loads(model_config)
        parameters_dict = json.loads(parameters)
        
        # 鍒涘缓GenerationTask瀵硅薄
        task = GenerationTask(
            task_id=task_id,
            task_type=module_type,
            prompt=prompt,
            negative_prompt=negative_prompt or "",
            model_name=model_config_dict.get("name", "default"),
            parameters=parameters_dict,
            project_id=project_id
        )
        
        # 瀛樺偍浠诲姟淇℃伅
        active_generations[task_id] = task
        
        # 娣诲姞鍒版暟鎹簱
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
        
        # 鍚庡彴鎵ц鐢熸垚浠诲姟
        background_tasks.add_task(execute_generation_task, task_id, task)
        
        return {
            "success": True,
            "data": {
                "generationId": task_id,
                "status": "pending"
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"鍚姩鐢熸垚浠诲姟澶辫触: {str(e)}")

async def execute_generation_task(task_id: str, task: GenerationTask):
    """鎵ц鐢熸垚浠诲姟"""
    try:
        # 鏇存柊浠诲姟鐘舵佷负澶勭悊涓?        active_generations[task_id].status = "processing"
        update_task_status(task_id, "processing", 0)
        
        # 鑾峰彇鍚庣绠＄悊鍣?        backend_manager = get_backend_manager()
        
    """执行生成任务"""
        if task.task_type == "image-gen":
            result = await execute_image_generation(task)
        elif task.task_type == "image-edit":
            result = await execute_image_editing(task)
        elif task.task_type == "video-gen":
            result = await execute_video_generation(task)
        elif task.task_type == "3d-gen":
            result = await execute_3d_generation(task)
        else:
            raise ValueError(f"涓嶆敮鎸佺殑浠诲姟绫诲瀷: {task.task_type}")
        
        # 鏇存柊浠诲姟鐘舵佷负瀹屾垚
        active_generations[task_id].status = "completed"
        active_generations[task_id].result_files = result
        update_task_status(task_id, "completed", 100, result)
        
    except Exception as e:
        # 鏇存柊浠诲姟鐘舵佷负澶辫触
        active_generations[task_id].status = "failed"
        active_generations[task_id].error_message = str(e)
        update_task_status(task_id, "failed", 0, None, str(e))

async def execute_image_generation(task: GenerationTask) -> List[str]:
    """鎵ц鍥惧儚鐢熸垚"""
    # 浣跨敤鐜版湁鐨勬ā鍨嬫敞鍐岃〃
    model_config = model_registry.get_model(task.model_name)
    
    if not model_config:
        raise ValueError(f"妯″瀷鏈壘鍒? {task.model_name}")
    
    # 鏋勫缓鐢熸垚閰嶇疆
    from main import GenerationConfig
    
    config = GenerationConfig(
        model_path=model_config.path,
        model_type=model_config.type,
        task_type="text2image",
        txt_folder="",  # 浣跨敤鐩存帴prompt
        pos_prompt_1=task.prompt,
        neg_prompt=task.negative_prompt,
        output_folder=str(STORAGE_PATH / "outputs"),
        **task.parameters
    )
    
    # 浣跨敤鐜绠＄悊鍣ㄦ墽琛岀敓鎴?    from main import EngineFactory
    
    engine = EngineFactory.create_engine(config)
    if not engine:
        raise ValueError("鏃犳硶鍒涘缓鐢熸垚寮曟搸")
    
    # 鎵ц鐢熸垚
    result = engine.generate(config)
    
    # 杩斿洖鐢熸垚鐨勬枃浠惰矾寰?    output_files = []
    if hasattr(result, 'images') and result.images:
        for img_path in result.images:
            output_files.append(str(img_path))
    
    return output_files

async def execute_image_editing(task: GenerationTask) -> List[str]:
    """鎵ц鍥惧儚缂栬緫"""
    # 鍥惧儚缂栬緫閫昏緫锛圛mg2Img, Inpainting绛夛級
    # 杩欓噷鍙互闆嗘垚鐜版湁鐨勫浘鍍忕紪杈戝姛鑳?    pass

async def execute_video_generation(task: GenerationTask) -> List[str]:
    """鎵ц瑙嗛鐢熸垚"""
    # 瑙嗛鐢熸垚閫昏緫
    # 杩欓噷鍙互闆嗘垚鐜版湁鐨勮棰戠敓鎴愬姛鑳?    pass

async def execute_3d_generation(task: GenerationTask) -> List[str]:
    """鎵ц3D鐢熸垚"""
    # 3D鐢熸垚閫昏緫
    # 杩欓噷鍙互闆嗘垚鐜版湁鐨?D鐢熸垚鍔熻兘
    pass

def update_task_status(task_id: str, status: str, progress: float, 
                     output_files: List[str] = None, error_message: str = None):
    """鏇存柊浠诲姟鐘舵佸埌鏁版嵁搴?""
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
        
        # 鏋勫缓鏇存柊SQL
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
        print(f"鏇存柊浠诲姟鐘舵佸け璐? {e}")

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
    """生成任务"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 鍩虹鏌ヨ
        query = '''
            SELECT id, user_id, project_id, module_type, prompt, negative_prompt,
                   model_config, parameters, input_files, output_files, status,
                   progress, created_at, completed_at, error_message
            FROM generation_tasks 
            WHERE user_id = ?
        '''
        params = [user_info["user_id"]]
        
        # 娣诲姞杩囨护鏉′欢
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
        
        # 娣诲姞鎺掑簭鍜屽垎椤?        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # 杞崲缁撴灉
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
            # 杩斿洖缁熻淇℃伅
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
        raise HTTPException(status_code=500, detail=f"鑾峰彇鐢熸垚鐘舵佸け璐? {str(e)}")

@app.delete("/api/generation-status")
async def cancel_generation(
    generationId: str,
    user_info: dict = Depends(verify_token)
):
    """鍙栨秷鐢熸垚浠诲姟"""
    try:
        if generationId in active_generations:
            active_generations[generationId].status = "cancelled"
            update_task_status(generationId, "cancelled", 0)
            del active_generations[generationId]
        
        return {
            "success": True,
            "message": "任务已取消\n",
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"鍙栨秷浠诲姟澶辫触: {str(e)}")

@app.post("/api/generation-status")
async def retry_generation(
    generationId: str,
    user_info: dict = Depends(verify_token)
):
    """閲嶈瘯鐢熸垚浠诲姟"""
    try:
        # 鑾峰彇鍘熶换鍔′俊鎭?        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT module_type, prompt, negative_prompt, model_config, parameters
            FROM generation_tasks WHERE id = ? AND user_id = ?
        ''', (generationId, user_info["user_id"]))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise HTTPException(status_code=404, detail="\xe4\xbb\xa5\xe5\x8a\xa1\xe6\x9c\xaa\xe6\x89\xbe\xe5\x88\xb0"
        
        # 鍒涘缓鏂颁换鍔?        new_task_id = str(uuid.uuid4())
        model_config_dict = json.loads(row[3])
        parameters_dict = json.loads(row[4])
        
        # 閲嶇敤鍘熷閫昏緫鍒涘缓鏂颁换鍔?        await start_generation(
            module_type=row[0],
            prompt=row[1],
            negative_prompt=row[2],
            model_config=json.dumps(model_config_dict),
            parameters=json.dumps(parameters_dict),
            user_info=user_info
        )
        
        return {
            "success": True,
            "message": "閲嶈瘯浠诲姟宸插垱寤"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"閲嶈瘯浠诲姟澶辫触: {str(e)}")

# ==================== 妯″瀷绠＄悊API ====================

@app.get("/api/model-management")
async def model_management(
    action: str,
    module_type: Optional[str] = None,
    user_info: dict = Depends(verify_token)
):
    """妯″瀷绠＄悊鐩稿叧API"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if action == "list":
            # 鑾峰彇鐢ㄦ埛妯″瀷鍒楄〃
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
            # 鑾峰彇LoRA妯″瀷鍒楄〃
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
            # 鑾峰彇閲囨牱鍣ㄥ垪琛?            samplers = [
                {"id": "dpmpp_2m", "name": "DPM++ 2M", "description": "速度快", "speed": "fast", "quality": "high", "memory_usage": "medium"},
                {"id": "dpmpp_2m_sde", "name": "DPM++ 2M SDE", "description": "楂樿川閲廠DE", "speed": "medium", "quality": "high", "memory_usage": "high"},
                {"id": "euler", "name": "Euler", "description": "简单快速", "speed": "fast", "quality": "standard", "memory_usage": "low"},
                {"id": "euler_a", "name": "Euler Ancestral", "description": "更多创意", "speed": "fast", "quality": "standard", "memory_usage": "low"},
                {"id": "dpm_2", "name": "DPM 2", "description": "存在一致性", "speed": "medium", "quality": "high", "memory_usage": "medium"},
                {"id": "ddim", "name": "DDIM", "description": "标准调度器", "type": "deterministic", "quality": "high", "memory_usage": "medium"},
            return {"success": True, "data": {"samplers": samplers}}
            
        elif action == "schedulers":
            # 鑾峰彇璋冨害鍣ㄥ垪琛?            schedulers = [
                {"id": "simple", "name": "Simple", "description": "鏍囧噯璋冨害鍣", "type: "simple", "stability": "medium"},
                {"id": "karras", "name": "Karras", "description": "Karras鍣０璋冨害", "type": "karras", "stability": "high"},
                {"id": "exponential", "name": "Exponential", "description": "鎸囨暟琛板噺", "type": "exponential", "stability": "medium"}
            ]
            return {"success": True, "data": {"schedulers": schedulers}}
            
        elif action == "aspect-ratios":
            # 鑾峰彇瀹介珮姣斿垪琛?            aspect_ratios = [
                {"id": "1:1", "name": "1:1 (512脳512)", "width": 512, "height": 512, "category": "square", "megapixels": 0.26, "usage_frequency": 85},
                {"id": "4:3", "name": "4:3 (640脳480)", "width": 640, "height": 480, "category": "landscape", "megapixels": 0.31, "usage_frequency": 70},
                {"id": "3:2", "name": "3:2 (768脳512)", "width": 768, "height": 512, "category": "landscape", "megapixels": 0.39, "usage_frequency": 75},
                {"id": "16:9", "name": "16:9 (768脳432)", "width": 768, "height": 432, "category": "landscape", "megapixels": 0.33, "usage_frequency": 80},
                {"id": "9:16", "name": "9:16 (512脳896)", "width": 512, "height": 896, "category": "portrait", "megapixels": 0.46, "usage_frequency": 90}
            ]
            return {"success": True, "data": {"aspectRatios": aspect_ratios}}
            
        conn.close()
        return {"success": False, "error": "涓嶆敮鎸佺殑鎿嶄綔"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"妯″瀷绠＄悊鎿嶄綔澶辫触: {str(e)}")

@app.post("/api/model-management")
async def upload_model(
    file: UploadFile = File(...),
    type: str = Form(...),
    name: str = Form(...),
    description: str = Form(None),
    user_info: dict = Depends(verify_token)
):
    """涓婁紶妯″瀷鏂囦欢"""
    try:
        # 鐢熸垚妯″瀷ID
        model_id = str(uuid.uuid4())
        
        # 淇濆瓨鏂囦欢
        file_extension = Path(file.filename).suffix
        file_path = STORAGE_PATH / "models" / f"{model_id}{file_extension}"
        file_path.parent.mkdir(exist_ok=True)
        
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # 淇濆瓨鍒版暟鎹簱
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
        raise HTTPException(status_code=500, detail=f"涓婁紶妯″瀷澶辫触: {str(e)}")

# ==================== 鏂囦欢澶勭悊API ====================

@app.post("/api/file-processor")
async def process_file(
    action: str,
    file: UploadFile = File(None),
    bucket: str = Form(None),
    folder: str = Form(None),
    project_id: str = Form(None),
    user_info: dict = Depends(verify_token)
):
    """鏂囦欢澶勭悊API"""
    try:
        if action == "upload" and file:
            # 涓婁紶鏂囦欢
            file_id = str(uuid.uuid4())
            file_extension = Path(file.filename).suffix
            
            # 纭畾瀛樺偍璺緞
            bucket_path = STORAGE_PATH / (bucket or "uploads")
            bucket_path.mkdir(exist_ok=True)
            
            if folder:
                bucket_path = bucket_path / folder
                bucket_path.mkdir(parents=True, exist_ok=True)
            
            file_path = bucket_path / f"{file_id}{file_extension}"
            
            # 淇濆瓨鏂囦欢
            async with aiofiles.open(file_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            # 杩斿洖鏂囦欢淇℃伅
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
            
        return {"success": False, "error": "涓嶆敮鎸佺殑鎿嶄綔"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"鏂囦欢澶勭悊澶辫触: {str(e)}")

@app.get("/api/files/{file_id}")
async def download_file(file_id: str):
    """涓嬭浇鏂囦欢"""
    try:
        # 鏌ユ壘鏂囦欢
        for file_path in STORAGE_PATH.rglob(f"{file_id}.*"):
            return FileResponse(
                path=file_path,
                filename=file_path.name,
                media_type='application/octet-stream'
            )
        
        raise HTTPException(status_code=404, detail="\xe4\xbb\xa5\xe5\x8a\xa1\xe6\x9c\xaa\xe6\x89\xbe\xe5\x88\xb0"
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"涓嬭浇鏂囦欢澶辫触: {str(e)}")

# ==================== 鐢ㄦ埛璁よ瘉API ====================

@app.post("/api/auth/signup")
async def signup(username: str, email: str, password: str):
    """鐢ㄦ埛娉ㄥ唽"""
    try:
        # 妫鏌ョ敤鎴锋槸鍚﹀凡瀛樺湪
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM users WHERE email = ? OR username = ?', (email, username))
        
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="鐢ㄦ埛宸插瓨鍦?)
        
        # 鍒涘缓鐢ㄦ埛
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
        
        # 鍒涘缓token
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
            "message": "娉ㄥ唽鎴愬姛"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"娉ㄥ唽澶辫触: {str(e)}")

@app.post("/api/auth/signin")
async def signin(email: str, password: str):
    """鐢ㄦ埛鐧诲綍"""
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
            raise HTTPException(status_code=401, detail="閭鎴栧瘑鐮侀敊璇?)
        
        # 鍒涘缓token
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
            "message": "鐧诲綍鎴愬姛"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"鐧诲綍澶辫触: {str(e)}")

# ==================== 搴旂敤鍚姩 ====================

@app.on_event("startup")
async def startup_event():
    """搴旂敤鍚姩鏃剁殑鍒濆鍖?""
    print("馃殌 鍚姩AIGC鏈湴API鏈嶅姟鍣?..")
    
    # 鍒濆鍖栨暟鎹簱
    init_database()
    print("鉁?鏁版嵁搴撳垵濮嬪寲瀹屾垚")
    
    # 妫鏌ョ幆澧?    environment_manager.print_environment_info()
    
    # 鍚姩浠诲姟璋冨害鍣?    print("鉁?浠诲姟璋冨害鍣ㄥ凡鍚姩")

# ==================== 鏁版嵁鏍囨敞绯荤粺 API ====================

@app.on_event("startup")
async def init_annotation_system():
    """鍒濆鍖栨爣娉ㄧ郴缁?""
    try:
        # 寤惰繜瀵煎叆閬垮厤寰幆渚濊禆
        import sys
        sys.path.append(str(Path(__file__).parent.parent.parent.parent))
        from backend.database_manager import get_annotation_manager, ANNOTATION_SYSTEM_AVAILABLE
        if ANNOTATION_SYSTEM_AVAILABLE:
            print("鉁?鏁版嵁鏍囨敞绯荤粺宸插姞杞?)
        else:
# print("鈿狅笍 鏁版嵁鏍囨敞绯荤粺妯″潡鏈壘鍒帮紝閮ㄥ垎鍔熻兘涓嶅彲鐢?)
    except Exception as e:
        print(f"鈿狅笍 鏍囨敞绯荤粺鍒濆鍖栧け璐? {e}")


@app.post("/api/annotation/projects")
async def create_annotation_project(
    name: str,
    description: str = None,
    created_by: str = None
):
    """鍒涘缓鏍囨敞椤圭洰"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            project_id = manager.create_project(
                name=name,
                description=description,
                created_by=created_by
            )
            return {"success": True, "data": {"project_id": project_id}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/projects")
async def list_annotation_projects(include_completed: bool = False):
    """鍒楀嚭鏍囨敞椤圭洰"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            projects = manager.list_projects(include_completed=include_completed)
            return {
                "success": True,
                "data": {
                    "projects": [
                        {
                            "project_id": p.project_id,
                            "name": p.name,
                            "description": p.description,
                            "status": p.status,
                            "created_at": p.created_at.isoformat() if p.created_at else None,
                        }
                        for p in projects
                    ]
                }
            }
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/images")
async def add_annotation_image(
    image_path: str,
    image_type: str = "single_image",
    source: str = "user_upload",
    project_id: str = None,
    created_by: str = None,
    parent_image_id: str = None
):
    """娣诲姞鍥剧墖鍒版爣娉ㄧ郴缁?""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            image_id = manager.add_image(
                image_path=image_path,
                image_type=image_type,
                source=source,
                project_id=project_id,
                created_by=created_by,
                parent_image_id=parent_image_id,
            )
            return {"success": True, "data": {"image_id": image_id}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/images/{image_id}")
async def get_annotation_image(image_id: str):
    """鑾峰彇鍥剧墖璇︽儏"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            image = manager.get_image(image_id)
            if image:
                return {
                    "success": True,
                    "data": {
                        "image_id": image.image_id,
                        "image_path": image.image_path,
                        "image_type": image.image_type,
                        "status": image.status,
                        "created_at": image.created_at.isoformat() if image.created_at else None,
                    }
                }
            return {"success": False, "error": "鍥剧墖涓嶅瓨鍦?}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/images")
async def list_annotation_images(
    project_id: str = None,
    image_type: str = None,
    status: str = None,
    limit: int = 100,
    offset: int = 0
):
    """鍒楀嚭鍥剧墖"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            images = manager.list_images(
                project_id=project_id,
                image_type=image_type,
                status=status,
                limit=limit,
                offset=offset,
            )
            return {
                "success": True,
                "data": {
                    "images": [
                        {
                            "image_id": img.image_id,
                            "image_path": img.image_path,
                            "image_type": img.image_type,
                            "status": img.status,
                        }
                        for img in images
                    ]
                }
            }
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/annotations")
async def add_annotation(
    image_id: str,
    annotation_type: str,
    label: str,
    coordinates: str,  # JSON string
    annotator: str,
    category_id: str = None,
    confidence: float = None
):
    """娣诲姞鏍囨敞"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            coords = json.loads(coordinates) if isinstance(coordinates, str) else coordinates
            annotation_id = manager.add_annotation(
                image_id=image_id,
                annotation_type=annotation_type,
                label=label,
                coordinates=coords,
                annotator=annotator,
                category_id=category_id,
                confidence=confidence,
            )
            return {"success": True, "data": {"annotation_id": annotation_id}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/images/{image_id}/annotations")
async def get_image_annotations(image_id: str):
    """鑾峰彇鍥剧墖鐨勬墍鏈夋爣娉?""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            annotations = manager.get_annotations(image_id)
            return {
                "success": True,
                "data": {
                    "annotations": [
                        {
                            "annotation_id": a.annotation_id,
                            "annotation_type": a.annotation_type,
                            "label": a.label,
                            "coordinates": a.coordinates,
                            "status": a.status,
                            "confidence": a.confidence,
                        }
                        for a in annotations
                    ]
                }
            }
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/quality-inspections")
async def add_quality_inspection(
    image_id: str,
    inspector: str,
    result: str,
    defects: str = "[]",  # JSON string
    notes: str = None
):
    """娣诲姞璐ㄩ噺妫鏌?""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            defect_list = json.loads(defects) if isinstance(defects, str) else defects
            inspection_id = manager.add_quality_inspection(
                image_id=image_id,
                inspector=inspector,
                result=result,
                defects=defect_list,
                notes=notes,
            )
            return {"success": True, "data": {"inspection_id": inspection_id}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/statistics")
async def get_annotation_statistics(project_id: str = None):
    """鑾峰彇鏍囨敞缁熻"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            stats = manager.get_statistics(project_id)
            return {"success": True, "data": stats}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/export")
async def export_annotations(
    format_type: str,  # coco, yolo
    project_id: str = None,
    image_ids: str = None,  # comma-separated
    output_path: str = None
):
    """瀵煎嚭鏍囨敞鏁版嵁"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            img_ids = image_ids.split(",") if image_ids else None
            file_path = manager.export_annotations(
                format_type=format_type,
                project_id=project_id,
                image_ids=img_ids,
                output_path=output_path,
            )
            return {"success": True, "data": {"file_path": file_path}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/annotation/images/{image_id}")
async def delete_annotation_image(image_id: str):
    """鍒犻櫎鍥剧墖(杞垹闄?"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            success = manager.soft_delete_image(image_id)
            return {"success": success}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/images/{image_id}/restore")
async def restore_annotation_image(image_id: str):
    """鎭㈠宸插垹闄ゅ浘鐗?""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            success = manager.restore_image(image_id)
            return {"success": success}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/comments")
async def add_annotation_comment(
    image_id: str,
    content: str,
    user: str,
    parent_comment_id: str = None
):
    """娣诲姞璇勮"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            comment_id = manager.add_comment(
                image_id=image_id,
                content=content,
                user=user,
                parent_comment_id=parent_comment_id,
            )
            return {"success": True, "data": {"comment_id": comment_id}}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/tags")
async def add_annotation_tag(
    image_id: str,
    tag_name: str,
    created_by: str
):
    """娣诲姞鏍囩"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            success = manager.add_tag(image_id, tag_name, created_by)
            return {"success": success}
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/annotation/search")
async def search_annotation_images(
    keyword: str = None,
    project_id: str = None,
    tags: str = None,  # comma-separated
    status: str = None,
    limit: int = 100
):
    """鎼滅储鍥剧墖"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            tag_list = tags.split(",") if tags else None
            images = manager.search_images(
                keyword=keyword,
                project_id=project_id,
                tags=tag_list,
                status=status,
                limit=limit,
            )
            return {
                "success": True,
                "data": {
                    "images": [
                        {
                            "image_id": img.image_id,
                            "image_path": img.image_path,
                            "status": img.status,
                        }
                        for img in images
                    ]
                }
            }
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/annotation/batch")
async def batch_add_annotation_images(
    image_paths: str,  # JSON array string
    image_type: str = "single_image",
    source: str = "user_upload",
    project_id: str = None,
    created_by: str = None
):
    """鎵归噺娣诲姞鍥剧墖"""
    try:
        from backend.database_manager import get_annotation_manager
        manager = get_annotation_manager()
        if manager and manager.annotation_manager:
            paths = json.loads(image_paths) if isinstance(image_paths, str) else image_paths
            success_count, failed_ids = manager.batch_add_images(
                image_paths=paths,
                image_type=image_type,
                source=source,
                project_id=project_id,
                created_by=created_by,
            )
            return {
                "success": True,
                "data": {
                    "success_count": success_count,
                    "failed_count": len(failed_ids),
                    "failed_ids": failed_ids,
                }
            }
# return {"success": False, "error": "鏍囨敞绯荤粺涓嶅彲鐢?}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Information Center API ====================

@app.get("/api/info/overview")
async def get_system_overview():
    """鑾峰彇绯荤粺鎬昏淇℃伅"""
    try:
        import psutil
        
        # CPU鍜屽唴瀛?        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        # 纾佺洏淇℃伅
        disk = psutil.disk_usage('/')
        
        # GPU淇℃伅 (灏濊瘯鑾峰彇)
        gpu_info = None
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                gpus = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 6:
                            gpus.append({
                                'index': int(parts[0]),
                                'name': parts[1],
                                'memory_total': float(parts[2]) * 1024 * 1024,
                                'memory_used': float(parts[3]) * 1024 * 1024,
                                'utilization': float(parts[4]),
                                'temperature': float(parts[5])
                            })
                gpu_info = {'gpus': gpus, 'total_count': len(gpus)}
        except:
            pass
        
        # 浠诲姟缁熻 (浠庢暟鎹簱鑾峰彇)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM generation_tasks GROUP BY status")
        task_stats = {'queue': 0, 'running': 0, 'completed': 0, 'failed': 0, 'total': 0}
        for status, count in cursor.fetchall():
            task_stats[status] = count
            task_stats['total'] += count
        
        # 鐢ㄦ埛缁熻 (妯℃嫙)
        user_stats = {'online': 1, 'active': 5, 'total': 10, 'new_today': 2}
        
        # 浼氳瘽缁熻 (妯℃嫙)
        session_stats = {'total': 156, 'today': 24, 'concurrent': 3, 'avg_duration': 1800}
        
        # 妯″瀷鐘舵?(浠庢暟鎹簱鑾峰彇)
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) FROM model_configs")
        model_result = cursor.fetchone()
        model_stats = {
            'loaded': model_result[1] or 0,
            'available': model_result[0] or 0,
            'downloading': 0,
            'total_size': '0GB',
            'models': []
        }
        conn.close()
        
        system_info = {
            'api': {'status': 'online', 'uptime': 99.9, 'latency': 12, 'requests': 15847},
            'gpu': {
                'total': gpu_info['total_count'] if gpu_info else 0,
                'available': gpu_info['total_count'] if gpu_info else 0,
                'memory_total': f"{gpu_info['gpus'][0]['memory_total'] / 1024**3:.1f}GB" if gpu_info and gpu_info['gpus'] else '0GB',
                'memory_used': f"{gpu_info['gpus'][0]['memory_used'] / 1024**3:.1f}GB" if gpu_info and gpu_info['gpus'] else '0GB',
                'utilization': f"{gpu_info['gpus'][0]['utilization']:.0f}%" if gpu_info and gpu_info['gpus'] else '0%',
                'temperature': gpu_info['gpus'][0]['temperature'] if gpu_info and gpu_info['gpus'] else None
            },
            'storage': {
                'used': f"{disk.used / 1024**3:.0f}GB",
                'total': f"{disk.total / 1024**3:.0f}GB",
                'type': 'NVMe SSD',
                'percent': int(disk.percent)
            },
            'memory': {
                'used': f"{memory.used / 1024**3:.1f}GB",
                'total': f"{memory.total / 1024**3:.1f}GB",
                'percent': int(memory.percent)
            },
            'tasks': task_stats,
            'users': user_stats,
            'models': model_stats,
            'sessions': session_stats
        }
        
        stats = {
            'today': {'generations': 247, 'users': 24, 'apiCalls': 4521, 'uptime': 99.9},
            'week': {'generations': 1823, 'users': 156, 'apiCalls': 32145, 'uptime': 99.8},
            'month': {'generations': 8234, 'users': 512, 'apiCalls': 145230, 'uptime': 99.7}
        }
        
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': '5.4.0',
            'uptime': 86400,
            'services': {'api': True, 'database': True, 'gpu': gpu_info is not None, 'storage': True},
            'metrics': {
                'cpu': cpu_percent,
                'memory': memory.percent,
                'disk': disk.percent,
                'gpu_utilization': gpu_info['gpus'][0]['utilization'] if gpu_info and gpu_info['gpus'] else None
            }
        }
        
        return {
            'success': True,
            'data': {
                'system_info': system_info,
                'activity_logs': [],
                'hot_topics': [],
                'stats': stats,
                'health': health
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/system")
async def get_system_info():
    """鑾峰彇绯荤粺淇℃伅"""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # GPU淇℃伅
        gpu_info = {'total': 0, 'available': 0, 'memory_total': '0GB', 'memory_used': '0GB', 'utilization': '0%'}
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,utilization.gpu', '--format=csv,noheader,nounits'], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = [p.strip() for p in lines[0].split(',')]
                    if len(parts) >= 5:
                        gpu_info = {
                            'total': len(lines),
                            'available': len(lines),
                            'memory_total': f"{float(parts[2]) / 1024:.1f}GB",
                            'memory_used': f"{float(parts[3]) / 1024:.1f}GB",
                            'utilization': f"{float(parts[4]):.0f}%"
                        }
        except:
            pass
        
        # 浠诲姟缁熻
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM generation_tasks GROUP BY status")
        task_stats = {'queue': 0, 'running': 0, 'completed': 0, 'failed': 0}
        for status, count in cursor.fetchall():
            if status in task_stats:
                task_stats[status] = count
        conn.close()
        
        return {
            'success': True,
            'data': {
                'api': {'status': 'online', 'uptime': 99.9, 'latency': 12, 'requests': 15847},
                'gpu': gpu_info,
'storage': {'used': f"{disk.used / 1024**3:.0f}GB", 'total': f"{disk.total / 1024**3:.0f}GB", 'type': 'NVMe SSD', 'percent': int(disk.percent)},
                'memory': {'used': f"{memory.used / 1024**3:.1f}GB", 'total': f"{memory.total / 1024**3:.1f}GB", 'percent': int(memory.percent)},
                'tasks': task_stats,
                'users': {'online': 1, 'active': 5, 'total': 10},
                'models': {'loaded': 5, 'available': 10, 'downloading': 0},
                'sessions': {'total': 156, 'today': 24, 'concurrent': 3}
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/activity")
async def get_activity_logs(limit: int = 100, type: str = None):
    """鑾峰彇娲诲姩鏃ュ織"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        query = "SELECT id, created_at as time, status as type, module_type || ': 浠诲姟' as message, user_id as user FROM generation_tasks"
        params = []
        if type:
            query += " WHERE status = ?"
            params.append(type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for i, row in enumerate(rows):
            logs.append({
                'id': i + 1,
                'time': row[1][:19] if row[1] else '',
                'type': row[2] if row[2] in ['success', 'error', 'warning', 'info'] else 'info',
                'message': row[3] or '鏈煡娲诲姩',
                'user': row[4] or 'System',
                'details': None,
                'source': 'task'
            })
        
        return {'success': True, 'data': {'logs': logs, 'total': len(logs)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/hot-topics")
async def get_hot_topics(category: str = None, limit: int = 20):
    """鑾峰彇鐑偣璇濋"""
    try:
        # 妯℃嫙鐑偣璇濋鏁版嵁 (瀹為檯搴斾粠ai_automation.py鑾峰彇)
        topics = [
            {'id': 1, 'topic': 'AI鐢熸垚瑙嗛鎶鏈?, 'trend': 'up', 'heat': 12500, 'category': '鎶鏈?, 'last_update': '鍒氬垰', 'source': '鎶鏈ぞ鍖?, 'related_tags': ['AIGC', '瑙嗛鐢熸垚']},
            {'id': 2, 'topic': 'Claude 4 鍙戝竷', 'trend': 'up', 'heat': 9800, 'category': 'AI', 'last_update': '1灏忔椂鍓?, 'source': 'AI璧勮', 'related_tags': ['Claude', 'Anthropic']},
            {'id': 3, 'topic': 'Live2D 妯″瀷甯傚満', 'trend': 'stable', 'heat': 7600, 'category': '鍒涗綔', 'last_update': '2灏忔椂鍓?, 'source': '鍒涗綔绀惧尯', 'related_tags': ['Live2D', '铏氭嫙褰㈣薄']},
            {'id': 4, 'topic': 'VRM 3D铏氭嫙褰㈣薄', 'trend': 'up', 'heat': 6500, 'category': '鎶鏈?, 'last_update': '30鍒嗛挓鍓?, 'source': '鎶鏈鍧?, 'related_tags': ['VRM', '3D']},
            {'id': 5, 'topic': 'ComfyUI 宸ヤ綔娴?, 'trend': 'up', 'heat': 5200, 'category': '宸ュ叿', 'last_update': '45鍒嗛挓鍓?, 'source': '宸ュ叿绀惧尯', 'related_tags': ['ComfyUI', '宸ヤ綔娴?]},
            {'id': 6, 'topic': 'AI Agent 鑷姩鍖?, 'trend': 'up', 'heat': 4800, 'category': '鎶鏈?, 'last_update': '1灏忔椂鍓?, 'source': '鎶鏈崥瀹?, 'related_tags': ['Agent', '鑷姩鍖?]},
            {'id': 7, 'topic': 'Stable Diffusion 3', 'trend': 'up', 'heat': 4200, 'category': 'AI', 'last_update': '2灏忔椂鍓?, 'source': 'AI璧勮', 'related_tags': ['SD3', '鍥惧儚鐢熸垚']},
            {'id': 8, 'topic': '鏁板瓧浜虹洿鎾?, 'trend': 'stable', 'heat': 3800, 'category': '鍒涗綔', 'last_update': '3灏忔椂鍓?, 'source': '鐩存挱绀惧尯', 'related_tags': ['鏁板瓧浜?, '鐩存挱']},
            {'id': 9, 'topic': 'FLUX 妯″瀷浼樺寲', 'trend': 'up', 'heat': 3500, 'category': 'AI', 'last_update': '30鍒嗛挓鍓?, 'source': '鎶鏈鍧?, 'related_tags': ['FLUX', '浼樺寲']},
            {'id': 10, 'topic': 'Midjourney V6', 'trend': 'down', 'heat': 3200, 'category': 'AI', 'last_update': '4灏忔椂鍓?, 'source': 'AI璧勮', 'related_tags': ['MJ', '鍥惧儚鐢熸垚']},
        ]
        
        if category and category != 'all':
            topics = [t for t in topics if t['category'] == category]
        
        return {
            'success': True,
            'data': {
                'topics': topics[:limit],
                'total': len(topics),
                'last_update': datetime.now().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/info/hot-topics/refresh")
async def refresh_hot_topics(categories: List[str] = None):
    """鍒锋柊鐑偣璇濋"""
    try:
        # 妯℃嫙鍒锋柊鐑偣璇濋 (瀹為檯搴旇皟鐢╝i_automation.py)
        import random
        topics = []
        for i in range(10):
            topics.append({
                'id': i + 1,
                'topic': f'鐑偣璇濋 {i + 1}',
                'trend': random.choice(['up', 'down', 'stable']),
                'heat': random.randint(1000, 15000),
                'category': random.choice(['鎶鏈?, 'AI', '鍒涗綔', '宸ュ叿', '绀惧尯']),
                'last_update': '鍒氬垰',
                'source': '瀹炴椂鍒锋柊'
            })
        return {
            'success': True,
            'data': {
                'topics': topics,
                'updated': len(topics),
                'duration': 2.5
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/stats")
async def get_stats(period: str = None):
    """鑾峰彇缁熻鏁版嵁"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 鑾峰彇浠诲姟缁熻
        cursor.execute("SELECT COUNT(*) FROM generation_tasks WHERE status = 'completed'")
        completed = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM generation_tasks WHERE DATE(created_at) = DATE('now')")
        today_tasks = cursor.fetchone()[0] or 0
        
        conn.close()
        
        stats = {
            'today': {'generations': today_tasks, 'users': 24, 'apiCalls': today_tasks * 20, 'uptime': 99.9},
            'week': {'generations': today_tasks * 7, 'users': 156, 'apiCalls': today_tasks * 7 * 20, 'uptime': 99.8},
            'month': {'generations': today_tasks * 30, 'users': 512, 'apiCalls': today_tasks * 30 * 20, 'uptime': 99.7}
        }
        
        return {'success': True, 'data': stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/health")
async def health_check():
    """鍋ュ悍妫鏌?""
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # 妫鏌ユ湇鍔＄姸鎬?        services = {
            'api': True,
            'database': DB_PATH.parent.exists(),
            'gpu': True,  # 绠鍖栨鏌?            'storage': disk.percent < 95
        }
        
        status = 'healthy'
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            status = 'degraded'
        if not services['database'] or not services['storage']:
            status = 'unhealthy'
        
        return {
            'success': True,
            'data': {
                'status': status,
                'timestamp': datetime.now().isoformat(),
                'version': '5.4.0',
                'uptime': 86400,
                'services': services,
                'metrics': {
                    'cpu': cpu_percent,
                    'memory': memory.percent,
                    'disk': disk.percent
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/gpu")
async def get_gpu_info():
    """鑾峰彇GPU淇℃伅"""
    try:
        gpus = []
        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw,power.limit,driver_version,cuda.version', '--format=csv,noheader'], 
                                   capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 11:
                            gpus.append({
                                'index': int(parts[0]),
                                'name': parts[1],
                                'memory_total': float(parts[2]) * 1024 * 1024,
                                'memory_used': float(parts[3]) * 1024 * 1024,
                                'memory_free': float(parts[4]) * 1024 * 1024,
                                'utilization': float(parts[5]),
                                'temperature': float(parts[6]),
                                'power_usage': float(parts[7]) if parts[7] else 0,
                                'power_limit': float(parts[8]) if parts[8] else 0,
                                'driver_version': parts[9],
                                'cuda_version': parts[10]
                            })
        except:
            pass
        
        return {
            'success': True,
            'data': {
                'gpus': gpus,
                'total_count': len(gpus)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/tasks")
async def get_task_stats():
    """鑾峰彇浠诲姟缁熻"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT status, COUNT(*) FROM generation_tasks GROUP BY status")
        stats = {'queue': 0, 'running': 0, 'completed': 0, 'failed': 0, 'total': 0, 'success_rate': 0}
        total = 0
        completed = 0
        for status, count in cursor.fetchall():
            if status in stats:
                stats[status] = count
            total += count
            if status == 'completed':
                completed = count
        
        stats['total'] = total
        if total > 0:
            stats['success_rate'] = round(completed / total * 100, 2)
        
        conn.close()
        return {'success': True, 'data': stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/users")
async def get_user_stats():
    """鑾峰彇鐢ㄦ埛缁熻"""
    return {
        'success': True,
        'data': {
            'online': 1,
            'active': 5,
            'total': 10,
            'new_today': 2
        }
    }


@app.get("/api/info/models")
async def get_model_stats():
    """鑾峰彇妯″瀷鐘舵?""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) FROM model_configs")
        result = cursor.fetchone()
        
        cursor.execute("SELECT id, name, type, size FROM model_configs LIMIT 10")
        models = [{'id': r[0], 'name': r[1], 'status': 'loaded', 'size': r[3] or 'Unknown'} for r in cursor.fetchall()]
        
        conn.close()
        
        return {
            'success': True,
            'data': {
                'loaded': result[1] or 0,
                'available': result[0] or 0,
                'downloading': 0,
                'total_size': '0GB',
                'models': models
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/info/sessions")
async def get_session_stats():
    """鑾峰彇浼氳瘽缁熻"""
    return {
        'success': True,
        'data': {
            'total': 156,
            'today': 24,
            'concurrent': 3,
            'avg_duration': 1800
        }
    }



# ==================== Model Management API ====================

import os
import glob

MODEL_DIRECTORIES = [
    os.path.join(os.path.expanduser('~'), 'AI', 'Models'),
    os.path.join(os.path.expanduser('~'), 'ComfyUI', 'models'),
    'D:\\AI\\Models',
    'D:\\ComfyUI\\models',
    'C:\\AI\\Models',
]

CONTROLNET_DIRECTORIES = [
    'D:\\AI\\Models\\ControlNet',
    'D:\\ComfyUI\\models\\controlnet',
    'D:\\stable-diffusion-webui\\models\\ControlNet',
    'C:\\AI\\Models\\ControlNet',
]

LORA_DIRECTORIES = [
    'D:\\AI\\Models\\LoRA',
    'D:\\ComfyUI\\models\\loras',
    'D:\\stable-diffusion-webui\\models\\Lora',
    'C:\\AI\\Models\\Lora',
]

VAE_DIRECTORIES = [
    'D:\\AI\\Models\\VAE',
    'D:\\ComfyUI\\models\\vae',
    'D:\\stable-diffusion-webui\\models\\VAE',
    'C:\\AI\\Models\\VAE',
]


def scan_directory_for_models(directory: str, extensions: List[str]) -> List[Dict[str, Any]]:
    """扫描目录中的模型文件"""
    models = []
    if not os.path.exists(directory):
        return models
    
    for ext in extensions:
        pattern = os.path.join(directory, f'*{ext}')
        for filepath in glob.glob(pattern):
            try:
                stat = os.stat(filepath)
                filename = os.path.basename(filepath)
                model_type = 'unknown'
                lower_name = filename.lower()
                if 'canny' in lower_name: model_type = 'canny'
                elif 'depth' in lower_name: model_type = 'depth'
                elif 'pose' in lower_name: model_type = 'pose'
                elif 'seg' in lower_name: model_type = 'seg'
                elif 'normal' in lower_name: model_type = 'normal'
                elif 'line' in lower_name: model_type = 'line'
                elif 'scribble' in lower_name: model_type = 'scribble'
                elif 'mlsd' in lower_name: model_type = 'mlsd'
                
                models.append({
                    'id': f'model_{hash(filepath)}',
                    'name': filename,
                    'path': filepath,
                    'size': stat.st_size,
                    'type': model_type,
                    'lastModified': stat.st_mtime,
                    'directory': directory
                })
            except: continue
    
    return models


@app.get("/api/models/list")
async def list_models(model_type: str = None, category: str = None, search: str = None, limit: int = 100):
    """获取模型列表 - 真实扫描文件系统"""
    try:
        all_models = []
        extensions = ['.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.onnx']
        directories_to_scan = CONTROLNET_DIRECTORIES if category == 'controlnet' else LORA_DIRECTORIES if category == 'lora' else VAE_DIRECTORIES if category == 'vae' else MODEL_DIRECTORIES
        
        for directory in directories_to_scan:
            models = scan_directory_for_models(directory, extensions)
            all_models.extend(models)
        
        if model_type and model_type != 'all':
            all_models = [m for m in all_models if m['type'] == model_type]
        if search:
            search_lower = search.lower()
            all_models = [m for m in all_models if search_lower in m['name'].lower()]
        
        all_models.sort(key=lambda x: x['lastModified'], reverse=True)
        all_models = all_models[:limit]
        
        return {'success': True, 'data': {'models': all_models, 'total': len(all_models), 'scanned_directories': directories_to_scan}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/controlnet")
async def list_controlnet_models(model_type: str = None, search: str = None, limit: int = 50):
    """获取ControlNet模型列表 - 真实扫描文件系统"""
    try:
        all_models = []
        extensions = ['.safetensors', '.ckpt', '.pt', '.pth', '.bin']
        for directory in CONTROLNET_DIRECTORIES:
            models = scan_directory_for_models(directory, extensions)
            all_models.extend(models)
        
        if model_type and model_type != 'all':
            all_models = [m for m in all_models if m['type'] == model_type]
        if search:
            search_lower = search.lower()
            all_models = [m for m in all_models if search_lower in m['name'].lower()]
        
        all_models.sort(key=lambda x: x['lastModified'], reverse=True)
        all_models = all_models[:limit]
        
        return {'success': True, 'data': {'models': all_models, 'total': len(all_models), 'scanned_directories': CONTROLNET_DIRECTORIES}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/lora")
async def list_lora_models(search: str = None, limit: int = 50):
    """获取LoRA模型列表 - 真实扫描文件系统"""
    try:
        all_models = []
        extensions = ['.safetensors', '.ckpt', '.pt', '.pth']
        for directory in LORA_DIRECTORIES:
            models = scan_directory_for_models(directory, extensions)
            all_models.extend(models)
        
        if search:
            search_lower = search.lower()
            all_models = [m for m in all_models if search_lower in m['name'].lower()]
        
        all_models.sort(key=lambda x: x['lastModified'], reverse=True)
        all_models = all_models[:limit]
        
        return {'success': True, 'data': {'models': all_models, 'total': len(all_models), 'scanned_directories': LORA_DIRECTORIES}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/vae")
async def list_vae_models(search: str = None, limit: int = 50):
    """获取VAE模型列表 - 真实扫描文件系统"""
    try:
        all_models = []
        extensions = ['.safetensors', '.ckpt', '.pt', '.pth', '.vae.pt', '.vae.safetensors']
        for directory in VAE_DIRECTORIES:
            models = scan_directory_for_models(directory, extensions)
            all_models.extend(models)
        
        if search:
            search_lower = search.lower()
            all_models = [m for m in all_models if search_lower in m['name'].lower()]
        
        all_models.sort(key=lambda x: x['lastModified'], reverse=True)
        all_models = all_models[:limit]
        
        return {'success': True, 'data': {'models': all_models, 'total': len(all_models), 'scanned_directories': VAE_DIRECTORIES}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/checkpoint")
async def list_checkpoint_models(search: str = None, limit: int = 50):
    """获取Checkpoint模型列表"""
    try:
        all_models = []
        extensions = ['.safetensors', '.ckpt', '.pt', '.pth']
        checkpoint_dirs = ['D:\\AI\\Models\\Stable-diffusion', 'D:\\ComfyUI\\models\\checkpoints', 'D:\\stable-diffusion-webui\\models\\Stable-diffusion']
        for directory in checkpoint_dirs:
            models = scan_directory_for_models(directory, extensions)
            all_models.extend(models)
        
        if search:
            search_lower = search.lower()
            all_models = [m for m in all_models if search_lower in m['name'].lower()]
        
        all_models.sort(key=lambda x: x['lastModified'], reverse=True)
        all_models = all_models[:limit]
        
        return {'success': True, 'data': {'models': all_models, 'total': len(all_models), 'scanned_directories': checkpoint_dirs}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/scan-status")
async def get_model_scan_status():
    """获取模型扫描状态"""
    try:
        status = {
            'controlnet': {'directories': CONTROLNET_DIRECTORIES, 'last_scan': None},
            'lora': {'directories': LORA_DIRECTORIES, 'last_scan': None},
            'vae': {'directories': VAE_DIRECTORIES, 'last_scan': None}
        }
        return {'success': True, 'data': status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 模型加载与推理 API ====================

@app.post("/api/inference/load-controlnet")
async def load_controlnet_model(
    controlnet_path: str = Form(...),
    controlnet_type: str = Form("canny"),
    user_info: dict = Depends(verify_token)
):
    """加载ControlNet模型"""
    try:
        from backend.inference_engine import get_inference_engine
        
        engine = get_inference_engine()
        success = engine.load_controlnet(controlnet_path, controlnet_type)
        
        if success:
            return {"success": True, "data": {"message": "ControlNet模型加载成功", "path": controlnet_path}}
        else:
            return {"success": False, "error": "ControlNet模型加载失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/load-lora")
async def load_lora_model(
    lora_configs: str = Form(...),  # JSON array of lora configs
    user_info: dict = Depends(verify_token)
):
    """加载LoRA模型"""
    try:
        from backend.inference_engine import get_inference_engine
        
        configs = json.loads(lora_configs)
        engine = get_inference_engine()
        
        if isinstance(configs, list):
            success = engine.load_multiple_loras(configs)
        else:
            success = engine.load_lora(configs.get('path'), configs.get('name'), configs.get('weight', 1.0))
        
        if success:
            return {"success": True, "data": {"message": "LoRA模型加载成功", "count": len(configs) if isinstance(configs, list) else 1}}
        else:
            return {"success": False, "error": "LoRA模型加载失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/generate-with-controlnet")
async def generate_with_controlnet(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    controlnet_image: UploadFile = File(...),
    controlnet_path: str = Form(None),
    controlnet_type: str = Form("canny"),
    negative_prompt: str = Form(""),
    width: int = Form(1024),
    height: int = Form(1024),
    num_inference_steps: int = Form(30),
    guidance_scale: float = Form(7.0),
    seed: int = Form(-1),
    controlnet_scale: float = Form(1.0),
    controlnet_guidance_start: float = Form(0.0),
    controlnet_guidance_end: float = Form(1.0),
    user_info: dict = Depends(verify_token)
):
    """使用ControlNet生成图像"""
    try:
        import io
        from PIL import Image
        from backend.inference_engine import get_inference_engine
        
        # 读取上传的图像
        image_bytes = await controlnet_image.read()
        controlnet_image_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # 创建生成任务ID
        task_id = str(uuid.uuid4())
        
        # 存储任务信息
        active_generations[task_id] = {
            "task_id": task_id,
            "type": "controlnet_generation",
            "status": "processing",
            "prompt": prompt
        }
        
        # 后台执行生成
        background_tasks.add_task(
            execute_controlnet_generation,
            task_id, prompt, controlnet_image_pil, controlnet_path,
            controlnet_type, negative_prompt, width, height,
            num_inference_steps, guidance_scale, seed,
            controlnet_scale, controlnet_guidance_start, controlnet_guidance_end
        )
        
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "processing"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def execute_controlnet_generation(
    task_id: str, prompt: str, controlnet_image: Image.Image,
    controlnet_path: str, controlnet_type: str, negative_prompt: str,
    width: int, height: int, num_inference_steps: int, guidance_scale: float,
    seed: int, controlnet_scale: float, controlnet_guidance_start: float,
    controlnet_guidance_end: float
):
    """执行ControlNet生成任务"""
    try:
        from backend.inference_engine import get_inference_engine
        
        engine = get_inference_engine()
        
        images = engine.generate_with_controlnet(
            prompt=prompt,
            controlnet_image=controlnet_image,
            controlnet_path=controlnet_path,
            controlnet_type=controlnet_type,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            controlnet_scale=controlnet_scale,
            controlnet_guidance_start=controlnet_guidance_start,
            controlnet_guidance_end=controlnet_guidance_end
        )
        
        # 保存生成的图像
        output_files = []
        output_dir = STORAGE_PATH / "outputs" / "controlnet"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for i, img in enumerate(images):
            output_path = output_dir / f"{task_id}_{i}.png"
            img.save(output_path)
            output_files.append(str(output_path))
        
        # 更新任务状态
        active_generations[task_id]["status"] = "completed"
        active_generations[task_id]["output_files"] = output_files
        update_task_status(task_id, "completed", 100, output_files)
        
    except Exception as e:
        active_generations[task_id]["status"] = "failed"
        active_generations[task_id]["error"] = str(e)
        update_task_status(task_id, "failed", 0, None, str(e))


@app.post("/api/inference/generate-with-lora")
async def generate_with_lora(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    lora_configs: str = Form(...),  # JSON array
    negative_prompt: str = Form(""),
    width: int = Form(1024),
    height: int = Form(1024),
    num_inference_steps: int = Form(30),
    guidance_scale: float = Form(7.0),
    seed: int = Form(-1),
    num_images: int = Form(1),
    user_info: dict = Depends(verify_token)
):
    """使用LoRA生成图像"""
    try:
        from backend.inference_engine import get_inference_engine
        
        configs = json.loads(lora_configs)
        
        # 先加载LoRA
        engine = get_inference_engine()
        if isinstance(configs, list):
            engine.load_multiple_loras(configs)
        else:
            engine.load_lora(configs.get('path'), configs.get('name'), configs.get('weight', 1.0))
        
        # 创建任务ID
        task_id = str(uuid.uuid4())
        
        active_generations[task_id] = {
            "task_id": task_id,
            "type": "lora_generation",
            "status": "processing",
            "prompt": prompt
        }
        
        # 后台执行生成
        background_tasks.add_task(
            execute_lora_generation,
            task_id, prompt, configs, negative_prompt,
            width, height, num_inference_steps, guidance_scale, seed, num_images
        )
        
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "status": "processing",
                "lora_count": len(configs) if isinstance(configs, list) else 1
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def execute_lora_generation(
    task_id: str, prompt: str, lora_configs: any, negative_prompt: str,
    width: int, height: int, num_inference_steps: int, guidance_scale: float,
    seed: int, num_images: int
):
    """执行LoRA生成任务"""
    try:
        from backend.inference_engine import get_inference_engine
        
        engine = get_inference_engine()
        
        # 确保LoRA已加载
        if isinstance(lora_configs, list):
            engine.load_multiple_loras(lora_configs)
        else:
            engine.load_lora(lora_configs.get('path'), lora_configs.get('name'), lora_configs.get('weight', 1.0))
        
        images = engine.generate_with_lora(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=num_images
        )
        
        # 保存图像
        output_files = []
        output_dir = STORAGE_PATH / "outputs" / "lora"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for i, img in enumerate(images):
            output_path = output_dir / f"{task_id}_{i}.png"
            img.save(output_path)
            output_files.append(str(output_path))
        
        active_generations[task_id]["status"] = "completed"
        active_generations[task_id]["output_files"] = output_files
        update_task_status(task_id, "completed", 100, output_files)
        
    except Exception as e:
        active_generations[task_id]["status"] = "failed"
        active_generations[task_id]["error"] = str(e)
        update_task_status(task_id, "failed", 0, None, str(e))


@app.get("/api/inference/loaded-models")
async def get_loaded_models(user_info: dict = Depends(verify_token)):
    """获取已加载的模型信息"""
    try:
        from backend.inference_engine import get_inference_engine
        
        engine = get_inference_engine()
        
        result = {
            "pipelines": list(engine.pipelines.keys()),
            "loaded_loras": getattr(engine, 'loaded_loras', {}),
            "current_pipeline": engine.current_pipeline,
            "device": engine.device
        }
        
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/clear-memory")
async def clear_inference_memory(user_info: dict = Depends(verify_token)):
    """清理推理内存"""
    try:
        from backend.inference_engine import get_inference_engine
        
        engine = get_inference_engine()
        engine.clear_memory()
        
        return {"success": True, "data": {"message": "内存清理完成"}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 最新AIGC模型 API ====================

@app.get("/api/models/latest/list")
async def get_latest_models(user_info: dict = Depends(verify_token)):
    try:
        from backend.inference_engine import MODEL_REPOS
        models = []
        for model_type, config in MODEL_REPOS.items():
            models.append({
                "type": model_type,
                "name": _get_model_display_name(model_type),
                "repo_id": config["repo_id"],
                "capability": config["type"],
                "category": _get_model_category(model_type)
            })
        return {"success": True, "data": {"models": models, "count": len(models)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/load-model")
async def load_latest_model(model_type: str = Form(...), model_path: str = Form(None),
    torch_dtype: str = Form("float16"), user_info: dict = Depends(verify_token)):
    try:
        from backend.inference_engine import get_inference_engine, MODEL_REPOS
        valid_types = list(MODEL_REPOS.keys()) + ["sdxl", "wan", "ltx", "hunyuan", "trellis"]
        if model_type not in valid_types:
            return {"success": False, "error": f"不支持的模型类型: {model_type}"}
        engine = get_inference_engine()
        success = engine.load_pipeline(model_type, model_path, torch_dtype)
        return {"success": True, "data": {"message": f"{_get_model_display_name(model_type)} 加载成功"}} if success else {"success": False, "error": "加载失败"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/generate-image")
async def generate_image_latest(background_tasks: BackgroundTasks, prompt: str = Form(...),
    negative_prompt: str = Form(""), model_type: str = Form("qwen_image"),
    width: int = Form(1024), height: int = Form(1024),
    num_inference_steps: int = Form(30), guidance_scale: float = Form(7.0),
    seed: int = Form(-1), num_images: int = Form(1), user_info: dict = Depends(verify_token)):
    try:
        from backend.inference_engine import get_inference_engine
        engine = get_inference_engine()
        if engine.current_pipeline != model_type:
            engine.load_pipeline(model_type)
        task_id = str(uuid.uuid4())
        active_generations[task_id] = {"task_id": task_id, "type": "image_generation", "model_type": model_type, "status": "processing", "prompt": prompt}
        background_tasks.add_task(execute_image_generation_latest, task_id, prompt, negative_prompt, model_type, width, height, num_inference_steps, guidance_scale, seed, num_images)
        return {"success": True, "data": {"task_id": task_id, "message": "图像生成任务已创建", "model_type": model_type}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/generate-video")
async def generate_video_latest(background_tasks: BackgroundTasks, prompt: str = Form(...),
    negative_prompt: str = Form(""), model_type: str = Form("wan_2_2"),
    num_inference_steps: int = Form(50), guidance_scale: float = Form(7.5),
    seed: int = Form(-1), num_frames: int = Form(61), fps: int = Form(24),
    user_info: dict = Depends(verify_token)):
    try:
        from backend.inference_engine import get_inference_engine
        engine = get_inference_engine()
        task_id = str(uuid.uuid4())
        active_generations[task_id] = {"task_id": task_id, "type": "video_generation", "model_type": model_type, "status": "processing", "prompt": prompt}
        background_tasks.add_task(execute_video_generation_latest, task_id, prompt, negative_prompt, model_type, num_inference_steps, guidance_scale, seed, num_frames, fps)
        return {"success": True, "data": {"task_id": task_id, "message": "视频生成任务已创建", "model_type": model_type}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/generate-3d")
async def generate_3d_latest(background_tasks: BackgroundTasks, prompt: str = Form(...),
    negative_prompt: str = Form(""), model_type: str = Form("hunyuan3d"),
    num_inference_steps: int = Form(50), guidance_scale: float = Form(7.5),
    seed: int = Form(-1), user_info: dict = Depends(verify_token)):
    try:
        from backend.inference_engine import get_inference_engine
        engine = get_inference_engine()
        task_id = str(uuid.uuid4())
        active_generations[task_id] = {"task_id": task_id, "type": "3d_generation", "model_type": model_type, "status": "processing", "prompt": prompt}
        background_tasks.add_task(execute_3d_generation_latest, task_id, prompt, negative_prompt, model_type, num_inference_steps, guidance_scale, seed)
        return {"success": True, "data": {"task_id": task_id, "message": "3D模型生成任务已创建", "model_type": model_type}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/inference/upscale")
async def upscale_image_latest(background_tasks: BackgroundTasks, image: UploadFile = File(...),
    upscale_scale: float = Form(2.0), model_type: str = Form("dat"),
    num_inference_steps: int = Form(30), seed: int = Form(-1),
    user_info: dict = Depends(verify_token)):
    try:
        import io
        from PIL import Image
        from backend.inference_engine import get_inference_engine
        image_bytes = await image.read()
        input_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        task_id = str(uuid.uuid4())
        active_generations[task_id] = {"task_id": task_id, "type": "upscale", "model_type": model_type, "status": "processing"}
        background_tasks.add_task(execute_upscale_latest, task_id, input_image, upscale_scale, model_type, num_inference_steps, seed)
        return {"success": True, "data": {"task_id": task_id, "message": "图像放大任务已创建", "model_type": model_type}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/capabilities")
async def get_model_capabilities(user_info: dict = Depends(verify_token)):
    return {"success": True, "data": {
        "image_generation": {"models": ["z_image", "qwen_image", "sd_xl"], "description": "文生图"},
        "image_editing": {"models": ["flux_2_klein", "qwen_image_edit"], "description": "图生图/局部重绘"},
        "video_generation": {"models": ["wan_2_2", "ltx_video"], "description": "视频生成"},
        "3d_generation": {"models": ["hunyuan3d", "trellis_2"], "description": "3D模型生成"},
        "upscale": {"models": ["dat", "dat_2", "mdat"], "description": "图像放大"}
    }}


# ==================== 辅助函数 ====================

def _get_model_display_name(model_type: str) -> str:
    return {"z_image": "Z-Image", "qwen_image": "Qwen-Image", "flux_2_klein": "FLUX.2_Klein",
        "qwen_image_edit": "Qwen-Image-Edit", "wan_2_2": "Wan 2.2", "ltx_video": "LTX-Video",
        "hunyuan3d": "Hunyuan3D", "trellis_2": "Trellis-2", "dat": "DAT", "dat_2": "DAT-2", "mdat": "MDAT", "sd_xl": "Stable Diffusion XL"}.get(model_type, model_type)


def _get_model_category(model_type:str) -> str:
    return {"z_image": "图像生成", "qwen_image": "图像生成", "flux_2_klein": "图像编辑",
        "qwen_image_edit": "图像编辑", "wan_2_2": "视频生成", "ltx_video": "视频生成",
        "hunyuan3d": "3D生成", "trellis_2": "3D生成", "dat": "图像放大", "dat_2": "图像放大", "mdat": "图像放大"}.get(model_type, "其他")


def execute_image_generation_latest(task_id, prompt, negative_prompt, model_type, width, height, num_inference_steps, guidance_scale, seed, num_images):
    try:
        from backend.inference_engine import get_inference_engine
        import os
        engine = get_inference_engine()
        if engine.current_pipeline != model_type:
            engine.load_pipeline(model_type)
        images = engine.generate_image(prompt=prompt, negative_prompt=negative_prompt, width=width, height=height, num_inference_steps=num_inference_steps, guidance_scale=guidance_scale, seed=seed, num_images=num_images)
        output_dir = "./outputs/images"
        os.makedirs(output_dir, exist_ok=True)
        output_paths = []
        for i, img in enumerate(images):
            output_path = os.path.join(output_dir, f"{task_id}_{i}.png")
            img.save(output_path)
            output_paths.append(output_path)
        if task_id in active_generations:
            active_generations[task_id].update({"status": "completed", "output_paths": output_paths, "images_count": len(images)})
    except Exception as e:
        if task_id in active_generations:
            active_generations[task_id].update({"status": "failed", "error": str(e)})


def execute_video_generation_latest(task_id, prompt, negative_prompt, model_type, num_inference_steps, guidance_scale, seed, num_frames, fps):
    try:
        from backend.inference_engine import get_inference_engine
        engine = get_inference_engine()
        if engine.current_pipeline != model_type:
            engine.load_pipeline(model_type)
        output_path = engine.generate_video(prompt=prompt, negative_prompt=negative_prompt, num_inference_steps=num_inference_steps, guidance_scale=guidance_scale, seed=seed, num_frames=num_frames, fps=fps)
        if task_id in active_generations:
            active_generations[task_id].update({"status": "completed" if output_path else "failed", "output_path": output_path})
    except Exception as e:
        if task_id in active_generations:
            active_generations[task_id].update({"status": "failed", "error": str(e)})


def execute_3d_generation_latest(task_id, prompt, negative_prompt, model_type, num_inference_steps, guidance_scale, seed):
    try:
        from backend.inference_engine import get_inference_engine
        engine = get_inference_engine()
        if engine.current_pipeline != model_type:
            engine.load_pipeline(model_type)
        output_path = engine.generate_3d(prompt=prompt, negative_prompt=negative_prompt, num_inference_steps=num_inference_steps, guidance_scale=guidance_scale, seed=seed)
        if task_id in active_generations:
            active_generations[task_id].update({"status": "completed" if output_path else "failed", "output_path": output_path})
    except Exception as e:
        if task_id in active_generations:
            active_generations[task_id].update({"status": "failed", "error": str(e)})


def execute_upscale_latest(task_id, input_image, upscale_scale, model_type, num_inference_steps, seed):
    try:
        from backend.inference_engine import get_inference_engine
        import os
        engine = get_inference_engine()
        if engine.current_pipeline != model_type:
            engine.load_pipeline(model_type)
        result_image = engine.upscale_image(input_image=input_image, upscale_scale=upscale_scale, num_inference_steps=num_inference_steps, seed=seed)
        output_dir = "./outputs/upscale"
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{task_id}_upscale.png")
        result_image.save(output_path)
        if task_id in active_generations:
            active_generations[task_id].update({"status": "completed", "output_path": output_path})
    except Exception as e:
        if task_id in active_generations:
            active_generations[task_id].update({"status": "failed", "error": str(e)})


@app.on_event("shutdown")
async def shutdown_event():
    """搴旂敤鍏抽棴鏃剁殑娓呯悊"""
    print("馃洃 姝ｅ湪鍏抽棴AIGC鏈湴API鏈嶅姟鍣?..")
    
    # 鍋滄鎵鏈夋椿璺冧换鍔?    for task_id, task in active_generations.items():
        task.status = "cancelled"
    
    print("鉁?API鏈嶅姟鍣ㄥ凡鍏抽棴")

if __name__ == "__main__":
    # 鍒涘缓鏁版嵁搴撶洰褰?    DB_PATH.parent.mkdir(exist_ok=True)
    
    # 鍚姩鏈嶅姟鍣?    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )

