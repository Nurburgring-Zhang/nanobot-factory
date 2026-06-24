# Makefile for Nanobot Factory
# Provides convenient build and development commands

# Variables
PYTHON := python3
NODE := npm
NPM := npm
PYTEST := pytest
PROJECT_DIR := $(shell pwd)
BACKEND_DIR := $(PROJECT_DIR)/backend
FRONTEND_DIR := $(PROJECT_DIR)

# K8s / Helm
KUBECTL := kubectl
KUSTOMIZE := kubectl
HELM := helm
K8S_DIR := $(PROJECT_DIR)/k8s
HELM_CHART := $(PROJECT_DIR)/helm/nanobot-factory
NAMESPACE := nanobot-factory
RELEASE_NAME := nanobot-factory
IMAGE_TAG ?= v0.8.0

# Default target
.PHONY: help

help:
	@echo "Nanobot Factory - Build Commands"
	@echo ""
	@echo "Development:"
	@echo "  make dev            - Start development mode"
	@echo "  make dev:backend    - Start backend server only"
	@echo "  make dev:frontend   - Start frontend only"
	@echo ""
	@echo "Build:"
	@echo "  make build          - Build frontend and backend"
	@echo "  make build:frontend - Build React frontend"
	@echo "  make build:main     - Build Electron main process"
	@echo "  make docker:build   - Build nanobot-factory:latest image"
	@echo ""
	@echo "Test:"
	@echo "  make test           - Run all tests"
	@echo "  make test:unit      - Run unit tests only"
	@echo "  make test:perf     - Run performance tests"
	@echo "  make test:security  - Run security tests"
	@echo "  make test:coverage  - Run tests with coverage"
	@echo ""
	@echo "K8s / Helm (P3-8-W1):"
	@echo "  make k8s-validate      - yaml.safe_load_all check (no kubectl needed)"
	@echo "  make k8s-dryrun        - kubectl apply --dry-run=client -f k8s/"
	@echo "  make k8s-deploy        - kubectl apply -k k8s/"
	@echo "  make k8s-delete        - kubectl delete -k k8s/"
	@echo "  make helm-template     - helm template nanobot-factory helm/nanobot-factory/"
	@echo "  make helm-install      - helm install nanobot-factory helm/nanobot-factory/"
	@echo "  make helm-uninstall    - helm uninstall nanobot-factory"
	@echo "  make k8s-status        - kubectl get all -n nanobot-factory"
	@echo ""
	@echo "Package:"
	@echo "  make package        - Package Electron app"
	@echo "  make installer      - Create Windows installer"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linters"
	@echo "  make format         - Format code"
	@echo "  make typecheck      - Run type checker"
	@echo ""
	@echo "Utilities:"
	@echo "  make install        - Install all dependencies"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make docs           - Generate documentation"

# Development
.PHONY: dev
dev: install
	cd $(FRONTEND_DIR) && $(NPM) run dev

.PHONY: dev:backend
dev:backend:
	cd $(BACKEND_DIR) && $(PYTHON) -m uvicorn server:app --reload --host 0.0.0.0 --port 8000

.PHONY: dev:frontend
dev:frontend:
	cd $(FRONTEND_DIR) && $(NPM) run dev:renderer

# Build
.PHONY: build
build: build:frontend build:main

.PHONY: build:frontend
build:frontend:
	cd $(FRONTEND_DIR) && $(NPM) run build:renderer

.PHONY: build:main
build:main:
	cd $(FRONTEND_DIR) && $(NPM) run build:main

# Test
.PHONY: test
test: test:unit

.PHONY: test:unit
test:unit:
	cd $(PROJECT_DIR) && $(PYTEST) tests/ -v --tb=short

.PHONY: test:perf
test:perf:
	cd $(PROJECT_DIR) && $(PYTEST) tests/test_performance.py -v -s

.PHONY: test:security
test:security:
	cd $(PROJECT_DIR) && $(PYTEST) tests/test_security.py -v

.PHONY: test:coverage
test:coverage:
	cd $(PROJECT_DIR) && $(PYTEST) tests/ -v --cov=backend --cov-report=html --cov-report=term

