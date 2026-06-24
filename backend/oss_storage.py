#!/usr/bin/env python3
"""
Nanobot Factory - Aliyun OSS Storage Integration
阿里云OSS对象存储集成 - 商业级数据管理核心模块

@author MiniMax Agent
@date 2026-03-03
@description 
- 支持图片/视频上传到阿里云OSS
- 支持云端文件管理和元数据同步
- 支持预签名URL生成
- 支持CDN加速
- 支持生命周期管理
"""

import os
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import base64

logger = logging.getLogger(__name__)


class StorageType(Enum):
    """存储类型枚举"""
    LOCAL = "local"
    OSS = "oss"
    OSS_CDN = "oss_cdn"  # CDN加速


class FileType(Enum):
    """文件类型枚举"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    MODEL = "model"
    DATASET = "dataset"
    OTHER = "other"


@dataclass
class OSSConfig:
    """OSS配置"""
    access_key_id: str = ""
    access_key_secret: str = ""
    bucket_name: str = ""
    endpoint: str = ""
    region: str = ""
    cdn_domain: str = ""  # CDN加速域名
    enabled: bool = False
    
    # 路径配置
    image_prefix: str = "assets/images/"
    video_prefix: str = "assets/videos/"
    audio_prefix: str = "assets/audios/"
    dataset_prefix: str = "datasets/"
    thumbnail_prefix: str = "thumbnails/"
    
    # 生命周期配置
    auto_delete_days: int = 0  # 0表示不自动删除
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OSSConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_key_id": self.access_key_id[:4] + "****" if self.access_key_id else "",
            "access_key_secret": "****" if self.access_key_secret else "",
            "bucket_name": self.bucket_name,
            "endpoint": self.endpoint,
            "region": self.region,
            "cdn_domain": self.cdn_domain,
            "enabled": self.enabled,
        }


@dataclass
class OSSFileInfo:
    """OSS文件信息"""
    key: str
    file_name: str
    file_type: FileType
    size: int
    content_type: str
    url: str
    cdn_url: str = ""
    oss_path: str = ""
    local_path: str = ""
    storage_type: StorageType = StorageType.LOCAL
    etag: str = ""
    last_modified: str = ""
    width: int = 0
    height: int = 0
    duration: int = 0  # 视频/音频时长(秒)
    thumbnail_key: str = ""
    thumbnail_url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "file_name": self.file_name,
            "file_type": self.file_type.value,
            "size": self.size,
            "content_type": self.content_type,
            "url": self.url,
            "cdn_url": self.cdn_url,
            "oss_path": self.oss_path,
            "local_path": self.local_path,
            "storage_type": self.storage_type.value,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "width": self.width,
            "height": self.height,
            "duration": self.duration,
            "thumbnail_key": self.thumbnail_key,
            "thumbnail_url": self.thumbnail_url,
            "metadata": self.metadata,
        }


class OSSStorageManager:
    """
    阿里云OSS存储管理器
    支持本地存储和云端OSS的双模式管理
    """
    
    def __init__(self, config: Optional[OSSConfig] = None, local_storage_path: str = "./storage"):
        self.config = config or OSSConfig()
        self.local_storage_path = local_storage_path
        self.oss_client = None
        self._oss_initialized = False
        
        # 本地存储路径
        self.local_paths = {
            FileType.IMAGE: os.path.join(local_storage_path, "images"),
            FileType.VIDEO: os.path.join(local_storage_path, "videos"),
            FileType.AUDIO: os.path.join(local_storage_path, "audios"),
            FileType.DOCUMENT: os.path.join(local_storage_path, "documents"),
            FileType.MODEL: os.path.join(local_storage_path, "models"),
            FileType.DATASET: os.path.join(local_storage_path, "datasets"),
        }
        
        # 初始化本地存储目录
        self._init_local_paths()
    
    def _init_local_paths(self):
        """初始化本地存储目录"""
        for path in self.local_paths.values():
            os.makedirs(path, exist_ok=True)
        logger.info(f"Local storage initialized at: {self.local_storage_path}")
    
    def _init_oss_client(self) -> bool:
        """初始化OSS客户端"""
        if self._oss_initialized:
            return True
            
        if not self.config.enabled:
            logger.info("OSS not enabled, using local storage only")
            return False
            
        try:
            import oss2
            
            auth = oss2.Auth(self.config.access_key_id, self.config.access_key_secret)
            self.oss_client = oss2.Bucket(
                auth,
                self.config.endpoint,
                self.config.bucket_name
            )
            self._oss_initialized = True
            logger.info(f"OSS client initialized: {self.config.bucket_name}")
            return True
        except ImportError:
            logger.error("oss2 package not installed. Install with: pip install oss2")
            return False
        except Exception as e:
            logger.error(f"Failed to initialize OSS client: {e}")
            return False
    
    def get_file_type(self, file_name: str, content_type: str = "") -> FileType:
        """根据文件名和内容类型判断文件类型"""
        ext = os.path.splitext(file_name)[1].lower()
        
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.ico'}
        video_exts = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}
        audio_exts = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}
        doc_exts = {'.pdf', '.doc', '.docx', '.txt', '.md', '.csv', '.json', '.xml'}
        model_exts = {'.pt', '.pth', '.ckpt', '.safetensors', '.onnx', '.h5', '.pb'}
        
        if ext in image_exts or 'image' in content_type.lower():
            return FileType.IMAGE
        elif ext in video_exts or 'video' in content_type.lower():
            return FileType.VIDEO
        elif ext in audio_exts or 'audio' in content_type.lower():
            return FileType.AUDIO
        elif ext in doc_exts or 'document' in content_type.lower():
            return FileType.DOCUMENT
        elif ext in model_exts:
            return FileType.MODEL
        else:
            return FileType.OTHER
    
    def get_prefix_for_type(self, file_type: FileType) -> str:
        """获取指定文件类型的存储前缀"""
        prefix_map = {
            FileType.IMAGE: self.config.image_prefix,
            FileType.VIDEO: self.config.video_prefix,
            FileType.AUDIO: self.config.audio_prefix,
            FileType.DATASET: self.config.dataset_prefix,
        }
        return prefix_map.get(file_type, "assets/others/")
    
    def generate_key(self, file_name: str, file_type: FileType) -> str:
        """生成唯一的OSS文件Key"""
        timestamp = datetime.now().strftime("%Y%m%d")
        hash_value = hashlib.md5(f"{file_name}{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        prefix = self.get_prefix_for_type(file_type)
        return f"{prefix}{timestamp}_{hash_value}_{file_name}"
    
    def generate_thumbnail_key(self, original_key: str) -> str:
        """生成缩略图Key"""
        base, ext = os.path.splitext(original_key)
        return f"{self.config.thumbnail_prefix}{os.path.basename(base)}_thumb.jpg"
    
    async def upload_file(
        self,
        file_path: str,
        file_type: Optional[FileType] = None,
        custom_key: Optional[str] = None,
        generate_thumbnail: bool = True,
    ) -> Tuple[bool, OSSFileInfo]:
        """
        上传文件到存储
        
        Args:
            file_path: 本地文件路径
            file_type: 文件类型，不指定则自动识别
            custom_key: 自定义存储Key
            generate_thumbnail: 是否生成缩略图
            
        Returns:
            (success, file_info)
        """
        if not os.path.exists(file_path):
            return False, OSSFileInfo(
                key="",
                file_name=os.path.basename(file_path),
                file_type=FileType.OTHER,
                size=0,
                content_type="",
                url="",
            )
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 自动识别文件类型
        if file_type is None:
            file_type = self.get_file_type(file_name)
        
        # 生成存储Key
        storage_key = custom_key or self.generate_key(file_name, file_type)
        
        # 本地存储路径
        local_path = os.path.join(self.local_paths.get(file_type, self.local_storage_path), storage_key.replace("/", os.sep))
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        
        # 复制文件到本地存储
        import shutil
        shutil.copy2(file_path, local_path)
        
        result = OSSFileInfo(
            key=storage_key,
            file_name=file_name,
            file_type=file_type,
            size=file_size,
            content_type=self._get_content_type(file_name),
            url=f"/storage/{storage_key}",
            local_path=local_path,
            storage_type=StorageType.LOCAL,
            last_modified=datetime.now().isoformat(),
        )
        
        # 如果OSS可用，同步上传到OSS
        if self._init_oss_client() and self.oss_client:
            try:
                result = await self._upload_to_oss(local_path, storage_key, result, generate_thumbnail)
            except Exception as e:
                logger.warning(f"Failed to upload to OSS, using local only: {e}")
        
        return True, result
    
    async def upload_bytes(
        self,
        content: bytes,
        file_name: str,
        file_type: Optional[FileType] = None,
        custom_key: Optional[str] = None,
    ) -> Tuple[bool, OSSFileInfo]:
        """上传字节内容到存储"""
        import tempfile
        
        # 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            return await self.upload_file(temp_path, file_type, custom_key, generate_thumbnail=False)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    async def _upload_to_oss(
        self,
        local_path: str,
        key: str,
        file_info: OSSFileInfo,
        generate_thumbnail: bool,
    ) -> OSSFileInfo:
        """上传文件到OSS并更新文件信息"""
        import oss2
        
        with open(local_path, 'rb') as f:
            result = self.oss_client.put_object(key, f)
        
        file_info.oss_path = key
        file_info.etag = result.etag
        file_info.storage_type = StorageType.OSS
        
        # 生成OSS URL
        file_info.url = f"https://{self.config.bucket_name}.{self.config.endpoint}/{key}"
        
        # 如果配置了CDN，生成CDN URL
        if self.config.cdn_domain:
            file_info.cdn_url = f"https://{self.config.cdn_domain}/{key}"
            file_info.url = file_info.cdn_url
        
        # 生成缩略图
        if generate_thumbnail and file_info.file_type == FileType.IMAGE:
            thumb_key = self.generate_thumbnail_key(key)
            try:
                thumb_created = await self._generate_thumbnail(local_path, thumb_key)
                if thumb_created:
                    file_info.thumbnail_key = thumb_key
                    file_info.thumbnail_url = f"https://{self.config.cdn_domain or self.config.bucket_name + '.' + self.config.endpoint}/{thumb_key}"
            except Exception as e:
                logger.warning(f"Failed to generate thumbnail: {e}")
        
        return file_info
    
    async def _generate_thumbnail(self, image_path: str, thumb_key: str) -> bool:
        """生成并上传缩略图"""
        try:
            from PIL import Image
            
            with Image.open(image_path) as img:
                # 计算缩略图尺寸
                thumb_size = (256, 256)
                img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
                
                # 保存到临时文件
                import tempfile
                temp_thumb = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                img.convert('RGB').save(temp_thumb.name, 'JPEG', quality=85)
                temp_thumb.close()
                
                # 上传到OSS
                with open(temp_thumb.name, 'rb') as f:
                    self.oss_client.put_object(thumb_key, f)
                
                os.remove(temp_thumb.name)
                return True
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")
            return False
    
    def _get_content_type(self, file_name: str) -> str:
        """获取文件MIME类型"""
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_name)
        return content_type or 'application/octet-stream'
    
    async def download_file(self, key: str, dest_path: str) -> Tuple[bool, str]:
        """从存储下载文件"""
        local_path = os.path.join(self.local_storage_path, key.replace("/", os.sep))
        
        # 先检查本地
        if os.path.exists(local_path):
            import shutil
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(local_path, dest_path)
            return True, dest_path
        
        # 检查OSS
        if self._init_oss_client() and self.oss_client:
            try:
                import oss2
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                result = self.oss_client.get_object_to_file(key, dest_path)
                return True, dest_path
            except oss2.exceptions.NoSuchKey:
                return False, ""
            except Exception as e:
                logger.error(f"OSS download failed: {e}")
        
        return False, ""
    
    async def delete_file(self, key: str) -> bool:
        """删除存储的文件"""
        # 删除本地文件
        local_path = os.path.join(self.local_storage_path, key.replace("/", os.sep))
        if os.path.exists(local_path):
            os.remove(local_path)
        
        # 删除OSS文件
        if self._init_oss_client() and self.oss_client:
            try:
                self.oss_client.delete_object(key)
                # 删除缩略图
                thumb_key = self.generate_thumbnail_key(key)
                self.oss_client.delete_object(thumb_key)
            except Exception as e:
                logger.warning(f"Failed to delete from OSS: {e}")
        
        return True
    
    def get_signed_url(self, key: str, expires: int = 3600) -> str:
        """获取预签名URL（用于私有bucket访问）"""
        if self._init_oss_client() and self.oss_client:
            try:
                from oss2.exceptions import NoSuchKey
                return self.oss_client.sign_url('GET', key, expires)
            except Exception as e:
                logger.warning(f"Failed to generate signed URL: {e}")
        return ""
    
    async def list_files(
        self,
        prefix: str = "",
        max_keys: int = 100,
        marker: str = "",
    ) -> Tuple[List[OSSFileInfo], str]:
        """列出存储的文件"""
        files = []
        next_marker = ""
        
        if self._init_oss_client() and self.oss_client:
            try:
                import oss2
                result = self.oss_client.list_objects(
                    prefix,
                    max_keys=max_keys,
                    marker=marker
                )
                
                for obj in result.object_list:
                    file_info = OSSFileInfo(
                        key=obj.key,
                        file_name=os.path.basename(obj.key),
                        file_type=self.get_file_type(os.path.basename(obj.key)),
                        size=obj.size,
                        content_type=self._get_content_type(obj.key),
                        url=f"https://{self.config.bucket_name}.{self.config.endpoint}/{obj.key}",
                        oss_path=obj.key,
                        storage_type=StorageType.OSS,
                        etag=obj.etag,
                        last_modified=obj.last_modified,
                    )
                    
                    if self.config.cdn_domain:
                        file_info.cdn_url = f"https://{self.config.cdn_domain}/{obj.key}"
                    
                    files.append(file_info)
                
                if result.is_truncated:
                    next_marker = result.next_marker
                    
            except Exception as e:
                logger.error(f"Failed to list OSS files: {e}")
        
        return files, next_marker
    
    def get_storage_info(self) -> Dict[str, Any]:
        """获取存储信息"""
        info = {
            "oss_enabled": self.config.enabled,
            "oss_configured": bool(self.config.access_key_id and self.config.bucket_name),
            "oss_endpoint": self.config.endpoint if self.config.enabled else "",
            "cdn_enabled": bool(self.config.cdn_domain) if self.config.enabled else False,
            "cdn_domain": self.config.cdn_domain if self.config.enabled else "",
            "bucket_name": self.config.bucket_name if self.config.enabled else "",
            "local_storage_path": self.local_storage_path,
            "local_paths": {k.value: v for k, v in self.local_paths.items()},
        }
        
        # 如果OSS可用，添加bucket统计
        if self._init_oss_client() and self.oss_client:
            try:
                import oss2
                bucket_info = self.oss_client.get_bucket_info()
                info["bucket_creation_date"] = bucket_info.creation_date
                info["bucket_storage_class"] = bucket_info.storage_class
                
                # 统计文件数量
                total_size = 0
                file_count = 0
                for obj in oss2.ObjectIterator(self.oss_client):
                    total_size += obj.size
                    file_count += 1
                info["oss_file_count"] = file_count
                info["oss_total_size"] = total_size
                
            except Exception as e:
                logger.warning(f"Failed to get OSS bucket info: {e}")
        
        return info
    
    def update_config(self, config: OSSConfig):
        """更新OSS配置"""
        self.config = config
        self._oss_initialized = False  # 重置OSS客户端
        logger.info("OSS config updated")
    
    def export_config(self) -> Dict[str, Any]:
        """导出配置（不含敏感信息）"""
        return self.config.to_dict()
    
    def import_config(self, config_dict: Dict[str, Any]):
        """导入配置"""
        self.config = OSSConfig.from_dict(config_dict)
        self._oss_initialized = False
        logger.info("OSS config imported")


# 全局OSS存储管理器实例
_oss_manager: Optional[OSSStorageManager] = None


def get_oss_manager(config: Optional[OSSConfig] = None) -> OSSStorageManager:
    """获取或创建全局OSS管理器实例"""
    global _oss_manager
    if _oss_manager is None:
        _oss_manager = OSSStorageManager(config)
    elif config:
        _oss_manager.update_config(config)
    return _oss_manager


# 示例用法
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 示例配置
    config = OSSConfig(
        access_key_id="your_access_key_id",
        access_key_secret="your_access_key_secret",
        bucket_name="your-bucket",
        endpoint="oss-cn-hangzhou.aliyuncs.com",
        region="cn-hangzhou",
        cdn_domain="cdn.example.com",
        enabled=False,  # 本地模式
    )
    
    manager = OSSStorageManager(config, "./test_storage")
    
    # 获取存储信息
    info = manager.get_storage_info()
    print(f"Storage Info: {json.dumps(info, indent=2)}")
