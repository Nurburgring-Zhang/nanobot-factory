"""
Engine Router — 5引擎统一调度与智能选择
=======================================
根据内容类型、质量需求、成本约束自动选择最优引擎组合。

融合调研成果:
  - html-video (2.4K★) | HyperFrames (9.6K★) | garden-web-video | ComfyUI | Manim
  - Frontend Slides (20.5K★) | HTML截图 | GPT-Image2 | ConardLi 21/22套模板
  - Claude Design 设计理念 | 女娲认知蒸馏 | PPT Director
"""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field


class ContentType(str, Enum):
    IMAGE = "image"
    INFOGRAPHIC = "infographic"
    DATA_CARD = "data_card"
    POSTER = "poster"
    PPT = "ppt"
    VIDEO_INFO = "video_info"
    VIDEO_BRAND = "video_brand"
    VIDEO_CREATIVE = "video_creative"
    VIDEO_MATH = "video_math"
    SHORT_DRAMA = "short_drama"
    WEB_PAGE = "web_page"
    STORYBOARD = "storyboard"
    MIXED = "mixed"
    # 数据生产类
    TRAIN_DATA = "train_data"
    VIDEO_DATA = "video_data"
    DRAMA_DATA = "drama_data"
    BOOK_DATA = "book_data"


class EngineType(str, Enum):
    HTML_VIDEO = "html-video"          # nexu-io/html-video (2.4K★)
    HYPERFRAMES = "hyperframes"        # HeyGen (9.6K★)
    GARDEN_VIDEO = "garden-video"      # ConardLi (22套模板)
    COMFYUI = "comfyui"                # 本地ComfyUI
    MANIM = "manim"                    # 数学动画
    HTML_SCREENSHOT = "html-screenshot" # 浏览器截图(0成本)
    GPT_IMAGE2 = "gpt-image-2"         # OpenAI图像
    FRONTEND_SLIDES = "frontend-slides" # 20.5K★ 34模板
    CLIPDROP = "clipdrop"              # ClipDrop API
    NANOBOT = "nanobot"                # NanoBot Factory
    MANUAL = "manual"                  # 人工指定


@dataclass
class EngineDecision:
    engines: List[EngineType]
    reasoning: str = ""
    confidence: float = 0.0
    fallback: Optional[EngineType] = None
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engines": [e.value for e in self.engines],
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "fallback": self.fallback.value if self.fallback else None,
            "params": self.params,
        }


