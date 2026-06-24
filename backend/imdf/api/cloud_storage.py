"""
IMDF Cloud Storage API — Universal Cloud Storage Interface (OSS/COS)
===================================================
Port source: Penguin Canvas v2.1.4 cloudUploads

Supported:
  - Tencent COS (V5 HMAC-SHA1 signing)
  - Alibaba OSS (Header Authorization signing)
  - Connectivity check (signed GET)
  - File upload
  - Object key generation (configurable prefix template)
  - Error classification and diagnostics

Endpoints:
  GET    /api/cloud/storage/status    — Get all cloud storage configuration status
  POST   /api/cloud/storage/settings  — Update cloud storage configuration
  POST   /api/cloud/storage/test      — Test single target connectivity
  POST   /api/cloud/storage/upload    — Upload file to cloud storage
"""

import os
import json
import logging
import hashlib
import hmac
import time
import re
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime

import httpx

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.platform_config import get_data_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cloud", tags=["cloud_storage"])


# ============================================================================
# Type definitions
# ============================================================================

CLOUD_PROVIDERS = {"tencent-cos", "aliyun-oss"}

MIME_BY_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".avif": "image/avif", ".mp4": "video/mp4", ".webm": "video/webm",
    ".mov": "video/quicktime", ".m4v": "video/mp4", ".mkv": "video/x-matroska",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".flac": "audio/flac", ".aac": "audio/aac",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".obj": "model/obj", ".fbx": "model/fbx", ".stl": "model/stl",
    ".usdz": "model/vnd.usdz+zip",
}


@dataclass
class CloudTargetConfig:
    """Cloud target configuration"""
    id: str = ""
    provider: str = "tencent-cos"
    label: str = "云存储"
    enabled: bool = False
    prefix: str = "imdf/{kind}/{yyyy-mm}"
    public_base_url: str = ""

    # 腾讯云 COS
    cos_bucket: str = ""
    cos_region: str = "ap-guangzhou"
    cos_secret_id: str = ""
    cos_secret_key: str = ""

    # 阿里云 OSS
    oss_bucket: str = ""
    oss_endpoint: str = "oss-cn-hangzhou.aliyuncs.com"
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        if mask_secrets:
            if d.get("cos_secret_id"):
                d["cos_secret_id"] = d["cos_secret_id"][:6] + "****"
            if d.get("cos_secret_key"):
                d["cos_secret_key"] = "****" if d["cos_secret_key"] else ""
            if d.get("oss_access_key_id"):
                d["oss_access_key_id"] = d["oss_access_key_id"][:6] + "****"
            if d.get("oss_access_key_secret"):
                d["oss_access_key_secret"] = "****" if d["oss_access_key_secret"] else ""
        return d


# 默认配置
DEFAULT_TARGETS = [
    CloudTargetConfig(
        id="tencent-cos", provider="tencent-cos", label="腾讯云 COS",
        prefix="imdf/{kind}/{yyyy-mm}",
    ),
    CloudTargetConfig(
        id="aliyun-oss", provider="aliyun-oss", label="阿里云 OSS",
        prefix="imdf/{kind}/{yyyy-mm}",
    ),
]


# ============================================================================
# Configuration storage
# ============================================================================

SETTINGS_DIR = str(get_data_root())
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "cloud_storage.json")


