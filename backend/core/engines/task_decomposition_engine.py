#!/usr/bin/env python3
"""
OpenClaw 任务分解引擎 (Task Decomposition Engine)
================================================

将复杂任务自动拆分为可执行的子任务，形成完整的任务执行计划。

核心功能：
1. 智能任务分析 - 理解任务意图和复杂度
2. 多维度分解 - 功能/流程/层次分解
3. 依赖关系管理 - 构建任务依赖图
4. 并行优化 - 识别可并行执行的任务
5. 资源评估 - 评估任务所需资源

@author MiniMax Agent
@date 2026-04-14
"""

import asyncio
import logging
import uuid
import json
import re
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import heapq

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型"""
    ANALYSIS = "analysis"           # 分析类
    DESIGN = "design"              # 设计类
    IMPLEMENTATION = "implementation"  # 实现类
    TESTING = "testing"            # 测试类
    DEPLOYMENT = "deployment"      # 部署类
    RESEARCH = "research"          # 研究类
    WRITING = "writing"            # 写作类
    ORCHESTRATION = "orchestration" # 编排类
    COORDINATION = "coordination"  # 协调类


class TaskPriority(Enum):
    """任务优先级"""
    CRITICAL = 1   # 关键
    HIGH = 2       # 高
    NORMAL = 3     # 普通
    LOW = 4        # 低
    BACKGROUND = 5  # 后台


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"           # 待执行
    READY = "ready"               # 就绪
    RUNNING = "running"           # 执行中
    WAITING = "waiting"           # 等待依赖
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消


class DependencyType(Enum):
    """依赖类型"""
    STRONG = "strong"      # 强依赖 - 必须等待
    WEAK = "weak"          # 弱依赖 - 可以并行但最好串行
    DATA = "data"          # 数据依赖 - 传递数据
    CONDITIONAL = "conditional"  # 条件依赖 - 满足条件后执行


@dataclass
class TaskInput:
    """任务输入定义"""
    name: str
    type: str  # string, number, object, array, file
    required: bool = True
    description: str = ""
    default: Any = None
    source: str = ""  # user, previous_task, external


@dataclass
class TaskOutput:
    """任务输出定义"""
    name: str
    type: str
    description: str = ""
    target: str = ""  # next_task, report, storage


@dataclass
class SubTask:
    """
    子任务定义
    
    每个子任务都是独立的执行单元，可以：
    1. 分配给特定Agent执行
    2. 调用特定Skill
    3. 使用特定工具
    4. 与其他任务形成依赖关系
    """
    # 基础信息
    task_id: str
    name: str
    description: str
    task_type: TaskType
    priority: TaskPriority = TaskPriority.NORMAL
    
    # 执行配置
    assigned_agent: Optional[str] = None  # 指定Agent类型
    required_skills: List[str] = field(default_factory=list)  # 需要的技能
    required_tools: List[str] = field(default_factory=list)   # 需要的工具
    expert_ids: List[str] = field(default_factory=list)      # 咨询的专家ID
    
    # 输入输出
    inputs: List[TaskInput] = field(default_factory=list)
    outputs: List[TaskOutput] = field(default_factory=list)
    
    # 依赖管理
    dependencies: List[Tuple[str, DependencyType]] = field(default_factory=list)  # (task_id, dep_type)
    dependents: List[str] = field(default_factory=list)  # 依赖此任务的任务
    
    # 状态
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: Any = None
    error: Optional[str] = None
    
    # 执行信息
    estimated_duration: int = 0  # 预估时长(秒)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def can_execute(self, completed_tasks: Set[str]) -> bool:
        """检查任务是否可以执行"""
        if self.status != TaskStatus.PENDING:
            return False
        
        for dep_id, dep_type in self.dependencies:
            if dep_type in [DependencyType.STRONG, DependencyType.DATA]:
                if dep_id not in completed_tasks:
                    return False
        
        return True
    
    def add_dependency(self, task_id: str, dep_type: DependencyType = DependencyType.STRONG):
        """添加依赖"""
        self.dependencies.append((task_id, dep_type))
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type.value,
            "priority": self.priority.value,
            "assigned_agent": self.assigned_agent,
            "required_skills": self.required_skills,
            "required_tools": self.required_tools,
            "expert_ids": self.expert_ids,
            "inputs": [{"name": i.name, "type": i.type, "required": i.required} for i in self.inputs],
            "outputs": [{"name": o.name, "type": o.type} for o in self.outputs],
            "dependencies": [{"task_id": t[0], "type": t[1].value} for t in self.dependencies],
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "estimated_duration": self.estimated_duration,
            "metadata": self.metadata
        }


@dataclass
class ExecutionPlan:
    """
    执行计划
    
    包含完整的任务分解结果和执行顺序
    """
    plan_id: str
    original_task: str
    description: str
    
    # 任务列表
    tasks: Dict[str, SubTask] = field(default_factory=dict)
    
    # 执行顺序(拓扑排序结果)
    execution_order: List[str] = field(default_factory=list)
    
    # 并行分组
    parallel_groups: List[List[str]] = field(default_factory=list)  # 可并行执行的任务组
    
    # 统计信息
    total_tasks: int = 0
    critical_path: List[str] = field(default_factory=list)  # 关键路径
    estimated_total_time: int = 0  # 预估总时长(秒)
    
    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_task(self, task_id: str) -> Optional[SubTask]:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_ready_tasks(self, completed: Set[str]) -> List[SubTask]:
        """获取就绪任务(所有依赖已完成)"""
        ready = []
        for task in self.tasks.values():
            if task.can_execute(completed) and task.status == TaskStatus.PENDING:
                ready.append(task)
        
        # 按优先级排序
        ready.sort(key=lambda t: t.priority.value)
        return ready
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "plan_id": self.plan_id,
            "original_task": self.original_task,
            "description": self.description,
            "total_tasks": self.total_tasks,
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "execution_order": self.execution_order,
            "parallel_groups": self.parallel_groups,
            "critical_path": self.critical_path,
            "estimated_total_time": self.estimated_total_time,
            "created_at": self.created_at,
            "metadata": self.metadata
        }


class TaskDecompositionEngine:
    """
    任务分解引擎
    
    核心能力：
    1. 理解复杂任务的意图和目标
    2. 智能识别任务类型和所需技能
    3. 多维度任务分解(功能/流程/层次)
    4. 构建精确的依赖关系图
    5. 优化执行顺序和并行度
    """
    
    # 任务模式库 - 用于识别任务类型和结构
    TASK_PATTERNS = {
        "analysis": [
            r"分析\s*(.+)",
            r"研究\s*(.+)",
            r"评估\s*(.+)",
            r"审查\s*(.+)",
            r"诊断\s*(.+)",
            r"调研\s*(.+)",
            r"检查\s*(.+)"
        ],
        "design": [
            r"设计\s*(.+)",
            r"规划\s*(.+)",
            r"制定\s*(.+)",
            r"架构\s*(.+)",
            r"方案\s*(.+)",
            r"蓝图\s*(.+)"
        ],
        "implementation": [
            r"开发\s*(.+)",
            r"实现\s*(.+)",
            r"构建\s*(.+)",
            r"创建\s*(.+)",
            r"编写\s*(.+)",
            r"制作\s*(.+)",
            r"生成\s*(.+)",
            r"修复\s*(.+)",
            r"优化\s*(.+)"
        ],
        "testing": [
            r"测试\s*(.+)",
            r"验证\s*(.+)",
            r"检查\s*(.+)",
            r"审计\s*(.+)",
            r"质检\s*(.+)"
        ],
        "deployment": [
            r"部署\s*(.+)",
            r"发布\s*(.+)",
            r"上线\s*(.+)",
            r"安装\s*(.+)",
            r"配置\s*(.+)"
        ],
        "research": [
            r"调研\s*(.+)",
            r"搜索\s*(.+)",
            r"收集\s*(.+)",
            r"查找\s*(.+)",
            r"探索\s*(.+)"
        ],
        "writing": [
            r"写\s*(.+)",
            r"编辑\s*(.+)",
            r"撰写\s*(.+)",
            r"生成\s*(.+)文档",
            r"制作\s*(.+)报告"
        ]
    }
    
    # Agent能力映射 - 将任务类型映射到最佳Agent类型
    AGENT_CAPABILITIES = {
        TaskType.ANALYSIS: ["analyst_agent", "data_analyst"],
        TaskType.DESIGN: ["architect_agent", "ux_designer", "product_designer"],
        TaskType.IMPLEMENTATION: ["frontend_developer", "backend_developer", "fullstack_developer"],
        TaskType.TESTING: ["qa_engineer", "test_automation_engineer"],
        TaskType.DEPLOYMENT: ["devops_engineer", "sre_engineer"],
        TaskType.RESEARCH: ["research_analyst", "market_analyst"],
        TaskType.WRITING: ["technical_writer", "content_writer", "documentation_specialist"],
        TaskType.ORCHESTRATION: ["project_manager", "tech_lead"],
        TaskType.COORDINATION: ["coordinator", "scrum_master"]
    }
    
    # 技能需求映射
    SKILL_REQUIREMENTS = {
        "frontend": ["react", "typescript", "css", "ui_design"],
        "backend": ["python", "fastapi", "database", "api_design"],
        "data": ["data_analysis", "visualization", "statistics"],
        "ai": ["machine_learning", "nlp", "llm", "prompt_engineering"],
        "devops": ["docker", "kubernetes", "ci_cd", "cloud"],
        "security": ["security_audit", "penetration_testing", "compliance"],
        "database": ["sql", "nosql", "data_modeling", "optimization"],
        "api": ["rest_api", "graphql", "grpc", "api_design"],
        "testing": ["unit_testing", "integration_testing", "e2e_testing", "test_automation"],
        "mobile": ["ios", "android", "react_native", "flutter"]
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._init_patterns()
    
    def _init_patterns(self):
        """初始化正则表达式模式"""
        self._compiled_patterns = {}
        for task_type, patterns in self.TASK_PATTERNS.items():
            self._compiled_patterns[task_type] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    async def decompose(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionPlan:
        """
        分解任务
        
        Args:
            task: 原始任务描述
            context: 上下文信息(可选)
            
        Returns:
            ExecutionPlan: 完整的执行计划
        """
        self.logger.info(f"开始分解任务: {task[:100]}...")
        
        # 生成计划ID
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        
        # 创建执行计划
        plan = ExecutionPlan(
            plan_id=plan_id,
            original_task=task,
            description=""
        )
        
        # 1. 分析任务
        task_analysis = await self._analyze_task(task, context)
        
        # 2. 选择分解策略
        decomposition_strategy = self._select_strategy(task_analysis)
        
        # 3. 执行分解
        if decomposition_strategy == "hierarchical":
            subtasks = await self._hierarchical_decomposition(task, task_analysis)
        elif decomposition_strategy == "functional":
            subtasks = await self._functional_decomposition(task, task_analysis)
        elif decomposition_strategy == "process":
            subtasks = await self._process_decomposition(task, task_analysis)
        else:
            subtasks = await self._hybrid_decomposition(task, task_analysis)
        
        # 4. 添加任务到计划
        for subtask in subtasks:
            plan.tasks[subtask.task_id] = subtask
            plan.total_tasks += 1
        
        # 5. 构建依赖图
        self._build_dependency_graph(plan, subtasks, task_analysis)
        
        # 6. 拓扑排序
        plan.execution_order = self._topological_sort(plan)
        
        # 7. 识别并行组
        plan.parallel_groups = self._identify_parallel_groups(plan)
        
        # 8. 计算关键路径
        plan.critical_path = self._calculate_critical_path(plan)
        
        # 9. 估算总时长
        plan.estimated_total_time = self._estimate_total_time(plan)
        
        # 10. 添加计划描述
        plan.description = self._generate_plan_description(plan, task_analysis)
        
        self.logger.info(f"任务分解完成: {plan.total_tasks}个子任务, 预计耗时{plan.estimated_total_time}秒")
        
        return plan
    
    async def _analyze_task(
        self,
        task: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """分析任务特征"""
        analysis = {
            "raw_task": task,
            "task_type": self._detect_task_type(task),
            "complexity": self._estimate_complexity(task),
            "domain": self._detect_domain(task),
            "required_skills": self._identify_required_skills(task),
            "estimated_subtasks": self._estimate_subtask_count(task),
            "keywords": self._extract_keywords(task),
            "intent": self._analyze_intent(task)
        }
        
        self.logger.debug(f"任务分析结果: {analysis}")
        return analysis
    
    def _detect_task_type(self, task: str) -> TaskType:
        """检测任务类型"""
        for task_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(task)
                if match:
                    try:
                        return TaskType(task_type)
                    except ValueError:
                        continue
        
        # 默认根据关键词判断
        task_lower = task.lower()
        if any(k in task_lower for k in ["分析", "研究", "评估", "审查"]):
            return TaskType.ANALYSIS
        elif any(k in task_lower for k in ["设计", "规划", "制定", "方案"]):
            return TaskType.DESIGN
        elif any(k in task_lower for k in ["开发", "实现", "构建", "创建", "修复"]):
            return TaskType.IMPLEMENTATION
        elif any(k in task_lower for k in ["测试", "验证", "检查"]):
            return TaskType.TESTING
        elif any(k in task_lower for k in ["部署", "发布", "上线"]):
            return TaskType.DEPLOYMENT
        elif any(k in task_lower for k in ["调研", "搜索", "收集"]):
            return TaskType.RESEARCH
        elif any(k in task_lower for k in ["写", "编辑", "撰写", "文档", "报告"]):
            return TaskType.WRITING
        else:
            return TaskType.IMPLEMENTATION
    
    def _estimate_complexity(self, task: str) -> str:
        """估算任务复杂度"""
        # 基于长度和关键词估计
        complexity_score = 0
        
        # 长度因素
        if len(task) > 500:
            complexity_score += 2
        elif len(task) > 200:
            complexity_score += 1
        
        # 关键词因素
        complex_keywords = [
            "复杂", "全面", "完整", "系统", "多个", "综合",
            "integrate", "comprehensive", "complex", "multiple"
        ]
        for kw in complex_keywords:
            if kw.lower() in task.lower():
                complexity_score += 1
        
        # 多步骤指示
        step_indicators = ["首先", "然后", "接着", "最后", "步骤", "流程"]
        for kw in step_indicators:
            if kw in task:
                complexity_score += 1
        
        if complexity_score >= 4:
            return "high"
        elif complexity_score >= 2:
            return "medium"
        else:
            return "low"
    
    def _detect_domain(self, task: str) -> List[str]:
        """检测任务领域"""
        domains = []
        task_lower = task.lower()
        
        domain_keywords = {
            "frontend": ["前端", "界面", "ui", "react", "vue", "html", "css", "页面"],
            "backend": ["后端", "服务器", "api", "数据库", "服务"],
            "mobile": ["移动", "ios", "android", "手机", "app"],
            "data": ["数据", "分析", "统计", "可视化", "图表"],
            "ai": ["ai", "机器学习", "深度学习", "模型", "训练", "llm"],
            "devops": ["部署", "docker", "kubernetes", "ci/cd", "运维"],
            "security": ["安全", "加密", "认证", "权限"],
            "database": ["数据库", "sql", "存储", "迁移"],
            "api": ["接口", "rest", "graphql", "webhook"],
            "testing": ["测试", "单元测试", "集成测试", "质量"],
            "documentation": ["文档", "说明", "手册", "注释"]
        }
        
        for domain, keywords in domain_keywords.items():
            if any(kw in task_lower for kw in keywords):
                domains.append(domain)
        
        if not domains:
            domains.append("general")
        
        return domains
    
    def _identify_required_skills(self, task: str) -> List[str]:
        """识别所需技能"""
        skills = []
        task_lower = task.lower()
        
        for category, category_skills in self.SKILL_REQUIREMENTS.items():
            for skill in category_skills:
                if skill.lower() in task_lower or category in task_lower:
                    skills.append(skill)
        
        # 添加通用技能
        if not skills:
            skills = ["problem_solving", "research", "coding"]
        
        return list(set(skills))
    
    def _estimate_subtask_count(self, task: str) -> int:
        """估算子任务数量"""
        # 简单估算
        count = 1
        
        # 步骤指示词
        step_words = ["第一步", "第二", "第三", "第四", "第五",
                     "首先", "然后", "接着", "最后", "此外", "同时",
                     "stage", "phase", "step", "first", "then", "next", "finally"]
        
        for word in step_words:
            if word in task:
                count += 1
        
        # 长度因素
        if len(task) > 1000:
            count += 3
        elif len(task) > 500:
            count += 2
        elif len(task) > 200:
            count += 1
        
        # 复杂度因素
        if "复杂" in task or "全面" in task or "完整" in task:
            count += 2
        
        return max(2, min(count, 15))  # 限制在2-15之间
    
    def _extract_keywords(self, task: str) -> List[str]:
        """提取关键词"""
        # 简单分词
        words = re.findall(r'[\w]+', task.lower())
        
        # 停用词
        stopwords = {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
            "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
            "你", "会", "着", "没有", "看", "好", "自己", "这", "那", "些",
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "to", "of", "in", "for", "on", "with",
            "at", "by", "from", "as", "or", "and", "if", "but", "so", "that", "this"
        }
        
        keywords = [w for w in words if w not in stopwords and len(w) > 1]
        return keywords[:20]  # 限制数量
    
    def _analyze_intent(self, task: str) -> str:
        """分析用户意图"""
        task_lower = task.lower()
        
        if any(k in task_lower for k in ["帮我", "请", "需要", "想要", "帮我"]):
            return "request"
        elif any(k in task_lower for k in ["为什么", "怎么", "如何", "什么", "哪个"]):
            return "question"
        elif any(k in task_lower for k in ["修复", "解决", "解决", "改正"]):
            return "fix"
        elif any(k in task_lower for k in ["优化", "改进", "提升", "增强"]):
            return "improve"
        elif any(k in task_lower for k in ["创建", "新建", "添加", "开发"]):
            return "create"
        else:
            return "general"
    
    def _select_strategy(self, analysis: Dict[str, Any]) -> str:
        """选择分解策略"""
        complexity = analysis["complexity"]
        task_type = analysis["task_type"]
        
        if complexity == "high":
            return "hierarchical"
        elif task_type in [TaskType.IMPLEMENTATION, TaskType.TESTING]:
            return "process"
        elif task_type in [TaskType.DESIGN, TaskType.ANALYSIS]:
            return "functional"
        else:
            return "hybrid"
    
    async def _hierarchical_decomposition(
        self,
        task: str,
        analysis: Dict[str, Any]
    ) -> List[SubTask]:
        """层次分解 - 将任务分为高层、详细层、实现层"""
        subtasks = []
        
        # 1. 高层任务 - 规划与设计
        planning_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="任务规划与设计",
            description=f"分析{task}的需求，制定详细实施方案",
            task_type=TaskType.DESIGN,
            priority=TaskPriority.HIGH,
            assigned_agent="architect_agent",
            required_skills=["system_design", "requirement_analysis"],
            estimated_duration=60
        )
        subtasks.append(planning_task)
        
        # 2. 准备任务 - 环境与资源
        prep_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="准备工作",
            description="准备开发环境、工具和资源",
            task_type=TaskType.IMPLEMENTATION,
            priority=TaskPriority.HIGH,
            dependencies=[(planning_task.task_id, DependencyType.STRONG)],
            estimated_duration=120
        )
        subtasks.append(prep_task)
        
        # 3. 核心实现任务
        impl_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="核心功能实现",
            description=f"实现{task}的核心功能",
            task_type=TaskType.IMPLEMENTATION,
            priority=TaskPriority.CRITICAL,
            assigned_agent="developer_agent",
            dependencies=[(prep_task.task_id, DependencyType.STRONG)],
            required_skills=analysis["required_skills"],
            estimated_duration=600
        )
        subtasks.append(impl_task)
        
        # 4. 测试任务
        test_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="测试与验证",
            description="进行单元测试、集成测试和功能验证",
            task_type=TaskType.TESTING,
            priority=TaskPriority.HIGH,
            dependencies=[(impl_task.task_id, DependencyType.STRONG)],
            required_skills=["unit_testing", "integration_testing"],
            estimated_duration=300
        )
        subtasks.append(test_task)
        
        # 5. 部署任务
        deploy_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="部署与上线",
            description="部署到目标环境并进行监控",
            task_type=TaskType.DEPLOYMENT,
            priority=TaskPriority.NORMAL,
            dependencies=[(test_task.task_id, DependencyType.STRONG)],
            required_skills=["deployment", "monitoring"],
            estimated_duration=180
        )
        subtasks.append(deploy_task)
        
        # 6. 文档任务
        doc_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="文档编写",
            description="编写用户文档和开发文档",
            task_type=TaskType.WRITING,
            priority=TaskPriority.LOW,
            dependencies=[(impl_task.task_id, DependencyType.WEAK)],
            required_skills=["technical_writing"],
            estimated_duration=120
        )
        subtasks.append(doc_task)
        
        return subtasks
    
    async def _functional_decomposition(
        self,
        task: str,
        analysis: Dict[str, Any]
    ) -> List[SubTask]:
        """功能分解 - 按功能模块分解"""
        subtasks = []
        
        # 识别功能模块
        domains = analysis["domain"]
        
        for domain in domains:
            # 数据收集任务
            data_task = SubTask(
                task_id=f"sub_{uuid.uuid4().hex[:8]}",
                name=f"{domain}数据收集",
                description=f"收集{domain}相关的资料和数据",
                task_type=TaskType.RESEARCH,
                priority=TaskPriority.HIGH,
                required_skills=[f"{domain}_knowledge"],
                estimated_duration=180
            )
            subtasks.append(data_task)
            
            # 分析任务
            analysis_task = SubTask(
                task_id=f"sub_{uuid.uuid4().hex[:8]}",
                name=f"{domain}分析",
                description=f"对{domain}数据进行分析",
                task_type=TaskType.ANALYSIS,
                priority=TaskPriority.HIGH,
                assigned_agent="analyst_agent",
                dependencies=[(data_task.task_id, DependencyType.STRONG)],
                required_skills=["data_analysis"],
                estimated_duration=300
            )
            subtasks.append(analysis_task)
        
        # 综合任务
        synthesis_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="综合分析与报告",
            description="整合各领域分析结果，生成最终报告",
            task_type=TaskType.ANALYSIS,
            priority=TaskPriority.CRITICAL,
            assigned_agent="senior_analyst",
            dependencies=[(t.task_id, DependencyType.STRONG) for t in subtasks],
            required_skills=["synthesis", "report_writing"],
            estimated_duration=300
        )
        subtasks.append(synthesis_task)
        
        return subtasks
    
    async def _process_decomposition(
        self,
        task: str,
        analysis: Dict[str, Any]
    ) -> List[SubTask]:
        """流程分解 - 按业务流程步骤分解"""
        subtasks = []
        
        # 标准开发流程
        steps = [
            ("需求分析", TaskType.ANALYSIS, "analyze_requirements", 180, ["requirement_analysis"]),
            ("技术设计", TaskType.DESIGN, "design_solution", 240, ["system_design", "architecture"]),
            ("编码实现", TaskType.IMPLEMENTATION, "implement_code", 600, analysis["required_skills"]),
            ("单元测试", TaskType.TESTING, "run_unit_tests", 180, ["unit_testing"]),
            ("集成测试", TaskType.TESTING, "run_integration_tests", 240, ["integration_testing"]),
            ("部署上线", TaskType.DEPLOYMENT, "deploy_solution", 120, ["deployment"])
        ]
        
        prev_task_id = None
        for step_name, step_type, action, duration, skills in steps:
            dependencies = [(prev_task_id, DependencyType.STRONG)] if prev_task_id else []
            
            step_task = SubTask(
                task_id=f"sub_{uuid.uuid4().hex[:8]}",
                name=step_name,
                description=f"执行{step_name}: {task}",
                task_type=step_type,
                priority=TaskPriority.NORMAL if step_name != "编码实现" else TaskPriority.HIGH,
                assigned_agent=self.AGENT_CAPABILITIES.get(step_type, ["general_agent"])[0],
                dependencies=dependencies,
                required_skills=skills,
                estimated_duration=duration,
                metadata={"action": action}
            )
            subtasks.append(step_task)
            prev_task_id = step_task.task_id
        
        return subtasks
    
    async def _hybrid_decomposition(
        self,
        task: str,
        analysis: Dict[str, Any]
    ) -> List[SubTask]:
        """混合分解策略"""
        subtasks = []
        
        # 1. 快速分析
        quick_analysis = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="快速分析",
            description=f"快速分析任务需求: {task[:50]}...",
            task_type=TaskType.ANALYSIS,
            priority=TaskPriority.HIGH,
            estimated_duration=60
        )
        subtasks.append(quick_analysis)
        
        # 2. 并行调研
        research_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="背景调研",
            description="调研相关技术和最佳实践",
            task_type=TaskType.RESEARCH,
            priority=TaskPriority.NORMAL,
            dependencies=[(quick_analysis.task_id, DependencyType.STRONG)],
            estimated_duration=180
        )
        subtasks.append(research_task)
        
        # 3. 方案设计
        design_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="方案设计",
            description="设计实现方案",
            task_type=TaskType.DESIGN,
            priority=TaskPriority.HIGH,
            dependencies=[(research_task.task_id, DependencyType.STRONG)],
            assigned_agent="architect_agent",
            estimated_duration=180
        )
        subtasks.append(design_task)
        
        # 4. 实施
        impl_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="实施执行",
            description=f"执行任务: {task[:50]}...",
            task_type=TaskType.IMPLEMENTATION,
            priority=TaskPriority.CRITICAL,
            dependencies=[(design_task.task_id, DependencyType.STRONG)],
            estimated_duration=600
        )
        subtasks.append(impl_task)
        
        # 5. 验证
        verify_task = SubTask(
            task_id=f"sub_{uuid.uuid4().hex[:8]}",
            name="结果验证",
            description="验证实施结果",
            task_type=TaskType.TESTING,
            priority=TaskPriority.HIGH,
            dependencies=[(impl_task.task_id, DependencyType.STRONG)],
            estimated_duration=120
        )
        subtasks.append(verify_task)
        
        return subtasks
    
    def _build_dependency_graph(
        self,
        plan: ExecutionPlan,
        subtasks: List[SubTask],
        analysis: Dict[str, Any]
    ):
        """构建依赖图"""
        # 添加反向依赖关系
        for task in subtasks:
            for dep_id, _ in task.dependencies:
                dep_task = plan.tasks.get(dep_id)
                if dep_task:
                    dep_task.dependents.append(task.task_id)
    
    def _topological_sort(self, plan: ExecutionPlan) -> List[str]:
        """拓扑排序 - 计算执行顺序"""
        # Kahn算法
        in_degree = defaultdict(int)
        adj_list = defaultdict(list)
        
        # 初始化入度和邻接表
        for task_id, task in plan.tasks.items():
            in_degree[task_id] = 0
        
        for task_id, task in plan.tasks.items():
            for dep_id, dep_type in task.dependencies:
                if dep_type == DependencyType.STRONG:
                    adj_list[dep_id].append(task_id)
                    in_degree[task_id] += 1
        
        # BFS
        queue = []
        for task_id, degree in in_degree.items():
            if degree == 0:
                heapq.heappush(queue, (plan.tasks[task_id].priority.value, task_id))
        
        result = []
        while queue:
            _, task_id = heapq.heappop(queue)
            result.append(task_id)
            
            for neighbor in adj_list[task_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    heapq.heappush(queue, (plan.tasks[neighbor].priority.value, neighbor))
        
        return result
    
    def _identify_parallel_groups(self, plan: ExecutionPlan) -> List[List[str]]:
        """识别可并行执行的任务组"""
        parallel_groups = []
        
        # 构建依赖图
        dependents = defaultdict(list)
        for task_id, task in plan.tasks.items():
            for dep_id, _ in task.dependencies:
                dependents[dep_id].append(task_id)
        
        # 使用拓扑排序的层级
        visited = set()
        levels = defaultdict(list)
        
        def get_level(task_id: str) -> int:
            """计算任务层级"""
            if task_id in levels:
                return levels[task_id]
            
            task = plan.tasks[task_id]
            if not task.dependencies:
                levels[task_id] = 0
                return 0
            
            max_dep_level = 0
            for dep_id, dep_type in task.dependencies:
                if dep_type == DependencyType.STRONG:
                    max_dep_level = max(max_dep_level, get_level(dep_id) + 1)
            
            levels[task_id] = max_dep_level
            return max_dep_level
        
        # 计算每个任务的层级
        for task_id in plan.tasks:
            get_level(task_id)
        
        # 按层级分组
        level_tasks = defaultdict(list)
        for task_id, level in levels.items():
            level_tasks[level].append(task_id)
        
        # 转换为列表
        max_level = max(level_tasks.keys()) if level_tasks else 0
        for level in range(max_level + 1):
            if level in level_tasks:
                parallel_groups.append(sorted(level_tasks[level]))
        
        return parallel_groups
    
    def _calculate_critical_path(self, plan: ExecutionPlan) -> List[str]:
        """计算关键路径"""
        # 关键路径是从起点到终点的最长路径
        # 使用动态规划
        
        # 计算每个任务的最早完成时间
        earliest_finish = {}
        
        def calc_earliest(task_id: str) -> int:
            if task_id in earliest_finish:
                return earliest_finish[task_id]
            
            task = plan.tasks[task_id]
            if not task.dependencies:
                earliest_finish[task_id] = task.estimated_duration
                return earliest_finish[task_id]
            
            max_time = 0
            for dep_id, dep_type in task.dependencies:
                if dep_type == DependencyType.STRONG:
                    dep_finish = calc_earliest(dep_id)
                    max_time = max(max_time, dep_finish)
            
            earliest_finish[task_id] = max_time + task.estimated_duration
            return earliest_finish[task_id]
        
        for task_id in plan.tasks:
            calc_earliest(task_id)
        
        # 找到关键路径 - 从终点回溯
        if not earliest_finish:
            return []
        
        max_finish = max(earliest_finish.values())
        critical_path = []
        
        # 找到结束任务
        end_tasks = [t for t, f in earliest_finish.items() if f == max_finish]
        
        # 回溯
        current = end_tasks[0] if end_tasks else list(earliest_finish.keys())[0]
        visited = set()
        
        while current and current not in visited:
            visited.add(current)
            critical_path.insert(0, current)
            
            # 找到前置任务
            task = plan.tasks[current]
            prev_tasks = []
            for dep_id, dep_type in task.dependencies:
                if dep_type == DependencyType.STRONG and dep_id in earliest_finish:
                    prev_tasks.append((dep_id, earliest_finish[dep_id]))
            
            if prev_tasks:
                prev_tasks.sort(key=lambda x: x[1], reverse=True)
                current = prev_tasks[0][0]
            else:
                break
        
        return critical_path
    
    def _estimate_total_time(self, plan: ExecutionPlan) -> int:
        """估算总执行时间"""
        if not plan.critical_path:
            return sum(t.estimated_duration for t in plan.tasks.values())
        
        # 关键路径时间
        critical_time = sum(
            plan.tasks[task_id].estimated_duration
            for task_id in plan.critical_path
            if task_id in plan.tasks
        )
        
        return critical_time
    
    def _generate_plan_description(
        self,
        plan: ExecutionPlan,
        analysis: Dict[str, Any]
    ) -> str:
        """生成计划描述"""
        task_count = plan.total_tasks
        parallel_groups = len(plan.parallel_groups)
        critical_path_length = len(plan.critical_path)
        estimated_minutes = plan.estimated_total_time // 60
        
        description = f"""任务执行计划
