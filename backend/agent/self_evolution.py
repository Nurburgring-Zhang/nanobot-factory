"""
NanoBot Factory - Self-Evolution System (自我进化优化系统)
基于Feedback-Loop的Agent自我改进机制

核心机制:
1. 性能追踪 - 记录每次任务执行的指标
2. 失败分析 - 识别错误模式和根本原因
3. 工具使用优化 - 学习最有效的工具调用策略
4. 提示词进化 - 根据成功/失败案例优化提示
5. 知识积累 - 将成功经验存入长期记忆
6. 自我诊断 - 定期评估并生成改进建议

参考: Self-Improving LLM Agents at Test-Time (arXiv:2510.07841)
      Feedback-Loop Pattern for Agent Self-Optimization

@author MiniMax Agent
@date 2026-04-13
"""
import logging, time, json, statistics
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class EvolutionEvent(Enum):
    TASK_SUCCESS = "task_success"
    TASK_FAILURE = "task_failure"
    TOOL_SUCCESS = "tool_success"
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    CONTEXT_COMPRESSED = "context_compressed"
    AGENT_DISPATCHED = "agent_dispatched"


class FailureCategory(Enum):
    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_ERROR = "tool_error"
    LLM_ERROR = "llm_error"
    CONTEXT_OVERFLOW = "context_overflow"
    TASK_UNCLEAR = "task_unclear"
    RESOURCE_UNAVAILABLE = "resource_unavailable"
    UNKNOWN = "unknown"


class ImprovementType(Enum):
    TOOL_SELECTION = "tool_selection"
    PROMPT_OPTIMIZATION = "prompt_optimization"
    RETRY_STRATEGY = "retry_strategy"
    CONTEXT_MANAGEMENT = "context_management"
    AGENT_ROUTING = "agent_routing"
    TIMEOUT_TUNING = "timeout_tuning"


@dataclass
class ExecutionRecord:
    """单次执行记录"""
    record_id: str
    task_description: str
    success: bool
    duration_ms: float
    tool_calls: List[str] = field(default_factory=list)
    tool_failures: List[str] = field(default_factory=list)
    iterations: int = 0
    token_count: int = 0
    error: Optional[str] = None
    failure_category: Optional[FailureCategory] = None
    agent_id: str = ""
    domain: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task": self.task_description[:100],
            "success": self.success,
            "duration_ms": round(self.duration_ms, 2),
            "tool_calls": self.tool_calls,
            "iterations": self.iterations,
            "error": self.error,
            "failure_category": self.failure_category.value if self.failure_category else None,
            "domain": self.domain,
            "timestamp": self.timestamp,
        }


@dataclass
class PerformanceMetrics:
    """性能指标快照"""
    window_size: int           # 统计窗口(最近N次)
    success_rate: float        # 成功率
    avg_duration_ms: float     # 平均执行时间
    avg_iterations: float      # 平均迭代次数
    avg_token_count: float     # 平均token消耗
    tool_success_rates: Dict[str, float]   # 各工具成功率
    domain_success_rates: Dict[str, float] # 各领域成功率
    failure_distribution: Dict[str, int]   # 失败类型分布
    trend: str                 # 趋势: improving/stable/degrading
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_size": self.window_size,
            "success_rate": round(self.success_rate, 4),
            "avg_duration_ms": round(self.avg_duration_ms, 2),
            "avg_iterations": round(self.avg_iterations, 2),
            "avg_token_count": round(self.avg_token_count, 2),
            "tool_success_rates": {k: round(v, 4) for k, v in self.tool_success_rates.items()},
            "domain_success_rates": {k: round(v, 4) for k, v in self.domain_success_rates.items()},
            "failure_distribution": self.failure_distribution,
            "trend": self.trend,
        }


