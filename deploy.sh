# Nanobot Factory — 生产级启动配置
# 直接使用 uvicorn --workers，不需要gunicorn

HOST=${NANOBOT_HOST:-"0.0.0.0"}
PORT=${NANOBOT_PORT:-8001}
WORKERS=${NANOBOT_WORKERS:-4}
APP_MODULE="production_app:app"

export DATABASE_PATH=${DATABASE_PATH:-"backend/data/nanobot.db"}
export LOG_LEVEL=${LOG_LEVEL:-"info"}

mkdir -p backend/logs

echo "🚀 Nanobot Factory — 生产模式启动"
echo "   地址: http://$HOST:$PORT"
echo "   Workers: $WORKERS"
echo "   日志: backend/logs/"

cd "$(dirname "$0")"

# 启动生产服务
uvicorn "$APP_MODULE" \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL" \
    --limit-concurrency 200 \
    --limit-max-requests 10000 \
    --timeout-keep-alive 30 \
    --ws auto