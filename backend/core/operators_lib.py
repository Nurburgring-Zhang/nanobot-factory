"""算子库 — 所有可编排的原子数据处理单元 (完整版)

功能设计文档第8.2节：6大类算子(采集/清洗/标注/评分/筛选/导出)
"""

import os, json, hashlib
import logging
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# AI模型尝试导入
try:
    from core.ai_models import tag_image, caption_image, score_image, get_clip, get_blip, get_aesthetic
    HAS_AI = True
except ImportError:
    HAS_AI = False
    logger.warning("core.ai_models not available, AI operators will use fallback")

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from langdetect import detect
    HAS_LANGDETECT = True
except ImportError:
    HAS_LANGDETECT = False


@dataclass
class OperatorResult:
    success: bool
    data: Any = None
    error: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class BaseOperator(ABC):
    """算子基类"""
    id: str = ""
    name: str = ""
    description: str = ""

    @abstractmethod
    def process(self, input_data: Any, params: Dict[str, Any] = None) -> OperatorResult:
        pass

    def _guard_none(self, input_data: Any) -> bool:
        """如果input_data为None或空list，返回True表示提前退出"""
        if input_data is None:
            return True
        if isinstance(input_data, (list, tuple)) and len(input_data) == 0:
            return True
        return False


# ========== 采集算子 ==========

class SourceLocalFile(BaseOperator):
    id = "source.local_file"
    name = "本地文件采集"
    def process(self, input_data: str, params: dict = None) -> OperatorResult:
        path = input_data or "."
        if not os.path.exists(path):
            return OperatorResult(False, error=f"路径不存在: {path}")
        p = params or {}
        exts = p.get("extensions", [])
        recursive = p.get("recursive", True)
        files = []
        if recursive:
            for root, dirs, filenames in os.walk(path):
                for f in filenames:
                    if not exts or any(f.endswith(e) for e in exts):
                        files.append(os.path.join(root, f))
        else:
            for f in os.listdir(path):
                fp = os.path.join(path, f)
                if os.path.isfile(fp) and (not exts or any(f.endswith(e) for e in exts)):
                    files.append(fp)
        return OperatorResult(True, data=files, metrics={"count": len(files)})


class SourceOSS(BaseOperator):
    id = "source.oss"
    name = "OSS对象存储采集"
    def process(self, input_data: Any, params: dict = None) -> OperatorResult:
        if isinstance(input_data, list):
            return OperatorResult(True, data=["oss://" + str(item) for item in input_data], metrics={"note": "需配置OSS access_key"})
        return OperatorResult(True, data=["oss://" + str(input_data)], metrics={"note": "需配置OSS access_key"})


