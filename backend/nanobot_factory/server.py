"""
Nanobot Factory Server — 导入实际 server.py
使 nanobot_factory.server:main 成为可用入口
"""
import sys, os
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# 导入实际的 server 模块
from server import app, main

__all__ = ['app', 'main']