# Package
.PHONY: package
package: build
	cd $(FRONTEND_DIR) && $(NPM) run package

.PHONY: installer
installer: package
	cd $(FRONTEND_DIR) && makensis ../installer.nsi

# Code Quality
.PHONY: lint
lint:
	cd $(BACKEND_DIR) && ruff check .
	cd $(FRONTEND_DIR) && $(NPM) run lint

.PHONY: format
format:
	cd $(BACKEND_DIR) && black .
	cd $(FRONTEND_DIR) && $(NPM) run format

.PHONY: typecheck
typecheck:
	cd $(BACKEND_DIR) && mypy .
	cd $(FRONTEND_DIR) && $(NPM) run typecheck

# Install dependencies
.PHONY: install
install:
	cd $(BACKEND_DIR) && $(PYTHON) -m pip install -r requirements.txt
	cd $(BACKEND_DIR) && $(PYTHON) -m pip install -r requirements-dev.txt
	cd $(FRONTEND_DIR) && $(NPM) install

# Clean
.PHONY: clean
clean:
	cd $(FRONTEND_DIR) && $(NPM) run clean
	find $(PROJECT_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(PROJECT_DIR) -type f -name "*.pyc" -delete
	rm -rf $(PROJECT_DIR)/htmlcov
	rm -rf $(PROJECT_DIR)/.coverage

# Docs
.PHONY: docs
docs:
	cd $(BACKEND_DIR) && pdoc -o ../docs backend/

# ============================================================================
# K8s / Helm targets (P3-8-W1)
# ============================================================================

# Validate K8s YAML files (no kubectl required).  Uses Python yaml.safe_load_all.
.PHONY: k8s-validate
k8s-validate:
	@echo "[k8s-validate] Checking all YAML files under $(K8S_DIR)/ and $(HELM_CHART)/ ..."
	$(PYTHON) -c "import glob, sys, yaml; \
files = sorted(glob.glob('$(K8S_DIR)/**/*.yaml', recursive=True)) + sorted(glob.glob('$(HELM_CHART)/**/*.yaml', recursive=True)); \
fail = 0; \
for f in files: \
    try: \
        list(yaml.safe_load_all(open(f, encoding='utf-8'))); \
        print('  OK', f) \
    except Exception as e: \
        print('  FAIL', f, '->', e); \
        fail += 1; \
sys.exit(1 if fail else 0)"

# Dry-run apply (client-side; no actual cluster connection).  Requires kubectl.
.PHONY: k8s-dryrun
k8s-dryrun:
	$(KUBECTL) apply --dry-run=client -k $(K8S_DIR)/

# Apply K8s manifests via kustomize.
.PHONY: k8s-deploy
k8s-deploy:
	$(KUBECTL) apply -k $(K8S_DIR)/
	@echo "[k8s-deploy] Waiting 10s for initial rollout ..."
	sleep 10
	$(KUBECTL) get all -n $(NAMESPACE)

# Delete K8s manifests.
.PHONY: k8s-delete
k8s-delete:
	$(KUBECTL) delete -k $(K8S_DIR)/

# Render Helm templates locally (no install).
.PHONY: helm-template
helm-template:
	$(HELM) template $(RELEASE_NAME) $(HELM_CHART)/ --namespace $(NAMESPACE)

# Install via Helm.
.PHONY: helm-install
helm-install:
	$(HELM) install $(RELEASE_NAME) $(HELM_CHART)/ \
		--namespace $(NAMESPACE) --create-namespace \
		--set image.tag=$(IMAGE_TAG)

# Uninstall via Helm.
.PHONY: helm-uninstall
helm-uninstall:
	$(HELM) uninstall $(RELEASE_NAME) --namespace $(NAMESPACE)

# Show live status.
.PHONY: k8s-status
k8s-status:
	$(KUBECTL) get all,configmap,secret,pvc,hpa,ingress -n $(NAMESPACE)

# Build Docker image (called by CI / pre-deploy).
.PHONY: docker:build
docker:build:
	docker build -t ghcr.io/minimax-ai/nanobot-factory:$(IMAGE_TAG) -f Dockerfile .
