#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - Virtual Tool Security Guard
虚拟工具安全守卫 - 实现工具调用安全验证、权限控制

核心功能：
- 工具签名验证
- 参数类型检查
- 权限控制
- 危险模式检测
- 速率限制
- 审计日志

@author MiniMax Agent
@date 2026-03-03
"""

import asyncio
import logging
import re
import time
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """安全等级"""
    SAFE = "safe"
    WARN = "warn"
    DANGER = "danger"
    BLOCK = "block"


class PermissionType(Enum):
    """权限类型"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    ADMIN = "admin"


@dataclass
class ToolSignature:
    """工具签名"""
    name: str
    description: str
    parameters: Dict[str, Any]
    required_permissions: List[PermissionType] = field(default_factory=list)
    required_roles: List[str] = field(default_factory=list)
    rate_limit: int = 60
    timeout: float = 30.0


@dataclass
class AuditLog:
    """审计日志"""
    id: str
    timestamp: datetime
    tool_name: str
    user_id: str
    action: str
    security_level: SecurityLevel
    parameters: Dict[str, Any]
    result: Optional[Any]
    error: Optional[str]
    execution_time: float


class DangerousPatternDetector:
    """危险模式检测器"""

    PATTERNS = {
        "sql_injection": [
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
            r"(--|\/\*|\*\/)",
        ],
        "command_injection": [
            r"[;&|`$]",
            r"\b(rm|del|format|shutdown)\b",
        ],
        "path_traversal": [
            r"\.\.[/\\]",
            r"(/etc/passwd|/windows/system32)",
        ],
        "xss": [
            r"<script[^>]*>",
            r"javascript:",
            r"on\w+\s*=",
        ],
    }

    def __init__(self):
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        for category, patterns in self.PATTERNS.items():
            self._compiled_patterns[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]

    def detect(self, text: str) -> Dict[str, List[str]]:
        """检测危险模式"""
        results = {}

        for category, patterns in self._compiled_patterns.items():
            matches = []
            for pattern in patterns:
                found = pattern.findall(text)
                matches.extend(found)

            if matches:
                results[category] = matches

        return results

    def get_security_level(self, text: str) -> SecurityLevel:
        """获取安全等级"""
        detections = self.detect(text)

        if not detections:
            return SecurityLevel.SAFE

        severe_categories = {"sql_injection", "command_injection", "path_traversal"}
        if any(cat in severe_categories for cat in detections.keys()):
            return SecurityLevel.BLOCK

        if detections:
            return SecurityLevel.WARN

        return SecurityLevel.SAFE


