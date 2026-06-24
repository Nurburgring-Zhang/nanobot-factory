"""
智影开发引擎 — 7步SDLC + 双AI互审强制流程
============================================
每次开发任务必须按此流程执行，不可跳过任何步骤。
双AI互审贯穿全程，每步执行前预审、执行后验证。

流程:
 Step 1: 全网检索 (web_search + session_search + fact_store)
 Step 2: 全局观念 (AGENTS.md规则 + 历史经验 + 相关skill)
 Step 3: 需求分析 (delegate_task子Agent深度分析)
 Step 4: 功能设置 (架构设计+技术选型+方案评审)
 Step 5: 软件开发 (TDD + 真实实现)
 Step 6: 审核测试 (测试 + 对抗式验证)
 Step 7: 交付上线 (复盘 + Memory提取 + 进化候选 + 齿轮注册)
"""

import sys
import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"      # 预审中
    APPROVED = "approved"        # 预审通过
    IN_PROGRESS = "in_progress"  # 执行中
    VERIFYING = "verifying"      # 验证中
    PASSED = "passed"            # 验证通过
    FAILED = "failed"            # 验证失败
    STOPPED = "stopped"          # 监督AI叫停


@dataclass
class ReviewRecord:
    step: str = ""
    action: str = ""            # pre_review / post_review / intervention
    tool_name: str = ""
    tool_args: dict = field(default_factory=dict)
    result: Any = None
    passed: bool = True
    reason: str = ""
    timestamp: float = 0.0


@dataclass
class DevTask:
    id: str = ""
    title: str = ""
    description: str = ""
    
    # 7步状态
    step1_search: StepStatus = StepStatus.PENDING
    step1_search_result: str = ""
    step2_context: StepStatus = StepStatus.PENDING
    step2_context_result: str = ""
    step3_analysis: StepStatus = StepStatus.PENDING
    step3_analysis_result: str = ""
    step4_design: StepStatus = StepStatus.PENDING
    step4_design_result: str = ""
    step5_dev: StepStatus = StepStatus.PENDING
    step5_dev_result: str = ""
    step6_test: StepStatus = StepStatus.PENDING
    step6_test_result: str = ""
    step7_deliver: StepStatus = StepStatus.PENDING
    step7_deliver_result: str = ""
    
    # 双审记录
    review_log: List[ReviewRecord] = field(default_factory=list)
    
    # 产出
    outputs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    # 全局上下文
    related_skills: List[str] = field(default_factory=list)
    history_sessions: List[str] = field(default_factory=list)
    fact_store_entries: List[str] = field(default_factory=list)


