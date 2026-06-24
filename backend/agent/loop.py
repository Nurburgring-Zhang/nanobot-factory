#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Agent Loop Engine
Agent循环引擎 - 实现ReAct推理循环、虚拟工具调用、会话管理

核心功能：
- ReAct循环实现（观察→推理→行动）
- 虚拟工具支持（结构化输出）
- 会话状态管理
- 执行追踪与日志
- 错误处理与恢复
- 并发会话支持

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import json
import re
import time
import ast
import operator
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import uuid

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    """
    Agent状态 - 完整20+状态机
    
    状态说明：
    - 基础状态：IDLE, INITIALIZING, RUNNING, PAUSED, STOPPED, COMPLETED, ERROR
    - 执行状态：THINKING, REASONING, PLANNING, EXECUTING, VALIDATING
    - 工具状态：TOOL_CALLING, TOOL_EXECUTING, TOOL_WAITING, TOOL_COMPLETED
    - 交互状态：WAITING_USER, WAITING_TOOL, WAITING_API, WAITING_GENERATION
    - 特殊状态：SUSPENDED, RETRYING, CANCELLING, TIMEOUT
    - 协作状态：MULTI_AGENT_COORDINATING, CONSENSUS_BUILDING
    """
    # ===== 基础状态 =====
    IDLE = "idle"                           # 空闲/初始状态
    INITIALIZING = "initializing"           # 初始化中
    RUNNING = "running"                     # 运行中
    PAUSED = "paused"                       # 已暂停
    STOPPED = "stopped"                     # 已停止
    COMPLETED = "completed"                  # 已完成
    ERROR = "error"                         # 错误状态
    
    # ===== 执行状态 =====
    THINKING = "thinking"                   # 思考中
    REASONING = "reasoning"                  # 推理中
    PLANNING = "planning"                    # 规划中
    EXECUTING = "executing"                  # 执行中
    VALIDATING = "validating"                # 验证中
    
    # ===== 工具状态 =====
    TOOL_CALLING = "tool_calling"           # 工具调用中
    TOOL_EXECUTING = "tool_executing"       # 工具执行中
    TOOL_WAITING = "tool_waiting"          # 等待工具响应
    TOOL_COMPLETED = "tool_completed"       # 工具执行完成
    
    # ===== 交互状态 =====
    WAITING_USER = "waiting_user"           # 等待用户输入
    WAITING_TOOL = "waiting_tool"            # 等待工具
    WAITING_API = "waiting_api"              # 等待API响应
    WAITING_GENERATION = "waiting_generation" # 等待生成完成
    
    # ===== 特殊状态 =====
    SUSPENDED = "suspended"                 # 已挂起
    RETRYING = "retrying"                   # 重试中
    CANCELLING = "cancelling"               # 取消中
    TIMEOUT = "timeout"                     # 超时
    
    # ===== 协作状态 =====
    MULTI_AGENT_COORDINATING = "multi_agent_coordinating" # 多Agent协调中
    CONSENSUS_BUILDING = "consensus_building" # 共识构建中
    
    # ===== 质量控制状态 =====
    QUALITY_CHECKING = "quality_checking"   # 质量检查中
    SELF_CORRECTING = "self_correcting"    # 自我修正中
    ITERATING = "iterating"                # 迭代中


class ActionType(Enum):
    """行动类型"""
    CONTINUE = "continue"           # 继续推理
    RESPOND = "respond"             # 直接回复
    TOOL_CALL = "tool_call"        # 调用工具
    FINISH = "finish"              # 完成
    ERROR = "error"                # 错误


@dataclass
class Thought:
    """思考步骤"""
    step: int
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ToolCall:
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None


@dataclass
class AgentSession:
    """Agent会话"""
    id: str
    user_id: str
    agent_type: str
    status: AgentStatus
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    thoughts: List[Thought] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)


class VirtualTool(ABC):
    """
    虚拟工具抽象基类

    所有Agent可用的工具必须继承此类
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        执行工具

        Args:
            **kwargs: 工具参数

        Returns:
            工具执行结果
        """
        pass

    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具的JSON Schema

        Returns:
            工具参数schema
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self._get_parameters_schema()
        }

    @abstractmethod
    def _get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数schema"""
        pass


class ReActPromptBuilder:
    """
    ReAct提示词构建器

    构建符合ReAct模式的提示词
    """

    def __init__(self):
        self.template = """你是一个智能助手，可以使用工具来帮助用户完成任务。

