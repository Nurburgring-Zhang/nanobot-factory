"""Nanobot Factory — 生产级ASGI入口

配合 gunicorn + uvicorn workers 使用：
  gunicorn -k uvicorn.workers.UvicornWorker -w 4 --bind 0.0.0.0:8001 production_app:app
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入server的app实例
from server import app
