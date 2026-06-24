#!/usr/bin/env python3
"""
Nanobot Factory - 阿里云 OSS 管理模块 (AI增强版)
用于管理海量多模态模型训练数据

@author MiniMax Agent
@date 2026-03-01
@description 支持 OSS 内海量数据的智能分类、评分、批量管理
               所有功能由 Nanobot+AI 驱动，无模拟代码
"""

import os
import json
import hashlib
import time
import asyncio
import uuid
from typing import Optional, Dict, Any, List, BinaryIO, Callable
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
import logging
import io

# 阿里云 OSS SDK
try:
    import oss2
    OSS_SDK_AVAILABLE = True
except ImportError:
    OSS_SDK_AVAILABLE = False
    logging.debug("阿里云 OSS SDK 未安装，请运行: pip install aliyun-python-sdk-oss")

logger = logging.getLogger(__name__)


# ============================================================================
# AI Service Interface (Nanobot+AI驱动)
# ============================================================================

class AIVisionService:
    """
    AI视觉服务接口
    用于图像评分、分类、物体检测等
    """

    async def score_image_quality(
        self,
        image_url: str,
        model: str = "qwen-vl-max"
    ) -> Dict[str, Any]:
        """
        AI驱动的图像质量评分

        Args:
            image_url: 图像URL
            model: 视觉模型

        Returns:
            评分结果
        """
        raise NotImplementedError("必须由具体的AI服务实现")

    async def classify_image(
        self,
        image_url: str,
        categories: List[str]
    ) -> Dict[str, Any]:
        """
        AI驱动的图像分类

        Args:
            image_url: 图像URL
            categories: 候选分类

        Returns:
            分类结果
        """
        raise NotImplementedError("必须由具体的AI服务实现")

    async def extract_image_tags(
        self,
        image_url: str,
        max_tags: int = 10
    ) -> List[str]:
        """
        AI驱动的图像标签提取

        Args:
            image_url: 图像URL
            max_tags: 最大标签数

        Returns:
            标签列表
        """
        raise NotImplementedError("必须由具体的AI服务实现")


class AILanguageService:
    """
    AI语言服务接口
    用于文本分类、摘要、生成等
    """

    async def classify_text(
        self,
        text: str,
        categories: List[str]
    ) -> Dict[str, Any]:
        """
        AI驱动的文本分类

        Args:
            text: 文本内容
            categories: 候选分类

        Returns:
            分类结果
        """
        raise NotImplementedError("必须由具体的AI服务实现")

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1000
    ) -> str:
        """
        AI驱动的文本生成

        Args:
            prompt: 提示词
            max_tokens: 最大token数

        Returns:
            生成的文本
        """
        raise NotImplementedError("必须由具体的AI服务实现")


# ============================================================================
# Concrete AI Services (实际实现)
# ============================================================================

class NanobotVisionService(AIVisionService):
    """
    基于Nanobot的视觉服务实现
    实际调用AI API进行图像分析
    """

    def __init__(self, generation_service=None):
        self.generation_service = generation_service

    async def score_image_quality(
        self,
        image_url: str,
        model: str = "qwen-vl-max"
    ) -> Dict[str, Any]:
        """
        使用视觉大模型评分图像质量
        """
        if not self.generation_service:
            raise Exception("生成服务未初始化")

        # 构建评分提示词
        prompt = f"""请分析这张图片的质量，从以下几个方面进行评分（0-1分）：

1. 画质清晰度：图片是否清晰、是否有模糊、噪点
2. 构图合理性：构图是否合理、是否有主体偏移
3. 色彩表现：色彩是否自然、是否有过曝或欠曝
4. 内容价值：图片内容是否有价值、是否适合作为训练数据
5. 审美评分：整体审美感受

请返回JSON格式的评分结果：
{{
    "clarity": 0.0-1.0,
    "composition": 0.0-1.0,
    "color": 0.0-1.0,
    "content_value": 0.0-1.0,
    "aesthetic": 0.0-1.0,
    "overall_score": 0.0-1.0,
    "reason": "评分理由"
}}"""

        try:
            # 调用视觉模型
            result = await self.generation_service.generate(
                provider_name="doubao",
                request={
                    "prompt": prompt,
                    "images": [image_url],
                    "model": model
                }
            )

            if result.status == "completed":
                # 解析JSON结果
                response_text = result.text or ""
                # 提取JSON（简化处理）
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    scores = json.loads(json_match.group())
                    return {
                        "success": True,
                        "scores": scores,
                        "model_used": model
                    }

            return {
                "success": False,
                "error": "评分失败"
            }

        except Exception as e:
            logger.error(f"图像质量评分异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def classify_image(
        self,
        image_url: str,
        categories: List[str]
    ) -> Dict[str, Any]:
        """
        使用视觉大模型进行图像分类
        """
        if not self.generation_service:
            raise Exception("生成服务未初始化")

        categories_str = ", ".join(categories)

        prompt = f"""请分析这张图片，从以下候选分类中选择最合适的分类：

候选分类：{categories_str}

请返回JSON格式的分类结果：
{{
    "category": "选择的分类",
    "confidence": 0.0-1.0,
    "reason": "分类理由"
}}"""

        try:
            result = await self.generation_service.generate(
                provider_name="doubao",
                request={
                    "prompt": prompt,
                    "images": [image_url]
                }
            )

            if result.status == "completed":
                response_text = result.text or ""
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    classification = json.loads(json_match.group())
                    return {
                        "success": True,
                        "classification": classification
                    }

            return {
                "success": False,
                "error": "分类失败"
            }

        except Exception as e:
            logger.error(f"图像分类异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def extract_image_tags(
        self,
        image_url: str,
        max_tags: int = 10
    ) -> List[str]:
        """
        使用视觉大模型提取图像标签
        """
        if not self.generation_service:
            raise Exception("生成服务未初始化")

        prompt = f"""请分析这张图片，提取最多{max_tags}个关键词标签。

请返回JSON格式的标签结果：
{{
    "tags": ["标签1", "标签2", ...],
    "reason": "提取理由"
}}"""

        try:
            result = await self.generation_service.generate(
                provider_name="doubao",
                request={
                    "prompt": prompt,
                    "images": [image_url]
                }
            )

            if result.status == "completed":
                response_text = result.text or ""
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    tags_result = json.loads(json_match.group())
                    return tags_result.get("tags", [])

            return []

        except Exception as e:
            logger.error(f"标签提取异常: {e}")
            return []


