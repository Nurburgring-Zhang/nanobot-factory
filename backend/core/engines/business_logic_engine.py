#!/usr/bin/env python3
"""
NanoBot Factory 业务逻辑引擎 (Business Logic Engine)
====================================================

负责业务流程编排、规则执行和数据处理。

@author MiniMax Agent
@date 2026-04-14
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class FlowStatus(Enum):
    """流程状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RuleAction(Enum):
    """规则动作"""
    ALLOW = "allow"
    DENY = "deny"
    MODIFY = "modify"
    FLAG = "flag"
    LOG = "log"


@dataclass
class FlowContext:
    """流程上下文"""
    flow_id: str
    session_id: str
    user_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    def update(self, key: str, value: Any):
        self.data[key] = value
    
    def add_history(self, action: str, result: Any):
        self.history.append({"action": action, "result": result, "timestamp": datetime.now().isoformat()})


@dataclass
class FlowResult:
    """流程执行结果"""
    success: bool
    flow_id: str
    output: Any = None
    error: Optional[str] = None
    steps_executed: List[str] = field(default_factory=list)
    execution_time: float = 0.0


@dataclass
class Rule:
    """业务规则"""
    rule_id: str
    name: str
    condition: str
    action: RuleAction
    priority: int = 0
    enabled: bool = True


@dataclass
class RuleResult:
    """规则执行结果"""
    rule_id: str
    matched: bool
    action: RuleAction
    message: str = ""


class StepHandler(ABC):
    """步骤处理器基类"""
    
    @abstractmethod
    async def execute(self, context: FlowContext, config: Dict[str, Any]) -> Any:
        pass


class FlowEngine:
    """流程引擎"""
    
    def __init__(self):
        self._flows: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, StepHandler] = {}
        self._running_flows: Dict[str, FlowContext] = {}
        logger.info("流程引擎初始化完成")
    
    def register_flow(self, flow_id: str, flow_config: Dict[str, Any]):
        """注册流程"""
        self._flows[flow_id] = flow_config
        logger.info(f"注册流程: {flow_id}")
    
    async def execute(
        self,
        flow_id: str,
        context: FlowContext
    ) -> FlowResult:
        """执行流程"""
        start_time = time.time()
        flow = self._flows.get(flow_id)
        
        if not flow:
            return FlowResult(False, flow_id, error=f"流程不存在: {flow_id}", execution_time=time.time() - start_time)
        
        try:
            steps = flow.get("steps", [])
            for step in steps:
                result = await self._execute_step(step, context)
                context.add_history(step.get("name", "unnamed"), result)
            
            return FlowResult(True, flow_id, output=context.data, steps_executed=[s.get("name") for s in steps], execution_time=time.time() - start_time)
        except Exception as e:
            return FlowResult(False, flow_id, error=str(e), execution_time=time.time() - start_time)
        finally:
            if flow_id in self._running_flows:
                del self._running_flows[flow_id]
    
    async def _execute_step(self, step: Dict[str, Any], context: FlowContext) -> Any:
        """执行步骤"""
        handler_name = step.get("handler", "default")
        handler = self._handlers.get(handler_name)
        config = step.get("config", {})
        
        if handler:
            return await handler.execute(context, config)
        return {"executed": True, "handler": handler_name}


class RuleEngine:
    """规则引擎"""
    
    def __init__(self):
        self._rules: List[Rule] = []
        self._action_handlers: Dict[RuleAction, Callable] = {
            RuleAction.ALLOW: lambda c, r: {"action": "allow"},
            RuleAction.DENY: lambda c, r: {"action": "deny"},
            RuleAction.LOG: lambda c, r: {"action": "log"},
        }
        logger.info("规则引擎初始化完成")
    
    def add_rule(self, rule: Rule):
        """添加规则"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        """评估规则"""
        results = []
        for rule in self._rules:
            if not rule.enabled:
                continue
            
            matched = await self._check_condition(rule.condition, data)
            result = RuleResult(rule.rule_id, matched, rule.action, f"规则 {rule.name} {'匹配' if matched else '不匹配'}")
            
            if matched:
                handler = self._action_handlers.get(rule.action)
                if handler:
                    handler(None, rule)
            
            results.append(result)
            
            if matched and rule.action == RuleAction.DENY:
                break
        
        return results
    
    async def _check_condition(self, condition: str, data: Dict[str, Any]) -> bool:
        """检查条件"""
        try:
            for key, value in data.items():
                if isinstance(value, str):
                    condition = condition.replace(f"${key}", f'"{value}"')
                else:
                    condition = condition.replace(f"${key}", str(value))
            return eval(condition, {"__builtins__": {}}, data)
        except Exception:
            return False


class BusinessLogicEngine:
    """
    业务逻辑引擎 - 主引擎类
    
    整合流程引擎和规则引擎。
    """
    
    def __init__(self):
        self.flow_engine = FlowEngine()
        self.rule_engine = RuleEngine()
        self._stats = {"flows_executed": 0, "flows_succeeded": 0, "flows_failed": 0}
        logger.info("业务逻辑引擎初始化完成")
    
    def register_flow(self, flow_id: str, flow_config: Dict[str, Any]):
        """注册流程"""
        self.flow_engine.register_flow(flow_id, flow_config)
    
    async def execute_flow(
        self,
        flow_id: str,
        session_id: str,
        user_id: str,
        data: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """执行流程"""
        context = FlowContext(flow_id=flow_id, session_id=session_id, user_id=user_id, data=data or {})
        result = await self.flow_engine.execute(flow_id, context)
        
        self._stats["flows_executed"] += 1
        if result.success:
            self._stats["flows_succeeded"] += 1
        else:
            self._stats["flows_failed"] += 1
        
        return result
    
    def add_rule(self, rule: Rule):
        """添加规则"""
        self.rule_engine.add_rule(rule)
    
    async def evaluate_rules(self, data: Dict[str, Any]) -> List[RuleResult]:
        """评估规则"""
        return await self.rule_engine.evaluate(data)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()


# 全局默认引擎
_default_engine: Optional[BusinessLogicEngine] = None


def get_default_business_engine() -> BusinessLogicEngine:
    """获取默认业务逻辑引擎"""
    global _default_engine
    if _default_engine is None:
        _default_engine = BusinessLogicEngine()
    return _default_engine
