"""算法在线审核+审批流引擎"""
from __future__ import annotations
import time
import json
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum


class ReviewStep(str, Enum):
    SUBMIT = "submit"
    PRE_REVIEW = "pre_review"
    TECHNICAL_REVIEW = "technical_review"
    FINAL_APPROVAL = "final_approval"
    DEPLOY = "deploy"


# 审批流顺序映射
FLOW_ORDER = [
    ReviewStep.SUBMIT,
    ReviewStep.PRE_REVIEW,
    ReviewStep.TECHNICAL_REVIEW,
    ReviewStep.FINAL_APPROVAL,
    ReviewStep.DEPLOY,
]


@dataclass
class AlgorithmSubmission:
    """算法提交"""
    id: str
    name: str
    version: str
    model_path: str
    metrics: Dict[str, float] = field(default_factory=dict)
    status: str = "submitted"
    errors: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    deployed_version: Optional[str] = None


@dataclass
class ReviewWorkflow:
    """审批流 - 管理多级审批步骤"""
    submission_id: str
    current_step: ReviewStep = ReviewStep.SUBMIT
    steps: Dict[str, dict] = field(default_factory=dict)
    approved_by: Dict[str, str] = field(default_factory=dict)  # step -> reviewer
    rejected: bool = False
    rejected_reason: str = ""


