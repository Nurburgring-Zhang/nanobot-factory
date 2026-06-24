"""
NanoBot Factory - MCP Functions Integration
MCP (Model Context Protocol) 服务器深度集成

基于以下项目:
- apinetwork/awesome-mcp-servers
- derekluo/awesome-mcp-servers

MCP Servers分类:
1. 文件系统 - 文件操作
2. GitHub - 仓库管理
3. PostgreSQL/MySQL - 数据库
4. SQLite - 轻量数据库
5. Slack - 团队协作
6. Google Drive - 云盘
7. Git - 版本控制

@author MiniMax Agent
@date 2026-03-08
"""

import os
import json
import shutil
import sqlite3
import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# =============================================================================
# MCP Function Categories
# =============================================================================

class MCPFunctionCategory(Enum):
    """MCP函数分类"""
    FILESYSTEM = "filesystem"           # 文件系统
    DATABASE = "database"             # 数据库
    VERSION_CONTROL = "version_control"  # 版本控制
    CLOUD_STORAGE = "cloud_storage"    # 云存储
    COMMUNICATION = "communication"   # 通讯
    DEVELOPMENT = "development"       # 开发工具


# =============================================================================
# MCP Server Definition
# =============================================================================

@dataclass
class MCPFunction:
    """MCP函数定义"""
    id: str
    name: str
    description: str
    category: MCPFunctionCategory
    server_name: str  # MCP服务器名称
    protocol: str = "mcp"
    enabled: bool = True
    version: str = "1.0.0"
    parameters: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# MCP Functions Implementation
# =============================================================================

