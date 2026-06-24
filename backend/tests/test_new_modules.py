"""
NanoBot Factory - New Modules Tests
测试新增的核心模块

@author MiniMax Agent
@date 2026-04-11
"""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestReActEngine:
    """ReAct循环引擎测试"""
    
    def test_agent_state_enum(self):
        """测试Agent状态枚举"""
        from agent.react_engine import AgentState
        assert hasattr(AgentState, 'IDLE')
        assert hasattr(AgentState, 'THINKING')
        assert hasattr(AgentState, 'COMPLETED')
        assert AgentState.IDLE.value == "idle"
    
    def test_loop_step_type(self):
        """测试循环步骤类型"""
        from agent.react_engine import LoopStepType
        assert hasattr(LoopStepType, 'THINK')
        assert hasattr(LoopStepType, 'ACT')
        assert hasattr(LoopStepType, 'OBSERVE')
    
    def test_loop_config(self):
        """测试循环配置"""
        from agent.react_engine import LoopConfig
        config = LoopConfig(max_iterations=10, timeout_seconds=60)
        assert config.max_iterations == 10
        assert config.timeout_seconds == 60
    
    def test_tool_executor(self):
        """测试工具执行器"""
        from agent.react_engine import ToolExecutor
        
        async def dummy_tool(query: str) -> str:
            return f"Result: {query}"
        
        executor = ToolExecutor({"search": dummy_tool})
        assert "search" in executor.get_available_tools()
    
    def test_reasoning_step(self):
        """测试推理步骤"""
        from agent.react_engine import ReasoningStep, LoopStepType
        step = ReasoningStep(
            step_id="test_001",
            step_type=LoopStepType.THINK,
            thought="Test thought"
        )
        assert step.thought == "Test thought"
        assert step.success is True


class TestDelayedQueue:
    """延迟队列测试"""
    
    def test_message_envelope(self):
        """测试消息包装器"""
        from agent.delayed_queue import MessageEnvelope
        msg = MessageEnvelope(id="test_001", content="Hello")
        assert msg.id == "test_001"
        assert msg.content == "Hello"
        assert msg.is_ready()
    
    def test_dlq_reason(self):
        """测试死信原因枚举"""
        from agent.delayed_queue import DLQReason
        assert hasattr(DLQReason, 'MAX_RETRIES_EXCEEDED')
        assert hasattr(DLQReason, 'PROCESSING_TIMEOUT')
    
    def test_retry_policy(self):
        """测试重试策略"""
        from agent.delayed_queue import RetryPolicy
        policy = RetryPolicy(max_retries=3, initial_delay_ms=1000)
        assert policy.max_retries == 3
        # 指数退避
        assert policy.get_delay(0) == 1.0  # 1000ms
        assert policy.get_delay(1) == 2.0  # 2000ms
    
    @pytest.mark.asyncio
    async def test_delayed_queue_schedule(self):
        """测试延迟队列调度"""
        from agent.delayed_queue import DelayedQueue
        queue = DelayedQueue(name="test_queue", default_delay_ms=100)
        msg_id = queue.schedule(content="Test message")
        assert msg_id is not None
        assert queue.get_pending_count() == 1
        queue.close()
    
    @pytest.mark.asyncio
    async def test_dlq_add(self):
        """测试死信队列"""
        from agent.delayed_queue import DeadLetterQueue, MessageEnvelope, DLQReason
        dlq = DeadLetterQueue(name="test_dlq")
        msg = MessageEnvelope(id="failed_001", content="Failed message")
        entry_id = dlq.add(msg, DLQReason.MAX_RETRIES_EXCEEDED)
        assert entry_id is not None
        entries = dlq.get_entries()
        assert len(entries) == 1
        dlq.close()


class TestAlertManager:
    """告警管理器测试"""
    
    def test_alert_levels(self):
        """测试告警级别"""
        from monitor.alert_manager import AlertLevel
        assert hasattr(AlertLevel, 'DEBUG')
        assert hasattr(AlertLevel, 'WARNING')
        assert hasattr(AlertLevel, 'ERROR')
        assert hasattr(AlertLevel, 'CRITICAL')
    
    def test_alert_categories(self):
        """测试告警类别"""
        from monitor.alert_manager import AlertCategory
        assert hasattr(AlertCategory, 'SYSTEM')
        assert hasattr(AlertCategory, 'SECURITY')
        assert hasattr(AlertCategory, 'PERFORMANCE')
    
    def test_webhook_handler(self):
        """测试Webhook处理器"""
        from monitor.alert_manager import WebhookAlertHandler
        handler = WebhookAlertHandler(webhook_url="https://example.com/webhook")
        assert handler.webhook_url == "https://example.com/webhook"
    
    def test_aggregator(self):
        """测试告警聚合器"""
        from monitor.alert_manager import AlertAggregator, Alert, AlertLevel, AlertCategory
        agg = AlertAggregator(window_seconds=60, max_per_window=5)
        alert = Alert(
            id="test", level=AlertLevel.WARNING,
            category=AlertCategory.SYSTEM,
            title="Test", message="Test", source="test",
            timestamp=__import__('datetime').datetime.now()
        )
        assert agg.should_send(alert) is True
    
    @pytest.mark.asyncio
    async def test_alert_manager_send(self):
        """测试告警发送"""
        from monitor.alert_manager import AlertManager, AlertLevel, AlertCategory
        manager = AlertManager()
        alert_id = await manager.send_alert(
            AlertLevel.WARNING, AlertCategory.SYSTEM,
            "Test Alert", "This is a test"
        )
        assert alert_id is not None
        stats = manager.get_statistics()
        assert stats["total_alerts"] == 1


class TestMemoryPersistence:
    """记忆持久化测试"""
    
    def test_redis_storage_init(self):
        """测试Redis存储初始化"""
        from agent.memory_persistence import RedisMemoryStorage
        storage = RedisMemoryStorage()
        assert storage._use_fallback is True  # Redis未连接时使用fallback
    
    @pytest.mark.asyncio
    async def test_save_and_get_memory(self):
        """测试保存和获取记忆"""
        from agent.memory_persistence import RedisMemoryStorage
        storage = RedisMemoryStorage()
        
        # 保存记忆
        success = await storage.save_memory(
            memory_id="test_001",
            content="Test memory content",
            memory_type="short_term"
        )
        assert success is True
        
        # 获取记忆
        memory = await storage.get_memory("test_001", "short_term")
        assert memory is not None
        
        await storage.close()
    
    @pytest.mark.asyncio
    async def test_delete_memory(self):
        """测试删除记忆"""
        from agent.memory_persistence import RedisMemoryStorage
        storage = RedisMemoryStorage()
        
        await storage.save_memory("del_001", "To be deleted", "short_term")
        success = await storage.delete_memory("del_001", "short_term")
        assert success is True
        
        await storage.close()
    
    @pytest.mark.asyncio
    async def test_list_memories(self):
        """测试列出记忆"""
        from agent.memory_persistence import RedisMemoryStorage
        storage = RedisMemoryStorage()
        
        await storage.save_memory("list_001", "Memory 1", "short_term")
        await storage.save_memory("list_002", "Memory 2", "short_term")
        
        memories = await storage.list_memories("short_term", limit=10)
        assert len(memories) >= 2
        
        await storage.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
