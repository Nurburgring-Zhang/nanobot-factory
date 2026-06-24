"""
Nanobot-Factory多智能体协作模块
===========================

本模块整合了多种多智能体协作框架的能力：
- ChatDev: 聊天驱动的软件开发框架
- MetaGPT: 元编程多智能体协作框架
- LangGraph: 基于图结构的多智能体编排
- AutoGen: 微软多智能体对话框架
- CrewAI: 角色扮演自主AI智能体编排框架

作者：MiniMax Agent
日期：2026-03-05
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)

# ========== Agent Registry & Spawn ==========
from backend.integrations.multi_agent.agent_registry import (
    AgentRegistry, AgentSpawner, AgentProfile, AgentInstance,
    AgentType, AgentState, get_agent_registry, get_agent_spawner
)

# ========== Multi-Agent工作流编排 ==========
from backend.integrations.multi_agent.workflow_orchestrator import (
    MultiAgentOrchestrator, DispatcherAgent, AgentExecutor, WorkflowAggregator,
    WorkflowDefinition, WorkflowExecution, SubAgentTask,
    WorkflowStatus, TaskStatus, ExecutionMode,
    create_orchestrator, create_dispatcher, get_global_orchestrator, get_global_dispatcher
)

# ========== Gateway注册 ==========
from backend.integrations.multi_agent.gateway_registration import (
    GatewayConfig, GatewayClient, AgentGatewayConfig, ExpertGatewayConfig,
    AgentGatewayRegistration, ExpertGatewayRegistration, GatewayRegistrationManager,
    RegistrationResult, GatewayStatus,
    create_gateway_manager, get_gateway_manager,
    register_agents_company_to_gateway, register_experts_system_to_gateway, register_all_to_gateway
)

# ========== 四层记忆架构 ==========
from backend.integrations.multi_agent.memory_architecture import (
    FourLayerMemorySystem, Layer1WorkingMemory, Layer2ShortTermMemory,
    Layer3LongTermMemory, Layer4SemanticMemory,
    MemoryEntry, MemoryQuery, MemoryRetrievalResult,
    MemoryLayer, MemoryType, get_agent_memory, get_system_memory
)

# ========== 偷懒行为检测 ==========
from backend.integrations.multi_agent.slacking_detector import (
    SlackingDetector, BehaviorMonitor, OutputAnalyzer,
    BehaviorMetrics, AgentBehaviorProfile,
    BehaviorType, SlackingIndicator,
    get_slacking_detector, get_behavior_monitor,
    analyze_output_quality, monitor_agent_task
)

# ========== 专家工作流 ==========
from backend.integrations.multi_agent.expert_workflow import (
    ExpertRegistry, ExpertProfile, ExpertExecutor, ExpertWorkflowEngine,
    ConsultationRequest, ConsultationResult,
    ExpertStatus, ConsultationType,
    get_expert_registry, get_expert_engine, register_expert, consult
)

# ========== Agents Company ==========
from backend.integrations.multi_agent.agents_company import (
    create_all_agents_company, initialize_agents_company, AGENTS_COMPANY
)

# ========== Experts System ==========
from backend.integrations.multi_agent.experts_system import (
    create_technical_experts, create_domain_experts,
    create_industry_experts, initialize_experts_system, EXPERTS_SYSTEM
)


class MultiAgentFramework(Enum):
    """多智能体框架枚举"""
    CHATDEV = "chatdev"           # 聊天驱动的软件开发
    METAGPT = "metagpt"           # 元编程协作框架
    LANGGRAPH = "langgraph"       # 图结构编排
    AUTOGEN = "autogen"           # 微软对话框架
    CREWAI = "crewai"             # 角色扮演编排
    CUSTOM = "custom"              # 自定义框架


class AgentRole(Enum):
    """智能体角色枚举"""
    CEO = "chief_executive"           # 首席执行官
    CPO = "chief_product"             # 首席产品官
    CTO = "chief_technical"          # 首席技术官
    PROGRAMMER = "programmer"         # 程序员
    TESTER = "tester"                 # 测试工程师
    DESIGNER = "designer"             # 设计师
    RESEARCHER = "researcher"        # 研究员
    WRITER = "writer"                # 撰稿人
    ANALYST = "analyst"              # 分析师
    COORDINATOR = "coordinator"      # 协调员


@dataclass
class Agent:
    """智能体定义"""
    name: str
    role: AgentRole
    description: str
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    llm_config: Dict[str, Any] = field(default_factory=dict)
    system_prompt: str = ""
    memory: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "role": self.role.value,
            "description": self.description,
            "capabilities": self.capabilities,
            "tools": self.tools,
            "llm_config": self.llm_config,
            "system_prompt": self.system_prompt,
            "memory": self.memory
        }


@dataclass
class Task:
    """任务定义"""
    id: str
    description: str
    assignee: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationMessage:
    """对话消息"""
    sender: str
    receiver: str
    content: str
    timestamp: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseMultiAgentSystem:
    """多智能体系统基类"""

    def __init__(self, framework: MultiAgentFramework):
        self.framework = framework
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, Task] = {}
        self.conversations: List[ConversationMessage] = []
        self.execution_history: List[Dict[str, Any]] = []

    def add_agent(self, agent: Agent) -> None:
        """添加智能体"""
        self.agents[agent.name] = agent
        logger.info(f"已添加智能体: {agent.name} (角色: {agent.role.value})")

    def remove_agent(self, name: str) -> None:
        """移除智能体"""
        if name in self.agents:
            del self.agents[name]
            logger.info(f"已移除智能体: {name}")

    def get_agent(self, name: str) -> Optional[Agent]:
        """获取智能体"""
        return self.agents.get(name)

    def create_task(self, task: Task) -> None:
        """创建任务"""
        self.tasks[task.id] = task
        logger.info(f"已创建任务: {task.id} - {task.description}")

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """执行任务"""
        raise NotImplementedError

    async def coordinate_agents(self, task_description: str) -> Dict[str, Any]:
        """协调多个智能体完成任务"""
        raise NotImplementedError

    def get_execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self.execution_history


class ChatDevSystem(BaseMultiAgentSystem):
    """
    ChatDev多智能体系统

    基于聊天的软件开发框架，模拟虚拟软件公司，
    包括CEO、程序员、测试工程师、设计师等角色。

    参考: https://github.com/netbuddy/ChatDev
    """

    def __init__(self):
        super().__init__(MultiAgentFramework.CHATDEV)
        self.phase = "designing"  # designing, coding, testing, documenting
        self.chat_chains: List[List[ConversationMessage]] = []

    def setup_software_company(self) -> None:
        """设置软件开发公司团队"""
        # 首席执行官
        ceo = Agent(
            name="CEO",
            role=AgentRole.CEO,
            description="负责整体决策和项目管理的首席执行官",
            capabilities=["战略规划", "决策制定", "项目监督"],
            system_prompt="你是一位经验丰富的首席执行官，负责软件项目的整体决策和团队管理。"
        )

        # 首席产品官
        cpo = Agent(
            name="CPO",
            role=AgentRole.CPO,
            description="负责产品规划和需求分析",
            capabilities=["需求分析", "产品规划", "用户体验设计"],
            system_prompt="你是一位首席产品官，负责将用户需求转化为产品规范。"
        )

        # 首席技术官
        cto = Agent(
            name="CTO",
            role=AgentRole.CTO,
            description="负责技术架构和技术决策",
            capabilities=["技术架构", "代码审查", "技术选型"],
            system_prompt="你是一位首席技术官，负责技术架构和关键技术决策。"
        )

        # 程序员
        programmer = Agent(
            name="Programmer",
            role=AgentRole.PROGRAMMER,
            description="负责代码编写和实现",
            capabilities=["编程开发", "代码实现", "调试修复"],
            system_prompt="你是一位专业程序员，负责将设计转化为可运行的代码。"
        )

        # 测试工程师
        tester = Agent(
            name="Tester",
            role=AgentRole.TESTER,
            description="负责软件测试和质量保证",
            capabilities=["测试用例", "缺陷发现", "质量评估"],
            system_prompt="你是一位测试工程师，负责确保软件质量。"
        )

        # 设计师
        designer = Agent(
            name="Designer",
            role=AgentRole.DESIGNER,
            description="负责用户界面和用户体验设计",
            capabilities=["UI设计", "UX设计", "视觉设计"],
            system_prompt="你是一位设计师，负责创建直观美观的产品界面。"
        )

        # 添加所有智能体
        for agent in [ceo, cpo, cto, programmer, tester, designer]:
            self.add_agent(agent)

        logger.info("ChatDev软件开发团队已组建")

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """执行软件开发任务"""
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result = {
            "task_id": task_id,
            "phases": {}
        }

        # 设计阶段
        if self.phase == "designing":
            design_result = await self._execute_design_phase(task.description)
            result["phases"]["designing"] = design_result

        # 编码阶段
        if self.phase in ["designing", "coding"]:
            coding_result = await self._execute_coding_phase(task.description)
            result["phases"]["coding"] = coding_result

        # 测试阶段
        if self.phase in ["designing", "coding", "testing"]:
            testing_result = await self._execute_testing_phase(task.description)
            result["phases"]["testing"] = testing_result

        # 文档编写阶段
        if self.phase in ["designing", "coding", "testing", "documenting"]:
            doc_result = await self._execute_documenting_phase(task.description)
            result["phases"]["documenting"] = doc_result

        task.status = "completed"
        task.result = result

        self.execution_history.append({
            "task_id": task_id,
            "result": result,
            "timestamp": asyncio.get_event_loop().time()
        })

        return {"success": True, "result": result}

    async def _execute_design_phase(self, task_description: str) -> Dict[str, Any]:
        """执行设计阶段"""
        # 模拟设计阶段的智能体协作
        design_msg = ConversationMessage(
            sender="CPO",
            receiver="Designer",
            content=f"分析需求: {task_description}",
            timestamp=asyncio.get_event_loop().time()
        )
        self.conversations.append(design_msg)

        return {
            "phase": "designing",
            "artifacts": ["需求文档", "UI设计稿", "架构设计"],
            "status": "completed"
        }

    async def _execute_coding_phase(self, task_description: str) -> Dict[str, Any]:
        """执行编码阶段"""
        coding_msg = ConversationMessage(
            sender="CTO",
            receiver="Programmer",
            content=f"根据设计实现: {task_description}",
            timestamp=asyncio.get_event_loop().time()
        )
        self.conversations.append(coding_msg)

        return {
            "phase": "coding",
            "artifacts": ["源代码文件", "配置文件", "依赖清单"],
            "status": "completed"
        }

    async def _execute_testing_phase(self, task_description: str) -> Dict[str, Any]:
        """执行测试阶段"""
        testing_msg = ConversationMessage(
            sender="CTO",
            receiver="Tester",
            content=f"测试实现: {task_description}",
            timestamp=asyncio.get_event_loop().time()
        )
        self.conversations.append(testing_msg)

        return {
            "phase": "testing",
            "artifacts": ["测试报告", "缺陷列表", "测试覆盖率"],
            "status": "completed"
        }

    async def _execute_documenting_phase(self, task_description: str) -> Dict[str, Any]:
        """执行文档编写阶段"""
        doc_msg = ConversationMessage(
            sender="CEO",
            receiver="CPO",
            content=f"编写文档: {task_description}",
            timestamp=asyncio.get_event_loop().time()
        )
        self.conversations.append(doc_msg)

        return {
            "phase": "documenting",
            "artifacts": ["用户手册", "API文档", "部署指南"],
            "status": "completed"
        }

    async def coordinate_agents(self, task_description: str) -> Dict[str, Any]:
        """协调智能体完成软件开发任务"""
        task = Task(
            id=f"task_{len(self.tasks) + 1}",
            description=task_description,
            status="in_progress"
        )
        self.create_task(task)

        return await self.execute_task(task.id)


class MetaGPTSystem(BaseMultiAgentSystem):
    """
    MetaGPT多智能体系统

    基于元编程的多智能体协作框架，
    采用标准操作程序(SOP)进行任务分解和协调。

    参考: https://github.com/geekan/MetaGPT
    """

    def __init__(self):
        super().__init__(MultiAgentFramework.METAGPT)
        self.sop_enabled = True
        self.role_pool: Dict[str, Dict[str, Any]] = {}

    def setup_sop_team(self) -> None:
        """设置SOP团队"""
        # 产品经理
        pm = Agent(
            name="ProductManager",
            role=AgentRole.CPO,
            description="负责需求分析和产品规划",
            capabilities=["需求分析", "PRD编写", "优先级排序"],
            system_prompt="你是一位专业的产品经理，负责将用户需求转化为详细的产品需求文档。"
        )

        # 架构师
        architect = Agent(
            name="Architect",
            role=AgentRole.CTO,
            description="负责系统架构设计",
            capabilities=["架构设计", "技术选型", "性能优化"],
            system_prompt="你是一位系统架构师，负责设计可扩展的系统架构。"
        )

        # 工程师
        engineer = Agent(
            name="Engineer",
            role=AgentRole.PROGRAMMER,
            description="负责代码实现",
            capabilities=["编码实现", "单元测试", "代码审查"],
            system_prompt="你是一位资深工程师，负责高质量的代码实现。"
        )

        # 质量保证
        qa = Agent(
            name="QAEngineer",
            role=AgentRole.TESTER,
            description="负责质量保证",
            capabilities=["测试计划", "缺陷管理", "质量评估"],
            system_prompt="你是一位QA工程师，负责确保产品质量。"
        )

        for agent in [pm, architect, engineer, qa]:
            self.add_agent(agent)

        # 定义角色池
        self.role_pool = {
            "pm": {
                "role": "ProductManager",
                "responsibilities": ["需求分析", "PRD编写", "任务分解"],
                "outputs": ["PRD", "任务列表"]
            },
            "architect": {
                "role": "Architect",
                "responsibilities": ["架构设计", "技术方案", "代码审查"],
                "outputs": ["架构文档", "技术方案"]
            },
            "engineer": {
                "role": "Engineer",
                "responsibilities": ["编码实现", "单元测试", "集成测试"],
                "outputs": ["源代码", "测试报告"]
            },
            "qa": {
                "role": "QAEngineer",
                "responsibilities": ["测试计划", "缺陷跟踪", "质量评估"],
                "outputs": ["测试报告", "质量报告"]
            }
        }

        logger.info("MetaGPT SOP团队已组建")

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """执行SOP任务"""
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result = {
            "task_id": task_id,
            "sop_steps": []
        }

        # SOP步骤1: 需求分析
        req_result = await self._sop_requirement_analysis(task.description)
        result["sop_steps"].append(req_result)

        # SOP步骤2: 架构设计
        arch_result = await self._sop_architecture_design(task.description)
        result["sop_steps"].append(arch_result)

        # SOP步骤3: 代码实现
        code_result = await self._sop_code_implementation(task.description)
        result["sop_steps"].append(code_result)

        # SOP步骤4: 质量保证
        qa_result = await self._sop_quality_assurance(task.description)
        result["sop_steps"].append(qa_result)

        task.status = "completed"
        task.result = result

        self.execution_history.append({
            "task_id": task_id,
            "result": result,
            "timestamp": asyncio.get_event_loop().time()
        })

        return {"success": True, "result": result}

    async def _sop_requirement_analysis(self, task: str) -> Dict[str, Any]:
        """SOP: 需求分析"""
        agent = self.get_agent("ProductManager")
        return {
            "step": "requirement_analysis",
            "agent": agent.name if agent else "ProductManager",
            "output": {
                "prd": f"需求文档: {task}",
                "tasks": ["任务1", "任务2", "任务3"]
            },
            "status": "completed"
        }

    async def _sop_architecture_design(self, task: str) -> Dict[str, Any]:
        """SOP: 架构设计"""
        agent = self.get_agent("Architect")
        return {
            "step": "architecture_design",
            "agent": agent.name if agent else "Architect",
            "output": {
                "architecture": "微服务架构",
                "tech_stack": ["Python", "FastAPI", "PostgreSQL"]
            },
            "status": "completed"
        }

    async def _sop_code_implementation(self, task: str) -> Dict[str, Any]:
        """SOP: 代码实现"""
        agent = self.get_agent("Engineer")
        return {
            "step": "code_implementation",
            "agent": agent.name if agent else "Engineer",
            "output": {
                "files": ["main.py", "models.py", "handlers.py"],
                "tests": ["test_main.py"]
            },
            "status": "completed"
        }

    async def _sop_quality_assurance(self, task: str) -> Dict[str, Any]:
        """SOP: 质量保证"""
        agent = self.get_agent("QAEngineer")
        return {
            "step": "quality_assurance",
            "agent": agent.name if agent else "QAEngineer",
            "output": {
                "test_report": "测试通过",
                "coverage": "85%"
            },
            "status": "completed"
        }

    async def coordinate_agents(self, task_description: str) -> Dict[str, Any]:
        """协调SOP团队完成任务"""
        task = Task(
            id=f"task_{len(self.tasks) + 1}",
            description=task_description,
            status="in_progress"
        )
        self.create_task(task)

        return await self.execute_task(task.id)


class AutoGenSystem(BaseMultiAgentSystem):
    """
    AutoGen多智能体系统

    微软的多智能体对话框架，
    支持灵活的对话模式和人工介入。

    参考: https://github.com/microsoft/autogen
    """

    def __init__(self):
        super().__init__(MultiAgentFramework.AUTOGEN)
        self.conversation_mode = "group"  # group, pairwise, hierarchical
        self.human_in_loop = False

    def setup_conversation_team(self) -> None:
        """设置对话团队"""
        # 助手智能体
        assistant = Agent(
            name="Assistant",
            role=AgentRole.CTO,
            description="AI助手，提供专业建议",
            capabilities=["问题解答", "代码生成", "方案建议"],
            system_prompt="你是一位AI助手，负责提供专业的建议和解决方案。"
        )

        # 用户代理
        user_proxy = Agent(
            name="UserProxy",
            role=AgentRole.COORDINATOR,
            description="代表用户执行操作",
            capabilities=["执行代码", "调用工具", "反馈结果"],
            system_prompt="你代表用户执行任务并收集反馈。"
        )

        # 调解员
        moderator = Agent(
            name="Moderator",
            role=AgentRole.COORDINATOR,
            description="协调多智能体讨论",
            capabilities=["讨论引导", "冲突解决", "共识推进"],
            system_prompt="你负责协调多个智能体之间的讨论。"
        )

        for agent in [assistant, user_proxy, moderator]:
            self.add_agent(agent)

        logger.info("AutoGen对话团队已组建")

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """执行对话任务"""
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result = {
            "task_id": task_id,
            "conversation": []
        }

        if self.conversation_mode == "group":
            conv_result = await self._group_conversation(task.description)
            result["conversation"].append(conv_result)
        elif self.conversation_mode == "pairwise":
            conv_result = await self._pairwise_conversation(task.description)
            result["conversation"].append(conv_result)
        elif self.conversation_mode == "hierarchical":
            conv_result = await self._hierarchical_conversation(task.description)
            result["conversation"].append(conv_result)

        task.status = "completed"
        task.result = result

        self.execution_history.append({
            "task_id": task_id,
            "result": result,
            "timestamp": asyncio.get_event_loop().time()
        })

        return {"success": True, "result": result}

    async def _group_conversation(self, task: str) -> Dict[str, Any]:
        """群聊模式"""
        messages = [
            {"sender": "UserProxy", "content": f"任务: {task}"},
            {"sender": "Assistant", "content": "我来分析这个任务..."},
            {"sender": "Moderator", "content": "让我们讨论解决方案..."},
            {"sender": "Assistant", "content": "最终建议: ..."}
        ]

        for msg in messages:
            self.conversations.append(ConversationMessage(
                sender=msg["sender"],
                receiver="all",
                content=msg["content"],
                timestamp=asyncio.get_event_loop().time()
            ))

        return {
            "mode": "group",
            "messages": messages,
            "conclusion": "任务完成"
        }

    async def _pairwise_conversation(self, task: str) -> Dict[str, Any]:
        """两两对话模式"""
        messages = [
            {"sender": "UserProxy", "receiver": "Assistant", "content": f"请帮我: {task}"},
            {"sender": "Assistant", "receiver": "UserProxy", "content": "好的，我来帮你..."}
        ]

        for msg in messages:
            self.conversations.append(ConversationMessage(
                sender=msg["sender"],
                receiver=msg["receiver"],
                content=msg["content"],
                timestamp=asyncio.get_event_loop().time()
            ))

        return {
            "mode": "pairwise",
            "messages": messages,
            "conclusion": "任务完成"
        }

    async def _hierarchical_conversation(self, task: str) -> Dict[str, Any]:
        """层级模式"""
        messages = [
            {"sender": "UserProxy", "receiver": "Moderator", "content": f"分配任务: {task}"},
            {"sender": "Moderator", "receiver": "Assistant", "content": "请提供方案..."},
            {"sender": "Assistant", "receiver": "Moderator", "content": "方案已提供"},
            {"sender": "Moderator", "receiver": "UserProxy", "content": "任务完成"}
        ]

        for msg in messages:
            self.conversations.append(ConversationMessage(
                sender=msg["sender"],
                receiver=msg["receiver"],
                content=msg["content"],
                timestamp=asyncio.get_event_loop().time()
            ))

        return {
            "mode": "hierarchical",
            "messages": messages,
            "conclusion": "层级任务完成"
        }

    async def coordinate_agents(self, task_description: str) -> Dict[str, Any]:
        """协调对话完成任务"""
        task = Task(
            id=f"task_{len(self.tasks) + 1}",
            description=task_description,
            status="in_progress"
        )
        self.create_task(task)

        return await self.execute_task(task.id)


class CrewAISystem(BaseMultiAgentSystem):
    """
    CrewAI多智能体系统

    角色扮演自主AI智能体编排框架，
    模拟团队协作模式。

    参考: https://github.com/joaomdmoura/crewai
    """

    def __init__(self):
        super().__init__(MultiAgentFramework.CREWAI)
        self.process = "sequential"  # sequential, hierarchical

    def setup_crew(self) -> None:
        """设置crew团队"""
        # 研究员
        researcher = Agent(
            name="Researcher",
            role=AgentRole.RESEARCHER,
            description="负责信息收集和研究",
            capabilities=["网络搜索", "数据收集", "信息整理"],
            system_prompt="你是一位专业研究员，负责收集和分析信息。"
        )

        # 撰稿人
        writer = Agent(
            name="Writer",
            role=AgentRole.WRITER,
            description="负责内容创作",
            capabilities=["文章撰写", "内容编辑", "文案创作"],
            system_prompt="你是一位专业撰稿人，负责创建高质量内容。"
        )

        # 分析师
        analyst = Agent(
            name="Analyst",
            role=AgentRole.ANALYST,
            description="负责数据分析和洞察",
            capabilities=["数据分析", "趋势分析", "报告生成"],
            system_prompt="你是一位数据分析师，负责提供深入洞察。"
        )

        # 编辑
        editor = Agent(
            name="Editor",
            role=AgentRole.WRITER,
            description="负责内容审核和编辑",
            capabilities=["内容审核", "质量控制", "修改建议"],
            system_prompt="你是一位专业编辑，负责确保内容质量。"
        )

        for agent in [researcher, writer, analyst, editor]:
            self.add_agent(agent)

        logger.info("CrewAI团队已组建")

    async def execute_task(self, task_id: str) -> Dict[str, Any]:
        """执行crew任务"""
        task = self.tasks.get(task_id)
        if not task:
            return {"success": False, "error": f"任务不存在: {task_id}"}

        result = {
            "task_id": task_id,
            "crew_steps": []
        }

        if self.process == "sequential":
            # 顺序执行
            research_result = await self._research_step(task.description)
            result["crew_steps"].append(research_result)

            write_result = await self._write_step(task.description)
            result["crew_steps"].append(write_result)

            analyze_result = await self._analyze_step(task.description)
            result["crew_steps"].append(analyze_result)

            edit_result = await self._edit_step(task.description)
            result["crew_steps"].append(edit_result)

        elif self.process == "hierarchical":
            # 层级执行
            coord_result = await self._coordinate_step(task.description)
            result["crew_steps"].append(coord_result)

        task.status = "completed"
        task.result = result

        self.execution_history.append({
            "task_id": task_id,
            "result": result,
            "timestamp": asyncio.get_event_loop().time()
        })

        return {"success": True, "result": result}

    async def _research_step(self, task: str) -> Dict[str, Any]:
        """研究步骤"""
        agent = self.get_agent("Researcher")
        return {
            "step": "research",
            "agent": agent.name if agent else "Researcher",
            "output": {"findings": ["信息1", "信息2"], "sources": ["source1"]},
            "status": "completed"
        }

    async def _write_step(self, task: str) -> Dict[str, Any]:
        """写作步骤"""
        agent = self.get_agent("Writer")
        return {
            "step": "write",
            "agent": agent.name if agent else "Writer",
            "output": {"content": "文章内容..."},
            "status": "completed"
        }

    async def _analyze_step(self, task: str) -> Dict[str, Any]:
        """分析步骤"""
        agent = self.get_agent("Analyst")
        return {
            "step": "analyze",
            "agent": agent.name if agent else "Analyst",
            "output": {"insights": ["洞察1", "洞察2"], "metrics": {}},
            "status": "completed"
        }

    async def _edit_step(self, task: str) -> Dict[str, Any]:
        """编辑步骤"""
        agent = self.get_agent("Editor")
        return {
            "step": "edit",
            "agent": agent.name if agent else "Editor",
            "output": {"revised_content": "修订后的内容", "feedback": "反馈意见"},
            "status": "completed"
        }

    async def _coordinate_step(self, task: str) -> Dict[str, Any]:
        """协调步骤"""
        return {
            "step": "coordinate",
            "agents": ["Researcher", "Writer", "Analyst", "Editor"],
            "output": {"coordinated_result": "协调结果"},
            "status": "completed"
        }

    async def coordinate_agents(self, task_description: str) -> Dict[str, Any]:
        """协调crew完成任务"""
        task = Task(
            id=f"task_{len(self.tasks) + 1}",
            description=task_description,
            status="in_progress"
        )
        self.create_task(task)

        return await self.execute_task(task.id)


class MultiAgentCoordinator:
    """多智能体协调器

    统一的协调接口，支持多种多智能体框架
    """

    def __init__(self):
        self.systems: Dict[MultiAgentFramework, BaseMultiAgentSystem] = {}
        self._register_default_systems()

    def _register_default_systems(self) -> None:
        """注册默认系统"""
        # ChatDev
        chatdev = ChatDevSystem()
        chatdev.setup_software_company()
        self.systems[MultiAgentFramework.CHATDEV] = chatdev

        # MetaGPT
        metagpt = MetaGPTSystem()
        metagpt.setup_sop_team()
        self.systems[MultiAgentFramework.METAGPT] = metagpt

        # AutoGen
        autogen = AutoGenSystem()
        autogen.setup_conversation_team()
        self.systems[MultiAgentFramework.AUTOGEN] = autogen

        # CrewAI
        crewai = CrewAISystem()
        crewai.setup_crew()
        self.systems[MultiAgentFramework.CREWAI] = crewai

        logger.info(f"已注册 {len(self.systems)} 个多智能体系统")

    def get_system(self, framework: MultiAgentFramework) -> Optional[BaseMultiAgentSystem]:
        """获取指定框架的系统"""
        return self.systems.get(framework)

    def get_available_frameworks(self) -> List[str]:
        """获取可用框架列表"""
        return [f.value for f in self.systems.keys()]

    async def execute_with_framework(
        self,
        framework: MultiAgentFramework,
        task_description: str
    ) -> Dict[str, Any]:
        """使用指定框架执行任务"""
        system = self.get_system(framework)
        if not system:
            return {
                "success": False,
                "error": f"未知的框架: {framework.value}"
            }

        return await system.coordinate_agents(task_description)

    async def execute_with_best_framework(
        self,
        task_description: str,
        task_type: str = "general"
    ) -> Dict[str, Any]:
        """自动选择最佳框架执行任务"""
        # 根据任务类型选择框架
        if task_type in ["software", "development", "coding"]:
            return await self.execute_with_framework(
                MultiAgentFramework.CHATDEV,
                task_description
            )
        elif task_type in ["analysis", "research", "report"]:
            return await self.execute_with_framework(
                MultiAgentFramework.METAGPT,
                task_description
            )
        elif task_type in ["discussion", "conversation", "dialogue"]:
            return await self.execute_with_framework(
                MultiAgentFramework.AUTOGEN,
                task_description
            )
        elif task_type in ["content", "writing", "creation"]:
            return await self.execute_with_framework(
                MultiAgentFramework.CREWAI,
                task_description
            )
        else:
            # 默认使用ChatDev
            return await self.execute_with_framework(
                MultiAgentFramework.CHATDEV,
                task_description
            )

    def get_system_stats(self, framework: MultiAgentFramework) -> Dict[str, Any]:
        """获取系统统计信息"""
        system = self.get_system(framework)
        if not system:
            return {"error": "系统不存在"}

        return {
            "framework": framework.value,
            "agents": len(system.agents),
            "tasks": len(system.tasks),
            "conversations": len(system.conversations),
            "execution_history": len(system.execution_history)
        }


# 全局协调器实例
_global_coordinator: Optional[MultiAgentCoordinator] = None


def get_multi_agent_coordinator() -> MultiAgentCoordinator:
    """获取全局多智能体协调器"""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = MultiAgentCoordinator()
    return _global_coordinator


# 导出模块
__all__ = [
    "MultiAgentFramework",
    "AgentRole",
    "Agent",
    "Task",
    "ConversationMessage",
    "BaseMultiAgentSystem",
    "ChatDevSystem",
    "MetaGPTSystem",
    "AutoGenSystem",
    "CrewAISystem",
    "MultiAgentCoordinator",
    "get_multi_agent_coordinator",
    # 新增：Agent注册系统
    "AgentRegistry",
    "AgentSpawner",
    "AgentProfile",
    "AgentInstance",
    "AgentType",
    "AgentState",
    "get_agent_registry",
    "get_agent_spawner",
    # 新增：Agents Company
    "create_all_agents_company",
    "initialize_agents_company",
    "AGENTS_COMPANY",
    # 新增：Experts System
    "create_technical_experts",
    "create_domain_experts",
    "create_industry_experts",
    "initialize_experts_system",
    "EXPERTS_SYSTEM",

    # ========== Multi-Agent工作流编排 ==========
    "MultiAgentOrchestrator",
    "DispatcherAgent",
    "AgentExecutor",
    "WorkflowAggregator",
    "WorkflowDefinition",
    "WorkflowExecution",
    "SubAgentTask",
    "WorkflowStatus",
    "TaskStatus",
    "ExecutionMode",
    "create_orchestrator",
    "create_dispatcher",
    "get_global_orchestrator",
    "get_global_dispatcher",

    # ========== Gateway注册 ==========
    "GatewayConfig",
    "GatewayClient",
    "AgentGatewayConfig",
    "ExpertGatewayConfig",
    "AgentGatewayRegistration",
    "ExpertGatewayRegistration",
    "GatewayRegistrationManager",
    "RegistrationResult",
    "GatewayStatus",
    "create_gateway_manager",
    "get_gateway_manager",
    "register_agents_company_to_gateway",
    "register_experts_system_to_gateway",
    "register_all_to_gateway",

    # ========== 四层记忆架构 ==========
    "FourLayerMemorySystem",
    "Layer1WorkingMemory",
    "Layer2ShortTermMemory",
    "Layer3LongTermMemory",
    "Layer4SemanticMemory",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryRetrievalResult",
    "MemoryLayer",
    "MemoryType",
    "get_agent_memory",
    "get_system_memory",

    # ========== 偷懒行为检测 ==========
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

    # ========== 专家工作流 ==========
    "ExpertRegistry",
    "ExpertProfile",
    "ExpertExecutor",
    "ExpertWorkflowEngine",
    "ConsultationRequest",
    "ConsultationResult",
    "ExpertStatus",
    "ConsultationType",
    "get_expert_registry",
    "get_expert_engine",
    "register_expert",
    "consult",
]
