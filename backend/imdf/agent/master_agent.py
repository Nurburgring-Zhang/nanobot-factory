"""
IMDF Master Agent — Task Planning & Scheduling Core
======================================
Responsible for task understanding, decomposition, engine selection, Worker scheduling, and quality audit.

Architecture:
  Master Agent (Goal Hive style)
    ├── ContentAnalyzer: understand user intent → determine production type
    ├── EngineRouter: type → optimal engine combination
    ├── TaskDecomposer: decompose into executable Workers
    ├── WorkerScheduler: scheduling handler
    ├── QualityGate: stage acceptance + Reviewer
    └── ErrorRecovery: self-healing mechanism
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging
import traceback

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class WorkerTask:
    """子任务单元"""
    id: str
    name: str
    engine: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    output: str = ""
    error: str = ""
    duration: float = 0.0
    retry_count: int = 0
    max_retries: int = 2


@dataclass
class ProductionPlan:
    """完整生产计划"""
    id: str = ""
    user_intent: str = ""
    content_type: str = ""
    primary_engine: str = ""
    fallback_engine: str = ""
    workers: List[WorkerTask] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = ""
    completed_at: str = ""
    quality_score: float = 0.0
    errors: List[str] = field(default_factory=list)
    checkpoints: Dict[str, bool] = field(default_factory=dict)


class ContentAnalyzer:
    """内容分析器 — 理解用户意图"""

    PATTERNS = {
        "image": ["picture", "image", "海报", "poster", "封面", "图片", "照片", "插图", "商品图", "产品图"],
        "infographic": ["infographic", "信息图", "数据图", "图表", "统计图", "可视化"],
        "ppt": ["ppt", "slide", "汇报", "演示", "幻灯片", "项目总结", "报告"],
        "video": ["video", "视频", "短视频", "影片", "宣传片", "vlog"],
        "short_drama": ["drama", "短剧", "剧本", "故事", "叙事"],
        "web_page": ["web", "page", "网页", "网站", "落地页", "landing"],
        "train_data": ["训练", "数据", "dataset", "数据集", "标注", "训练数据"],
    }

    def analyze(self, user_input: str) -> Dict[str, Any]:
        """分析用户输入,返回意图和参数"""
        text = user_input.lower()
        
        # 识别生产类型
        content_type = "mixed"
        best_match = 0
        for ctype, keywords in self.PATTERNS.items():
            matches = sum(1 for k in keywords if k in text)
            if matches > best_match:
                best_match = matches
                content_type = ctype

        # 提取风格偏好
        style_prefs = {
            "warm": "暖色" in text or "温暖" in text,
            "dark": "深色" in text or "暗色" in text or "dark" in text,
            "minimal": "极简" in text or "minimal" in text,
            "tech": "科技" in text or "技术" in text or "tech" in text,
        }

        # 提取其他参数
        params = {}
        for word in ["时长", "duration"]:
            idx = text.find(word)
            if idx >= 0:
                import re
                nums = re.findall(r'\d+', text[idx:idx+10])
                if nums:
                    params["duration"] = int(nums[0])

        return {
            "content_type": content_type,
            "style": [k for k, v in style_prefs.items() if v],
            "params": params,
            "confidence": min(0.9, best_match * 0.2 + 0.3),
        }


class QualityGate:
    """Quality gate — stage acceptance + independent Reviewer"""

    def __init__(self):
        self.checklist: Dict[str, List[str]] = {}

    def define_checklist(self, content_type: str) -> List[str]:
        """根据内容Type definitions验收清单"""
        checklists = {
            "image": [
                "画面清晰度达标",
                "色彩正常不偏色",
                "文字渲染正确(如有)",
                "构图完整不截断",
            ],
            "infographic": [
                "文字信息准确可读",
                "数据可视化清晰",
                "布局整洁不杂乱",
                "配色符合设计系统",
            ],
            "ppt": [
                "封面标题正确",
                "内容页信息完整",
                "排版美观统一",
                "导航交互正常",
                "反AI味检查通过",
            ],
            "video": [
                "画面流畅不卡顿",
                "音画同步(如有音频)",
                "字幕准确(如有)",
                "时长符合预期",
            ],
            "short_drama": [
                "角色一致性(跨镜头脸不崩塌)",
                "镜头连贯性(转场自然)",
                "故事完整性(起承转合)",
                "音画同步",
                "反AI味检查",
            ],
        }
        return checklists.get(content_type, ["产出物存在", "格式正确"])

    def review_output(self, content_type: str, output_path: str,
                       plan: ProductionPlan) -> Dict[str, Any]:
        """独立Reviewer审核产出"""
        checklist = self.define_checklist(content_type)
        
        # 自动检查条目
        passed = []
        failed = []
        
        # 1. Check output file exists
        import os
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            passed.append(f"文件存在({file_size} bytes)")
        else:
            failed.append("输出文件不存在")
        
        # 2. Check for errors
        if plan.errors:
            failed.append(f"有{len(plan.errors)}个错误")
        else:
            passed.append("无执行错误")
        
        # 3. Worker completion rate
        completed = sum(1 for w in plan.workers if w.status == TaskStatus.COMPLETED)
        total = len(plan.workers)
        if total > 0:
            rate = completed / total
            if rate >= 0.8:
                passed.append(f"Worker completion rate{rate:.0%}")
            else:
                failed.append(f"Worker completion rate仅{rate:.0%}")
        
        # 计算通过率评分
        score = len(passed) / max(1, len(passed) + len(failed)) * 100
        
        return {
            "passed": passed,
            "failed": failed,
            "score": score,
            "checklist": checklist,
            "verdict": "passed" if score >= 60 else "needs_review",
        }


class ErrorRecovery:
    """错误恢复与自愈机制"""

    def __init__(self):
        self.failure_history: Dict[str, List[str]] = {}
        self.checklist: Dict[str, List[str]] = {}

    def record_failure(self, task_name: str, error: str):
        """记录失败日志"""
        if task_name not in self.failure_history:
            self.failure_history[task_name] = []
        self.failure_history[task_name].append(error)
        
        # Generate checklist to avoid repeats
        if task_name not in self.checklist:
            self.checklist[task_name] = []
        if error not in self.checklist[task_name]:
            self.checklist[task_name].append(error)
            logger.info(f"[ErrorRecovery] 为\"{task_name}\"添加防护: {error}")

    def should_retry(self, task_name: str, max_retries: int = 2) -> bool:
        """判断是否应该重试"""
        history = self.failure_history.get(task_name, [])
        return len(history) <= max_retries

    def get_fallback_strategy(self, task_name: str) -> str:
        """获取降级策略"""
        fallbacks = {
            "comfyui": "尝试HTML截图引擎",
            "gpt-image-2": "降级到NanoBot本地生成",
            "seedance": "降级到ComfyUI视频节点",
            "tts": "跳过语音,仅输出画面",
            "default": "报告失败,等待人工处理",
        }
        return fallbacks.get(task_name, fallbacks["default"])


class MasterAgent:
    """
    Master Agent — task planning + scheduling + quality audit + error recovery
    
    User input "turn this article into a video" → full production pipeline:
    分析→拆解→调度引擎→执行→审核→交付
    """

    def __init__(self):
        self.analyzer = ContentAnalyzer()
        self.quality_gate = QualityGate()
        self.error_recovery = ErrorRecovery()
        self._plans: Dict[str, ProductionPlan] = {}

    def plan(self, user_input: str) -> ProductionPlan:
        """接收用户输入,生成完整生产计划"""
        # 1. Analyze intent
        analysis = self.analyzer.analyze(user_input)
        
        # 2. Create plan
        plan = ProductionPlan(
            id=f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            user_intent=user_input,
            content_type=analysis["content_type"],
            status=TaskStatus.PLANNING,
            created_at=datetime.now().isoformat(),
        )

        # 3. Generate checkpoint checklist
        plan.checkpoints = {
            "content_analyzed": True,
            "engine_selected": False,
            "workers_created": False,
            "execution_started": False,
            "quality_reviewed": False,
        }

        # 4. Create Workers based on content type
        content_type = analysis["content_type"]
        
        if content_type == "ppt":
            plan.primary_engine = "frontend-slides"
            plan.fallback_engine = "html-screenshot"
            plan.workers = [
                WorkerTask(id="w1", name="内容提取与分析", engine="llm"),
                WorkerTask(id="w2", name="选择模板与设计系统", engine="frontend-slides"),
                WorkerTask(id="w3", name="填充内容到各slide", engine="frontend-slides"),
                WorkerTask(id="w4", name="评审与修改", engine="reviewer"),
            ]
        elif content_type in ("train_data", "video_data", "drama_data", "book_data"):
            plan.primary_engine = "data-engine"
            if content_type == "train_data":
                plan.workers = [
                    WorkerTask(id="w1", name="图片质量筛选", engine="data-quality"),
                    WorkerTask(id="w2", name="Caption生成", engine="data-caption"),
                    WorkerTask(id="w3", name="格式转换(WebDataset/COCO)", engine="data-format"),
                    WorkerTask(id="w4", name="去重+NSFW过滤", engine="data-quality"),
                ]
            elif content_type == "video_data":
                plan.workers = [
                    WorkerTask(id="w1", name="视频帧提取", engine="ffmpeg"),
                    WorkerTask(id="w2", name="视频Caption生成", engine="data-caption"),
                    WorkerTask(id="w3", name="视频编辑对生产", engine="data-edit"),
                ]
            elif content_type == "drama_data":
                plan.workers = [
                    WorkerTask(id="w1", name="多镜头对生成", engine="data-drama"),
                    WorkerTask(id="w2", name="角色一致性数据", engine="data-drama"),
                ]
            else:  # book_data
                plan.workers = [
                    WorkerTask(id="w1", name="绘本布局数据", engine="data-book"),
                    WorkerTask(id="w2", name="风格一致性数据", engine="data-book"),
                ]
        elif content_type in ("video", "short_drama"):
            plan.primary_engine = "html-video"
            plan.fallback_engine = "garden-video"
            plan.workers = [
                WorkerTask(id="w1", name="剧本/大纲生成", engine="llm"),
                WorkerTask(id="w2", name="口播稿+分镜", engine="llm"),
                WorkerTask(id="w3", name="画面生成", engine="html-video"),
                WorkerTask(id="w4", name="TTS配音+字幕", engine="tts"),
                WorkerTask(id="w5", name="合成导出", engine="ffmpeg"),
            ]
            if content_type == "short_drama":
                plan.workers.insert(1, WorkerTask(id="w1.5", name="角色视觉锁定", engine="gpt-image-2"))
                plan.workers.insert(3, WorkerTask(id="w2.5", name="逐镜头生成", engine="seedance"))
                plan.primary_engine = "story-arc"
        elif content_type in ("image", "infographic"):
            plan.primary_engine = "html-screenshot" if content_type == "infographic" else "gpt-image-2"
            plan.fallback_engine = "nanobot"
            plan.workers = [
                WorkerTask(id="w1", name="内容结构化", engine="llm"),
                WorkerTask(id="w2", name="模板选择", engine=plan.primary_engine),
                WorkerTask(id="w3", name="渲染输出", engine=plan.primary_engine),
            ]
        elif content_type == "web_page":
            plan.primary_engine = "frontend-slides"
            plan.workers = [
                WorkerTask(id="w1", name="设计系统宣告", engine="llm"),
                WorkerTask(id="w2", name="页面构建", engine="web-design"),
                WorkerTask(id="w3", name="评审优化", engine="reviewer"),
            ]
        else:
            plan.workers = [WorkerTask(id="w1", name="通用处理", engine="default")]

        plan.status = TaskStatus.PENDING
        plan.checkpoints["engine_selected"] = True
        plan.checkpoints["workers_created"] = True
        self._plans[plan.id] = plan
        
        return plan

    def get_plan(self, plan_id: str) -> Optional[ProductionPlan]:
        return self._plans.get(plan_id)

    def update_worker_status(self, plan_id: str, worker_id: str,
                              status: TaskStatus, output: str = "",
                              error: str = ""):
        """更新Worker状态"""
        plan = self._plans.get(plan_id)
        if not plan:
            return
        for w in plan.workers:
            if w.id == worker_id:
                w.status = status
                w.output = output
                w.error = error
                break
        
        # 检查是否所有Worker完成
        all_done = all(w.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                       for w in plan.workers)
        if all_done:
            plan.status = TaskStatus.AWAITING_REVIEW

    def execute_quality_gate(self, plan_id: str, output_path: str) -> Dict:
        """执行质量审计"""
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": "plan not found"}
        
        review = self.quality_gate.review_output(
            plan.content_type, output_path, plan
        )
        plan.quality_score = review["score"]
        plan.checkpoints["quality_reviewed"] = True
        
        if review["verdict"] == "passed":
            plan.status = TaskStatus.COMPLETED
            plan.completed_at = datetime.now().isoformat()
        else:
            plan.status = TaskStatus.PARTIAL
        
        return review

    def get_summary(self, plan_id: str) -> Dict[str, Any]:
        """获取生产摘要"""
        plan = self._plans.get(plan_id)
        if not plan:
            return {"error": "not found"}
        
        worker_status = {}
        for w in plan.workers:
            worker_status[w.id] = {
                "name": w.name,
                "status": w.status.value,
                "engine": w.engine,
                "error": w.error if w.error else None,
            }
        
        return {
            "plan_id": plan.id,
            "content_type": plan.content_type,
            "primary_engine": plan.primary_engine,
            "status": plan.status.value,
            "workers": worker_status,
            "quality_score": plan.quality_score,
            "checkpoints": plan.checkpoints,
            "created_at": plan.created_at,
            "completed_at": plan.completed_at,
        }
