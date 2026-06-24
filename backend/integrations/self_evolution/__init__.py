"""
Nanobot-Factory自我进化与学习模块
===========================

本模块整合了多种自我进化和持续学习能力：
- Reflexion: 言语强化学习框架
- AgentGym: 通用智能体自我进化平台
- 持续学习: 增量学习与知识更新
- 记忆系统: 情景记忆、语义记忆、操作记忆
- 反馈机制: 自我评估、外部反馈、错误学习

作者：MiniMax Agent
日期：2026-03-05
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class LearningType(Enum):
    """学习类型枚举"""
    BEHAVIOR_CLONING = "behavior_cloning"       # 行为克隆
    REINFORCEMENT = "reinforcement"             # 强化学习
    REFLEXION = "reflexion"                     # 反思学习
    FEW_SHOT = "few_shot"                       # 少样本学习
    CONTINUAL = "continual"                      # 持续学习
    META_LEARNING = "meta_learning"             # 元学习


class MemoryType(Enum):
    """记忆类型枚举"""
    EPISODIC = "episodic"                       # 情景记忆
    SEMANTIC = "semantic"                       # 语义记忆
    PROCEDURAL = "procedural"                   # 程序记忆
    WORKING = "working"                         # 工作记忆


class FeedbackSource(Enum):
    """反馈来源枚举"""
    SELF = "self"                               # 自我评估
    EXTERNAL = "external"                       # 外部反馈
    ENVIRONMENT = "environment"                  # 环境反馈
    HUMAN = "human"                             # 人类反馈


@dataclass
class Experience:
    """经验数据"""
    id: str
    state: str
    action: str
    result: str
    reward: float
    feedback: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Memory:
    """记忆条目"""
    id: str
    content: str
    memory_type: MemoryType
    importance: float
    timestamp: float
    access_count: int = 0
    last_access: float = 0.0
    associations: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None


@dataclass
class Reflection:
    """反思记录"""
    id: str
    experience_id: str
    reflection_text: str
    lessons_learned: List[str]
    action_adjustments: List[str]
    confidence: float
    timestamp: float


@dataclass
class EvolutionRecord:
    """进化记录"""
    id: str
    iteration: int
    learning_type: LearningType
    changes: Dict[str, Any]
    performance_before: float
    performance_after: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class ReflexionAgent:
    """
    Reflexion智能体

    基于言语强化学习的智能体，
    通过维护情景记忆进行试错学习。

    参考: https://github.com/noahshinn/reflexion
    """

    def __init__(self, name: str):
        self.name = name
        self.episodic_memory: List[Experience] = []
        self.reflections: List[Reflection] = []
        self.max_memory_size = 100
        self.reflection_threshold = 0.7

    def add_experience(self, experience: Experience) -> None:
        """添加经验到记忆"""
        self.episodic_memory.append(experience)

        # 保持记忆大小
        if len(self.episodic_memory) > self.max_memory_size:
            self.episodic_memory.pop(0)

        logger.info(f"添加经验: {experience.id}, 奖励: {experience.reward}")

    async def reflect(self) -> Optional[Reflection]:
        """进行反思"""
        if len(self.episodic_memory) < 3:
            return None

        # 找到低奖励的经验
        low_reward_experiences = [
            exp for exp in self.episodic_memory
            if exp.reward < self.reflection_threshold
        ]

        if not low_reward_experiences:
            return None

        # 生成反思
        reflection = await self._generate_reflection(
            low_reward_experiences[-1]
        )

        self.reflections.append(reflection)
        logger.info(f"生成反思: {reflection.id}")

        return reflection

    async def _generate_reflection(self, experience: Experience) -> Reflection:
        """生成反思内容"""
        # 分析经验
        lessons = []
        adjustments = []

        if experience.reward < 0.3:
            lessons.append("需要改变策略")
            adjustments.append("尝试不同的方法")
        elif experience.reward < 0.6:
            lessons.append("策略部分有效")
            adjustments.append("优化当前方法")

        confidence = 1.0 - experience.reward

        reflection = Reflection(
            id=f"ref_{len(self.reflections) + 1}",
            experience_id=experience.id,
            reflection_text=f"分析: {experience.action} -> {experience.result}",
            lessons_learned=lessons,
            action_adjustments=adjustments,
            confidence=confidence,
            timestamp=asyncio.get_event_loop().time()
        )

        return reflection

    def get_relevant_memories(self, query: str, limit: int = 5) -> List[Experience]:
        """获取相关记忆"""
        # 简化版本：返回最近的记忆
        return self.episodic_memory[-limit:] if self.episodic_memory else []

    def clear_old_memories(self, keep_recent: int = 10) -> int:
        """清理旧记忆"""
        removed = len(self.episodic_memory) - keep_recent
        if removed > 0:
            self.episodic_memory = self.episodic_memory[-keep_recent:]
            logger.info(f"清理了 {removed} 条旧记忆")
        return removed


class AgentGymEvolver:
    """
    AgentGym进化器

    通用智能体自我进化平台，
    实现数据采样、训练微调、自我进化、能力评测。

    参考: https://github.com/WooooDyy/AgentGym
    """

    def __init__(self, name: str):
        self.name = name
        self.general_capabilities: List[str] = []
        self.task_history: List[Dict[str, Any]] = []
        self.current_iteration = 0

    async def initialize(self, expert_trajectories: List[Dict[str, Any]]) -> None:
        """初始化：行为克隆"""
        logger.info("开始行为克隆初始化...")

        for trajectory in expert_trajectories:
            # 学习专家轨迹
            self.general_capabilities.append(trajectory.get("skill", "unknown"))

        logger.info(f"行为克隆完成，掌握 {len(self.general_capabilities)} 个技能")

    async def explore_and_learn(
        self,
        environments: List[str],
        external_feedback: bool = True
    ) -> Dict[str, Any]:
        """探索学习阶段"""
        logger.info(f"开始探索 {len(environments)} 个环境...")

        exploration_results = {
            "new_skills": [],
            "performance_improvements": [],
            "tasks_completed": 0
        }

        for env in environments:
            # 在环境中探索
            result = await self._explore_environment(env, external_feedback)
            exploration_results["new_skills"].extend(result.get("new_skills", []))
            exploration_results["tasks_completed"] += result.get("completed", 0)

            if result.get("improvement", 0) > 0:
                exploration_results["performance_improvements"].append(result["improvement"])

        self.current_iteration += 1
        logger.info(f"探索完成，迭代 {self.current_iteration}")

        return exploration_results

    async def _explore_environment(
        self,
        env: str,
        external_feedback: bool
    ) -> Dict[str, Any]:
        """探索单个环境"""
        # 模拟探索
        new_skills = [f"skill_from_{env}"]
        completed = 1
        improvement = 0.1

        return {
            "environment": env,
            "new_skills": new_skills,
            "completed": completed,
            "improvement": improvement
        }

    async def evaluate_capabilities(self) -> Dict[str, Any]:
        """评估能力"""
        return {
            "iteration": self.current_iteration,
            "general_capabilities": len(self.general_capabilities),
            "task_history_length": len(self.task_history),
            "performance_score": 0.85,  # 模拟分数
            "status": "evaluated"
        }

    def get_evolution_status(self) -> Dict[str, Any]:
        """获取进化状态"""
        return {
            "name": self.name,
            "iteration": self.current_iteration,
            "capabilities_count": len(self.general_capabilities),
            "task_history_count": len(self.task_history)
        }


class ContinuousLearningSystem:
    """
    持续学习系统

    实现增量学习、知识更新、能力扩展
    """

    def __init__(self):
        self.learned_knowledge: Dict[str, Any] = {}
        self.learning_history: List[Dict[str, Any]] = []
        self.performance_metrics: Dict[str, List[float]] = {}

    async def learn_from_feedback(
        self,
        feedback: Any,
        learning_type: LearningType = LearningType.CONTINUAL
    ) -> Dict[str, Any]:
        """从反馈中学习"""
        logger.info(f"开始{learning_type.value}学习...")

        result = {
            "learning_type": learning_type.value,
            "knowledge_updated": False,
            "insights": []
        }

        if learning_type == LearningType.CONTINUAL:
            # 持续学习
            result["insights"] = await self._continual_learning(feedback)
            result["knowledge_updated"] = True

        elif learning_type == LearningType.FEW_SHOT:
            # 少样本学习
            result["insights"] = await self._few_shot_learning(feedback)
            result["knowledge_updated"] = True

        elif learning_type == LearningType.META_LEARNING:
            # 元学习
            result["insights"] = await self._meta_learning(feedback)
            result["knowledge_updated"] = True

        self.learning_history.append({
            "type": learning_type.value,
            "timestamp": datetime.now().isoformat(),
            "insights": result["insights"]
        })

        return result

    async def _continual_learning(self, feedback: Any) -> List[str]:
        """持续学习"""
        insights = []

        # 分析反馈
        if isinstance(feedback, dict):
            if "error" in feedback:
                insights.append(f"从错误中学习: {feedback['error']}")
            if "success" in feedback:
                insights.append(f"强化成功经验: {feedback['success']}")
            if "suggestion" in feedback:
                insights.append(f"采纳建议: {feedback['suggestion']}")

        return insights

    async def _few_shot_learning(self, feedback: Any) -> List[str]:
        """少样本学习"""
        insights = []

        # 从少量示例中学习
        if isinstance(feedback, list) and len(feedback) > 0:
            insights.append(f"从 {len(feedback)} 个示例中提取模式")

        return insights

    async def _meta_learning(self, feedback: Any) -> List[str]:
        """元学习：学习如何学习"""
        insights = []

        # 分析学习过程
        insights.append("优化学习策略")
        insights.append("提高样本效率")

        return insights

    def update_performance(self, metric_name: str, value: float) -> None:
        """更新性能指标"""
        if metric_name not in self.performance_metrics:
            self.performance_metrics[metric_name] = []

        self.performance_metrics[metric_name].append(value)

        # 保持最近100个数据点
        if len(self.performance_metrics[metric_name]) > 100:
            self.performance_metrics[metric_name] = \
                self.performance_metrics[metric_name][-100:]

    def get_performance_trend(self, metric_name: str) -> Dict[str, Any]:
        """获取性能趋势"""
        if metric_name not in self.performance_metrics:
            return {"error": "指标不存在"}

        values = self.performance_metrics[metric_name]

        if not values:
            return {"error": "没有数据"}

        return {
            "metric": metric_name,
            "current": values[-1],
            "average": sum(values) / len(values),
            "trend": "improving" if values[-1] > values[0] else "declining",
            "data_points": len(values)
        }


class MemoryOrganizationSystem:
    """
    记忆组织系统

    实现自组织记忆、情景记忆、语义记忆管理
    """

    def __init__(self):
        self.memories: Dict[str, Memory] = {}
        self.memory_index: Dict[MemoryType, List[str]] = {
            MemoryType.EPISODIC: [],
            MemoryType.SEMANTIC: [],
            MemoryType.PROCEDURAL: [],
            MemoryType.WORKING: []
        }
        self.max_memories = 1000

    def store_memory(self, memory: Memory) -> str:
        """存储记忆"""
        self.memories[memory.id] = memory
        self.memory_index[memory.memory_type].append(memory.id)

        # 保持记忆数量
        if len(self.memories) > self.max_memories:
            self._consolidate_memories()

        logger.info(f"存储记忆: {memory.id}, 类型: {memory.memory_type.value}")
        return memory.id

    def retrieve_memories(
        self,
        memory_type: Optional[MemoryType] = None,
        importance_threshold: float = 0.0,
        limit: int = 10
    ) -> List[Memory]:
        """检索记忆"""
        candidates = []

        for mem_id, memory in self.memories.items():
            if memory_type and memory.memory_type != memory_type:
                continue
            if memory.importance < importance_threshold:
                continue
            candidates.append(memory)

        # 按重要性排序
        candidates.sort(key=lambda m: m.importance, reverse=True)

        # 更新访问统计
        for mem in candidates[:limit]:
            mem.access_count += 1
            mem.last_access = asyncio.get_event_loop().time()

        return candidates[:limit]

    def find_related_memories(self, memory_id: str) -> List[Memory]:
        """查找相关记忆"""
        if memory_id not in self.memories:
            return []

        target = self.memories[memory_id]
        related = []

        for mem_id, memory in self.memories.items():
            if mem_id == memory_id:
                continue

            # 基于关联查找
            if set(target.associations) & set(memory.associations):
                related.append(memory)

            # 基于内容相似度（简化版本）
            if target.memory_type == memory.memory_type:
                related.append(memory)

        return related[:5]

    def _consolidate_memories(self) -> None:
        """记忆整合：保留重要记忆"""
        # 按重要性排序
        sorted_memories = sorted(
            self.memories.values(),
            key=lambda m: m.importance,
            reverse=True
        )

        # 保留前一半
        keep_count = self.max_memories // 2
        keep_ids = {m.id for m in sorted_memories[:keep_count]}

        # 删除不重要记忆
        for mem_id in list(self.memories.keys()):
            if mem_id not in keep_ids:
                mem_type = self.memories[mem_id].memory_type
                del self.memories[mem_id]
                if mem_id in self.memory_index[mem_type]:
                    self.memory_index[mem_type].remove(mem_id)

        logger.info(f"记忆整合完成，保留 {keep_count} 条记忆")

    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计"""
        return {
            "total_memories": len(self.memories),
            "by_type": {
                mtype.value: len(ids)
                for mtype, ids in self.memory_index.items()
            },
            "average_importance": sum(
                m.importance for m in self.memories.values()
            ) / len(self.memories) if self.memories else 0
        }