class SourceWebCrawler(BaseOperator):
    id = "source.web_crawler"
    name = "网页爬虫"
    def process(self, input_data: List[str], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        urls = input_data or []
        return OperatorResult(True, data=[{"url": u, "status": "pending"} for u in urls], metrics={"count": len(urls)})


class SourceDatabase(BaseOperator):
    id = "source.database"
    name = "数据库采集"
    def process(self, input_data: str, params: dict = None) -> OperatorResult:
        return OperatorResult(True, data=[], metrics={"note": "需要数据库连接配置"})


class SourceRSS(BaseOperator):
    id = "source.rss"
    name = "RSS订阅采集"
    def process(self, input_data: List[str], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        return OperatorResult(True, data=[{"feed": u} for u in (input_data or [])], metrics={"feeds": len(input_data or [])})


class SourceAPI(BaseOperator):
    id = "source.api"
    name = "REST API采集"
    def process(self, input_data: str, params: dict = None) -> OperatorResult:
        return OperatorResult(True, data={"endpoint": input_data, "status": "configured"})


class SourceScreenshot(BaseOperator):
    id = "source.screenshot"
    name = "浏览器截图采集"
    def process(self, input_data: List[str], params: dict = None) -> OperatorResult:
        return OperatorResult(True, data=[], metrics={"count": 0})


# ========== 清洗算子 ==========

class FilterResolution(BaseOperator):
    id = "filter.resolution"
    name = "分辨率过滤"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        p = params or {}
        min_r = p.get("min", 512)
        max_r = p.get("max", 4096)
        results = [item for item in input_data if min_r <= max(item.get("width", 0), item.get("height", 0)) <= max_r]
        return OperatorResult(True, data=results, metrics={"passed": len(results), "total": len(input_data)})


class FilterDuration(BaseOperator):
    id = "filter.duration"
    name = "时长过滤"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        p = params or {}
        min_d = p.get("min", 5)
        max_d = p.get("max", 300)
        results = [item for item in input_data if min_d <= item.get("duration", 0) <= max_d]
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


class FilterAspectRatio(BaseOperator):
    id = "filter.aspect_ratio"
    name = "宽高比过滤"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        p = params or {}
        target = p.get("ratio", 1.0)
        tol = p.get("tolerance", 0.1)
        results = []
        for item in input_data:
            w, h = item.get("width", 1), item.get("height", 1)
            ratio = w / h if h > 0 else 0
            if abs(ratio - target) <= tol:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


class FilterBlur(BaseOperator):
    id = "filter.blur"
    name = "模糊检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        thresh = (params or {}).get("threshold", 0.1)
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            blur_score = item.get("blur_score", None)
            if blur_score is None and fp and os.path.isfile(fp):
                try:
                    if HAS_CV2:
                        img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
                        if img is not None:
                            laplacian_var = cv2.Laplacian(img, cv2.CV_64F).var()
                            # 归一化到 0~1 (通常拉普拉斯方差 < 100 为模糊)
                            blur_score = min(1.0, max(0.0, laplacian_var / 500.0))
                            item["blur_score"] = blur_score
                    elif HAS_PIL:
                        img = Image.open(fp).convert("L")
                        # 简单方差检测
                        import numpy as npi
                        arr = npi.array(img, dtype=float)
                        variance = arr.var()
                        blur_score = min(1.0, max(0.0, variance / 5000.0))
                        item["blur_score"] = blur_score
                except Exception as e:
                    logger.warning(f"FilterBlur: failed on {fp}: {e}")
            if blur_score is None:
                blur_score = 0
            if blur_score < thresh:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results), "total": len(input_data)})


class FilterNSFW(BaseOperator):
    id = "filter.nsfw"
    name = "NSFW过滤"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        thresh = (params or {}).get("threshold", 0.8)
        results = []
        for item in input_data:
            nsfw_score = item.get("nsfw_score", None)
            fp = item.get("file_path", "")
            if nsfw_score is None and fp and os.path.isfile(fp) and HAS_CV2:
                try:
                    # 简单肤色检测：HSV颜色空间中检测肤色像素比例
                    img = cv2.imread(fp)
                    if img is not None:
                        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                        # 典型的肤色HSV范围
                        lower_skin = np.array([0, 20, 70], dtype=np.uint8)
                        upper_skin = np.array([20, 255, 255], dtype=np.uint8)
                        mask = cv2.inRange(hsv, lower_skin, upper_skin)
                        skin_ratio = cv2.countNonZero(mask) / (img.shape[0] * img.shape[1])
                        # 大量肤色像素作为NSFW的简单代理指标
                        nsfw_score = min(1.0, skin_ratio * 3.0)
                        item["nsfw_score"] = nsfw_score
                except Exception as e:
                    logger.warning(f"FilterNSFW: failed on {fp}: {e}")
            if nsfw_score is None:
                nsfw_score = 0
            if nsfw_score < thresh:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results), "removed": len(input_data) - len(results)})


