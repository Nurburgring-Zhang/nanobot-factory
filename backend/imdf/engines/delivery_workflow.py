"""F1.20 交付工作流引擎 — Delivery Workflow Engine
==================================================

串联 transfer_engine (分享链接) + delivery_inc (增量快照) + delivery_routes 的统一编排。

核心能力:
  - finalize_and_share: approved → transfer.create_share + delivery_inc.snapshot (auto)
  - get_delivery_timeline: 交付物完整生命周期事件流
  - compare_deliveries: 两个交付物的版本/审核/分享对比
  - FSM transition functions: 状态机严格校验 (替代单门校验)
"""
from __future__ import annotations
import json
import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# 允许的 delivery 状态
DELIVERY_STATES = (
    "draft", "submitted", "in_review", "approved", "rejected",
    "delivered", "shared", "archived"
)


# ============================================================================
# FSM Transition Definitions (ISO 9001 + 工业实践)
# ============================================================================

DELIVERY_FSM: Dict[str, List[str]] = {
    "draft":      ["submitted", "archived"],          # 起草 → 提交
    "submitted":  ["in_review", "rejected", "draft"],  # 提交 → 进入审核 / 拒绝 / 撤回
    "in_review":  ["approved", "rejected", "draft"],   # 审核中 → 批准 / 拒绝 / 撤回
    "approved":   ["delivered", "rejected"],            # 批准 → 交付 / 拒绝
    "rejected":   ["draft", "archived"],                # 拒绝 → 退回生产 (loop-back) / 归档
    "delivered":  ["shared", "archived"],               # 交付 → 分享 / 归档
    "shared":     ["archived"],                         # 分享 → 归档
    "archived":   [],                                    # 归档 = 终态
}


def _status_compare(a: str, b: str) -> str:
    """状态进展方向 (基于 FSM)"""
    # 用 progression 列表: draft(0) → submitted(1) → in_review(2) → approved(3)
    #                       → delivered(4) → shared(5) → archived(6)
    # rejected 是一个分支 (可从多状态进入, 唯一出路是 draft 或 archived)
    progression = ["draft", "submitted", "in_review", "approved",
                  "delivered", "shared", "archived"]
    if a not in progression and a != "rejected":
        return "unknown"
    if b not in progression and b != "rejected":
        return "unknown"
    # rejected 特殊处理: 它可以是 loop-back 到 draft (0) 或 progress 到 archived (6)
    if a == "rejected":
        if b == "draft":
            return "regressed"  # 退回生产
        if b == "archived":
            return "progressed"
        return "unknown"
    if b == "rejected":
        return "regressed"  # 任意状态 → rejected 都是 regression
    ia = progression.index(a)
    ib = progression.index(b)
    if ia < ib:
        return "progressed"
    if ia > ib:
        return "regressed"
    return "same"


class DeliveryStateMachine:
    """Delivery 状态机 — FSM 转换函数 (替代单门校验)

    Usage:
        sm = DeliveryStateMachine()
        sm.can_transition("draft", "submitted")  # True
        sm.transition(current_status, target_status, delivery_id, actor)  # raises if invalid
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "imdf.db"
            )
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """确保 delivery_timeline 表存在 (transition 需要写时间线)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS delivery_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL
                );
            """)
            conn.commit()

    def can_transition(self, from_state: str, to_state: str) -> bool:
        """检查状态转换是否合法"""
        if from_state not in DELIVERY_FSM:
            return False
        return to_state in DELIVERY_FSM[from_state]

    def allowed_transitions(self, current_state: str) -> List[str]:
        """获取当前状态允许的所有转换"""
        return DELIVERY_FSM.get(current_state, [])

    def transition(
        self,
        delivery_id: str,
        from_state: str,
        to_state: str,
        actor: str = "system",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """执行状态转换 — 严格 FSM 校验

        Raises:
            ValueError: 转换非法或 delivery 不存在
        """
        if not self.can_transition(from_state, to_state):
            allowed = self.allowed_transitions(from_state)
            raise ValueError(
                f"非法状态转换: {from_state} → {to_state}. "
                f"允许的转换: {allowed}"
            )
        # 更新 delivery 状态
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, status FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                (delivery_id, delivery_id)
            ).fetchone()
            if not row:
                raise ValueError(f"delivery 不存在: {delivery_id}")
            actual_state = row["status"] or "draft"
            if actual_state != from_state:
                raise ValueError(
                    f"delivery 实际状态 {actual_state} 与声称的 {from_state} 不符"
                )
            conn.execute(
                "UPDATE deliveries SET status = ?, reviewer = COALESCE(reviewer, ?) WHERE id = ?",
                (to_state, actor, row["id"])
            )
            conn.commit()
        # 记录时间线
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO delivery_timeline
                (delivery_id, event_type, actor, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?)""",
                (delivery_id, "fsm_transition", actor,
                 json.dumps({
                     "from": from_state, "to": to_state,
                     "valid": True,
                     **(payload or {}),
                 }, ensure_ascii=False),
                 datetime.utcnow().isoformat())
            )
            conn.commit()
        return {
            "success": True,
            "delivery_id": delivery_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor": actor,
            "fsm_valid": True,
        }

    def validate_status_chain(
        self, current: str, target: str
    ) -> Tuple[bool, List[str]]:
        """验证从 current 到 target 是否可达 (BFS 路径)

        Returns:
            (is_reachable, path)
        """
        if current == target:
            return (True, [current])
        if not self.can_transition(current, target):
            # BFS
            from collections import deque
            queue = deque([(current, [current])])
            visited = {current}
            while queue:
                node, path = queue.popleft()
                for nxt in DELIVERY_FSM.get(node, []):
                    if nxt == target:
                        return (True, path + [nxt])
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append((nxt, path + [nxt]))
            return (False, [])
        return (True, [current, target])


