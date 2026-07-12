"""F1.19 需求方验收引擎 — Requester Acceptance Engine
====================================================

需求方(下游客户)对已完成交付的验收流程: 抽样检查、接受/拒绝、退回生产。

特性:
  - 创建验收任务 (基于已批准的 delivery)
  - 抽样资产列表 (按 sample_rate 均匀抽样)
  - 提交验收决定 (accepted/rejected)
  - 退回生产 (request_revision)
  - 验收统计
  - SQLite 持久化 (acceptance_records)
"""
from __future__ import annotations
import json
import os
import random
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VALID_STATUSES = ("pending", "accepted", "rejected", "needs_revision")


@dataclass
class AcceptanceRecord:
    """需求方验收记录"""
    id: str
    delivery_id: str
    requester_id: str
    status: str = "pending"
    comments: str = ""
    sampled_assets: List[str] = field(default_factory=list)
    accepted_assets: List[str] = field(default_factory=list)
    rejected_assets: List[str] = field(default_factory=list)
    issues: List[Dict[str, Any]] = field(default_factory=list)
    sampled_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "delivery_id": self.delivery_id,
            "requester_id": self.requester_id,
            "status": self.status,
            "comments": self.comments,
            "sampled_assets": self.sampled_assets,
            "accepted_assets": self.accepted_assets,
            "rejected_assets": self.rejected_assets,
            "issues": self.issues,
            "sampled_count": self.sampled_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "acceptance_rate": (
                self.accepted_count / max(1, self.sampled_count)
                if self.sampled_count else 0.0
            ),
        }


# ============================================================================
# RequesterAcceptanceEngine
# ============================================================================