class AlgorithmReview:
    """算法审核 - 多级审批流、自动预审、部署/回滚"""

    def __init__(self):
        self.submissions: Dict[str, AlgorithmSubmission] = {}
        self.workflows: Dict[str, ReviewWorkflow] = {}
        self._deployments: List[dict] = []

    # ── submit ──

    def submit_algorithm(self, algo_id: str, name: str, version: str,
                         model_path: str, metrics: Optional[Dict[str, float]] = None) -> AlgorithmSubmission:
        sub = AlgorithmSubmission(
            id=algo_id,
            name=name,
            version=version,
            model_path=model_path,
            metrics=metrics or {},
            status="submitted",
        )
        self.submissions[algo_id] = sub

        wf = ReviewWorkflow(submission_id=algo_id)
        wf.steps["submit"] = {"status": "completed", "timestamp": time.time()}
        self.workflows[algo_id] = wf

        return sub

    def advance_workflow(self, algo_id: str) -> bool:
        """将审批流推进到下一步"""
        wf = self.workflows.get(algo_id)
        if not wf or wf.rejected:
            return False
        idx = FLOW_ORDER.index(wf.current_step)
        if idx + 1 >= len(FLOW_ORDER):
            return False
        wf.current_step = FLOW_ORDER[idx + 1]
        wf.steps[wf.current_step.value] = {"status": "pending", "timestamp": time.time()}
        sub = self.submissions.get(algo_id)
        if sub:
            sub.status = wf.current_step.value
            sub.updated_at = time.time()
        return True

    # ── pre-review (auto validation) ──

    def run_pre_review(self, algo_id: str,
                       model_file_exists: bool = True,
                       metrics_valid: bool = True) -> Tuple[bool, List[str]]:
        """自动预审：检查模型文件完整性、指标有效性"""
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf:
            return False, ["submission not found"]

        errors = []

        # 1) 检查模型文件是否存在（由参数控制）
        if not model_file_exists:
            errors.append(f"model file not found: {sub.model_path}")

        # 2) 检查 metrics
        if not sub.metrics:
            errors.append("no metrics provided")
        elif not metrics_valid:
            errors.append("metrics validation failed")

        # 3) 检查版本号格式
        if not sub.version or not isinstance(sub.version, str):
            errors.append("invalid version format")

        sub.errors = errors
        passed = len(errors) == 0

        if passed:
            sub.status = "pre_review_passed"
            wf.steps["pre_review"] = {"status": "passed", "timestamp": time.time()}
            # 通过预审后自动前进到 technical_review 步骤
            self.advance_workflow(algo_id)  # submit -> pre_review
            self.advance_workflow(algo_id)  # pre_review -> technical_review
        else:
            sub.status = "pre_review_failed"
            wf.steps["pre_review"] = {"status": "failed", "errors": errors, "timestamp": time.time()}

        return passed, errors

    # ── technical review ──

    def schedule_technical_review(self, algo_id: str, reviewer: str) -> bool:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf or wf.current_step != ReviewStep.TECHNICAL_REVIEW:
            return False

        wf.steps["technical_review"] = {
            "status": "in_progress",
            "reviewer": reviewer,
            "timestamp": time.time(),
        }
        sub.status = "in_technical_review"
        sub.updated_at = time.time()
        return True

    def approve_technical_review(self, algo_id: str, reviewer: str,
                                 comments: str = "") -> bool:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf:
            return False

        wf.steps["technical_review"] = {
            "status": "approved",
            "reviewer": reviewer,
            "comments": comments,
            "timestamp": time.time(),
        }
        wf.approved_by["technical_review"] = reviewer
        sub.status = "technical_review_passed"
        sub.updated_at = time.time()
        self.advance_workflow(algo_id)
        return True

    def reject_technical_review(self, algo_id: str, reviewer: str,
                                reason: str = "") -> bool:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf:
            return False

        wf.steps["technical_review"] = {
            "status": "rejected",
            "reviewer": reviewer,
            "reason": reason,
            "timestamp": time.time(),
        }
        wf.rejected = True
        wf.rejected_reason = reason
        sub.status = "rejected"
        sub.updated_at = time.time()
        return True

    # ── final approval ──

    def final_approval(self, algo_id: str, approver: str) -> bool:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf or wf.current_step != ReviewStep.FINAL_APPROVAL:
            return False

        wf.steps["final_approval"] = {
            "status": "approved",
            "approver": approver,
            "timestamp": time.time(),
        }
        wf.approved_by["final_approval"] = approver
        sub.status = "approved"
        sub.updated_at = time.time()
        self.advance_workflow(algo_id)
        return True

    # ── deploy ──

    def deploy(self, algo_id: str, deployed_by: str) -> bool:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf or wf.current_step != ReviewStep.DEPLOY:
            return False

        deploy_info = {
            "algo_id": algo_id,
            "name": sub.name,
            "version": sub.version,
            "deployed_by": deployed_by,
            "timestamp": time.time(),
            "action": "deploy",
        }
        self._deployments.append(deploy_info)
        sub.status = "deployed"
        sub.deployed_version = sub.version
        sub.updated_at = time.time()
        wf.steps["deploy"] = {"status": "completed", "deployed_by": deployed_by, "timestamp": time.time()}
        return True

    def rollback(self, algo_id: str, deployed_by: str,
                 target_version: Optional[str] = None) -> bool:
        """回滚到指定版本或上一个版本"""
        sub = self.submissions.get(algo_id)
        if not sub or sub.status != "deployed":
            return False

        rollback_info = {
            "algo_id": algo_id,
            "name": sub.name,
            "from_version": sub.deployed_version,
            "to_version": target_version or "previous",
            "deployed_by": deployed_by,
            "timestamp": time.time(),
            "action": "rollback",
        }
        self._deployments.append(rollback_info)
        sub.deployed_version = target_version
        sub.status = "rolled_back"
        sub.updated_at = time.time()
        return True

    # ── status ──

    def get_workflow_status(self, algo_id: str) -> dict:
        sub = self.submissions.get(algo_id)
        wf = self.workflows.get(algo_id)
        if not sub or not wf:
            return {}
        return {
            "submission_id": sub.id,
            "name": sub.name,
            "version": sub.version,
            "status": sub.status,
            "current_step": wf.current_step.value,
            "rejected": wf.rejected,
            "rejected_reason": wf.rejected_reason,
            "steps": wf.steps,
            "approved_by": wf.approved_by,
            "deployed_version": sub.deployed_version,
        }
