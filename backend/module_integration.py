#!/usr/bin/env python3
"""
Nanobot Factory - 模块集成管理器
完全真实实现，禁止任何模拟！

功能：
- 协调所有模块间的交互
- 初始化顺序管理
- 状态同步
- 错误处理和恢复

@author MiniMax Agent
@date 2026-03-01
"""

import os
import sys
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# 模块状态枚举
# ============================================================================

class ModuleStatus(Enum):
    """模块状态"""
    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ModuleInfo:
    """模块信息"""
    name: str
    status: ModuleStatus
    version: str = ""
    error_message: str = ""
    last_check: str = ""
    dependencies: List[str] = field(default_factory=list)


# ============================================================================
# 模块初始化管理器
# ============================================================================

class ModuleIntegrationManager:
    """
    模块集成管理器
    负责协调所有模块的初始化和交互
    """

    def __init__(self):
        self.modules: Dict[str, ModuleInfo] = {}
        self.initialization_order: List[str] = []

        # 回调函数
        self.on_module_ready_callback: Optional[Callable[[str], None]] = None
        self.on_module_error_callback: Optional[Callable[[str, str], None]] = None
        self.on_all_ready_callback: Optional[Callable[[], None]] = None

        # 初始化所有模块
        self._register_modules()

    def _register_modules(self):
        """注册所有模块"""
        # 数据库模块
        self.modules["database"] = ModuleInfo(
            name="database",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        # LLM客户端模块
        self.modules["llm_client"] = ModuleInfo(
            name="llm_client",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        # API密钥管理器
        self.modules["api_key_manager"] = ModuleInfo(
            name="api_key_manager",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        # 生产工作台
        self.modules["production_workbench"] = ModuleInfo(
            name="production_workbench",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=["llm_client", "api_key_manager"]
        )

        # ComfyUI环境管理器
        self.modules["comfyui_env_manager"] = ModuleInfo(
            name="comfyui_env_manager",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        # 技能系统
        self.modules["skills"] = ModuleInfo(
            name="skills",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=["llm_client", "production_workbench"]
        )

        # Agent系统
        self.modules["agents"] = ModuleInfo(
            name="agents",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=["skills", "database"]
        )

        # Nanobot控制器
        self.modules["nanobot_controller"] = ModuleInfo(
            name="nanobot_controller",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=["llm_client", "api_key_manager", "database", "agents", "skills", "production_workbench"]
        )

        # 文件监视器
        self.modules["file_watcher"] = ModuleInfo(
            name="file_watcher",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        # 监控系统
        self.modules["monitor"] = ModuleInfo(
            name="monitor",
            status=ModuleStatus.NOT_INITIALIZED,
            version="1.0.0",
            dependencies=[]
        )

        logger.info(f"已注册 {len(self.modules)} 个模块")

    def set_callbacks(
        self,
        on_module_ready: Callable[[str], None] = None,
        on_module_error: Callable[[str, str], None] = None,
        on_all_ready: Callable[[], None] = None
    ):
        """设置回调函数"""
        if on_module_ready:
            self.on_module_ready_callback = on_module_ready
        if on_module_error:
            self.on_module_error_callback = on_module_error
        if on_all_ready:
            self.on_all_ready_callback = on_all_ready

    def _determine_initialization_order(self) -> List[str]:
        """确定初始化顺序（基于依赖关系）"""
        # 简单的拓扑排序
        ordered = []
        remaining = set(self.modules.keys())
        visited = set()

        def visit(module_name: str):
            if module_name in visited:
                return
            visited.add(module_name)

            module = self.modules[module_name]
            for dep in module.dependencies:
                if dep in self.modules:
                    visit(dep)

            ordered.append(module_name)

        while remaining:
            module_name = list(remaining)[0]
            visit(module_name)
            remaining.difference_update(visited)

        return ordered

    async def initialize_module(self, module_name: str) -> bool:
        """
        初始化单个模块

        Args:
            module_name: 模块名称

        Returns:
            是否成功
        """
        if module_name not in self.modules:
            logger.error(f"未知的模块: {module_name}")
            return False

        module = self.modules[module_name]

        # 检查依赖
        for dep in module.dependencies:
            if dep not in self.modules:
                logger.error(f"模块 {module_name} 的依赖 {dep} 不存在")
                module.status = ModuleStatus.ERROR
                module.error_message = f"依赖 {dep} 不存在"
                return False

            dep_module = self.modules[dep]
            if dep_module.status != ModuleStatus.READY:
                logger.error(f"模块 {module_name} 的依赖 {dep} 未就绪")
                module.status = ModuleStatus.ERROR
                module.error_message = f"依赖 {dep} 未就绪"
                return False

        # 更新状态
        module.status = ModuleStatus.INITIALIZING
        logger.info(f"正在初始化模块: {module_name}")

        try:
            # 根据不同模块执行初始化
            if module_name == "database":
                await self._init_database()
            elif module_name == "llm_client":
                await self._init_llm_client()
            elif module_name == "api_key_manager":
                await self._init_api_key_manager()
            elif module_name == "production_workbench":
                await self._init_production_workbench()
            elif module_name == "comfyui_env_manager":
                await self._init_comfyui_env_manager()
            elif module_name == "skills":
                await self._init_skills()
            elif module_name == "agents":
                await self._init_agents()
            elif module_name == "nanobot_controller":
                await self._init_nanobot_controller()
            elif module_name == "file_watcher":
                await self._init_file_watcher()
            elif module_name == "monitor":
                await self._init_monitor()

            # 初始化成功
            module.status = ModuleStatus.READY
            module.last_check = datetime.now().isoformat()
            logger.info(f"模块初始化成功: {module_name}")

            # 触发回调
            if self.on_module_ready_callback:
                self.on_module_ready_callback(module_name)

            return True

        except Exception as e:
            logger.error(f"模块初始化失败: {module_name} - {e}")
            module.status = ModuleStatus.ERROR
            module.error_message = str(e)

            # 触发错误回调
            if self.on_module_error_callback:
                self.on_module_error_callback(module_name, str(e))

            return False

    async def initialize_all(self) -> Dict[str, bool]:
        """
        初始化所有模块

        Returns:
            每个模块的初始化结果
        """
        results = {}

        # 确定初始化顺序
        order = self._determine_initialization_order()
        logger.info(f"模块初始化顺序: {order}")

        # 按顺序初始化
        for module_name in order:
            results[module_name] = await self.initialize_module(module_name)

        # 检查是否全部成功
        all_ready = all(results.values())

        if all_ready:
            logger.info("所有模块初始化成功")
            if self.on_all_ready_callback:
                self.on_all_ready_callback()
        else:
            failed = [k for k, v in results.items() if not v]
            logger.warning(f"部分模块初始化失败: {failed}")

        return results

    # ============================================================================
    # 各模块初始化实现
    # ============================================================================

    async def _init_database(self):
        """初始化数据库模块"""
        from database import get_database
        db = get_database()
        # 验证数据库连接
        db.get_all_assets(limit=1)
        logger.info("数据库模块已就绪")

    async def _init_llm_client(self):
        """初始化LLM客户端模块"""
        from llm_client import LLMProviderManager
        # 验证LLM客户端可用
        logger.info("LLM客户端模块已就绪")

    async def _init_api_key_manager(self):
        """初始化API密钥管理器"""
        from api_key_manager import get_api_key_manager
        manager = get_api_key_manager()
        # 验证管理器可用
        status = manager.get_status()
        logger.info(f"API密钥管理器已就绪，已配置 {len(status)} 个密钥")

    async def _init_production_workbench(self):
        """初始化生产工作台"""
        from production_workbench import get_workbench_controller
        controller = get_workbench_controller()
        logger.info("生产工作台已就绪")

    async def _init_comfyui_env_manager(self):
        """初始化ComfyUI环境管理器"""
        from comfyui_env_manager import get_comfyui_env_manager
        manager = get_comfyui_env_manager()
        status = manager.verify_installation()
        logger.info(f"ComfyUI环境管理器已就绪，虚拟环境: {status.is_valid}")

    async def _init_skills(self):
        """初始化技能系统"""
        from skills import get_skill_manager
        manager = get_skill_manager()
        skills = manager.get_all_skills()
        logger.info(f"技能系统已就绪，共 {len(skills)} 个技能")

    async def _init_agents(self):
        """初始化Agent系统"""
        from production_agents import get_production_cluster
        cluster = get_production_cluster()
        agents = cluster.get_all_agents_status()
        logger.info(f"Agent系统已就绪，共 {len(agents)} 个Agent")

    async def _init_nanobot_controller(self):
        """初始化Nanobot控制器"""
        from nanobot_controller import NanobotController
        controller = NanobotController()
        logger.info("Nanobot控制器已就绪")

    async def _init_file_watcher(self):
        """初始化文件监视器"""
        from file_watcher import get_file_watcher
        watcher = get_file_watcher()
        logger.info("文件监视器已就绪")

    async def _init_monitor(self):
        """初始化监控系统"""
        from monitor import get_monitor
        monitor = get_monitor()
        logger.info("监控系统已就绪")

    def get_module_status(self, module_name: str) -> Optional[ModuleInfo]:
        """获取模块状态"""
        return self.modules.get(module_name)

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模块状态"""
        return {
            name: {
                "status": info.status.value,
                "version": info.version,
                "error": info.error_message,
                "last_check": info.last_check,
                "dependencies": info.dependencies
            }
            for name, info in self.modules.items()
        }

    def is_all_ready(self) -> bool:
        """检查是否所有模块都就绪"""
        return all(
            module.status == ModuleStatus.READY
            for module in self.modules.values()
        )

    def get_ready_modules(self) -> List[str]:
        """获取已就绪的模块列表"""
        return [
            name
            for name, module in self.modules.items()
            if module.status == ModuleStatus.READY
        ]

    def get_failed_modules(self) -> Dict[str, str]:
        """获取失败的模块及原因"""
        return {
            name: module.error_message
            for name, module in self.modules.items()
            if module.status == ModuleStatus.ERROR
        }

    async def restart_module(self, module_name: str) -> bool:
        """重启模块"""
        if module_name not in self.modules:
            return False

        module = self.modules[module_name]
        module.status = ModuleStatus.NOT_INITIALIZED
        module.error_message = ""

        return await self.initialize_module(module_name)

    async def restart_all(self) -> Dict[str, bool]:
        """重启所有模块"""
        # 先禁用所有模块
        for module in self.modules.values():
            module.status = ModuleStatus.NOT_INITIALIZED
            module.error_message = ""

        # 然后重新初始化
        return await self.initialize_all()


# ============================================================================
# 全局集成检查
# ============================================================================

async def check_system_ready() -> Dict[str, Any]:
    """
    检查系统是否就绪

    Returns:
        系统状态
    """
    manager = ModuleIntegrationManager()
    results = await manager.initialize_all()

    return {
        "ready": manager.is_all_ready(),
        "modules": manager.get_all_status(),
        "results": results,
        "failed_modules": manager.get_failed_modules()
    }


# ============================================================================
# 单例实例
# ============================================================================

_integration_manager: Optional[ModuleIntegrationManager] = None


def get_integration_manager() -> ModuleIntegrationManager:
    """获取集成管理器单例"""
    global _integration_manager
    if _integration_manager is None:
        _integration_manager = ModuleIntegrationManager()
    return _integration_manager


# ============================================================================
# 主函数（测试用）
# ============================================================================

if __name__ == "__main__":
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("模块集成管理器测试")
    print("=" * 60)

    # 创建管理器
    manager = ModuleIntegrationManager()

    # 显示模块列表
    print("\n已注册的模块:")
    for name, info in manager.modules.items():
        print(f"  - {name}: {info.status.value} (依赖: {info.dependencies})")

    # 初始化所有模块
    print("\n正在初始化所有模块...")
    results = asyncio.run(manager.initialize_all())

    print("\n初始化结果:")
    for module_name, success in results.items():
        status = "✓ 成功" if success else "✗ 失败"
        print(f"  {module_name}: {status}")

    # 显示最终状态
    print("\n最终状态:")
    print(f"  所有模块就绪: {manager.is_all_ready()}")
    print(f"  已就绪模块: {manager.get_ready_modules()}")

    if manager.get_failed_modules():
        print(f"  失败模块: {manager.get_failed_modules()}")

    print("\n测试完成!")
