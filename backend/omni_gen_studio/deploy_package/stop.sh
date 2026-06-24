#!/bin/bash

echo "================================"
echo " 停止 General AIGC Enhanced 服务"
echo "================================"
echo

echo "[信息] 正在停止相关服务..."

# 停止后端服务
echo "[步骤1/3] 停止后端服务..."
if [ -f backend.pid ]; then
    BACKEND_PID=$(cat backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "终止后端进程: $BACKEND_PID"
        kill $BACKEND_PID 2>/dev/null
        sleep 2
        # 强制终止
        kill -9 $BACKEND_PID 2>/dev/null
    fi
    rm -f backend.pid
fi

# 停止前端服务
echo "[步骤2/3] 停止前端服务..."
if [ -f frontend.pid ]; then
    FRONTEND_PID=$(cat frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "终止前端进程: $FRONTEND_PID"
        kill $FRONTEND_PID 2>/dev/null
        sleep 2
        # 强制终止
        kill -9 $FRONTEND_PID 2>/dev/null
    fi
    rm -f frontend.pid
fi

# 清理其他相关进程
echo "[步骤3/3] 清理其他相关进程..."
echo "清理Python进程..."
pkill -f "uvicorn.*8000" 2>/dev/null
pkill -f "python.*http.server.*3000" 2>/dev/null
pkill -f "python3.*http.server.*3000" 2>/dev/null

# 清理端口占用
echo "清理端口占用..."
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:8000 | xargs kill -9 2>/dev/null

echo
echo "[完成] 所有服务已停止！"
echo

# 显示清理后的端口状态
echo "端口状态检查:"
netstat -tuln | grep -E ":3000|:8000" || echo "端口已清理"