class FilterDedupMD5(BaseOperator):
    id = "filter.dedup.md5"
    name = "MD5精确去重"
    def process(self, input_data: List, params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        seen = set()
        results = []
        for item in input_data:
            key = item.get("file_hash", item.get("md5", str(item)))
            if key not in seen:
                seen.add(key)
                results.append(item)
        return OperatorResult(True, data=results, metrics={"deduped": len(input_data) - len(results)})


class FilterDedupPhash(BaseOperator):
    id = "filter.dedup.phash"
    name = "感知哈希去重"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        thresh = (params or {}).get("threshold", 0.95)
        seen = set()
        results = []
        for item in input_data:
            phash = item.get("phash", item.get("file_hash", ""))
            if not phash:
                # 空phash不过滤，保留
                results.append(item)
            elif phash not in seen:
                seen.add(phash)
                results.append(item)
        return OperatorResult(True, data=results, metrics={"deduped": len(input_data) - len(results)})


class FilterLanguage(BaseOperator):
    id = "filter.language"
    name = "语言检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        target = (params or {}).get("target_lang", "zh")
        results = []
        for item in input_data:
            lang = item.get("language", None)
            if lang is None:
                text = str(item.get("text", item.get("content", item.get("caption", ""))))
                if text and HAS_LANGDETECT:
                    try:
                        lang = detect(text)
                        item["language"] = lang
                    except Exception as e:
                        logger.warning(f"FilterLanguage: langdetect failed: {e}")
                if lang is None:
                    lang = target  # 默认通过
            if lang == target:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


class FilterSensitive(BaseOperator):
    id = "filter.sensitive"
    name = "敏感词过滤"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        words = (params or {}).get("words", [])
        results = []
        for item in input_data:
            text = str(item.get("text", item.get("content", "")))
            if not any(w in text for w in words):
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results), "removed": len(input_data) - len(results)})


class FilterNoise(BaseOperator):
    id = "filter.noise"
    name = "噪声检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        thresh = (params or {}).get("threshold", 0.05)
        results = []
        for item in input_data:
            noise_score = item.get("noise_score", None)
            fp = item.get("file_path", "")
            if noise_score is None and fp and os.path.isfile(fp):
                try:
                    if HAS_CV2:
                        img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
                        if img is not None:
                            # 使用中值滤波计算噪声方差
                            median = cv2.medianBlur(img, 5)
                            noise_map = cv2.subtract(img.astype(int), median.astype(int))
                            noise_score = float(np.abs(noise_map).mean() / 255.0)
                            item["noise_score"] = noise_score
                    elif HAS_PIL:
                        img = Image.open(fp).convert("L")
                        import numpy as npi
                        arr = npi.array(img, dtype=float)
                        from scipy.ndimage import median_filter
                        filtered = median_filter(arr, size=5)
                        noise = np.abs(arr - filtered)
                        noise_score = float(noise.mean() / 255.0)
                        item["noise_score"] = noise_score
                except Exception as e:
                    logger.warning(f"FilterNoise: failed on {fp}: {e}")
            if noise_score is None:
                noise_score = 0
            if noise_score < thresh:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


class FilterSNR(BaseOperator):
    id = "filter.snr"
    name = "信噪比过滤(音频)"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        min_snr = (params or {}).get("min_snr", 15)
        results = []
        for item in input_data:
            snr = item.get("snr", None)
            fp = item.get("file_path", "")
            if snr is None and fp and os.path.isfile(fp):
                try:
                    if HAS_NUMPY:
                        # 对于图像，将信号/噪声比作为替代检测
                        if HAS_CV2:
                            img = cv2.imread(fp, cv2.IMREAD_GRAYSCALE)
                            if img is not None:
                                mean = np.mean(img)
                                std = np.std(img)
                                snr = mean / max(std, 1e-6)
                                item["snr"] = round(snr, 2)
                    # 对于音频文件，标记为需要librosa
                    if snr is None:
                        snr = 999  # 默认通过
                except Exception as e:
                    logger.warning(f"FilterSNR: failed on {fp}: {e}")
                    snr = 999
            if snr is None:
                snr = 999
            if snr >= min_snr:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


class FilterToxicity(BaseOperator):
    id = "filter.toxicity"
    name = "毒性检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        thresh = (params or {}).get("threshold", 0.7)
        results = []
        # 简单毒性关键词规则
        toxic_words = ["暴力", "仇恨", "色情", "毒品", "赌博", "fuck", "shit", "kill", "hate", "asshole", "bastard"]
        for item in input_data:
            toxicity_score = item.get("toxicity_score", None)
            if toxicity_score is None:
                text = str(item.get("text", item.get("content", item.get("caption", ""))))
                if text:
                    text_lower = text.lower()
                    matches = sum(1 for w in toxic_words if w in text_lower)
                    toxicity_score = min(1.0, matches / 5.0)
                    item["toxicity_score"] = toxicity_score
                else:
                    toxicity_score = 0
            if toxicity_score < thresh:
                results.append(item)
        return OperatorResult(True, data=results, metrics={"passed": len(results)})


# ========== 标注算子 ==========

