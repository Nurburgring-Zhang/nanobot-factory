#!/bin/bash

echo "================================"
echo " General AIGC Enhanced - 本地化部署"
echo " Version: 1.0.0"
echo "================================"
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到Python3，请先安装Python 3.8+"
    echo "Ubuntu/Debian: sudo apt update && sudo apt install python3 python3-pip"
    echo "macOS: brew install python3"
    exit 1
fi

echo "[信息] 检测到Python环境"
python3 --version
echo

# 检查pip是否可用
if ! command -v pip3 &> /dev/null; then
    echo "[错误] pip3不可用，请检查Python安装"
    exit 1
fi

# 进入后端目录
cd "$(dirname "$0")/backend"

echo "[信息] 检查Python依赖..."

# 安装Python依赖
echo "[步骤1/4] 安装Python后端依赖..."
pip3 install -r requirements_windows.txt
if [ $? -ne 0 ]; then
    echo "[错误] Python依赖安装失败"
    exit 1
fi

# 启动FastAPI后端服务
echo
echo "[步骤2/4] 启动FastAPI后端服务..."
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!

# 等待后端服务启动
echo "[信息] 等待后端服务启动..."
sleep 10

# 启动Web服务器服务前端
echo "[步骤3/4] 启动前端Web服务..."
cd "$(dirname "$0")/frontend"

echo "[步骤4/4] 启动前端Web服务器..."
nohup python3 -m http.server 3000 > frontend.log 2>&1 &
FRONTEND_PID=$!

# 打开浏览器（Linux）
if command -v xdg-open &> /dev/null; then
    echo
    echo "[完成] 服务启动完成！"
    echo
    echo "前端地址: http://localhost:3000"
    echo "后端API: http://localhost:8000"
    echo "API文档: http://localhost:8000/docs"
    echo
    echo "正在打开浏览器..."
    sleep 2
    xdg-open http://localhost:3000
elif command -v open &> /dev/null; then
    # macOS
    echo
    echo "[完成] 服务启动完成！"
    echo
    echo "前端地址: http://localhost:3000"
    echo "后端API: http://localhost:8000"
    echo "API文档: http://localhost:8000/docs"
    echo
    echo "正在打开浏览器..."
    sleep 2
    open http://localhost:3000
else
    echo
    echo "[完成] 服务启动完成！"
    echo
    echo "前端地址: http://localhost:3000"
    echo "后端API: http://localhost:8000"
    echo "API文档: http://localhost:8000/docs"
    echo
    echo "请手动在浏览器中打开: http://localhost:3000"
fi

echo
echo "服务已在后台运行。"
echo "停止服务: kill $BACKEND_PID $FRONTEND_PID"
echo

# 保存PID到文件
echo $BACKEND_PID > backend.pid
echo $FRONTEND_PID > frontend.pid

# 等待用户输入
read -p "按回车键停止服务..." dummy

# 停止服务
echo "正在停止服务..."
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
rm -f backend.pid frontend.pid
echo "服务已停止"