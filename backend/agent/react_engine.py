"""
NanoBot Factory - ReAct Loop Engine
ReAct (Reasoning + Acting) 循环引擎实现

核心功能：
- Think-Act-Observe 迭代循环
- 推理步骤记录与回溯
- 工具执行与结果处理
- 状态机管理
- 终止条件判断

@author MiniMax Agent
@date 2026-04-11
"""

import asyncio
import logging
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque
import json

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Agent状态枚举"""
    IDLE = "idle"                 # 空闲状态
    THINKING = "thinking"         # 推理中
    ACTING = "acting"            # 执行中
    OBSERVING = "observing"      # 观察中
    WAITING = "waiting"           # 等待中
    COMPLETED = "completed"       # 已完成
    ERROR = "error"               # 错误状态
    TERMINATED = "terminated"     # 已终止


class LoopStepType(Enum):
    """循环步骤类型"""
    THINK = "think"               # 推理步骤
    ACT = "act"                  # 行动步骤
    OBSERVE = "observe"          # 观察步骤
    SYSTEM = "system"            # 系统步骤


@dataclass
class ReasoningStep:
    """推理步骤记录"""
    step_id: str
    step_type: LoopStepType
    thought: str                           # 思考内容
    action: Optional[str] = None            # 执行的动作
    action_input: Optional[Dict] = None     # 动作输入参数
    observation: Optional[str] = None        # 观察结果
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error
        }


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopConfig:
    """循环配置"""
    max_iterations: int = 20            # 最大迭代次数
    max_tokens: int = 8000             # 最大token数
    timeout_seconds: float = 120.0      # 超时时间
    temperature: float = 0.7           # 温度参数
    termination_keywords: List[str] = None  # 终止关键词
    enable_reflection: bool = True      # 是否启用反思
    max_reasoning_depth: int = 5        # 最大推理深度
    
    def __post_init__(self):
        if self.termination_keywords is None:
            self.termination_keywords = ["完成", "TERMINATE", "FINAL_ANSWER", "结果"]


@dataclass
class LoopResult:
    """循环执行结果"""
    success: bool
    final_answer: Optional[str] = None
    steps: List[ReasoningStep] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    error: Optional[str] = None
    total_iterations: int = 0
    total_duration_ms: float = 0.0
    tool_calls: List[ToolResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "final_answer": self.final_answer,
            "steps": [s.to_dict() for s in self.steps],
            "state": self.state.value,
            "error": self.error,
            "total_iterations": self.total_iterations,
            "total_duration_ms": self.total_duration_ms,
            "tool_calls": [
                {
                    "tool_name": tc.tool_name,
                    "success": tc.success,
                    "duration_ms": tc.duration_ms
                } for tc in self.tool_calls
            ],
            "metadata": self.metadata
        }


class ToolExecutor:
    """工具执行器"""
    
    def __init__(self, tool_registry: Dict[str, Callable]):
        self.tool_registry = tool_registry
        self.execution_history: List[ToolResult] = []
        self._lock = asyncio.Lock()
    
    def register_tool(self, name: str, func: Callable) -> None:
        """注册工具"""
        self.tool_registry[name] = func
        logger.info(f"Registered tool: {name}")
    
    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        if name in self.tool_registry:
            del self.tool_registry[name]
            return True
        return False
    
    async def execute(self, tool_name: str, tool_input: Dict[str, Any]) -> ToolResult:
        """执行工具"""
        start_time = time.time()
        
        if tool_name not in self.tool_registry:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=f"Tool '{tool_name}' not found"
            )
        
        try:
            tool_func = self.tool_registry[tool_name]
            
            # 支持同步和异步工具
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**tool_input)
            else:
                result = tool_func(**tool_input)
            
            duration = (time.time() - start_time) * 1000
            
            tool_result = ToolResult(
                tool_name=tool_name,
                success=True,
                result=result,
                duration_ms=duration
            )
            
            async with self._lock:
                self.execution_history.append(tool_result)
            
            logger.info(f"Tool executed: {tool_name} ({duration:.2f}ms)")
            return tool_result
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            tool_result = ToolResult(
                tool_name=tool_name,
                success=False,
                result=None,
                error=error_msg,
                duration_ms=duration
            )
            
            async with self._lock:
                self.execution_history.append(tool_result)
            
            logger.error(f"Tool execution failed: {tool_name} - {error_msg}")
            return tool_result
    
    def get_available_tools(self) -> List[str]:
        """获取可用工具列表"""
        return list(self.tool_registry.keys())
    
    def get_execution_history(self) -> List[ToolResult]:
        """获取执行历史"""
        return self.execution_history.copy()


class PromptBuilder:
    """提示词构建器"""
    
    # 系统提示词模板
    SYSTEM_PROMPT = """你是一个AI助手，使用ReAct (Reasoning + Acting)模式来解决问题。

