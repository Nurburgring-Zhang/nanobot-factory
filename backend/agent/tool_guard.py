"""
NanoBot Factory - Virtual Tool Guard Module
工具守卫模块 - 提供工具调用的安全验证和防护

功能：
- 工具调用前的安全检查
- 敏感操作二次确认
- 操作频率限制
- 恶意请求拦截
- 操作审计日志

@author MiniMax Agent
@date 2026-04-10
"""

import os
import re
import logging
import hashlib
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """威胁等级"""
    SAFE = "safe"           # 安全
    LOW = "low"             # 低风险
    MEDIUM = "medium"       # 中风险
    HIGH = "high"           # 高风险
    CRITICAL = "critical"   # 严重风险


class OperationType(Enum):
    """操作类型"""
    READ = "read"           # 读取操作
    WRITE = "write"         # 写入操作
    DELETE = "delete"       # 删除操作
    EXECUTE = "execute"     # 执行操作
    NETWORK = "network"     # 网络操作
    FILE_SYSTEM = "file_system"  # 文件系统操作
    DATABASE = "database"   # 数据库操作


@dataclass
class GuardRule:
    """守卫规则"""
    name: str
    pattern: str                    # 匹配模式（正则表达式）
    threat_level: ThreatLevel
    requires_confirmation: bool = False
    max_calls_per_minute: int = 0   # 0表示不限制
    enabled: bool = True
    description: str = ""


@dataclass
class GuardResult:
    """守卫检查结果"""
    allowed: bool
    threat_level: ThreatLevel
    message: str
    requires_confirmation: bool = False
    confirmation_token: Optional[str] = None
    suggested_action: Optional[str] = None


@dataclass
class OperationLog:
    """操作日志"""
    timestamp: datetime
    tool_name: str
    user_id: str
    session_id: str
    parameters: Dict[str, Any]
    threat_level: ThreatLevel
    result: str
    duration_ms: float