class SelfEvolutionEngine:
    """
    自我进化引擎

    整合所有自我进化能力的主引擎
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.reflexion = ReflexionAgent(agent_name)
        self.evolver = AgentGymEvolver(agent_name)
        self.learning = ContinuousLearningSystem()
        self.memory = MemoryOrganizationSystem()
        self.evolution_records: List[EvolutionRecord] = []
        self.is_evolving = False

    async def initialize_with_expertise(
        self,
        expert_trajectories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """初始化：获取专家能力"""
        logger.info("开始专家能力初始化...")

        await self.evolver.initialize(expert_trajectories)

        record = EvolutionRecord(
            id=f"evo_{len(self.evolution_records) + 1}",
            iteration=0,
            learning_type=LearningType.BEHAVIOR_CLONING,
            changes={"skills_acquired": len(expert_trajectories)},
            performance_before=0.0,
            performance_after=0.5,
            timestamp=asyncio.get_event_loop().time()
        )
        self.evolution_records.append(record)

        return {
            "status": "initialized",
            "skills_count": len(expert_trajectories)
        }

    async def evolve_with_exploration(
        self,
        environments: List[str]
    ) -> Dict[str, Any]:
        """通过探索进行进化"""
        if self.is_evolving:
            return {"status": "already_evolving"}

        self.is_evolving = True
        logger.info("开始自我进化...")

        try:
            # 探索学习
            explore_result = await self.evolver.explore_and_learn(environments)

            # 反思学习
            await self.reflexion.reflect()

            # 持续学习
            learning_result = await self.learning.learn_from_feedback(
                explore_result,
                LearningType.CONTINUAL
            )

            # 评估进化效果
            evaluation = await self.evolver.evaluate_capabilities()

            # 记录进化
            record = EvolutionRecord(
                id=f"evo_{len(self.evolution_records) + 1}",
                iteration=self.evolver.current_iteration,
                learning_type=LearningType.REFLEXION,
                changes=explore_result,
                performance_before=0.5,
                performance_after=evaluation["performance_score"],
                timestamp=asyncio.get_event_loop().time()
            )
            self.evolution_records.append(record)

            return {
                "status": "evolved",
                "iteration": self.evolver.current_iteration,
                "exploration": explore_result,
                "learning": learning_result,
                "evaluation": evaluation
            }

        finally:
            self.is_evolving = False

    async def learn_from_result(
        self,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """从结果中学习"""
        # 提取奖励
        reward = result.get("reward", 0.5)

        # 创建经验
        experience = Experience(
            id=f"exp_{len(self.reflexion.episodic_memory) + 1}",
            state=result.get("state", ""),
            action=result.get("action", ""),
            result=result.get("result", ""),
            reward=reward,
            feedback=result.get("feedback", ""),
            timestamp=asyncio.get_event_loop().time()
        )

        # 添加到记忆
        self.reflexion.add_experience(experience)

        # 存储到记忆系统
        memory = Memory(
            id=f"mem_{len(self.memory.memories) + 1}",
            content=result.get("result", ""),
            memory_type=MemoryType.EPISODIC,
            importance=reward,
            timestamp=asyncio.get_event_loop().time(),
            associations=[result.get("action", "")]
        )
        self.memory.store_memory(memory)

        # 更新性能指标
        self.learning.update_performance("task_success", reward)

        # 触发反思
        if reward < 0.7:
            reflection = await self.reflexion.reflect()
            if reflection:
                return {
                    "status": "reflected",
                    "reflection": {
                        "lessons": reflection.lessons_learned,
                        "adjustments": reflection.action_adjustments
                    }
                }

        return {
            "status": "learned",
            "reward": reward
        }

    def get_evolution_history(self) -> List[Dict[str, Any]]:
        """获取进化历史"""
        return [
            {
                "iteration": record.iteration,
                "learning_type": record.learning_type.value,
                "performance_delta": record.performance_after - record.performance_before,
                "timestamp": record.timestamp
            }
            for record in self.evolution_records
        ]

    def get_comprehensive_status(self) -> Dict[str, Any]:
        """获取综合状态"""
        return {
            "agent_name": self.agent_name,
            "evolution": {
                "iteration": self.evolver.current_iteration,
                "is_evolving": self.is_evolving,
                "capabilities": len(self.evolver.general_capabilities)
            },
            "memory": self.memory.get_memory_stats(),
            "learning": {
                "history_length": len(self.learning.learning_history),
                "metrics": list(self.learning.performance_metrics.keys())
            },
            "reflexion": {
                "memories": len(self.reflexion.episodic_memory),
                "reflections": len(self.reflexion.reflections)
            }
        }


# 全局自我进化引擎
_global_evolution_engine: Optional[SelfEvolutionEngine] = None


def get_evolution_engine(agent_name: str = "nanobot") -> SelfEvolutionEngine:
    """获取全局自我进化引擎"""
    global _global_evolution_engine
    if _global_evolution_engine is None:
        _global_evolution_engine = SelfEvolutionEngine(agent_name)
    return _global_evolution_engine


# 导出模块
__all__ = [
    "LearningType",
    "MemoryType",
    "FeedbackSource",
    "Experience",
    "Memory",
    "Reflection",
    "EvolutionRecord",
    "ReflexionAgent",
    "AgentGymEvolver",
    "ContinuousLearningSystem",
    "MemoryOrganizationSystem",
    "SelfEvolutionEngine",
    "get_evolution_engine",
]
