"""
F1.16 受控传输共享引擎 — Transfer Engine
=========================================
提供签名URL生成、密码保护、下载限制、分享链接管理的核心逻辑。

特性:
  - 生成HMAC签名的临时分享URL (防篡改)
  - SHA-256 密码哈希保护
  - 下载次数限制 (达到上限自动失效)
  - 过期时间自动清理
  - 支持 file / directory / dataset 多种资源类型
  - JSON文件持久化分享记录
"""

from __future__ import annotations
import os
import json
import hmac
import hashlib
import time
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class ShareLink:
    """分享链接数据模型"""
    token: str = ""
    resource_path: str = ""
    resource_type: str = "file"          # file | directory | dataset
    created_at: str = ""
    expires_at: int = 0                   # unix timestamp
    expires_at_iso: str = ""
    password_hash: Optional[str] = None
    max_downloads: int = 0               # 0 = unlimited
    downloads_used: int = 0
    signature: str = ""
    is_active: bool = True
    note: str = ""
    creator: str = ""                     # 创建者 (用户名/IP)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "resource_path": self.resource_path,
            "resource_type": self.resource_type,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expires_at_iso": self.expires_at_iso,
            "has_password": self.password_hash is not None,
            "max_downloads": self.max_downloads,
            "downloads_used": self.downloads_used,
            "is_active": self.is_active,
            "note": self.note,
            "creator": self.creator,
        }

    def remaining_downloads(self) -> int:
        """剩余下载次数 (-1 表示无限制)"""
        if self.max_downloads <= 0:
            return -1
        return max(0, self.max_downloads - self.downloads_used)

    def is_expired(self) -> bool:
        """检查是否已过期"""
        return time.time() > self.expires_at


@dataclass
class ShareAccessResult:
    """访问分享的结果"""
    granted: bool = False
    error: str = ""
    share: Optional[Dict[str, Any]] = None
    file_info: Optional[Dict[str, Any]] = None
    downloads_remaining: str = "unlimited"
    requires_password: bool = False


# ============================================================================
# TransferEngine Core
# ============================================================================