class VirtualToolGuard:
    """虚拟工具守卫
    
    在工具执行前进行多层安全检查：
    1. 模式匹配检查
    2. 频率限制检查
    3. 敏感操作确认
    4. 威胁等级评估
    """
    
    # 默认危险模式
    DEFAULT_DANGEROUS_PATTERNS = [
        # 文件系统危险操作
        (r"(?i)(rm\s+-rf\s+/|del\s+/[ssy]|\*|format\s+c:)", ThreatLevel.CRITICAL),
        (r"(?i)(chmod\s+777|chmod\s+-r\s+777)", ThreatLevel.HIGH),
        (r"(?i)(eval|exec|system)\s*\(", ThreatLevel.MEDIUM),
        
        # 网络危险操作
        (r"(?i)(curl|wget).*\|.*sh", ThreatLevel.CRITICAL),
        (r"(?i)(nc\s+-e|netcat\s+-e)", ThreatLevel.CRITICAL),
        (r"(?i)(rm\s+/|mkfs|dd\s+if=)", ThreatLevel.CRITICAL),
        
        # 数据库危险操作
        (r"(?i)DROP\s+TABLE.*CASCADE", ThreatLevel.HIGH),
        (r"(?i)DELETE\s+FROM\s+\w+\s*;", ThreatLevel.MEDIUM),
        (r"(?i)TRUNCATE\s+TABLE", ThreatLevel.HIGH),
        
        # 系统配置危险操作
        (r"(?i)/etc/passwd|/etc/shadow", ThreatLevel.HIGH),
        (r"(?i)\.ssh/authorized_keys", ThreatLevel.HIGH),
        (r"(?i)(sudo|su\s+)", ThreatLevel.MEDIUM),
    ]
    
    # 需要确认的操作
    CONFIRMATION_REQUIRED_PATTERNS = [
        # 文件操作
        (r"(?i)(delete|remove|rm|del)\s+", ThreatLevel.MEDIUM),
        (r"(?i)(format|truncate)\s+", ThreatLevel.HIGH),
        
        # 数据库操作
        (r"(?i)(drop|alter)\s+(table|database)", ThreatLevel.HIGH),
        
        # 网络操作
        (r"(?i)(post|put)\s+.*(password|secret|token|key)", ThreatLevel.MEDIUM),
        
        # 执行操作
        (r"(?i)(execute|run|eval)\s+", ThreatLevel.LOW),
    ]
    
    def __init__(self, strict_mode: bool = False):
        """初始化工具守卫
        
        Args:
            strict_mode: 严格模式，会拦截更多潜在危险操作
        """
        self.strict_mode = strict_mode
        self._rules: List[GuardRule] = []
        self._call_history: Dict[str, List[float]] = defaultdict(list)
        self._operation_logs: List[OperationLog] = []
        self._pending_confirmations: Dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._max_logs = 10000  # 最多保留10000条日志
        
        # 注册默认规则
        self._register_default_rules()
        
        logger.info(f"VirtualToolGuard initialized (strict_mode={strict_mode})")
    
    def _register_default_rules(self) -> None:
        """注册默认规则"""
        # 危险命令规则
        dangerous_commands = [
            (r"(?i)^rm\s+-rf", ThreatLevel.CRITICAL, True, 10),
            (r"(?i)^del\s+/[sy]", ThreatLevel.CRITICAL, True, 5),
            (r"(?i)^dd\s+", ThreatLevel.HIGH, True, 5),
            (r"(?i)^mkfs", ThreatLevel.HIGH, True, 5),
            (r"(?i)^chmod\s+777", ThreatLevel.HIGH, False, 20),
        ]
        
        for pattern, level, need_confirm, rate_limit in dangerous_commands:
            self._rules.append(GuardRule(
                name=f"dangerous_cmd_{pattern[:20]}",
                pattern=pattern,
                threat_level=level,
                requires_confirmation=need_confirm,
                max_calls_per_minute=rate_limit,
                description=f"危险命令检测: {pattern}"
            ))
    
    def add_rule(self, rule: GuardRule) -> None:
        """添加自定义规则
        
        Args:
            rule: 守卫规则
        """
        with self._lock:
            self._rules.append(rule)
        logger.info(f"Added guard rule: {rule.name}")
    
    def remove_rule(self, rule_name: str) -> bool:
        """移除规则
        
        Args:
            rule_name: 规则名称
            
        Returns:
            是否成功移除
        """
        with self._lock:
            for i, rule in enumerate(self._rules):
                if rule.name == rule_name:
                    self._rules.pop(i)
                    logger.info(f"Removed guard rule: {rule_name}")
                    return True
        return False
    
    def check(self, tool_name: str, parameters: Dict[str, Any], 
              user_id: str = "anonymous", session_id: str = "default") -> GuardResult:
        """检查工具调用是否安全
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            user_id: 用户ID
            session_id: 会话ID
            
        Returns:
            守卫检查结果
        """
        start_time = time.time()
        combined_input = f"{tool_name}:{str(parameters)}"
        
        # 1. 检查危险模式
        danger_result = self._check_dangerous_patterns(combined_input)
        if not danger_result["safe"]:
            self._log_operation(
                tool_name, user_id, session_id, parameters,
                danger_result["level"], "BLOCKED", time.time() - start_time
            )
            return GuardResult(
                allowed=False,
                threat_level=danger_result["level"],
                message=danger_result["message"],
                suggested_action="请修改参数后重试"
            )
        
        # 2. 检查确认要求
        confirm_result = self._check_confirmation_required(combined_input)
        if confirm_result["required"]:
            token = self._generate_confirmation_token(user_id, tool_name)
            self._pending_confirmations[token] = datetime.now() + timedelta(minutes=5)
            
            self._log_operation(
                tool_name, user_id, session_id, parameters,
                ThreatLevel.LOW, "PENDING_CONFIRMATION", time.time() - start_time
            )
            
            return GuardResult(
                allowed=False,
                threat_level=ThreatLevel.LOW,
                message=confirm_result["message"],
                requires_confirmation=True,
                confirmation_token=token,
                suggested_action="请确认执行此操作"
            )
        
        # 3. 检查频率限制
        rate_result = self._check_rate_limit(tool_name, user_id)
        if not rate_result["allowed"]:
            self._log_operation(
                tool_name, user_id, session_id, parameters,
                ThreatLevel.LOW, "RATE_LIMITED", time.time() - start_time
            )
            return GuardResult(
                allowed=False,
                threat_level=ThreatLevel.LOW,
                message=f"操作过于频繁，请等待 {rate_result.get('wait_seconds', 60)} 秒后重试",
                suggested_action=f"等待 {rate_result.get('wait_seconds', 60)} 秒"
            )
        
        # 4. 检查自定义规则
        custom_result = self._check_custom_rules(combined_input)
        if not custom_result["allowed"]:
            self._log_operation(
                tool_name, user_id, session_id, parameters,
                custom_result["level"], "BLOCKED_BY_RULE", time.time() - start_time
            )
            return GuardResult(
                allowed=False,
                threat_level=custom_result["level"],
                message=custom_result["message"],
                suggested_action="请联系管理员调整规则"
            )
        
        # 所有检查通过
        self._log_operation(
            tool_name, user_id, session_id, parameters,
            ThreatLevel.SAFE, "ALLOWED", time.time() - start_time
        )
        
        return GuardResult(
            allowed=True,
            threat_level=ThreatLevel.SAFE,
            message="安全检查通过"
        )
    
    def confirm_operation(self, token: str) -> bool:
        """确认待定操作
        
        Args:
            token: 确认令牌
            
        Returns:
            是否确认成功
        """
        with self._lock:
            if token in self._pending_confirmations:
                if datetime.now() < self._pending_confirmations[token]:
                    del self._pending_confirmations[token]
                    logger.info(f"Operation confirmed: {token}")
                    return True
                else:
                    del self._pending_confirmations[token]
                    logger.warning(f"Confirmation token expired: {token}")
            
            return False
    
    def _check_dangerous_patterns(self, input_text: str) -> Dict[str, Any]:
        """检查危险模式"""
        for pattern, level in self.DEFAULT_DANGEROUS_PATTERNS:
            try:
                if re.search(pattern, input_text):
                    if level == ThreatLevel.CRITICAL:
                        return {
                            "safe": False,
                            "level": level,
                            "message": f"检测到严重危险操作: {pattern}"
                        }
                    elif level == ThreatLevel.HIGH and self.strict_mode:
                        return {
                            "safe": False,
                            "level": level,
                            "message": f"严格模式: 检测到高风险操作: {pattern}"
                        }
            except re.error as e:
                logger.error(f"Regex error in pattern {pattern}: {e}")
        
        return {"safe": True}
    
    def _check_confirmation_required(self, input_text: str) -> Dict[str, Any]:
        """检查是否需要确认"""
        for pattern, level in self.CONFIRMATION_REQUIRED_PATTERNS:
            try:
                if re.search(pattern, input_text):
                    return {
                        "required": True,
                        "message": f"此操作 ({level.value}) 需要确认",
                        "level": level
                    }
            except re.error:
                continue
        
        return {"required": False}
    
    def _check_rate_limit(self, tool_name: str, user_id: str) -> Dict[str, Any]:
        """检查频率限制"""
        key = f"{user_id}:{tool_name}"
        current_time = time.time()
        cutoff_time = current_time - 60  # 1分钟窗口
        
        with self._lock:
            # 清理过期记录
            self._call_history[key] = [
                t for t in self._call_history[key] if t > cutoff_time
            ]
            
            # 默认限制：每分钟60次
            max_calls = 60
            
            # 查找是否有自定义限制
            for rule in self._rules:
                if rule.enabled and rule.max_calls_per_minute > 0:
                    if re.search(rule.pattern, tool_name):
                        max_calls = rule.max_calls_per_minute
                        break
            
            if len(self._call_history[key]) >= max_calls:
                return {
                    "allowed": False,
                    "wait_seconds": 60 - int(current_time - self._call_history[key][0])
                }
            
            # 记录此次调用
            self._call_history[key].append(current_time)
            
            return {"allowed": True}
    
    def _check_custom_rules(self, input_text: str) -> Dict[str, Any]:
        """检查自定义规则"""
        for rule in self._rules:
            if not rule.enabled:
                continue
            
            try:
                if re.search(rule.pattern, input_text):
                    if rule.requires_confirmation:
                        continue  # 确认由另一个检查处理
                    
                    return {
                        "allowed": False,
                        "level": rule.threat_level,
                        "message": f"触发规则 [{rule.name}]: {rule.description}"
                    }
            except re.error:
                continue
        
        return {"allowed": True}
    
    def _generate_confirmation_token(self, user_id: str, tool_name: str) -> str:
        """生成确认令牌"""
        data = f"{user_id}:{tool_name}:{time.time()}:{os.urandom(8).hex()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def _log_operation(self, tool_name: str, user_id: str, session_id: str,
                       parameters: Dict[str, Any], threat_level: ThreatLevel,
                       result: str, duration_ms: float) -> None:
        """记录操作日志"""
        log = OperationLog(
            timestamp=datetime.now(),
            tool_name=tool_name,
            user_id=user_id,
            session_id=session_id,
            parameters=self._sanitize_parameters(parameters),
            threat_level=threat_level,
            result=result,
            duration_ms=duration_ms * 1000
        )
        
        with self._lock:
            self._operation_logs.append(log)
            
            # 保持日志数量限制
            if len(self._operation_logs) > self._max_logs:
                self._operation_logs = self._operation_logs[-self._max_logs:]
    
    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """清理敏感参数"""
        sensitive_keys = ['password', 'secret', 'token', 'key', 'api_key', 'apikey']
        sanitized = {}
        
        for k, v in parameters.items():
            if any(s in k.lower() for s in sensitive_keys):
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_parameters(v)
            else:
                sanitized[k] = v
        
        return sanitized
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取守卫统计信息"""
        with self._lock:
            total = len(self._operation_logs)
            if total == 0:
                return {"total_operations": 0}
            
            blocked = sum(1 for log in self._operation_logs if log.result == "BLOCKED")
            confirmed = sum(1 for log in self._operation_logs if log.result == "PENDING_CONFIRMATION")
            
            threat_counts = defaultdict(int)
            for log in self._operation_logs:
                threat_counts[log.threat_level.value] += 1
            
            return {
                "total_operations": total,
                "blocked_operations": blocked,
                "pending_confirmations": confirmed,
                "pass_rate": f"{(total - blocked) / total * 100:.1f}%",
                "threat_distribution": dict(threat_counts),
                "rules_count": len(self._rules),
                "strict_mode": self.strict_mode
            }
    
    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的操作日志"""
        with self._lock:
            logs = self._operation_logs[-limit:]
            return [
                {
                    "timestamp": log.timestamp.isoformat(),
                    "tool_name": log.tool_name,
                    "user_id": log.user_id,
                    "threat_level": log.threat_level.value,
                    "result": log.result,
                    "duration_ms": f"{log.duration_ms:.2f}"
                }
                for log in reversed(logs)
            ]
    
    def clear_logs(self) -> None:
        """清空操作日志"""
        with self._lock:
            self._operation_logs.clear()
        logger.info("Operation logs cleared")


# 全局守卫实例
_tool_guard: Optional[VirtualToolGuard] = None


def get_tool_guard(strict_mode: bool = False) -> VirtualToolGuard:
    """获取全局工具守卫实例"""
    global _tool_guard
    if _tool_guard is None:
        _tool_guard = VirtualToolGuard(strict_mode=strict_mode)
    return _tool_guard
