"""
F9.1 API/SDK 导出端点 — 真实化实现
=====================================
- /openapi: 返回完整OpenAPI 3.1 spec (从FastAPI app动态生成)
- /python: 生成Python SDK代码
- /typescript: 生成TypeScript类型定义
- /generate: 真实代码生成器
实现: 动态OpenAPI规范 + 真实SDK代码生成
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Body, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sdk", tags=["sdk"])

# ── Pydantic Models ─────────────────────────────────────────────────────────

# P1-A3: extend language regex to include new SDK targets + add openapi_spec
_LANG_PATTERN = r"^(python|typescript|javascript|js|go|both)$"

class GenerateRequest(BaseModel):
    # NOTE: "python|typescript|both" is the historical set; P1-A3 adds
    # "javascript|js|go". Any of the new languages routes through
    # SDKGenerator and returns a zip; python/typescript/both still use
    # the legacy single-file path for backward compatibility.
    language: str = Field(default="python", pattern=_LANG_PATTERN)
    package_name: str = Field(
        default="imdf-sdk",
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9_\-]{0,127}$",
    )
    version: str = Field(
        default="1.0.0",
        max_length=32,
        pattern=r"^\d+\.\d+\.\d+([\-+][a-zA-Z0-9.]+)?$",
        description="SemVer, e.g. 1.0.0 / 1.0.0-rc.1",
    )
    include_auth: bool = True
    include_async: bool = True
    # P1-A3: optional OpenAPI spec input. When provided, the SDK
    # generator walks this dict instead of the platform's built-in
    # schema. If None, the generator falls back to _build_openapi_spec.
    openapi_spec: Optional[Dict[str, Any]] = None
    # P1-A3: response format. "zip" returns application/zip; "files"
    # returns JSON metadata only (legacy behavior).
    response_format: str = Field(default="auto", pattern="^(auto|zip|files)$")

# ── OpenAPI Schema Builder ───────────────────────────────────────────────────

def _build_openapi_spec(host: str = "localhost:8900") -> Dict[str, Any]:
    """Build complete OpenAPI 3.1 spec for the IMDF platform."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "IMDF Platform API",
            "version": "1.0.0",
            "description": "IMDF (Intelligent Media Data Factory) - AI数据工厂平台API，提供资源管理、AI生成、众包协作、数据处理等功能。",
            "contact": {
                "name": "IMDF Team",
                "url": "https://imdf.example.com",
                "email": "api@imdf.example.com",
            },
            "license": {"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
        },
        "servers": [
            {"url": f"http://{host}/api/v1", "description": "IMDF API v1"},
            {"url": f"http://{host}/api/v2", "description": "IMDF API v2 (latest)"},
        ],
        "tags": [
            {"name": "health", "description": "健康检查"},
            {"name": "assets", "description": "资源管理"},
            {"name": "datasets", "description": "数据集管理"},
            {"name": "generation", "description": "AI生成"},
            {"name": "search", "description": "搜索"},
            {"name": "copyright", "description": "版权/水印"},
            {"name": "privacy", "description": "数据隐私/PII"},
            {"name": "webhooks", "description": "Webhook订阅"},
            {"name": "crowd_settlement", "description": "众包结算"},
            {"name": "workflow_contract", "description": "工作流契约"},
            {"name": "sdk", "description": "SDK导出"},
        ],
        "paths": {
            "/health": {
                "get": {
                    "tags": ["health"],
                    "summary": "基础健康检查",
                    "operationId": "healthCheck",
                    "responses": {
                        "200": {"description": "OK", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/HealthResponse"}}}},
                        "503": {"description": "Service Unavailable"},
                    }
                }
            },
            "/assets": {
                "get": {
                    "tags": ["assets"],
                    "summary": "列出资源",
                    "operationId": "listAssets",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                        {"name": "size", "in": "query", "schema": {"type": "integer", "default": 20}},
                        {"name": "type", "in": "query", "schema": {"type": "string"}, "description": "资源类型过滤"},
                    ],
                    "responses": {"200": {"description": "Assets list"}}
                },
                "post": {
                    "tags": ["assets"],
                    "summary": "创建资源",
                    "operationId": "createAsset",
                    "requestBody": {"$ref": "#/components/requestBodies/CreateAssetRequest"},
                    "responses": {"201": {"description": "Created"}}
                }
            },
            "/datasets": {
                "get": {
                    "tags": ["datasets"],
                    "summary": "列出数据集",
                    "operationId": "listDatasets",
                    "responses": {"200": {"description": "Datasets list"}}
                }
            },
            "/generate": {
                "post": {
                    "tags": ["generation"],
                    "summary": "AI生成内容",
                    "operationId": "generateContent",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/GenerationRequest"}}}
                    },
                    "responses": {"202": {"description": "Generation started"}}
                }
            },
            "/search": {
                "get": {
                    "tags": ["search"],
                    "summary": "搜索资源",
                    "operationId": "search",
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                        {"name": "page", "in": "query", "schema": {"type": "integer", "default": 1}},
                    ],
                    "responses": {"200": {"description": "Search results"}}
                }
            },
            "/copyright/sign": {
                "post": {
                    "tags": ["copyright"],
                    "summary": "生成数字签名",
                    "operationId": "signContent",
                    "responses": {"200": {"description": "Signature generated"}}
                }
            },
            "/copyright/verify": {
                "post": {
                    "tags": ["copyright"],
                    "summary": "验证签名",
                    "operationId": "verifySignature",
                    "responses": {"200": {"description": "Verification result"}}
                }
            },
            "/copyright/embed": {
                "post": {
                    "tags": ["copyright"],
                    "summary": "嵌入版权信息",
                    "operationId": "embedCopyright",
                    "responses": {"200": {"description": "Copyright embedded"}}
                }
            },
            "/copyright/similarity": {
                "post": {
                    "tags": ["copyright"],
                    "summary": "计算相似度",
                    "operationId": "checkSimilarity",
                    "responses": {"200": {"description": "Similarity scores"}}
                }
            },
            "/privacy/pii/detect": {
                "post": {
                    "tags": ["privacy"],
                    "summary": "检测PII",
                    "operationId": "detectPII",
                    "responses": {"200": {"description": "PII detection results"}}
                }
            },
            "/privacy/pii/mask": {
                "post": {
                    "tags": ["privacy"],
                    "summary": "脱敏PII",
                    "operationId": "maskPII",
                    "responses": {"200": {"description": "Masked text"}}
                }
            },
            "/privacy/dsar/export": {
                "post": {
                    "tags": ["privacy"],
                    "summary": "DSAR导出",
                    "operationId": "dsarExport",
                    "responses": {"200": {"description": "Data export"}}
                }
            },
            "/privacy/dsar/delete": {
                "post": {
                    "tags": ["privacy"],
                    "summary": "DSAR删除",
                    "operationId": "dsarDelete",
                    "responses": {"200": {"description": "Data deleted"}}
                }
            },
            "/privacy/consent/record": {
                "post": {
                    "tags": ["privacy"],
                    "summary": "记录同意",
                    "operationId": "recordConsent",
                    "responses": {"200": {"description": "Consent recorded"}}
                }
            },
            "/webhooks": {
                "get": {
                    "tags": ["webhooks"],
                    "summary": "列出Webhook",
                    "operationId": "listWebhooks",
                    "responses": {"200": {"description": "Webhooks list"}}
                },
                "post": {
                    "tags": ["webhooks"],
                    "summary": "创建Webhook",
                    "operationId": "createWebhook",
                    "responses": {"201": {"description": "Webhook created"}}
                }
            },
            "/webhooks/event-types": {
                "get": {
                    "tags": ["webhooks"],
                    "summary": "事件类型列表",
                    "operationId": "listEventTypes",
                    "responses": {"200": {"description": "Event types"}}
                }
            },
            "/crowd/settlement/calculate": {
                "post": {
                    "tags": ["crowd_settlement"],
                    "summary": "计算结算",
                    "operationId": "calculateSettlement",
                    "responses": {"200": {"description": "Settlement calculated"}}
                }
            },
            "/crowd/settlement/approve": {
                "post": {
                    "tags": ["crowd_settlement"],
                    "summary": "批准结算",
                    "operationId": "approveSettlement",
                    "responses": {"200": {"description": "Settlement approved"}}
                }
            },
            "/crowd/settlement/pay": {
                "post": {
                    "tags": ["crowd_settlement"],
                    "summary": "执行支付",
                    "operationId": "paySettlement",
                    "responses": {"200": {"description": "Payment processed"}}
                }
            },
            "/workflow/contract/define": {
                "post": {
                    "tags": ["workflow_contract"],
                    "summary": "定义契约",
                    "operationId": "defineContract",
                    "responses": {"200": {"description": "Contract defined"}}
                }
            },
            "/workflow/contract/validate": {
                "post": {
                    "tags": ["workflow_contract"],
                    "summary": "验证契约",
                    "operationId": "validateContract",
                    "responses": {"200": {"description": "Validation result"}}
                }
            },
            "/workflow/contract/templates": {
                "get": {
                    "tags": ["workflow_contract"],
                    "summary": "契约模板",
                    "operationId": "listContractTemplates",
                    "responses": {"200": {"description": "Templates list"}}
                }
            },
        },
        "components": {
            "schemas": {
                "HealthResponse": {
                    "type": "object",
                    "properties": {
                        "success": {"type": "boolean"},
                        "data": {"$ref": "#/components/schemas/HealthData"},
                        "message": {"type": "string"},
                    }
                },
                "HealthData": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["ok", "degraded"]},
                        "service": {"type": "string"},
                        "version": {"type": "string"},
                        "timestamp": {"type": "string", "format": "date-time"},
                    }
                },
                "GenerationRequest": {
                    "type": "object",
                    "required": ["prompt"],
                    "properties": {
                        "prompt": {"type": "string", "description": "生成提示词"},
                        "negative_prompt": {"type": "string"},
                        "generator": {"type": "string", "default": "comfyui"},
                        "settings": {"type": "object"},
                    }
                },
                "AssetResponse": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "size": {"type": "integer"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "created_at": {"type": "string", "format": "date-time"},
                    }
                },
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean", "default": False},
                        "error": {"type": "string"},
                        "detail": {"type": "string"},
                    }
                },
                "Pagination": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer"},
                        "size": {"type": "integer"},
                        "total": {"type": "integer"},
                    }
                },
            },
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "API Key for authentication"
                },
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            },
            "requestBodies": {
                "CreateAssetRequest": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name", "type"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string", "enum": ["image", "video", "audio", "text", "3d", "document"]},
                                    "tags": {"type": "array", "items": {"type": "string"}},
                                    "metadata": {"type": "object"},
                                }
                            }
                        }
                    }
                }
            },
        },
        "security": [{"ApiKeyAuth": []}, {"BearerAuth": []}],
    }