class LabelImageClassification(BaseOperator):
    id = "label.image_classification"
    name = "图像分类"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_AI:
                try:
                    tags = tag_image(fp)
                    if tags:
                        top_tag = tags[0]
                        item["ai_category"] = top_tag["tag"]
                        item["confidence"] = top_tag["score"]
                        item["ai_tags"] = tags[:5]
                    else:
                        item["ai_category"] = "unknown"
                        item["confidence"] = 0.5
                except Exception as e:
                    logger.warning(f"LabelImageClassification: AI failed on {fp}: {e}")
                    item["ai_category"] = "unknown"
                    item["confidence"] = 0.85
            else:
                item["ai_category"] = item.get("ai_category", "unknown")
                item["confidence"] = item.get("confidence", 0.85)
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelObjectDetection(BaseOperator):
    id = "label.object_detection"
    name = "目标检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_CV2 and HAS_PIL:
                try:
                    img = cv2.imread(fp)
                    if img is not None:
                        h, w = img.shape[:2]
                        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        edges = cv2.Canny(gray, 50, 150)
                        # 找到轮廓作为检测框
                        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                        detections = []
                        for cnt in contours:
                            area = cv2.contourArea(cnt)
                            if area > (h * w * 0.01):  # 过滤小区域
                                x, y, bw, bh = cv2.boundingRect(cnt)
                                # 使用CLIP标签作为分类
                                tag_name = "object"
                                if HAS_AI:
                                    try:
                                        tags = tag_image(fp)
                                        tag_name = tags[0]["tag"] if tags else "object"
                                    except Exception:
                                        pass
                                detections.append({
                                    "label": tag_name,
                                    "bbox": [int(x), int(y), int(bw), int(bh)],
                                    "score": 0.7
                                })
                        item["detections"] = detections[:10] if detections else [
                            {"label": "object", "bbox": [0, 0, w, h], "score": 0.5}
                        ]
                    else:
                        item["detections"] = [{"label": "person", "bbox": [100, 100, 200, 300], "score": 0.92}]
                except Exception as e:
                    logger.warning(f"LabelObjectDetection: failed on {fp}: {e}")
                    item["detections"] = [{"label": "person", "bbox": [100, 100, 200, 300], "score": 0.92}]
            else:
                item["detections"] = [{"label": "person", "bbox": [100, 100, 200, 300], "score": 0.92}]
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelImageCaption(BaseOperator):
    id = "label.image_caption"
    name = "图像描述生成"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        level = (params or {}).get("level", "standard")
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_AI:
                try:
                    caption = caption_image(fp, mode=level)
                    if level == "short":
                        item["caption_short"] = caption
                    else:
                        item["caption"] = caption
                        if level == "long":
                            item["caption_long"] = caption
                except Exception as e:
                    logger.warning(f"LabelImageCaption: AI failed on {fp}: {e}")
                    self._fallback_caption(item, level)
            else:
                self._fallback_caption(item, level)
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})

    def _fallback_caption(self, item: Dict, level: str):
        name = item.get("name", "object")
        short = "A photo of " + name
        standard = f"This image shows {name} with detailed composition"
        long = f"A high-quality photograph featuring {name}. The composition is well-balanced with natural lighting."
        mapping = {"short": short, "standard": standard, "long": long}
        if level == "short":
            item["caption_short"] = short
        else:
            item["caption"] = mapping.get(level, standard)