class RequesterAcceptanceEngine:
    """需求方验收引擎"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "imdf.db"
            )
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS acceptance_records (
                    id TEXT PRIMARY KEY,
                    delivery_id TEXT NOT NULL,
                    requester_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    comments TEXT DEFAULT '',
                    sampled_assets_json TEXT DEFAULT '[]',
                    accepted_assets_json TEXT DEFAULT '[]',
                    rejected_assets_json TEXT DEFAULT '[]',
                    issues_json TEXT DEFAULT '[]',
                    sampled_count INTEGER DEFAULT 0,
                    accepted_count INTEGER DEFAULT 0,
                    rejected_count INTEGER DEFAULT 0,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_acceptance_delivery ON acceptance_records(delivery_id);
                CREATE INDEX IF NOT EXISTS ix_acceptance_requester ON acceptance_records(requester_id);
                CREATE INDEX IF NOT EXISTS ix_acceptance_status ON acceptance_records(status);
            """)

    # ─── 加载交付物资产 ────────────────────────────────────────────────────

    def _load_delivery_assets(
        self, delivery_id: str, asset_provider: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """从交付物或数据集加载资产列表"""
        if asset_provider is not None:
            return list(asset_provider(delivery_id))
        try:
            with self._connect() as conn:
                # 优先查 deliveries.extra 字段
                row = conn.execute(
                    "SELECT * FROM deliveries WHERE id = ? OR name = ? LIMIT 1",
                    (delivery_id, delivery_id)
                ).fetchone()
                if not row:
                    return []
                # 用 delivery_id 模拟一批资产
                total = 100
                if row["dataset_version"]:
                    # 用 dataset_version 后缀模拟
                    try:
                        total = int(float(row["dataset_version"].strip("v")) * 200) or 100
                    except Exception:
                        total = 100
                total = max(20, min(2000, total))
                return [
                    {"id": f"{delivery_id}_a{i:04d}", "name": f"asset_{i}"}
                    for i in range(total)
                ]
        except Exception:
            return [
                {"id": f"{delivery_id}_a{i:04d}", "name": f"asset_{i}"}
                for i in range(50)
            ]

    # ─── 创建验收任务 ──────────────────────────────────────────────────────

    def create_acceptance(
        self,
        delivery_id: str,
        requester_id: str,
        sample_rate: float = 0.05,
        asset_provider: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        seed: Optional[int] = None,
    ) -> AcceptanceRecord:
        """创建验收任务 — 自动抽样"""
        if sample_rate <= 0 or sample_rate > 1.0:
            raise ValueError(f"sample_rate 必须在 (0,1], 收到 {sample_rate}")
        if seed is not None:
            random.seed(seed)
        assets = self._load_delivery_assets(delivery_id, asset_provider)
        n = max(1, int(round(len(assets) * sample_rate)))
        sampled = random.sample(assets, min(n, len(assets)))
        sampled_ids = [a["id"] for a in sampled]
        now = datetime.utcnow().isoformat()
        record = AcceptanceRecord(
            id=f"acc_{uuid.uuid4().hex[:12]}",
            delivery_id=delivery_id,
            requester_id=requester_id,
            status="pending",
            comments="",
            sampled_assets=sampled_ids,
            accepted_assets=[],
            rejected_assets=[],
            issues=[],
            sampled_count=len(sampled_ids),
            accepted_count=0,
            rejected_count=0,
            metadata=metadata or {"sample_rate": sample_rate},
            created_at=now,
            updated_at=now,
        )
        self._save_record(record)
        return record

    # ─── 抽样 (独立) ──────────────────────────────────────────────────────

    def sample_for_acceptance(
        self,
        delivery_id: str,
        sample_rate: float = 0.05,
        asset_provider: Optional[Any] = None,
        seed: Optional[int] = None,
    ) -> List[str]:
        """独立获取抽样列表 (不创建记录)"""
        if sample_rate <= 0 or sample_rate > 1.0:
            raise ValueError(f"sample_rate 必须在 (0,1], 收到 {sample_rate}")
        if seed is not None:
            random.seed(seed)
        assets = self._load_delivery_assets(delivery_id, asset_provider)
        n = max(1, int(round(len(assets) * sample_rate)))
        sampled = random.sample(assets, min(n, len(assets)))
        return [a["id"] for a in sampled]

    # ─── 提交验收决定 ──────────────────────────────────────────────────────

    def submit_acceptance(
        self,
        acceptance_id: str,
        status: str,
        comments: str = "",
        accepted_assets: Optional[List[str]] = None,
        rejected_assets: Optional[List[str]] = None,
        issues: Optional[List[Dict[str, Any]]] = None,
    ) -> AcceptanceRecord:
        """提交验收决定

        Args:
            status: accepted / rejected / needs_revision
            accepted_assets: 通过的资产 ID 列表
            rejected_assets: 拒绝的资产 ID 列表
            issues: 问题列表 [{"asset_id": "...", "description": "..."}]
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"status 必须是 {VALID_STATUSES}, 收到 {status}")
        record = self.get_acceptance(acceptance_id)
        if not record:
            raise ValueError(f"验收记录不存在: {acceptance_id}")
        if record.status != "pending":
            raise ValueError(
                f"验收已提交 (status={record.status}), 不能重复提交"
            )
        # 默认通过 = 所有抽样资产; 默认拒绝 = 空
        if accepted_assets is None:
            accepted_assets = list(record.sampled_assets) if status == "accepted" else []
        if rejected_assets is None:
            rejected_assets = list(record.sampled_assets) if status == "rejected" else []
        if issues is None:
            issues = []

        record.status = status
        record.comments = comments
        record.accepted_assets = accepted_assets
        record.rejected_assets = rejected_assets
        record.issues = issues
        record.accepted_count = len(accepted_assets)
        record.rejected_count = len(rejected_assets)
        record.updated_at = datetime.utcnow().isoformat()
        self._update_record(record)
        return record

    # ─── 退回生产 ──────────────────────────────────────────────────────────

    def request_revision(
        self,
        acceptance_id: str,
        reason: str = "",
        issues: Optional[List[Dict[str, Any]]] = None,
    ) -> AcceptanceRecord:
        """退回生产 (needs_revision)"""
        return self.submit_acceptance(
            acceptance_id=acceptance_id,
            status="needs_revision",
            comments=reason,
            rejected_assets=self.get_acceptance(acceptance_id).sampled_assets if self.get_acceptance(acceptance_id) else [],
            issues=issues or [],
        )

    # ─── 查询 ─────────────────────────────────────────────────────────────

    def get_acceptance(self, acceptance_id: str) -> Optional[AcceptanceRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM acceptance_records WHERE id = ?", (acceptance_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def get_acceptance_by_delivery(
        self, delivery_id: str
    ) -> List[AcceptanceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM acceptance_records WHERE delivery_id = ? "
                "ORDER BY created_at DESC",
                (delivery_id,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_pending_for_requester(
        self, requester_id: str
    ) -> List[AcceptanceRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM acceptance_records WHERE requester_id = ? "
                "AND status = 'pending' ORDER BY created_at DESC",
                (requester_id,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_for_requester(
        self, requester_id: str, status: Optional[str] = None
    ) -> List[AcceptanceRecord]:
        sql = "SELECT * FROM acceptance_records WHERE requester_id = ?"
        params: List[Any] = [requester_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_acceptance_stats(self, acceptance_id: str) -> Dict[str, Any]:
        record = self.get_acceptance(acceptance_id)
        if not record:
            return {"error": "验收记录不存在", "acceptance_id": acceptance_id}
        sampled = max(1, record.sampled_count)
        return {
            "acceptance_id": acceptance_id,
            "delivery_id": record.delivery_id,
            "requester_id": record.requester_id,
            "status": record.status,
            "sampled_count": record.sampled_count,
            "accepted_count": record.accepted_count,
            "rejected_count": record.rejected_count,
            "acceptance_rate": round(record.accepted_count / sampled, 4),
            "rejection_rate": round(record.rejected_count / sampled, 4),
            "issue_count": len(record.issues),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    # ─── 持久化 ───────────────────────────────────────────────────────────

    def _save_record(self, record: AcceptanceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO acceptance_records
                (id, delivery_id, requester_id, status, comments,
                 sampled_assets_json, accepted_assets_json, rejected_assets_json,
                 issues_json, sampled_count, accepted_count, rejected_count,
                 metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.id, record.delivery_id, record.requester_id,
                 record.status, record.comments,
                 json.dumps(record.sampled_assets, ensure_ascii=False),
                 json.dumps(record.accepted_assets, ensure_ascii=False),
                 json.dumps(record.rejected_assets, ensure_ascii=False),
                 json.dumps(record.issues, ensure_ascii=False),
                 record.sampled_count, record.accepted_count, record.rejected_count,
                 json.dumps(record.metadata, ensure_ascii=False),
                 record.created_at, record.updated_at)
            )
            conn.commit()

    def _update_record(self, record: AcceptanceRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """UPDATE acceptance_records SET
                    status=?, comments=?,
                    sampled_assets_json=?, accepted_assets_json=?, rejected_assets_json=?,
                    issues_json=?, sampled_count=?, accepted_count=?, rejected_count=?,
                    metadata_json=?, updated_at=?
                WHERE id=?""",
                (record.status, record.comments,
                 json.dumps(record.sampled_assets, ensure_ascii=False),
                 json.dumps(record.accepted_assets, ensure_ascii=False),
                 json.dumps(record.rejected_assets, ensure_ascii=False),
                 json.dumps(record.issues, ensure_ascii=False),
                 record.sampled_count, record.accepted_count, record.rejected_count,
                 json.dumps(record.metadata, ensure_ascii=False),
                 record.updated_at, record.id)
            )
            conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> AcceptanceRecord:
        return AcceptanceRecord(
            id=row["id"],
            delivery_id=row["delivery_id"],
            requester_id=row["requester_id"],
            status=row["status"],
            comments=row["comments"] or "",
            sampled_assets=json.loads(row["sampled_assets_json"] or "[]"),
            accepted_assets=json.loads(row["accepted_assets_json"] or "[]"),
            rejected_assets=json.loads(row["rejected_assets_json"] or "[]"),
            issues=json.loads(row["issues_json"] or "[]"),
            sampled_count=row["sampled_count"],
            accepted_count=row["accepted_count"],
            rejected_count=row["rejected_count"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ============================================================================
# Singleton
# ============================================================================

_engine_instance: Optional[RequesterAcceptanceEngine] = None


def get_requester_engine(db_path: Optional[str] = None) -> RequesterAcceptanceEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RequesterAcceptanceEngine(db_path)
    return _engine_instance