class ParameterValidator:
    """参数验证器"""

    TYPE_MAPPING = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    def __init__(self):
        self._custom_validators: Dict[str, Callable] = {}

    def register_validator(
        self,
        param_name: str,
        validator: Callable[[Any], bool],
    ):
        """注册自定义验证器"""
        self._custom_validators[param_name] = validator

    def validate(
        self,
        parameters: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> tuple[bool, Optional[str]]:
        """验证参数"""
        try:
            required = schema.get("required", [])
            for param in required:
                if param not in parameters:
                    return False, f"Missing required parameter: {param}"

            properties = schema.get("properties", {})
            for name, value in parameters.items():
                if name not in properties:
                    continue

                param_schema = properties[name]

                if "type" in param_schema:
                    expected_type = self.TYPE_MAPPING.get(param_schema["type"])
                    if expected_type and not isinstance(value, expected_type):
                        return False, f"Invalid type for {name}"

                if "enum" in param_schema:
                    if value not in param_schema["enum"]:
                        return False, f"Invalid value for {name}"

                if "minimum" in param_schema:
                    if isinstance(value, (int, float)) and value < param_schema["minimum"]:
                        return False, f"Value for {name} must be >= {param_schema['minimum']}"

                if "maximum" in param_schema:
                    if isinstance(value, (int, float)) and value > param_schema["maximum"]:
                        return False, f"Value for {name} must be <= {param_schema['maximum']}"

            return True, None

        except Exception as e:
            return False, f"Validation error: {str(e)}"


class RoleBasedAccessControl:
    """基于角色的访问控制"""

    DEFAULT_ROLE_PERMISSIONS = {
        "admin": [PermissionType.READ, PermissionType.WRITE, PermissionType.DELETE, PermissionType.EXECUTE, PermissionType.ADMIN],
        "developer": [PermissionType.READ, PermissionType.WRITE, PermissionType.EXECUTE],
        "user": [PermissionType.READ, PermissionType.EXECUTE],
        "guest": [PermissionType.READ],
    }

    def __init__(self):
        self._user_roles: Dict[str, Set[str]] = {}
        self._role_permissions: Dict[str, Set[PermissionType]] = {
            role: set(perms) for role, perms in self.DEFAULT_ROLE_PERMISSIONS.items()
        }

    def assign_role(self, user_id: str, role: str):
        """分配角色"""
        if user_id not in self._user_roles:
            self._user_roles[user_id] = set()
        self._user_roles[user_id].add(role)

    def revoke_role(self, user_id: str, role: str):
        """撤销角色"""
        if user_id in self._user_roles:
            self._user_roles[user_id].discard(role)

    def get_user_roles(self, user_id: str) -> Set[str]:
        """获取用户角色"""
        return self._user_roles.get(user_id, set())

    def has_permission(self, user_id: str, permission: PermissionType) -> bool:
        """检查用户权限"""
        user_roles = self._user_roles.get(user_id, set())

        for role in user_roles:
            role_perms = self._role_permissions.get(role, set())
            if permission in role_perms:
                return True

        return False

    def can_execute_tool(
        self,
        user_id: str,
        tool_signature: ToolSignature,
    ) -> tuple[bool, Optional[str]]:
        """检查是否可执行工具"""
        for required_perm in tool_signature.required_permissions:
            if not self.has_permission(user_id, required_perm):
                return False, f"Missing required permission: {required_perm.value}"

        user_roles = self._user_roles.get(user_id, set())
        for required_role in tool_signature.required_roles:
            if required_role not in user_roles:
                return False, f"Missing required role: {required_role}"

        return True, None


class RateLimiter:
    """速率限制器"""

    def __init__(self):
        self._limits: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(
        self,
        key: str,
        max_count: int,
        window_seconds: int = 60,
    ) -> tuple[bool, Optional[int]]:
        """检查速率限制"""
        async with self._lock:
            now = datetime.now()

            if key not in self._limits:
                self._limits[key] = {
                    "count": 0,
                    "window_start": now,
                }

            info = self._limits[key]

            elapsed = (now - info["window_start"]).total_seconds()
            if elapsed > window_seconds:
                info["count"] = 0
                info["window_start"] = now

            if info["count"] >= max_count:
                return False, 0

            info["count"] += 1

            return True, max_count - info["count"]

    async def reset(self, key: str):
        """重置限制"""
        async with self._lock:
            if key in self._limits:
                del self._limits[key]


class SecurityAuditLogger:
    """安全审计日志"""

    def __init__(self, max_entries: int = 10000):
        self.max_entries = max_entries
        self._logs: List[AuditLog] = []
        self._lock = asyncio.Lock()

    async def log(
        self,
        tool_name: str,
        user_id: str,
        action: str,
        security_level: SecurityLevel,
        parameters: Dict[str, Any],
        result: Optional[Any] = None,
        error: Optional[str] = None,
        execution_time: float = 0.0,
    ):
        """记录审计日志"""
        async with self._lock:
            log_entry = AuditLog(
                id=f"audit_{id(object())}",
                timestamp=datetime.now(),
                tool_name=tool_name,
                user_id=user_id,
                action=action,
                security_level=security_level,
                parameters=parameters,
                result=result,
                error=error,
                execution_time=execution_time,
            )

            self._logs.append(log_entry)

            if len(self._logs) > self.max_entries:
                self._logs = self._logs[-self.max_entries:]

    async def get_logs(
        self,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        security_level: Optional[SecurityLevel] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """查询审计日志"""
        async with self._lock:
            logs = self._logs

            if user_id:
                logs = [l for l in logs if l.user_id == user_id]

            if tool_name:
                logs = [l for l in logs if l.tool_name == tool_name]

            if security_level:
                logs = [l for l in logs if l.security_level == security_level]

            return logs[-limit:]


class VirtualToolSecurityGuard:
    """虚拟工具安全守卫"""

    def __init__(self):
        self.pattern_detector = DangerousPatternDetector()
        self.parameter_validator = ParameterValidator()
        self.rbac = RoleBasedAccessControl()
        self.rate_limiter = RateLimiter()
        self.audit_logger = SecurityAuditLogger()
        self._tool_registry: Dict[str, ToolSignature] = {}
        self._execution_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

        logger.info("VirtualToolSecurityGuard initialized")

    def register_tool(self, signature: ToolSignature):
        """注册工具"""
        self._tool_registry[signature.name] = signature
        logger.info(f"Tool registered: {signature.name}")

    def get_tool_signature(self, tool_name: str) -> Optional[ToolSignature]:
        """获取工具签名"""
        return self._tool_registry.get(tool_name)

    async def validate_and_execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        user_id: str = "default",
        executor: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """验证并执行工具"""
        start_time = time.time()

        signature = self._tool_registry.get(tool_name)
        if not signature:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
                "security_level": SecurityLevel.BLOCK.value,
            }

        can_execute, perm_error = self.rbac.can_execute_tool(user_id, signature)
        if not can_execute:
            await self.audit_logger.log(
                tool_name, user_id, "permission_denied",
                SecurityLevel.BLOCK, parameters,
                execution_time=time.time() - start_time,
                error=perm_error,
            )
            return {
                "success": False,
                "error": f"Permission denied: {perm_error}",
                "security_level": SecurityLevel.BLOCK.value,
            }

        rate_limit_key = f"{user_id}:{tool_name}"
        allowed, remaining = await self.rate_limiter.check_rate_limit(
            rate_limit_key,
            signature.rate_limit,
        )
        if not allowed:
            return {
                "success": False,
                "error": "Rate limit exceeded",
                "security_level": SecurityLevel.BLOCK.value,
            }

        if signature.parameters:
            valid, validate_error = self.parameter_validator.validate(
                parameters,
                signature.parameters,
            )
            if not valid:
                return {
                    "success": False,
                    "error": f"Invalid parameters: {validate_error}",
                    "security_level": SecurityLevel.BLOCK.value,
                }

        danger_detected = False
        for param_name, param_value in parameters.items():
            if isinstance(param_value, str):
                level = self.pattern_detector.get_security_level(param_value)

                if level == SecurityLevel.BLOCK:
                    danger_detected = True
                    return {
                        "success": False,
                        "error": f"Dangerous pattern detected in {param_name}",
                        "security_level": SecurityLevel.BLOCK.value,
                    }

        if tool_name not in self._execution_locks:
            self._execution_locks[tool_name] = asyncio.Lock()

        execution_lock = self._execution_locks[tool_name]

        async with execution_lock:
            try:
                if executor:
                    result = await asyncio.wait_for(
                        executor(parameters),
                        timeout=signature.timeout,
                    )
                else:
                    result = None

                execution_time = time.time() - start_time

                await self.audit_logger.log(
                    tool_name, user_id, "executed",
                    SecurityLevel.SAFE if not danger_detected else SecurityLevel.WARN,
                    parameters,
                    result=result,
                    execution_time=execution_time,
                )

                return {
                    "success": True,
                    "result": result,
                    "security_level": SecurityLevel.SAFE.value if not danger_detected else SecurityLevel.WARN.value,
                    "remaining_rate_limit": remaining,
                    "execution_time": execution_time,
                }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "error": "Execution timeout",
                    "security_level": SecurityLevel.WARN.value,
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "security_level": SecurityLevel.WARN.value,
                }

    async def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """获取审计日志"""
        return await self.audit_logger.get_logs(
            user_id=user_id,
            tool_name=tool_name,
            limit=limit,
        )

    def get_security_stats(self) -> Dict[str, Any]:
        """获取安全统计"""
        return {
            "registered_tools": len(self._tool_registry),
        }


def create_security_guard() -> VirtualToolSecurityGuard:
    """创建安全守卫实例"""
    return VirtualToolSecurityGuard()


def create_tool_signature(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    required_permissions: Optional[List[PermissionType]] = None,
    required_roles: Optional[List[str]] = None,
    rate_limit: int = 60,
    timeout: float = 30.0,
) -> ToolSignature:
    """创建工具签名"""
    return ToolSignature(
        name=name,
        description=description,
        parameters=parameters,
        required_permissions=required_permissions or [],
        required_roles=required_roles or [],
        rate_limit=rate_limit,
        timeout=timeout,
    )


if __name__ == "__main__":
    import asyncio

    async def main():
        guard = create_security_guard()

        tool_sig = create_tool_signature(
            name="file_read",
            description="Read file content",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
            required_permissions=[PermissionType.READ],
            required_roles=["user"],
        )
        guard.register_tool(tool_sig)

        guard.rbac.assign_role("user1", "user")

        result = await guard.validate_and_execute(
            tool_name="file_read",
            parameters={"path": "/etc/passwd"},
            user_id="user1",
        )

        print(result)

    asyncio.run(main())
