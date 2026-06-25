#!/bin/bash
# 智影数据工场(统一平台) — 一键启动
# 启动 server_unified.py (8899端口, 包含IMDF+nanobot-factory)
set -e

echo "=============================="
echo "  智影数据工场 — 统一平台启动"
echo "=============================="

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJ_DIR"

# ===== JWT_SECRET 检查和生成 =====
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi
if [ -z "$JWT_SECRET" ] || [ "$JWT_SECRET" = "change...n==" ]; then
    echo ""
    echo "⚠️  JWT_SECRET 未设置，正在自动生成..."
    JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "JWT_SECRET=$JWT_SECRET" >> .env
    export JWT_SECRET
    echo "✅ JWT_SECRET 已生成并写入 .env"
fi

# ===== 环境检查 =====
echo "[1/4] 检查Python环境..."
PYTHON=$(which python3 || which python)
echo "  Python: $($PYTHON --version 2>&1)"

echo "[2/4] 检查必要模块..."
$PYTHON -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "  ⚠️ fastapi/uvicorn 未安装，尝试安装..."
    $PYTHON -m pip install fastapi uvicorn aiofiles -q
    echo "  ✅ 已安装"
}
echo "  ✅ 依赖就绪"

echo "[3/4] 检查端口..."
if ss -tlnp | grep -q ":8899 "; then
    echo "  ⚠️ 8899端口被占用，正在清理..."
    fuser -k 8899/tcp 2>/dev/null || true
    sleep 1
fi
echo "  ✅ 端口8899可用"

# ===== 启动统一平台 =====
echo "[4/4] 启动统一平台 (8899端口)..."
$PYTHON server_unified.py &
SERVER_PID=$!
echo "  进程 PID: $SERVER_PID"

# 等待服务就绪
echo "  等待服务就绪..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8899/health 2>/dev/null | grep -q "ok"; then
        echo "  ✅ 服务就绪"
        break
    fi
    sleep 1
done

echo ""
echo "=============================="
echo "  访问地址:"
echo "  统一平台:  http://localhost:8899"
echo "  前端界面:  http://localhost:8899/"
echo "  API文档:   http://localhost:8899/docs"
echo "  健康检查:  http://localhost:8899/health"
echo ""
echo "  后端服务(独立): http://localhost:8899/nb/api"
echo "  IMDF子系统:     http://localhost:8899/api/datasets"
echo "=============================="
echo ""
echo "按 Ctrl+C 停止"

wait $SERVER_PID