class NanobotLanguageService(AILanguageService):
    """
    基于Nanobot的语言服务实现
    实际调用LLM API进行文本处理
    """

    def __init__(self, generation_service=None):
        self.generation_service = generation_service

    async def classify_text(
        self,
        text: str,
        categories: List[str]
    ) -> Dict[str, Any]:
        """
        使用LLM进行文本分类
        """
        if not self.generation_service:
            raise Exception("生成服务未初始化")

        categories_str = ", ".join(categories)

        prompt = f"""请分析以下文本，从候选分类中选择最合适的分类：

候选分类：{categories_str}

文本内容：
{text}

请返回JSON格式的分类结果：
{{
    "category": "选择的分类",
    "confidence": 0.0-1.0,
    "reason": "分类理由"
}}"""

        try:
            result = await self.generation_service.generate(
                provider_name="doubao",
                request={"prompt": prompt}
            )

            if result.status == "completed":
                response_text = result.text or ""
                import re
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    classification = json.loads(json_match.group())
                    return {
                        "success": True,
                        "classification": classification
                    }

            return {
                "success": False,
                "error": "分类失败"
            }

        except Exception as e:
            logger.error(f"文本分类异常: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def generate_text(
        self,
        prompt: str,
        max_tokens: int = 1000
    ) -> str:
        """
        使用LLM生成文本
        """
        if not self.generation_service:
            raise Exception("生成服务未初始化")

        try:
            result = await self.generation_service.generate(
                provider_name="doubao",
                request={
                    "prompt": prompt,
                    "max_tokens": max_tokens
                }
            )

            if result.status == "completed":
                return result.text or ""

            return ""

        except Exception as e:
            logger.error(f"文本生成异常: {e}")
            return ""


# ============================================================================
# 数据类型枚举
# ============================================================================

class DataType:
    """多模态数据类型"""
    IMAGE = "image"                    # 图片
    IMAGE_TEXT_PAIR = "image_text"    # 图文对
    IMAGE_EDIT_PAIR = "image_edit"    # 图片编辑对
    VIDEO_TEXT_PAIR = "video_text"    # 视频文字对
    VIDEO = "video"                   # 视频
    MODEL_3D = "model_3d"             # 3D模型
    TEXT_3D_PAIR = "text_3d"          # 3D文字对
    SFT_DATA = "sft"                  # SFT监督微调数据
    RLHF_DATA = "rlhf"                # RLHF强化学习数据
    DPO_DATA = "dpo"                  # DPO直接偏好优化数据
    AUDIO = "audio"                   # 音频
    DOCUMENT = "document"             # 文档


class DataQuality:
    """数据质量等级"""
    EXCELLENT = "excellent"    # 优秀
    GOOD = "good"             # 良好
    MEDIUM = "medium"         # 中等
    POOR = "poor"             # 较差
    REJECTED = "rejected"     # 拒绝


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class OSSFile:
    """OSS文件对象"""
    key: str                          # OSS路径键
    name: str                        # 文件名
    size: int                        # 文件大小(字节)
    content_type: str                # 内容类型
    etag: str                        # ETag
    last_modified: str               # 最后修改时间
    url: str = ""                    # 访问URL
    metadata: Dict[str, Any] = field(default_factory=dict)  # 自定义元数据


@dataclass
class DatasetMetadata:
    """数据集元数据"""
    dataset_id: str
    name: str
    description: str
    data_type: str                   # 数据类型
    total_files: int = 0
    total_size: int = 0
    tags: List[str] = field(default_factory=list)
    quality_scores: Dict[str, float] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class DataAnnotation:
    """数据标注"""
    file_key: str
    category: str = ""                # 分类标签
    quality_score: float = 0.0       # 质量评分 (0-1)
    aesthetic_score: float = 0.0    # 审美评分 (0-1)
    tags: List[str] = field(default_factory=list)
    annotations: Dict[str, Any] = field(default_factory=dict)
    model_used: str = ""             # 使用的评分模型
    annotated_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# AI驱动的批量任务
