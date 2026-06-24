#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Context Builder
上下文构建器 - 实现动态提示词组装、对话上下文管理、工具格式化

核心功能：
- 对话上下文管理
- 工具定义格式化
- 消息历史组装
- 记忆系统集成
- 多模态上下文支持

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import re

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """消息角色"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """消息"""
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    required: List[str] = field(default_factory=list)


@dataclass
class ConversationContext:
    """
    对话上下文

    包含：
    - 消息历史
    - 工具列表
    - 系统提示
    - 用户信息
    - 额外上下文
    """

    session_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    tools: List[ToolDefinition] = field(default_factory=list)
    system_prompt: str = ""
    user_info: Dict[str, Any] = field(default_factory=dict)
    context_data: Dict[str, Any] = field(default_factory=dict)
    max_history: int = 20
    max_tokens: Optional[int] = None

    def add_message(
        self,
        role: MessageRole,
        content: str,
        name: Optional[str] = None,
        tool_call_id: Optional[str] = None,
    ):
        """添加消息"""
        message = Message(
            role=role,
            content=content,
            name=name,
            tool_call_id=tool_call_id,
        )
        self.messages.append(message)

        # 限制历史长度
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

    def get_history(self, limit: Optional[int] = None) -> List[Message]:
        """获取历史消息"""
        if limit:
            return self.messages[-limit:]
        return self.messages.copy()

    def clear_history(self):
        """清空历史"""
        self.messages.clear()


class BaseMessageFormatter(ABC):
    """消息格式化器基类"""

    @abstractmethod
    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """格式化消息列表"""
        pass

    @abstractmethod
    def format_tools(self, tools: List[ToolDefinition]) -> str:
        """格式化工具列表"""
        pass


class OpenAIMessageFormatter(BaseMessageFormatter):
    """OpenAI格式消息格式化器"""

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """格式化消息为OpenAI格式"""
        result = []
        for msg in messages:
            item = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.name:
                item["name"] = msg.name
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            result.append(item)
        return result

    def format_tools(self, tools: List[ToolDefinition]) -> str:
        """格式化工具为OpenAI格式"""
        tool_defs = []
        for tool in tools:
            tool_defs.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            })
        return json.dumps(tool_defs, ensure_ascii=False)


class AnthropicMessageFormatter(BaseMessageFormatter):
    """Anthropic格式消息格式化器"""

    def format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """格式化消息为Anthropic格式"""
        result = []
        system_msg = None

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_msg = msg.content
                continue

            item = {
                "role": msg.role.value,
                "content": msg.content,
            }
            if msg.name:
                item["name"] = msg.name
            result.append(item)

        # Anthropic需要单独的system字段
        if system_msg:
            return {"system": system_msg, "messages": result}
        return result

    def format_tools(self, tools: List[ToolDefinition]) -> str:
        """格式化工具为Anthropic格式"""
        # Anthropic目前不支持tools，使用描述代替
        tool_desc = "\n\n".join([
            f"- {tool.name}: {tool.description}"
            for tool in tools
        ])
        return tool_desc


class ContextBuilder:
    """
    上下文构建器

    负责：
    - 组装对话上下文
    - 格式化消息
    - 整合工具定义
    - 管理记忆检索
    """

    def __init__(
        self,
        provider: str = "openai",
        max_history: int = 20,
        max_context_tokens: int = 128000,
    ):
        self.provider = provider
        self.max_history = max_history
        self.max_context_tokens = max_context_tokens

        # 选择格式化器
        if provider == "openai":
            self.formatter = OpenAIMessageFormatter()
        elif provider == "anthropic":
            self.formatter = AnthropicMessageFormatter()
        else:
            self.formatter = OpenAIMessageFormatter()

        # 记忆检索函数
        self._memory_retriever: Optional[Callable] = None

        logger.info(f"ContextBuilder initialized (provider={provider})")

    def set_memory_retriever(self, retriever: Callable):
        """
        设置记忆检索函数

        Args:
            retriever: async function(query: str) -> List[Dict]
        """
        self._memory_retriever = retriever

    def create_context(
        self,
        session_id: str,
        user_id: str,
        system_prompt: Optional[str] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ConversationContext:
        """创建对话上下文"""
        return ConversationContext(
            session_id=session_id,
            user_id=user_id,
            system_prompt=system_prompt or self._get_default_system_prompt(),
            user_info=user_info or {},
            max_history=self.max_history,
        )

    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示"""
        return """你是一个智能助手，可以帮助用户完成各种任务。

你可以：
- 回答问题
- 执行计算
- 搜索信息
- 分析文件
- 编写代码

请尽量提供准确、有用的回答。"""

    async def build(
        self,
        context: ConversationContext,
        current_input: str,
        include_tools: bool = True,
        include_memory: bool = True,
    ) -> Dict[str, Any]:
        """
        构建上下文

        Args:
            context: 对话上下文
            current_input: 当前输入
            include_tools: 是否包含工具
            include_memory: 是否包含记忆

        Returns:
            构建好的上下文
        """
        # 添加当前用户消息
        context.add_message(
            role=MessageRole.USER,
            content=current_input,
        )

        # 准备消息列表
        messages = []

        # 添加系统消息
        if context.system_prompt:
            messages.append(Message(
                role=MessageRole.SYSTEM,
                content=context.system_prompt,
            ))

        # 添加历史消息
        history = context.get_history()
        messages.extend(history)

        # 检索记忆
        if include_memory and self._memory_retriever:
            try:
                memories = await self._memory_retriever(current_input)
                if memories:
                    memory_text = self._format_memories(memories)
                    # 插入到系统消息后
                    messages.insert(1, Message(
                        role=MessageRole.SYSTEM,
                        content=f"相关记忆：\n{memory_text}",
                    ))
            except Exception as e:
                logger.error(f"Memory retrieval error: {e}")

        # 格式化消息
        formatted_messages = self.formatter.format_messages(messages)

        # 准备结果
        result = {
            "messages": formatted_messages,
            "session_id": context.session_id,
            "user_id": context.user_id,
        }

        # 添加工具
        if include_tools and context.tools:
            result["tools"] = self.formatter.format_tools(context.tools)

        return result

    def _format_memories(self, memories: List[Dict[str, Any]]) -> str:
        """格式化记忆"""
        lines = []
        for i, mem in enumerate(memories[:5], 1):  # 最多5条
            content = mem.get("content", "")
            timestamp = mem.get("timestamp", "")
            lines.append(f"{i}. {content} [{timestamp}]")
        return "\n".join(lines)

    def add_tool(self, context: ConversationContext, tool: ToolDefinition):
        """添加工具到上下文"""
        context.tools.append(tool)

    def add_tools(self, context: ConversationContext, tools: List[ToolDefinition]):
        """批量添加工具"""
        context.tools.extend(tools)

    def format_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        results: List[Any],
    ) -> List[Message]:
        """
        格式化工具调用结果

        Args:
            tool_calls: 工具调用列表
            results: 结果列表

        Returns:
            消息列表
        """
        messages = []
        for call, result in zip(tool_calls, results):
            msg = Message(
                role=MessageRole.TOOL,
                content=str(result),
                name=call.get("name"),
                tool_call_id=call.get("id"),
            )
            messages.append(msg)
        return messages

    def extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        从响应中提取JSON

        Args:
            response: 原始响应

        Returns:
            解析的JSON或None
        """
        # 尝试直接解析
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # 尝试提取代码块
        json_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取花括号包裹的内容
        brace_match = re.search(r"\{[\s\S]*\}", response)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def estimate_tokens(self, text: str) -> int:
        """
        估算token数量

        Args:
            text: 文本

        Returns:
            估算的token数量
        """
        # 简单估算：中文约1字=2token，英文约1词=1.3token
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        other = len(text) - chinese_chars - english_words

        return int(chinese_chars * 2 + english_words * 1.3 + other * 1.5)

    def truncate_to_token_limit(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int,
    ) -> List[Dict[str, Any]]:
        """
        根据token限制截断消息

        Args:
            messages: 消息列表
            max_tokens: 最大token数

        Returns:
            截断后的消息
        """
        total_tokens = 0
        truncated = []

        # 从最新的消息开始
        for msg in reversed(messages):
            content = msg.get("content", "")
            msg_tokens = self.estimate_tokens(content)

            if total_tokens + msg_tokens > max_tokens:
                # 尝试截断此消息
                remaining = max_tokens - total_tokens
                if remaining > 100:  # 保留至少100 tokens
                    # 截断内容
                    chars_estimate = int(remaining / 1.5)
                    truncated_content = content[:chars_estimate] + "..."
                    msg["content"] = truncated_content
                    truncated.insert(0, msg)
                    break
                else:
                    break

            truncated.insert(0, msg)
            total_tokens += msg_tokens

        return truncated


class DynamicPromptBuilder:
    """
    动态提示词构建器

    根据任务类型动态生成提示词
    """

    # 任务类型模板
    TASK_TEMPLATES = {
        "general": """你是一个智能助手，请回答用户的问题。

