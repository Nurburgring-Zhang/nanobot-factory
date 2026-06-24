# =============================================================================
# NanoBot Factory - Functions Package
# 完整的Functions生态系统 - 集成16个链接的所有能力
# =============================================================================

"""
NanoBot Factory Functions Package
=================================

本包包含完整的Functions系统，基于以下开源项目深度集成：

1. OpenClaw Skills (5400+ skills)
   - 来源: VoltAgent/awesome-openclaw-skills
   - 包含: 编程、内容处理、macOS自动化等

2. Antigravity Awesome Skills (1000+ skills)
   - 来源: sickn33/antigravity-awesome-skills
   - 包含: Claude Code/Cursor专用技能

3. Claude Code Skills (50+ skills)
   - 来源: karanb192/awesome-claude-skills
   - 包含: 开发、代码审查、测试等

4. MCP Servers (Model Context Protocol)
   - 来源: apinetwork/awesome-mcp-servers
   - 包含: 文件系统、GitHub、数据库等

5. Browser-use
   - 智能浏览器自动化

6. WorldMonitor
   - 全球信息监控

7. AIRI
   - 虚拟角色/AI伴侣

8. Agent-Reach
   - 互联网搜索Agents

@author MiniMax Agent
@date 2026-03-08
"""

from .openclaw_functions import OpenClawFunctions
from .mcp_functions import MCPFunctions
from .browser_functions import BrowserFunctions
from .search_functions import SearchFunctions
from .monitor_functions import MonitorFunctions
from .ai_functions import AIFunctions

__all__ = [
    "OpenClawFunctions",
    "MCPFunctions", 
    "BrowserFunctions",
    "SearchFunctions",
    "MonitorFunctions",
    "AIFunctions",
]

__version__ = "2.0.0"
__author__ = "NanoBot Factory Team"
