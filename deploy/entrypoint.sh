# =====================================================================
# Nanobot Factory — entrypoint.sh
# Boots the FastAPI backend (uvicorn) + nginx in the same container.
# Tini (PID 1) propagates SIGTERM to the whole process group.
# =====================================================================
#!/bin/sh
set -eu

echo "[entrypoint] starting nanobot-factory container..."

# Ensure runtime dirs exist
mkdir -p /app/data /app/logs /var/log/nginx /var/lib/nginx/tmp /run/nginx

# Run database migrations / seed if a script exists
if [ -f /app/scripts/migrate.sh ]; then
    echo "[entrypoint] running migrations..."
    sh /app/scripts/migrate.sh || echo "[entrypoint] migration script returned non-zero (continuing)"
fi

# Start uvicorn in the background (FastAPI on 127.0.0.1:8001 — internal only)
echo "[entrypoint] starting uvicorn on 127.0.0.1:8001"
/opt/venv/bin/uvicorn backend.server:app \
    --host 127.0.0.1 \
    --port 8001 \
    --workers "${UVICORN_WORKERS:-2}" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --log-level "${LOG_LEVEL:-info}" &

UVICORN_PID=$!
echo "[entrypoint] uvicorn PID=$UVICORN_PID"

# Wait for /healthz to come up (max 30s)
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8001/healthz >/dev/null 2>&1; then
        echo "[entrypoint] backend ready after ${i}s"
        break
    fi
    sleep 1
done

# Start nginx in the foreground (PID 1 = tini, which forwards signals here)
echo "[entrypoint] starting nginx on 0.0.0.0:8080"
exec nginx -g "daemon off;"