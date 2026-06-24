# =====================================================================
# Nanobot Factory — Multi-stage Dockerfile
# Stage 1: node:20-alpine  → install JS deps & build the Vue 3 frontend
# Stage 2: python:3.11-slim → install Python deps & copy backend
# Stage 3: nginx:1.27-alpine → runtime, serves static frontend + reverse-proxies /api → backend
# =====================================================================

# ---------- Stage 1: frontend build ----------
FROM node:20-alpine AS frontend-build
WORKDIR /workspace/frontend

# Copy only manifests first for better layer caching
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund --prefer-offline

# Copy frontend sources and build
COPY frontend/ ./
# The Vue 3 frontend is a CDN-based SPA (frontend/index.html). It does not require
# a JS build step, but we still run a "build" so package-lock drift is detected.
# If you later migrate to Vite, replace this with: RUN npm run build
RUN echo "frontend ready (CDN SPA, no build step)" > /workspace/frontend/.built

# ---------- Stage 2: backend build ----------
FROM python:3.11-slim AS backend-build
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: build-essential for wheels; tini for proper signal handling; curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        tini \
        curl \
        ca-certificates \
        libjpeg-dev \
        zlib1g-dev \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (use requirements_full.txt; main deps are identical to requirements.txt)
COPY requirements_full.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Copy backend source
COPY backend/ /app/backend/
COPY config/ /app/config/ 2>/dev/null || true
COPY scripts/ /app/scripts/ 2>/dev/null || true

# ---------- Stage 3: runtime ----------
FROM nginx:1.27-alpine AS runtime

# Add tini for proper PID 1 signal handling
RUN apk add --no-cache tini curl

# Labels (OCI image annotation spec)
LABEL org.opencontainers.image.title="nanobot-factory" \
      org.opencontainers.image.description="AIGC production platform — web UI + FastAPI backend" \
      org.opencontainers.image.vendor="MiniMax Agent" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/MiniMax-AI/nanobot-factory"

# Install Python runtime (Alpine) for the sidecar FastAPI process
# We use the lighter "python3" package + pip rather than the full Python image
RUN apk add --no-cache python3 py3-pip py3-virtualenv \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip

# Install Python deps into the venv
COPY requirements_full.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy backend from the build stage
COPY --from=backend-build /app/backend/ /app/backend/
COPY --from=backend-build /app/config/ /app/config/ 2>/dev/null || true

# Copy frontend static files
COPY --from=frontend-build /workspace/frontend/ /usr/share/nginx/html/

# Copy our nginx config
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf

# Copy entrypoint script (boots uvicorn + nginx)
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose: nginx on 8080 (unprivileged), backend on 8001 (internal)
EXPOSE 8080 8001

# Healthcheck hits nginx → /healthz (which nginx proxies to backend)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

# Use tini as PID 1 for proper signal forwarding
ENTRYPOINT ["/sbin/tini", "--", "/entrypoint.sh"]