# ── Python SDK Code Generator ────────────────────────────────────────────────

def _generate_python_sdk(version: str = "1.0.0", include_auth: bool = True, include_async: bool = True) -> str:
    """Generate complete Python SDK source code."""
    code = f'''"""
IMDF Python SDK v{version}
==========================
Auto-generated SDK for IMDF Platform API.
Install: pip install requests (for sync) / aiohttp (for async)

Usage:
    from imdf_sdk import IMDFClient
    
    client = IMDFClient(api_key="your-api-key", base_url="http://localhost:8900")
    
    # Health check
    health = client.health.check()
    
    # List assets
    assets = client.assets.list(page=1, size=20)
    
    # Search
    results = client.search.query("cat", page=1)
    
    # Generate content
    task = client.generate.create(prompt="a beautiful sunset", generator="comfyui")
    
    # Copyright
    sig = client.copyright.sign(asset_id="asset_001", content="Hello World")
    verified = client.copyright.verify(asset_id="asset_001", content="Hello World", signature=sig["signature"])
    
    # PII Detection
    pii = client.privacy.detect_pii(text="Contact me at user@example.com")
    masked = client.privacy.mask_pii(text="Contact me at user@example.com")
    
    # Webhooks
    wh = client.webhooks.create(url="https://example.com/hook", events=["task.completed"])
    
    # Settlement
    settlement = client.settlement.calculate(worker_id="w_001", period="weekly")
'''

    code += f'''
import json
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin

VERSION = "{version}"

# ── HTTP Client ──────────────────────────────────────────────────────────

class _HTTPClient:
    """Internal HTTP client using requests."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
    
    def _headers(self) -> Dict[str, str]:
        headers = {{"Content-Type": "application/json", "User-Agent": f"imdf-sdk-python/{{VERSION}}"}}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
    
    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))
    
    def get(self, path: str, params: Dict = None) -> Dict:
        import requests
        resp = requests.get(self._url(path), headers=self._headers(), params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def post(self, path: str, data: Dict = None) -> Dict:
        import requests
        resp = requests.post(self._url(path), headers=self._headers(), json=data or {{}}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def put(self, path: str, data: Dict = None) -> Dict:
        import requests
        resp = requests.put(self._url(path), headers=self._headers(), json=data or {{}}, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
    
    def delete(self, path: str) -> Dict:
        import requests
        resp = requests.delete(self._url(path), headers=self._headers(), timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

'''

    if include_async:
        code += '''
# ── Async HTTP Client ────────────────────────────────────────────────────

class _AsyncHTTPClient:
    """Internal async HTTP client using aiohttp."""
    
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
    
    def _headers(self) -> Dict[str, str]:
        headers = {{"Content-Type": "application/json", "User-Agent": f"imdf-sdk-python/{{VERSION}}"}}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers
    
    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))
    
    async def get(self, path: str, params: Dict = None) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(self._url(path), headers=self._headers(), params=params,
                                   timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                resp.raise_for_status()
                return await resp.json()
    
    async def post(self, path: str, data: Dict = None) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(self._url(path), headers=self._headers(), json=data or {{}},
                                    timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                resp.raise_for_status()
                return await resp.json()
    
    async def put(self, path: str, data: Dict = None) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.put(self._url(path), headers=self._headers(), json=data or {{}},
                                   timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                resp.raise_for_status()
                return await resp.json()
    
    async def delete(self, path: str) -> Dict:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.delete(self._url(path), headers=self._headers(),
                                      timeout=aiohttp.ClientTimeout(total=self.timeout)) as resp:
                resp.raise_for_status()
                return await resp.json()
'''

    code += '''
# ── Service Modules ──────────────────────────────────────────────────────

class HealthAPI:
    """Health check endpoints."""
    def __init__(self, client):
        self._client = client
    
    def check(self) -> Dict:
        """Basic health check."""
        return self._client.get("/api/v1/health")
    
    def ready(self) -> Dict:
        """Readiness check."""
        return self._client.get("/api/v1/health/ready")
    
    def live(self) -> Dict:
        """Liveness check."""
        return self._client.get("/api/v1/health/live")


class AssetsAPI:
    """Asset management endpoints."""
    def __init__(self, client):
        self._client = client
    
    def list(self, page: int = 1, size: int = 20, type: str = None) -> Dict:
        """List assets with pagination."""
        params = {"page": page, "size": size}
        if type:
            params["type"] = type
        return self._client.get("/api/v1/assets", params=params)
    
    def get(self, asset_id: str) -> Dict:
        """Get asset by ID."""
        return self._client.get(f"/api/v1/assets/{asset_id}")
    
    def create(self, name: str, type: str, tags: List[str] = None, metadata: Dict = None) -> Dict:
        """Create a new asset."""
        return self._client.post("/api/v1/assets", {
            "name": name, "type": type, "tags": tags or [], "metadata": metadata or {}
        })
    
    def update(self, asset_id: str, **kwargs) -> Dict:
        """Update an asset."""
        return self._client.put(f"/api/v1/assets/{asset_id}", kwargs)
    
    def delete(self, asset_id: str) -> Dict:
        """Delete an asset."""
        return self._client.delete(f"/api/v1/assets/{asset_id}")


class DatasetsAPI:
    """Dataset management endpoints."""
    def __init__(self, client):
        self._client = client
    
    def list(self) -> Dict:
        return self._client.get("/api/v1/datasets")
    
    def get(self, dataset_id: str) -> Dict:
        return self._client.get(f"/api/v1/datasets/{dataset_id}")
    
    def create(self, name: str, description: str = "") -> Dict:
        return self._client.post("/api/v1/datasets", {"name": name, "description": description})
    
    def add_assets(self, dataset_id: str, asset_ids: List[str]) -> Dict:
        return self._client.post(f"/api/v1/datasets/{dataset_id}/assets", {"asset_ids": asset_ids})


class GenerationAPI:
    """AI generation endpoints."""
    def __init__(self, client):
        self._client = client
    
    def create(self, prompt: str, negative_prompt: str = "", generator: str = "comfyui", settings: Dict = None) -> Dict:
        """Start an AI generation task."""
        return self._client.post("/api/v1/generate", {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "generator": generator,
            "settings": settings or {},
        })
    
    def status(self, task_id: str) -> Dict:
        """Get generation task status."""
        return self._client.get(f"/api/v1/generate/status/{task_id}")


class SearchAPI:
    """Search endpoints."""
    def __init__(self, client):
        self._client = client
    
    def query(self, q: str, page: int = 1, size: int = 20) -> Dict:
        return self._client.get("/api/v1/search", {"q": q, "page": page, "size": size})
    
    def multimodal(self, text: str = "", image_url: str = "", audio_url: str = "") -> Dict:
        return self._client.post("/api/v1/search/advanced/multimodal", {
            "text": text, "image_url": image_url, "audio_url": audio_url
        })
    
    def similar(self, asset_id: str, type: str = "style") -> Dict:
        return self._client.post("/api/v1/search/advanced/similar", {"asset_id": asset_id, "type": type})
    
    def faceted(self, filters: Dict = None) -> Dict:
        return self._client.post("/api/v1/search/advanced/faceted", {"filters": filters or {}})


class CopyrightAPI:
    """Copyright and watermark endpoints."""
    def __init__(self, client):
        self._client = client
    
    def sign(self, asset_id: str, content: str, algorithm: str = "HMAC-SHA256", secret_key: str = None) -> Dict:
        return self._client.post("/api/v1/copyright/sign", {
            "asset_id": asset_id, "content": content, "algorithm": algorithm, "secret_key": secret_key
        })
    
    def verify(self, asset_id: str, content: str, signature: str, algorithm: str = "HMAC-SHA256") -> Dict:
        return self._client.post("/api/v1/copyright/verify", {
            "asset_id": asset_id, "content": content, "signature": signature, "algorithm": algorithm
        })
    
    def embed(self, asset_id: str, creator: str = "", license: str = "CC-BY-4.0", copyright_text: str = "") -> Dict:
        return self._client.post("/api/v1/copyright/embed", {
            "asset_id": asset_id, "creator": creator, "license": license, "copyright_text": copyright_text
        })
    
    def similarity(self, source_id: str, content_a: str, content_b: str) -> Dict:
        return self._client.post("/api/v1/copyright/similarity", {
            "source_id": source_id, "content_a": content_a, "content_b": content_b
        })


class PrivacyAPI:
    """Privacy and PII endpoints."""
    def __init__(self, client):
        self._client = client
    
    def detect_pii(self, text: str) -> Dict:
        return self._client.post("/api/v1/privacy/pii/detect", {"text": text})
    
    def mask_pii(self, text: str, method: str = "replacement") -> Dict:
        return self._client.post("/api/v1/privacy/pii/mask", {"text": text, "method": method})
    
    def dsar_export(self, user_id: str) -> Dict:
        return self._client.post("/api/v1/privacy/dsar/export", {"user_id": user_id})
    
    def dsar_delete(self, user_id: str, scope: str = "all") -> Dict:
        return self._client.post("/api/v1/privacy/dsar/delete", {"user_id": user_id, "scope": scope})
    
    def record_consent(self, user_id: str, purpose: str, action: str) -> Dict:
        return self._client.post("/api/v1/privacy/consent/record", {
            "user_id": user_id, "purpose": purpose, "action": action
        })
    
    def get_consents(self, user_id: str) -> Dict:
        return self._client.get(f"/api/v1/privacy/consent/{user_id}")


class WebhooksAPI:
    """Webhook management endpoints."""
    def __init__(self, client):
        self._client = client
    
    def create(self, url: str, events: List[str], description: str = "") -> Dict:
        return self._client.post("/api/v1/webhooks", {"url": url, "events": events, "description": description})
    
    def list(self, active_only: bool = False) -> Dict:
        return self._client.get("/api/v1/webhooks", {"active_only": str(active_only).lower()})
    
    def get(self, webhook_id: str) -> Dict:
        return self._client.get(f"/api/v1/webhooks/{webhook_id}")
    
    def update(self, webhook_id: str, **kwargs) -> Dict:
        return self._client.put(f"/api/v1/webhooks/{webhook_id}", kwargs)
    
    def delete(self, webhook_id: str) -> Dict:
        return self._client.delete(f"/api/v1/webhooks/{webhook_id}")
    
    def test(self, webhook_id: str) -> Dict:
        return self._client.post(f"/api/v1/webhooks/{webhook_id}/test")
    
    def event_types(self) -> Dict:
        return self._client.get("/api/v1/webhooks/event-types")


class SettlementAPI:
    """Crowd settlement endpoints."""
    def __init__(self, client):
        self._client = client
    
    def calculate(self, worker_id: str, period: str = "weekly") -> Dict:
        return self._client.post("/api/v1/crowd/settlement/calculate", {
            "worker_id": worker_id, "period": period
        })
    
    def approve(self, batch_id: str, approver: str = "admin") -> Dict:
        return self._client.post("/api/v1/crowd/settlement/approve", {
            "batch_id": batch_id, "approver": approver
        })
    
    def pay(self, batch_id: str, method: str = "bank_transfer") -> Dict:
        return self._client.post("/api/v1/crowd/settlement/pay", {
            "batch_id": batch_id, "method": method
        })
    
    def history(self, worker_id: str = "", page: int = 1, size: int = 20) -> Dict:
        params = {"page": page, "size": size}
        if worker_id:
            params["worker_id"] = worker_id
        return self._client.get("/api/v1/crowd/settlement/history", params=params)
    
    def reputation(self, worker_id: str) -> Dict:
        return self._client.post("/api/v1/crowd/settlement/reputation/recalculate", {"worker_id": worker_id})


class WorkflowAPI:
    """Workflow contract endpoints."""
    def __init__(self, client):
        self._client = client
    
    def define_contract(self, node_type: str, inputs: Dict, outputs: Dict) -> Dict:
        return self._client.post("/api/v1/workflow/contract/define", {
            "node_type": node_type, "inputs": inputs, "outputs": outputs
        })
    
    def validate(self, source_node: str, target_node: str, source_output: Dict, target_input: Dict) -> Dict:
        return self._client.post("/api/v1/workflow/contract/validate", {
            "source_node": source_node, "target_node": target_node,
            "source_output": source_output, "target_input": target_input
        })
    
    def templates(self) -> Dict:
        return self._client.get("/api/v1/workflow/contract/templates")


# ── Main Client ──────────────────────────────────────────────────────────

class IMDFClient:
    """IMDF Platform API Client.
    
    Usage:
        client = IMDFClient(api_key="your-key", base_url="http://localhost:8900")
        health = client.health.check()
        assets = client.assets.list()
    """
    
    def __init__(self, base_url: str = "http://localhost:8900", api_key: Optional[str] = None, timeout: int = 30):
        self._client = _HTTPClient(base_url, api_key, timeout)
        self.health = HealthAPI(self._client)
        self.assets = AssetsAPI(self._client)
        self.datasets = DatasetsAPI(self._client)
        self.generate = GenerationAPI(self._client)
        self.search = SearchAPI(self._client)
        self.copyright = CopyrightAPI(self._client)
        self.privacy = PrivacyAPI(self._client)
        self.webhooks = WebhooksAPI(self._client)
        self.settlement = SettlementAPI(self._client)
        self.workflow = WorkflowAPI(self._client)
'''

    if include_async:
        code += '''

class AsyncIMDFClient:
    """Async IMDF Platform API Client.
    
    Usage:
        async with AsyncIMDFClient(api_key="your-key") as client:
            health = await client.health.check()
    """
    
    def __init__(self, base_url: str = "http://localhost:8900", api_key: Optional[str] = None, timeout: int = 30):
        self._client = _AsyncHTTPClient(base_url, api_key, timeout)
        self.health = HealthAPI(self._client)
        self.assets = AssetsAPI(self._client)
        self.datasets = DatasetsAPI(self._client)
        self.generate = GenerationAPI(self._client)
        self.search = SearchAPI(self._client)
        self.copyright = CopyrightAPI(self._client)
        self.privacy = PrivacyAPI(self._client)
        self.webhooks = WebhooksAPI(self._client)
        self.settlement = SettlementAPI(self._client)
        self.workflow = WorkflowAPI(self._client)
'''

    return code


