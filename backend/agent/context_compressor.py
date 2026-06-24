"""
NanoBot Factory - Context Compressor (上下文压缩系统)
解决LLM长上下文问题，智能保留关键信息

压缩策略:
1. 滑动窗口 - 保留最近N条消息
2. 重要性评分 - 优先保留高重要性消息
3. 摘要压缩 - 将旧消息摘要为简短描述
4. 关键信息提取 - 保留工具结果/系统消息/用户指令
5. 动态阈值 - 根据token数自动触发压缩

@author MiniMax Agent
@date 2026-04-13
"""
import logging, re, time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    OBSERVATION = "observation"


class MessageImportance(Enum):
    CRITICAL = 5    # 系统消息/工具错误/用户指令
    HIGH = 4        # 工具结果/关键推理
    MEDIUM = 3      # 普通对话
    LOW = 2         # 重复/冗余内容
    NEGLIGIBLE = 1  # 格式化消息


@dataclass
class ContextMessage:
    role: MessageRole
    content: str
    importance: MessageImportance = MessageImportance.MEDIUM
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
    is_compressed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = self._estimate_tokens()

    def _estimate_tokens(self) -> int:
        # 简单估算: 中文字符约1.5token, 英文单词约1.3token
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', self.content))
        english_words = len(re.findall(r'[a-zA-Z]+', self.content))
        other_chars = len(self.content) - chinese_chars - english_words
        return int(chinese_chars * 1.5 + english_words * 1.3 + other_chars * 0.5) + 4


@dataclass
class CompressionConfig:
    max_tokens: int = 4000          # 最大token数
    target_tokens: int = 3000       # 压缩目标token数
    min_recent_messages: int = 6    # 最少保留最近消息数
    max_summary_tokens: int = 500   # 摘要最大token数
    importance_threshold: MessageImportance = MessageImportance.MEDIUM  # 保留阈值
    compress_on_threshold: float = 0.85  # 触发压缩的比例 (85%)
    enable_summarization: bool = True   # 是否启用摘要
    preserve_system_messages: bool = True   # 始终保留系统消息
    preserve_tool_results: bool = True      # 始终保留工具结果


@dataclass
class CompressionResult:
    original_token_count: int
    compressed_token_count: int
    messages_removed: int
    messages_summarized: int
    compression_ratio: float
    summary: Optional[str] = None
    compressed_messages: List[ContextMessage] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_tokens": self.original_token_count,
            "compressed_tokens": self.compressed_token_count,
            "messages_removed": self.messages_removed,
            "messages_summarized": self.messages_summarized,
            "compression_ratio": round(self.compression_ratio, 3),
            "summary": self.summary[:200] + "..." if self.summary and len(self.summary) > 200 else self.summary
        }


class ImportanceScorer:
    """消息重要性评分器"""

    # 关键词权重
    CRITICAL_PATTERNS = [
        r"error|错误|失败|异常|exception|traceback",
        r"final.answer|最终答案|terminate",
        r"system:|系统:",
    ]
    HIGH_PATTERNS = [
        r"tool.result|工具结果|observation|观察",
        r"action:|动作:|act:",
        r"user.*instruction|用户.*指令",
    ]
    LOW_PATTERNS = [
        r"^ok$|^好的$|^明白$|^understood$",
        r"^(thinking|思考中|processing)\.+$",
    ]

    @classmethod
    def score(cls, message: ContextMessage) -> MessageImportance:
        content_lower = message.content.lower()

        # 系统消息始终重要
        if message.role == MessageRole.SYSTEM:
            return MessageImportance.CRITICAL

        # 检查关键模式
        for pattern in cls.CRITICAL_PATTERNS:
            if re.search(pattern, content_lower):
                return MessageImportance.CRITICAL

        # 工具/观察消息
        if message.role in (MessageRole.TOOL, MessageRole.OBSERVATION):
            for pattern in cls.HIGH_PATTERNS:
                if re.search(pattern, content_lower):
                    return MessageImportance.HIGH
            return MessageImportance.HIGH  # 工具结果默认高重要性

        # 用户消息 - 通常高重要性
        if message.role == MessageRole.USER:
            if len(message.content) > 20:  # 超过20字的用户消息视为重要
                return MessageImportance.HIGH
            return MessageImportance.MEDIUM

        # 低重要性检查
        for pattern in cls.LOW_PATTERNS:
            if re.search(pattern, content_lower):
                return MessageImportance.LOW

        # 默认中等
        return MessageImportance.MEDIUM


