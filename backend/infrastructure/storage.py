#!/usr/bin/env python3
"""
Nanobot Factory - S3/OSS 对象存储模块
完整的异步对象存储管理，支持本地MinIO、阿里云OSS、AWS S3

@author MiniMax Agent
@date 2026-03-02
@description 基于 boto3/aioboto3 异步驱动的对象存储管理
"""

import os
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List, BinaryIO, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import asyncio
import io

# S3/OSS 驱动
try:
    import aioboto3
    import botocore
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    try:
        import boto3
        from boto3.exceptions import BotoCoreError
        S3_AVAILABLE = True
    except ImportError:
        S3_AVAILABLE = False
        logging.warning("S3/OSS 驱动未安装: pip install boto3 aioboto3")

# 阿里云 OSS 驱动
try:
    import oss2
    OSS_SDK_AVAILABLE = True
except ImportError:
    OSS_SDK_AVAILABLE = False
    logging.warning("阿里云 OSS SDK 未安装: pip install aliyun-python-sdk-oss")

logger = logging.getLogger(__name__)


# ============================================================================
# 存储类型枚举
# ============================================================================

class StorageType(Enum):
    """存储类型"""
    S3 = "s3"           # AWS S3
    OSS = "oss"          # 阿里云 OSS
    MINIO = "minio"      # MinIO 本地存储
    LOCAL = "local"      # 本地文件系统


class StorageClass(Enum):
    """存储类别"""
    STANDARD = "STANDARD"
    INFREQUENT = "INTELLIGENT_TIERING"
    GLACIER = "GLACIER"
    DEEP_ARCHIVE = "DEEP_ARCHIVE"


@dataclass
class ObjectMetadata:
    """对象元数据"""
    key: str
    size: int
    content_type: str = ""
    etag: str = ""
    last_modified: datetime = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    storage_class: str = ""


@dataclass
class UploadResult:
    """上传结果"""
    success: bool
    bucket: str
    key: str
    url: str = ""
    etag: str = ""
    version_id: str = ""
    error: str = ""


@dataclass
class DownloadResult:
    """下载结果"""
    success: bool
    content: bytes = None
    path: str = ""
    metadata: ObjectMetadata = None
    error: str = ""


# ============================================================================
# S3/OSS 管理器
# ============================================================================