def load_settings() -> Dict[str, Any]:
    """Load cloud storage settings"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Load cloud storage settings失败: {e}")
    return {"targets": []}


def save_settings(data: Dict[str, Any]):
    """Save cloud storage settings"""
    os.makedirs(SETTINGS_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_targets() -> List[CloudTargetConfig]:
    """Get configured cloud storage targets"""
    raw = load_settings().get("targets", [])
    targets = []
    for item in raw:
        try:
            targets.append(CloudTargetConfig(**item))
        except Exception as e:
            logger.warning(f"解析云存储目标失败: {e}")
    return targets or [CloudTargetConfig(**asdict(d)) for d in DEFAULT_TARGETS]


def save_targets(targets: List[CloudTargetConfig]):
    """保存云存储目标"""
    save_settings({"targets": [asdict(t) for t in targets]})


# ============================================================================
# COS Signing (Tencent Cloud)
# ============================================================================

def cos_host(cfg: CloudTargetConfig) -> str:
    return f"{cfg.cos_bucket}.cos.{cfg.cos_region}.myqcloud.com"


def sha1_hex(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def hmac_sha1_hex(key: str, value: str) -> str:
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha1).hexdigest()


def hmac_sha1_base64(key: str, value: str) -> str:
    import base64
    return base64.b64encode(
        hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")


def strict_encode(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def canonical_query(params: Dict[str, str]) -> str:
    items = sorted(
        (k.lower(), v) for k, v in params.items()
        if k and v is not None
    )
    return "&".join(f"{strict_encode(k)}={strict_encode(v)}" for k, v in items)


def query_key_list(params: Dict[str, str]) -> str:
    keys = sorted(k.lower() for k in params if k)
    return ";".join(strict_encode(k) for k in keys)


def sign_cos_request(
    method: str, host: str, uri_path: str = "/",
    query: Dict[str, str] = None,
    secret_id: str = "", secret_key: str = "",
    expires_seconds: int = 900,
) -> str:
    """COS V5 HMAC-SHA1 签名"""
    query = query or {}
    now = int(time.time())
    key_time = f"{now};{now + expires_seconds}"
    normalized_method = method.lower()
    normalized_path = uri_path if uri_path.startswith("/") else f"/{uri_path}"
    url_param_string = canonical_query(query)
    url_param_list = query_key_list(query)
    header_string = f"host={host.lower()}\n"
    http_string = f"{normalized_method}\n{normalized_path}\n{url_param_string}\n{header_string}"
    string_to_sign = f"sha1\n{key_time}\n{sha1_hex(http_string)}\n"
    sign_key = hmac_sha1_hex(secret_key, key_time)
    signature = hmac_sha1_hex(sign_key, string_to_sign)
    return (
        "q-sign-algorithm=sha1"
        f"&q-ak={strict_encode(secret_id)}"
        f"&q-sign-time={key_time}"
        f"&q-key-time={key_time}"
        "&q-header-list=host"
        f"&q-url-param-list={url_param_list}"
        f"&q-signature={signature}"
    )


# ============================================================================
# OSS Signing (Alibaba Cloud)
# ============================================================================

def normalize_oss_endpoint(endpoint: str) -> str:
    e = endpoint.strip().replace("https://", "").replace("http://", "").rstrip("/")
    if re.match(r"^oss-[a-z0-9-]+$", e, re.I):
        return f"{e}.aliyuncs.com"
    if re.match(r"^(cn|ap|us|eu|me)-[a-z0-9-]+$", e, re.I):
        return f"oss-{e}.aliyuncs.com"
    return e


def oss_host(cfg: CloudTargetConfig) -> str:
    endpoint = normalize_oss_endpoint(cfg.oss_endpoint)
    return f"{cfg.oss_bucket}.{endpoint}"


def oss_subresource(query: Dict[str, str]) -> str:
    items = sorted(
        k for k in query if k
    )
    result = []
    for key in items:
        v = query[key]
        if v == "" or v is None:
            result.append(key)
        else:
            result.append(f"{key}={v}")
    return "&".join(result)


def sign_oss_authorization(
    method: str, bucket: str, object_key: str = "",
    query: Dict[str, str] = None,
    access_key_id: str = "", access_key_secret: str = "",
    date: str = "", content_md5: str = "", content_type: str = "",
) -> str:
    """OSS Header Authorization 签名"""
    query = query or {}
    subresources = oss_subresource(query)
    canonical_resource = f"/{bucket}/{object_key}"
    if subresources:
        canonical_resource += f"?{subresources}"
    string_to_sign = (
        f"{method.upper()}\n{content_md5}\n{content_type}\n{date}\n"
        f"{canonical_resource}"
    )
    signature = hmac_sha1_base64(access_key_secret, string_to_sign)
    return f"OSS {access_key_id}:{signature}"


# ============================================================================
# Utility functions
# ============================================================================

def kind_from_ext(ext: str) -> str:
    ext_clean = ext.lower().lstrip(".")
    img = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"}
    vid = {"mp4", "webm", "mov", "m4v", "mkv", "avi"}
    aud = {"mp3", "wav", "ogg", "m4a", "flac", "aac"}
    if ext_clean in img:
        return "image"
    if ext_clean in vid:
        return "video"
    if ext_clean in aud:
        return "audio"
    if ext_clean in {"glb", "gltf", "obj", "fbx", "stl", "usdz"}:
        return "model3d"
    return "file"


def build_object_key(cfg: CloudTargetConfig, filename: str,
                      kind: str = "file") -> str:
    """Build object storage path"""
    now = datetime.now()
    prefix = cfg.prefix or "imdf/{kind}/{yyyy-mm}"
    prefix = (
        prefix.replace("{kind}", kind)
        .replace("{yyyy-mm}", now.strftime("%Y-%m"))
        .replace("{date}", now.strftime("%Y-%m-%d"))
        .replace("\\", "/")
        .strip("/")
    )
    # 文件名加时间戳防重
    base, ext = os.path.splitext(filename)
    unique_name = f"{base}_{int(time.time())}{ext}"
    key = f"{prefix}/{unique_name}".replace("//", "/")
    return key


def extract_xml_tag(text: str, tag: str) -> str:
    m = re.search(f"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


# ============================================================================
# Core operations
# ============================================================================

async def test_connectivity(cfg: CloudTargetConfig) -> Dict[str, Any]:
    """Test cloud storage connectivity (signed GET)"""
    if cfg.provider == "tencent-cos":
        host = cos_host(cfg)
        url = f"https://{host}/?location"
        auth = sign_cos_request("GET", host, "/", {"location": ""},
                                 cfg.cos_secret_id, cfg.cos_secret_key)
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, headers={"Authorization": auth})
            if resp.status_code < 400:
                return {"ok": True, "provider": "tencent-cos",
                        "bucket": cfg.cos_bucket, "region": cfg.cos_region}
            else:
                text = resp.text
                code = extract_xml_tag(text, "Code") or extract_xml_tag(text, "ErrorCode")
                msg = extract_xml_tag(text, "Message")
                raise Exception(f"连通测试失败: {code} {msg}" if code else f"HTTP {resp.status_code}")

    elif cfg.provider == "aliyun-oss":
        host = oss_host(cfg)
        url = f"https://{host}/?location"
        import email.utils
        date = email.utils.formatdate(usegmt=True)
        auth = sign_oss_authorization("GET", cfg.oss_bucket, "",
                                       {"location": ""},
                                       cfg.oss_access_key_id, cfg.oss_access_key_secret,
                                       date=date)
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, headers={
                "Authorization": auth,
                "Date": date,
            })
            if resp.status_code < 400:
                return {"ok": True, "provider": "aliyun-oss",
                        "bucket": cfg.oss_bucket, "endpoint": cfg.oss_endpoint}
            else:
                raise Exception(f"连通测试失败: HTTP {resp.status_code}")

    else:
        raise Exception(f"不支持的云存储提供商: {cfg.provider}")


async def upload_file(cfg: CloudTargetConfig, local_path: str,
                       filename: Optional[str] = None,
                       kind: Optional[str] = None) -> Dict[str, Any]:
    """Upload file to cloud storage"""
    if not os.path.exists(local_path):
        raise Exception(f"本地文件不存在: {local_path}")

    fname = filename or os.path.basename(local_path)
    ext = os.path.splitext(fname)[1].lower()
    fkind = kind or kind_from_ext(ext)
    object_key = build_object_key(cfg, fname, fkind)

    if cfg.provider == "tencent-cos":
        host = cos_host(cfg)
        url = f"https://{host}/{object_key}"
        auth = sign_cos_request("PUT", host, f"/{object_key}",
                                 cfg.cos_secret_id, cfg.cos_secret_key)

        async with httpx.AsyncClient(timeout=120) as client:
            with open(local_path, "rb") as f:
                resp = await client.put(url, content=f, headers={
                    "Authorization": auth,
                    "Content-Type": MIME_BY_EXT.get(ext, "application/octet-stream"),
                })
            if resp.status_code < 400:
                public_url = f"{cfg.public_base_url}/{object_key}" if cfg.public_base_url else url
                return {"ok": True, "provider": "tencent-cos",
                        "object_key": object_key, "url": public_url}
            else:
                raise Exception(f"上传失败: HTTP {resp.status_code}")

    elif cfg.provider == "aliyun-oss":
        host = oss_host(cfg)
        url = f"https://{host}/{object_key}"
        import email.utils
        date = email.utils.formatdate(usegmt=True)
        auth = sign_oss_authorization("PUT", cfg.oss_bucket, object_key,
                                       access_key_id=cfg.oss_access_key_id,
                                       access_key_secret=cfg.oss_access_key_secret,
                                       date=date)

        async with httpx.AsyncClient(timeout=120) as client:
            with open(local_path, "rb") as f:
                resp = await client.put(url, content=f, headers={
                    "Authorization": auth,
                    "Date": date,
                    "Content-Type": MIME_BY_EXT.get(ext, "application/octet-stream"),
                })
            if resp.status_code < 400:
                public_url = f"{cfg.public_base_url}/{object_key}" if cfg.public_base_url else url
                return {"ok": True, "provider": "aliyun-oss",
                        "object_key": object_key, "url": public_url}
            else:
                raise Exception(f"上传失败: HTTP {resp.status_code}")

    else:
        raise Exception(f"不支持的云存储提供商: {cfg.provider}")


# ============================================================================
# FastAPI endpoints
# ============================================================================

class SettingsUpdateRequest(BaseModel):
    targets: List[Dict[str, Any]] = []


class TestRequest(BaseModel):
    target_id: str = ""


class UploadRequest(BaseModel):
    target_id: str = ""
    local_path: str = ""
    filename: Optional[str] = None
    kind: Optional[str] = None


@router.get("/storage/status")
async def get_storage_status():
    """Get all cloud storage configuration status"""
    targets = get_targets()
    return {
        "success": True,
        "data": {
            "targets": [t.to_dict(mask_secrets=True) for t in targets],
            "summary": f"已配置 {len([t for t in targets if t.enabled])}/{len(targets)} 个目标",
        },
    }


@router.post("/storage/settings")
async def update_storage_settings(req: SettingsUpdateRequest):
    """Update cloud storage configuration"""
    targets = []
    for item in req.targets:
        try:
            targets.append(CloudTargetConfig(**item))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"配置格式错误: {e}")
    save_targets(targets)
    return {"success": True, "message": "配置已保存"}


@router.post("/storage/test")
async def test_storage(req: TestRequest):
    """Test single target connectivity"""
    targets = get_targets()
    target = next((t for t in targets if t.id == req.target_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    if not target.enabled:
        raise HTTPException(status_code=400, detail="目标未启用")
    try:
        result = await test_connectivity(target)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/storage/upload")
async def upload_to_storage(req: UploadRequest):
    """Upload file to cloud storage"""
    targets = get_targets()
    target = next((t for t in targets if t.id == req.target_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    if not target.enabled:
        raise HTTPException(status_code=400, detail="目标未启用")
    try:
        result = await upload_file(target, req.local_path, req.filename, req.kind)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
