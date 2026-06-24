"""
NanoBot Factory - Backend Tests
Unit tests for core backend modules
"""

import pytest
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestMemorySystem:
    """Test cases for memory system"""

    @pytest.mark.asyncio
    async def test_memory_save(self):
        """Test memory save functionality"""
        from agent.memory import EnhancedMemorySystem
        
        memory = EnhancedMemorySystem()
        
        # Test saving a memory
        session_id = "test_session_001"
        content = "This is a test conversation about AI agents"
        
        # Save should not raise exception
        result = await memory.add_memory(session_id, content)
        assert result is not None or result == True

    @pytest.mark.asyncio
    async def test_memory_retrieve(self):
        """Test memory retrieval"""
        from agent.memory import EnhancedMemorySystem
        
        memory = EnhancedMemorySystem()
        
        # Test retrieval
        session_id = "test_session_001"
        user_id = "test_user_001"
        result = await memory.get_session_memories(session_id, user_id)
        assert result is not None

    @pytest.mark.asyncio
    async def test_importance_levels(self):
        """Test importance level handling"""
        from agent.memory import ImportanceLevel
        
        # Verify importance levels exist
        assert hasattr(ImportanceLevel, 'CRITICAL')
        assert hasattr(ImportanceLevel, 'HIGH')
        assert hasattr(ImportanceLevel, 'NORMAL')
        assert hasattr(ImportanceLevel, 'LOW')
        assert hasattr(ImportanceLevel, 'DISCARD')


class TestMessageBus:
    """Test cases for message bus"""

    @pytest.mark.asyncio
    async def test_message_priority(self):
        """Test message priority enum"""
        from agent.message_bus import MessagePriority
        
        # Verify priority levels
        assert hasattr(MessagePriority, 'CRITICAL')
        assert hasattr(MessagePriority, 'HIGH')
        assert hasattr(MessagePriority, 'NORMAL')
        assert hasattr(MessagePriority, 'LOW')
        assert hasattr(MessagePriority, 'BULK')

    @pytest.mark.asyncio
    async def test_channel_subscription(self):
        """Test channel subscription"""
        from agent.message_bus import Channel
        
        channel = Channel(name="test_channel")
        assert channel.name == "test_channel"

    def test_message_creation(self):
        """Test message creation"""
        from agent.message_bus import Message, MessageType, MessagePriority
        import uuid
        from datetime import datetime
        
        msg = Message(
            id=str(uuid.uuid4()),
            type=MessageType.REQUEST,
            priority=MessagePriority.NORMAL,
            channel="test_channel",
            sender="user",
            receiver="agent",
            content="test message",
            timestamp=datetime.now()
        )
        assert msg.content == "test message"


class TestContextBuilder:
    """Test cases for context builder"""

    @pytest.mark.asyncio
    async def test_context_creation(self):
        """Test context creation"""
        from agent.context_builder import ContextBuilder
        
        builder = ContextBuilder()
        assert builder is not None

    def test_message_roles(self):
        """Test message role enum"""
        from agent.context_builder import MessageRole
        
        assert hasattr(MessageRole, 'SYSTEM')
        assert hasattr(MessageRole, 'USER')
        assert hasattr(MessageRole, 'ASSISTANT')
        assert hasattr(MessageRole, 'TOOL')


class TestDatabase:
    """Test cases for database module"""

    def test_database_config(self):
        """Test database configuration"""
        from database import DatabaseConfig
        
        config = DatabaseConfig(
            db_path="test.db",
            pool_size=5
        )
        assert config.db_path == "test.db"
        assert config.pool_size == 5


class TestRateLimiter:
    """Test cases for rate limiter"""

    def test_rate_limiter_init(self):
        """Test rate limiter initialization"""
        from server import RateLimiter
        
        limiter = RateLimiter(requests=60, window=60)
        assert limiter is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