@dataclass
class ImprovementSuggestion:
    """改进建议"""
    suggestion_id: str
    type: ImprovementType
    priority: int              # 1-10
    description: str
    action: str                # 具体行动建议
    evidence: List[str]        # 支持证据
    estimated_impact: float    # 预期改善比例 0-1
    implemented: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.suggestion_id,
            "type": self.type.value,
            "priority": self.priority,
            "description": self.description,
            "action": self.action,
            "evidence": self.evidence[:3],
            "estimated_impact": round(self.estimated_impact, 3),
            "implemented": self.implemented,
        }


class FailureAnalyzer:
    """失败模式分析器"""

    # 错误关键词到失败类型的映射
    ERROR_PATTERNS = {
        FailureCategory.TOOL_NOT_FOUND: ["tool.*not found", "no such tool", "unknown tool", "不存在.*工具"],
        FailureCategory.TOOL_TIMEOUT: ["timeout", "timed out", "超时"],
        FailureCategory.TOOL_ERROR: ["tool.*error", "tool.*failed", "工具.*失败", "工具.*错误"],
        FailureCategory.LLM_ERROR: ["llm.*error", "api.*error", "rate limit", "openai", "anthropic"],
        FailureCategory.CONTEXT_OVERFLOW: ["context.*length", "token.*limit", "too long", "超出.*长度"],
        FailureCategory.TASK_UNCLEAR: ["unclear", "ambiguous", "不明确", "无法理解"],
        FailureCategory.RESOURCE_UNAVAILABLE: ["connection.*refused", "service.*unavailable", "服务.*不可用"],
    }

    @classmethod
    def categorize(cls, error: Optional[str], tool_failures: List[str]) -> FailureCategory:
        if not error and not tool_failures:
            return FailureCategory.UNKNOWN

        text = (error or "").lower()

        for category, patterns in cls.ERROR_PATTERNS.items():
            import re
            for pattern in patterns:
                if re.search(pattern, text):
                    return category

        if tool_failures:
            return FailureCategory.TOOL_ERROR

        return FailureCategory.UNKNOWN