你可以使用以下工具：
{tool_definitions}

让我们一步步思考。每个思考步骤后，你可能需要调用工具来获取更多信息。

历史对话：
{history}

当前问题：{question}

请按以下格式输出你的思考和行动：

思考 {step}: {thought}
行动: {action_name}
行动输入: {action_input}
观察: {observation}

注意：
- 如果需要使用工具，必须按照上述格式明确指定工具名称和参数
- 如果已经获得足够信息回答问题，请直接输出答案
- 使用JSON格式提供行动输入
"""

    def build(
        self,
        question: str,
        tools: List[VirtualTool],
        history: List[Dict[str, str]] = None,
        context: Dict[str, Any] = None,
    ) -> str:
        """构建提示词"""
        # 工具定义
        tool_defs = []
        for tool in tools:
            tool_defs.append(
                f"- {tool.name}: {tool.description}\n"
                f"  参数: {json.dumps(tool._get_parameters_schema(), ensure_ascii=False)}"
            )

        # 历史对话
        history_text = ""
        if history:
            for msg in history[-10:]:  # 只保留最近10条
                role = msg.get("role", "user")
                content = msg.get("content", "")
                history_text += f"{role}: {content}\n"

        return self.template.format(
            tool_definitions="\n".join(tool_defs),
            history=history_text or "无",
            question=question,
        )

    def build_response_prompt(
        self,
        question: str,
        thoughts: List[Thought],
        tools: List[VirtualTool],
    ) -> str:
        """构建响应提示词"""
        # 添加思考历史
        thought_context = "\n".join([
            f"步骤 {t.step}: {t.thought}"
            + (f" -> 行动: {t.action}" if t.action else "")
            + (f" -> 观察: {t.observation}" if t.observation else "")
            for t in thoughts[-5:]  # 最近5步
        ])

        return f"""基于以下思考过程，请给出最终答案：

思考历史：
{thought_context}

问题：{question}

