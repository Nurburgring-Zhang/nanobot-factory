"""
Eval Engine — 评测闭环引擎 (智影设计文档 §1.5 核心闭环架构 + §8 Agent实现)
======================================================================
核心闭环: 评测→BadCase分析→反馈闭环→迭代
"""
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json, os, logging, random, math
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


class EvalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EvalTask:
    """评测任务"""
    id: str = ""
    model_name: str = ""
    dataset_version: str = ""
    status: EvalStatus = EvalStatus.PENDING
    metrics: Dict[str, float] = field(default_factory=dict)
    created_at: str = ""
    completed_at: str = ""
    error: str = ""

    def to_dict(self) -> Dict:
        return {
            "id": self.id, "model_name": self.model_name,
            "dataset_version": self.dataset_version,
            "status": self.status.value,
            "metrics": self.metrics,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EvalTask":
        return cls(
            id=data.get("id", ""),
            model_name=data.get("model_name", ""),
            dataset_version=data.get("dataset_version", ""),
            status=EvalStatus(data.get("status", "pending")),
            metrics=data.get("metrics", {}),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
            error=data.get("error", ""),
        )


@dataclass
class EvalSample:
    """单个评测样本"""
    input_text: str = ""
    expected: str = ""
    predicted: str = ""
    score: float = 0.0
    error_type: str = ""  # classification/accuracy/coverage/relevance
    details: str = ""


class EvalRunner:
    """评测执行器 — 加载模型 → 运行推理 → 计算指标"""

    def __init__(self, registry: Optional[Dict[str, Any]] = None):
        self.registry = registry or {}

    def run_eval(self, task: EvalTask, test_samples: List[Dict]) -> Tuple[EvalTask, List[EvalSample]]:
        """
        执行完整评测闭环:
        1. 加载模型 (模拟)
        2. 运行推理
        3. 计算指标
        返回更新后的task (包含metrics)
        """
        logger.info(f"Starting eval: {task.id} on {task.model_name}")
        task.status = EvalStatus.RUNNING
        task.created_at = datetime.now().isoformat()

        # Step 1: 加载模型 (模拟注册表查找)
        model_fn = self._load_model(task.model_name)

        # Step 2: 运行推理
        results: List[EvalSample] = []
        for sample in test_samples:
            pred = model_fn(sample.get("input", ""))
            score = self._compute_sample_score(pred, sample.get("expected", ""))
            error_type = self._classify_error(pred, sample.get("expected", ""))
            results.append(EvalSample(
                input_text=sample.get("input", ""),
                expected=sample.get("expected", ""),
                predicted=pred,
                score=score,
                error_type=error_type,
            ))

        # Step 3: 计算聚合指标
        metrics = self._aggregate_metrics(results)
        task.metrics = metrics
        task.completed_at = datetime.now().isoformat()
        task.status = EvalStatus.SUCCESS

        logger.info(f"Eval {task.id} completed: {metrics}")
        return task, results

    def _load_model(self, model_name: str):
        """模拟模型加载 — 实际对接时替换为真实模型调用"""
        if model_name in self.registry:
            return self.registry[model_name]

        # 默认模拟行为: 返回输入
        def dummy_model(text: str) -> str:
            return f"{text} [模拟推理结果]"

        return dummy_model

    def _compute_sample_score(self, predicted: str, expected: str) -> float:
        """计算单样本得分 (0.0~1.0) — 模拟精确匹配/语义相似度"""
        if not expected:
            return 1.0
        # 简单词袋重叠率 — 实际场景可用BLEU/ROUGE/语义向量
        pred_tokens = set(predicted.lower().split())
        exp_tokens = set(expected.lower().split())
        if not exp_tokens:
            return 1.0
        intersection = pred_tokens & exp_tokens
        union = pred_tokens | exp_tokens
        return len(intersection) / max(len(union), 1)

    def _classify_error(self, predicted: str, expected: str) -> str:
        """分类错误类型"""
        if not expected:
            return ""
        pred_lower = predicted.lower().strip()
        exp_lower = expected.lower().strip()
        if not pred_lower or pred_lower == "":
            return "empty"
        if pred_lower == exp_lower:
            return ""
        # 检查是精度还是覆盖问题
        if len(pred_lower) < len(exp_lower) * 0.5:
            return "coverage"
        if not any(t in pred_lower for t in exp_lower.split()):
            return "relevance"
        return "accuracy"

    def _aggregate_metrics(self, results: List[EvalSample]) -> Dict[str, float]:
        """聚合整体评测指标"""
        n = len(results)
        if n == 0:
            return {"accuracy": 0.0, "avg_score": 0.0, "total": 0}
        scores = [r.score for r in results]
        errors = [r for r in results if r.error_type]
        accuracy = sum(1 for r in results if r.score >= 0.8) / n
        return {
            "accuracy": round(accuracy, 4),
            "avg_score": round(sum(scores) / n, 4),
            "min_score": round(min(scores), 4),
            "max_score": round(max(scores), 4),
            "total_error": len(errors),
            "total_samples": n,
        }


class BadCaseAnalyzer:
    """Bad Case分析器 — 聚类→根因分析→数据问题识别"""

    def __init__(self):
        self.error_clusters: Dict[str, List[EvalSample]] = {}

    def cluster_errors(self, results: List[EvalSample]) -> Dict[str, List[EvalSample]]:
        """
        对失败案例进行自动聚类
        按error_type聚类 → 再按pattern细分
        """
        by_type: Dict[str, List[EvalSample]] = defaultdict(list)
        for sample in results:
            if sample.error_type:
                by_type[sample.error_type].append(sample)

        # 按error_type聚类
        self.error_clusters = dict(by_type)

        # 在每个类型内按文本模式再分
        fine_clusters: Dict[str, List[EvalSample]] = {}
        for etype, samples in by_type.items():
            for i, s in enumerate(samples):
                cluster_key = f"{etype}_cluster_{i % 3}"  # 模拟子聚类
                fine_clusters.setdefault(cluster_key, []).append(s)

        return fine_clusters

    def root_cause_analysis(self, clusters: Dict[str, List[EvalSample]]) -> List[Dict]:
        """
        根因分析 — 对每个聚类分析根本原因
        返回: [{"cluster": str, "root_cause": str, "suggested_action": str, "affected_count": int}]
        """
        analyses = []
        for cluster_key, samples in clusters.items():
            if not samples:
                continue
            # 分析主导错误类型
            error_types = Counter(s.error_type for s in samples if s.error_type)
            dominant_error = error_types.most_common(1)[0][0] if error_types else "unknown"

            # 模式识别
            avg_score = sum(s.score for s in samples) / max(len(samples), 1)
            input_lengths = [len(s.input_text) for s in samples]
            avg_input_len = sum(input_lengths) / max(len(input_lengths), 1)

            # 根因推断
            if dominant_error == "accuracy":
                root_cause = "模型对精细指令对齐不足，输出细节与预期不匹配"
                action = "增加精确匹配的标注数据，强化监督微调"
            elif dominant_error == "coverage":
                root_cause = "模型输出过短，未覆盖完整信息"
                action = "补充完整输出的训练样本，增加输出长度约束"
            elif dominant_error == "relevance":
                root_cause = "模型输出偏离目标语义"
                action = "添加语义相似度负样本，增强相关度约束"
            elif dominant_error == "empty":
                root_cause = "模型拒绝回答或输出为空"
                action = "添加空输出检测机制，优化指令模板"
            else:
                root_cause = f"未分类错误模式 (dominant={dominant_error})"
                action = "人工审查样例，补充错误类型分类"

            analyses.append({
                "cluster": cluster_key,
                "root_cause": root_cause,
                "suggested_action": action,
                "affected_count": len(samples),
                "avg_score": round(avg_score, 4),
                "avg_input_length": round(avg_input_len, 1),
                "dominant_error_type": dominant_error,
            })

        return analyses

    def identify_data_issues(self, analyses: List[Dict]) -> List[Dict]:
        """
        从根因分析结果识别具体数据问题
        返回: [{"issue": str, "severity": str, "data_type": str, "recommendation": str}]
        """
        issues = []
        seen_causes = set()

        for a in analyses:
            cause = a.get("root_cause", "")
            if cause in seen_causes:
                continue
            seen_causes.add(cause)

            affected = a.get("affected_count", 0)
            severity = "high" if affected >= 10 else ("medium" if affected >= 3 else "low")

            if "对齐" in cause:
                issues.append({
                    "issue": "标注数据质量不足",
                    "severity": severity,
                    "data_type": "标注数据",
                    "recommendation": "采样复审low-quality标注，进行标注规范培训",
                    "affected_samples": affected,
                })
            elif "覆盖" in cause or "过短" in cause:
                issues.append({
                    "issue": "训练数据不足或覆盖不全",
                    "severity": severity,
                    "data_type": "训练样本",
                    "recommendation": "补充该方向的采集和标注任务",
                    "affected_samples": affected,
                })
            elif "偏离" in cause:
                issues.append({
                    "issue": "数据分布偏差",
                    "severity": severity,
                    "data_type": "数据分布",
                    "recommendation": "检查数据采集合规性，补充多样性样本",
                    "affected_samples": affected,
                })
            else:
                issues.append({
                    "issue": "未识别数据问题",
                    "severity": severity,
                    "data_type": "other",
                    "recommendation": "人工排查",
                    "affected_samples": affected,
                })

        return issues


class FeedbackLoop:
    """反馈闭环 — 评测结果→识别数据短板→生成补充采集/标注任务→触发迭代"""

    def __init__(self, task_queue: Optional[List[Dict]] = None):
        self.feedback_tasks: List[Dict] = []
        self.task_queue = task_queue or []
        self.iteration_count = 0

    def analyze_and_feedback(
        self,
        eval_results: Tuple[EvalTask, List[EvalSample]],
        analyses: List[Dict],
        data_issues: List[Dict],
    ) -> List[Dict]:
        """
        完整反馈闭环:
        1. 接收评测结果 + 根因分析 + 数据问题
        2. 识别数据短板
        3. 生成补充采集/标注任务
        4. 触发迭代
        返回生成的feedback tasks列表
        """
        task, samples = eval_results
        self.iteration_count += 1

        logger.info(f"FeedbackLoop iteration #{self.iteration_count} for eval {task.id}")

        # 识别数据短板: 综合metrics + 根因分析
        gaps = self._identify_data_gaps(task, analyses, data_issues)

        # 生成补充任务
        feedback_tasks = []
        for gap in gaps:
            ftask = self.generate_feedback_task(gap, task.id)
            feedback_tasks.append(ftask)
            self.feedback_tasks.append(ftask)
            if self.task_queue is not None:
                self.task_queue.append(ftask)

        logger.info(f"Generated {len(feedback_tasks)} feedback tasks")
        self._trigger_iteration(feedback_tasks)

        return feedback_tasks

    def _identify_data_gaps(
        self, task: EvalTask, analyses: List[Dict], data_issues: List[Dict]
    ) -> List[Dict]:
        """从评测结果识别数据短板"""
        gaps = []

        # 1. 基于整体的accuracy判断
        accuracy = task.metrics.get("accuracy", 1.0)
        if accuracy < 0.6:
            gaps.append({
                "type": "comprehensive",
                "reason": f"整体准确率过低 ({accuracy:.1%})，需要全面补充训练数据",
                "priority": "critical",
                "estimated_samples": 1000 * (1 - accuracy),
            })
        elif accuracy < 0.8:
            gaps.append({
                "type": "targeted",
                "reason": f"准确率 {accuracy:.1%} 需要定向提升",
                "priority": "high",
                "estimated_samples": 500,
            })

        # 2. 基于根因分析
        for a in analyses:
            affected = a.get("affected_count", 0)
            if affected >= 5:
                gaps.append({
                    "type": "root_cause",
                    "reason": a.get("root_cause", ""),
                    "priority": "medium" if affected < 10 else "high",
                    "estimated_samples": affected * 20,
                    "cluster": a.get("cluster", ""),
                })

        # 3. 基于数据问题
        for di in data_issues:
            if di.get("severity") in ("high", "medium"):
                gaps.append({
                    "type": "data_quality",
                    "reason": di.get("issue", ""),
                    "priority": di.get("severity", "medium"),
                    "recommendation": di.get("recommendation", ""),
                })

        return gaps

    def generate_feedback_task(self, gap: Dict, source_eval_id: str) -> Dict:
        """
        生成一个反馈任务 (补充采集/标注/数据清洗)
        返回任务字典
        """
        task_id = f"fb_{source_eval_id}_{len(self.feedback_tasks) + 1}_{int(datetime.now().timestamp())}"
        gap_type = gap.get("type", "unknown")

        # 根据gap类型决定任务类型
        if gap_type == "comprehensive":
            task_type = "data_collection"
            instruction = gap.get("reason", "全面数据补充")
            estimated_volume = gap.get("estimated_samples", 1000)
        elif gap_type == "targeted":
            task_type = "data_annotation"
            instruction = gap.get("reason", "定向标注补充")
            estimated_volume = gap.get("estimated_samples", 500)
        elif gap_type == "root_cause":
            task_type = "data_augmentation"
            instruction = gap.get("reason", "针对bad case的数据增强")
            estimated_volume = gap.get("estimated_samples", 200)
        elif gap_type == "data_quality":
            task_type = "data_cleaning"
            instruction = gap.get("recommendation", "数据质量清洗")
            estimated_volume = 100
        else:
            task_type = "review"
            instruction = "人工审查"
            estimated_volume = 50

        return {
            "id": task_id,
            "type": task_type,
            "source_eval_id": source_eval_id,
            "gap_type": gap_type,
            "instruction": instruction,
            "estimated_volume": int(estimated_volume),
            "priority": gap.get("priority", "medium"),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }

    def _trigger_iteration(self, tasks: List[Dict]) -> None:
        """触发新一轮迭代 — 实际对接时调用pipeline/scheduler"""
        logger.info(
            f"Iteration triggered: {len(tasks)} task(s) queued "
            f"(iteration #{self.iteration_count})"
        )
        # 模拟触发
        for t in tasks:
            logger.debug(f"  -> {t['type']}: {t['id']} [{t['instruction'][:40]}...]")

    def get_feedback_history(self) -> List[Dict]:
        """获取所有反馈历史"""
        return list(self.feedback_tasks)