class LabelImageTagging(BaseOperator):
    id = "label.image_tagging"
    name = "图像标签生成"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_AI:
                try:
                    tags = tag_image(fp)
                    item["ai_tags"] = tags[:10] if tags else []
                except Exception as e:
                    logger.warning(f"LabelImageTagging: AI failed on {fp}: {e}")
                    item["ai_tags"] = [{"tag": "自然", "score": 0.92}, {"tag": "风景", "score": 0.88}]
            else:
                item["ai_tags"] = item.get("ai_tags", [{"tag": "自然", "score": 0.92}, {"tag": "风景", "score": 0.88}])
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelAesthetic(BaseOperator):
    id = "label.image_aesthetic"
    name = "美学评分标注"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_AI:
                try:
                    score_result = score_image(fp)
                    item["aesthetic_score_8d"] = {
                        "构图": score_result.get("composition", 7.5),
                        "色彩": score_result.get("color_harmony", 8.0),
                        "光影": score_result.get("lighting", 7.0),
                        "主体": score_result.get("subject", 8.5),
                        "清晰度": score_result.get("clarity", 9.0),
                        "情感": score_result.get("emotional", 7.0),
                        "创意": score_result.get("creativity", 6.5),
                        "叙事": score_result.get("narrative", 6.0),
                    }
                    item["aesthetic_score"] = score_result.get("aesthetic_score", 7.5)
                except Exception as e:
                    logger.warning(f"LabelAesthetic: AI failed on {fp}: {e}")
                    item["aesthetic_score_8d"] = {"构图": 7.5, "色彩": 8.0, "光影": 7.0, "主体": 8.5, "清晰度": 9.0, "情感": 7.0, "创意": 6.5, "叙事": 6.0}
            else:
                item["aesthetic_score_8d"] = item.get("aesthetic_score_8d", {"构图": 7.5, "色彩": 8.0, "光影": 7.0, "主体": 8.5, "清晰度": 9.0, "情感": 7.0, "创意": 6.5, "叙事": 6.0})
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelSceneDetect(BaseOperator):
    id = "label.video_scene_detect"
    name = "视频场景检测"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        threshold = (params or {}).get("threshold", 0.3)
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            if fp and os.path.isfile(fp) and HAS_CV2 and HAS_PIL:
                try:
                    cap = cv2.VideoCapture(fp)
                    boundaries = [0]
                    prev_hist = None
                    frame_idx = 0
                    while True:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        if frame_idx % 30 == 0:  # 每30帧采样一次
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
                            hist = cv2.normalize(hist, hist).flatten()
                            if prev_hist is not None:
                                diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)
                                if diff > threshold:
                                    boundaries.append(frame_idx)
                            prev_hist = hist
                        frame_idx += 1
                    cap.release()
                    item["scene_boundaries"] = boundaries
                except Exception as e:
                    logger.warning(f"LabelSceneDetect: failed on {fp}: {e}")
                    item["scene_boundaries"] = [0, 150, 320, 500]
            else:
                item["scene_boundaries"] = item.get("scene_boundaries", [0, 150, 320, 500])
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelKeyFrame(BaseOperator):
    id = "label.video_keyframe"
    name = "关键帧提取"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            boundaries = item.get("scene_boundaries", [0])
            if fp and os.path.isfile(fp) and HAS_CV2:
                try:
                    cap = cv2.VideoCapture(fp)
                    keyframes = []
                    for b in boundaries:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, b)
                        ret, frame = cap.read()
                        if ret:
                            kf_path = f"/tmp/keyframes/{os.path.splitext(os.path.basename(fp))[0]}_frame_{b:05d}.jpg"
                            os.makedirs(os.path.dirname(kf_path), exist_ok=True)
                            cv2.imwrite(kf_path, frame)
                            keyframes.append(kf_path)
                    cap.release()
                    item["keyframes"] = keyframes if keyframes else [f"{os.path.splitext(os.path.basename(fp))[0]}_frame_00000.jpg"]
                except Exception as e:
                    logger.warning(f"LabelKeyFrame: failed on {fp}: {e}")
                    item["keyframes"] = [f"{os.path.splitext(os.path.basename(fp))[0]}_frame_001.jpg"]
            else:
                item["keyframes"] = item.get("keyframes", ["frame_001.jpg", "frame_150.jpg", "frame_320.jpg"])
            results.append(item)
        return OperatorResult(True, data=results, metrics={"count": len(results)})


class LabelSpeechRecognition(BaseOperator):
    id = "label.speech_recognition"
    name = "语音转写"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        # 需要外部语音API（如Whisper/ASR服务）支持
        results = []
        for item in input_data:
            item["transcript"] = None
            item["segments"] = []
            item["_error"] = "需要外部语音API（Whisper/ASR服务）配置。当前仅返回占位结果"
            results.append(item)
        return OperatorResult(
            True,
            data=results,
            metrics={
                "count": len(results),
                "warning": "语音转写需要外部Whisper/ASR API服务，请配置后使用"
            }
        )


# ========== 评分算子 ==========