class ContextSummarizer:
    """上下文摘要器 - 将多条消息压缩为摘要"""

    @staticmethod
    def summarize_messages(messages: List[ContextMessage], max_tokens: int = 300) -> str:
        """生成消息摘要 (无LLM版本 - 基于规则提取关键信息)"""
        if not messages:
            return ""

        summary_parts = []
        tool_calls = []
        observations = []
        decisions = []

        for msg in messages:
            content = msg.content.strip()
            if not content:
                continue

            if msg.role == MessageRole.SYSTEM:
                continue  # 系统消息不摘要

            elif msg.role == MessageRole.TOOL or msg.role == MessageRole.OBSERVATION:
                # 截取工具结果的前100字
                obs_summary = content[:100] + ("..." if len(content) > 100 else "")
                observations.append(f"[工具结果] {obs_summary}")

            elif msg.role == MessageRole.ASSISTANT:
                # 提取动作行
                lines = content.split('\n')
                for line in lines:
                    if any(kw in line.lower() for kw in ['action:', '动作:', 'act:', '最终答案', 'final answer']):
                        decisions.append(line.strip()[:80])
                        break

            elif msg.role == MessageRole.USER:
                if len(content) > 20:
                    summary_parts.append(f"[用户] {content[:80]}{'...' if len(content)>80 else ''}")

        # 组合摘要
        result_parts = []
        if summary_parts:
            result_parts.append("用户请求摘要:\n" + "\n".join(summary_parts[-3:]))
        if decisions:
            result_parts.append("已做决策:\n" + "\n".join(decisions[-5:]))
        if observations:
            result_parts.append("工具执行结果:\n" + "\n".join(observations[-3:]))

        summary = "\n\n".join(result_parts)

        # Token限制截断
        if len(summary) > max_tokens * 3:  # 粗略估算
            summary = summary[:max_tokens * 3] + "\n[...摘要截断...]"

        return summary or f"[已压缩 {len(messages)} 条历史消息]"