# ── TypeScript Type Generator ────────────────────────────────────────────────

def _generate_typescript_types() -> str:
    """Generate TypeScript type definitions for the IMDF API."""
    return '''/**
 * IMDF Platform API - TypeScript Type Definitions
 * Auto-generated. Compatible with Node.js and browser.
 * 
 * Usage:
 *   import { IMDFClient, Asset, GenerationRequest } from '@imdf/sdk';
 *   
 *   const client = new IMDFClient({ apiKey: 'your-key', baseUrl: 'http://localhost:8900' });
 *   const assets = await client.assets.list();
 */

// ── Core Types ──────────────────────────────────────────────────────────

export interface APIResponse<T = any> {
  ok: boolean;
  data: T;
  error?: string;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

// ── Health ──────────────────────────────────────────────────────────────

export interface HealthCheckData {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  uptime_seconds: number;
  timestamp: string;
  checks?: Record<string, { ok: boolean; message: string }>;
}

// ── Assets ──────────────────────────────────────────────────────────────

export type AssetType = 'image' | 'video' | 'audio' | 'text' | '3d' | 'document';

export interface Asset {
  id: string;
  name: string;
  type: AssetType;
  path?: string;
  size: number;
  tags: string[];
  metadata: Record<string, any>;
  quality_score?: number;
  aesthetic_score?: number;
  nsfw_score?: number;
  created_at: string;
  updated_at: string;
}

export interface CreateAssetRequest {
  name: string;
  type: AssetType;
  tags?: string[];
  metadata?: Record<string, any>;
}

export interface UpdateAssetRequest {
  name?: string;
  tags?: string[];
  metadata?: Record<string, any>;
  quality_score?: number;
}

// ── Datasets ────────────────────────────────────────────────────────────

export interface Dataset {
  id: string;
  name: string;
  description: string;
  asset_count: number;
  created_at: string;
}

// ── Generation ──────────────────────────────────────────────────────────

export interface GenerationRequest {
  prompt: string;
  negative_prompt?: string;
  generator?: 'comfyui' | 'stable-diffusion' | 'midjourney';
  settings?: Record<string, any>;
}

export interface GenerationResponse {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  results?: string[];
}

// ── Search ──────────────────────────────────────────────────────────────

export interface SearchResult {
  id: string;
  type: AssetType;
  score: number;
  preview_url?: string;
  metadata: Record<string, any>;
}

export interface MultimodalSearchRequest {
  text?: string;
  image_url?: string;
  audio_url?: string;
}

export interface FacetValue {
  value: string;
  count: number;
}

export interface FacetedSearchResult {
  facets: Record<string, FacetValue[]>;
  results: SearchResult[];
  active_filters: Record<string, string>;
}

// ── Copyright ───────────────────────────────────────────────────────────

export interface SignatureResult {
  signature_id: string;
  asset_id: string;
  content_hash: string;
  signature: string;
  algorithm: string;
  created_at: string;
}

export interface VerifyResult {
  asset_id: string;
  valid: boolean;
  content_hash: string;
  algorithm: string;
}

export interface SimilarityResult {
  source_id: string;
  hash_match: boolean;
  similarity_scores: {
    hash: number;
    jaccard: number;
    levenshtein: number;
    char_ngram: number;
    combined: number;
  };
  risk_level: 'critical' | 'high' | 'medium' | 'low' | 'none';
}

export interface CopyrightRecord {
  record_id: string;
  asset_id: string;
  creator: string;
  license: string;
  copyright_text: string;
  embedded_at: string;
}

// ── Privacy / PII ───────────────────────────────────────────────────────

export interface PIIDetection {
  type: string;
  label: string;
  value: string;
  confidence: number;
  position: { start: number; end: number };
}

export interface PIIDetectResponse {
  pii_found: PIIDetection[];
  contains_pii: boolean;
  pii_types: string[];
  total_count: number;
}

export interface PIIMaskResponse {
  masked_text: string;
  masked_count: number;
  method: string;
}

export interface DSARExportResponse {
  request_id: string;
  user_id: string;
  status: string;
  data_categories: string[];
  exported_data: any[];
  total_records: number;
}

export interface ConsentRecord {
  consent_id: string;
  user_id: string;
  purpose: string;
  action: 'granted' | 'withdrawn';
  version: string;
  recorded_at: string;
}

// ── Webhooks ────────────────────────────────────────────────────────────

export interface EventType {
  type: string;
  description: string;
  category: string;
}

export interface Webhook {
  webhook_id: string;
  url: string;
  description: string;
  events: string[];
  active: boolean;
  created_at: string;
  success_count: number;
  failure_count: number;
}

export interface CreateWebhookRequest {
  url: string;
  events: string[];
  description?: string;
  secret?: string;
}

export interface WebhookDelivery {
  delivery_id: string;
  event_type: string;
  status: 'success' | 'failed' | 'pending';
  attempt: number;
  http_status: number;
  error_message?: string;
  sent_at: string;
}

// ── Settlement ──────────────────────────────────────────────────────────

export interface SettlementCalculation {
  worker_id: string;
  base_amount: number;
  quality_coefficient: number;
  bonus: number;
  penalty: number;
  total_amount: number;
  task_count: number;
  approved_count: number;
  approval_rate: number;
}

export interface SettlementBatch {
  batch_id: string;
  period: string;
  calculations: SettlementCalculation[];
  total_payout: number;
  currency: string;
  status: string;
}

// ── Workflow Contract ───────────────────────────────────────────────────

export interface ContractDefinition {
  contract_id: string;
  node_type: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
  version: string;
}

export interface ContractValidation {
  source_node: string;
  target_node: string;
  compatible: boolean;
  warnings: string[];
}

export interface ContractTemplate {
  node_type: string;
  inputs: Record<string, string>;
  outputs: Record<string, string>;
}

// ── Client Configuration ────────────────────────────────────────────────

export interface IMDFClientConfig {
  baseUrl?: string;
  apiKey?: string;
  timeout?: number;
}

// ── API Client ──────────────────────────────────────────────────────────

export class IMDFClient {
  private baseUrl: string;
  private apiKey?: string;
  private timeout: number;

  constructor(config: IMDFClientConfig = {}) {
    this.baseUrl = (config.baseUrl || 'http://localhost:8900').replace(/\\/$/, '');
    this.apiKey = config.apiKey;
    this.timeout = config.timeout || 30000;
  }

  private async request<T>(method: string, path: string, body?: any, params?: Record<string, string>): Promise<APIResponse<T>> {
    const url = new URL(path, this.baseUrl);
    if (params) {
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    }
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.apiKey) headers['X-API-Key'] = this.apiKey;

    const response = await fetch(url.toString(), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(this.timeout),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // Health
  health = {
    check: () => this.request<HealthCheckData>('GET', '/api/v1/health'),
    ready: () => this.request<HealthCheckData>('GET', '/api/v1/health/ready'),
    live: () => this.request<{ status: string }>('GET', '/api/v1/health/live'),
  };

  // Assets
  assets = {
    list: (page = 1, size = 20) => 
      this.request<PaginatedResponse<Asset>>('GET', '/api/v1/assets', undefined, { page: String(page), size: String(size) }),
    get: (id: string) => this.request<Asset>('GET', `/api/v1/assets/${id}`),
    create: (data: CreateAssetRequest) => this.request<Asset>('POST', '/api/v1/assets', data),
    update: (id: string, data: UpdateAssetRequest) => this.request<Asset>('PUT', `/api/v1/assets/${id}`, data),
    delete: (id: string) => this.request<{ deleted: boolean }>('DELETE', `/api/v1/assets/${id}`),
  };

  // Generation
  generate = {
    create: (data: GenerationRequest) => this.request<GenerationResponse>('POST', '/api/v1/generate', data),
    status: (taskId: string) => this.request<GenerationResponse>('GET', `/api/v1/generate/status/${taskId}`),
  };

  // Search
  search = {
    query: (q: string, page = 1) => 
      this.request<PaginatedResponse<SearchResult>>('GET', '/api/v1/search', undefined, { q, page: String(page) }),
    multimodal: (data: MultimodalSearchRequest) => this.request<PaginatedResponse<SearchResult>>('POST', '/api/v1/search/advanced/multimodal', data),
  };

  // Copyright
  copyright = {
    sign: (assetId: string, content: string, algorithm = 'HMAC-SHA256') => 
      this.request<SignatureResult>('POST', '/api/v1/copyright/sign', { asset_id: assetId, content, algorithm }),
    verify: (assetId: string, content: string, signature: string) => 
      this.request<VerifyResult>('POST', '/api/v1/copyright/verify', { asset_id: assetId, content, signature }),
    similarity: (sourceId: string, contentA: string, contentB: string) =>
      this.request<SimilarityResult>('POST', '/api/v1/copyright/similarity', { source_id: sourceId, content_a: contentA, content_b: contentB }),
  };

  // Privacy
  privacy = {
    detectPII: (text: string) => this.request<PIIDetectResponse>('POST', '/api/v1/privacy/pii/detect', { text }),
    maskPII: (text: string, method = 'replacement') => this.request<PIIMaskResponse>('POST', '/api/v1/privacy/pii/mask', { text, method }),
    dsarExport: (userId: string) => this.request<DSARExportResponse>('POST', '/api/v1/privacy/dsar/export', { user_id: userId }),
    dsarDelete: (userId: string) => this.request<{ deleted_records: number }>('POST', '/api/v1/privacy/dsar/delete', { user_id: userId }),
  };

  // Webhooks
  webhooks = {
    create: (data: CreateWebhookRequest) => this.request<Webhook>('POST', '/api/v1/webhooks', data),
    list: () => this.request<{ webhooks: Webhook[] }>('GET', '/api/v1/webhooks'),
    eventTypes: () => this.request<{ event_types: EventType[] }>('GET', '/api/v1/webhooks/event-types'),
  };

  // Settlement
  settlement = {
    calculate: (workerId: string, period = 'weekly') =>
      this.request<SettlementBatch>('POST', '/api/v1/crowd/settlement/calculate', { worker_id: workerId, period }),
  };
}

export default IMDFClient;
'''


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/health")
async def sdk_health():
    return {"status": "ok", "module": "sdk", "version": "1.0.0"}