class StorageManager:
    """
    统一存储管理器
    支持 S3、阿里云 OSS、MinIO、本地存储
    """

    def __init__(
        self,
        storage_type: StorageType = StorageType.LOCAL,
        config: Dict[str, Any] = None
    ):
        """
        初始化存储管理器

        Args:
            storage_type: 存储类型
            config: 存储配置
        """
        self.storage_type = storage_type
        self.config = config or {}

        # S3 配置
        self.s3_config = self.config.get("s3", {})
        self.access_key = self.s3_config.get("access_key") or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = self.s3_config.get("secret_key") or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = self.s3_config.get("region", "us-east-1")
        self.bucket = self.s3_config.get("bucket") or os.getenv("S3_BUCKET")
        self.endpoint = self.s3_config.get("endpoint")  # MinIO/OSS 使用

        # 阿里云 OSS 配置
        self.oss_config = self.config.get("oss", {})
        self.oss_access_key = self.oss_config.get("access_key") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        self.oss_secret_key = self.oss_config.get("secret_key") or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        self.oss_bucket = self.oss_config.get("bucket") or os.getenv("OSS_BUCKET_NAME")
        self.oss_endpoint = self.oss_config.get("endpoint") or os.getenv("OSS_ENDPOINT")
        self.oss_region = self.oss_config.get("region", "oss-cn-hangzhou")

        # 本地存储配置
        self.local_config = self.config.get("local", {})
        self.local_path = self.local_config.get("path", "./storage")

        # 客户端
        self._s3_client = None
        self._oss_bucket = None
        self._is_configured = False

        # 初始化
        self._init_client()

    def _init_client(self):
        """初始化客户端"""
        if self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
            if not S3_AVAILABLE:
                logger.warning("S3 驱动未安装")
                return
            self._is_configured = True

        elif self.storage_type == StorageType.OSS:
            if not OSS_SDK_AVAILABLE:
                logger.warning("阿里云 OSS SDK 未安装")
                return

            if self.oss_access_key and self.oss_bucket:
                try:
                    auth = oss2.Auth(self.oss_access_key, self.oss_secret_key)
                    if not self.oss_endpoint:
                        self.oss_endpoint = f"oss-{self.oss_region}.aliyuncs.com"
                    self._oss_bucket = oss2.Bucket(auth, self.oss_endpoint, self.oss_bucket)
                    self._is_configured = True
                    logger.info(f"阿里云 OSS 已配置: {self.oss_bucket}")
                except Exception as e:
                    logger.error(f"阿里云 OSS 配置失败: {e}")

        elif self.storage_type == StorageType.LOCAL:
            # 创建本地存储目录
            Path(self.local_path).mkdir(parents=True, exist_ok=True)
            self._is_configured = True
            logger.info(f"本地存储已配置: {self.local_path}")

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return self._is_configured

    # =========================================================================
    # 基础操作
    # =========================================================================

    async def upload_file(
        self,
        file_path: str,
        key: str,
        metadata: Dict[str, Any] = None,
        storage_class: str = None
    ) -> UploadResult:
        """
        上传文件

        Args:
            file_path: 本地文件路径
            key: 存储键
            metadata: 元数据
            storage_class: 存储类别

        Returns:
            上传结果
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_upload_file(file_path, key, metadata)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_upload_file(file_path, key, metadata, storage_class)
            else:
                return await self._local_upload_file(file_path, key, metadata)
        except Exception as e:
            logger.error(f"上传文件失败: {e}")
            return UploadResult(success=False, bucket=self._get_bucket_name(), key=key, error=str(e))

    async def upload_data(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, Any] = None
    ) -> UploadResult:
        """
        上传数据

        Args:
            data: 二进制数据
            key: 存储键
            content_type: 内容类型
            metadata: 元数据

        Returns:
            上传结果
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_upload_data(data, key, content_type, metadata)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_upload_data(data, key, content_type, metadata)
            else:
                return await self._local_upload_data(data, key, content_type, metadata)
        except Exception as e:
            logger.error(f"上传数据失败: {e}")
            return UploadResult(success=False, bucket=self._get_bucket_name(), key=key, error=str(e))

    async def download_file(self, key: str, file_path: str) -> DownloadResult:
        """
        下载文件

        Args:
            key: 存储键
            file_path: 本地保存路径

        Returns:
            下载结果
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_download_file(key, file_path)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_download_file(key, file_path)
            else:
                return await self._local_download_file(key, file_path)
        except Exception as e:
            logger.error(f"下载文件失败: {e}")
            return DownloadResult(success=False, path=file_path, error=str(e))

    async def get_object(self, key: str) -> Optional[bytes]:
        """
        获取对象内容

        Args:
            key: 存储键

        Returns:
            对象内容
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_get_object(key)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_get_object(key)
            else:
                return await self._local_get_object(key)
        except Exception as e:
            logger.error(f"获取对象失败: {e}")
            return None

    async def delete_object(self, key: str) -> bool:
        """
        删除对象

        Args:
            key: 存储键

        Returns:
            是否删除成功
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_delete_object(key)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_delete_object(key)
            else:
                return await self._local_delete_object(key)
        except Exception as e:
            logger.error(f"删除对象失败: {e}")
            return False

    async def delete_objects(self, keys: List[str]) -> int:
        """
        批量删除对象

        Args:
            keys: 存储键列表

        Returns:
            成功删除的数量
        """
        deleted = 0
        for key in keys:
            if await self.delete_object(key):
                deleted += 1
        return deleted

    async def list_objects(
        self,
        prefix: str = "",
        max_keys: int = 1000,
        delimiter: str = ""
    ) -> List[ObjectMetadata]:
        """
        列出对象

        Args:
            prefix: 前缀
            max_keys: 最大数量
            delimiter: 分隔符

        Returns:
            对象列表
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_list_objects(prefix, max_keys, delimiter)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_list_objects(prefix, max_keys, delimiter)
            else:
                return await self._local_list_objects(prefix, max_keys, delimiter)
        except Exception as e:
            logger.error(f"列出对象失败: {e}")
            return []

    async def get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """
        获取对象元数据

        Args:
            key: 存储键

        Returns:
            对象元数据
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_get_object_metadata(key)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_get_object_metadata(key)
            else:
                return await self._local_get_object_metadata(key)
        except Exception as e:
            logger.error(f"获取对象元数据失败: {e}")
            return None

    async def copy_object(
        self,
        source_key: str,
        dest_key: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        复制对象

        Args:
            source_key: 源键
            dest_key: 目标键
            metadata: 元数据

        Returns:
            是否复制成功
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_copy_object(source_key, dest_key, metadata)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_copy_object(source_key, dest_key, metadata)
            else:
                return await self._local_copy_object(source_key, dest_key, metadata)
        except Exception as e:
            logger.error(f"复制对象失败: {e}")
            return False

    # =========================================================================
    # 签名 URL
    # =========================================================================

    async def get_presigned_url(
        self,
        key: str,
        expires: int = 3600,
        http_method: str = "GET"
    ) -> Optional[str]:
        """
        获取预签名 URL

        Args:
            key: 存储键
            expires: 过期时间（秒）
            http_method: HTTP 方法

        Returns:
            签名 URL
        """
        try:
            if self.storage_type == StorageType.OSS:
                return await self._oss_get_presigned_url(key, expires)
            elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
                return await self._s3_get_presigned_url(key, expires, http_method)
            else:
                return await self._local_get_presigned_url(key, expires)
        except Exception as e:
            logger.error(f"获取签名URL失败: {e}")
            return None

    async def get_upload_presigned_url(
        self,
        key: str,
        expires: int = 3600,
        content_type: str = "application/octet-stream"
    ) -> Optional[str]:
        """
        获取上传预签名 URL

        Args:
            key: 存储键
            expires: 过期时间（秒）
            content_type: 内容类型

        Returns:
            上传签名 URL
        """
        return await self.get_presigned_url(key, expires, "PUT")

    # =========================================================================
    # 阿里云 OSS 实现
    # =========================================================================

    async def _oss_upload_file(self, file_path: str, key: str, metadata: Dict) -> UploadResult:
        """OSS 上传文件"""
        try:
            # 添加元数据
            headers = {}
            if metadata:
                for k, v in metadata.items():
                    headers[f"x-oss-meta-{k}"] = str(v)

            result = self._oss_bucket.put_object_from_file(key, file_path, headers)

            if result.status == 200:
                url = self._oss_bucket.sign_url("GET", key, 3600)
                return UploadResult(
                    success=True,
                    bucket=self.oss_bucket,
                    key=key,
                    url=url,
                    etag=result.etag
                )

            return UploadResult(success=False, bucket=self.oss_bucket, key=key, error=f"Status: {result.status}")

        except Exception as e:
            return UploadResult(success=False, bucket=self.oss_bucket, key=key, error=str(e))

    async def _oss_upload_data(self, data: bytes, key: str, content_type: str, metadata: Dict) -> UploadResult:
        """OSS 上传数据"""
        try:
            headers = {"Content-Type": content_type}
            if metadata:
                for k, v in metadata.items():
                    headers[f"x-oss-meta-{k}"] = str(v)

            result = self._oss_bucket.put_object(key, data, headers)

            if result.status == 200:
                url = self._oss_bucket.sign_url("GET", key, 3600)
                return UploadResult(
                    success=True,
                    bucket=self.oss_bucket,
                    key=key,
                    url=url,
                    etag=result.etag
                )

            return UploadResult(success=False, bucket=self.oss_bucket, key=key)

        except Exception as e:
            return UploadResult(success=False, bucket=self.oss_bucket, key=key, error=str(e))

    async def _oss_download_file(self, key: str, file_path: str) -> DownloadResult:
        """OSS 下载文件"""
        try:
            result = self._oss_bucket.get_object_to_file(key, file_path)

            if result.status == 200:
                return DownloadResult(success=True, path=file_path)

            return DownloadResult(success=False, path=file_path, error=f"Status: {result.status}")

        except Exception as e:
            return DownloadResult(success=False, path=file_path, error=str(e))

    async def _oss_get_object(self, key: str) -> Optional[bytes]:
        """OSS 获取对象"""
        try:
            result = self._oss_bucket.get_object(key)
            return result.read()
        except Exception as e:
            logger.warning(f"OSS获取对象失败 {key}: {e}")
            return None

    async def _oss_delete_object(self, key: str) -> bool:
        """OSS 删除对象"""
        try:
            result = self._oss_bucket.delete_object(key)
            return result.status in [200, 204]
        except Exception as e:
            logger.warning(f"OSS删除对象失败 {key}: {e}")
            return False

    async def _oss_list_objects(self, prefix: str, max_keys: int, delimiter: str) -> List[ObjectMetadata]:
        """OSS 列出对象"""
        try:
            objects = []
            for obj in oss2.ObjectIterator(self._oss_bucket, prefix=prefix):
                objects.append(ObjectMetadata(
                    key=obj.key,
                    size=obj.size,
                    content_type=obj.content_type,
                    etag=obj.etag,
                    last_modified=obj.last_modified,
                    storage_class=obj.storage_class
                ))
                if len(objects) >= max_keys:
                    break
            return objects
        except Exception as e:
            logger.warning(f"OSS列出对象失败 prefix={prefix}: {e}")
            return []

    async def _oss_get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """OSS 获取对象元数据"""
        try:
            meta = self._oss_bucket.head_object(key)
            return ObjectMetadata(
                key=key,
                size=meta.content_length,
                content_type=meta.content_type,
                etag=meta.etag,
                last_modified=meta.last_modified
            )
        except Exception as e:
            logger.warning(f"OSS获取元数据失败 {key}: {e}")
            return None

    async def _oss_copy_object(self, source: str, dest: str, metadata: Dict) -> bool:
        """OSS 复制对象"""
        try:
            result = self._oss_bucket.copy_object(source, dest)
            return result.status == 200
        except Exception as e:
            logger.warning(f"OSS复制对象失败 {source}->{dest}: {e}")
            return False

    async def _oss_get_presigned_url(self, key: str, expires: int) -> str:
        """OSS 获取签名 URL"""
        return self._oss_bucket.sign_url("GET", key, expires)

    # ============================================================================
    # S3 实现
    # ============================================================================

    async def _s3_upload_file(self, file_path: str, key: str, metadata: Dict, storage_class: str) -> UploadResult:
        """S3 上传文件"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                extra_args = {}
                if metadata:
                    extra_args['Metadata'] = metadata
                if storage_class:
                    extra_args['StorageClass'] = storage_class

                await s3.upload_file(
                    file_path,
                    self.bucket,
                    key,
                    ExtraArgs=extra_args
                )

                url = await self._s3_get_presigned_url(key, 3600)
                return UploadResult(success=True, bucket=self.bucket, key=key, url=url)

        except Exception as e:
            return UploadResult(success=False, bucket=self.bucket, key=key, error=str(e))

    async def _s3_upload_data(self, data: bytes, key: str, content_type: str, metadata: Dict) -> UploadResult:
        """S3 上传数据"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                extra_args = {'ContentType': content_type}
                if metadata:
                    extra_args['Metadata'] = metadata

                await s3.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=data,
                    **extra_args
                )

                url = await self._s3_get_presigned_url(key, 3600)
                return UploadResult(success=True, bucket=self.bucket, key=key, url=url)

        except Exception as e:
            return UploadResult(success=False, bucket=self.bucket, key=key, error=str(e))

    async def _s3_download_file(self, key: str, file_path: str) -> DownloadResult:
        """S3 下载文件"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                await s3.download_file(self.bucket, key, file_path)
                return DownloadResult(success=True, path=file_path)

        except Exception as e:
            return DownloadResult(success=False, path=file_path, error=str(e))

    async def _s3_get_object(self, key: str) -> Optional[bytes]:
        """S3 获取对象"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                response = await s3.get_object(Bucket=self.bucket, Key=key)
                async with response['Body'] as stream:
                    return await stream.read()
        except Exception as e:
            logger.warning(f"S3获取对象失败 {key}: {e}")
            return None

    async def _s3_delete_object(self, key: str) -> bool:
        """S3 删除对象"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                await s3.delete_object(Bucket=self.bucket, Key=key)
                return True

        except Exception as e:
            logger.warning(f"S3删除对象失败 {key}: {e}")
            return False

    async def _s3_list_objects(self, prefix: str, max_keys: int, delimiter: str) -> List[ObjectMetadata]:
        """S3 列出对象"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                response = await s3.list_objects_v2(
                    Bucket=self.bucket,
                    Prefix=prefix,
                    MaxKeys=max_keys,
                    Delimiter=delimiter
                )

                objects = []
                if 'Contents' in response:
                    for obj in response['Contents']:
                        objects.append(ObjectMetadata(
                            key=obj['Key'],
                            size=obj['Size'],
                            etag=obj['ETag'],
                            last_modified=obj['LastModified']
                        ))

                return objects

        except Exception as e:
            logger.warning(f"S3列出对象失败 prefix={prefix}: {e}")
            return []

    async def _s3_get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """S3 获取对象元数据"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                response = await s3.head_object(Bucket=self.bucket, Key=key)
                return ObjectMetadata(
                    key=key,
                    size=response['ContentLength'],
                    content_type=response.get('ContentType', ''),
                    etag=response['ETag'],
                    last_modified=response['LastModified']
                )

        except Exception as e:
            logger.warning(f"S3获取元数据失败 {key}: {e}")
            return None

    async def _s3_copy_object(self, source: str, dest: str, metadata: Dict) -> bool:
        """S3 复制对象"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            copy_source = {'Bucket': self.bucket, 'Key': source}
            async with session.client('s3') as s3:
                await s3.copy_object(
                    Bucket=self.bucket,
                    Key=dest,
                    CopySource=copy_source,
                    Metadata=metadata,
                    MetadataDirective='REPLACE' if metadata else 'COPY'
                )
                return True

        except Exception as e:
            logger.warning(f"S3复制对象失败 {source}->{dest}: {e}")
            return False

    async def _s3_get_presigned_url(self, key: str, expires: int, http_method: str) -> str:
        """S3 获取签名 URL"""
        try:
            session = aioboto3.Session(
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name=self.region
            )

            async with session.client('s3') as s3:
                url = await s3.generate_presigned_url(
                    HttpMethod=http_method,
                    Params={'Bucket': self.bucket, 'Key': key},
                    ExpiresIn=expires
                )
                return url

        except Exception as e:
            logger.warning(f"S3获取签名URL失败 {key}: {e}")
            return ""

    # ============================================================================
    # 本地存储实现
    # ============================================================================

    async def _local_upload_file(self, file_path: str, key: str, metadata: Dict) -> UploadResult:
        """本地存储上传文件"""
        try:
            import shutil
            dest_path = os.path.join(self.local_path, key)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(file_path, dest_path)

            url = f"/storage/{key}"
            return UploadResult(success=True, bucket="local", key=key, url=url)

        except Exception as e:
            return UploadResult(success=False, bucket="local", key=key, error=str(e))

    async def _local_upload_data(self, data: bytes, key: str, content_type: str, metadata: Dict) -> UploadResult:
        """本地存储上传数据"""
        try:
            dest_path = os.path.join(self.local_path, key)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            with open(dest_path, 'wb') as f:
                f.write(data)

            url = f"/storage/{key}"
            return UploadResult(success=True, bucket="local", key=key, url=url)

        except Exception as e:
            return UploadResult(success=False, bucket="local", key=key, error=str(e))

    async def _local_download_file(self, key: str, file_path: str) -> DownloadResult:
        """本地存储下载文件"""
        try:
            import shutil
            source_path = os.path.join(self.local_path, key)
            shutil.copy2(source_path, file_path)
            return DownloadResult(success=True, path=file_path)

        except Exception as e:
            return DownloadResult(success=False, path=file_path, error=str(e))

    async def _local_get_object(self, key: str) -> Optional[bytes]:
        """本地存储获取对象"""
        try:
            path = os.path.join(self.local_path, key)
            with open(path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"本地获取对象失败 {key}: {e}")
            return None

    async def _local_delete_object(self, key: str) -> bool:
        """本地存储删除对象"""
        try:
            path = os.path.join(self.local_path, key)
            os.remove(path)
            return True
        except Exception as e:
            logger.warning(f"本地删除对象失败 {key}: {e}")
            return False

    async def _local_list_objects(self, prefix: str, max_keys: int, delimiter: str) -> List[ObjectMetadata]:
        """本地存储列出对象"""
        try:
            prefix_path = os.path.join(self.local_path, prefix)
            objects = []

            for root, dirs, files in os.walk(self.local_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.local_path)

                    if rel_path.startswith(prefix):
                        stat = os.stat(file_path)
                        objects.append(ObjectMetadata(
                            key=rel_path,
                            size=stat.st_size,
                            last_modified=datetime.fromtimestamp(stat.st_mtime)
                        ))

                        if len(objects) >= max_keys:
                            break

                if len(objects) >= max_keys:
                    break

            return objects

        except Exception as e:
            logger.warning(f"本地列出对象失败 prefix={prefix}: {e}")
            return []

    async def _local_get_object_metadata(self, key: str) -> Optional[ObjectMetadata]:
        """本地存储获取对象元数据"""
        try:
            path = os.path.join(self.local_path, key)
            stat = os.stat(path)
            return ObjectMetadata(
                key=key,
                size=stat.st_size,
                last_modified=datetime.fromtimestamp(stat.st_mtime)
            )

        except Exception as e:
            logger.warning(f"本地获取元数据失败 {key}: {e}")
            return None

    async def _local_copy_object(self, source: str, dest: str, metadata: Dict) -> bool:
        """本地存储复制对象"""
        try:
            import shutil
            source_path = os.path.join(self.local_path, source)
            dest_path = os.path.join(self.local_path, dest)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.copy2(source_path, dest_path)
            return True
        except Exception as e:
            logger.warning(f"本地复制对象失败 {source}->{dest}: {e}")
            return False

    async def _local_get_presigned_url(self, key: str, expires: int) -> str:
        """本地存储获取签名 URL"""
        return f"/storage/{key}"

    # ============================================================================
    # 辅助方法
    # ============================================================================

    def _get_bucket_name(self) -> str:
        """获取桶名称"""
        if self.storage_type == StorageType.OSS:
            return self.oss_bucket
        elif self.storage_type == StorageType.S3 or self.storage_type == StorageType.MINIO:
            return self.bucket
        else:
            return "local"

    async def get_storage_info(self) -> Dict[str, Any]:
        """获取存储信息"""
        return {
            "type": self.storage_type.value,
            "bucket": self._get_bucket_name(),
            "configured": self._is_configured
        }


# ============================================================================
# 单例实例
# ============================================================================

_storage_manager: StorageManager = None


def get_storage_manager() -> StorageManager:
    """获取存储管理器单例"""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
    return _storage_manager


def init_storage_manager(
    storage_type: StorageType = StorageType.LOCAL,
    config: Dict[str, Any] = None
) -> StorageManager:
    """初始化存储管理器"""
    global _storage_manager
    _storage_manager = StorageManager(storage_type=storage_type, config=config)
    return _storage_manager