请直接给出答案，不要再调用工具。"""


class ResponseParser:
    """
    响应解析器

    解析LLM输出，提取思考、行动和观察
    """

    # 匹配模式
    THOUGHT_PATTERN = r"思考\s*(\d+):\s*(.+?)(?=\n行动:|\Z)"
    ACTION_PATTERN = r"行动:\s*(\S+)"
    ACTION_INPUT_PATTERN = r"行动输入:\s*(\{[\s\S]*?\})(?=\n观察:|\Z)"
    OBSERVATION_PATTERN = r"观察:\s*(.+?)(?=\n思考|\Z)"

    def __init__(self):
        self.thought_re = re.compile(self.THOUGHT_PATTERN, re.MULTILINE | re.DOTALL)
        self.action_re = re.compile(self.ACTION_PATTERN, re.MULTILINE)
        self.action_input_re = re.compile(self.ACTION_INPUT_PATTERN, re.MULTILINE | re.DOTALL)
        self.observation_re = re.compile(self.OBSERVATION_PATTERN, re.MULTILINE | re.DOTALL)

    def parse(self, response: str) -> Dict[str, Any]:
        """
        解析响应

        Args:
            response: LLM原始响应

        Returns:
            解析结果
        """
        result = {
            "thoughts": [],
            "action": None,
            "action_input": None,
            "observation": None,
            "is_finished": False,
        }

        # 提取思考
        thought_matches = self.thought_re.findall(response)
        for step, thought in thought_matches:
            result["thoughts"].append({
                "step": int(step),
                "thought": thought.strip()
            })

        # 提取行动
        action_match = self.action_re.search(response)
        if action_match:
            result["action"] = action_match.group(1).strip()

        # 提取行动输入
        action_input_match = self.action_input_re.search(response)
        if action_input_match:
            try:
                result["action_input"] = json.loads(action_input_match.group(1))
            except json.JSONDecodeError:
                result["action_input"] = {"raw": action_input_match.group(1)}

        # 提取观察
        observation_match = self.observation_re.search(response)
        if observation_match:
            result["observation"] = observation_match.group(1).strip()

        # 检查是否完成
        if not result["action"] or result["action"] == "完成":
            result["is_finished"] = True

        return result


class AgentLoopEngine:
    """
    Agent循环引擎

    实现完整的ReAct推理循环：
    1. 接收用户输入
    2. 构建提示词
    3. 调用LLM
    4. 解析响应
    5. 执行工具（如需要）
    6. 收集观察结果
    7. 重复步骤2-6直到完成
    """

    def __init__(
        self,
        llm_client: Any,
        max_iterations: int = 10,
        timeout: float = 120.0,
        enable_thinking: bool = True,
    ):
        self.llm_client = llm_client
        self.max_iterations = max_iterations
        self.timeout = timeout
        self.enable_thinking = enable_thinking

        # 工具注册表
        self._tools: Dict[str, VirtualTool] = {}

        # 会话管理
        self._sessions: Dict[str, AgentSession] = {}

        # 提示词构建器
        self.prompt_builder = ReActPromptBuilder()

        # 响应解析器
        self.parser = ResponseParser()

        logger.info(f"AgentLoopEngine initialized (max_iterations={max_iterations})")

    def register_tool(self, tool: VirtualTool):
        """注册工具"""
        self._tools[tool.name] = tool
        logger.info(f"Tool registered: {tool.name}")

    def get_tool(self, name: str) -> Optional[VirtualTool]:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, str]]:
        """列出所有工具"""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    async def create_session(
        self,
        user_id: str,
        agent_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        创建会话

        Args:
            user_id: 用户ID
            agent_type: Agent类型
            metadata: 元数据

        Returns:
            会话ID
        """
        session_id = f"session_{uuid.uuid4().hex[:12]}"

        session = AgentSession(
            id=session_id,
            user_id=user_id,
            agent_type=agent_type,
            status=AgentStatus.IDLE,
            metadata=metadata or {},
        )

        self._sessions[session_id] = session
        logger.info(f"Session created: {session_id}")
        return session_id

    async def get_session(self, session_id: str) -> Optional[AgentSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    async def run(
        self,
        session_id: str,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        运行Agent

        Args:
            session_id: 会话ID
            user_input: 用户输入
            context: 额外上下文

        Returns:
            执行结果
        """
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # 更新会话
        session.status = AgentStatus.THINKING
        session.context = context or {}

        # 添加用户消息
        session.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().isoformat(),
        })

        try:
            # ReAct循环
            result = await self._run_react_loop(session, user_input)

            # 标记完成
            session.status = AgentStatus.COMPLETED

            return {
                "success": True,
                "session_id": session_id,
                "result": result,
                "thoughts": [
                    {
                        "step": t.step,
                        "thought": t.thought,
                        "action": t.action,
                        "observation": t.observation,
                    }
                    for t in session.thoughts
                ],
                "tool_calls": [
                    {
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "result": tc.result,
                        "error": tc.error,
                        "duration": tc.duration,
                    }
                    for tc in session.tool_calls
                ],
            }

        except Exception as e:
            session.status = AgentStatus.ERROR
            logger.error(f"Agent run error: {e}")

            return {
                "success": False,
                "session_id": session_id,
                "error": str(e),
            }

    async def _run_react_loop(
        self,
        session: AgentSession,
        user_input: str,
    ) -> str:
        """执行ReAct循环"""
        iteration = 0
        final_response = None

        # 初始思考
        thought = Thought(
            step=0,
            thought=f"我需要帮助用户解决：{user_input}",
        )
        session.thoughts.append(thought)

        while iteration < self.max_iterations:
            iteration += 1
            session.status = AgentStatus.THINKING

            # 构建提示词
            prompt = self.prompt_builder.build(
                question=user_input,
                tools=list(self._tools.values()),
                history=session.messages[-10:],
                context=session.context,
            )

            # 添加思考历史
            if session.thoughts:
                thought_history = "\n".join([
                    f"步骤 {t.step}: {t.thought}"
                    + (f" -> 行动: {t.action}" if t.action else "")
                    + (f" -> 观察: {t.observation}" if t.observation else "")
                    for t in session.thoughts[-5:]
                ])
                prompt += f"\n\n之前的思考：\n{thought_history}"

            # 调用LLM
            try:
                response = await self._call_llm(prompt)
            except Exception as e:
                logger.error(f"LLM call error: {e}")
                raise

            # 解析响应
            parsed = self.parser.parse(response)

            # 更新思考
            if parsed["thoughts"]:
                latest_thought = parsed["thoughts"][-1]
                thought = Thought(
                    step=len(session.thoughts),
                    thought=latest_thought["thought"],
                    action=parsed.get("action"),
                    action_input=parsed.get("action_input"),
                )
                session.thoughts.append(thought)

            # 处理行动
            action = parsed.get("action")
            action_input = parsed.get("action_input")

            if action and action in self._tools:
                session.status = AgentStatus.ACTING

                # 执行工具
                tool = self._tools[action]
                tool_call = ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name=action,
                    arguments=action_input or {},
                    start_time=datetime.now(),
                )
                session.tool_calls.append(tool_call)

                try:
                    result = await tool.execute(**(action_input or {}))
                    tool_call.result = result
                    tool_call.end_time = datetime.now()
                    tool_call.duration = (tool_call.end_time - tool_call.start_time).total_seconds()

                    # 更新观察
                    thought.observation = str(result)
                    session.status = AgentStatus.THINKING

                except Exception as e:
                    tool_call.error = str(e)
                    tool_call.end_time = datetime.now()
                    tool_call.duration = (tool_call.end_time - tool_call.start_time).total_seconds()

                    thought.observation = f"工具执行错误: {str(e)}"
                    session.status = AgentStatus.THINKING

            elif action in ["完成", "finish", "respond", None] or parsed.get("is_finished"):
                # 完成
                if parsed["thoughts"]:
                    # 使用最后的思考生成响应
                    final_prompt = self.prompt_builder.build_response_prompt(
                        question=user_input,
                        thoughts=session.thoughts,
                        tools=list(self._tools.values()),
                    )

                    try:
                        final_response = await self._call_llm(final_prompt)
                    except Exception:
                        final_response = parsed["thoughts"][-1]["thought"]

                session.status = AgentStatus.COMPLETED
                break

            else:
                # 无法识别的行动
                thought.observation = f"无法识别的行动: {action}"

        # 检查是否超时
        if iteration >= self.max_iterations:
            final_response = f"已达到最大迭代次数({self.max_iterations})，请简化您的问题。"

        # 添加助手消息
        session.messages.append({
            "role": "assistant",
            "content": final_response or "处理完成",
            "timestamp": datetime.now().isoformat(),
        })

        return final_response or "处理完成"

    async def _call_llm(self, prompt: str) -> str:
        """
        调用LLM

        Args:
            prompt: 提示词

        Returns:
            LLM响应
        """
        # 根据不同的LLM客户端适配
        if hasattr(self.llm_client, "generate"):
            # 兼容自定义LLM客户端
            result = await self.llm_client.generate(prompt)
            return result.get("content", str(result))
        elif hasattr(self.llm_client, "chat"):
            # 兼容聊天接口
            messages = [{"role": "user", "content": prompt}]
            result = await self.llm_client.chat(messages)
            return result.get("content", str(result))
        else:
            raise ValueError("LLM client not supported")

    async def clear_session(self, session_id: str):
        """清理会话"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Session cleared: {session_id}")

    def get_session_history(
        self,
        session_id: str,
        max_messages: int = 50,
    ) -> List[Dict[str, Any]]:
        """获取会话历史"""
        session = self._sessions.get(session_id)
        if not session:
            return []

        return session.messages[-max_messages:]

    def get_metrics(self) -> Dict[str, Any]:
        """获取指标"""
        total_thoughts = sum(len(s.thoughts) for s in self._sessions.values())
        total_tool_calls = sum(len(s.tool_calls) for s in self._sessions.values())

        return {
            "total_sessions": len(self._sessions),
            "total_thoughts": total_thoughts,
            "total_tool_calls": total_tool_calls,
            "registered_tools": len(self._tools),
        }


# =============================================================================
# 安全数学表达式计算器 (使用AST而非eval，防止代码注入攻击)
# =============================================================================

class SafeCalculator:
    """安全数学表达式计算器 - 使用AST解析而非eval()，防止代码注入"""
    OPERATORS = {
        ast.Add: operator.add, ast.Sub: operator.sub,
        ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg,
    }
    def __init__(self):
        self.functions = {"abs": abs, "round": round, "min": min, "max": max}
        self.constants = {"pi": 3.14159265359, "e": 2.71828182846}
    def _eval_node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant): return node.value
        elif isinstance(node, ast.Num): return node.n
        elif isinstance(node, ast.BinOp):
            left, right = self._eval_node(node.left), self._eval_node(node.right)
            op_type = type(node.op)
            if op_type in self.OPERATORS: return self.OPERATORS[op_type](left, right)
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_type = type(node.op)
            if op_type in self.OPERATORS: return self.OPERATORS[op_type](operand)
            raise ValueError("不支持的一元运算符")
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name in self.functions:
                return self.functions[func_name](*[self._eval_node(a) for a in node.args])
            raise ValueError(f"不支持的函数: {func_name}")
        elif isinstance(node, ast.Name):
            if node.id in self.constants: return self.constants[node.id]
            raise ValueError(f"未定义的名称: {node.id}")
        elif isinstance(node, ast.Expression): return self._eval_node(node.body)
        raise ValueError(f"不支持的节点: {type(node).__name__}")
    def evaluate(self, expression: str) -> float:
        expression = expression.strip()
        try: tree = ast.parse(expression, mode='eval')
        except SyntaxError as e: raise ValueError(f"语法错误: {e}")
        for node in ast.walk(tree):
            allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult,
                      ast.Div, ast.Pow, ast.Name, ast.Call, ast.Constant, ast.Num)
            if not isinstance(node, allowed) and not isinstance(node, ast.NameConstant):
                raise ValueError(f"不支持的操作: {type(node).__name__}")
        return self._eval_node(tree.body)