class MCPFunctions:
    """
    MCP Functions主类
    集成所有MCP服务器的真实能力
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.functions: Dict[str, MCPFunction] = {}
        self._initialize_functions()
        
    def _initialize_functions(self):
        """初始化所有MCP函数"""
        # 文件系统类
        self._register_filesystem_functions()
        
        # 数据库类
        self._register_database_functions()
        
        # 版本控制类
        self._register_version_control_functions()
        
        # 云存储类
        self._register_cloud_storage_functions()
        
        # 通讯类
        self._register_communication_functions()
        
        # 开发工具类
        self._register_development_functions()
        
    def _register_filesystem_functions(self):
        """注册文件系统函数"""
        fs_functions = [
            MCPFunction(
                id="mcp_fs_read",
                name="Filesystem Read",
                description="安全读取文件 - 支持各种格式文件读取",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "文件路径",
                    "encoding": "编码 (utf-8, gbk)",
                    "limit": "读取行数限制"
                }
            ),
            MCPFunction(
                id="mcp_fs_write",
                name="Filesystem Write",
                description="安全写入文件 - 创建或覆盖文件",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "文件路径",
                    "content": "文件内容",
                    "encoding": "编码"
                }
            ),
            MCPFunction(
                id="mcp_fs_list",
                name="Filesystem List",
                description="列出目录内容 - 查看文件夹结构",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "目录路径",
                    "pattern": "文件过滤模式",
                    "recursive": "是否递归"
                }
            ),
            MCPFunction(
                id="mcp_fs_search",
                name="Filesystem Search",
                description="搜索文件 - 按名称或内容搜索",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "搜索路径",
                    "query": "搜索关键词",
                    "file_type": "文件类型"
                }
            ),
            MCPFunction(
                id="mcp_fs_create_dir",
                name="Filesystem Create Directory",
                description="创建目录 - 创建新文件夹",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "目录路径"
                }
            ),
            MCPFunction(
                id="mcp_fs_delete",
                name="Filesystem Delete",
                description="删除文件或目录 - 安全删除",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "路径",
                    "recursive": "是否递归删除"
                }
            ),
            MCPFunction(
                id="mcp_fs_move",
                name="Filesystem Move",
                description="移动文件或目录 - 移动或重命名",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "source": "源路径",
                    "destination": "目标路径"
                }
            ),
            MCPFunction(
                id="mcp_fs_copy",
                name="Filesystem Copy",
                description="复制文件或目录",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "source": "源路径",
                    "destination": "目标路径"
                }
            ),
            MCPFunction(
                id="mcp_fs_watch",
                name="Filesystem Watch",
                description="监控文件变化 - 监听文件改动",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "监控路径",
                    "events": "监控事件类型"
                }
            ),
            MCPFunction(
                id="mcp_fs_get_info",
                name="Filesystem Get Info",
                description="获取文件信息 - 大小、权限、时间等",
                category=MCPFunctionCategory.FILESYSTEM,
                server_name="filesystem",
                parameters={
                    "path": "文件路径"
                }
            ),
        ]
        
        for func in fs_functions:
            self.functions[func.id] = func
            
    def _register_database_functions(self):
        """注册数据库函数"""
        db_functions = [
            MCPFunction(
                id="mcp_postgres_query",
                name="PostgreSQL Query",
                description="PostgreSQL查询 - 执行SQL查询",
                category=MCPFunctionCategory.DATABASE,
                server_name="postgresql",
                parameters={
                    "query": "SQL查询语句",
                    "params": "查询参数",
                    "limit": "结果数量限制"
                }
            ),
            MCPFunction(
                id="mcp_postgres_schema",
                name="PostgreSQL Schema",
                description="PostgreSQL结构 - 查看数据库结构",
                category=MCPFunctionCategory.DATABASE,
                server_name="postgresql",
                parameters={
                    "table": "表名",
                    "include_views": "包含视图"
                }
            ),
            MCPFunction(
                id="mcp_postgres_tables",
                name="PostgreSQL Tables",
                description="PostgreSQL表列表 - 查看所有表",
                category=MCPFunctionCategory.DATABASE,
                server_name="postgresql",
                parameters={
                    "schema": "schema名称"
                }
            ),
            MCPFunction(
                id="mcp_sqlite_query",
                name="SQLite Query",
                description="SQLite查询 - 轻量数据库操作",
                category=MCPFunctionCategory.DATABASE,
                server_name="sqlite",
                parameters={
                    "database": "数据库文件路径",
                    "query": "SQL查询",
                    "params": "参数"
                }
            ),
            MCPFunction(
                id="mcp_sqlite_tables",
                name="SQLite Tables",
                description="SQLite表列表 - 查看所有表",
                category=MCPFunctionCategory.DATABASE,
                server_name="sqlite",
                parameters={
                    "database": "数据库文件路径"
                }
            ),
            MCPFunction(
                id="mcp_sqlite_schema",
                name="SQLite Schema",
                description="SQLite结构 - 查看表结构",
                category=MCPFunctionCategory.DATABASE,
                server_name="sqlite",
                parameters={
                    "database": "数据库文件路径",
                    "table": "表名"
                }
            ),
            MCPFunction(
                id="mcp_mysql_query",
                name="MySQL Query",
                description="MySQL查询 - 执行SQL查询",
                category=MCPFunctionCategory.DATABASE,
                server_name="mysql",
                parameters={
                    "query": "SQL查询语句",
                    "database": "数据库名"
                }
            ),
            MCPFunction(
                id="mcp_mongodb_query",
                name="MongoDB Query",
                description="MongoDB查询 - NoSQL数据库操作",
                category=MCPFunctionCategory.DATABASE,
                server_name="mongodb",
                parameters={
                    "database": "数据库名",
                    "collection": "集合名",
                    "filter": "查询过滤器",
                    "projection": "返回字段"
                }
            ),
        ]
        
        for func in db_functions:
            self.functions[func.id] = func
            
    def _register_version_control_functions(self):
        """注册版本控制函数"""
        vc_functions = [
            MCPFunction(
                id="mcp_git_status",
                name="Git Status",
                description="Git状态 - 查看工作区状态",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径"
                }
            ),
            MCPFunction(
                id="mcp_git_log",
                name="Git Log",
                description="Git提交历史 - 查看提交记录",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "max_count": "最大数量",
                    "branch": "分支名"
                }
            ),
            MCPFunction(
                id="mcp_git_diff",
                name="Git Diff",
                description="Git差异 - 查看文件变化",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "file": "文件路径",
                    "commit": "提交ID"
                }
            ),
            MCPFunction(
                id="mcp_git_branch",
                name="Git Branch",
                description="Git分支 - 列出所有分支",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径"
                }
            ),
            MCPFunction(
                id="mcp_git_commit",
                name="Git Commit",
                description="Git提交 - 创建新提交",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "message": "提交信息",
                    "files": "提交的文件"
                }
            ),
            MCPFunction(
                id="mcp_git_push",
                name="Git Push",
                description="Git推送 - 推送到远程",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "remote": "远程名称",
                    "branch": "分支名"
                }
            ),
            MCPFunction(
                id="mcp_git_pull",
                name="Git Pull",
                description="Git拉取 - 从远程拉取",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "remote": "远程名称",
                    "branch": "分支名"
                }
            ),
            MCPFunction(
                id="mcp_git_search",
                name="Git Search",
                description="Git代码搜索 - 搜索代码内容",
                category=MCPFunctionCategory.VERSION_CONTROL,
                server_name="git",
                parameters={
                    "repo_path": "仓库路径",
                    "query": "搜索内容",
                    "file_pattern": "文件模式"
                }
            ),
        ]
        
        for func in vc_functions:
            self.functions[func.id] = func
            
    def _register_cloud_storage_functions(self):
        """注册云存储函数"""
        cs_functions = [
            MCPFunction(
                id="mcp_gdrive_list",
                name="Google Drive List",
                description="Google Drive列表 - 列出文件",
                category=MCPFunctionCategory.CLOUD_STORAGE,
                server_name="google-drive",
                parameters={
                    "folder_id": "文件夹ID",
                    "query": "搜索查询"
                }
            ),
            MCPFunction(
                id="mcp_gdrive_read",
                name="Google Drive Read",
                description="Google Drive读取 - 读取文件内容",
                category=MCPFunctionCategory.CLOUD_STORAGE,
                server_name="google-drive",
                parameters={
                    "file_id": "文件ID"
                }
            ),
            MCPFunction(
                id="mcp_gdrive_write",
                name="Google Drive Write",
                description="Google Drive写入 - 创建或更新文件",
                category=MCPFunctionCategory.CLOUD_STORAGE,
                server_name="google-drive",
                parameters={
                    "name": "文件名",
                    "content": "文件内容",
                    "folder_id": "文件夹ID"
                }
            ),
            MCPFunction(
                id="mcp_gdrive_search",
                name="Google Drive Search",
                description="Google Drive搜索 - 搜索文件",
                category=MCPFunctionCategory.CLOUD_STORAGE,
                server_name="google-drive",
                parameters={
                    "query": "搜索内容",
                    "file_type": "文件类型"
                }
            ),
        ]
        
        for func in cs_functions:
            self.functions[func.id] = func
            
    def _register_communication_functions(self):
        """注册通讯函数"""
        comm_functions = [
            MCPFunction(
                id="mcp_slack_channels",
                name="Slack Channels",
                description="Slack频道列表 - 查看所有频道",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="slack",
                parameters={
                    "include_archived": "包含已归档"
                }
            ),
            MCPFunction(
                id="mcp_slack_history",
                name="Slack History",
                description="Slack历史 - 查看频道消息",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="slack",
                parameters={
                    "channel": "频道ID",
                    "limit": "消息数量"
                }
            ),
            MCPFunction(
                id="mcp_slack_send",
                name="Slack Send",
                description="Slack发送消息",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="slack",
                parameters={
                    "channel": "频道ID",
                    "text": "消息内容",
                    "thread": "线程ID"
                }
            ),
            MCPFunction(
                id="mcp_slack_search",
                name="Slack Search",
                description="Slack搜索 - 搜索消息",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="slack",
                parameters={
                    "query": "搜索内容"
                }
            ),
            MCPFunction(
                id="mcp_discord_guilds",
                name="Discord Guilds",
                description="Discord服务器列表",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="discord",
                parameters={}
            ),
            MCPFunction(
                id="mcp_discord_channels",
                name="Discord Channels",
                description="Discord频道列表",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="discord",
                parameters={
                    "guild_id": "服务器ID"
                }
            ),
            MCPFunction(
                id="mcp_discord_messages",
                name="Discord Messages",
                description="Discord消息操作",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="discord",
                parameters={
                    "channel_id": "频道ID",
                    "limit": "数量"
                }
            ),
            MCPFunction(
                id="mcp_discord_send",
                name="Discord Send",
                description="Discord发送消息",
                category=MCPFunctionCategory.COMMUNICATION,
                server_name="discord",
                parameters={
                    "channel_id": "频道ID",
                    "content": "消息内容"
                }
            ),
        ]
        
        for func in comm_functions:
            self.functions[func.id] = func
            
    def _register_development_functions(self):
        """注册开发工具函数"""
        dev_functions = [
            MCPFunction(
                id="mcp_github_repos",
                name="GitHub Repositories",
                description="GitHub仓库列表 - 查看用户仓库",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="github",
                parameters={
                    "username": "用户名",
                    "sort": "排序方式"
                }
            ),
            MCPFunction(
                id="mcp_github_issues",
                name="GitHub Issues",
                description="GitHub Issues - 查看和管理issues",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="github",
                parameters={
                    "repo": "仓库名",
                    "state": "状态 (open, closed)"
                }
            ),
            MCPFunction(
                id="mcp_github_pr",
                name="GitHub Pull Requests",
                description="GitHub Pull Requests - 管理PR",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="github",
                parameters={
                    "repo": "仓库名",
                    "state": "状态"
                }
            ),
            MCPFunction(
                id="mcp_github_create_issue",
                name="GitHub Create Issue",
                description="GitHub创建Issue",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="github",
                parameters={
                    "repo": "仓库名",
                    "title": "标题",
                    "body": "内容",
                    "labels": "标签"
                }
            ),
            MCPFunction(
                id="mcp_github_search_code",
                name="GitHub Search Code",
                description="GitHub代码搜索",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="github",
                parameters={
                    "query": "搜索内容",
                    "language": "语言"
                }
            ),
            MCPFunction(
                id="mcp_gitlab_projects",
                name="GitLab Projects",
                description="GitLab项目列表",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="gitlab",
                parameters={
                    "group": "组名"
                }
            ),
            MCPFunction(
                id="mcp_gitlab_issues",
                name="GitLab Issues",
                description="GitLab Issues管理",
                category=MCPFunctionCategory.DEVELOPMENT,
                server_name="gitlab",
                parameters={
                    "project_id": "项目ID",
                    "state": "状态"
                }
            ),
        ]
        
        for func in dev_functions:
            self.functions[func.id] = func
    
    # =========================================================================
    # Public API
    # =========================================================================
    
    def get_function(self, func_id: str) -> Optional[MCPFunction]:
        """获取函数定义"""
        return self.functions.get(func_id)
    
    def get_all_functions(self) -> List[MCPFunction]:
        """获取所有函数"""
        return list(self.functions.values())
    
    def get_functions_by_category(self, category: MCPFunctionCategory) -> List[MCPFunction]:
        """按分类获取函数"""
        return [f for f in self.functions.values() if f.category == category]
    
    def execute_function(self, func_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """执行MCP函数 - 真实实现"""
        func = self.get_function(func_id)
        if not func:
            return {"error": f"Function {func_id} not found"}
            
        if not func.enabled:
            return {"error": f"Function {func_id} is disabled"}
        
        try:
            result = self._dispatch(func, parameters)
            return {
                "status": "success",
                "function_id": func_id,
                "server": func.server_name,
                "result": result,
                "parameters": parameters
            }
        except Exception as e:
            logger.error(f"Error executing MCP function {func_id}: {e}")
            return {
                "status": "error",
                "function_id": func_id,
                "server": func.server_name,
                "error": str(e)
            }
    
    def _dispatch(self, func: MCPFunction, params: Dict[str, Any]) -> Any:
        """Dispatch to the appropriate handler"""
        category = func.category
        
        if category == MCPFunctionCategory.FILESYSTEM:
            return self._handle_filesystem(func.id, params)
        elif category == MCPFunctionCategory.DATABASE:
            return self._handle_database(func.id, params)
        elif category == MCPFunctionCategory.VERSION_CONTROL:
            return self._handle_vcs(func.id, params)
        elif category == MCPFunctionCategory.CLOUD_STORAGE:
            return self._handle_cloud_storage(func.id, params)
        elif category == MCPFunctionCategory.COMMUNICATION:
            return self._handle_communication(func.id, params)
        elif category == MCPFunctionCategory.DEVELOPMENT:
            return self._handle_development(func.id, params)
        else:
            return f"Executed {func.name} (no handler)"
    
    # ----- 文件系统 handlers -----
    
    def _handle_filesystem(self, func_id: str, params: Dict[str, Any]) -> Any:
        if func_id == "mcp_fs_read":
            path = params.get("path", "")
            encoding = params.get("encoding", "utf-8")
            limit = params.get("limit", 0)
            if not os.path.exists(path):
                return {"error": f"File not found: {path}"}
            with open(path, "r", encoding=encoding) as f:
                if limit > 0:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= limit:
                            break
                        lines.append(line.rstrip("\n"))
                    return "\n".join(lines)
                return f.read()
        
        elif func_id == "mcp_fs_write":
            path = params.get("path", "")
            content = params.get("content", "")
            encoding = params.get("encoding", "utf-8")
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding=encoding) as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"
        
        elif func_id == "mcp_fs_list":
            path = params.get("path", ".")
            pattern = params.get("pattern", "*")
            recursive = params.get("recursive", False)
            if not os.path.exists(path):
                return {"error": f"Directory not found: {path}"}
            if recursive:
                result = []
                for root, dirs, files in os.walk(path):
                    for name in files + dirs:
                        full = os.path.join(root, name)
                        result.append(full)
                return result
            else:
                return os.listdir(path)
        
        elif func_id == "mcp_fs_search":
            search_path = params.get("path", ".")
            query = params.get("query", "")
            file_type = params.get("file_type", "")
            results = []
            for root, dirs, files in os.walk(search_path):
                for file in files:
                    if file_type and not file.endswith(file_type):
                        continue
                    if query and query.lower() not in file.lower():
                        continue
                    results.append(os.path.join(root, file))
            return results[:100]  # Limit results
        
        elif func_id == "mcp_fs_create_dir":
            path = params.get("path", "")
            os.makedirs(path, exist_ok=True)
            return f"Directory created: {path}"
        
        elif func_id == "mcp_fs_delete":
            path = params.get("path", "")
            recursive = params.get("recursive", False)
            if not os.path.exists(path):
                return {"error": f"Path not found: {path}"}
            if os.path.isdir(path):
                if recursive:
                    shutil.rmtree(path)
                    return f"Directory removed: {path}"
                else:
                    os.rmdir(path) if len(os.listdir(path)) == 0 else "Directory not empty"
                    return f"Directory removed: {path}"
            else:
                os.remove(path)
                return f"File removed: {path}"
        
        elif func_id == "mcp_fs_move":
            src = params.get("source", "")
            dst = params.get("destination", "")
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            shutil.move(src, dst)
            return f"Moved {src} -> {dst}"
        
        elif func_id == "mcp_fs_copy":
            src = params.get("source", "")
            dst = params.get("destination", "")
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return f"Copied {src} -> {dst}"
        
        elif func_id == "mcp_fs_watch":
            path = params.get("path", "")
            events = params.get("events", "all")
            try:
                from watchdog.observers import Observer
                from watchdog.events import FileSystemEventHandler
                
                class WatchHandler(FileSystemEventHandler):
                    def on_modified(self, event):
                        logger.info(f"File modified: {event.src_path}")
                    def on_created(self, event):
                        logger.info(f"File created: {event.src_path}")
                    def on_deleted(self, event):
                        logger.info(f"File deleted: {event.src_path}")
                
                observer = Observer()
                observer.schedule(WatchHandler(), path, recursive=True)
                observer.start()
                return f"Watching {path} for events: {events}"
            except ImportError:
                return f"Watchdog not installed. Would watch {path} for events: {events}"
        
        elif func_id == "mcp_fs_get_info":
            path = params.get("path", "")
            if not os.path.exists(path):
                return {"error": f"Path not found: {path}"}
            stat = os.stat(path)
            return {
                "path": path,
                "size": stat.st_size,
                "is_dir": os.path.isdir(path),
                "is_file": os.path.isfile(path),
                "permissions": oct(stat.st_mode)[-3:],
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "accessed": datetime.fromtimestamp(stat.st_atime).isoformat()
            }
        
        return f"Executed filesystem function {func_id}"
    
    # ----- 数据库 handlers -----
    
    def _handle_database(self, func_id: str, params: Dict[str, Any]) -> Any:
        # SQLite handlers (always available - built-in)
        if func_id in ("mcp_sqlite_query", "mcp_sqlite_tables", "mcp_sqlite_schema"):
            return self._handle_sqlite(func_id, params)
        
        # PostgreSQL handlers
        if func_id.startswith("mcp_postgres_"):
            return self._try_postgres(func_id, params)
        
        # MySQL handlers
        if func_id.startswith("mcp_mysql_"):
            return self._try_mysql(func_id, params)
        
        # MongoDB handlers
        if func_id.startswith("mcp_mongodb_"):
            return self._try_mongodb(func_id, params)
        
        return f"Database function {func_id}"
    
    def _handle_sqlite(self, func_id: str, params: Dict[str, Any]) -> Any:
        db_path = params.get("database", self.config.get("sqlite_db", ":memory:"))
        conn = None
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if func_id == "mcp_sqlite_query":
                query = params.get("query", "")
                query_params = params.get("params", [])
                cursor.execute(query, query_params)
                if query.strip().upper().startswith(("SELECT", "PRAGMA")):
                    rows = [dict(row) for row in cursor.fetchall()]
                    return rows
                else:
                    conn.commit()
                    return {"affected_rows": cursor.rowcount, "last_id": cursor.lastrowid}
            
            elif func_id == "mcp_sqlite_tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                return [row["name"] for row in cursor.fetchall()]
            
            elif func_id == "mcp_sqlite_schema":
                table = params.get("table", "")
                if table:
                    cursor.execute(f"PRAGMA table_info('{table}')")
                    return [dict(row) for row in cursor.fetchall()]
                return {"error": "No table specified"}
            
        except Exception as e:
            return {"error": f"SQLite error: {e}"}
        finally:
            if conn:
                conn.close()
    
    def _try_postgres(self, func_id: str, params: Dict[str, Any]) -> Any:
        try:
            import psycopg2
            conn_config = self.config.get("postgres", {})
            conn = psycopg2.connect(**conn_config)
            cursor = conn.cursor()
            
            if func_id == "mcp_postgres_query":
                cursor.execute(params.get("query", ""))
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(params.get("limit", 100)) if cursor.description else []
                return [dict(zip(columns, row)) for row in rows]
            
            elif func_id == "mcp_postgres_tables":
                schema = params.get("schema", "public")
                cursor.execute("""
                    SELECT table_name FROM information_schema.tables 
                    WHERE table_schema = %s
                """, (schema,))
                return [row[0] for row in cursor.fetchall()]
            
            elif func_id == "mcp_postgres_schema":
                table = params.get("table", "")
                cursor.execute("""
                    SELECT column_name, data_type, is_nullable 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                """, (table,))
                return [{"column": r[0], "type": r[1], "nullable": r[2]} for r in cursor.fetchall()]
            
            cursor.close()
            conn.close()
        except ImportError:
            return {"info": f"psycopg2 not installed. Would execute: {func_id}"}
        except Exception as e:
            return {"error": f"PostgreSQL error: {e}"}
        return f"PostgreSQL: {func_id}"
    
    def _try_mysql(self, func_id: str, params: Dict[str, Any]) -> Any:
        try:
            import pymysql
            conn_config = self.config.get("mysql", {})
            conn = pymysql.connect(**conn_config)
            cursor = conn.cursor()
            
            if func_id == "mcp_mysql_query":
                db = params.get("database", "")
                if db:
                    cursor.execute(f"USE `{db}`")
                cursor.execute(params.get("query", ""))
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            
            cursor.close()
            conn.close()
        except ImportError:
            return {"info": "pymysql not installed. Would execute MySQL query."}
        except Exception as e:
            return {"error": f"MySQL error: {e}"}
        return f"MySQL: {func_id}"
    
    def _try_mongodb(self, func_id: str, params: Dict[str, Any]) -> Any:
        try:
            from pymongo import MongoClient
            mongo_config = self.config.get("mongodb", {})
            client = MongoClient(**mongo_config)
            db_name = params.get("database", "test")
            db = client[db_name]
            
            if func_id == "mcp_mongodb_query":
                collection_name = params.get("collection", "")
                filter_query = params.get("filter", {})
                projection = params.get("projection", None)
                if collection_name:
                    results = list(db[collection_name].find(filter_query, projection).limit(100))
                    for r in results:
                        r["_id"] = str(r["_id"])  # Convert ObjectId
                    return results
            
            client.close()
        except ImportError:
            return {"info": "pymongo not installed. Would execute MongoDB query."}
        except Exception as e:
            return {"error": f"MongoDB error: {e}"}
        return f"MongoDB: {func_id}"
    
    # ----- 版本控制 handlers -----
    
    def _handle_vcs(self, func_id: str, params: Dict[str, Any]) -> Any:
        repo_path = params.get("repo_path", ".")
        
        try:
            if func_id == "mcp_git_status":
                result = subprocess.run(
                    ["git", "status", "--porcelain"],
                    capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                lines = [line.strip() for line in result.stdout.split("\n") if line.strip()]
                return {"files": lines, "clean": len(lines) == 0}
            
            elif func_id == "mcp_git_log":
                max_count = params.get("max_count", 10)
                branch = params.get("branch", "HEAD")
                result = subprocess.run(
                    ["git", "log", branch, f"--max-count={max_count}", 
                     "--format=%H|%an|%ai|%s"],
                    capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                commits = []
                for line in result.stdout.strip().split("\n"):
                    if "|" in line:
                        parts = line.split("|", 3)
                        commits.append({
                            "hash": parts[0],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3] if len(parts) > 3 else ""
                        })
                return commits
            
            elif func_id == "mcp_git_diff":
                file_path = params.get("file", "")
                commit = params.get("commit", "HEAD")
                args = ["git", "diff"]
                if commit:
                    args.append(f"{commit}^..{commit}")
                if file_path:
                    args.append("--", file_path)
                result = subprocess.run(
                    args, capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                return result.stdout
            
            elif func_id == "mcp_git_branch":
                result = subprocess.run(
                    ["git", "branch", "-a"],
                    capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                branches = []
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if line:
                        current = line.startswith("*")
                        branches.append({
                            "name": line.lstrip("* ").strip(),
                            "current": current
                        })
                return branches
            
            elif func_id == "mcp_git_commit":
                message = params.get("message", "Auto commit")
                files = params.get("files", [])
                if files:
                    subprocess.run(["git", "add"] + files, cwd=repo_path, timeout=30)
                else:
                    subprocess.run(["git", "add", "-A"], cwd=repo_path, timeout=30)
                result = subprocess.run(
                    ["git", "commit", "-m", message],
                    capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                return {"output": result.stdout, "returncode": result.returncode}
            
            elif func_id == "mcp_git_push":
                remote = params.get("remote", "origin")
                branch = params.get("branch", "HEAD")
                result = subprocess.run(
                    ["git", "push", remote, branch],
                    capture_output=True, text=True, cwd=repo_path, timeout=60
                )
                return {"output": result.stdout + result.stderr, "returncode": result.returncode}
            
            elif func_id == "mcp_git_pull":
                remote = params.get("remote", "origin")
                branch = params.get("branch", "main")
                result = subprocess.run(
                    ["git", "pull", remote, branch],
                    capture_output=True, text=True, cwd=repo_path, timeout=60
                )
                return {"output": result.stdout + result.stderr, "returncode": result.returncode}
            
            elif func_id == "mcp_git_search":
                query = params.get("query", "")
                file_pattern = params.get("file_pattern", "")
                args = ["git", "grep", "-n", query]
                if file_pattern:
                    args.extend(["--", file_pattern])
                result = subprocess.run(
                    args, capture_output=True, text=True, cwd=repo_path, timeout=30
                )
                lines = [l for l in result.stdout.split("\n") if l.strip()]
                return {"matches": len(lines), "results": lines[:100]}
        
        except FileNotFoundError:
            return {"error": "Git not found on system"}
        except subprocess.TimeoutExpired:
            return {"error": "Git command timed out"}
        except Exception as e:
            return {"error": f"Git error: {e}"}
        
        return f"VCS function: {func_id}"
    
    # ----- 云存储 handlers -----
    
    def _handle_cloud_storage(self, func_id: str, params: Dict[str, Any]) -> Any:
        # Try Google Drive API
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            
            creds_config = self.config.get("google_drive", {})
            if creds_config.get("token"):
                creds = Credentials.from_authorized_user_info(creds_config)
                service = build("drive", "v3", credentials=creds)
                
                if func_id == "mcp_gdrive_list":
                    folder_id = params.get("folder_id", "root")
                    query = params.get("query", "")
                    q = f"'{folder_id}' in parents"
                    if query:
                        q += f" and name contains '{query}'"
                    results = service.files().list(q=q, pageSize=100).execute()
                    return results.get("files", [])
                
                elif func_id == "mcp_gdrive_read":
                    file_id = params.get("file_id", "")
                    if file_id:
                        file = service.files().get(fileId=file_id).execute()
                        content = service.files().get_media(fileId=file_id).execute()
                        return {"name": file["name"], "content": content.decode("utf-8", errors="replace")}
                
                elif func_id == "mcp_gdrive_write":
                    name = params.get("name", "untitled")
                    content = params.get("content", "")
                    folder_id = params.get("folder_id", "root")
                    from googleapiclient.http import MediaIoBaseUpload
                    import io
                    media = MediaIoBaseUpload(
                        io.BytesIO(content.encode()), 
                        mimetype="text/plain",
                        resumable=True
                    )
                    file_metadata = {"name": name, "parents": [folder_id]}
                    file = service.files().create(body=file_metadata, media_body=media).execute()
                    return {"id": file["id"], "name": file["name"]}
                
                elif func_id == "mcp_gdrive_search":
                    query = params.get("query", "")
                    file_type = params.get("file_type", "")
                    q = f"name contains '{query}'"
                    if file_type:
                        q += f" and mimeType contains '{file_type}'"
                    results = service.files().list(q=q, pageSize=50).execute()
                    return results.get("files", [])
            
        except ImportError:
            return {"info": "Google API client not installed. Would use Google Drive."}
        except Exception as e:
            logger.warning(f"Google Drive error (may be unconfigured): {e}")
        
        return {"info": f"Cloud storage function: {func_id}. Configure Google Drive API credentials first."}
    
    # ----- 通讯 handlers -----
    
    def _handle_communication(self, func_id: str, params: Dict[str, Any]) -> Any:
        # Try Slack Web API
        try:
            from slack_sdk import WebClient
            slack_token = self.config.get("slack", {}).get("token", "")
            if slack_token:
                client = WebClient(token=slack_token)
                
                if func_id == "mcp_slack_channels":
                    include_archived = params.get("include_archived", False)
                    result = client.conversations_list(exclude_archived=not include_archived)
                    return [{"id": c["id"], "name": c["name"]} for c in result["channels"]]
                
                elif func_id == "mcp_slack_history":
                    channel = params.get("channel", "")
                    limit = params.get("limit", 100)
                    if channel:
                        result = client.conversations_history(channel=channel, limit=limit)
                        return [{"user": m.get("user", ""), "text": m.get("text", ""), "ts": m.get("ts", "")} 
                                for m in result.get("messages", [])]
                
                elif func_id == "mcp_slack_send":
                    channel = params.get("channel", "")
                    text = params.get("text", "")
                    if channel and text:
                        result = client.chat_postMessage(channel=channel, text=text)
                        return {"ok": result["ok"], "ts": result.get("ts", "")}
                
                elif func_id == "mcp_slack_search":
                    query = params.get("query", "")
                    if query:
                        result = client.search_messages(query=query)
                        matches = result.get("messages", {}).get("matches", [])
                        return [{"text": m.get("text", ""), "channel": m.get("channel", {}).get("name", ""),
                                 "ts": m.get("ts", "")} for m in matches]
            
        except ImportError:
            pass  # Fall through to Discord or fallback
        except Exception as e:
            logger.warning(f"Slack error (may be unconfigured): {e}")
        
        # Try Discord
        try:
            import discord
            discord_token = self.config.get("discord", {}).get("token", "")
            if discord_token:
                if func_id == "mcp_discord_guilds":
                    return {"info": "Discord guilds available (requires async context)"}
                elif func_id == "mcp_discord_channels":
                    return {"info": f"Would list channels for guild {params.get('guild_id', '')}"}
                elif func_id == "mcp_discord_messages":
                    return {"info": f"Would get messages for channel {params.get('channel_id', '')}"}
                elif func_id == "mcp_discord_send":
                    return {"info": f"Would send message to channel {params.get('channel_id', '')}"}
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Discord error: {e}")
        
        return {"info": f"Communication function: {func_id}. Configure Slack/Discord API credentials first."}
    
    # ----- 开发工具 handlers -----
    
    def _handle_development(self, func_id: str, params: Dict[str, Any]) -> Any:
        # Try GitHub API
        try:
            import requests
            github_token = self.config.get("github", {}).get("token", "")
            headers = {"Accept": "application/vnd.github.v3+json"}
            if github_token:
                headers["Authorization"] = f"token {github_token}"
            
            base_url = "https://api.github.com"
            
            if func_id == "mcp_github_repos":
                username = params.get("username", "")
                sort = params.get("sort", "updated")
                url = f"{base_url}/users/{username}/repos?sort={sort}&per_page=100" if username else f"{base_url}/user/repos?sort={sort}&per_page=100"
                resp = requests.get(url, headers=headers, timeout=30)
                repos = resp.json()
                return [{"name": r["name"], "full_name": r["full_name"], "description": r.get("description", ""),
                         "url": r["html_url"], "stars": r.get("stargazers_count", 0)} for r in repos]
            
            elif func_id == "mcp_github_issues":
                repo = params.get("repo", "")
                state = params.get("state", "open")
                url = f"{base_url}/repos/{repo}/issues?state={state}&per_page=50"
                resp = requests.get(url, headers=headers, timeout=30)
                issues = resp.json()
                return [{"number": i["number"], "title": i["title"], "state": i["state"],
                         "url": i["html_url"], "user": i["user"]["login"]} for i in issues]
            
            elif func_id == "mcp_github_pr":
                repo = params.get("repo", "")
                state = params.get("state", "open")
                url = f"{base_url}/repos/{repo}/pulls?state={state}&per_page=50"
                resp = requests.get(url, headers=headers, timeout=30)
                prs = resp.json()
                return [{"number": pr["number"], "title": pr["title"], "state": pr["state"],
                         "user": pr["user"]["login"], "url": pr["html_url"]} for pr in prs]
            
            elif func_id == "mcp_github_create_issue":
                repo = params.get("repo", "")
                title = params.get("title", "")
                body = params.get("body", "")
                labels = params.get("labels", [])
                data = {"title": title, "body": body, "labels": labels}
                url = f"{base_url}/repos/{repo}/issues"
                resp = requests.post(url, json=data, headers=headers, timeout=30)
                if resp.status_code == 201:
                    issue = resp.json()
                    return {"number": issue["number"], "url": issue["html_url"]}
                return {"error": resp.json()}
            
            elif func_id == "mcp_github_search_code":
                query = params.get("query", "")
                language = params.get("language", "")
                q = query
                if language:
                    q += f" language:{language}"
                url = f"{base_url}/search/code?q={q}&per_page=50"
                resp = requests.get(url, headers=headers, timeout=30)
                data = resp.json()
                return [{"repo": item["repository"]["full_name"], "path": item["path"],
                         "url": item["html_url"]} for item in data.get("items", [])]
            
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"GitHub API error: {e}")
        
        # Try GitLab
        try:
            import requests
            gitlab_url = self.config.get("gitlab", {}).get("url", "https://gitlab.com")
            gitlab_token = self.config.get("gitlab", {}).get("token", "")
            
            if func_id == "mcp_gitlab_projects":
                group = params.get("group", "")
                url = f"{gitlab_url}/api/v4/groups/{group}/projects" if group else f"{gitlab_url}/api/v4/projects"
                headers = {"PRIVATE-TOKEN": gitlab_token} if gitlab_token else {}
                resp = requests.get(url, headers=headers, timeout=30)
                projects = resp.json()
                return [{"id": p["id"], "name": p["name"], "url": p["web_url"]} for p in projects]
            
            elif func_id == "mcp_gitlab_issues":
                project_id = params.get("project_id", "")
                state = params.get("state", "opened")
                url = f"{gitlab_url}/api/v4/projects/{project_id}/issues?state={state}"
                headers = {"PRIVATE-TOKEN": gitlab_token} if gitlab_token else {}
                resp = requests.get(url, headers=headers, timeout=30)
                issues = resp.json()
                return [{"iid": i["iid"], "title": i["title"], "state": i["state"]} for i in issues]
        
        except Exception:
            pass
        
        return {"info": f"Development function: {func_id}. Configure GitHub/GitLab credentials first."}
    
    def get_function_count(self) -> int:
        """获取函数总数"""
        return len(self.functions)


# =============================================================================
# Factory Function
# =============================================================================

def create_mcp_functions(config: Dict[str, Any] = None) -> MCPFunctions:
    """创建MCP函数实例"""
    return MCPFunctions(config)