class ZhiyingDevEngine:
    """智影开发引擎 — 7步SDLC + 双AI互审"""
    
    # 高风险工具 — 预审自动拦截
    DANGEROUS_TOOLS = [
        "delete", "remove", "rm", "drop", "truncate",
        "shutdown", "reboot", "format", "purge",
    ]
    DANGEROUS_PATTERNS = [
        "rm -rf", "DROP TABLE", "DROP DATABASE",
        "> /dev/sda", "chmod 777", "format C:",
        "dd if=", "mkfs.", "fdisk",
    ]
    
    def __init__(self, task: DevTask = None):
        self.task = task or DevTask()
        self._current_step = 0
    
    # ========== 双AI互审 ==========
    
    def pre_review(self, step: str, tool_name: str, tool_args: dict) -> dict:
        """预审 — 工具调用前"""
        record = ReviewRecord(
            step=step, action="pre_review",
            tool_name=tool_name, tool_args=tool_args,
            timestamp=__import__('time').time(),
        )
        
        # 高风险工具检查
        for d in self.DANGEROUS_TOOLS:
            if d in tool_name.lower():
                record.passed = False
                record.reason = f"高风险工具: {tool_name}, 需要人类确认"
                self.task.review_log.append(record)
                return {"passed": False, "reason": record.reason, "intervention": "stop"}
        
        # 危险模式检查
        args_str = json.dumps(tool_args)
        for p in self.DANGEROUS_PATTERNS:
            if p in args_str:
                record.passed = False
                record.reason = f"检测到危险模式: {p}"
                self.task.review_log.append(record)
                return {"passed": False, "reason": record.reason, "intervention": "stop"}
        
        # 步骤完整性检查
        if step == "step3_analysis":
            if self.task.step1_search != StepStatus.PASSED:
                record.passed = False
                record.reason = "Step 1(全网检索)未完成, 不能进入Step 3"
                self.task.review_log.append(record)
                return {"passed": False, "reason": record.reason, "intervention": "stop"}
            if self.task.step2_context != StepStatus.PASSED:
                record.passed = False
                record.reason = "Step 2(全局观念)未完成, 不能进入Step 3"
                self.task.review_log.append(record)
                return {"passed": False, "reason": record.reason, "intervention": "stop"}
        
        if step == "step5_dev":
            for req_step in ["step3_analysis", "step4_design"]:
                if getattr(self.task, req_step) != StepStatus.PASSED:
                    record.passed = False
                    record.reason = f"{req_step}未完成, 不能进入Step 5"
                    self.task.review_log.append(record)
                    return {"passed": False, "reason": record.reason, "intervention": "stop"}
        
        record.passed = True
        record.reason = f"预审通过: {tool_name}"
        self.task.review_log.append(record)
        return {"passed": True, "reason": record.reason, "intervention": "none"}
    
    def post_review(self, step: str, tool_name: str, result: Any) -> dict:
        """验证 — 工具调用后"""
        record = ReviewRecord(
            step=step, action="post_review",
            tool_name=tool_name, result=str(result)[:500],
            timestamp=__import__('time').time(),
        )
        
        # 检查结果是否有错误
        if isinstance(result, dict) and result.get("error"):
            record.passed = False
            record.reason = f"执行错误: {result['error']}"
        
        # 检查是否有异常数据
        result_str = str(result)
        if "Traceback" in result_str or "Exception" in result_str:
            record.passed = False
            record.reason = f"执行异常(Traceback/Exception)"
        
        self.task.review_log.append(record)
        
        # 连续失败检测(最近3次)
        recent = [r for r in self.task.review_log[-5:] if r.action == "post_review"]
        if len(recent) >= 3 and all(not r.passed for r in recent[-3:]):
            return {"passed": False, "verdict": "连续3次失败, 建议切换模型或重新规划"}
        
        return {"passed": record.passed, "verdict": record.reason or "验证通过"}
    
    # ========== 7步流程 ==========
    
    def step1_search(self) -> dict:
        """Step 1: 全网检索"""
        self.task.step1_search = StepStatus.IN_REVIEW
        
        plan = {
            "step": 1,
            "name": "全网检索",
            "description": "通过web_search + session_search + fact_store三路并行收集信息",
            "actions": [
                {"tool": "web_search", "purpose": "获取最新技术和方案"},
                {"tool": "session_search", "purpose": "回顾历史对话经验"},
                {"tool": "fact_store", "purpose": "检索持久化知识"},
                {"tool": "skills_list", "purpose": "检索相关skill"},
            ],
            "output": "检索摘要 + 相关链接 + 经验教训",
            "pre_check": [
                "是否覆盖了至少3个信息源?",
                "是否有历史类似方案?",
                "有没有已踩过的坑需要避免?",
            ],
        }
        self.task.step1_search = StepStatus.APPROVED
        return plan
    
    def step2_context(self) -> dict:
        """Step 2: 全局观念建立"""
        self.task.step2_context = StepStatus.IN_REVIEW
        
        plan = {
            "step": 2,
            "name": "全局观念",
            "description": "读取AGENTS.md/SOUL.md规则 + 历史经验 + 相关skill",
            "actions": [
                {"tool": "read_file", "purpose": "读取AGENTS.md/SOUL.md/生产规范"},
                {"tool": "skill_view", "purpose": "加载相关skill"},
                {"tool": "memory", "purpose": "读取用户偏好和项目经验"},
            ],
            "output": "规则约束清单 + 可复用模式 + 注意事项",
            "pre_check": [
                "是否读过SOUL.md核心规则?",
                "是否有相关skill未加载?",
                "格林主人的偏好是否已考虑?",
            ],
        }
        self.task.step2_context = StepStatus.APPROVED
        return plan
    
    def step3_analysis(self) -> dict:
        """Step 3: 需求分析"""
        self.task.step3_analysis = StepStatus.IN_REVIEW
        
        plan = {
            "step": 3,
            "name": "需求分析",
            "description": "使用delegate_task创建子Agent深度分析需求",
            "actions": [
                {"tool": "delegate_task", "purpose": "子Agent深度分析需求"},
                {"tool": "clarify", "purpose": "如有歧义需澄清"},
            ],
            "output": "需求文档 + 功能清单 + 优先级排序",
            "pre_check": [
                "Step 1是否已完成?",
                "是否有未澄清的歧义?",
                "功能点是否可验证?",
            ],
        }
        self.task.step3_analysis = StepStatus.APPROVED
        return plan
    
    def step4_design(self) -> dict:
        """Step 4: 功能设置"""
        self.task.step4_design = StepStatus.IN_REVIEW
        
        plan = {
            "step": 4,
            "name": "功能设置",
            "description": "架构设计 + 技术选型 + 方案评审",
            "actions": [
                {"tool": "delegate_task", "purpose": "专家系统评审方案"},
                {"tool": "write_file", "purpose": "输出设计文档"},
            ],
            "output": "架构设计文档 + 技术选型理由 + 评审记录",
            "pre_check": [
                "是否对比了至少2种方案?",
                "架构是否可扩展?",
                "技术选型是否有充分理由?",
            ],
        }
        self.task.step4_design = StepStatus.APPROVED
        return plan
    
    def step5_dev(self) -> dict:
        """Step 5: 软件开发"""
        self.task.step5_dev = StepStatus.IN_REVIEW
        
        plan = {
            "step": 5,
            "name": "软件开发",
            "description": "TDD驱动 + 真实实现（禁止占位符）",
            "actions": [
                {"tool": "write_file", "purpose": "实现代码"},
                {"tool": "terminal", "purpose": "运行测试"},
                {"tool": "patch", "purpose": "修改代码"},
                {"tool": "execute_code", "purpose": "验证逻辑"},
            ],
            "output": "可运行的代码 + 测试 + 文档",
            "pre_check": [
                "Step 4设计文档是否已完成?",
                "是否有占位符/模拟数据?",
                "是否先写了测试?",
            ],
            "quality_gates": [
                "禁止纯静态展示",
                "禁止mock数据代替真实实现",
                "每个函数都要有docstring",
                "所有异常路径要处理",
            ],
        }
        self.task.step5_dev = StepStatus.APPROVED
        return plan
    
    def step6_test(self) -> dict:
        """Step 6: 审核测试"""
        self.task.step6_test = StepStatus.IN_REVIEW
        
        plan = {
            "step": 6,
            "name": "审核测试",
            "description": "测试 + 对抗式验证（两个不同视角验证）",
            "actions": [
                {"tool": "terminal", "purpose": "运行测试套件"},
                {"tool": "delegate_task", "purpose": "对抗式验证"},
            ],
            "output": "测试报告 + 验证记录",
            "pre_check": [
                "测试覆盖率是否达标?",
                "是否检查了边界情况?",
                "是否有对抗式验证?",
            ],
        }
        self.task.step6_test = StepStatus.APPROVED
        return plan
    
    def step7_deliver(self) -> dict:
        """Step 7: 交付上线"""
        self.task.step7_deliver = StepStatus.IN_REVIEW
        
        plan = {
            "step": 7,
            "name": "交付上线",
            "description": "复盘 + Memory提取 + 进化候选 + 齿轮注册",
            "actions": [
                {"tool": "memory", "purpose": "将经验写入永久记忆"},
                {"tool": "skill_manage", "purpose": "如果需要保存为skill"},
            ],
            "output": "交付物 + 复盘报告 + 记忆更新",
            "pre_check": [
                "所有Step是否已完成?",
                "产出物是否可验证?",
                "经验教训是否已提取?",
            ],
        }
        self.task.step7_deliver = StepStatus.APPROVED
        return plan
    
    def get_workflow(self) -> List[dict]:
        """获取完整7步工作流"""
        return [
            self.step1_search(),
            self.step2_context(),
            self.step3_analysis(),
            self.step4_design(),
            self.step5_dev(),
            self.step6_test(),
            self.step7_deliver(),
        ]
    
    def get_status_report(self) -> dict:
        """获取当前任务状态报告"""
        steps = [
            ("Step 1 全网检索", self.task.step1_search),
            ("Step 2 全局观念", self.task.step2_context),
            ("Step 3 需求分析", self.task.step3_analysis),
            ("Step 4 功能设置", self.task.step4_design),
            ("Step 5 软件开发", self.task.step5_dev),
            ("Step 6 审核测试", self.task.step6_test),
            ("Step 7 交付上线", self.task.step7_deliver),
        ]
        
        status_map = {s.value: s.name for s in StepStatus}
        
        report = {
            "task": self.task.title,
            "steps": [(name, status_map[s.value]) for name, s in steps],
            "reviews": len(self.task.review_log),
            "interventions": sum(1 for r in self.task.review_log if not r.passed),
            "outputs": self.task.outputs,
            "errors": self.task.errors,
        }
        return report


