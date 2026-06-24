"""
NanoBot Factory - Unified Capabilities
统一能力接口 - 整合所有Functions和Skills

这个模块提供一个统一的接口来访问所有150+能力

@author MiniMax Agent
@date 2026-03-08
"""

import logging
from typing import Dict, Any, List, Optional
from .capability_manager import CapabilityManager, CapabilityType, Capability

logger = logging.getLogger(__name__)


class UnifiedCapabilities:
    """
    统一能力接口
    整合OpenClaw, MCP, Browser, Search, Monitor, AI所有能力
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.capability_manager = CapabilityManager(config)
        
    # =========================================================================
    # 查询方法
    # =========================================================================
    
    def get_all_capabilities(self) -> List[Capability]:
        """获取所有能力"""
        return self.capability_manager.get_all_capabilities()
    
    def get_capability(self, cap_id: str) -> Optional[Capability]:
        """获取指定能力"""
        return self.capability_manager.get_capability(cap_id)
    
    def search_capabilities(self, query: str) -> List[Capability]:
        """搜索能力"""
        return self.capability_manager.search_capabilities(query)
    
    def get_capabilities_by_type(self, cap_type: CapabilityType) -> List[Capability]:
        """按类型获取能力"""
        return self.capability_manager.get_capabilities_by_type(cap_type)
    
    def get_capabilities_by_category(self, category: str) -> List[Capability]:
        """按分类获取能力"""
        return self.capability_manager.get_capabilities_by_category(category)
    
    # =========================================================================
    # 执行方法
    # =========================================================================
    
    async def execute(self, cap_id: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行能力"""
        return await self.capability_manager.execute_capability(cap_id, parameters or {})
    
    # =========================================================================
    # 统计方法
    # =========================================================================
    
    def get_total_count(self) -> int:
        """获取能力总数"""
        return self.capability_manager.get_capability_count()
    
    def get_count_by_type(self, cap_type: CapabilityType) -> int:
        """按类型获取数量"""
        return self.capability_manager.get_capability_count_by_type(cap_type)
    
    def get_count_by_category(self, category: str) -> int:
        """按分类获取数量"""
        return self.capability_manager.get_capability_count_by_category(category)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取能力摘要"""
        return {
            "total": self.get_total_count(),
            "by_type": {
                "openclaw": {
                    "coding": self.get_count_by_type(CapabilityType.OPENCLAW_CODING),
                    "content": self.get_count_by_type(CapabilityType.OPENCLAW_CONTENT),
                    "macos": self.get_count_by_type(CapabilityType.OPENCLAW_MACOS),
                    "search": self.get_count_by_type(CapabilityType.OPENCLAW_SEARCH),
                    "memory": self.get_count_by_type(CapabilityType.OPENCLAW_MEMORY),
                    "automation": self.get_count_by_type(CapabilityType.OPENCLAW_AUTOMATION),
                },
                "mcp": {
                    "filesystem": self.get_count_by_type(CapabilityType.MCP_FILESYSTEM),
                    "database": self.get_count_by_type(CapabilityType.MCP_DATABASE),
                    "version_control": self.get_count_by_type(CapabilityType.MCP_VERSION_CONTROL),
                    "cloud_storage": self.get_count_by_type(CapabilityType.MCP_CLOUD_STORAGE),
                    "communication": self.get_count_by_type(CapabilityType.MCP_COMMUNICATION),
                    "development": self.get_count_by_type(CapabilityType.MCP_DEVELOPMENT),
                },
                "browser": {
                    "navigation": self.get_count_by_type(CapabilityType.BROWSER_NAVIGATION),
                    "interaction": self.get_count_by_type(CapabilityType.BROWSER_INTERACTION),
                    "extraction": self.get_count_by_type(CapabilityType.BROWSER_EXTRACTION),
                    "automation": self.get_count_by_type(CapabilityType.BROWSER_AUTOMATION),
                },
                "search": {
                    "social": self.get_count_by_type(CapabilityType.SEARCH_SOCIAL),
                    "video": self.get_count_by_type(CapabilityType.SEARCH_VIDEO),
                    "code": self.get_count_by_type(CapabilityType.SEARCH_CODE),
                    "news": self.get_count_by_type(CapabilityType.SEARCH_NEWS),
                },
                "monitor": {
                    "news": self.get_count_by_type(CapabilityType.MONITOR_NEWS),
                    "social": self.get_count_by_type(CapabilityType.MONITOR_SOCIAL),
                    "market": self.get_count_by_type(CapabilityType.MONITOR_MARKET),
                    "sentiment": self.get_count_by_type(CapabilityType.MONITOR_SENTIMENT),
                    "trend": self.get_count_by_type(CapabilityType.MONITOR_TREND),
                },
                "ai": {
                    "companion": self.get_count_by_type(CapabilityType.AI_COMPANION),
                    "voice": self.get_count_by_type(CapabilityType.AI_VOICE),
                    "character": self.get_count_by_type(CapabilityType.AI_CHARACTER),
                    "multimodal": self.get_count_by_type(CapabilityType.AI_MULTIMODAL),
                },
            }
        }
    
    def list_all(self) -> List[str]:
        """列出所有能力"""
        return self.capability_manager.list_all_capability_names()


# =============================================================================
# Factory Function
# =============================================================================

def create_unified_capabilities(config: Dict[str, Any] = None) -> UnifiedCapabilities:
    """创建统一能力实例"""
    return UnifiedCapabilities(config)