class PerformanceTracker:
    """性能指标追踪器"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._records: deque = deque(maxlen=window_size)
        self._tool_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})
        self._domain_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"success": 0, "failure": 0})
        self._baseline_success_rate: Optional[float] = None

    def record(self, record: ExecutionRecord):
        """记录执行结果"""
        self._records.append(record)

        # 更新工具统计
        for tool in record.tool_calls:
            if tool not in record.tool_failures:
                self._tool_stats[tool]["success"] += 1
            else:
                self._tool_stats[tool]["failure"] += 1

        for tool in record.tool_failures:
            if tool not in record.tool_calls:
                self._tool_stats[tool]["failure"] += 1

        # 更新领域统计
        if record.domain:
            if record.success:
                self._domain_stats[record.domain]["success"] += 1
            else:
                self._domain_stats[record.domain]["failure"] += 1

    def get_metrics(self) -> PerformanceMetrics:
        """计算当前性能指标"""
        records = list(self._records)
        if not records:
            return PerformanceMetrics(0, 0.0, 0.0, 0.0, 0.0, {}, {}, {}, "stable")

        # 基础指标
        success_count = sum(1 for r in records if r.success)
        success_rate = success_count / len(records)
        avg_duration = statistics.mean(r.duration_ms for r in records) if records else 0
        avg_iterations = statistics.mean(r.iterations for r in records) if records else 0
        avg_tokens = statistics.mean(r.token_count for r in records) if records else 0

        # 工具成功率
        tool_rates = {}
        for tool, stats in self._tool_stats.items():
            total = stats["success"] + stats["failure"]
            if total > 0:
                tool_rates[tool] = stats["success"] / total

        # 领域成功率
        domain_rates = {}
        for domain, stats in self._domain_stats.items():
            total = stats["success"] + stats["failure"]
            if total > 0:
                domain_rates[domain] = stats["success"] / total

        # 失败类型分布
        failure_dist = defaultdict(int)
        for r in records:
            if not r.success and r.failure_category:
                failure_dist[r.failure_category.value] += 1

        # 计算趋势 (对比前半段和后半段)
        trend = "stable"
        if len(records) >= 20:
            mid = len(records) // 2
            first_half_rate = sum(1 for r in records[:mid] if r.success) / mid
            second_half_rate = sum(1 for r in records[mid:] if r.success) / (len(records) - mid)
            diff = second_half_rate - first_half_rate
            if diff > 0.05:
                trend = "improving"
            elif diff < -0.05:
                trend = "degrading"

        return PerformanceMetrics(
            window_size=len(records),
            success_rate=success_rate,
            avg_duration_ms=avg_duration,
            avg_iterations=avg_iterations,
            avg_token_count=avg_tokens,
            tool_success_rates=tool_rates,
            domain_success_rates=domain_rates,
            failure_distribution=dict(failure_dist),
            trend=trend
        )


class SuggestionEngine:
    """改进建议生成引擎"""

    def generate(self, metrics: PerformanceMetrics, records: List[ExecutionRecord]) -> List[ImprovementSuggestion]:
        """基于性能指标生成改进建议"""
        suggestions = []

        # 1. 低成功率 → 提示词优化
        if metrics.success_rate < 0.7:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"prompt_opt_{int(time.time())}",
                type=ImprovementType.PROMPT_OPTIMIZATION,
                priority=9,
                description=f"整体成功率偏低 ({metrics.success_rate:.1%})，需要优化提示词策略",
                action="分析失败案例，提取失败模式，在系统提示词中添加更清晰的指令和示例",
                evidence=[f"最近{metrics.window_size}次任务成功率仅{metrics.success_rate:.1%}",
                          f"失败分布: {metrics.failure_distribution}"],
                estimated_impact=0.15
            ))

        # 2. 工具失败率高 → 工具选择优化
        bad_tools = [(t, r) for t, r in metrics.tool_success_rates.items() if r < 0.6]
        if bad_tools:
            tools_str = ", ".join(f"{t}({r:.0%})" for t, r in bad_tools[:3])
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"tool_sel_{int(time.time())}",
                type=ImprovementType.TOOL_SELECTION,
                priority=8,
                description=f"以下工具成功率过低: {tools_str}",
                action="考虑为这些工具添加重试逻辑，或替换为更可靠的备选工具",
                evidence=[f"{t}: {r:.1%}成功率" for t, r in bad_tools[:3]],
                estimated_impact=0.1
            ))

        # 3. 超时问题 → 超时参数调整
        timeout_count = metrics.failure_distribution.get(FailureCategory.TOOL_TIMEOUT.value, 0)
        if timeout_count > metrics.window_size * 0.1:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"timeout_{int(time.time())}",
                type=ImprovementType.TIMEOUT_TUNING,
                priority=7,
                description=f"超时失败占比 {timeout_count/max(metrics.window_size,1):.1%}，超时设置过严",
                action=f"将工具调用超时从当前值增加50%，或对复杂任务使用自适应超时",
                evidence=[f"超时失败 {timeout_count} 次 / 总 {metrics.window_size} 次",
                          f"平均执行时间: {metrics.avg_duration_ms:.0f}ms"],
                estimated_impact=0.08
            ))

        # 4. 上下文溢出 → 上下文管理
        ctx_overflow = metrics.failure_distribution.get(FailureCategory.CONTEXT_OVERFLOW.value, 0)
        if ctx_overflow > 0:
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"ctx_mgmt_{int(time.time())}",
                type=ImprovementType.CONTEXT_MANAGEMENT,
                priority=7,
                description=f"上下文溢出 {ctx_overflow} 次，需要更激进的压缩策略",
                action="降低压缩触发阈值至70%，增加最小保留消息数到8条",
                evidence=[f"上下文溢出 {ctx_overflow} 次",
                          f"平均token: {metrics.avg_token_count:.0f}"],
                estimated_impact=0.12
            ))

        # 5. 执行时间过长 → 迭代优化
        if metrics.avg_duration_ms > 30000:  # 30秒
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"perf_{int(time.time())}",
                type=ImprovementType.RETRY_STRATEGY,
                priority=6,
                description=f"平均执行时间 {metrics.avg_duration_ms/1000:.1f}s 过长",
                action="限制最大迭代次数，添加早停条件，对简单任务减少推理步骤",
                evidence=[f"平均执行: {metrics.avg_duration_ms/1000:.1f}s",
                          f"平均迭代: {metrics.avg_iterations:.1f}次"],
                estimated_impact=0.2
            ))

        # 6. 领域成功率不均衡 → Agent路由优化
        poor_domains = [(d, r) for d, r in metrics.domain_success_rates.items() if r < 0.6]
        if poor_domains:
            domains_str = ", ".join(f"{d}({r:.0%})" for d, r in poor_domains[:3])
            suggestions.append(ImprovementSuggestion(
                suggestion_id=f"routing_{int(time.time())}",
                type=ImprovementType.AGENT_ROUTING,
                priority=7,
                description=f"以下领域成功率低: {domains_str}",
                action="为这些领域配置更专业的专家Agent，或降低任务复杂度要求",
                evidence=[f"{d}: {r:.1%}" for d, r in poor_domains[:3]],
                estimated_impact=0.12
            ))

        # 按优先级排序
        suggestions.sort(key=lambda s: s.priority, reverse=True)
        return suggestions


class KnowledgeBase:
    """成功经验知识库"""

    def __init__(self, max_entries: int = 500):
        self.max_entries = max_entries
        self._success_patterns: deque = deque(maxlen=max_entries)
        self._tool_sequences: Dict[str, List[List[str]]] = defaultdict(list)  # domain → [[tools], ...]
        self._prompt_templates: Dict[str, List[str]] = defaultdict(list)      # domain → [prompt_hints]

    def learn_from_success(self, record: ExecutionRecord):
        """从成功案例学习"""
        if not record.success:
            return

        # 记录成功工具序列
        if record.tool_calls and record.domain:
            self._tool_sequences[record.domain].append(record.tool_calls[:])
            if len(self._tool_sequences[record.domain]) > 20:
                self._tool_sequences[record.domain].pop(0)

        # 记录成功模式
        pattern = {
            "domain": record.domain,
            "task_keywords": record.task_description.split()[:5],
            "tools_used": record.tool_calls,
            "iterations": record.iterations,
            "duration_ms": record.duration_ms,
        }
        self._success_patterns.append(pattern)

    def get_recommended_tools(self, domain: str) -> List[str]:
        """获取领域推荐工具"""
        sequences = self._tool_sequences.get(domain, [])
        if not sequences:
            return []

        # 统计工具出现频率
        tool_freq = defaultdict(int)
        for seq in sequences:
            for tool in seq:
                tool_freq[tool] += 1

        # 返回最高频的前5个工具
        sorted_tools = sorted(tool_freq.items(), key=lambda x: x[1], reverse=True)
        return [t for t, _ in sorted_tools[:5]]

    def get_avg_iterations(self, domain: str) -> Optional[float]:
        """获取领域平均迭代次数"""
        domain_patterns = [p for p in self._success_patterns if p.get("domain") == domain]
        if not domain_patterns:
            return None
        return statistics.mean(p["iterations"] for p in domain_patterns)

    def get_knowledge_summary(self) -> Dict[str, Any]:
        return {
            "total_success_patterns": len(self._success_patterns),
            "domains_with_knowledge": list(self._tool_sequences.keys()),
            "top_domain_tools": {
                domain: self.get_recommended_tools(domain)
                for domain in list(self._tool_sequences.keys())[:5]
            }
        }


class SelfEvolutionSystem:
    """
    自我进化优化系统主类

    生命周期:
    1. 记录 → record_execution()
    2. 分析 → analyze()
    3. 建议 → get_suggestions()
    4. 进化 → apply_improvements()
    5. 监控 → get_evolution_report()
    """

    def __init__(self, window_size: int = 100, auto_analyze_interval: int = 20):
        self.tracker = PerformanceTracker(window_size)
        self.failure_analyzer = FailureAnalyzer()
        self.suggestion_engine = SuggestionEngine()
        self.knowledge_base = KnowledgeBase()

        self._suggestions: List[ImprovementSuggestion] = []
        self._evolution_history: List[Dict[str, Any]] = []
        self._record_count = 0
        self._auto_analyze_interval = auto_analyze_interval  # 每N次记录自动分析
        self._applied_improvements: Dict[str, Any] = {}  # 已应用的改进

        # 自适应参数 (这些参数会被自动调整)
        self.adaptive_params = {
            "tool_timeout_seconds": 30.0,
            "max_iterations": 20,
            "context_compression_threshold": 0.85,
            "retry_count": 2,
            "min_confidence_threshold": 0.6,
        }

        logger.info("SelfEvolutionSystem initialized")

    def record_execution(
        self,
        task_description: str,
        success: bool,
        duration_ms: float,
        tool_calls: List[str] = None,
        tool_failures: List[str] = None,
        iterations: int = 0,
        token_count: int = 0,
        error: Optional[str] = None,
        agent_id: str = "",
        domain: str = "",
        metadata: Dict[str, Any] = None
    ) -> ExecutionRecord:
        """记录一次任务执行"""
        import uuid
        tool_calls = tool_calls or []
        tool_failures = tool_failures or []

        failure_category = None
        if not success:
            failure_category = self.failure_analyzer.categorize(error, tool_failures)

        record = ExecutionRecord(
            record_id=str(uuid.uuid4())[:8],
            task_description=task_description,
            success=success,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
            tool_failures=tool_failures,
            iterations=iterations,
            token_count=token_count,
            error=error,
            failure_category=failure_category,
            agent_id=agent_id,
            domain=domain,
            metadata=metadata or {}
        )

        self.tracker.record(record)
        self.knowledge_base.learn_from_success(record)

        self._record_count += 1

        # 自动分析
        if self._record_count % self._auto_analyze_interval == 0:
            self._auto_analyze()

        return record

    def _auto_analyze(self):
        """自动分析并生成改进建议"""
        metrics = self.tracker.get_metrics()
        records = list(self.tracker._records)
        new_suggestions = self.suggestion_engine.generate(metrics, records)

        # 去重并添加新建议
        existing_types = {s.type for s in self._suggestions if not s.implemented}
        for s in new_suggestions:
            if s.type not in existing_types:
                self._suggestions.append(s)
                logger.info(f"New improvement suggestion: [{s.type.value}] {s.description}")

        # 自动应用部分改进
        self._auto_apply_improvements()

    def _auto_apply_improvements(self):
        """自动应用可安全应用的改进"""
        for suggestion in self._suggestions:
            if suggestion.implemented:
                continue

            # 超时调整: 自动应用
            if suggestion.type == ImprovementType.TIMEOUT_TUNING:
                old_timeout = self.adaptive_params["tool_timeout_seconds"]
                new_timeout = min(old_timeout * 1.5, 120.0)
                self.adaptive_params["tool_timeout_seconds"] = new_timeout
                suggestion.implemented = True
                self._applied_improvements["timeout"] = {
                    "old": old_timeout, "new": new_timeout,
                    "applied_at": time.time()
                }
                logger.info(f"Auto-applied: tool timeout {old_timeout:.0f}s → {new_timeout:.0f}s")

            # 上下文管理: 自动应用
            elif suggestion.type == ImprovementType.CONTEXT_MANAGEMENT:
                old_threshold = self.adaptive_params["context_compression_threshold"]
                new_threshold = max(old_threshold - 0.1, 0.6)
                self.adaptive_params["context_compression_threshold"] = new_threshold
                suggestion.implemented = True
                self._applied_improvements["context"] = {
                    "old": old_threshold, "new": new_threshold,
                    "applied_at": time.time()
                }
                logger.info(f"Auto-applied: compression threshold {old_threshold:.0%} → {new_threshold:.0%}")

    def analyze(self) -> PerformanceMetrics:
        """手动触发分析"""
        metrics = self.tracker.get_metrics()
        records = list(self.tracker._records)
        self._suggestions = self.suggestion_engine.generate(metrics, records)

        snapshot = {
            "timestamp": time.time(),
            "metrics": metrics.to_dict(),
            "suggestion_count": len(self._suggestions),
        }
        self._evolution_history.append(snapshot)
        if len(self._evolution_history) > 50:
            self._evolution_history.pop(0)

        return metrics

    def get_suggestions(self, pending_only: bool = True) -> List[ImprovementSuggestion]:
        """获取改进建议"""
        if pending_only:
            return [s for s in self._suggestions if not s.implemented]
        return self._suggestions

    def mark_suggestion_implemented(self, suggestion_id: str) -> bool:
        """标记建议已实施"""
        for s in self._suggestions:
            if s.suggestion_id == suggestion_id:
                s.implemented = True
                return True
        return False

    def get_adaptive_params(self) -> Dict[str, Any]:
        """获取当前自适应参数"""
        return self.adaptive_params.copy()

    def get_evolution_report(self) -> Dict[str, Any]:
        """获取完整进化报告"""
        metrics = self.tracker.get_metrics()
        pending_suggestions = self.get_suggestions(pending_only=True)
        knowledge = self.knowledge_base.get_knowledge_summary()

        return {
            "report_time": datetime.now().isoformat(),
            "total_records": self._record_count,
            "performance_metrics": metrics.to_dict(),
            "adaptive_params": self.adaptive_params,
            "pending_suggestions": [s.to_dict() for s in pending_suggestions[:5]],
            "applied_improvements": self._applied_improvements,
            "knowledge_base": knowledge,
            "evolution_trend": metrics.trend,
            "health_score": self._calculate_health_score(metrics),
        }

    def _calculate_health_score(self, metrics: PerformanceMetrics) -> float:
        """计算系统健康评分 0-100"""
        if metrics.window_size == 0:
            return 100.0

        score = 0.0
        # 成功率 (40分)
        score += metrics.success_rate * 40

        # 执行速度 (20分): <5s满分
        speed_score = max(0, 1 - (metrics.avg_duration_ms - 1000) / 29000)
        score += speed_score * 20

        # 趋势 (20分)
        trend_scores = {"improving": 20, "stable": 15, "degrading": 5}
        score += trend_scores.get(metrics.trend, 15)

        # 工具稳定性 (20分)
        if metrics.tool_success_rates:
            avg_tool_rate = statistics.mean(metrics.tool_success_rates.values())
            score += avg_tool_rate * 20
        else:
            score += 20

        return round(min(score, 100), 1)

    def reset(self):
        """重置进化系统"""
        self.tracker = PerformanceTracker()
        self._suggestions.clear()
        self._record_count = 0
        logger.info("SelfEvolutionSystem reset")


def create_evolution_system(
    window_size: int = 100,
    auto_analyze_interval: int = 20
) -> SelfEvolutionSystem:
    """创建自我进化系统"""
    return SelfEvolutionSystem(window_size, auto_analyze_interval)


__all__ = [
    "SelfEvolutionSystem", "ExecutionRecord", "PerformanceMetrics",
    "ImprovementSuggestion", "FailureAnalyzer", "PerformanceTracker",
    "SuggestionEngine", "KnowledgeBase", "EvolutionEvent",
    "FailureCategory", "ImprovementType", "create_evolution_system"
]
