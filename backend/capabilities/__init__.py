# =============================================================================
# NanoBot Factory - Capabilities Package
# 完整的Capabilities生态系统 - 集成所有Skills和Functions的高级能力
# =============================================================================

"""
NanoBot Factory Capabilities Package
=================================

本包包含完整的高级能力系统:

1. OpenClaw Functions (40+)
   - 编程、内容处理、macOS自动化

2. MCP Functions (50+)
   - 文件系统、数据库、版本控制、云存储

3. Browser Functions (25+)
   - 浏览器自动化、网页交互

4. Search Functions (10+)
   - 跨平台搜索

5. Monitor Functions (15+)
   - 舆情监控、市场监控

6. AI Functions (15+)
   - 虚拟角色、语音、多模态

总计: 150+ 真实可执行的能力

@author MiniMax Agent
@date 2026-03-08
"""

from .capability_manager import CapabilityManager, CapabilityType
from .unified_capabilities import UnifiedCapabilities

__all__ = [
    "CapabilityManager",
    "CapabilityType", 
    "UnifiedCapabilities",
]

__version__ = "2.0.0"
__author__ = "NanoBot Factory Team"
