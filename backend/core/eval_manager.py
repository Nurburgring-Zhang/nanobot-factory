"""模型评测与反馈闭环 — 评测任务/Bad Case/反馈闭环"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class EvalTaskType(str, Enum):
    AUTO_OBJECTIVE = "auto_objective"
    MANUAL_SUBJECTIVE = "manual_subjective"
    AB_TEST = "ab_test"
    BAD_CASE_MINING = "bad_case_mining"
    BIAS_SAFETY = "bias_safety"
    ROBUSTNESS = "robustness"


class EvalStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BadCaseStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    FIXED = "fixed"
    VERIFIED = "verified"
    CLOSED = "closed"


# 合法BadCase状态转换
_BAD_CASE_TRANSITIONS = {
    BadCaseStatus.OPEN: {BadCaseStatus.ASSIGNED},
    BadCaseStatus.ASSIGNED: {BadCaseStatus.FIXED},
    BadCaseStatus.FIXED: {BadCaseStatus.VERIFIED},
    BadCaseStatus.VERIFIED: {BadCaseStatus.CLOSED},
    BadCaseStatus.CLOSED: set(),
}


class EvalMetric(BaseModel):
    name: str
    value: float
    details: Dict[str, Any] = {}


class EvalTask(BaseModel):
    id: str
    name: str
    type: EvalTaskType = EvalTaskType.AUTO_OBJECTIVE
    model_id: str = ""
    model_version: str = ""
    dataset_id: str = ""
    metrics: List[EvalMetric] = []
    status: EvalStatus = EvalStatus.PENDING
    created_by: str = ""
    created_at: str = ""
    completed_at: str = ""


class BadCase(BaseModel):
    id: str
    eval_task_id: str = ""
    item_id: str = ""
    model_output: str = ""
    reference: str = ""
    error_type: str = ""
    severity: int = 3
    status: BadCaseStatus = BadCaseStatus.OPEN
    correction_task_id: str = ""
    created_at: str = ""
    closed_at: str = ""


class FeedbackLoop(BaseModel):
    id: str
    name: str = ""
    trigger_eval_task_id: str = ""
    bad_case_count: int = 0
    root_cause_analysis: str = ""
    actions_taken: Dict[str, Any] = {}
    new_dataset_version: str = ""
    retrained_model: str = ""
    improvement_metrics: Dict[str, float] = {}
    created_at: str = ""
    closed_at: str = ""


class EvalManager(PersistentManager):
    _db_table = "eval_tasks"
    _db_fields = ["id","name","type","model_id","model_version","dataset_id","metrics","status","created_by","created_at","completed_at"]
    _db_table_bad_cases = "eval_bad_cases"
    _db_fields_bad_cases = ["id","eval_task_id","item_id","model_output","reference","error_type","severity","status","correction_task_id","created_at","closed_at"]
    _db_table_feedback = "eval_feedback_loops"
    _db_fields_feedback = ["id","name","trigger_eval_task_id","bad_case_count","root_cause_analysis","actions_taken","new_dataset_version","retrained_model","improvement_metrics","created_at","closed_at"]

    def __init__(self):
        self._tasks: Dict[str, EvalTask] = {}
        self._bad_cases: Dict[str, BadCase] = {}
        self._feedback_loops: Dict[str, FeedbackLoop] = {}
        super().__init__()
        self._ensure_table(self._db_table_bad_cases, self._db_fields_bad_cases)
        self._ensure_table(self._db_table_feedback, self._db_fields_feedback)
        self._load_from_db()
        self._load_bad_cases_from_db()
        self._load_feedback_loops_from_db()

    def _load_from_db(self):
        for row in self._load_all(self._db_table, self._db_fields):
            task = EvalTask(**row)
            self._tasks[task.id] = task

    def _load_bad_cases_from_db(self):
        for row in self._load_all(self._db_table_bad_cases, self._db_fields_bad_cases):
            bc = BadCase(**row)
            self._bad_cases[bc.id] = bc

    def _load_feedback_loops_from_db(self):
        for row in self._load_all(self._db_table_feedback, self._db_fields_feedback):
            fl = FeedbackLoop(**row)
            self._feedback_loops[fl.id] = fl

    def _save_bad_case(self, bc: BadCase):
        self._save(bc.id, bc.model_dump(), table=self._db_table_bad_cases, fields=self._db_fields_bad_cases)

    def _save_feedback_loop(self, fl: FeedbackLoop):
        self._save(fl.id, fl.model_dump(), table=self._db_table_feedback, fields=self._db_fields_feedback)

    def create_eval_task(
        self,
        name: str,
        model_id: str,
        dataset_id: str,
        type: EvalTaskType = EvalTaskType.AUTO_OBJECTIVE,
    ) -> EvalTask:
        task = EvalTask(
            id=f"eval-{uuid.uuid4().hex[:8]}",
            name=name,
            model_id=model_id,
            dataset_id=dataset_id,
            type=type,
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task.id] = task
        self._save(task.id, task.model_dump())
        return task

    def add_metric(
        self, task_id: str, name: str, value: float, details: Dict = None
    ) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.metrics.append(
            EvalMetric(name=name, value=value, details=details or {})
        )
        self._save(task.id, task.model_dump())
        return True

    def complete_eval(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = EvalStatus.COMPLETED
        task.completed_at = datetime.now().isoformat()
        self._save(task.id, task.model_dump())
        return True

    def add_bad_case(
        self,
        eval_task_id: str,
        item_id: str,
        error_type: str,
        model_output: str = "",
        reference: str = "",
        severity: int = 3,
    ) -> BadCase:
        bc = BadCase(
            id=f"bc-{uuid.uuid4().hex[:8]}",
            eval_task_id=eval_task_id,
            item_id=item_id,
            error_type=error_type,
            severity=severity,
            model_output=model_output,
            reference=reference,
            created_at=datetime.now().isoformat(),
        )
        self._bad_cases[bc.id] = bc
        self._save_bad_case(bc)
        return bc

    def get_bad_cases(
        self,
        eval_task_id: str = "",
        error_type: str = "",
        status: Optional[BadCaseStatus] = None,
    ) -> List[BadCase]:
        results = list(self._bad_cases.values())
        if eval_task_id:
            results = [bc for bc in results if bc.eval_task_id == eval_task_id]
        if error_type:
            results = [bc for bc in results if bc.error_type == error_type]
        if status:
            results = [bc for bc in results if bc.status == status]
        return results

    def assign_bad_case(self, bc_id: str, task_id: str) -> bool:
        bc = self._bad_cases.get(bc_id)
        if not bc:
            return False
        bc.correction_task_id = task_id
        bc.status = BadCaseStatus.ASSIGNED
        self._save_bad_case(bc)
        return True

    def update_bad_case_status(self, bc_id: str, new_status: BadCaseStatus) -> bool:
        """BadCase状态转换：open→assigned→fixed→verified→closed"""
        bc = self._bad_cases.get(bc_id)
        if not bc:
            return False
        allowed = _BAD_CASE_TRANSITIONS.get(bc.status, set())
        if new_status not in allowed:
            return False
        bc.status = new_status
        if new_status == BadCaseStatus.CLOSED:
            bc.closed_at = datetime.now().isoformat()
        self._save_bad_case(bc)
        return True

    def create_feedback_loop(self, name: str, trigger_task_id: str) -> Optional[FeedbackLoop]:
        """创建反馈闭环，检查eval_task是否存在"""
        if trigger_task_id not in self._tasks:
            return None
        bc_count = len(self.get_bad_cases(trigger_task_id))
        fl = FeedbackLoop(
            id=f"fl-{uuid.uuid4().hex[:8]}",
            name=name,
            trigger_eval_task_id=trigger_task_id,
            bad_case_count=bc_count,
            created_at=datetime.now().isoformat(),
        )
        self._feedback_loops[fl.id] = fl
        self._save_feedback_loop(fl)
        return fl

    def complete_feedback_loop(
        self,
        fl_id: str,
        new_dataset_ver: str,
        retrained_model: str,
        improvements: Dict[str, float],
    ) -> bool:
        fl = self._feedback_loops.get(fl_id)
        if not fl:
            return False
        fl.new_dataset_version = new_dataset_ver
        fl.retrained_model = retrained_model
        fl.improvement_metrics = improvements
        fl.closed_at = datetime.now().isoformat()
        self._save_feedback_loop(fl)
        return True

    def get_eval_task(self, task_id: str) -> Optional[EvalTask]:
        return self._tasks.get(task_id)

    def list_eval_tasks(self, model_id: str = "") -> List[EvalTask]:
        if model_id:
            return [t for t in self._tasks.values() if t.model_id == model_id]
        return list(self._tasks.values())

    def get_feedback_loops(self) -> List[FeedbackLoop]:
        return list(self._feedback_loops.values())
