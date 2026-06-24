#!/usr/bin/env python3
"""
NanoBot Factory - Slacking Behavior Detection System
偷懒行为检测系统 - 监控Agent行为，检测偷懒/敷衍行为
@author MiniMax Agent
@date 2026-04-15
"""
import asyncio
import logging
import json
import time
import hashlib
import re
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading
import statistics

logger = logging.getLogger(__name__)


class BehaviorType(Enum):
    """行为类型"""
    HARD_WORK = "hard_work"           # 勤奋
    NORMAL = "normal"                 # 正常
    SUSPICIOUS = "suspicious"         # 可疑
    SLAKING = "slacking"             # 偷懒
    MALICIOUS = "malicious"          # 恶意


class SlackingIndicator(Enum):
    """偷懒指标"""
    LOW_OUTPUT_LENGTH = "low_output_length"
    LOW_CODE_COMPLEXITY = "low_code_complexity"
    HIGH_SKIP_RATE = "high_skip_rate"
    QUICK_COMPLETION = "quick_completion"
    REPETITIVE_OUTPUT = "repetitive_output"
    GENERIC_RESPONSE = "generic_response"
    NO_TOOL_USAGE = "no_tool_usage"
    LOW_QUALITY_SCORE = "low_quality_score"
    TASK_INCOMPLETION = "task_incompletion"


@dataclass
class BehaviorMetrics:
    """行为指标"""
    agent_id: str
    task_id: str
    timestamp: datetime = field(default_factory=datetime.now)

    # 产出指标
    output_length: int = 0
    output_words: int = 0
    code_lines: int = 0
    tool_calls: int = 0

    # 时间指标
    expected_duration_ms: float = 0
    actual_duration_ms: float = 0
    think_time_ms: float = 0

    # 质量指标
    quality_score: float = 0.0
    completeness_score: float = 0.0
    novelty_score: float = 0.0

    # 行为标记
    has_error: bool = False
    is_retry: bool = False
    skipped_steps: int = 0
    repeated_patterns: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat(),
            "output_length": self.output_length,
            "tool_calls": self.tool_calls,
            "actual_duration_ms": self.actual_duration_ms,
            "quality_score": self.quality_score,
        }


@dataclass
class AgentBehaviorProfile:
    """Agent行为画像"""
    agent_id: str
    agent_name: str

    # 基线指标
    avg_output_length: float = 0.0
    avg_duration_ms: float = 0.0
    avg_quality_score: float = 0.0
    avg_tool_calls: float = 0.0

    # 统计
    total_tasks: int = 0
    completed_tasks: int = 0
    skipped_tasks: int = 0
    failed_tasks: int = 0

    # 偷懒相关
    slacking_score: float = 0.0  # 0.0 - 1.0
    behavior_type: BehaviorType = BehaviorType.NORMAL
    warnings: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "slacking_score": round(self.slacking_score, 3),
            "behavior_type": self.behavior_type.value,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "completion_rate": round(self.completed_tasks / max(self.total_tasks, 1) * 100, 1),
            "warnings": self.warnings[-5:],  # 最近5条
        }