class EngineRouter:
    """
    引擎路由器 — 智能选择最优引擎组合
    
    规则:
      - 多引擎可组合(比如先html-video生成,再ComfyUI增强)
      - 有fallback链(主引擎失败自动降级)
      - 根据输入内容自动判断类型
    """

    # 引擎能力矩阵: 每个引擎适用的内容类型
    ENGINE_CAPABILITIES = {
        EngineType.HTML_VIDEO: {
            "types": [ContentType.VIDEO_INFO, ContentType.VIDEO_BRAND],
            "strength": "有文字/数据的内容最擅长, Content-Graph多场景",
            "cost": "free", "quality": "high", "speed": "fast",
            "url": "https://github.com/nexu-io/html-video",
            "stars": 2368,
        },
        EngineType.HYPERFRAMES: {
            "types": [ContentType.VIDEO_BRAND, ContentType.VIDEO_INFO],
            "strength": "确定性输出,像素级精确,GSAP动画",
            "cost": "free", "quality": "very_high", "speed": "medium",
            "url": "https://github.com/heygen-com/hyperframes",
            "stars": 9600,
        },
        EngineType.GARDEN_VIDEO: {
            "types": [ContentType.VIDEO_INFO],
            "strength": "22套主题,可插拔TTS,文章转视频最快路径",
            "cost": "free", "quality": "high", "speed": "fast",
            "url": "https://github.com/ConardLi/garden-skills",
            "stars": 7000,
        },
        EngineType.COMFYUI: {
            "types": [ContentType.VIDEO_CREATIVE, ContentType.IMAGE,
                       ContentType.VIDEO_BRAND],
            "strength": "最高质量,35个视频节点,Wan/AnimateDiff",
            "cost": "gpu", "quality": "highest", "speed": "slow",
        },
        EngineType.MANIM: {
            "types": [ContentType.VIDEO_MATH],
            "strength": "数学/算法可视化,3Blue1Brown级别",
            "cost": "free", "quality": "very_high", "speed": "medium",
        },
        EngineType.HTML_SCREENSHOT: {
            "types": [ContentType.INFOGRAPHIC, ContentType.DATA_CARD,
                       ContentType.IMAGE],
            "strength": "像素级精确,零成本,5秒出图,中文渲染完美",
            "cost": "free", "quality": "perfect_for_text", "speed": "instant",
        },
        EngineType.GPT_IMAGE2: {
            "types": [ContentType.IMAGE, ContentType.POSTER,
                       ContentType.STORYBOARD],
            "strength": "Arena第一,中文文字稳定,结构化79模板",
            "cost": "api", "quality": "highest", "speed": "fast",
        },
        EngineType.FRONTEND_SLIDES: {
            "types": [ContentType.PPT, ContentType.WEB_PAGE],
            "strength": "34套顶美模板,零依赖HTML,导出PDF",
            "cost": "free", "quality": "very_high", "speed": "fast",
            "url": "https://github.com/zarazhangrui/frontend-slides",
            "stars": 20500,
        },
        EngineType.NANOBOT: {
            "types": [ContentType.IMAGE, ContentType.VIDEO_CREATIVE],
            "strength": "NanoBot Factory推理能力",
            "cost": "api", "quality": "high", "speed": "medium",
        },
    }

    # 内容类型检测关键词
    CONTENT_PATTERNS = {
        ContentType.INFOGRAPHIC: ["信息图", "数据卡片", "infographic", "data card"],
        ContentType.DATA_CARD: ["数据", "卡片", "统计", "数字", "指标"],
        ContentType.POSTER: ["海报", "poster", "封面", "banner", "宣传"],
        ContentType.PPT: ["ppt", "幻灯片", "slide", "演示", "汇报", "deck"],
        ContentType.VIDEO_INFO: ["视频", "科普", "教学", "教程", "讲解", "文章转视频"],
        ContentType.VIDEO_BRAND: ["品牌", "产品", "宣传片", "广告", "promo"],
        ContentType.SHORT_DRAMA: ["短剧", "drama", "故事", "剧情", "分镜"],
        ContentType.WEB_PAGE: ["网页", "网站", "首页", "landing", "落地页"],
        ContentType.STORYBOARD: ["分镜", "故事板", "storyboard", "previs"],
        # 数据生产类
        ContentType.TRAIN_DATA: ["训练数据", "数据集", "训练集", "生成图片数据", "图片编辑数据",
                                  "训练图", "微调数据", "ControlNet", "数据对"],
        ContentType.VIDEO_DATA: ["视频数据", "视频训练", "视频编辑数据"],
        ContentType.DRAMA_DATA: ["影视数据", "短剧数据", "角色一致", "多镜头数据"],
        ContentType.BOOK_DATA: ["绘本数据", "绘本训练", "儿童绘本", "故事书数据"],
    }

    def classify_content(self, user_input: str) -> ContentType:
        """根据用户输入自动判断内容类型"""
        text = user_input.lower()
        for ctype, patterns in self.CONTENT_PATTERNS.items():
            if any(p in text for p in patterns):
                return ctype
        return ContentType.MIXED

    def decide(self, user_input: str, prefer_quality: bool = True,
               prefer_cost: str = "free") -> EngineDecision:
        """
        自动选择最优引擎

        Args:
            user_input: 用户输入(要做什么)
            prefer_quality: True=质量优先, False=速度优先
            prefer_cost: "free" / "api" / "gpu"
        """
        content_type = self.classify_content(user_input)

        # 找到所有能处理该类型的引擎
        candidates = []
        for engine, cap in self.ENGINE_CAPABILITIES.items():
            if content_type in cap["types"]:
                score = 0
                # 质量评分
                quality_map = {"lowest": 1, "low": 2, "high": 4,
                               "very_high": 5, "highest": 6,
                               "perfect_for_text": 5}
                score += quality_map.get(cap.get("quality", "high"), 3)

                # 成本评分(免费优先)
                cost_map = {"free": 5, "api": 3, "gpu": 1}
                score += cost_map.get(cap.get("cost", "free"), 3)

                # 速度评分
                speed_map = {"instant": 5, "fast": 4, "medium": 3, "slow": 1}
                score += speed_map.get(cap.get("speed", "medium"), 3)

                # 星标加成
                stars = cap.get("stars", 0)
                if stars > 10000:
                    score += 2
                elif stars > 1000:
                    score += 1

                candidates.append((score, engine, cap))

        # 按分数排序
        candidates.sort(key=lambda x: -x[0])

        if not candidates:
            return EngineDecision(
                engines=[EngineType.HTML_SCREENSHOT],
                reasoning="未识别内容类型,使用通用HTML截图引擎",
                confidence=0.3,
            )

        primary = candidates[0]
        reasoning_parts = [
            f"内容类型:{content_type.value}",
            f"首选:{primary[1].value}({primary[2].get('strength','')})",
        ]

        # fallback: 如果有第二个候选引擎
        fallback = candidates[1][1] if len(candidates) > 1 else None
        if fallback:
            reasoning_parts.append(f"fallback:{fallback.value}")

        return EngineDecision(
            engines=[c[1] for c in candidates[:2]],
            reasoning=" | ".join(reasoning_parts),
            confidence=min(0.95, primary[0] / 15.0),
            fallback=fallback,
            params={
                "content_type": content_type.value,
                "prefer_quality": prefer_quality,
                "prefer_cost": prefer_cost,
                "scores": {c[1].value: c[0] for c in candidates[:5]},
            },
        )

    def get_template_list(self, engine: EngineType) -> List[Dict[str, str]]:
        """获取指定引擎的可用模板列表"""
        templates = {
            EngineType.FRONTEND_SLIDES: [
                {"name": "现代商务", "desc": "干净留白,大字标题,适合汇报"},
                {"name": "深色科技", "desc": "暗色背景,霓虹强调,适合技术分享"},
                {"name": "数据叙事", "desc": "NYT风格数据图表,适合分析报告"},
                {"name": "杂志编辑", "desc": "高端杂志排版,适合品牌故事"},
                {"name": "极简白", "desc": "纯白底,极细字体,无装饰"},
                {"name": "终端风", "desc": "CLI风格,代码块突出"},
                {"name": "布鲁塔利", "desc": "粗犷字体+色块,态度鲜明"},
                {"name": "温感自然", "desc": "暖色调+自然纹理,柔和"},
                {"name": "霓虹夜", "desc": "暗色+霓虹光,科技感"},
                {"name": "双色对比", "desc": "左右双色画布,对比展示"},
                {"name": "国家地理", "desc": "沉稳文献感,适合纪录片"},
                {"name": "创意工作室", "desc": "实验性设计,适合创意展示"},
            ],
            EngineType.GARDEN_VIDEO: [
                {"name": "演讲风", "desc": "左文右图,适合演讲录制"},
                {"name": "科技架构", "desc": "技术架构图+代码展示"},
                {"name": "数据报告", "desc": "动态数据图表视频"},
                {"name": "科普讲解", "desc": "关联卡片+文字标注"},
                {"name": "终端CLI", "desc": "CLI工具教程风格"},
                {"name": "杂志特稿", "desc": "热点解读和深度报道"},
                {"name": "B2B路演", "desc": "白底商务风格"},
                {"name": "包豪斯", "desc": "现代主义鲜明风格"},
                {"name": "赛博朋克", "desc": "霓虹科技未来感"},
                {"name": "双色对比", "desc": "左右分屏对比"},
                {"name": "时尚杂志", "desc": "品牌故事和高端产品"},
                {"name": "自然人文", "desc": "沉稳文献气质"},
            ],
        }
        return templates.get(engine, [])