如果需要使用工具，请明确指定工具名称和参数。""",

        "coding": """你是一个专业的程序员，请帮助用户解决编程问题。

你可以：
- 编写代码
- 调试程序
- 解释代码
- 优化性能
- 编写测试

请提供清晰、准确的代码和解释。""",

        "analysis": """你是一个数据分析专家，请帮助用户分析数据。

请提供：
- 清晰的分析思路
- 准确的结论
- 可视化建议（如适用）""",

        "search": """你是一个信息检索专家，请帮助用户找到需要的信息。

请：
- 理解用户的信息需求
- 提供准确的搜索结果
- 总结关键信息""",

        "creative": """你是一个创意专家，请帮助用户进行创意工作。

你可以：
- 头脑风暴
- 撰写文案
- 创作故事
- 提供设计建议""",
    }

    def __init__(self):
        self.custom_templates: Dict[str, str] = {}

    def get_template(self, task_type: str) -> str:
        """获取任务模板"""
        return self.custom_templates.get(
            task_type,
            self.TASK_TEMPLATES.get(task_type, self.TASK_TEMPLATES["general"])
        )

    def register_template(self, name: str, template: str):
        """注册自定义模板"""
        self.custom_templates[name] = template
        logger.info(f"Custom template registered: {name}")

    def build(
        self,
        task_type: str,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        构建提示词

        Args:
            task_type: 任务类型
            user_input: 用户输入
            context: 上下文

        Returns:
            完整的提示词
        """
        template = self.get_template(task_type)

        # 替换变量
        if context:
            for key, value in context.items():
                template = template.replace(f"{{{key}}}", str(value))

        return f"{template}\n\n用户问题：{user_input}"

    def build_with_examples(
        self,
        task_type: str,
        user_input: str,
        examples: List[Dict[str, str]],
    ) -> str:
        """
        构建带示例的提示词

        Args:
            task_type: 任务类型
            user_input: 用户输入
            examples: 示例列表

        Returns:
            完整的提示词
        """
        template = self.get_template(task_type)

        # 添加示例
        if examples:
            example_text = "\n\n示例：\n"
            for ex in examples:
                example_text += f"输入：{ex.get('input', '')}\n"
                example_text += f"输出：{ex.get('output', '')}\n\n"

            template = f"{template}\n{example_text}"

        return f"{template}\n\n用户问题：{user_input}"