class ContextCompressor:
    """
    上下文压缩器主类
    自动管理对话历史，防止超出token限制
    """

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self.scorer = ImportanceScorer()
        self.summarizer = ContextSummarizer()
        self._compression_count = 0
        self._total_tokens_saved = 0
        logger.info(f"ContextCompressor initialized (max_tokens={self.config.max_tokens})")

    def add_message(
        self,
        messages: List[ContextMessage],
        role: MessageRole,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Tuple[List[ContextMessage], Optional[CompressionResult]]:
        """
        添加消息并自动检查是否需要压缩

        Returns:
            (updated_messages, compression_result_if_compressed)
        """
        msg = ContextMessage(role=role, content=content, metadata=metadata or {})
        msg.importance = self.scorer.score(msg)
        messages = messages + [msg]

        # 检查是否需要压缩
        total_tokens = sum(m.token_count for m in messages)
        threshold = int(self.config.max_tokens * self.config.compress_on_threshold)

        if total_tokens > threshold:
            messages, result = self.compress(messages)
            return messages, result

        return messages, None

    def compress(
        self,
        messages: List[ContextMessage]
    ) -> Tuple[List[ContextMessage], CompressionResult]:
        """
        压缩消息列表

        策略:
        1. 始终保留系统消息
        2. 始终保留最近 min_recent_messages 条消息
        3. 对较旧的消息按重要性过滤
        4. 将被移除的消息生成摘要插入
        """
        original_count = len(messages)
        original_tokens = sum(m.token_count for m in messages)

        if not messages:
            return messages, CompressionResult(0, 0, 0, 0, 1.0)

        # 分离系统消息
        system_msgs = [m for m in messages if m.role == MessageRole.SYSTEM] if self.config.preserve_system_messages else []
        non_system = [m for m in messages if m.role != MessageRole.SYSTEM]

        # 保留最近N条消息
        recent_count = min(self.config.min_recent_messages, len(non_system))
        recent_msgs = non_system[-recent_count:]
        older_msgs = non_system[:-recent_count] if recent_count > 0 else non_system

        # 对较旧消息按重要性过滤
        kept_older = [
            m for m in older_msgs
            if m.importance.value >= self.config.importance_threshold.value
            or (self.config.preserve_tool_results and m.role in (MessageRole.TOOL, MessageRole.OBSERVATION))
        ]
        removed_msgs = [m for m in older_msgs if m not in kept_older]

        # 生成摘要
        summary_msg = None
        if removed_msgs and self.config.enable_summarization:
            summary_text = self.summarizer.summarize_messages(
                removed_msgs, self.config.max_summary_tokens
            )
            if summary_text:
                summary_msg = ContextMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[历史摘要 - {len(removed_msgs)}条消息已压缩]\n{summary_text}",
                    importance=MessageImportance.HIGH,
                    is_compressed=True
                )

        # 组合新消息列表
        new_messages = system_msgs[:]
        if summary_msg:
            new_messages.append(summary_msg)
        new_messages.extend(kept_older)
        new_messages.extend(recent_msgs)

        # 如果仍然超出目标，强制截断旧消息
        total_tokens = sum(m.token_count for m in new_messages)
        while total_tokens > self.config.target_tokens and len(new_messages) > len(system_msgs) + recent_count + 1:
            # 移除第一条非系统非最近消息
            for i, m in enumerate(new_messages):
                if m.role != MessageRole.SYSTEM and m not in recent_msgs:
                    total_tokens -= m.token_count
                    new_messages.pop(i)
                    break
            else:
                break  # 无法再删除

        compressed_tokens = sum(m.token_count for m in new_messages)

        result = CompressionResult(
            original_token_count=original_tokens,
            compressed_token_count=compressed_tokens,
            messages_removed=len(removed_msgs),
            messages_summarized=len(removed_msgs),
            compression_ratio=compressed_tokens/max(original_tokens, 1),
            summary=summary_msg.content if summary_msg else None,
            compressed_messages=new_messages
        )

        self._compression_count += 1
        self._total_tokens_saved += (original_tokens - compressed_tokens)

        logger.info(
            f"Compression #{self._compression_count}: "
            f"{original_tokens}→{compressed_tokens} tokens "
            f"({len(original_count - len(new_messages))} msgs removed)"
            if False else
            f"Compression #{self._compression_count}: "
            f"{original_tokens}→{compressed_tokens} tokens, "
            f"{len(removed_msgs)} msgs removed"
        )

        return new_messages, result

    def should_compress(self, messages: List[ContextMessage]) -> bool:
        """检查是否需要压缩"""
        total = sum(m.token_count for m in messages)
        return total > int(self.config.max_tokens * self.config.compress_on_threshold)

    def get_token_count(self, messages: List[ContextMessage]) -> int:
        """获取总token数"""
        return sum(m.token_count for m in messages)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "compression_count": self._compression_count,
            "total_tokens_saved": self._total_tokens_saved,
            "config": {
                "max_tokens": self.config.max_tokens,
                "target_tokens": self.config.target_tokens,
                "min_recent_messages": self.config.min_recent_messages,
            }
        }

    @staticmethod
    def from_dict_messages(
        dict_messages: List[Dict[str, str]]
    ) -> List[ContextMessage]:
        """从字典格式消息转换"""
        role_map = {
            "system": MessageRole.SYSTEM,
            "user": MessageRole.USER,
            "assistant": MessageRole.ASSISTANT,
            "tool": MessageRole.TOOL,
            "observation": MessageRole.OBSERVATION,
        }
        msgs = []
        for m in dict_messages:
            role = role_map.get(m.get("role","user"), MessageRole.USER)
            content = m.get("content", "")
            msg = ContextMessage(role=role, content=content)
            msg.importance = ImportanceScorer.score(msg)
            msgs.append(msg)
        return msgs

    @staticmethod
    def to_dict_messages(
        messages: List[ContextMessage]
    ) -> List[Dict[str, str]]:
        """转换回字典格式"""
        return [{"role": m.role.value, "content": m.content} for m in messages]


def create_context_compressor(
    max_tokens: int = 4000,
    target_tokens: int = 3000,
    min_recent: int = 6
) -> ContextCompressor:
    """创建上下文压缩器"""
    config = CompressionConfig(
        max_tokens=max_tokens,
        target_tokens=target_tokens,
        min_recent_messages=min_recent
    )
    return ContextCompressor(config)


__all__ = [
    "ContextCompressor", "ContextMessage", "CompressionConfig",
    "CompressionResult", "MessageRole", "MessageImportance",
    "ImportanceScorer", "ContextSummarizer", "create_context_compressor"
]