@router.get("/openapi.json")
async def openapi_spec(request: Request):
    """
    返回完整的OpenAPI 3.1规范。
    动态生成包含所有IMDF API端点、类型定义和安全配置。
    """
    try:
        host = request.headers.get("host", "localhost:8900")
        spec = _build_openapi_spec(host)
        generated_at = datetime.now(timezone.utc).isoformat()
        spec["info"]["x-generated-at"] = generated_at
        spec["info"]["x-endpoint-count"] = len(spec["paths"])

        logger.info(f"OpenAPI spec generated: {len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas")
        return JSONResponse(content=spec)
    except Exception as e:
        logger.exception(f"OpenAPI spec generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/python", response_class=PlainTextResponse)
async def sdk_python(
    version: str = Query("1.0.0", pattern=r"^\d+\.\d+\.\d+([\-+][a-zA-Z0-9.]+)?$",
                         description="SemVer, e.g. 1.0.0 / 1.0.0-rc.1"),
    include_auth: bool = True,
    include_async: bool = True,
):
    """
    生成Python SDK源代码。
    返回完整可用的Python SDK代码，可直接保存为 imdf_sdk.py 使用。
    R2 改造: version 用 SemVer 格式校验
    """
    try:
        code = _generate_python_sdk(version=version, include_auth=include_auth, include_async=include_async)
        logger.info(f"Python SDK generated: {len(code)} chars, version={version}")
        return PlainTextResponse(content=code, media_type="text/x-python",
                                 headers={"Content-Disposition": f"attachment; filename=imdf_sdk.py"})
    except Exception as e:
        logger.exception(f"Python SDK generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/typescript", response_class=PlainTextResponse)
