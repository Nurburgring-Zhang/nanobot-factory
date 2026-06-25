#!/usr/bin/env python3
"""
统一数据生产平台 — 主入口
集成: nanobot-factory核心 + IMDF + 智影
启动: python server_unified.py --port 8899
"""
import sys, os, logging

# ===== Path Setup =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMDF_DIR = os.path.join(BASE_DIR, 'backend', 'imdf')
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))
sys.path.insert(0, IMDF_DIR)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("unified")

# ===== FastAPI App =====
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("统一平台启动中...")
    yield
    logger.info("统一平台关闭")

app = FastAPI(title="统一数据生产平台", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ===== 挂载IMDF子系统(含智影) =====
try:
    from api.canvas_web import app as imdf_app
    app.mount("/", imdf_app)  # IMDF+智影作为主应用
    logger.info(f"IMDF+智影已挂载为根应用 ({len(imdf_app.routes)}路由)")
except Exception as e:
    logger.warning(f"IMDF挂载失败: {e}")

# ===== 挂载nanobot-factory Vue前端 =====
frontend_dir = os.path.join(BASE_DIR, 'web', 'dist')
if os.path.exists(frontend_dir):
    app.mount("/nb", StaticFiles(directory=frontend_dir, html=True))
    logger.info("nanobot-factory前端已挂载于 /nb")
else:
    logger.info("nanobot-factory前端未构建(需 npm run build)")

# ===== 挂载nanobot-factory后端API(可选) =====
try:
    from backend.server import app as nb_app
    app.mount("/nb/api", nb_app)
    logger.info("nanobot-factory后端已挂载于 /nb/api")
except Exception:
    logger.info("nanobot-factory后端独立模式(请单独启动 server.py --port 8899)")

# ===== 首页重定向 =====
@app.get("/portal", response_class=HTMLResponse)
async def portal():
    return """
    <h1>统一数据生产平台</h1>
    <ul>
    <li><a href="/">IMDF+智影 数据工厂</a></li>
    <li><a href="/nb">nanobot-factory 前端</a></li>
    </ul>
    """

# ===== 启动 =====
if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('UNIFIED_PORT', sys.argv[2] if len(sys.argv)>2 and sys.argv[1]=='--port' else '8899'))
    logger.info(f"统一平台启动于 http://0.0.0.0:{port}")
    uvicorn.run(app, host='0.0.0.0', port=port)