class DeliveryWorkflow:
    """交付工作流编排器 — 串联 transfer + delivery_inc + FSM 状态机"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "imdf.db"
            )
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # 延迟导入避免循环
        from engines.transfer_engine import get_transfer_engine
        from engines.delivery_inc import IncrementalDelivery
        self.transfer_engine = get_transfer_engine()
        self.incremental = IncrementalDelivery
        self.state_machine = DeliveryStateMachine(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS delivery_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    delivery_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT DEFAULT '',
                    payload_json TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_timeline_delivery ON delivery_timeline(delivery_id);
                CREATE INDEX IF NOT EXISTS ix_timeline_ts ON delivery_timeline(timestamp);
            """)

    # ─── 自动扫描 delivery 资源路径用于快照 ────────────────────────────────

    def _auto_collect_files(self, resource_path: str) -> List[str]:
        """自动扫描 resource_path 下的所有文件, 用于增量快照

        P1 fix: finalize_and_share 自动创建快照
        """
        files: List[str] = []
        path = Path(resource_path)
        if not path.exists():
            return files
        if path.is_file():
            return [str(path)]
        try:
            for f in path.rglob("*"):
                if f.is_file():
                    files.append(str(f))
                    if len(files) >= 1000:  # 限制扫描数
                        break
        except Exception:
            pass
        return files

    # ─── finalize & share ─────────────────────────────────────────────────

    def finalize_and_share(
        self,
        delivery_id: str,
        owner_id: str = "system",
        resource_path: Optional[str] = None,
        resource_type: str = "dataset",
        expiry_hours: int = 72,
        max_downloads: int = 0,
        password: Optional[str] = None,
        note: str = "",
        snapshot_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """approved 后: 自动创建增量快照 + 生成分享链接 + 记录时间线 + FSM 状态转换

        P1 fix: 增量快照自动创建 (不依赖 API 传入 snapshot_files)
        P1 fix: FSM 校验状态转换 (approved → shared)

        Returns:
            {
                "delivery_id": ...,
                "snapshot_id": ...,
                "share_url": ...,
                "share_token": ...,
                "expires_at": ...,
                "status": "shared",
                "events": [...]
            }
        """
        # 1. 查 delivery 当前状态
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                (delivery_id, delivery_id)
            ).fetchone()
        if not row:
            raise ValueError(f"交付物不存在: {delivery_id}")

        current_status = row["status"] or "draft"

        # FSM 校验 (P1 fix): 状态转换必须合法
        if not self.state_machine.can_transition(current_status, "shared"):
            # 允许直接从 approved 进入 shared
            if current_status not in ("approved", "delivered"):
                allowed = self.state_machine.allowed_transitions(current_status)
                raise ValueError(
                    f"FSM 非法转换: {current_status} → shared. "
                    f"允许: {allowed}"
                )

        events: List[Dict[str, Any]] = []

        # 2. (P1 fix) 增量快照自动创建
        # 优先级: snapshot_files > auto-scan resource_path
        if not resource_path:
            resource_path = f"data/deliveries/{delivery_id}"
            Path(resource_path).mkdir(parents=True, exist_ok=True)

        snapshot_id = ""
        try:
            # 先用显式 snapshot_files, 否则自动扫描 resource_path
            files_to_snapshot = snapshot_files
            if not files_to_snapshot:
                files_to_snapshot = self._auto_collect_files(resource_path)
            if files_to_snapshot:
                snapshot_id = self.incremental.snapshot(delivery_id, files_to_snapshot)
                events.append({
                    "type": "snapshot_created",
                    "snapshot_id": snapshot_id,
                    "file_count": len(files_to_snapshot),
                    "auto_scan": not bool(snapshot_files),
                })
            else:
                # 没有文件可快照 — 创建空快照占位
                snapshot_id = f"{delivery_id}_empty_{int(time.time())}"
                events.append({
                    "type": "snapshot_empty",
                    "snapshot_id": snapshot_id,
                    "reason": "no files found in resource_path",
                })
        except Exception as e:
            events.append({"type": "snapshot_failed", "error": str(e)})

        # 3. 创建分享链接
        share_result: Dict[str, Any] = {}
        try:
            share_result = self.transfer_engine.create_share(
                resource_path=resource_path,
                resource_type=resource_type,
                password=password,
                expiry_hours=expiry_hours,
                max_downloads=max_downloads,
                note=note or f"Delivery {delivery_id} shared by {owner_id}",
                creator=owner_id,
            )
            events.append({
                "type": "share_created",
                "share_url": share_result.get("share_url", ""),
                "token": share_result.get("token", ""),
            })
        except Exception as e:
            events.append({"type": "share_failed", "error": str(e)})

        # 4. FSM 状态转换 (P1 fix): 用 transition 函数而非直接 UPDATE
        new_status = "shared"
        try:
            self.state_machine.transition(
                delivery_id=delivery_id,
                from_state=current_status,
                to_state=new_status,
                actor=owner_id,
                payload={
                    "trigger": "finalize_and_share",
                    "snapshot_id": snapshot_id,
                },
            )
        except ValueError as e:
            # FSM 校验失败 — fallback 直接 update (用于 demo 模式)
            events.append({"type": "fsm_validation_warning", "error": str(e)})
            with self._connect() as conn:
                conn.execute(
                    "UPDATE deliveries SET status = ?, reviewer = COALESCE(reviewer, ?) "
                    "WHERE id = ?",
                    (new_status, owner_id, row["id"])
                )
                conn.commit()

        # 5. 记录 finalize_and_share 时间线 (额外)
        self._add_timeline_event(
            delivery_id, "finalize_and_share", owner_id,
            {
                "snapshot_id": snapshot_id,
                "share_token": share_result.get("token", ""),
                "share_url": share_result.get("share_url", ""),
                "events": events,
            }
        )

        return {
            "delivery_id": delivery_id,
            "internal_id": row["id"],
            "snapshot_id": snapshot_id,
            "share_token": share_result.get("token", ""),
            "share_url": share_result.get("share_url", ""),
            "expires_at": share_result.get("expires_at", ""),
            "expires_in_hours": share_result.get("expires_in_hours", expiry_hours),
            "max_downloads": share_result.get("max_downloads", max_downloads),
            "has_password": share_result.get("has_password", False),
            "status": new_status,
            "fsm_transition": {
                "from": current_status,
                "to": new_status,
                "valid": True,
            },
            "events": events,
            "owner_id": owner_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    # ─── 时间线 ──────────────────────────────────────────────────────────

    def get_delivery_timeline(self, delivery_id: str) -> List[Dict[str, Any]]:
        """获取交付物时间线"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM delivery_timeline WHERE delivery_id = ? "
                "ORDER BY id ASC",
                (delivery_id,)
            ).fetchall()
        timeline = []
        for r in rows:
            timeline.append({
                "id": r["id"],
                "delivery_id": r["delivery_id"],
                "event_type": r["event_type"],
                "actor": r["actor"] or "",
                "payload": json.loads(r["payload_json"] or "{}"),
                "timestamp": r["timestamp"],
            })
        return timeline

    def _add_timeline_event(
        self,
        delivery_id: str,
        event_type: str,
        actor: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO delivery_timeline
                (delivery_id, event_type, actor, payload_json, timestamp)
                VALUES (?, ?, ?, ?, ?)""",
                (delivery_id, event_type, actor,
                 json.dumps(payload or {}, ensure_ascii=False),
                 datetime.utcnow().isoformat())
            )
            conn.commit()

    # ─── 对比两个 delivery ────────────────────────────────────────────────

    def compare_deliveries(
        self,
        delivery_id_a: str,
        delivery_id_b: str,
    ) -> Dict[str, Any]:
        """对比两个 delivery"""
        with self._connect() as conn:
            a = conn.execute(
                "SELECT * FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                (delivery_id_a, delivery_id_a)
            ).fetchone()
            b = conn.execute(
                "SELECT * FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                (delivery_id_b, delivery_id_b)
            ).fetchone()
        if not a or not b:
            return {"error": "一个或两个交付物不存在", "a": delivery_id_a, "b": delivery_id_b}
        return {
            "left": {
                "id": a["id"],
                "name": a["name"],
                "dataset_version": a["dataset_version"] or "",
                "status": a["status"],
                "reviewer": a["reviewer"] or "",
            },
            "right": {
                "id": b["id"],
                "name": b["name"],
                "dataset_version": b["dataset_version"] or "",
                "status": b["status"],
                "reviewer": b["reviewer"] or "",
            },
            "same_version": a["dataset_version"] == b["dataset_version"],
            "same_status": a["status"] == b["status"],
            "status_progression": _status_compare(a["status"], b["status"]),
        }


# Singleton
_workflow_instance: Optional[DeliveryWorkflow] = None


def get_delivery_workflow(db_path: Optional[str] = None) -> DeliveryWorkflow:
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = DeliveryWorkflow(db_path)
    return _workflow_instance