_safe_calculator = SafeCalculator()


# =============================================================================
# 内置工具示例
# =============================================================================

class CalculatorTool(VirtualTool):
    """计算器工具 (安全版本，使用AST解析)"""

    def __init__(self):
        super().__init__(
            name="calculator",
            description="执行数学计算（安全版本，支持加减乘除、括号、幂运算）",
        )

    async def execute(self, expression: str = None, **kwargs) -> str:
        """执行安全计算"""
        if expression:
            try:
                result = _safe_calculator.evaluate(expression)
                if isinstance(result, float):
                    return str(int(result)) if result.is_integer() else f"{result:.10g}"
                return str(result)
            except Exception as e:
                return f"计算错误: {str(e)}"

        # 使用kwargs中的参数
        operation = kwargs.get("operation")
        a = kwargs.get("a", 0)
        b = kwargs.get("b", 0)

        if operation == "add":
            return str(a + b)
        elif operation == "subtract":
            return str(a - b)
        elif operation == "multiply":
            return str(a * b)
        elif operation == "divide":
            if b == 0:
                return "错误：除数不能为零"
            return str(a / b)
        else:
            return "未知操作"

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 2+3*4, (10+5)*2, 2**3（幂运算）",
                },
            },
            "required": ["expression"],
        }


class SearchTool(VirtualTool):
    """搜索工具（示例）"""

    def __init__(self):
        super().__init__(
            name="search",
            description="搜索信息",
        )

    async def execute(self, query: str = None, **kwargs) -> str:
        """执行搜索"""
        if not query:
            query = kwargs.get("q", "")

        if not query:
            return "请提供搜索关键词"

        # 实际实现应调用搜索API
        # 这里返回模拟结果
        return f"搜索结果 for '{query}': [这是搜索功能的占位符]"

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
            },
            "required": ["query"],
        }


