"""P1-A3-W2: 众包任务定价 + 结算引擎

流程:
1. price_task — 基于 type / difficulty / deadline 动态定价
2. lock_price — 标注员接单, 锁定价格
3. settle — 审核通过 → 钱包增加 / 不通过 → 记录但不支付
4. withdraw — 提现申请 (mock)

设计:
- 纯内存 store (wallet / tasks / withdrawals)
- 价格公式: base * (1 + 0.2 * (difficulty-1)) * (1 + 0.3 * urgency_factor)
- 钱包按 worker_id 隔离
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── 价格常量 ────────────────────────────────────────────────────────────────

TASK_TYPE_BASE_PRICE: Dict[str, float] = {
    "image_annotation": 2.0,
    "text_classification": 1.0,
    "bbox_annotation": 3.0,
    "audio_transcription": 4.0,
    "video_labeling": 5.0,
    "default": 1.5,
}

DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 5

# 截止时间紧迫度 (hours → factor):
#   >= 168h (1 周): 0.0 (无加成)
#   48-168h:       0.1
#   24-48h:        0.2
#   < 24h:         0.3
DEADLINE_THRESHOLDS: List[Tuple[float, float]] = [
    (168.0, 0.0),
    (48.0, 0.1),
    (24.0, 0.2),
    (0.0, 0.3),
]


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class Task:
    task_id: str
    task_type: str
    difficulty: int
    deadline_hours: float
    price: float
    status: str = "open"  # open / locked / settled / failed
    locked_by: Optional[str] = None
    locked_at: Optional[float] = None
    settled: bool = False
    settlement_amount: float = 0.0
    created_at: float = field(default_factory=time.time)


@dataclass
class Withdrawal:
    withdrawal_id: str
    worker_id: str
    amount: float
    status: str = "pending"  # pending / approved / rejected
    created_at: float = field(default_factory=time.time)


# ── 引擎 ────────────────────────────────────────────────────────────────────

class CrowdSettlementEngine:
    """众包任务定价 + 结算 + 钱包管理."""

    def __init__(self) -> None:
        # task_id -> Task
        self.tasks: Dict[str, Task] = {}
        # worker_id -> balance
        self.wallets: Dict[str, float] = {}
        # worker_id -> total earned
        self.total_earned: Dict[str, float] = {}
        # withdrawal_id -> Withdrawal
        self.withdrawals: Dict[str, Withdrawal] = {}
        # worker_id -> List[withdrawal_id]  (注意: 不要叫 withdraw_history, 跟方法重名)
        self._wd_index: Dict[str, List[str]] = {}

    # ── 定价 ────────────────────────────────────────────────────────────

    def price_task(self, task_type: str, difficulty: int, deadline_hours: float) -> float:
        """动态定价: base * (1 + 0.2*(d-1)) * (1 + 0.3*urgency).

        difficulty 在 [1, 5], deadline_hours >= 0
        """
        # 参数校验 (raise 不抛, 返回 -1 让调用方 catch)
        if not isinstance(difficulty, int) or difficulty < DIFFICULTY_MIN or difficulty > DIFFICULTY_MAX:
            raise ValueError(f"difficulty must be int in [{DIFFICULTY_MIN},{DIFFICULTY_MAX}], got {difficulty}")
        if not isinstance(deadline_hours, (int, float)) or deadline_hours < 0:
            raise ValueError(f"deadline_hours must be non-negative number, got {deadline_hours}")

        base = TASK_TYPE_BASE_PRICE.get(task_type, TASK_TYPE_BASE_PRICE["default"])
        difficulty_factor = 1.0 + 0.2 * (difficulty - 1)
        urgency = 0.0
        for threshold, factor in DEADLINE_THRESHOLDS:
            if deadline_hours >= threshold:
                urgency = factor
                break
        urgency_factor = 1.0 + 0.3 * urgency

        price = base * difficulty_factor * urgency_factor
        return round(price, 4)

    def create_task(
        self, task_type: str, difficulty: int, deadline_hours: float,
        task_id: Optional[str] = None,
    ) -> Task:
        """创建并定价一个任务."""
        price = self.price_task(task_type, difficulty, deadline_hours)
        tid = task_id or f"task_{uuid.uuid4().hex[:12]}"
        task = Task(
            task_id=tid,
            task_type=task_type,
            difficulty=difficulty,
            deadline_hours=float(deadline_hours),
            price=price,
        )
        self.tasks[tid] = task
        return task

    # ── 接单 ────────────────────────────────────────────────────────────

    def lock_price(self, task_id: str, worker_id: str) -> Dict[str, Any]:
        """标注员接单, 锁定价格.

        锁定后 price 不可变 (后续 price_task 调用不影响).
        重复 lock 同 task → 返回已有锁定.
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"task '{task_id}' not found")
        if not worker_id or not isinstance(worker_id, str):
            raise ValueError("worker_id must be non-empty string")

        if task.status == "open":
            task.locked_by = worker_id
            task.locked_at = time.time()
            task.status = "locked"
        elif task.status == "locked" and task.locked_by != worker_id:
            raise PermissionError(f"task '{task_id}' already locked by '{task.locked_by}'")
        # else: 同 worker 重复 lock → idempotent, 返回当前状态

        return {
            "task_id": task.task_id,
            "worker_id": task.locked_by,
            "locked_price": task.price,
            "locked_at": task.locked_at,
            "status": task.status,
        }

    # ── 结算 ────────────────────────────────────────────────────────────

    def settle(self, task_id: str, passed: bool, reviewer: str = "system") -> Dict[str, Any]:
        """结算: passed=True → 钱包增加, False → 仅记录不支付.

        幂等: 重复 settle 同 task 返回已有结果.
        """
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"task '{task_id}' not found")

        if task.status == "settled":
            # 幂等: 返回已有结算
            return {
                "task_id": task.task_id,
                "passed": task.settlement_amount > 0,
                "amount": task.settlement_amount,
                "worker_id": task.locked_by,
                "status": task.status,
                "idempotent": True,
            }

        if task.status != "locked":
            raise ValueError(f"task '{task_id}' not in locked state (status={task.status})")
        if task.locked_by is None:
            raise ValueError(f"task '{task_id}' has no locked worker")

        worker_id = task.locked_by
        if passed:
            amount = task.price
            self._credit_wallet(worker_id, amount)
            task.settlement_amount = amount
            task.status = "settled"
        else:
            # 不通过: 记录但钱包不变
            task.settlement_amount = 0.0
            task.status = "failed"

        return {
            "task_id": task.task_id,
            "passed": passed,
            "amount": task.settlement_amount if passed else 0.0,
            "worker_id": worker_id,
            "status": task.status,
            "reviewer": reviewer,
            "idempotent": False,
        }

    def _credit_wallet(self, worker_id: str, amount: float) -> None:
        self.wallets[worker_id] = round(self.wallets.get(worker_id, 0.0) + amount, 4)
        self.total_earned[worker_id] = round(self.total_earned.get(worker_id, 0.0) + amount, 4)

    # ── 钱包 / 提现 ────────────────────────────────────────────────────

    def get_wallet(self, worker_id: str) -> Dict[str, Any]:
        return {
            "worker_id": worker_id,
            "balance": round(self.wallets.get(worker_id, 0.0), 4),
            "total_earned": round(self.total_earned.get(worker_id, 0.0), 4),
            "total_withdrawn": round(
                sum(w.amount for wid in self._wd_index.get(worker_id, [])
                    for w in [self.withdrawals[wid]] if w.status == "approved"),
                4,
            ),
        }

    def withdraw(self, worker_id: str, amount: float) -> Dict[str, Any]:
        """提现申请. amount 必须 > 0 且 <= 余额."""
        if not isinstance(amount, (int, float)):
            raise ValueError("amount must be number")
        if amount <= 0:
            raise ValueError(f"amount must be positive, got {amount}")

        balance = self.wallets.get(worker_id, 0.0)
        if amount > balance:
            raise ValueError(f"insufficient balance: requested {amount}, available {balance}")

        wid = f"wd_{uuid.uuid4().hex[:12]}"
        wd = Withdrawal(withdrawal_id=wid, worker_id=worker_id, amount=round(amount, 4))
        self.withdrawals[wid] = wd
        self._wd_index.setdefault(worker_id, []).append(wid)
        # 立即扣减钱包 (mock 流程: 申请即扣减, 后续 admin 审核)
        self.wallets[worker_id] = round(balance - amount, 4)
        wd.status = "approved"  # mock 默认通过

        return {
            "withdrawal_id": wid,
            "worker_id": worker_id,
            "amount": wd.amount,
            "status": wd.status,
            "remaining_balance": self.wallets[worker_id],
            "created_at": wd.created_at,
        }

    def withdraw_history(self, worker_id: str) -> List[Dict[str, Any]]:
        """获取 worker 的提现历史."""
        ids = self._wd_index.get(worker_id, [])
        return [{
            "withdrawal_id": wid,
            "worker_id": worker_id,
            "amount": self.withdrawals[wid].amount,
            "status": self.withdrawals[wid].status,
            "created_at": self.withdrawals[wid].created_at,
        } for wid in ids if wid in self.withdrawals]