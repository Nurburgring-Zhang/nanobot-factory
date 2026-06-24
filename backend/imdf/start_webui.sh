#!/bin/bash
# Infinite Multimodal Data Foundry — Web UI 启动器
# 用于WSL/Ubuntu

IMDF_DIR="/mnt/d/Hermes/infinite-multimodal-data-foundry"
PORT=${1:-8765}

echo "========================================"
echo "  IMDF Canvas Web UI"
echo "========================================"
echo ""

# 检查依赖
echo "[检查] Python..."
python3 -c "import fastapi, uvicorn" 2>/dev/null || { echo "❌ 需要安装: pip install fastapi uvicorn"; exit 1; }
echo "  ✅ Python + FastAPI"

echo "[检查] ffmpeg..."
which ffmpeg 2>/dev/null && echo "  ✅ ffmpeg" || echo "  ⚠️ ffmpeg未安装,视频合成功将受限"

echo "[检查] 模块完整性..."
cd "$IMDF_DIR"
python3 -c "
import sys; sys.path.insert(0,'.')
from core.canvas_core import InfiniteCanvas
from agent.master_agent import MasterAgent
from api.canvas_web import CanvasWebApp
print('  ✅ 所有模块就绪')
" 2>/dev/null || { echo "❌ 模块加载失败"; exit 1; }

echo ""
echo "启动 Web UI 在 http://localhost:$PORT"
echo "按 Ctrl+C 停止"
echo "========================================"
echo ""

python3 api/canvas_web.py --port $PORT