# =============================================================================
# 工厂函数
# =============================================================================

def create_agent_loop(
    llm_client: Any,
    max_iterations: int = 10,
    timeout: float = 120.0,
) -> AgentLoopEngine:
    """
    创建Agent循环引擎

    Args:
        llm_client: LLM客户端
        max_iterations: 最大迭代次数
        timeout: 超时时间

    Returns:
        AgentLoopEngine实例
    """
    engine = AgentLoopEngine(
        llm_client=llm_client,
        max_iterations=max_iterations,
        timeout=timeout,
    )

    # 注册内置工具
    engine.register_tool(CalculatorTool())
    engine.register_tool(SearchTool())

    return engine


# =============================================================================
# 使用示例
# =============================================================================

async def example_usage():
    """使用示例"""

    # 模拟LLM客户端
    class MockLLMClient:
        async def chat(self, messages):
            # 返回模拟响应
            return {
                "content": """思考 1: 用户想要计算一个表达式，我需要使用计算器工具。

行动: calculator
行动输入: {"expression": "2+3*4"}

观察: 14

思考 2: 计算完成，我得到了结果14。

行动: 完成
"""
            }

    # 创建引擎
    engine = create_agent_loop(MockLLMClient())

    # 创建会话
    session_id = await engine.create_session(
        user_id="user1",
        agent_type="math",
    )

    # 运行
    result = await engine.run(
        session_id=session_id,
        user_input="计算 2+3*4 等于多少？",
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 获取指标
    print(engine.get_metrics())


if __name__ == "__main__":
    asyncio.run(example_usage())