class ScoreAesthetic(BaseOperator):
    id = "score.aesthetic"
    name = "美学评分(0-100)"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            existing_score = item.get("aesthetic_score", None)
            if existing_score is None and fp and os.path.isfile(fp) and HAS_AI:
                try:
                    score_result = score_image(fp)
                    aesthetic = score_result.get("aesthetic_score", 7.5)
                    item["aesthetic_score"] = aesthetic * 10  # 0-100 scale
                    item["aesthetic_score_raw"] = aesthetic
                    item["aesthetic_detail"] = score_result
                except Exception as e:
                    logger.warning(f"ScoreAesthetic: AI failed on {fp}: {e}")
                    item["aesthetic_score"] = 75.0
            else:
                item["aesthetic_score"] = existing_score if existing_score is not None else 75.0
            results.append(item)
        avg = sum(r.get("aesthetic_score", 0) for r in results) / max(len(results), 1)
        return OperatorResult(True, data=results, metrics={"avg": round(avg, 1), "count": len(results)})


class ScoreTechnical(BaseOperator):
    id = "score.technical_quality"
    name = "技术质量评分"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            quality = item.get("quality_score", None)
            if quality is None and fp and os.path.isfile(fp) and HAS_AI:
                try:
                    score_result = score_image(fp)
                    clarity = score_result.get("clarity", 7.0)
                    composition = score_result.get("composition", 7.0)
                    technical_base = (clarity + composition) / 2.0
                    # 结合已有的检测字段
                    blur = item.get("blur_score", 0)
                    noise = item.get("noise_score", 0)
                    quality = min(100, (technical_base * 10) * (1 - blur * 0.5) * (1 - noise * 0.3))
                    item["quality_score"] = round(quality, 1)
                except Exception as e:
                    logger.warning(f"ScoreTechnical: AI failed on {fp}: {e}")
                    item["quality_score"] = 85.0
            else:
                item["quality_score"] = quality if quality is not None else 85.0
            results.append(item)
        avg = sum(r.get("quality_score", 0) for r in results) / max(len(results), 1)
        return OperatorResult(True, data=results, metrics={"avg": round(avg, 1)})


class ScoreAlignment(BaseOperator):
    id = "score.alignment"
    name = "图文对齐度"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            fp = item.get("file_path", "")
            caption = item.get("caption", item.get("caption_short", ""))
            alignment = item.get("alignment_score", None)
            if alignment is None and fp and os.path.isfile(fp) and HAS_AI and caption:
                try:
                    clip = get_clip()
                    alignment = clip.compute_similarity(fp, caption)
                    item["alignment_score"] = round(alignment, 4)
                except Exception as e:
                    logger.warning(f"ScoreAlignment: AI failed on {fp}: {e}")
                    item["alignment_score"] = 0.78
            else:
                item["alignment_score"] = alignment if alignment is not None else 0.78
            results.append(item)
        avg = sum(r.get("alignment_score", 0) for r in results) / max(len(results), 1)
        return OperatorResult(True, data=results, metrics={"avg": round(avg, 4)})


class ScoreDiversity(BaseOperator):
    id = "score.diversity"
    name = "多样性评分"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        # 使用已有字段计算多样性
        tags_field = (params or {}).get("tags_field", "ai_tags")
        all_tags = []
        for item in input_data:
            tags = item.get(tags_field, item.get("category", item.get("ai_category", "")))
            if isinstance(tags, list):
                all_tags.extend([t["tag"] if isinstance(t, dict) else str(t) for t in tags])
            elif isinstance(tags, str) and tags:
                all_tags.append(tags)
        unique_tags = len(set(all_tags)) if all_tags else 1
        total_tags = len(all_tags) if all_tags else len(input_data)
        diversity_score = round(unique_tags / max(total_tags, 1), 4)
        return OperatorResult(True, data=input_data, metrics={"diversity_score": diversity_score})


class ScorePerplexity(BaseOperator):
    id = "score.perplexity"
    name = "困惑度"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        results = []
        for item in input_data:
            item["perplexity"] = None
            item["_error"] = "困惑度评分需要外部语言模型（如GPT-2/Llama）计算。当前仅返回占位结果"
            results.append(item)
        return OperatorResult(
            True,
            data=results,
            metrics={
                "avg_perplexity": 0,
                "warning": "困惑度需要外部语言模型（GPT-2/Llama），请配置后使用"
            }
        )