class TransferEngine:
    """受控传输共享引擎

    单例模式 — 使用 get_transfer_engine() 获取实例
    """

    _instance: Optional["TransferEngine"] = None

    def __new__(cls) -> "TransferEngine":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 存储路径
        self.store_dir = Path("data/sharing")
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.store_dir / "shares.json"

        # 签名密钥 (生产环境应从环境变量或密钥管理器读取)
        self.secret = os.environ.get("IMDF_SHARING_SECRET", "imdf-sharing-secret-key-2024")

        # 内存缓存 (减少文件IO)
        self._cache: Dict[str, dict] = {}
        self._cache_loaded = False

        logger.info("TransferEngine 初始化完成")

    # ─── 持久化 ─────────────────────────────────────────────────────────────

    def _load(self) -> Dict[str, dict]:
        """从JSON文件加载分享记录"""
        if self._cache_loaded:
            return self._cache

        if self.meta_file.exists():
            try:
                self._cache = json.loads(self.meta_file.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}
        else:
            self._cache = {}
        self._cache_loaded = True
        return self._cache

    def _save(self):
        """保存分享记录到JSON文件"""
        self.meta_file.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def _reload(self):
        """强制重新加载"""
        self._cache_loaded = False
        self._load()

    # ─── 签名 ───────────────────────────────────────────────────────────────

    def generate_signature(self, token: str, expiry: int, resource: str) -> str:
        """生成HMAC-SHA256签名 (取前16字符)"""
        message = f"{token}:{expiry}:{resource}"
        sig = hmac.new(
            self.secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:16]
        return sig

    def verify_signature(self, token: str, expiry: int, resource: str, signature: str) -> bool:
        """验证签名"""
        expected = self.generate_signature(token, expiry, resource)
        return hmac.compare_digest(expected, signature)

    # ─── 密码 ───────────────────────────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """对密码进行SHA-256哈希"""
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码 (常数时间比较)"""
        return hmac.compare_digest(
            hashlib.sha256(password.encode()).hexdigest(),
            password_hash
        )

    # ─── 清理 ───────────────────────────────────────────────────────────────

    def cleanup_expired(self) -> int:
        """清理过期分享记录, 返回清理数量"""
        shares = self._load()
        now = time.time()
        expired_tokens = [
            t for t, s in shares.items()
            if s.get("expires_at", 0) < now
        ]
        for t in expired_tokens:
            del shares[t]
        if expired_tokens:
            self._save()
            logger.info(f"清理了 {len(expired_tokens)} 条过期分享记录")
        return len(expired_tokens)

    # ─── 创建分享 ─────────────────────────────────────────────────────────────

    def create_share(
        self,
        resource_path: str,
        resource_type: str = "file",
        password: Optional[str] = None,
        expiry_hours: int = 24,
        max_downloads: int = 0,
        note: str = "",
        creator: str = "",
    ) -> Dict[str, Any]:
        """创建受控分享链接

        Args:
            resource_path: 资源路径 (文件/目录)
            resource_type: 资源类型 (file/directory/dataset)
            password: 访问密码 (可选)
            expiry_hours: 有效时长 (小时)
            max_downloads: 最大下载次数 (0=无限制)
            note: 备注
            creator: 创建者标识

        Returns:
            包含 token, share_url, expires_at 等信息的字典

        Raises:
            ValueError: resource_path 为空
            FileNotFoundError: 文件资源不存在
        """
        if not resource_path:
            raise ValueError("resource_path is required")

        # 验证资源存在 (仅文件类型严格检查)
        if resource_type == "file":
            full_path = Path(resource_path)
            if not full_path.exists():
                raise FileNotFoundError(f"Resource not found: {resource_path}")

        # 生成唯一 token
        token = uuid.uuid4().hex[:12]
        now = time.time()
        expiry_ts = int(now + expiry_hours * 3600)

        # 生成签名
        signature = self.generate_signature(token, expiry_ts, resource_path)

        # 密码哈希
        password_hash = None
        if password:
            password_hash = self.hash_password(password)

        # 构建记录
        created_at_iso = datetime.fromtimestamp(now).isoformat()
        expires_at_iso = datetime.fromtimestamp(expiry_ts).isoformat()

        share_record = {
            "token": token,
            "resource_path": resource_path,
            "resource_type": resource_type,
            "created_at": created_at_iso,
            "expires_at": expiry_ts,
            "expires_at_iso": expires_at_iso,
            "password_hash": password_hash,
            "max_downloads": max_downloads,
            "downloads_used": 0,
            "signature": signature,
            "is_active": True,
            "note": note,
            "creator": creator,
        }

        # 持久化
        shares = self._load()
        shares[token] = share_record
        self._save()

        # 构造分享URL
        share_url = f"/api/transfer/{token}?sig={signature}&exp={expiry_ts}"

        logger.info(
            "share_created",
            token=token,
            resource=resource_path,
            expiry_hours=expiry_hours,
            has_password=password is not None,
            max_downloads=max_downloads,
        )

        return {
            "token": token,
            "share_url": share_url,
            "resource_path": resource_path,
            "resource_type": resource_type,
            "created_at": created_at_iso,
            "expires_at": expires_at_iso,
            "expires_in_hours": expiry_hours,
            "has_password": password is not None,
            "max_downloads": max_downloads,
            "note": note,
        }

    # ─── 访问分享 ─────────────────────────────────────────────────────────────

    def access_share(
        self,
        token: str,
        signature: str = "",
        password: str = "",
        increment_download: bool = True,
    ) -> ShareAccessResult:
        """访问分享内容

        完整验证流程:
        1. 分享存在且活跃
        2. 未过期
        3. 签名校验 (防篡改)
        4. 密码验证 (如设置)
        5. 下载限制检查

        Args:
            token: 分享token
            signature: URL中的签名
            password: 访问密码
            increment_download: 是否增加下载计数

        Returns:
            ShareAccessResult (granted, error, file_info 等)
        """
        shares = self._load()
        share = shares.get(token)
        result = ShareAccessResult()

        if not share:
            result.error = "分享不存在或已过期"
            return result

        # 1. 活跃检查
        if not share.get("is_active", False):
            result.error = "分享已被撤销"
            return result

        # 2. 过期检查
        now = time.time()
        if share.get("expires_at", 0) < now:
            share["is_active"] = False
            self._save()
            result.error = "分享链接已过期"
            return result

        # 3. 签名验证
        if signature:
            if not self.verify_signature(
                token,
                share["expires_at"],
                share["resource_path"],
                signature
            ):
                result.error = "签名无效"
                return result

        # 4. 密码验证
        if share.get("password_hash"):
            result.requires_password = True
            if not password:
                result.error = "需要密码访问"
                return result
            if not self.verify_password(password, share["password_hash"]):
                result.error = "密码错误"
                return result

        # 5. 下载限制
        max_dl = share.get("max_downloads", 0)
        dl_used = share.get("downloads_used", 0)
        if max_dl > 0 and dl_used >= max_dl:
            result.error = "已达到下载次数上限"
            return result

        # 更新下载计数
        if increment_download:
            share["downloads_used"] = dl_used + 1
            self._save()

        # 构建资源信息
        resource_path = share["resource_path"]
        full_path = Path(resource_path)
        file_info = self._build_file_info(full_path)

        result.granted = True
        result.share = share
        result.file_info = file_info
        result.downloads_remaining = (
            str(max_dl - share["downloads_used"])
            if max_dl > 0 else "unlimited"
        )

        return result

    def _build_file_info(self, full_path: Path) -> Dict[str, Any]:
        """构建资源文件信息"""
        info: Dict[str, Any] = {}
        if full_path.exists():
            if full_path.is_file():
                stat = full_path.stat()
                size = stat.st_size
                if size < 1024 * 1024:
                    size_human = f"{size / 1024:.1f} KB"
                else:
                    size_human = f"{size / 1024 / 1024:.1f} MB"
                info = {
                    "name": full_path.name,
                    "size": size,
                    "size_human": size_human,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "file",
                }
            elif full_path.is_dir():
                children = list(full_path.iterdir())[:50]
                info = {
                    "name": full_path.name,
                    "type": "directory",
                    "children_count": len(children),
                    "children": [
                        {"name": c.name, "type": "dir" if c.is_dir() else "file"}
                        for c in children
                    ],
                }
        return info

    # ─── 列出分享 ─────────────────────────────────────────────────────────────

    def list_shares(self, creator: str = "") -> List[Dict[str, Any]]:
        """列出活跃分享

        Args:
            creator: 可选过滤创建者

        Returns:
            活跃分享列表
        """
        self.cleanup_expired()
        shares = self._load()
        active = []

        for token, share in shares.items():
            if not share.get("is_active", False):
                continue
            if creator and share.get("creator", "") != creator:
                continue

            active.append({
                "token": token,
                "resource_path": share["resource_path"],
                "resource_type": share["resource_type"],
                "created_at": share["created_at"],
                "expires_at": share.get("expires_at_iso", ""),
                "has_password": share.get("password_hash") is not None,
                "downloads_used": share.get("downloads_used", 0),
                "max_downloads": share.get("max_downloads", 0),
                "note": share.get("note", ""),
                "creator": share.get("creator", ""),
            })

        return active

    # ─── 撤销/删除分享 ────────────────────────────────────────────────────────

    def revoke_share(self, token: str) -> bool:
        """撤销分享 (软删除 — 设为 inactive)

        Returns:
            True 如果成功撤销, False 如果分享不存在
        """
        shares = self._load()
        if token not in shares:
            return False

        shares[token]["is_active"] = False
        self._save()

        logger.info("share_revoked", token=token)
        return True

    def delete_share(self, token: str) -> bool:
        """永久删除分享记录

        Returns:
            True 如果成功删除, False 如果分享不存在
        """
        shares = self._load()
        if token in shares:
            del shares[token]
            self._save()
            logger.info("share_deleted", token=token)
            return True
        return False

    # ─── 分享ID查找 ───────────────────────────────────────────────────────────

    def find_by_id(self, share_id: str) -> Optional[Dict[str, Any]]:
        """通过ID(token)查找分享"""
        shares = self._load()
        return shares.get(share_id)

    def find_by_resource(self, resource_path: str) -> List[Dict[str, Any]]:
        """通过资源路径查找分享"""
        shares = self._load()
        return [
            s for s in shares.values()
            if s.get("resource_path") == resource_path and s.get("is_active", False)
        ]


# ============================================================================
# Singleton Accessor
# ============================================================================

def get_transfer_engine() -> TransferEngine:
    """获取TransferEngine单例"""
    return TransferEngine()
