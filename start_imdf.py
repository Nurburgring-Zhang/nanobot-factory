#!/usr/bin/env python3
"""统一平台启动脚本 — 从 nanobot-factory 目录启动IMDF+智影"""
import sys, os

# 设置路径
IMDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend', 'imdf')
sys.path.insert(0, IMDF_DIR)
sys.path.insert(0, os.path.dirname(IMDF_DIR))

from api.canvas_web import app
import uvicorn

if __name__ == '__main__':
    port = int(os.environ.get('IMDF_PORT', '8765'))
    print(f'╔══════════════════════════════════════╗')
    print(f'║  统一数据生产平台 — IMDF+智影      ║')
    print(f'║  端口: {port}                          ║')
    print(f'║  目录: {os.path.dirname(IMDF_DIR)}   ║')
    print(f'╚══════════════════════════════════════╝')
    uvicorn.run(app, host='0.0.0.0', port=port, log_level='info')