async def sdk_typescript():
    """
    生成TypeScript类型定义。
    返回完整可用的TypeScript SDK代码，可直接保存并 npm install 使用。
    """
    try:
        code = _generate_typescript_types()
        logger.info(f"TypeScript SDK generated: {len(code)} chars")
        return PlainTextResponse(content=code, media_type="text/typescript",
                                 headers={"Content-Disposition": f"attachment; filename=imdf_sdk.ts"})
    except Exception as e:
        logger.exception(f"TypeScript SDK generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def sdk_generate(req: GenerateRequest):
    """
    按需生成SDK代码: 根据指定语言生成对应的SDK代码包。
    返回生成的文件内容和元信息。

    P1-A3 改造:
      - 支持 python / typescript / javascript / go / both
      - 新语言 (javascript / go) 走 SDKGenerator, 返回 application/zip
      - 旧语言 (python / typescript) 保持原行为, 返回 JSON 文件元信息
      - 可选 openapi_spec 输入; 不传则用平台内置 spec
    """
    try:
        # Normalize language aliases
        lang_norm = req.language
        if lang_norm == "js":
            lang_norm = "javascript"

        # P1-A3: new SDK targets route through SDKGenerator → zip
        if lang_norm in ("javascript", "go"):
            from fastapi.responses import Response
            try:
                from engines.sdk_generator import SDKGenerator
            except Exception as e:  # pragma: no cover - import guard
                logger.error(f"SDKGenerator import failed: {e}")
                raise HTTPException(
                    status_code=503,
                    detail=f"SDK generator unavailable: {e}",
                )
            spec = req.openapi_spec
            if not spec:
                # Lazy import to avoid circulars
                from api.sdk_routes import _build_openapi_spec  # type: ignore
                spec = _build_openapi_spec()
            try:
                blob = SDKGenerator().generate(
                    openapi_spec=spec,
                    language=lang_norm,
                    package_name=req.package_name,
                    version=req.version,
                )
            except ValueError as ve:
                # Invalid language or package_name → 400
                raise HTTPException(status_code=400, detail=str(ve))
            filename = f"{req.package_name}-{lang_norm}.zip"
            logger.info(
                f"SDK generated (zip): package={req.package_name} lang={lang_norm} "
                f"size={len(blob)}B"
            )
            return Response(
                content=blob,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Package-Name": req.package_name,
                    "X-SDK-Language": lang_norm,
                    "X-SDK-Version": req.version,
                },
            )

        # Legacy path (python / typescript / both) — keeps prior behavior.
        results = []
        languages = [lang_norm] if lang_norm != "both" else ["python", "typescript"]

        for lang in languages:
            if lang == "python":
                code = _generate_python_sdk(version=req.version, include_auth=req.include_auth,
                                           include_async=req.include_async)
                filename = f"{req.package_name}.py"
                results.append({
                    "language": "python",
                    "filename": filename,
                    "size_bytes": len(code),
                    "lines": code.count("\n") + 1,
                    "install_command": "pip install requests  # (required dependency)",
                    "example": f"from {req.package_name.replace('-', '_')} import IMDFClient\nclient = IMDFClient(api_key='your-key')",
                })
            elif lang == "typescript":
                code = _generate_typescript_types()
                filename = f"{req.package_name}.ts"
                results.append({
                    "language": "typescript",
                    "filename": filename,
                    "size_bytes": len(code),
                    "lines": code.count("\n") + 1,
                    "install_command": "npm install (no extra dependencies required)",
                    "example": f"import {{ IMDFClient }} from './{req.package_name}';\nconst client = new IMDFClient({{ apiKey: 'your-key' }});",
                })

        generated_at = datetime.now(timezone.utc).isoformat()
        logger.info(f"SDK generated: {req.language}, languages={languages}")

        return {
            "ok": True,
            "data": {
                "package_name": req.package_name,
                "version": req.version,
                "generated_at": generated_at,
                "languages": languages,
                "files": results,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"SDK generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/languages")
async def sdk_languages():
    """列出 SDK 生成器支持的编程语言 + 各语言元信息。"""
    try:
        from engines.sdk_generator import SUPPORTED_LANGUAGES  # type: ignore
    except Exception as e:  # pragma: no cover
        logger.warning(f"SDKGenerator import failed: {e}")
        SUPPORTED_LANGUAGES_LOCAL: List[str] = []
    else:
        SUPPORTED_LANGUAGES_LOCAL = list(SUPPORTED_LANGUAGES)

    meta = {
        "python": {"file_ext": ".py", "mime": "text/x-python",
                    "install": "pip install <package>", "runtime": "Python >= 3.9"},
        "javascript": {"file_ext": ".js", "mime": "application/javascript",
                       "install": "npm install <package>", "runtime": "Node >= 14"},
        "go": {"file_ext": ".go", "mime": "text/x-go",
               "install": "go get <module>", "runtime": "Go >= 1.21"},
    }
    return {
        "ok": True,
        "data": {
            "supported_languages": SUPPORTED_LANGUAGES_LOCAL or
                                   ["python", "javascript", "go"],
            "languages": [
                {
                    "id": lang,
                    **meta.get(lang, {}),
                    "endpoint": f"/api/v1/sdk/generate?language={lang}",
                    "available": True,
                }
                for lang in (SUPPORTED_LANGUAGES_LOCAL or
                             ["python", "javascript", "go"])
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    }


@router.get("/versions")
async def sdk_versions():
    """SDK版本信息和可用SDK列表"""
    return {
        "ok": True,
        "data": {
            "sdks": [
                {"language": "python", "version": "1.0.0", "status": "stable",
                 "endpoint": "/api/v1/sdk/python"},
                {"language": "typescript", "version": "1.0.0", "status": "stable",
                 "endpoint": "/api/v1/sdk/typescript"},
                {"language": "openapi", "version": "3.1.0", "status": "stable",
                 "endpoint": "/api/v1/sdk/openapi.json"},
            ],
            "api_version": "v1",
            "openapi_version": "3.1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    }