==============

原始任务: {plan.original_task[:100]}...
任务类型: {analysis['task_type'].value}
复杂度: {analysis['complexity']}
所需技能: {', '.join(analysis['required_skills'][:5])}

计划概要:
- 总任务数: {task_count}
- 并行组数: {parallel_groups}
- 关键路径任务数: {critical_path_length}
- 预估耗时: {estimated_minutes}分钟

执行阶段:
"""
        
        for i, group in enumerate(plan.parallel_groups):
            group_desc = ", ".join([plan.tasks[t].name for t in group])
            description += f"{i+1}. 阶段{i+1}: {group_desc}\n"
        
        return description
    
    def get_execution_order(self, plan: ExecutionPlan) -> List[SubTask]:
        """获取可执行的下一个任务"""
        completed = {
            task_id for task_id, task in plan.tasks.items()
            if task.status == TaskStatus.COMPLETED
        }
        
        ready_tasks = plan.get_ready_tasks(completed)
        return ready_tasks
    
    def update_task_status(
        self,
        plan: ExecutionPlan,
        task_id: str,
        status: TaskStatus,
        result: Any = None,
        error: Optional[str] = None
    ):
        """更新任务状态"""
        task = plan.tasks.get(task_id)
        if not task:
            return
        
        task.status = status
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now().isoformat()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            task.completed_at = datetime.now().isoformat()
            if result is not None:
                task.result = result
            if error:
                task.error = error


# 导出
__all__ = [
    "TaskDecompositionEngine",
    "ExecutionPlan",
    "SubTask",
    "TaskType",
    "TaskPriority",
    "TaskStatus",
    "DependencyType",
    "TaskInput",
    "TaskOutput"
]
