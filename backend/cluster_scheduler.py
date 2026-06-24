#!/usr/bin/env python3
"""
Nanobot Factory - Multi-Agent Cluster Scheduler
Smart task distribution and parallel execution for multiple agents

@author MiniMax Agent
@date 2026-02-25
@description 多Agent集群调度器，支持Smart Forking Detection智能任务分发
"""

import os
import json
import logging
import asyncio
import hashlib
import time
import threading
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent status"""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"
    OFFLINE = "offline"


class TaskPriority(int, Enum):
    """Task priority levels"""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class Agent:
    """Represents an agent in the cluster"""
    id: str
    name: str
    model: str
    provider: str
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_execution_time: float = 0.0
    capabilities: List[str] = field(default_factory=list)
    max_concurrent: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_heartbeat: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ClusterTask:
    """Task to be executed by the cluster"""
    id: str
    name: str
    task_type: str  # generation, analysis, processing, etc.
    payload: Dict[str, Any]
    priority: TaskPriority = TaskPriority.NORMAL
    required_capabilities: List[str] = field(default_factory=list)

    # Dependencies
    depends_on: List[str] = field(default_factory=list)

    # Execution
    status: str = "pending"  # pending, scheduled, running, completed, failed
    assigned_agent_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Timing
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    scheduled_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Parallelism score (computed by Smart Forking Detection)
    parallelism_score: float = 0.0
    can_parallelize: bool = False


class SmartForkingDetector:
    """
    Smart Forking Detection algorithm.
    Analyzes tasks to determine if they can be parallelized.
    """

    @staticmethod
    def analyze_parallelism(task: ClusterTask, history: Dict[str, Any]) -> Dict[str, float]:
        """
        Analyze task to determine parallelism potential.

        Returns:
            Dict with 'score' (0-1), 'can_parallelize' (bool), and 'reasoning'
        """
        score = 0.0
        reasoning = []

        # Check dependencies
        if not task.depends_on:
            score += 0.3
            reasoning.append("No dependencies - can run independently")
        else:
            reasoning.append(f"Has {len(task.depends_on)} dependencies")

        # Check task type
        batch_types = {'batch_generate', 'batch_analyze', 'batch_process'}
        if task.task_type in batch_types:
            score += 0.4
            reasoning.append(f"Task type '{task.task_type}' supports batch processing")
        elif task.task_type in {'generation', 'analysis'}:
            score += 0.2
            reasoning.append(f"Task type '{task.task_type}' can be parallelized")

        # Check data independence
        payload_size = len(json.dumps(task.payload))
        if payload_size < 10000:  # Small payload = more parallelizable
            score += 0.2
            reasoning.append("Small payload size - data independent")
        elif payload_size < 100000:
            score += 0.1
            reasoning.append("Medium payload size")

        # Check historical success rate
        task_type_history = history.get(task.task_type, {})
        success_rate = task_type_history.get('success_rate', 0.8)
        score += success_rate * 0.2
        reasoning.append(f"Historical success rate: {success_rate:.1%}")

        # Cap at 1.0
        score = min(1.0, score)

        return {
            'score': score,
            'can_parallelize': score >= 0.5,
            'reasoning': reasoning
        }


class AgentCluster:
    """
    Multi-Agent Cluster Scheduler.
    Manages agent allocation, task distribution, and parallel execution.
    """

    def __init__(self, max_concurrent_tasks: int = 10):
        self.max_concurrent_tasks = max_concurrent_tasks
        self.agents: Dict[str, Agent] = {}
        self.tasks: Dict[str, ClusterTask] = {}
        self.task_queue: List[str] = []  # Task IDs in priority order

        # Task history for Smart Forking Detection
        self.task_history: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total': 0,
            'success': 0,
            'failed': 0,
            'avg_time': 0.0
        })

        # Execution state
        self._running = False
        self._executor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Callbacks
        self._on_task_scheduled: Optional[Callable] = None
        self._on_task_completed: Optional[Callable] = None
        self._on_task_failed: Optional[Callable] = None

        # Statistics
        self.stats = {
            'total_tasks_scheduled': 0,
            'total_tasks_completed': 0,
            'total_tasks_failed': 0,
            'total_execution_time': 0.0
        }

    def set_callbacks(self,
                     on_task_scheduled: Optional[Callable] = None,
                     on_task_completed: Optional[Callable] = None,
                     on_task_failed: Optional[Callable] = None):
        """Set event callbacks"""
        self._on_task_scheduled = on_task_scheduled
        self._on_task_completed = on_task_completed
        self._on_task_failed = on_task_failed

    # =========================================================================
    # Agent Management
    # =========================================================================

    def register_agent(self, agent: Agent) -> bool:
        """Register a new agent to the cluster"""
        with self._lock:
            if agent.id in self.agents:
                logger.warning(f"Agent {agent.id} already registered")
                return False

            self.agents[agent.id] = agent
            logger.info(f"Registered agent: {agent.name} ({agent.id})")
            return True

    def unregister_agent(self, agent_id: str) -> bool:
        """Unregister an agent from the cluster"""
        with self._lock:
            if agent_id not in self.agents:
                return False

            agent = self.agents[agent_id]
            if agent.status == AgentStatus.BUSY:
                logger.warning(f"Cannot unregister busy agent {agent_id}")
                return False

            del self.agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
            return True

    def get_available_agents(self, required_capabilities: List[str] = None) -> List[Agent]:
        """Get list of available (idle) agents"""
        with self._lock:
            available = [
                a for a in self.agents.values()
                if a.status == AgentStatus.IDLE
            ]

            # Filter by capabilities if required
            if required_capabilities:
                available = [
                    a for a in available
                    if all(cap in a.capabilities for cap in required_capabilities)
                ]

            return available

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID"""
        return self.agents.get(agent_id)

    def update_agent_status(self, agent_id: str, status: AgentStatus):
        """Update agent status"""
        with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].status = status
                self.agents[agent_id].last_heartbeat = datetime.now().isoformat()

    # =========================================================================
    # Task Management
    # =========================================================================

    def submit_task(self, task: ClusterTask) -> str:
        """
        Submit a new task to the cluster.
        Returns task ID.
        """
        with self._lock:
            # Generate task ID if not provided
            if not task.id:
                task.id = str(uuid.uuid4())[:8]

            # Analyze parallelism using Smart Forking Detection
            analysis = SmartForkingDetector.analyze_parallelism(task, self.task_history)
            task.parallelism_score = analysis['score']
            task.can_parallelize = analysis['can_parallelize']

            # Store task
            self.tasks[task.id] = task

            # Add to priority queue
            self._add_to_queue(task.id)

            logger.info(f"Submitted task: {task.name} (id={task.id}, score={task.parallelism_score:.2f})")
            return task.id

    def _add_to_queue(self, task_id: str):
        """Add task to priority queue"""
        task = self.tasks[task_id]

        # Check if dependencies are met
        if not self._dependencies_met(task_id):
            return

        # Insert based on priority
        inserted = False
        for i, existing_id in enumerate(self.task_queue):
            existing = self.tasks[existing_id]
            if task.priority > existing.priority:
                self.task_queue.insert(i, task_id)
                inserted = True
                break

        if not inserted:
            self.task_queue.append(task_id)

    def _dependencies_met(self, task_id: str) -> bool:
        """Check if all dependencies are completed"""
        task = self.tasks[task_id]
        for dep_id in task.depends_on:
            dep = self.tasks.get(dep_id)
            if not dep or dep.status != 'completed':
                return False
        return True

    def get_task(self, task_id: str) -> Optional[ClusterTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return False

            if task.status in ['completed', 'failed']:
                return False

            # If assigned to agent, try to cancel
            if task.assigned_agent_id:
                agent = self.agents.get(task.assigned_agent_id)
                if agent and agent.current_task_id == task_id:
                    agent.current_task_id = None
                    agent.status = AgentStatus.IDLE

            task.status = 'cancelled'
            if task_id in self.task_queue:
                self.task_queue.remove(task_id)

            logger.info(f"Cancelled task: {task_id}")
            return True

    # =========================================================================
    # Scheduling
    # =========================================================================

    def _schedule_task(self, task_id: str) -> bool:
        """
        Schedule a task to an available agent.
        Returns True if successfully scheduled.
        """
        task = self.tasks.get(task_id)
        if not task or task.status != 'pending':
            return False

        # Check dependencies
        if not self._dependencies_met(task_id):
            return False

        # Find available agent
        available_agents = self.get_available_agents(task.required_capabilities)
        if not available_agents:
            return False

        # Select best agent (least loaded)
        best_agent = min(available_agents, key=lambda a: a.tasks_completed)

        # Assign task
        task.status = 'scheduled'
        task.assigned_agent_id = best_agent.id
        task.scheduled_at = datetime.now().isoformat()

        best_agent.status = AgentStatus.BUSY
        best_agent.current_task_id = task_id

        # Remove from queue
        if task_id in self.task_queue:
            self.task_queue.remove(task_id)

        self.stats['total_tasks_scheduled'] += 1

        if self._on_task_scheduled:
            self._on_task_scheduled(task, best_agent)

        logger.info(f"Scheduled task {task_id} to agent {best_agent.id}")
        return True

    def _run_scheduler(self):
        """Main scheduling loop"""
        while self._running:
            try:
                with self._lock:
                    # Count running tasks
                    running = sum(
                        1 for a in self.agents.values()
                        if a.status == AgentStatus.BUSY
                    )

                    # Schedule if under limit
                    if running < self.max_concurrent_tasks:
                        # Try to schedule from queue
                        for task_id in list(self.task_queue):
                            if self._schedule_task(task_id):
                                running += 1
                                if running >= self.max_concurrent_tasks:
                                    break

                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(1.0)

    def start(self):
        """Start the cluster scheduler"""
        if self._running:
            return

        self._running = True
        self._executor_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self._executor_thread.start()
        logger.info("Agent cluster scheduler started")

    def stop(self):
        """Stop the cluster scheduler"""
        self._running = False
        if self._executor_thread:
            self._executor_thread.join(timeout=5.0)
        logger.info("Agent cluster scheduler stopped")

    # =========================================================================
    # Task Execution Callbacks
    # =========================================================================

    def complete_task(self, task_id: str, result: Dict[str, Any]):
        """Mark task as completed"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            task.status = 'completed'
            task.result = result
            task.completed_at = datetime.now().isoformat()

            # Update agent
            if task.assigned_agent_id:
                agent = self.agents.get(task.assigned_agent_id)
                if agent:
                    agent.status = AgentStatus.IDLE
                    agent.current_task_id = None
                    agent.tasks_completed += 1

                    # Update avg execution time
                    if task.started_at and task.completed_at:
                        start = datetime.fromisoformat(task.started_at)
                        end = datetime.fromisoformat(task.completed_at)
                        exec_time = (end - start).total_seconds()
                        agent.avg_execution_time = (
                            (agent.avg_execution_time * (agent.tasks_completed - 1) + exec_time)
                            / agent.tasks_completed
                        )

            # Update history
            self.task_history[task.task_type]['total'] += 1
            self.task_history[task.task_type]['success'] += 1

            # Check dependents
            self._check_dependents(task_id)

            self.stats['total_tasks_completed'] += 1

            if self._on_task_completed:
                self._on_task_completed(task)

            logger.info(f"Task completed: {task_id}")

    def fail_task(self, task_id: str, error: str):
        """Mark task as failed"""
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                return

            task.status = 'failed'
            task.error = error
            task.completed_at = datetime.now().isoformat()

            # Update agent
            if task.assigned_agent_id:
                agent = self.agents.get(task.assigned_agent_id)
                if agent:
                    agent.status = AgentStatus.IDLE
                    agent.current_task_id = None
                    agent.tasks_failed += 1

            # Update history
            self.task_history[task.task_type]['total'] += 1
            self.task_history[task.task_type]['failed'] += 1

            self.stats['total_tasks_failed'] += 1

            if self._on_task_failed:
                self._on_task_failed(task, error)

            logger.error(f"Task failed: {task_id} - {error}")

    def _check_dependents(self, completed_task_id: str):
        """Check if any pending tasks can now be scheduled"""
        for task_id, task in self.tasks.items():
            if task.status == 'pending' and completed_task_id in task.depends_on:
                if self._dependencies_met(task_id):
                    self._add_to_queue(task_id)

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_cluster_stats(self) -> Dict[str, Any]:
        """Get cluster statistics"""
        with self._lock:
            agents_by_status = defaultdict(int)
            for agent in self.agents.values():
                agents_by_status[agent.status.value] += 1

            tasks_by_status = defaultdict(int)
            for task in self.tasks.values():
                tasks_by_status[task.status] += 1

            return {
                'agents': {
                    'total': len(self.agents),
                    'by_status': dict(agents_by_status),
                    'idle': len([a for a in self.agents.values() if a.status == AgentStatus.IDLE]),
                    'busy': len([a for a in self.agents.values() if a.status == AgentStatus.BUSY])
                },
                'tasks': {
                    'total': len(self.tasks),
                    'by_status': dict(tasks_by_status),
                    'pending': len([t for t in self.tasks.values() if t.status == 'pending']),
                    'running': len([t for t in self.tasks.values() if t.status == 'running']),
                    'completed': len([t for t in self.tasks.values() if t.status == 'completed']),
                    'failed': len([t for t in self.tasks.values() if t.status == 'failed'])
                },
                'queue_length': len(self.task_queue),
                'max_concurrent': self.max_concurrent_tasks,
                'stats': self.stats
            }

    def get_agent_stats(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific agent"""
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        return {
            'id': agent.id,
            'name': agent.name,
            'model': agent.model,
            'provider': agent.provider,
            'status': agent.status.value,
            'current_task_id': agent.current_task_id,
            'tasks_completed': agent.tasks_completed,
            'tasks_failed': agent.tasks_failed,
            'avg_execution_time': agent.avg_execution_time,
            'capabilities': agent.capabilities,
            'uptime': (datetime.now() - datetime.fromisoformat(agent.created_at)).total_seconds()
        }


# =========================================================================
# Global Instance
# =========================================================================

_cluster: Optional[AgentCluster] = None


def get_agent_cluster() -> AgentCluster:
    """Get global agent cluster instance"""
    global _cluster
    if _cluster is None:
        _cluster = AgentCluster(max_concurrent_tasks=10)
    return _cluster


# =========================================================================
# Example Usage
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create cluster
    cluster = AgentCluster(max_concurrent_tasks=4)

    # Register agents
    agents = [
        Agent(id="agent-1", name="Claude-3-5", model="claude-3.5-sonnet", provider="anthropic",
              capabilities=["generation", "analysis", "reasoning"]),
        Agent(id="agent-2", name="GPT-4", model="gpt-4-turbo", provider="openai",
              capabilities=["generation", "analysis"]),
        Agent(id="agent-3", name="Gemini-Pro", model="gemini-pro", provider="google",
              capabilities=["analysis", "reasoning"])
    ]

    for agent in agents:
        cluster.register_agent(agent)

    # Start cluster
    cluster.start()

    # Submit tasks
    tasks = [
        ClusterTask(
            id="task-1",
            name="Generate Images",
            task_type="batch_generate",
            payload={"prompts": ["a cat", "a dog"]},
            priority=TaskPriority.HIGH
        ),
        ClusterTask(
            id="task-2",
            name="Analyze Data",
            task_type="analysis",
            payload={"data": "some data"},
            priority=TaskPriority.NORMAL
        ),
        ClusterTask(
            id="task-3",
            name="Process Results",
            task_type="processing",
            payload={},
            priority=TaskPriority.LOW,
            depends_on=["task-1"]
        )
    ]

    for task in tasks:
        cluster.submit_task(task)

    # Wait for execution
    print("\n=== Initial Cluster State ===")
    stats = cluster.get_cluster_stats()
    print(f"Agents: {stats['agents']}")
    print(f"Tasks: {stats['tasks']}")

    # Simulate task completion
    time.sleep(2)
    cluster.complete_task("task-1", {"status": "success", "output": ["img1.png", "img2.png"]})

    time.sleep(1)
    print("\n=== Final Cluster State ===")
    stats = cluster.get_cluster_stats()
    print(f"Agents: {stats['agents']}")
    print(f"Tasks: {stats['tasks']}")

    # Stop cluster
    cluster.stop()
