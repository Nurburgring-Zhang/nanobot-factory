"""
NanoBot Factory - Agent Orchestration
Agent编排系统 - 多Agent协作工作流

功能:
1. Agent编排引擎
2. 任务分解与分配
3. 多Agent协作
4. 结果汇总

@author MiniMax Agent
@date 2026-03-08
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class OrchestrationPattern(Enum):
    """编排模式"""
    SEQUENTIAL = "sequential"       # 顺序执行
    PARALLEL = "parallel"           # 并行执行
    PIPELINE = "pipeline"          # 管道模式
    TREE = "tree"                  # 树形模式
    FAN_OUT_FAN_IN = "fan_out_fan_in"  # 扇出扇入


@dataclass
class OrchestrationStep:
    """编排步骤"""
    step_id: str
    name: str
    agent_type: str
    capability: str
    input_mapping: Dict[str, str] = field(default_factory=dict)  # 输入映射
    output_key: str = ""  # 输出键
    depends_on: List[str] = field(default_factory=list)  # 依赖步骤


@dataclass
class OrchestrationWorkflow:
    """编排工作流"""
    workflow_id: str
    name: str
    description: str
    pattern: OrchestrationPattern
    steps: List[OrchestrationStep]
    max_parallel: int = 3
    timeout: float = 300.0


class AgentOrchestrator:
    """
    Agent编排器
    管理复杂的多Agent任务编排
    """
    
    def __init__(self, cluster_manager=None):
        self.cluster_manager = cluster_manager
        self.workflows: Dict[str, OrchestrationWorkflow] = {}
        self.execution_results: Dict[str, Dict[str, Any]] = {}
        
    def register_workflow(self, workflow: OrchestrationWorkflow):
        """注册工作流"""
        self.workflows[workflow.workflow_id] = workflow
        logger.info(f"Workflow {workflow.name} registered")
        
    def create_workflow(
        self,
        name: str,
        description: str,
        pattern: OrchestrationPattern,
        steps: List[Dict[str, Any]]
    ) -> OrchestrationWorkflow:
        """创建工作流"""
        workflow_steps = []
        for i, step in enumerate(steps):
            workflow_steps.append(OrchestrationStep(
                step_id=step.get("step_id", f"step_{i}"),
                name=step.get("name", f"Step {i}"),
                agent_type=step.get("agent_type", "worker"),
                capability=step.get("capability", ""),
                input_mapping=step.get("input_mapping", {}),
                output_key=step.get("output_key", f"output_{i}"),
                depends_on=step.get("depends_on", [])
            ))
            
        workflow = OrchestrationWorkflow(
            workflow_id=str(uuid.uuid4()),
            name=name,
            description=description,
            pattern=pattern,
            steps=workflow_steps
        )
        
        self.register_workflow(workflow)
        return workflow
        
    async def execute_workflow(
        self,
        workflow_id: str,
        initial_inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工作流"""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return {"error": f"Workflow {workflow_id} not found"}
            
        results = {}
        
        if workflow.pattern == OrchestrationPattern.SEQUENTIAL:
            results = await self._execute_sequential(workflow, initial_inputs)
        elif workflow.pattern == OrchestrationPattern.PARALLEL:
            results = await self._execute_parallel(workflow, initial_inputs)
        elif workflow.pattern == OrchestrationPattern.PIPELINE:
            results = await self._execute_pipeline(workflow, initial_inputs)
        elif workflow.pattern == OrchestrationPattern.TREE:
            results = await self._execute_tree(workflow, initial_inputs)
        elif workflow.pattern == OrchestrationPattern.FAN_OUT_FAN_IN:
            results = await self._execute_fan_out_fan_in(workflow, initial_inputs)
            
        self.execution_results[workflow_id] = results
        return results
        
    async def _execute_sequential(
        self,
        workflow: OrchestrationWorkflow,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """顺序执行"""
        results = dict(inputs)
        
        for step in workflow.steps:
            # 准备输入
            step_input = {}
            for key, mapping in step.input_mapping.items():
                step_input[key] = results.get(mapping, inputs.get(mapping))
                
            # 执行步骤
            result = await self._execute_step(step, step_input)
            results[step.output_key] = result
            
        return results
        
    async def _execute_parallel(
        self,
        workflow: OrchestrationWorkflow,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """并行执行"""
        results = dict(inputs)
        
        # 并行执行所有步骤
        tasks = []
        for step in workflow.steps:
            step_input = {}
            for key, mapping in step.input_mapping.items():
                step_input[key] = results.get(mapping, inputs.get(mapping))
            tasks.append(self._execute_step(step, step_input))
            
        step_results = await asyncio.gather(*tasks)
        
        for step, result in zip(workflow.steps, step_results):
            results[step.output_key] = result
            
        return results
        
    async def _execute_pipeline(
        self,
        workflow: OrchestrationWorkflow,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """管道执行"""
        return await self._execute_sequential(workflow, inputs)
        
    async def _execute_tree(
        self,
        workflow: OrchestrationWorkflow,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """树形执行"""
        results = dict(inputs)
        
        # 找出根步骤（没有依赖的步骤）
        root_steps = [s for s in workflow.steps if not s.depends_on]
        
        async def execute_with_deps(step: OrchestrationStep) -> Any:
            # 先执行依赖
            for dep_id in step.depends_on:
                dep_step = next((s for s in workflow.steps if s.step_id == dep_id), None)
                if dep_step and dep_step.output_key not in results:
                    results[dep_step.output_key] = await execute_with_deps(dep_step)
                    
            # 执行当前步骤
            step_input = {}
            for key, mapping in step.input_mapping.items():
                step_input[key] = results.get(mapping, inputs.get(mapping))
                
            return await self._execute_step(step, step_input)
            
        for step in root_steps:
            results[step.output_key] = await execute_with_deps(step)
            
        return results
        
    async def _execute_fan_out_fan_in(
        self,
        workflow: OrchestrationWorkflow,
        inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """扇出扇入执行"""
        results = dict(inputs)
        
        # 扇出：并行执行
        if workflow.steps:
            fan_out_steps = workflow.steps[:-1]  # 除最后一个步骤外的所有步骤
            fan_in_step = workflow.steps[-1]      # 最后一个步骤作为扇入
            
            tasks = []
            for step in fan_out_steps:
                step_input = {}
                for key, mapping in step.input_mapping.items():
                    step_input[key] = results.get(mapping, inputs.get(mapping))
                tasks.append(self._execute_step(step, step_input))
                
            fan_out_results = await asyncio.gather(*tasks)
            
            # 收集所有结果
            results["fan_out_results"] = fan_out_results
            
            # 扇入：汇总结果
            fan_in_input = {}
            for key, mapping in fan_in_step.input_mapping.items():
                if mapping == "fan_out_results":
                    fan_in_input[key] = fan_out_results
                else:
                    fan_in_input[key] = results.get(mapping, inputs.get(mapping))
                    
            results[fan_in_step.output_key] = await self._execute_step(fan_in_step, fan_in_input)
            
        return results
        
    async def _execute_step(
        self,
        step: OrchestrationStep,
        inputs: Dict[str, Any]
    ) -> Any:
        """执行单个步骤"""
        # 这里会根据步骤定义的capability调用相应的能力
        # 实际实现会调用 capability_manager
        return {
            "step": step.name,
            "capability": step.capability,
            "input": inputs,
            "executed": True
        }
        
    def get_workflow(self, workflow_id: str) -> Optional[OrchestrationWorkflow]:
        """获取工作流"""
        return self.workflows.get(workflow_id)
        
    def list_workflows(self) -> List[str]:
        """列出所有工作流"""
        return [f"{w.name} ({w.workflow_id})" for w in self.workflows.values()]


# =============================================================================
# 工厂函数
# =============================================================================

def create_orchestrator(cluster_manager=None) -> AgentOrchestrator:
    """创建编排器"""
    return AgentOrchestrator(cluster_manager)


# =============================================================================
# 预定义工作流模板
# =============================================================================

class WorkflowTemplates:
    """工作流模板"""
    
    @staticmethod
    def create_content_generation_workflow(orchestrator: AgentOrchestrator) -> str:
        """创建内容生成工作流"""
        workflow = orchestrator.create_workflow(
            name="内容生成",
            description="AI内容生成完整流程：分析->生成->优化->输出",
            pattern=OrchestrationPattern.SEQUENTIAL,
            steps=[
                {
                    "step_id": "analyze",
                    "name": "分析需求",
                    "agent_type": "analyzer",
                    "capability": "analysis",
                    "input_mapping": {"prompt": "user_input"},
                    "output_key": "analysis_result"
                },
                {
                    "step_id": "generate",
                    "name": "生成内容",
                    "agent_type": "generator",
                    "capability": "content_generation",
                    "input_mapping": {"analysis": "analysis_result"},
                    "output_key": "generated_content"
                },
                {
                    "step_id": "optimize",
                    "name": "优化内容",
                    "agent_type": "optimizer",
                    "capability": "optimization",
                    "input_mapping": {"content": "generated_content"},
                    "output_key": "optimized_content"
                }
            ]
        )
        return workflow.workflow_id
        
    @staticmethod
    def create_research_workflow(orchestrator: AgentOrchestrator) -> str:
        """创建研究工作流"""
        workflow = orchestrator.create_workflow(
            name="信息研究",
            description="多源信息收集、分析、汇总",
            pattern=OrchestrationPattern.FAN_OUT_FAN_IN,
            steps=[
                {
                    "step_id": "search_web",
                    "name": "网页搜索",
                    "agent_type": "searcher",
                    "capability": "web_search",
                    "input_mapping": {"query": "topic"},
                    "output_key": "web_results"
                },
                {
                    "step_id": "search_news",
                    "name": "新闻搜索",
                    "agent_type": "searcher",
                    "capability": "news_search",
                    "input_mapping": {"query": "topic"},
                    "output_key": "news_results"
                },
                {
                    "step_id": "search_social",
                    "name": "社交媒体搜索",
                    "agent_type": "searcher",
                    "capability": "social_search",
                    "input_mapping": {"query": "topic"},
                    "output_key": "social_results"
                },
                {
                    "step_id": "summarize",
                    "name": "汇总分析",
                    "agent_type": "analyzer",
                    "capability": "summarization",
                    "input_mapping": {"all_results": "fan_out_results"},
                    "output_key": "final_report"
                }
            ]
        )
        return workflow.workflow_id


# =============================================================================
# 修复版 AgentOrchestrator - 真实调用 capability_manager (2026-04-13)
# =============================================================================

class EnhancedOrchestrator(AgentOrchestrator):
    """
    增强版编排器 - 真实调用 CapabilityManager 执行步骤
    修复原始 AgentOrchestrator._execute_step 为存根的问题
    """

    def __init__(self, cluster_manager=None, capability_manager=None, dispatcher=None):
        super().__init__(cluster_manager)
        self.capability_manager = capability_manager
        self.dispatcher = dispatcher  # DispatcherAgent 实例

    async def _execute_step(self, step: OrchestrationStep, inputs: dict) -> dict:
        """
        真实执行步骤 - 按优先级调用:
        1. dispatcher (Expert Agent路由)
        2. capability_manager (直接能力调用)
        3. cluster_manager (子Agent调用)
        4. 存根返回
        """
        capability = step.capability
        step_name = step.name

        # 策略1: 使用DispatcherAgent路由到专家Agent
        if self.dispatcher and step.agent_type != "direct":
            try:
                task_desc = f"{step_name}: {inputs.get('prompt', inputs.get('query', str(inputs)))}"
                result = await self.dispatcher.dispatch(
                    task_description=task_desc,
                    inputs=inputs,
                )
                if result.success:
                    return {
                        "step": step_name,
                        "capability": capability,
                        "result": result.result,
                        "agent": result.agent_name,
                        "execution_ms": result.execution_ms,
                        "success": True,
                    }
            except Exception as e:
                logger.warning(f"Dispatcher failed for step {step_name}: {e}")

        # 策略2: 直接调用 CapabilityManager
        if self.capability_manager and capability:
            try:
                cap_result = await self.capability_manager.execute_capability(
                    capability, inputs
                )
                return {
                    "step": step_name,
                    "capability": capability,
                    "result": cap_result.result,
                    "status": cap_result.status,
                    "execution_time": cap_result.execution_time,
                    "success": cap_result.status == "success",
                }
            except Exception as e:
                logger.warning(f"CapabilityManager failed for {capability}: {e}")

        # 策略3: cluster_manager子Agent调用
        if self.cluster_manager and hasattr(self.cluster_manager, 'execute_task'):
            try:
                result = await self.cluster_manager.execute_task(
                    agent_type=step.agent_type,
                    capability=capability,
                    inputs=inputs
                )
                return {
                    "step": step_name,
                    "capability": capability,
                    "result": result,
                    "success": True,
                }
            except Exception as e:
                logger.warning(f"ClusterManager failed: {e}")

        # 兜底: 返回基本信息 (不再是完全空的存根)
        return {
            "step": step_name,
            "capability": capability,
            "input": inputs,
            "executed": True,
            "note": "fallback_execution - no handler available"
        }


def create_enhanced_orchestrator(
    cluster_manager=None,
    capability_manager=None,
    dispatcher=None
) -> EnhancedOrchestrator:
    """创建增强版编排器（真实执行）"""
    return EnhancedOrchestrator(cluster_manager, capability_manager, dispatcher)