class SlackingDetector:
    """
    偷懒检测器
    基于多维度指标检测Agent偷懒行为
    """

    def __init__(self):
        # 阈值配置
        self.thresholds = {
            "min_output_length": 50,           # 最小输出长度
            "min_code_lines": 10,              # 最小代码行数
            "min_quality_score": 0.4,         # 最小质量分数
            "max_skip_rate": 0.3,             # 最大跳过率
            "max_quick_completion_rate": 0.2,  # 最大快速完成率
            "min_tool_usage": 1,              # 最小工具调用数
            "min_think_time_ms": 100,         # 最小思考时间
        }

        # 权重配置
        self.weights = {
            SlackingIndicator.LOW_OUTPUT_LENGTH: 0.15,
            SlackingIndicator.LOW_CODE_COMPLEXITY: 0.10,
            SlackingIndicator.HIGH_SKIP_RATE: 0.20,
            SlackingIndicator.QUICK_COMPLETION: 0.15,
            SlackingIndicator.REPETITIVE_OUTPUT: 0.10,
            SlackingIndicator.GENERIC_RESPONSE: 0.10,
            SlackingIndicator.NO_TOOL_USAGE: 0.10,
            SlackingIndicator.LOW_QUALITY_SCORE: 0.10,
        }

        self._profiles: Dict[str, AgentBehaviorProfile] = {}
        self._metrics_history: Dict[str, List[BehaviorMetrics]] = defaultdict(list)
        self._lock = threading.RLock()
        self._callbacks: List[Callable] = []

        logger.info("SlackingDetector 初始化完成")

    def register_callback(self, callback: Callable):
        """注册检测回调"""
        self._callbacks.append(callback)

    def analyze_metrics(self, metrics: BehaviorMetrics) -> Dict[str, Any]:
        """分析单个任务的行为指标"""
        indicators = {}
        total_score = 0.0

        # 1. 输出长度检查
        if metrics.output_length < self.thresholds["min_output_length"]:
            indicators[SlackingIndicator.LOW_OUTPUT_LENGTH] = True
            total_score += self.weights[SlackingIndicator.LOW_OUTPUT_LENGTH]

        # 2. 代码复杂度检查
        if metrics.code_lines > 0 and metrics.code_lines < self.thresholds["min_code_lines"]:
            indicators[SlackingIndicator.LOW_CODE_COMPLEXITY] = True
            total_score += self.weights[SlackingIndicator.LOW_CODE_COMPLEXITY]

        # 3. 跳过率检查
        if metrics.skipped_steps > 0:
            total_steps = metrics.skipped_steps + 1
            skip_rate = metrics.skipped_steps / total_steps
            if skip_rate > self.thresholds["max_skip_rate"]:
                indicators[SlackingIndicator.HIGH_SKIP_RATE] = True
                total_score += self.weights[SlackingIndicator.HIGH_SKIP_RATE]

        # 4. 快速完成检查 (实际时间 << 预期时间)
        if metrics.expected_duration_ms > 0:
            time_ratio = metrics.actual_duration_ms / metrics.expected_duration_ms
            if time_ratio < 0.2:  # 完成时间少于预期的20%
                indicators[SlackingIndicator.QUICK_COMPLETION] = True
                total_score += self.weights[SlackingIndicator.QUICK_COMPLETION]

        # 5. 重复输出检查
        if metrics.repeated_patterns > 3:
            indicators[SlackingIndicator.REPETITIVE_OUTPUT] = True
            total_score += self.weights[SlackingIndicator.REPETITIVE_OUTPUT]

        # 6. 通用响应检查 - 短输出可能是敷衍的通用回复
        if metrics.output_length < 100 and metrics.output_words < 20:
            indicators[SlackingIndicator.GENERIC_RESPONSE] = True
            total_score += self.weights[SlackingIndicator.GENERIC_RESPONSE]

        # 7. 无工具使用检查
        if metrics.tool_calls < self.thresholds["min_tool_usage"] and metrics.actual_duration_ms > 1000:
            indicators[SlackingIndicator.NO_TOOL_USAGE] = True
            total_score += self.weights[SlackingIndicator.NO_TOOL_USAGE]

        # 8. 质量分数检查
        if metrics.quality_score < self.thresholds["min_quality_score"]:
            indicators[SlackingIndicator.LOW_QUALITY_SCORE] = True
            total_score += self.weights[SlackingIndicator.LOW_QUALITY_SCORE]

        return {
            "indicators": [i.value for i in indicators.keys()],
            "slacking_score": min(total_score, 1.0),
            "is_suspected": total_score > 0.3,
            "is_confirmed": total_score > 0.6,
        }

    def update_profile(self, agent_id: str, agent_name: str, metrics: BehaviorMetrics,
                       analysis: Dict[str, Any]):
        """更新Agent行为画像"""
        with self._lock:
            if agent_id not in self._profiles:
                self._profiles[agent_id] = AgentBehaviorProfile(
                    agent_id=agent_id,
                    agent_name=agent_name,
                )

            profile = self._profiles[agent_id]

            # 更新历史
            self._metrics_history[agent_id].append(metrics)
            if len(self._metrics_history[agent_id]) > 100:
                self._metrics_history[agent_id].pop(0)

            # 更新统计
            profile.total_tasks += 1
            if metrics.has_error:
                profile.failed_tasks += 1
            elif metrics.skipped_steps > 0:
                profile.skipped_tasks += 1
            else:
                profile.completed_tasks += 1

            # 更新滑动平均
            history = self._metrics_history[agent_id]
            if len(history) >= 5:
                recent = history[-20:]
                profile.avg_output_length = statistics.mean(m.output_length for m in recent)
                profile.avg_duration_ms = statistics.mean(m.actual_duration_ms for m in recent)
                profile.avg_quality_score = statistics.mean(m.quality_score for m in recent)
                profile.avg_tool_calls = statistics.mean(m.tool_calls for m in recent)

            # 更新偷懒分数
            profile.slacking_score = (
                0.7 * profile.slacking_score +
                0.3 * analysis["slacking_score"]
            )

            # 更新行为类型
            if profile.slacking_score > 0.6:
                profile.behavior_type = BehaviorType.SLACKING
                profile.warnings.append(f"{metrics.timestamp.isoformat()}: 检测到偷懒行为")
            elif profile.slacking_score > 0.3:
                profile.behavior_type = BehaviorType.SUSPICIOUS
                profile.warnings.append(f"{metrics.timestamp.isoformat()}: 可疑行为")
            elif profile.slacking_score < 0.1:
                profile.behavior_type = BehaviorType.HARD_WORK
            else:
                profile.behavior_type = BehaviorType.NORMAL

            profile.last_updated = datetime.now()

            # 触发回调
            if analysis["is_confirmed"]:
                for callback in self._callbacks:
                    try:
                        callback(agent_id, profile, analysis)
                    except Exception as e:
                        logger.error(f"回调执行失败: {e}")

    def get_profile(self, agent_id: str) -> Optional[AgentBehaviorProfile]:
        """获取Agent行为画像"""
        return self._profiles.get(agent_id)

    def get_all_profiles(self) -> List[AgentBehaviorProfile]:
        """获取所有Agent画像"""
        return list(self._profiles.values())

    def get_suspected_agents(self, min_score: float = 0.3) -> List[AgentBehaviorProfile]:
        """获取疑似偷懒的Agent"""
        return [
            p for p in self._profiles.values()
            if p.slacking_score >= min_score
        ]

    def get_stats(self) -> Dict[str, Any]:
        """获取检测统计"""
        profiles = list(self._profiles.values())
        if not profiles:
            return {"total_agents": 0}

        return {
            "total_agents": len(profiles),
            "hard_workers": len([p for p in profiles if p.behavior_type == BehaviorType.HARD_WORK]),
            "normal": len([p for p in profiles if p.behavior_type == BehaviorType.NORMAL]),
            "suspicious": len([p for p in profiles if p.behavior_type == BehaviorType.SUSPICIOUS]),
            "slacking": len([p for p in profiles if p.behavior_type == BehaviorType.SLACKING]),
            "avg_slacking_score": round(statistics.mean(p.slacking_score for p in profiles), 3),
            "total_tasks_tracked": sum(p.total_tasks for p in profiles),
        }