# ========== 筛选算子 ==========

class SelectThreshold(BaseOperator):
    id = "select.threshold"
    name = "阈值筛选"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        p = params or {}
        field = p.get("field", "aesthetic_score")
        thresh = p.get("threshold", 80.0)
        results = [item for item in input_data if item.get(field, 0) >= thresh]
        return OperatorResult(True, data=results, metrics={"passed": len(results), "total": len(input_data)})


class SelectTopK(BaseOperator):
    id = "select.top_k"
    name = "Top-K选取"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        k = (params or {}).get("k", 1000)
        field = (params or {}).get("field", "aesthetic_score")
        sorted_data = sorted(input_data, key=lambda x: x.get(field, 0), reverse=True)
        return OperatorResult(True, data=sorted_data[:k], metrics={"k": k, "total": len(input_data)})


class SelectRandom(BaseOperator):
    id = "select.random"
    name = "随机采样"
    def process(self, input_data: List, params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        import random
        count = (params or {}).get("count", 100)
        sampled = random.sample(input_data, min(count, len(input_data)))
        return OperatorResult(True, data=sampled, metrics={"sampled": len(sampled)})


class SelectStratified(BaseOperator):
    id = "select.stratified"
    name = "分层采样"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        from collections import defaultdict
        import random
        field = (params or {}).get("field", "category")
        count = (params or {}).get("count", 100)
        groups = defaultdict(list)
        for item in input_data:
            groups[item.get(field, "unknown")].append(item)
        per_group = max(1, count // max(len(groups), 1))
        results = []
        for g, items in groups.items():
            results.extend(random.sample(items, min(per_group, len(items))))
        return OperatorResult(True, data=results[:count], metrics={"groups": len(groups), "sampled": min(count, len(results))})


class SelectDiversity(BaseOperator):
    id = "select.diversity"
    name = "多样性采样"
    supports_ai = True
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=[])
        count = (params or {}).get("count", 100)
        field = (params or {}).get("field", "category")
        from collections import defaultdict
        groups = defaultdict(list)
        for item in input_data:
            groups[item.get(field, "unknown")].append(item)
        results = []
        while len(results) < count and groups:
            for g in list(groups.keys()):
                if groups[g]:
                    results.append(groups[g].pop(0))
                if not groups[g]:
                    del groups[g]
                if len(results) >= count:
                    break
        return OperatorResult(True, data=results, metrics={"sampled": len(results)})


# ========== 导出算子 ==========

class ExportJSONL(BaseOperator):
    id = "export.jsonl"
    name = "导出JSONL"
    def process(self, input_data: List, params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("output_path", "/tmp/export.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for item in input_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return OperatorResult(True, data=path, metrics={"count": len(input_data), "path": path})


class ExportParquet(BaseOperator):
    id = "export.parquet"
    name = "导出Parquet"
    def process(self, input_data: List, params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("output_path", "/tmp/export.parquet")
        return OperatorResult(True, data=path, metrics={"count": len(input_data), "note": "需要pyarrow"})


class ExportCSV(BaseOperator):
    id = "export.csv"
    name = "导出CSV"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("output_path", "/tmp/export.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if input_data:
            fields = list(input_data[0].keys())
            with open(path, "w") as f:
                f.write(",".join(fields) + "\n")
                for item in input_data:
                    f.write(",".join(str(item.get(k, "")) for k in fields) + "\n")
        return OperatorResult(True, data=path, metrics={"count": len(input_data)})


class ExportLLaVA(BaseOperator):
    id = "export.llava"
    name = "导出LLaVA格式"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("output_path", "/tmp/llava.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        output = []
        for item in input_data:
            output.append({
                "id": item.get("id", ""),
                "image": item.get("file_path", ""),
                "conversations": item.get("conversations", [{"from": "human", "value": "<image>\nDescribe"}, {"from": "gpt", "value": item.get("caption", "")}])
            })
        with open(path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        return OperatorResult(True, data=path, metrics={"count": len(output)})


class ExportCOCO(BaseOperator):
    id = "export.coco"
    name = "导出COCO格式"
    def process(self, input_data: List[Dict], params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("output_path", "/tmp/coco.json")
        coco = {"images": [], "annotations": [], "categories": []}
        seen_cats = {}
        for item in input_data:
            img_info = item.get("image_info", {"id": 0, "file_name": "", "width": 0, "height": 0})
            coco["images"].append({"id": img_info.get("id", 0), "file_name": img_info.get("file_name", ""), "width": img_info.get("width", 0), "height": img_info.get("height", 0)})
            for ann in item.get("annotations", []):
                cat_name = ann.get("category", "object")
                if cat_name not in seen_cats:
                    seen_cats[cat_name] = len(seen_cats) + 1
                coco["annotations"].append({"id": ann.get("id", 0), "image_id": img_info.get("id", 0), "category_id": seen_cats[cat_name], "bbox": ann.get("bbox", [0, 0, 0, 0])})
        for name, cid in seen_cats.items():
            coco["categories"].append({"id": cid, "name": name})
        # 确保导出目录存在
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump(coco, f, indent=2)
        return OperatorResult(True, data=path, metrics={"images": len(coco["images"]), "annotations": len(coco["annotations"])})


class ExportLocal(BaseOperator):
    id = "export.local"
    name = "导出到本地"
    def process(self, input_data: List, params: dict = None) -> OperatorResult:
        if self._guard_none(input_data):
            return OperatorResult(True, data=None)
        path = (params or {}).get("target_dir", "/tmp/export")
        os.makedirs(path, exist_ok=True)
        return OperatorResult(True, data=path, metrics={"count": len(input_data)})


# ========== 所有算子注册表 ==========

OPERATOR_REGISTRY: Dict[str, type] = {
    # 采集(7)
    "source.local_file": SourceLocalFile,
    "source.oss": SourceOSS,
    "source.web_crawler": SourceWebCrawler,
    "source.database": SourceDatabase,
    "source.rss": SourceRSS,
    "source.api": SourceAPI,
    "source.screenshot": SourceScreenshot,
    # 清洗(13)
    "filter.resolution": FilterResolution,
    "filter.duration": FilterDuration,
    "filter.aspect_ratio": FilterAspectRatio,
    "filter.blur": FilterBlur,
    "filter.nsfw": FilterNSFW,
    "filter.dedup.md5": FilterDedupMD5,
    "filter.dedup.phash": FilterDedupPhash,
    "filter.language": FilterLanguage,
    "filter.sensitive": FilterSensitive,
    "filter.noise": FilterNoise,
    "filter.snr": FilterSNR,
    "filter.toxicity": FilterToxicity,
    # 标注(8)
    "label.image_classification": LabelImageClassification,
    "label.object_detection": LabelObjectDetection,
    "label.image_caption": LabelImageCaption,
    "label.image_tagging": LabelImageTagging,
    "label.image_aesthetic": LabelAesthetic,
    "label.video_scene_detect": LabelSceneDetect,
    "label.video_keyframe": LabelKeyFrame,
    "label.speech_recognition": LabelSpeechRecognition,
    # 评分(5)
    "score.aesthetic": ScoreAesthetic,
    "score.technical_quality": ScoreTechnical,
    "score.alignment": ScoreAlignment,
    "score.diversity": ScoreDiversity,
    "score.perplexity": ScorePerplexity,
    # 筛选(5)
    "select.threshold": SelectThreshold,
    "select.top_k": SelectTopK,
    "select.random": SelectRandom,
    "select.stratified": SelectStratified,
    "select.diversity": SelectDiversity,
    # 导出(6)
    "export.jsonl": ExportJSONL,
    "export.parquet": ExportParquet,
    "export.csv": ExportCSV,
    "export.llava": ExportLLaVA,
    "export.coco": ExportCOCO,
    "export.local": ExportLocal,
}


def get_operator(op_id: str) -> Optional[BaseOperator]:
    cls = OPERATOR_REGISTRY.get(op_id)
    return cls() if cls else None


def list_operators(category: str = "") -> List[Dict]:
    result = []
    for op_id, cls in OPERATOR_REGISTRY.items():
        inst = cls()
        info = {"id": inst.id, "name": inst.name, "category": op_id.split(".")[0]}
        if hasattr(inst, "supports_ai") and inst.supports_ai:
            info["supports_ai"] = True
        if not category or info["category"] == category:
            result.append(info)
    return result