# =============================================================================
# 工厂函数
# =============================================================================

def create_context_builder(
    provider: str = "openai",
    max_history: int = 20,
    max_context_tokens: int = 128000,
) -> ContextBuilder:
    """
    创建上下文构建器

    Args:
        provider: LLM提供者
        max_history: 最大历史数
        max_context_tokens: 最大token数

    Returns:
        ContextBuilder实例
    """
    return ContextBuilder(
        provider=provider,
        max_history=max_history,
        max_context_tokens=max_context_tokens,
    )


def create_dynamic_prompt_builder() -> DynamicPromptBuilder:
    """创建动态提示词构建器"""
    return DynamicPromptBuilder()


# =============================================================================
# 使用示例
# =============================================================================

async def example_usage():
    """使用示例"""
    # 创建上下文构建器
    builder = create_context_builder(provider="openai")

    # 创建对话上下文
    context = builder.create_context(
        session_id="session1",
        user_id="user1",
        system_prompt="你是一个有帮助的助手。",
    )

    # 添加工具
    context.tools.append(ToolDefinition(
        name="calculator",
        description="执行数学计算",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式"}
            },
            "required": ["expression"]
        },
        required=["expression"],
    ))

    # 构建上下文
    built = await builder.build(
        context=context,
        current_input="计算 2+3 等于多少？",
    )

    print(json.dumps(built, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(example_usage())