在每个推理步骤中，你需要：
1. THINK: 分析当前情况，进行推理
2. ACT: 选择并执行一个工具来获取信息或完成任务
3. OBSERVE: 观察工具执行的结果

可用工具:
{tools_description}

记住：
- 每次只执行一个工具
- 仔细分析工具返回的结果
- 当获得最终答案时，明确说出"最终答案"或"TERMINATE"
"""
    
    @staticmethod
    def build_system_prompt(tools: Dict[str, Callable], tool_descriptions: Dict[str, str] = None) -> str:
        """构建系统提示词"""
        if tool_descriptions is None:
            tool_descriptions = {name: f"{name}()" for name in tools.keys()}
        
        tools_desc = "\n".join([f"- {name}: {desc}" for name, desc in tool_descriptions.items()])
        return PromptBuilder.SYSTEM_PROMPT.format(tools_description=tools_desc)
    
    @staticmethod
    def build_iteration_prompt(
        user_question: str,
        reasoning_history: List[ReasoningStep],
        available_tools: List[str]
    ) -> str:
        """构建迭代提示词"""
        history_text = ""
        for i, step in enumerate(reasoning_history[-5:], 1):  # 最近5步
            history_text += f"\n步骤 {i}:\n"
            history_text += f"思考: {step.thought}\n"
            if step.action:
                history_text += f"动作: {step.action}({step.action_input})\n"
            if step.observation:
                history_text += f"观察: {step.observation}\n"
        
        return f"""问题: {user_question}

历史推理:
{history_text}

可用工具: {', '.join(available_tools)}