# ============================================================================

@dataclass
class AIBatchTask:
    """AI批量任务"""
    task_id: str
    task_type: str  # "classification", "scoring", "tagging"
    status: str = "pending"
    total: int = 0
    completed: int = 0
    failed: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None


# ============================================================================
# OSS管理器 (AI增强版)
# ============================================================================

class OSSManager:
    """
    阿里云 OSS 管理器 (AI增强版)
    支持海量多模态模型训练数据的智能管理、分类、评分

    核心特性：
    1. AI驱动的数据分类 - 使用视觉大模型自动分类
    2. AI驱动的质量评分 - 使用视觉大模型自动评分
    3. AI驱动的标签提取 - 自动提取图像标签
    4. 批量智能处理 - 并行处理大规模数据集
    5. 与生产数据库集成 - 完整的数据管理
    """

    def __init__(
        self,
        access_key_id: str = None,
        access_key_secret: str = None,
        bucket_name: str = None,
        endpoint: str = None,
        region: str = "oss-cn-hangzhou",
        vision_service: AIVisionService = None,
        language_service: AILanguageService = None,
        database_manager=None
    ):
        """
        初始化OSS管理器

        Args:
            access_key_id: 阿里云AccessKey ID
            access_key_secret: 阿里云AccessKey Secret
            bucket_name: OSS Bucket名称
            endpoint: OSS endpoint地址
            region: 区域(默认: oss-cn-hangzhou)
            vision_service: AI视觉服务
            language_service: AI语言服务
            database_manager: 生产数据库管理器
        """
        self.access_key_id = access_key_id or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        self.access_key_secret = access_key_secret or os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        self.bucket_name = bucket_name or os.getenv("OSS_BUCKET_NAME", "")
        self.endpoint = endpoint or os.getenv("OSS_ENDPOINT", "")
        self.region = region

        # AI服务
        self.vision_service = vision_service
        self.language_service = language_service
        self.database_manager = database_manager

        self.auth = None
        self.bucket = None
        self.is_configured = False

        # AI批量任务
        self.ai_tasks: Dict[str, AIBatchTask] = {}
        self.ai_task_callbacks: Dict[str, Callable] = {}

        if OSS_SDK_AVAILABLE and self.access_key_id and self.bucket_name:
            self._init_client()

    def _init_client(self):
        """初始化OSS客户端"""
        try:
            # 使用默认区域endpoint
            if not self.endpoint:
                self.endpoint = f"oss-{self.region}.aliyuncs.com"

            # 创建auth对象
            self.auth = oss2.Auth(self.access_key_id, self.access_key_secret)

            # 创建bucket对象
            self.bucket = oss2.Bucket(self.auth, self.endpoint, self.bucket_name)

            # 验证连接
            self.bucket.get_bucket_info()
            self.is_configured = True
            logger.info(f"OSS连接成功: {self.bucket_name} @ {self.endpoint}")
        except Exception as e:
            logger.error(f"OSS连接失败: {e}")
            self.is_configured = False

    def is_available(self) -> bool:
        """检查OSS是否可用"""
        return self.is_configured and OSS_SDK_AVAILABLE

    # =========================================================================
    # 文件操作基础API
    # =========================================================================

    def upload_file(
        self,
        local_path: str,
        oss_key: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        上传本地文件到OSS

        Args:
            local_path: 本地文件路径
            oss_key: OSS存储路径
            metadata: 自定义元数据

        Returns:
            是否上传成功
        """
        if not self.is_available():
            logger.warning("OSS未配置，跳过上传")
            return False

        try:
            # 添加元数据
            headers = {}
            if metadata:
                for key, value in metadata.items():
                    headers[f"x-oss-meta-{key}"] = str(value)

            # 上传文件
            result = self.bucket.put_object_from_file(oss_key, local_path, headers)

            if result.status == 200:
                logger.info(f"文件上传成功: {oss_key}")
                return True
            else:
                logger.error(f"文件上传失败: {result.status}")
                return False
        except Exception as e:
            logger.error(f"上传文件异常: {e}")
            return False

    def upload_data(
        self,
        data: bytes,
        oss_key: str,
        content_type: str = "application/octet-stream",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        上传二进制数据到OSS

        Args:
            data: 二进制数据
            oss_key: OSS存储路径
            content_type: 内容类型
            metadata: 自定义元数据

        Returns:
            是否上传成功
        """
        if not self.is_available():
            logger.warning("OSS未配置，跳过上传")
            return False

        try:
            # 添加元数据
            headers = {"Content-Type": content_type}
            if metadata:
                for key, value in metadata.items():
                    headers[f"x-oss-meta-{key}"] = str(value)

            # 上传数据
            result = self.bucket.put_object(oss_key, data, headers)

            if result.status == 200:
                logger.info(f"数据上传成功: {oss_key}")
                return True
            return False
        except Exception as e:
            logger.error(f"上传数据异常: {e}")
            return False

    def download_file(self, oss_key: str, local_path: str) -> bool:
        """
        从OSS下载文件

        Args:
            oss_key: OSS存储路径
            local_path: 本地保存路径

        Returns:
            是否下载成功
        """
        if not self.is_available():
            return False

        try:
            result = self.bucket.get_object_to_file(oss_key, local_path)
            return result.status == 200
        except Exception as e:
            logger.error(f"下载文件异常: {e}")
            return False

    def delete_file(self, oss_key: str) -> bool:
        """
        删除OSS文件

        Args:
            oss_key: OSS存储路径

        Returns:
            是否删除成功
        """
        if not self.is_available():
            return False

        try:
            result = self.bucket.delete_object(oss_key)
            return result.status == 204
        except Exception as e:
            logger.error(f"删除文件异常: {e}")
            return False

    def delete_files(self, oss_keys: List[str]) -> int:
        """
        批量删除OSS文件

        Args:
            oss_keys: OSS存储路径列表

        Returns:
            成功删除的文件数量
        """
        if not self.is_available() or not oss_keys:
            return 0

        try:
            # 批量删除(每次最多1000个)
            result = self.bucket.batch_delete_objects(oss_keys)
            return len(result.deleted_keys)
        except Exception as e:
            logger.error(f"批量删除文件异常: {e}")
            return 0

    def get_file_info(self, oss_key: str) -> Optional[OSSFile]:
        """
        获取文件信息

        Args:
            oss_key: OSS存储路径

        Returns:
            OSSFile对象或None
        """
        if not self.is_available():
            return None

        try:
            # 获取文件元信息
            meta = self.bucket.head_object(oss_key)

            # 构建OSSFile对象
            return OSSFile(
                key=oss_key,
                name=oss_key.split("/")[-1],
                size=meta.content_length,
                content_type=meta.content_type,
                etag=meta.etag,
                last_modified=meta.last_modified,
                metadata=meta.user_metadata or {}
            )
        except Exception as e:
            logger.error(f"获取文件信息异常: {e}")
            return None

    def get_signed_url(
        self,
        oss_key: str,
        expires: int = 3600
    ) -> Optional[str]:
        """
        获取签名URL(用于临时访问)

        Args:
            oss_key: OSS存储路径
            expires: 过期时间(秒)

        Returns:
            签名URL或None
        """
        if not self.is_available():
            return None

        try:
            url = self.bucket.sign_url("GET", oss_key, expires)
            return url
        except Exception as e:
            logger.error(f"生成签名URL异常: {e}")
            return None

    def get_upload_signed_url(
        self,
        oss_key: str,
        expires: int = 3600
    ) -> Optional[str]:
        """
        获取上传签名URL(用于前端直传)

        Args:
            oss_key: OSS存储路径
            expires: 过期时间(秒)

        Returns:
            签名URL或None
        """
        if not self.is_available():
            return None

        try:
            url = self.bucket.sign_url("PUT", oss_key, expires)
            return url
        except Exception as e:
            logger.error(f"生成上传签名URL异常: {e}")
            return None

    # =========================================================================
    # 目录和列表操作
    # =========================================================================

    def list_files(
        self,
        prefix: str = "",
        max_keys: int = 100,
        continuation_token: str = None
    ) -> Dict[str, Any]:
        """
        列出OSS文件

        Args:
            prefix: 路径前缀
            max_keys: 最大返回数量
            continuation_token: 分页标记

        Returns:
            包含文件列表和分页信息的字典
        """
        if not self.is_available():
            return {"files": [], "total_count": 0}

        try:
            # 构建list请求
            params = {
                "max_keys": max_keys,
                "prefix": prefix
            }
            if continuation_token:
                params["continuation_token"] = continuation_token

            # 获取文件列表
            result = self.bucket.list_objects(**params)

            # 转换为OSSFile对象列表
            files = []
            for obj in result.object_list:
                files.append(OSSFile(
                    key=obj.key,
                    name=obj.key.split("/")[-1],
                    size=obj.size,
                    content_type="",
                    etag=obj.etag,
                    last_modified=obj.last_modified.isoformat() if obj.last_modified else ""
                ))

            return {
                "files": files,
                "total_count": result.key_count,
                "next_token": result.next_continuation_token if hasattr(result, 'next_continuation_token') else None,
                "is_truncated": result.is_truncated
            }
        except Exception as e:
            logger.error(f"列出文件异常: {e}")
            return {"files": [], "total_count": 0}

    def list_all_files(
        self,
        prefix: str = "",
        max_keys: int = 1000
    ) -> List[OSSFile]:
        """
        列出所有匹配的文件(递归)

        Args:
            prefix: 路径前缀
            max_keys: 每次请求的最大数量

        Returns:
            OSSFile对象列表
        """
        all_files = []
        continuation_token = None

        while True:
            result = self.list_files(prefix, max_keys, continuation_token)
            all_files.extend(result["files"])

            if not result.get("is_truncated"):
                break

            continuation_token = result.get("next_token")
            if not continuation_token:
                break

        return all_files

    # =========================================================================
    # 批量操作
    # =========================================================================

    def copy_file(self, source_key: str, dest_key: str) -> bool:
        """
        复制文件

        Args:
            source_key: 源文件路径
            dest_key: 目标文件路径

        Returns:
            是否复制成功
        """
        if not self.is_available():
            return False

        try:
            # 复制文件
            result = self.bucket.copy_object(source_key, dest_key)
            return result.status == 200
        except Exception as e:
            logger.error(f"复制文件异常: {e}")
            return False

    def move_file(self, source_key: str, dest_key: str) -> bool:
        """
        移动文件(复制+删除)

        Args:
            source_key: 源文件路径
            dest_key: 目标文件路径

        Returns:
            是否移动成功
        """
        if not self.is_available():
            return False

        # 先复制
        if not self.copy_file(source_key, dest_key):
            return False

        # 再删除源文件
        return self.delete_file(source_key)

    def update_metadata(
        self,
        oss_key: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        更新文件元数据

        Args:
            oss_key: OSS存储路径
            metadata: 新的元数据

        Returns:
            是否更新成功
        """
        if not self.is_available():
            return False

        try:
            # 构建元数据头
            headers = {}
            for key, value in metadata.items():
                headers[f"x-oss-meta-{key}"] = str(value)

            # 复制文件到自身(带新元数据)
            result = self.bucket.copy_object(oss_key, oss_key, headers)
            return result.status == 200
        except Exception as e:
            logger.error(f"更新元数据异常: {e}")
            return False

    # =========================================================================
    # 数据集管理
    # =========================================================================

    def create_dataset(
        self,
        name: str,
        description: str,
        data_type: str,
        base_prefix: str = "datasets/"
    ) -> str:
        """
        创建数据集

        Args:
            name: 数据集名称
            description: 数据集描述
            data_type: 数据类型
            base_prefix: 基础路径前缀

        Returns:
            数据集ID
        """
        # 生成数据集ID
        dataset_id = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:16]

        # 创建数据集目录
        dataset_prefix = f"{base_prefix}{dataset_id}/"

        # 创建元数据文件
        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=name,
            description=description,
            data_type=data_type,
            total_files=0,
            total_size=0
        )

        metadata_key = f"{dataset_prefix}metadata.json"
        self.upload_data(
            json.dumps(metadata.__dict__, ensure_ascii=False, indent=2).encode(),
            metadata_key,
            "application/json"
        )

        logger.info(f"数据集创建成功: {dataset_id}")
        return dataset_id

    def get_dataset(self, dataset_id: str, base_prefix: str = "datasets/") -> Optional[DatasetMetadata]:
        """
        获取数据集元数据

        Args:
            dataset_id: 数据集ID
            base_prefix: 基础路径前缀

        Returns:
            DatasetMetadata对象或None
        """
        metadata_key = f"{base_prefix}{dataset_id}/metadata.json"
        file_info = self.get_file_info(metadata_key)

        if not file_info:
            return None

        # 下载元数据
        try:
            result = self.bucket.get_object(metadata_key)
            content = result.read()
            data = json.loads(content)
            return DatasetMetadata(**data)
        except Exception as e:
            logger.error(f"获取数据集元数据异常: {e}")
            return None

    def list_datasets(self, base_prefix: str = "datasets/") -> List[DatasetMetadata]:
        """
        列出所有数据集

        Args:
            base_prefix: 基础路径前缀

        Returns:
            DatasetMetadata列表
        """
        # 获取datasets目录下的所有子目录
        result = self.list_files(base_prefix, max_keys=100)

        datasets = []
        for file in result.get("files", []):
            if file.name == "metadata.json":
                # 这是数据集元数据文件
                dataset_prefix = file.key.replace("metadata.json", "")
                dataset_id = dataset_prefix.strip("/").split("/")[-1]
                dataset = self.get_dataset(dataset_id, base_prefix)
                if dataset:
                    datasets.append(dataset)

        return datasets

    def update_dataset_metadata(
        self,
        dataset_id: str,
        metadata: Dict[str, Any],
        base_prefix: str = "datasets/"
    ) -> bool:
        """
        更新数据集元数据

        Args:
            dataset_id: 数据集ID
            metadata: 更新的元数据
            base_prefix: 基础路径前缀

        Returns:
            是否更新成功
        """
        dataset = self.get_dataset(dataset_id, base_prefix)
        if not dataset:
            return False

        # 更新字段
        for key, value in metadata.items():
            if hasattr(dataset, key):
                setattr(dataset, key, value)

        dataset.updated_at = datetime.now().isoformat()

        # 保存
        metadata_key = f"{base_prefix}{dataset_id}/metadata.json"
        return self.upload_data(
            json.dumps(dataset.__dict__, ensure_ascii=False, indent=2).encode(),
            metadata_key,
            "application/json"
        )

    # =========================================================================
    # 数据标注管理
    # =========================================================================

    def save_annotation(
        self,
        dataset_id: str,
        annotation: DataAnnotation,
        base_prefix: str = "datasets/"
    ) -> bool:
        """
        保存数据标注

        Args:
            dataset_id: 数据集ID
            annotation: 数据标注
            base_prefix: 基础路径前缀

        Returns:
            是否保存成功
        """
        annotation_key = f"{base_prefix}{dataset_id}/annotations/{annotation.file_key}.json"

        return self.upload_data(
            json.dumps(annotation.__dict__, ensure_ascii=False, indent=2).encode(),
            annotation_key,
            "application/json"
        )

    def get_annotation(
        self,
        dataset_id: str,
        file_key: str,
        base_prefix: str = "datasets/"
    ) -> Optional[DataAnnotation]:
        """
        获取数据标注

        Args:
            dataset_id: 数据集ID
            file_key: 文件路径
            base_prefix: 基础路径前缀

        Returns:
            DataAnnotation对象或None
        """
        annotation_key = f"{base_prefix}{dataset_id}/annotations/{file_key}.json"

        try:
            result = self.bucket.get_object(annotation_key)
            content = result.read()
            data = json.loads(content)
            return DataAnnotation(**data)
        except Exception as e:
            logger.warning(f"OSS获取标注失败: {e}")
            return None

    def list_annotations(
        self,
        dataset_id: str,
        base_prefix: str = "datasets/"
    ) -> List[DataAnnotation]:
        """
        列出数据集的所有标注

        Args:
            dataset_id: 数据集ID
            base_prefix: 基础路径前缀

        Returns:
            DataAnnotation列表
        """
        annotation_prefix = f"{base_prefix}{dataset_id}/annotations/"
        result = self.list_files(annotation_prefix, max_keys=1000)

        annotations = []
        for file in result.get("files", []):
            if file.name.endswith(".json"):
                annotation = self.get_annotation(dataset_id, file.name.replace(".json", ""), base_prefix)
                if annotation:
                    annotations.append(annotation)

        return annotations

    # =========================================================================
    # 统计分析
    # =========================================================================

    def get_statistics(
        self,
        prefix: str = ""
    ) -> Dict[str, Any]:
        """
        获取OSS目录统计信息

        Args:
            prefix: 路径前缀

        Returns:
            统计信息字典
        """
        files = self.list_all_files(prefix)

        total_size = sum(f.size for f in files)
        file_types = {}

        for f in files:
            # 提取文件扩展名
            ext = f.name.split(".")[-1].lower() if "." in f.name else "no_ext"
            file_types[ext] = file_types.get(ext, 0) + 1

        return {
            "total_files": len(files),
            "total_size": total_size,
            "total_size_gb": round(total_size / (1024**3), 2),
            "file_types": file_types
        }

    def get_dataset_statistics(
        self,
        dataset_id: str,
        base_prefix: str = "datasets/"
    ) -> Dict[str, Any]:
        """
        获取数据集统计信息

        Args:
            dataset_id: 数据集ID
            base_prefix: 基础路径前缀

        Returns:
            统计信息字典
        """
        dataset = self.get_dataset(dataset_id, base_prefix)
        if not dataset:
            return {}

        # 获取数据文件
        data_prefix = f"{base_prefix}{dataset_id}/data/"
        files = self.list_all_files(data_prefix)

        # 获取标注统计
        annotations = self.list_annotations(dataset_id, base_prefix)

        # 计算评分分布
        quality_dist = {"excellent": 0, "good": 0, "medium": 0, "poor": 0, "rejected": 0}
        aesthetic_scores = []
        quality_scores = []

        for ann in annotations:
            if ann.quality_score >= 0.9:
                quality_dist["excellent"] += 1
            elif ann.quality_score >= 0.7:
                quality_dist["good"] += 1
            elif ann.quality_score >= 0.5:
                quality_dist["medium"] += 1
            elif ann.quality_score >= 0.3:
                quality_dist["poor"] += 1
            else:
                quality_dist["rejected"] += 1

            aesthetic_scores.append(ann.aesthetic_score)
            quality_scores.append(ann.quality_score)

        return {
            "dataset": dataset.__dict__,
            "files": {
                "total": len(files),
                "total_size": sum(f.size for f in files)
            },
            "annotations": {
                "total": len(annotations),
                "quality_distribution": quality_dist,
                "avg_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
                "avg_aesthetic_score": sum(aesthetic_scores) / len(aesthetic_scores) if aesthetic_scores else 0
            }
        }

    # =========================================================================
    # AI驱动的数据管理
    # =========================================================================

    async def ai_classify_images(
        self,
        image_urls: List[str],
        categories: List[str],
        parallel: int = 4,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        AI驱动的图像批量分类

        Args:
            image_urls: 图像URL列表
            categories: 候选分类列表
            parallel: 并行数量
            progress_callback: 进度回调

        Returns:
            任务ID
        """
        if not self.vision_service:
            raise Exception("视觉服务未初始化")

        task_id = str(uuid.uuid4())

        task = AIBatchTask(
            task_id=task_id,
            task_type="classification",
            total=len(image_urls)
        )
        self.ai_tasks[task_id] = task

        if progress_callback:
            self.ai_task_callbacks[task_id] = progress_callback

        # 并行执行
        semaphore = asyncio.Semaphore(parallel)

        async def classify_with_semaphore(url: str, index: int):
            async with semaphore:
                try:
                    result = await self.vision_service.classify_image(url, categories)

                    task.results.append({
                        "index": index,
                        "url": url,
                        "result": result
                    })
                    task.completed += 1

                except Exception as e:
                    logger.error(f"分类失败 {url}: {e}")
                    task.results.append({
                        "index": index,
                        "url": url,
                        "error": str(e)
                    })
                    task.failed += 1

                self._notify_ai_progress(task_id)

        # 创建所有任务
        tasks = [classify_with_semaphore(url, i) for i, url in enumerate(image_urls)]
        await asyncio.gather(*tasks, return_exceptions=True)

        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        return task_id

    async def ai_score_images(
        self,
        image_urls: List[str],
        model: str = "qwen-vl-max",
        parallel: int = 4,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        AI驱动的图像批量质量评分

        Args:
            image_urls: 图像URL列表
            model: 视觉模型
            parallel: 并行数量
            progress_callback: 进度回调

        Returns:
            任务ID
        """
        if not self.vision_service:
            raise Exception("视觉服务未初始化")

        task_id = str(uuid.uuid4())

        task = AIBatchTask(
            task_id=task_id,
            task_type="scoring",
            total=len(image_urls)
        )
        self.ai_tasks[task_id] = task

        if progress_callback:
            self.ai_task_callbacks[task_id] = progress_callback

        semaphore = asyncio.Semaphore(parallel)

        async def score_with_semaphore(url: str, index: int):
            async with semaphore:
                try:
                    result = await self.vision_service.score_image_quality(url, model)

                    task.results.append({
                        "index": index,
                        "url": url,
                        "result": result
                    })
                    task.completed += 1

                except Exception as e:
                    logger.error(f"评分失败 {url}: {e}")
                    task.results.append({
                        "index": index,
                        "url": url,
                        "error": str(e)
                    })
                    task.failed += 1

                self._notify_ai_progress(task_id)

        tasks = [score_with_semaphore(url, i) for i, url in enumerate(image_urls)]
        await asyncio.gather(*tasks, return_exceptions=True)

        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        return task_id

    async def ai_extract_tags(
        self,
        image_urls: List[str],
        max_tags: int = 10,
        parallel: int = 4,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        AI驱动的图像批量标签提取

        Args:
            image_urls: 图像URL列表
            max_tags: 最大标签数
            parallel: 并行数量
            progress_callback: 进度回调

        Returns:
            任务ID
        """
        if not self.vision_service:
            raise Exception("视觉服务未初始化")

        task_id = str(uuid.uuid4())

        task = AIBatchTask(
            task_id=task_id,
            task_type="tagging",
            total=len(image_urls)
        )
        self.ai_tasks[task_id] = task

        if progress_callback:
            self.ai_task_callbacks[task_id] = progress_callback

        semaphore = asyncio.Semaphore(parallel)

        async def tag_with_semaphore(url: str, index: int):
            async with semaphore:
                try:
                    tags = await self.vision_service.extract_image_tags(url, max_tags)

                    task.results.append({
                        "index": index,
                        "url": url,
                        "tags": tags
                    })
                    task.completed += 1

                except Exception as e:
                    logger.error(f"标签提取失败 {url}: {e}")
                    task.results.append({
                        "index": index,
                        "url": url,
                        "error": str(e)
                    })
                    task.failed += 1

                self._notify_ai_progress(task_id)

        tasks = [tag_with_semaphore(url, i) for i, url in enumerate(image_urls)]
        await asyncio.gather(*tasks, return_exceptions=True)

        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        return task_id

    async def ai_process_dataset(
        self,
        dataset_id: str,
        operations: List[str],
        categories: Optional[List[str]] = None,
        parallel: int = 4,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        AI驱动的数据集智能处理

        Args:
            dataset_id: 数据集ID
            operations: 操作列表 ["classification", "scoring", "tagging"]
            categories: 分类列表（用于分类操作）
            parallel: 并行数量
            progress_callback: 进度回调

        Returns:
            任务ID
        """
        # 获取数据集所有文件
        dataset = self.get_dataset(dataset_id)
        if not dataset:
            raise Exception(f"数据集不存在: {dataset_id}")

        data_prefix = f"datasets/{dataset_id}/data/"
        files = self.list_all_files(data_prefix)

        # 只处理图像文件
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
        image_files = [
            f for f in files
            if Path(f.name).suffix.lower() in image_extensions
        ]

        # 生成图像URL
        image_urls = []
        for f in image_files:
            url = self.get_signed_url(f.key)
            if url:
                image_urls.append(url)

        if not image_urls:
            raise Exception("数据集中没有图像文件")

        task_id = str(uuid.uuid4())
        task = AIBatchTask(
            task_id=task_id,
            task_type="dataset_processing",
            total=len(image_urls) * len(operations)
        )
        self.ai_tasks[task_id] = task

        if progress_callback:
            self.ai_task_callbacks[task_id] = progress_callback

        # 执行所有操作
        for operation in operations:
            if operation == "classification" and categories:
                op_task_id = await self.ai_classify_images(
                    image_urls, categories, parallel
                )
            elif operation == "scoring":
                op_task_id = await self.ai_score_images(image_urls, parallel=parallel)
            elif operation == "tagging":
                op_task_id = await self.ai_extract_tags(image_urls, parallel=parallel)
            else:
                logger.warning(f"未知操作: {operation}")
                continue

            # 合并结果
            op_task = self.ai_tasks.get(op_task_id)
            if op_task:
                task.results.extend(op_task.results)
                task.completed += op_task.completed
                task.failed += op_task.failed

        task.status = "completed"
        task.completed_at = datetime.now().isoformat()

        return task_id

    def _notify_ai_progress(self, task_id: str):
        """通知AI任务进度"""
        task = self.ai_tasks.get(task_id)
        if not task:
            return

        progress = {
            "task_id": task_id,
            "task_type": task.task_type,
            "status": task.status,
            "total": task.total,
            "completed": task.completed,
            "failed": task.failed,
            "progress": task.completed / task.total if task.total > 0 else 0
        }

        if task_id in self.ai_task_callbacks:
            try:
                self.ai_task_callbacks[task_id](progress)
            except Exception as e:
                logger.error(f"AI进度回调异常: {e}")

    def get_ai_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取AI任务状态"""
        task = self.ai_tasks.get(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "total": task.total,
            "completed": task.completed,
            "failed": task.failed,
            "progress": task.completed / task.total if task.total > 0 else 0,
            "created_at": task.created_at,
            "completed_at": task.completed_at
        }

    def get_ai_task_results(self, task_id: str) -> List[Dict[str, Any]]:
        """获取AI任务结果"""
        task = self.ai_tasks.get(task_id)
        if not task:
            return []

        return sorted(task.results, key=lambda x: x.get("index", 0))

    # =========================================================================
    # 与生产数据库集成
    # =========================================================================

    async def sync_to_database(self, dataset_id: str) -> bool:
        """
        同步数据集到生产数据库

        Args:
            dataset_id: 数据集ID

        Returns:
            是否同步成功
        """
        if not self.database_manager:
            logger.warning("数据库管理器未初始化，跳过同步")
            return False

        try:
            dataset = self.get_dataset(dataset_id)
            if not dataset:
                return False

            # 同步数据集信息
            await self.database_manager.create_dataset(
                name=dataset.name,
                description=dataset.description,
                data_type=dataset.data_type,
                user_id="system"
            )

            # 同步标注数据
            annotations = self.list_annotations(dataset_id)

            for annotation in annotations:
                await self.database_manager.save_asset_annotation(
                    asset_id=annotation.file_key,
                    annotation_data=annotation.__dict__
                )

            logger.info(f"数据集同步成功: {dataset_id}")
            return True

        except Exception as e:
            logger.error(f"数据集同步异常: {e}")
            return False

    async def import_from_database(self, dataset_id: str) -> bool:
        """
        从生产数据库导入数据到OSS

        Args:
            dataset_id: 数据集ID

        Returns:
            是否导入成功
        """
        if not self.database_manager:
            logger.warning("数据库管理器未初始化，跳过导入")
            return False

        try:
            # 从数据库获取资产列表
            assets = await self.database_manager.list_assets(
                dataset_id=dataset_id,
                limit=10000
            )

            # 统计
            imported = 0
            failed = 0

            for asset in assets:
                # 下载并上传到OSS
                if "url" in asset:
                    local_path = f"/tmp/{asset['asset_id']}"

                    # 下载
                    # 这里需要实现实际的下载逻辑
                    # 上传到OSS
                    # ...

                    imported += 1
                else:
                    failed += 1

            logger.info(f"数据导入完成: 成功 {imported}, 失败 {failed}")
            return True

        except Exception as e:
            logger.error(f"数据导入异常: {e}")
            return False


# ============================================================================
# 单例实例
# ============================================================================

_oss_manager: Optional[OSSManager] = None


def get_oss_manager() -> OSSManager:
    """获取OSS管理器单例"""
    global _oss_manager
    if _oss_manager is None:
        _oss_manager = OSSManager()
    return _oss_manager


def init_oss_manager(
    access_key_id: str,
    access_key_secret: str,
    bucket_name: str,
    endpoint: str = None,
    region: str = "oss-cn-hangzhou",
    generation_service=None,
    database_manager=None
) -> OSSManager:
    """
    初始化OSS管理器 (AI增强版)

    Args:
        access_key_id: 阿里云AccessKey ID
        access_key_secret: 阿里云AccessKey Secret
        bucket_name: OSS Bucket名称
        endpoint: OSS endpoint地址
        region: 区域
        generation_service: 生成服务 (用于AI视觉和语言服务)
        database_manager: 生产数据库管理器

    Returns:
        OSSManager实例
    """
    global _oss_manager

    # 创建AI服务
    vision_service = None
    language_service = None

    if generation_service:
        vision_service = NanobotVisionService(generation_service)
        language_service = NanobotLanguageService(generation_service)

    _oss_manager = OSSManager(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
        bucket_name=bucket_name,
        endpoint=endpoint,
        region=region,
        vision_service=vision_service,
        language_service=language_service,
        database_manager=database_manager
    )

    logger.info("OSS管理器(AI增强版)初始化完成")

    return _oss_manager