# ========== 快捷入口 ==========

def create_dev_task(title: str, description: str = "") -> DevTask:
    """创建一个新的开发任务"""
    import uuid
    return DevTask(
        id=f"dev_{uuid.uuid4().hex[:8]}",
        title=title,
        description=description,
    )


def get_workflow_plan(task: DevTask) -> List[dict]:
    """获取开发任务的完整7步工作流"""
    engine = ZhiyingDevEngine(task)
    return engine.get_workflow()


# ========== 预审/验证快捷函数 ==========

def pre_review(step: str, tool: str, args: dict) -> dict:
    """预审 — 在每次工具调用前调用"""
    import time
    # 高风险拦截
    dangerous_tools = ["delete", "remove", "rm -rf", "drop", "shutdown", "format"]
    for d in dangerous_tools:
        if d in tool.lower():
            return {"passed": False, "reason": f"高风险工具: {tool}", "intervention": "stop"}
    
    args_str = json.dumps(args)
    dangerous_patterns = ["rm -rf /", "DROP TABLE", "DROP DATABASE", "format C:", "dd if="]
    for p in dangerous_patterns:
        if p in args_str:
            return {"passed": False, "reason": f"危险模式: {p}", "intervention": "stop"}
    
    return {"passed": True, "reason": "通过", "intervention": "none"}


def post_review(step: str, tool: str, result: Any) -> dict:
    """验证 — 在每次工具调用后调用"""
    result_str = str(result)
    if "Traceback" in result_str or "Exception" in result_str:
        return {"passed": False, "verdict": "执行异常"}
    if isinstance(result, dict) and result.get("error"):
        return {"passed": False, "verdict": f"错误: {result['error']}"}
    return {"passed": True, "verdict": "通过"}
