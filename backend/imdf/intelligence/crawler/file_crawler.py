"""智影 V4 — 文件/OSS 爬虫: S3/GCS/Azure/MinIO/local/FTP"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

try:
    import boto3  # type: ignore
    from botocore.config import Config as BotoConfig  # type: ignore
except ImportError:
    boto3 = None
    BotoConfig = None
try:
    from google.cloud import storage as gcs_storage  # type: ignore
except ImportError:
    gcs_storage = None
try:
    from azure.storage.blob import BlobServiceClient  # type: ignore
except ImportError:
    BlobServiceClient = None
try:
    import aioftp  # type: ignore
except ImportError:
    aioftp = None
try:
    import aiofiles  # type: ignore
except ImportError:
    aiofiles = None

from .base import BaseCrawler, CrawlerConfig, RawDocument

logger = logging.getLogger(__name__)


class FileCrawler(BaseCrawler):
    """文件 / OSS 爬虫 — 支持 6 种存储后端"""

    def __init__(self, config: CrawlerConfig):
        super().__init__(config)
        self._s3 = None
        self._gcs = None
        self._azure = None

    async def fetch(self, url: str) -> RawDocument:
        """根据 url scheme 路由 — s3:// / gs:// / azure:// / minio:// / ftp:// / file://"""
        start = time.time()
        if url.startswith("s3://") or url.startswith("minio://"):
            return await self._fetch_s3_compat(url, start)
        if url.startswith("gs://"):
            return await self._fetch_gcs(url, start)
        if url.startswith("azure://"):
            return await self._fetch_azure(url, start)
        if url.startswith("ftp://"):
            return await self._fetch_ftp(url, start)
        if url.startswith("file://") or url.startswith("/"):
            return await self._fetch_local(url, start)
        # 通用 HTTP(S) 文件下载
        return await self._fetch_http(url, start)

    async def _fetch_s3_compat(self, url: str, start: float) -> RawDocument:
        """S3 兼容协议 (含 MinIO)"""
        if boto3 is None:
            raise RuntimeError("boto3 未安装: pip install boto3")
        # 解析 s3://bucket/key 或 minio://bucket/key
        scheme, rest = url.split("://", 1)
        bucket, _, key = rest.partition("/")
        endpoint = self.config.selectors.get("endpoint_url")  # MinIO endpoint
        access_key = self.config.selectors.get("access_key", os.getenv("AWS_ACCESS_KEY_ID", ""))
        secret_key = self.config.selectors.get("secret_key", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
        region = self.config.selectors.get("region", "us-east-1")
        if self._s3 is None:
            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
                config=BotoConfig(retries={"max_attempts": 3, "mode": "adaptive"}) if BotoConfig else None,
            )
        # list 还是 get_object?
        if not key or key.endswith("/"):
            # list
            resp = self._s3.list_objects_v2(Bucket=bucket, Prefix=key or "", MaxKeys=self.config.max_pages)
            files = [{"Key": o["Key"], "Size": o["Size"]} for o in resp.get("Contents", [])]
            return RawDocument(
                url=url,
                type="json",
                title=f"S3 list: s3://{bucket}/{key}",
                json={"bucket": bucket, "prefix": key, "files": files, "count": len(files)},
                source_metadata={"protocol": scheme, "operation": "list"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        # get_object
        resp = self._s3.get_object(Bucket=bucket, Key=key)
        data = resp["Body"].read()
        content_type = resp.get("ContentType", "application/octet-stream")
        # 文本类型尝试 decode
        text = ""
        if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
            try:
                text = data.decode("utf-8", errors="ignore")
            except Exception:
                pass
        return RawDocument(
            url=url,
            type="file",
            title=key.split("/")[-1],
            text=text,
            files=[{"bucket": bucket, "key": key, "size": len(data), "content_type": content_type}],
            source_metadata={"protocol": scheme, "operation": "get", "bucket": bucket, "key": key},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_gcs(self, url: str, start: float) -> RawDocument:
        """GCS (Google Cloud Storage)"""
        if gcs_storage is None:
            raise RuntimeError("google-cloud-storage 未安装")
        # gs://bucket/key
        _, rest = url.split("gs://", 1)
        bucket_name, _, key = rest.partition("/")
        if self._gcs is None:
            self._gcs = gcs_storage.Client()
        bucket = self._gcs.bucket(bucket_name)
        if not key or key.endswith("/"):
            blobs = list(bucket.list_blobs(prefix=key or "", max_results=self.config.max_pages))
            files = [{"name": b.name, "size": b.size} for b in blobs]
            return RawDocument(
                url=url,
                type="json",
                title=f"GCS: gs://{bucket_name}/{key}",
                json={"bucket": bucket_name, "prefix": key, "files": files, "count": len(files)},
                source_metadata={"protocol": "gcs", "operation": "list"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        blob = bucket.blob(key)
        data = blob.download_as_bytes()
        text = data.decode("utf-8", errors="ignore") if blob.content_type and (blob.content_type.startswith("text/") or blob.content_type in ("application/json", "application/xml")) else ""
        return RawDocument(
            url=url,
            type="file",
            title=key.split("/")[-1],
            text=text,
            files=[{"bucket": bucket_name, "key": key, "size": len(data), "content_type": blob.content_type}],
            source_metadata={"protocol": "gcs", "operation": "get", "bucket": bucket_name, "key": key},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_azure(self, url: str, start: float) -> RawDocument:
        """Azure Blob Storage"""
        if BlobServiceClient is None:
            raise RuntimeError("azure-storage-blob 未安装")
        # azure://container/blob
        _, rest = url.split("azure://", 1)
        container, _, blob_name = rest.partition("/")
        conn_str = self.config.selectors.get("connection_string", os.getenv("AZURE_STORAGE_CONNECTION_STRING", ""))
        if self._azure is None:
            self._azure = BlobServiceClient.from_connection_string(conn_str)
        container_client = self._azure.get_container_client(container)
        if not blob_name or blob_name.endswith("/"):
            blobs = list(container_client.list_blobs(name_starts_with=blob_name or "")[: self.config.max_pages])
            files = [{"name": b.name, "size": b.size} for b in blobs]
            return RawDocument(
                url=url,
                type="json",
                title=f"Azure: {container}/{blob_name}",
                json={"container": container, "prefix": blob_name, "files": files, "count": len(files)},
                source_metadata={"protocol": "azure", "operation": "list"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        blob_client = container_client.get_blob_client(blob_name)
        stream = blob_client.download_blob()
        data = stream.readall()
        return RawDocument(
            url=url,
            type="file",
            title=blob_name.split("/")[-1],
            files=[{"container": container, "blob": blob_name, "size": len(data), "content_type": stream.properties.content_settings.content_type}],
            source_metadata={"protocol": "azure", "operation": "get", "container": container, "blob": blob_name},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_ftp(self, url: str, start: float) -> RawDocument:
        """FTP / FTPS 文件下载"""
        if aioftp is None:
            raise RuntimeError("aioftp 未安装: pip install aioftp")
        from urllib.parse import urlparse
        u = urlparse(url)
        user = u.username or "anonymous"
        password = u.password or "anonymous@"
        host = u.hostname
        port = u.port or 21
        path = u.path.lstrip("/")
        async with aioftp.Client() as client:
            await client.connect(host, port)
            await client.login(user, password)
            if path.endswith("/"):
                # list
                entries = []
                async for entry in client.list(path):
                    entries.append({"name": entry[0], "size": entry[1].get("size", 0), "type": entry[1].get("type")})
                return RawDocument(
                    url=url,
                    type="json",
                    title=f"FTP: {path}",
                    json={"path": path, "entries": entries[: self.config.max_pages]},
                    source_metadata={"protocol": "ftp", "operation": "list"},
                    crawl_duration_ms=(time.time() - start) * 1000,
                )
            # 下载单文件到内存
            buf = bytearray()
            async with client.download_stream(path) as stream:
                async for chunk in stream.iter_by_block():
                    buf.extend(chunk)
            return RawDocument(
                url=url,
                type="file",
                title=path.split("/")[-1],
                files=[{"path": path, "size": len(buf)}],
                source_metadata={"protocol": "ftp", "operation": "get", "path": path},
                crawl_duration_ms=(time.time() - start) * 1000,
            )

    async def _fetch_local(self, url: str, start: float) -> RawDocument:
        """本地文件系统 — /path/to/file 或 file:///path"""
        path = url.replace("file://", "") if url.startswith("file://") else url
        if not os.path.exists(path):
            return RawDocument(
                url=url,
                type="file",
                http_status=404,
                source_metadata={"protocol": "file", "error": "not_found", "path": path},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        if os.path.isdir(path):
            files: List[Dict[str, Any]] = []
            for root, _, fnames in os.walk(path):
                for fn in fnames[: self.config.max_pages]:
                    full = os.path.join(root, fn)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    files.append({"path": full, "name": fn, "size": size})
                if len(files) >= self.config.max_pages:
                    break
            return RawDocument(
                url=url,
                type="json",
                title=f"Local dir: {path}",
                json={"path": path, "files": files, "count": len(files)},
                source_metadata={"protocol": "file", "operation": "list"},
                crawl_duration_ms=(time.time() - start) * 1000,
            )
        # 单文件
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            data = f.read()
        text = ""
        # 尝试按文本读
        try:
            text = data.decode("utf-8", errors="ignore")[:50000]
        except Exception:
            pass
        return RawDocument(
            url=url,
            type="file",
            title=os.path.basename(path),
            text=text,
            files=[{"path": path, "size": size}],
            source_metadata={"protocol": "file", "operation": "get", "path": path, "size": size},
            crawl_duration_ms=(time.time() - start) * 1000,
        )

    async def _fetch_http(self, url: str, start: float) -> RawDocument:
        """HTTP(S) 文件下载 (任意 URL)"""
        import httpx
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("content-type", "application/octet-stream")
            text = ""
            if content_type.startswith("text/") or content_type in ("application/json", "application/xml"):
                try:
                    text = data.decode("utf-8", errors="ignore")[:50000]
                except Exception:
                    pass
            filename = url.split("/")[-1].split("?")[0] or "download"
            return RawDocument(
                url=url,
                type="file",
                title=filename,
                text=text,
                files=[{"url": url, "size": len(data), "content_type": content_type}],
                source_metadata={"protocol": "http", "content_type": content_type, "size": len(data)},
                crawl_duration_ms=(time.time() - start) * 1000,
            )

    async def close(self):
        # boto3/gcs/azure client 无显式 close
        self._s3 = None
        self._gcs = None
        self._azure = None