请继续推理（THINK）、选择工具（ACT）或给出最终答案。"""


class ReasoningHistory:
    """推理历史管理器"""
    
    def __init__(self, max_size: int = 100):
        self.steps: deque = deque(maxlen=max_size)
        self._total_think_time = 0.0
        self._total_act_time = 0.0
    
    def add_step(self, step: ReasoningStep) -> None:
        """添加推理步骤"""
        self.steps.append(step)
        
        if step.step_type == LoopStepType.THINK:
            self._total_think_time += step.duration_ms
        elif step.step_type == LoopStepType.ACT:
            self._total_act_time += step.duration_ms
    
    def get_recent_steps(self, n: int = 5) -> List[ReasoningStep]:
        """获取最近n步"""
        return list(self.steps)[-n:]
    
    def get_all_steps(self) -> List[ReasoningStep]:
        """获取所有步骤"""
        return list(self.steps)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_steps": len(self.steps),
            "think_steps": sum(1 for s in self.steps if s.step_type == LoopStepType.THINK),
            "act_steps": sum(1 for s in self.steps if s.step_type == LoopStepType.ACT),
            "observe_steps": sum(1 for s in self.steps if s.step_type == LoopStepType.OBSERVE),
            "total_think_time_ms": self._total_think_time,
            "total_act_time_ms": self._total_act_time,
            "success_rate": sum(1 for s in self.steps if s.success) / max(len(self.steps), 1)
        }
    
    def clear(self) -> None:
        """清空历史"""
        self.steps.clear()
        self._total_think_time = 0.0
        self._total_act_time = 0.0


class TerminationChecker:
    """终止条件检查器"""
    
    def __init__(self, config: LoopConfig):
        self.config = config
        self._iteration_count = 0
        self._token_count = 0
        self._start_time: Optional[float] = None
    
    def reset(self) -> None:
        """重置计数器"""
        self._iteration_count = 0
        self._token_count = 0
        self._start_time = time.time()
    
    def check(self, response: str, step: ReasoningStep) -> tuple[bool, str]:
        """
        检查是否应终止循环
        
        Returns:
            (should_terminate, reason)
        """
        self._iteration_count += 1
        
        # 检查最大迭代次数
        if self._iteration_count >= self.config.max_iterations:
            return True, f"达到最大迭代次数 ({self.config.max_iterations})"
        
        # 检查超时
        if self._start_time:
            elapsed = time.time() - self._start_time
            if elapsed >= self.config.timeout_seconds:
                return True, f"达到超时限制 ({self.config.timeout_seconds}s)"
        
        # 检查终止关键词
        for keyword in self.config.termination_keywords:
            if keyword in response:
                return True, f"检测到终止关键词: {keyword}"
        
        # 检查错误状态
        if not step.success:
            return True, f"执行失败: {step.error}"
        
        # 检查最终答案标记
        if "最终答案" in response or "TERMINATE" in response or "FINAL_ANSWER" in response:
            return True, "获得最终答案"
        
        return False, ""
    
    @property
    def iteration_count(self) -> int:
        return self._iteration_count
    
    @property
    def elapsed_time(self) -> float:
        if self._start_time:
            return time.time() - self._start_time
        return 0.0


class AgentLoopEngine:
    """
    ReAct循环引擎主类
    
    实现 Think-Act-Observe 迭代模式:
    1. THINK: LLM进行推理，决定下一步行动
    2. ACT: 执行工具调用
    3. OBSERVE: 处理工具返回结果
    """
    
    def __init__(
        self,
        llm_client,
        tool_executor: ToolExecutor,
        config: Optional[LoopConfig] = None
    ):
        """
        初始化ReAct循环引擎
        
        Args:
            llm_client: LLM客户端（需要支持chat/complete方法）
            tool_executor: 工具执行器
            config: 循环配置
        """
        self.llm_client = llm_client
        self.tool_executor = tool_executor
        self.config = config or LoopConfig()
        
        self.prompt_builder = PromptBuilder()
        self.reasoning_history = ReasoningHistory()
        self.termination_checker = TerminationChecker(self.config)
        
        self.state = AgentState.IDLE
        self.current_session_id: Optional[str] = None
        
        # 回调函数
        self.on_state_change: Optional[Callable[[AgentState], None]] = None
        self.on_step_complete: Optional[Callable[[ReasoningStep], None]] = None
        
        logger.info(f"AgentLoopEngine initialized (max_iterations={self.config.max_iterations})")
    
    async def run(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        system_context: Optional[str] = None
    ) -> LoopResult:
        """
        运行ReAct循环
        
        Args:
            user_input: 用户输入/问题
            session_id: 会话ID
            system_context: 系统上下文
            
        Returns:
            LoopResult: 循环执行结果
        """
        self.current_session_id = session_id or str(uuid.uuid4())
        self.reasoning_history.clear()
        self.termination_checker.reset()
        
        start_time = time.time()
        result = LoopResult(success=False)
        
        try:
            self._set_state(AgentState.THINKING)
            
            # 构建初始提示词
            tools = self.tool_executor.get_available_tools()
            system_prompt = self.prompt_builder.build_system_prompt(
                self.tool_executor.tool_registry
            )
            
            # 添加系统上下文
            if system_context:
                system_prompt += f"\n\n系统上下文:\n{system_context}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
            
            # ReAct循环
            while True:
                # 1. THINK - 推理
                thought_step = await self._think(messages)
                self.reasoning_history.add_step(thought_step)
                result.steps.append(thought_step)
                
                if self.on_step_complete:
                    self.on_step_complete(thought_step)
                
                # 检查终止条件
                should_stop, stop_reason = self.termination_checker.check(
                    thought_step.thought, thought_step
                )
                
                if should_stop:
                    if "最终答案" in thought_step.thought or "TERMINATE" in thought_step.thought:
                        result.success = True
                        result.final_answer = thought_step.thought
                    else:
                        result.error = stop_reason
                    result.state = AgentState.COMPLETED if result.success else AgentState.ERROR
                    break
                
                # 2. ACT - 执行
                if thought_step.action:
                    self._set_state(AgentState.ACTING)
                    act_step = await self._act(thought_step, messages)
                    self.reasoning_history.add_step(act_step)
                    result.steps.append(act_step)
                    result.tool_calls.append(ToolResult(
                        tool_name=thought_step.action,
                        success=act_step.success,
                        result=act_step.observation,
                        error=act_step.error
                    ))
                    
                    if self.on_step_complete:
                        self.on_step_complete(act_step)
                    
                    # 检查执行是否成功
                    if not act_step.success:
                        result.error = act_step.error
                        result.state = AgentState.ERROR
                        break
                
                # 3. OBSERVE - 观察
                self._set_state(AgentState.OBSERVING)
                await self._observe(messages)
            
        except asyncio.TimeoutError:
            result.error = "执行超时"
            result.state = AgentState.ERROR
            logger.error(f"Session {self.current_session_id} timeout")
            
        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)}"
            result.state = AgentState.ERROR
            logger.exception(f"Session {self.current_session_id} error")
        
        finally:
            self._set_state(AgentState.TERMINATED)
            result.total_iterations = self.termination_checker.iteration_count
            result.total_duration_ms = (time.time() - start_time) * 1000
            result.metadata = {
                "session_id": self.current_session_id,
                "elapsed_time": result.total_duration_ms,
                "reasoning_stats": self.reasoning_history.get_statistics()
            }
        
        return result
    
    async def _think(self, messages: List[Dict]) -> ReasoningStep:
        """执行推理步骤"""
        start_time = time.time()
        
        # 构建推理提示词
        prompt = self.prompt_builder.build_iteration_prompt(
            user_question=messages[-1]["content"],
            reasoning_history=self.reasoning_history.get_recent_steps(),
            available_tools=self.tool_executor.get_available_tools()
        )
        
        # 添加到消息历史
        messages.append({"role": "assistant", "content": prompt})
        
        try:
            # 调用LLM
            response = await self._call_llm(messages)
            
            # 解析响应
            thought, action, action_input = self._parse_llm_response(response)
            
            messages[-1]["content"] = response  # 更新最后一条消息
            
            return ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=LoopStepType.THINK,
                thought=thought,
                action=action,
                action_input=action_input,
                duration_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            return ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=LoopStepType.THINK,
                thought=f"推理失败: {str(e)}",
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    async def _act(self, think_step: ReasoningStep, messages: List[Dict]) -> ReasoningStep:
        """执行动作步骤"""
        start_time = time.time()
        
        if not think_step.action:
            return ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=LoopStepType.ACT,
                thought="无需执行动作",
                success=True,
                duration_ms=0
            )
        
        try:
            # 执行工具
            tool_result = await self.tool_executor.execute(
                think_step.action,
                think_step.action_input or {}
            )
            
            observation = self._format_observation(tool_result)
            
            return ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=LoopStepType.ACT,
                thought=f"执行工具: {think_step.action}",
                observation=observation,
                success=tool_result.success,
                error=tool_result.error,
                duration_ms=(time.time() - start_time) * 1000
            )
            
        except Exception as e:
            return ReasoningStep(
                step_id=str(uuid.uuid4()),
                step_type=LoopStepType.ACT,
                thought=f"工具执行异常: {str(e)}",
                success=False,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000
            )
    
    async def _observe(self, messages: List[Dict]) -> None:
        """观察步骤 - 更新消息历史"""
        # 添加观察结果到消息历史
        recent_steps = self.reasoning_history.get_recent_steps(1)
        if recent_steps:
            last_step = recent_steps[-1]
            if last_step.observation:
                messages.append({
                    "role": "system",
                    "content": f"[观察结果] {last_step.observation}"
                })
    
    async def _call_llm(self, messages: List[Dict]) -> str:
        """调用LLM"""
        try:
            # 尝试不同的LLM客户端接口
            if hasattr(self.llm_client, 'chat'):
                response = await self.llm_client.chat(messages)
                return response.get("content", "") if isinstance(response, dict) else str(response)
            elif hasattr(self.llm_client, 'complete'):
                response = await self.llm_client.complete(messages)
                return str(response)
            elif hasattr(self.llm_client, 'generate'):
                response = await self.llm_client.generate(messages)
                return str(response)
            else:
                raise ValueError("LLM client must have 'chat', 'complete', or 'generate' method")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _parse_llm_response(self, response: str) -> tuple[str, Optional[str], Optional[Dict]]:
        """
        解析LLM响应
        
        Returns:
            (thought, action, action_input)
        """
        thought = response
        action = None
        action_input = {}
        
        # 尝试解析动作指令
        # 格式: ACTION: tool_name INPUT: {...}
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('ACTION:') or line.startswith('动作:'):
                action = line.split(':', 1)[1].strip()
            elif line.startswith('INPUT:') or line.startswith('输入:'):
                try:
                    input_str = line.split(':', 1)[1].strip()
                    action_input = json.loads(input_str)
                except (json.JSONDecodeError, ValueError):
                    action_input = {"query": line.split(':', 1)[1].strip()}
        
        return thought, action, action_input
    
    def _format_observation(self, tool_result: ToolResult) -> str:
        """格式化观察结果"""
        if tool_result.success:
            result_str = str(tool_result.result)
            # 截断过长的结果
            if len(result_str) > 1000:
                result_str = result_str[:1000] + "..."
            return f"工具 {tool_result.tool_name} 执行成功: {result_str}"
        else:
            return f"工具 {tool_result.tool_name} 执行失败: {tool_result.error}"
    
    def _set_state(self, new_state: AgentState) -> None:
        """设置状态"""
        if self.state != new_state:
            self.state = new_state
            logger.debug(f"Agent state changed to: {new_state.value}")
            if self.on_state_change:
                self.on_state_change(new_state)
    
    def get_state(self) -> AgentState:
        """获取当前状态"""
        return self.state
    
    def get_history(self) -> List[ReasoningStep]:
        """获取推理历史"""
        return self.reasoning_history.get_all_steps()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "state": self.state.value,
            "session_id": self.current_session_id,
            "reasoning_stats": self.reasoning_history.get_statistics(),
            "available_tools": self.tool_executor.get_available_tools(),
            "config": {
                "max_iterations": self.config.max_iterations,
                "timeout_seconds": self.config.timeout_seconds
            }
        }


# 便捷函数
def create_react_engine(
    llm_client,
    tools: Dict[str, Callable],
    config: Optional[LoopConfig] = None
) -> AgentLoopEngine:
    """创建ReAct引擎的便捷函数"""
    executor = ToolExecutor(tools)
    return AgentLoopEngine(llm_client, executor, config)


# 示例工具定义
async def search_tool(query: str) -> str:
    """示例搜索工具"""
    await asyncio.sleep(0.1)  # 模拟网络延迟
    return f"搜索结果: 关于'{query}'的信息..."


async def calculator_tool(expression: str) -> str:
    """示例计算器工具"""
    try:
        result = eval(expression)  # 注意：实际使用时请用安全的表达式解析器
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


# 导出
__all__ = [
    'AgentLoopEngine',
    'ToolExecutor', 
    'PromptBuilder',
    'ReasoningHistory',
    'TerminationChecker',
    'LoopConfig',
    'LoopResult',
    'ReasoningStep',
    'ToolResult',
    'AgentState',
    'LoopStepType',
    'create_react_engine'
]