class OutputAnalyzer:
    """输出分析器 - 检测敷衍/通用响应"""

    GENERIC_PATTERNS = [
        r"^好的$", r"^ok$", r"^完成$", r"^done$",
        r"^没问题$", r"^OK$", r"^收到$",
        r"^已处理$", r"^已完成$", r"^处理中$",
    ]

    REPETITIVE_PATTERNS = [
        r"(.+?)\1{3,}",  # 重复3次以上的字符
        r"(.{10,}?)\1{2,}",  # 重复的10字符以上片段
    ]

    LOW_QUALITY_INDICATORS = [
        "placeholder", "todo", "xxx", "...",
        "此处省略", "待填充", "TODO",
    ]

    @classmethod
    def analyze_output(cls, output: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """分析输出质量"""
        output_lower = output.lower()
        indicators = []
        quality_score = 1.0

        # 1. 检查通用响应
        for pattern in cls.GENERIC_PATTERNS:
            if re.match(pattern, output_lower.strip()):
                indicators.append("generic_response")
                quality_score -= 0.3
                break

        # 2. 检查重复模式
        for pattern in cls.REPETITIVE_PATTERNS:
            if re.search(pattern, output):
                indicators.append("repetitive_output")
                quality_score -= 0.2
                break

        # 3. 检查低质量指示词
        for indicator in cls.LOW_QUALITY_INDICATORS:
            if indicator in output_lower:
                indicators.append(f"low_quality_indicator: {indicator}")
                quality_score -= 0.15
                break

        # 4. 检查长度
        if len(output) < 20:
            indicators.append("too_short")
            quality_score -= 0.3
        elif len(output) < 50:
            quality_score -= 0.1

        # 5. 检查是否有实质内容
        substantive_words = ["分析", "实现", "设计", "方案", "代码", "结果", "问题", "建议"]
        if not any(word in output for word in substantive_words):
            indicators.append("no_substantive_content")
            quality_score -= 0.2

        return {
            "is_generic": "generic_response" in indicators,
            "is_repetitive": "repetitive_output" in indicators,
            "quality_score": max(0.0, quality_score),
            "indicators": indicators,
            "output_length": len(output),
            "is_acceptable": quality_score >= 0.5 and len(output) >= 20,
        }


class BehaviorMonitor:
    """
    行为监控器
    实时监控Agent行为，记录并分析
    """

    def __init__(self, detector: SlackingDetector):
        self.detector = detector
        self._active_monitors: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        logger.info("BehaviorMonitor 初始化完成")

    async def start_monitor(self, agent_id: str, agent_name: str, task_id: str,
                            expected_duration_ms: float = 0) -> str:
        """开始监控"""
        monitor_id = f"{agent_id}_{task_id}_{time.time()}"
        with self._lock:
            self._active_monitors[monitor_id] = {
                "agent_id": agent_id,
                "agent_name": agent_name,
                "task_id": task_id,
                "start_time": time.time(),
                "expected_duration_ms": expected_duration_ms,
                "tool_calls": 0,
                "output_parts": [],
            }
        logger.debug(f"开始监控: {monitor_id}")
        return monitor_id

    def record_tool_call(self, monitor_id: str):
        """记录工具调用"""
        with self._lock:
            if monitor_id in self._active_monitors:
                self._active_monitors[monitor_id]["tool_calls"] += 1

    def record_output_part(self, monitor_id: str, part: str):
        """记录输出片段"""
        with self._lock:
            if monitor_id in self._active_monitors:
                self._active_monitors[monitor_id]["output_parts"].append(part)

    async def end_monitor(self, monitor_id: str, has_error: bool = False) -> BehaviorMetrics:
        """结束监控并返回分析结果"""
        with self._lock:
            if monitor_id not in self._active_monitors:
                raise ValueError(f"Monitor {monitor_id} not found")

            data = self._active_monitors.pop(monitor_id)

        metrics = BehaviorMetrics(
            agent_id=data["agent_id"],
            task_id=data["task_id"],
            output_length=sum(len(p) for p in data["output_parts"]),
            output_words=len("".join(data["output_parts"]).split()),
            tool_calls=data["tool_calls"],
            actual_duration_ms=(time.time() - data["start_time"]) * 1000,
            expected_duration_ms=data.get("expected_duration_ms", 0),
            has_error=has_error,
        )

        # 分析
        analysis = self.detector.analyze_metrics(metrics)
        self.detector.update_profile(
            data["agent_id"],
            data["agent_name"],
            metrics,
            analysis
        )

        return metrics

    def get_active_monitors(self) -> List[Dict[str, Any]]:
        """获取当前活跃监控"""
        return list(self._active_monitors.values())


# 全局实例
_detector: Optional[SlackingDetector] = None
_monitor: Optional[BehaviorMonitor] = None


def get_slacking_detector() -> SlackingDetector:
    global _detector
    if _detector is None:
        _detector = SlackingDetector()
    return _detector


def get_behavior_monitor() -> BehaviorMonitor:
    global _monitor
    if _monitor is None:
        _monitor = BehaviorMonitor(get_slacking_detector())
    return _monitor


def analyze_output_quality(output: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """便捷函数：分析输出质量"""
    return OutputAnalyzer.analyze_output(output, context)


async def monitor_agent_task(agent_id: str, agent_name: str, task_id: str,
                              task_func, expected_duration_ms: float = 0) -> Tuple[Any, Dict]:
    """便捷函数：监控Agent任务执行"""
    monitor = get_behavior_monitor()
    detector = get_slacking_detector()

    monitor_id = await monitor.start_monitor(
        agent_id, agent_name, task_id, expected_duration_ms
    )

    try:
        result = await task_func()
        metrics = await monitor.end_monitor(monitor_id, has_error=False)
        return result, {
            "metrics": metrics.to_dict(),
            "analysis": detector.analyze_metrics(metrics),
        }
    except Exception as e:
        await monitor.end_monitor(monitor_id, has_error=True)
        raise


__all__ = [
    "SlackingDetector",
    "BehaviorMonitor",
    "OutputAnalyzer",
    "BehaviorMetrics",
    "AgentBehaviorProfile",
    "BehaviorType",
    "SlackingIndicator",
    "get_slacking_detector",
    "get_behavior_monitor",
    "analyze_output_quality",
    "monitor_agent_task",
]
