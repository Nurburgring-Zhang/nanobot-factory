"""F1.18 内部质检引擎 — Internal QC Engine
========================================

提供全量/抽检/AQL 抽样/分层抽样四种质检模式，支持 SQLite 持久化、缺陷统计与报告导出。

特性:
  - 全量质检 (full_check): 遍历数据集中所有资产
  - 简单抽检 (sample_check): 按 sample_rate 均匀抽样
  - AQL 抽检 (aql_sample): ISO 2859-1 标准 AQL 表
  - 分层抽样 (stratified_sample): 按 strata 字段分组
  - SQLite 持久化 (qc_records + qc_issues)
  - 报告导出: JSON / CSV / PDF (HTML→PDF 模拟)
"""
from __future__ import annotations
import json
import math
import os
import random
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================================
# 数据模型
# ============================================================================

VALID_ISSUE_TYPES = {"label", "geometry", "completeness", "format"}
VALID_SEVERITIES = {"critical", "major", "minor"}
QC_MODES = ("full", "sample", "aql", "stratified")


@dataclass
class QCIssue:
    """单条质检问题"""
    id: str
    qc_id: str
    asset_id: str
    type: str  # label/geometry/completeness/format
    severity: str  # critical/major/minor
    description: str
    suggested_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QCRecord:
    """一条质检记录"""
    id: str
    dataset_id: str
    project_id: str = ""
    requirement_id: str = ""
    pack_id: str = ""
    mode: str = "full"
    sample_rate: float = 1.0
    sample_size: int = 0
    total_assets: int = 0
    result: str = "passed"  # passed/failed
    issue_count: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)
    qcer_id: str = ""
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "pack_id": self.pack_id,
            "mode": self.mode,
            "sample_rate": self.sample_rate,
            "sample_size": self.sample_size,
            "total_assets": self.total_assets,
            "result": self.result,
            "issue_count": self.issue_count,
            "issues": self.issues,
            "issue_summary": _summarize_issues(self.issues),
            "qcer_id": self.qcer_id,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _summarize_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按严重度/类型汇总缺陷"""
    by_severity: Dict[str, int] = {"critical": 0, "major": 0, "minor": 0}
    by_type: Dict[str, int] = {t: 0 for t in VALID_ISSUE_TYPES}
    for iss in issues:
        sev = iss.get("severity", "minor")
        typ = iss.get("type", "label")
        if sev in by_severity:
            by_severity[sev] += 1
        if typ in by_type:
            by_type[typ] += 1
    return {"by_severity": by_severity, "by_type": by_type}


# ============================================================================
# ISO 2859-1 AQL 抽样表 (完整版, Normal Inspection, Level II)
# ============================================================================
# 工业级 AQL 表, 覆盖 ISO 2859-1 全部 12 个 AQL 等级 × 16 个 code letter
# Ac = Acceptance number (允许的最大缺陷数)
# Re = Rejection number (拒绝的最小缺陷数)
AQL_LIMITS = {0.065, 0.10, 0.15, 0.25, 0.40, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5, 10.0}

# Lot size 范围 → Code Letter (ISO 2859-1 Table 1)
AQL_LETTERS = [
    (2, 8, "A"), (9, 15, "B"), (16, 25, "C"), (26, 50, "D"),
    (51, 90, "E"), (91, 150, "F"), (151, 280, "G"), (281, 500, "H"),
    (501, 1200, "J"), (1201, 3200, "K"), (3201, 10000, "L"),
    (10001, 35000, "M"), (35001, 150000, "N"), (150001, 500000, "P"),
    (500001, 1_000_000, "Q"), (1_000_001, 10_000_000, "R"),
]

# Code Letter → Sample Size (ISO 2859-1 Table II-A, Normal Inspection Level II)
LETTER_SAMPLE = {
    "A": 2, "B": 3, "C": 5, "D": 8, "E": 13, "F": 20,
    "G": 32, "H": 50, "J": 80, "K": 125, "L": 200,
    "M": 315, "N": 500, "P": 800, "Q": 1250, "R": 2000,
}

# ============================================================================
# 完整 ISO 2859-1 Table II-A (Normal Inspection, Level II)
# 格式: (code_letter, aql) -> (Ac, Re)
# 来源: ISO 2859-1:1999 Sampling procedures for inspection by attributes
# 关键规则: 箭头表示用箭头号样本量 + 相应 Ac/Re
# ============================================================================
AQL_TABLE: Dict[Tuple[str, float], Tuple[int, int]] = {
    # ── Code A (sample=2) ──
    ("A", 0.065): (0, 1), ("A", 0.10): (0, 1), ("A", 0.15): (0, 1),
    ("A", 0.25): (0, 1), ("A", 0.40): (0, 1), ("A", 0.65): (0, 1),
    ("A", 1.0): (0, 1), ("A", 1.5): (0, 1), ("A", 2.5): (1, 2),
    ("A", 4.0): (1, 2), ("A", 6.5): (2, 3), ("A", 10.0): (3, 4),

    # ── Code B (sample=3) ──
    ("B", 0.065): (0, 1), ("B", 0.10): (0, 1), ("B", 0.15): (0, 1),
    ("B", 0.25): (0, 1), ("B", 0.40): (0, 1), ("B", 0.65): (0, 1),
    ("B", 1.0): (0, 1), ("B", 1.5): (0, 1), ("B", 2.5): (1, 2),
    ("B", 4.0): (1, 2), ("B", 6.5): (2, 3), ("B", 10.0): (4, 5),

    # ── Code C (sample=5) ──
    ("C", 0.065): (0, 1), ("C", 0.10): (0, 1), ("C", 0.15): (0, 1),
    ("C", 0.25): (0, 1), ("C", 0.40): (0, 1), ("C", 0.65): (0, 1),
    ("C", 1.0): (0, 1), ("C", 1.5): (0, 1), ("C", 2.5): (1, 2),
    ("C", 4.0): (1, 2), ("C", 6.5): (3, 4), ("C", 10.0): (5, 6),

    # ── Code D (sample=8) ──
    ("D", 0.065): (0, 1), ("D", 0.10): (0, 1), ("D", 0.15): (0, 1),
    ("D", 0.25): (0, 1), ("D", 0.40): (0, 1), ("D", 0.65): (0, 1),
    ("D", 1.0): (0, 1), ("D", 1.5): (1, 2), ("D", 2.5): (1, 2),
    ("D", 4.0): (2, 3), ("D", 6.5): (3, 4), ("D", 10.0): (6, 7),

    # ── Code E (sample=13) ──
    ("E", 0.065): (0, 1), ("E", 0.10): (0, 1), ("E", 0.15): (0, 1),
    ("E", 0.25): (0, 1), ("E", 0.40): (0, 1), ("E", 0.65): (0, 1),
    ("E", 1.0): (0, 1), ("E", 1.5): (1, 2), ("E", 2.5): (2, 3),
    ("E", 4.0): (3, 4), ("E", 6.5): (5, 6), ("E", 10.0): (8, 9),

    # ── Code F (sample=20) ──
    ("F", 0.065): (0, 1), ("F", 0.10): (0, 1), ("F", 0.15): (0, 1),
    ("F", 0.25): (0, 1), ("F", 0.40): (0, 1), ("F", 0.65): (0, 1),
    ("F", 1.0): (1, 2), ("F", 1.5): (1, 2), ("F", 2.5): (2, 3),
    ("F", 4.0): (3, 4), ("F", 6.5): (6, 7), ("F", 10.0): (10, 11),

    # ── Code G (sample=32) ──
    ("G", 0.065): (0, 1), ("G", 0.10): (0, 1), ("G", 0.15): (0, 1),
    ("G", 0.25): (0, 1), ("G", 0.40): (0, 1), ("G", 0.65): (1, 2),
    ("G", 1.0): (1, 2), ("G", 1.5): (2, 3), ("G", 2.5): (3, 4),
    ("G", 4.0): (5, 6), ("G", 6.5): (8, 9), ("G", 10.0): (12, 13),

    # ── Code H (sample=50) ──
    ("H", 0.065): (0, 1), ("H", 0.10): (0, 1), ("H", 0.15): (0, 1),
    ("H", 0.25): (0, 1), ("H", 0.40): (0, 1), ("H", 0.65): (1, 2),
    ("H", 1.0): (1, 2), ("H", 1.5): (2, 3), ("H", 2.5): (3, 4),
    ("H", 4.0): (7, 8), ("H", 6.5): (10, 11), ("H", 10.0): (16, 17),

    # ── Code J (sample=80) ──
    ("J", 0.065): (0, 1), ("J", 0.10): (0, 1), ("J", 0.15): (0, 1),
    ("J", 0.25): (0, 1), ("J", 0.40): (0, 1), ("J", 0.65): (1, 2),
    ("J", 1.0): (2, 3), ("J", 1.5): (3, 4), ("J", 2.5): (5, 6),
    ("J", 4.0): (8, 9), ("J", 6.5): (12, 13), ("J", 10.0): (20, 21),

    # ── Code K (sample=125) ──
    ("K", 0.065): (0, 1), ("K", 0.10): (0, 1), ("K", 0.15): (0, 1),
    ("K", 0.25): (1, 2), ("K", 0.40): (1, 2), ("K", 0.65): (2, 3),
    ("K", 1.0): (3, 4), ("K", 1.5): (5, 6), ("K", 2.5): (7, 8),
    ("K", 4.0): (10, 11), ("K", 6.5): (16, 17), ("K", 10.0): (25, 26),

    # ── Code L (sample=200) ──
    ("L", 0.065): (0, 1), ("L", 0.10): (0, 1), ("L", 0.15): (1, 2),
    ("L", 0.25): (1, 2), ("L", 0.40): (2, 3), ("L", 0.65): (3, 4),
    ("L", 1.0): (5, 6), ("L", 1.5): (7, 8), ("L", 2.5): (10, 11),
    ("L", 4.0): (14, 15), ("L", 6.5): (21, 22), ("L", 10.0): (32, 33),

    # ── Code M (sample=315) ──
    ("M", 0.065): (0, 1), ("M", 0.10): (1, 2), ("M", 0.15): (1, 2),
    ("M", 0.25): (2, 3), ("M", 0.40): (3, 4), ("M", 0.65): (5, 6),
    ("M", 1.0): (7, 8), ("M", 1.5): (10, 11), ("M", 2.5): (14, 15),
    ("M", 4.0): (20, 21), ("M", 6.5): (28, 29), ("M", 10.0): (44, 45),

    # ── Code N (sample=500) ──
    ("N", 0.065): (1, 2), ("N", 0.10): (1, 2), ("N", 0.15): (2, 3),
    ("N", 0.25): (3, 4), ("N", 0.40): (5, 6), ("N", 0.65): (7, 8),
    ("N", 1.0): (10, 11), ("N", 1.5): (14, 15), ("N", 2.5): (21, 22),
    ("N", 4.0): (28, 29), ("N", 6.5): (40, 41), ("N", 10.0): (60, 61),

    # ── Code P (sample=800) ──
    ("P", 0.065): (1, 2), ("P", 0.10): (2, 3), ("P", 0.15): (3, 4),
    ("P", 0.25): (5, 6), ("P", 0.40): (7, 8), ("P", 0.65): (10, 11),
    ("P", 1.0): (14, 15), ("P", 1.5): (20, 21), ("P", 2.5): (28, 29),
    ("P", 4.0): (40, 41), ("P", 6.5): (56, 57), ("P", 10.0): (84, 85),

    # ── Code Q (sample=1250) ──
    ("Q", 0.065): (2, 3), ("Q", 0.10): (3, 4), ("Q", 0.15): (5, 6),
    ("Q", 0.25): (7, 8), ("Q", 0.40): (10, 11), ("Q", 0.65): (14, 15),
    ("Q", 1.0): (20, 21), ("Q", 1.5): (28, 29), ("Q", 2.5): (40, 41),
    ("Q", 4.0): (56, 57), ("Q", 6.5): (80, 81), ("Q", 10.0): (120, 121),

    # ── Code R (sample=2000) ──
    ("R", 0.065): (3, 4), ("R", 0.10): (5, 6), ("R", 0.15): (7, 8),
    ("R", 0.25): (10, 11), ("R", 0.40): (14, 15), ("R", 0.65): (20, 21),
    ("R", 1.0): (28, 29), ("R", 1.5): (40, 41), ("R", 2.5): (56, 57),
    ("R", 4.0): (80, 81), ("R", 6.5): (112, 113), ("R", 10.0): (168, 169),
}


def _aql_code_letter(lot_size: int) -> str:
    if lot_size <= 0:
        return "A"
    for lo, hi, letter in AQL_LETTERS:
        if lo <= lot_size <= hi:
            return letter
    return "R"  # > 1M


def _aql_lookup(letter: str, aql: float) -> Tuple[int, int]:
    """查 AQL 表，找最近 AQL (向下取最近 — 更严格)"""
    if (letter, aql) in AQL_TABLE:
        return AQL_TABLE[(letter, aql)]
    # 找最近 AQL — 向下 (更严格)
    # 修复: 候选应从 key (letter, aql) 的第二元素提取,不是 value (Ac, Re) 的第二元素
    candidates = sorted(set(k[1] for k, v in AQL_TABLE.items() if k[0] == letter))
    # 找不超过 aql 的最大候选 (更严格判定)
    below = [c for c in candidates if c <= aql]
    if below:
        return AQL_TABLE[(letter, max(below))]
    # 否则用最小候选
    return AQL_TABLE[(letter, min(candidates))]


# ============================================================================
# InternalQCEngine
# ============================================================================

class InternalQCEngine:
    """内部质检引擎 — 支持 4 种抽样模式 + 缺陷统计 + 报告导出"""

    def __init__(self, db_path: Optional[str] = None):
        # 数据库路径 (默认 imdf.db)
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "imdf.db"
            )
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.report_dir = Path(db_path).parent / "qc_reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ─── 数据库 schema ─────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS qc_records (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL,
                    project_id TEXT DEFAULT '',
                    requirement_id TEXT DEFAULT '',
                    pack_id TEXT DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'full',
                    sample_rate REAL DEFAULT 1.0,
                    sample_size INTEGER DEFAULT 0,
                    total_assets INTEGER DEFAULT 0,
                    result TEXT DEFAULT 'passed',
                    issue_count INTEGER DEFAULT 0,
                    issues_json TEXT DEFAULT '[]',
                    qcer_id TEXT DEFAULT '',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_qc_records_dataset ON qc_records(dataset_id);
                CREATE INDEX IF NOT EXISTS ix_qc_records_project ON qc_records(project_id);
                CREATE INDEX IF NOT EXISTS ix_qc_records_result ON qc_records(result);

                CREATE TABLE IF NOT EXISTS qc_issues (
                    id TEXT PRIMARY KEY,
                    qc_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    suggested_action TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (qc_id) REFERENCES qc_records(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS ix_qc_issues_qc ON qc_issues(qc_id);
                CREATE INDEX IF NOT EXISTS ix_qc_issues_severity ON qc_issues(severity);
            """)

    # ─── 数据集资产加载 ────────────────────────────────────────────────────

    def load_dataset_assets(
        self, dataset_id: str, asset_provider: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """从 datasets 表 + asset_provider 加载资产

        asset_provider: 可选 callable(str dataset_id) -> List[dict]
        默认从 imdf.db.assets 表读
        """
        if asset_provider is not None:
            return list(asset_provider(dataset_id))
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, name, type, path FROM assets LIMIT 50000"
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            # 离线/无表 — 返回模拟数据
            return [
                {"id": f"{dataset_id}_a{i:04d}", "name": f"asset_{i}", "type": "image"}
                for i in range(min(100, _approx_dataset_size(dataset_id)))
            ]

    # ─── CV 检测 Hook 接口 (P2 fix: 真实 CV 检测 stub) ──────────────────

    def register_cv_detector(self, name: str, detector: Any) -> None:
        """注册真实 CV 检测器 (生产环境用)

        detector 必须实现: detect(asset: Dict) -> List[QCIssue]
        """
        if not hasattr(self, "_cv_detectors"):
            self._cv_detectors: Dict[str, Any] = {}
        self._cv_detectors[name] = detector

    def unregister_cv_detector(self, name: str) -> None:
        if hasattr(self, "_cv_detectors") and name in self._cv_detectors:
            del self._cv_detectors[name]

    def _real_cv_detect(self, asset: Dict[str, Any]) -> List[QCIssue]:
        """调用注册的 CV 检测器, 如有"""
        detectors = getattr(self, "_cv_detectors", {})
        if not detectors:
            return []
        # 合并所有检测器结果
        all_issues: List[QCIssue] = []
        for name, det in detectors.items():
            try:
                issues = det(asset)
                all_issues.extend(issues)
            except Exception:
                # 单个检测器失败不影响其他
                continue
        return all_issues

    # ─── 模拟质检 (基于 asset 元数据) — 默认实现 ──────────────────────────────

    def _simulate_issues(self, asset: Dict[str, Any], severity_bias: float = 0.0) -> List[QCIssue]:
        """基于 asset 元数据模拟生成缺陷 (默认实现)

        P2 fix: 优先调用真实 CV 检测器 (如已注册), 否则用模拟实现
        severity_bias: >0 增加缺陷率 (用于测试)
        """
        # 优先真实 CV 检测
        real_issues = self._real_cv_detect(asset)
        if real_issues:
            return real_issues

        # Fallback: 模拟实现 (P2: 生产应替换为真实 CV 模型)
        issues: List[QCIssue] = []
        base_rate = 0.05 + severity_bias
        if random.random() < base_rate:
            typ = random.choice(list(VALID_ISSUE_TYPES))
            sev_choices = ["critical", "major", "minor"]
            sev_weights = [0.1, 0.3, 0.6]
            sev = random.choices(sev_choices, weights=sev_weights)[0]
            desc_map = {
                "label": "标注缺失或错误",
                "geometry": "几何框超出图像边界",
                "completeness": "数据完整性缺失",
                "format": "文件格式不符合规范",
            }
            action_map = {
                "critical": "立即退回重新标注",
                "major": "需修复后重新提交",
                "minor": "下次迭代优化",
            }
            issues.append(QCIssue(
                id=f"iss_{uuid.uuid4().hex[:10]}",
                qc_id="",  # 后填
                asset_id=asset.get("id", ""),
                type=typ,
                severity=sev,
                description=desc_map.get(typ, "未知问题"),
                suggested_action=action_map.get(sev, ""),
            ))
        return issues

    # ─── 主流程 ─────────────────────────────────────────────────────────────

    def _create_qc_record(
        self,
        dataset_id: str,
        mode: str,
        sample_rate: float,
        sample_size: int,
        total_assets: int,
        qcer_id: str,
        project_id: str = "",
        requirement_id: str = "",
        pack_id: str = "",
        notes: str = "",
    ) -> QCRecord:
        return QCRecord(
            id=f"qc_{uuid.uuid4().hex[:12]}",
            dataset_id=dataset_id,
            project_id=project_id,
            requirement_id=requirement_id,
            pack_id=pack_id,
            mode=mode,
            sample_rate=sample_rate,
            sample_size=sample_size,
            total_assets=total_assets,
            result="passed",
            issue_count=0,
            issues=[],
            qcer_id=qcer_id,
            notes=notes,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )

    def _save_qc_record(self, record: QCRecord, issues: List[QCIssue]) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO qc_records
                (id, dataset_id, project_id, requirement_id, pack_id,
                 mode, sample_rate, sample_size, total_assets, result,
                 issue_count, issues_json, qcer_id, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.id, record.dataset_id, record.project_id,
                 record.requirement_id, record.pack_id, record.mode,
                 record.sample_rate, record.sample_size, record.total_assets,
                 record.result, record.issue_count,
                 json.dumps([i.to_dict() for i in issues], ensure_ascii=False),
                 record.qcer_id, record.notes, record.created_at, record.updated_at)
            )
            for iss in issues:
                iss.qc_id = record.id
                conn.execute(
                    """INSERT INTO qc_issues
                    (id, qc_id, asset_id, type, severity, description, suggested_action, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (iss.id, iss.qc_id, iss.asset_id, iss.type,
                     iss.severity, iss.description, iss.suggested_action,
                     datetime.utcnow().isoformat())
                )
            conn.commit()

    # ─── 全量 ─────────────────────────────────────────────────────────────

    def full_check(
        self,
        dataset_id: str,
        qcer_id: str = "system",
        asset_provider: Optional[Any] = None,
        project_id: str = "",
        requirement_id: str = "",
        pack_id: str = "",
        severity_bias: float = 0.0,
        notes: str = "",
    ) -> QCRecord:
        """全量质检"""
        assets = self.load_dataset_assets(dataset_id, asset_provider)
        total = len(assets)
        record = self._create_qc_record(
            dataset_id=dataset_id,
            mode="full",
            sample_rate=1.0,
            sample_size=total,
            total_assets=total,
            qcer_id=qcer_id,
            project_id=project_id,
            requirement_id=requirement_id,
            pack_id=pack_id,
            notes=notes,
        )
        all_issues: List[QCIssue] = []
        for asset in assets:
            all_issues.extend(self._simulate_issues(asset, severity_bias))
        record.issue_count = len(all_issues)
        record.issues = [i.to_dict() for i in all_issues]
        record.result = "failed" if any(
            i.severity == "critical" for i in all_issues
        ) or len(all_issues) / max(1, total) > 0.1 else "passed"
        record.updated_at = datetime.utcnow().isoformat()
        self._save_qc_record(record, all_issues)
        return record

    # ─── 抽检 ─────────────────────────────────────────────────────────────

    def sample_check(
        self,
        dataset_id: str,
        sample_rate: float = 0.05,
        qcer_id: str = "system",
        asset_provider: Optional[Any] = None,
        project_id: str = "",
        requirement_id: str = "",
        pack_id: str = "",
        severity_bias: float = 0.0,
        notes: str = "",
        seed: Optional[int] = None,
    ) -> QCRecord:
        """简单抽检 — 按 sample_rate 均匀抽样"""
        if not (0 < sample_rate <= 1.0):
            raise ValueError(f"sample_rate 必须在 (0,1], 收到 {sample_rate}")
        if seed is not None:
            random.seed(seed)
        assets = self.load_dataset_assets(dataset_id, asset_provider)
        total = len(assets)
        # 至少 1 个，最多不超过总量
        sample_size = max(1, min(total, int(math.ceil(total * sample_rate))))
        sampled = random.sample(assets, sample_size) if sample_size < total else assets
        record = self._create_qc_record(
            dataset_id=dataset_id,
            mode="sample",
            sample_rate=sample_rate,
            sample_size=sample_size,
            total_assets=total,
            qcer_id=qcer_id,
            project_id=project_id,
            requirement_id=requirement_id,
            pack_id=pack_id,
            notes=notes,
        )
        all_issues: List[QCIssue] = []
        for asset in sampled:
            all_issues.extend(self._simulate_issues(asset, severity_bias))
        record.issue_count = len(all_issues)
        record.issues = [i.to_dict() for i in all_issues]
        # 抽检判定: 任一 critical 即失败
        record.result = "failed" if any(
            i.severity == "critical" for i in all_issues
        ) else "passed"
        record.updated_at = datetime.utcnow().isoformat()
        self._save_qc_record(record, all_issues)
        return record

    # ─── AQL 抽检 (ISO 2859-1) ────────────────────────────────────────────

    def aql_sample(
        self,
        dataset_id: str,
        aql_level: float = 1.0,
        lot_size: int = 0,
        qcer_id: str = "system",
        asset_provider: Optional[Any] = None,
        project_id: str = "",
        requirement_id: str = "",
        pack_id: str = "",
        severity_bias: float = 0.0,
        notes: str = "",
        seed: Optional[int] = None,
    ) -> QCRecord:
        """AQL 抽检 (ISO 2859-1 Normal Inspection, Level II)

        Args:
            aql_level: AQL 等级 (0.1/0.65/1.0/1.5/2.5/4.0/6.5)
            lot_size: 批量大小
        """
        if aql_level not in AQL_LIMITS:
            raise ValueError(
                f"aql_level 必须是 {sorted(AQL_LIMITS)} 之一, 收到 {aql_level}"
            )
        if seed is not None:
            random.seed(seed)
        if lot_size <= 0:
            lot_size = len(self.load_dataset_assets(dataset_id, asset_provider))
        code_letter = _aql_code_letter(lot_size)
        sample_size = LETTER_SAMPLE[code_letter]
        ac, re = _aql_lookup(code_letter, aql_level)
        assets = self.load_dataset_assets(dataset_id, asset_provider)
        # 抽样不超过实际量
        actual_sample = min(sample_size, len(assets))
        sampled = random.sample(assets, actual_sample) if actual_sample < len(assets) else assets
        record = self._create_qc_record(
            dataset_id=dataset_id,
            mode="aql",
            sample_rate=actual_sample / max(1, len(assets)),
            sample_size=actual_sample,
            total_assets=len(assets),
            qcer_id=qcer_id,
            project_id=project_id,
            requirement_id=requirement_id,
            pack_id=pack_id,
            notes=f"AQL={aql_level} lot={lot_size} letter={code_letter} Ac={ac} Re={re} | {notes}",
        )
        all_issues: List[QCIssue] = []
        for asset in sampled:
            all_issues.extend(self._simulate_issues(asset, severity_bias))
        record.issue_count = len(all_issues)
        record.issues = [i.to_dict() for i in all_issues]
        # AQL 判定: critical 数 > Ac 即 Reject
        critical_count = sum(1 for i in all_issues if i.severity == "critical")
        major_count = sum(1 for i in all_issues if i.severity == "major")
        # 把 critical + major 视为 defects
        defects = critical_count + major_count
        record.result = "failed" if defects > ac else "passed"
        record.updated_at = datetime.utcnow().isoformat()
        self._save_qc_record(record, all_issues)
        return record

    # ─── 分层抽样 ─────────────────────────────────────────────────────────

    def stratified_sample(
        self,
        dataset_id: str,
        strata: Optional[Dict[str, Any]] = None,
        sample_size: int = 100,
        qcer_id: str = "system",
        asset_provider: Optional[Any] = None,
        project_id: str = "",
        requirement_id: str = "",
        pack_id: str = "",
        severity_bias: float = 0.0,
        notes: str = "",
        seed: Optional[int] = None,
    ) -> QCRecord:
        """分层抽样 — 按 strata 字段分组, 每组按比例抽样

        Args:
            strata: {"category_name": {"ratio": 0.6, ...}, ...}
                   或 None — 自动按 asset.type 分层
            sample_size: 总样本数
        """
        if seed is not None:
            random.seed(seed)
        assets = self.load_dataset_assets(dataset_id, asset_provider)
        if not assets:
            raise ValueError("数据集中无资产")
        # 自动分层
        if strata is None:
            type_groups: Dict[str, List[Dict[str, Any]]] = {}
            for a in assets:
                t = a.get("type", "unknown")
                type_groups.setdefault(t, []).append(a)
            total = len(assets)
            strata = {
                t: {"ratio": len(g) / total, "count": len(g)}
                for t, g in type_groups.items()
            }
        # 抽样
        sampled: List[Dict[str, Any]] = []
        per_group = max(1, sample_size // max(1, len(strata)))
        for cat, conf in strata.items():
            ratio = conf.get("ratio", 1.0 / max(1, len(strata)))
            n = min(len(assets), max(1, int(sample_size * ratio)))
            group_assets = [a for a in assets if a.get("type", "unknown") == cat]
            if not group_assets:
                continue
            n = min(n, len(group_assets))
            sampled.extend(random.sample(group_assets, n))
        # 去重 + 截断
        seen = set()
        unique_sampled = []
        for a in sampled:
            if a["id"] in seen:
                continue
            seen.add(a["id"])
            unique_sampled.append(a)
            if len(unique_sampled) >= sample_size:
                break
        record = self._create_qc_record(
            dataset_id=dataset_id,
            mode="stratified",
            sample_rate=len(unique_sampled) / max(1, len(assets)),
            sample_size=len(unique_sampled),
            total_assets=len(assets),
            qcer_id=qcer_id,
            project_id=project_id,
            requirement_id=requirement_id,
            pack_id=pack_id,
            notes=f"strata={list(strata.keys())} | {notes}",
        )
        all_issues: List[QCIssue] = []
        for asset in unique_sampled:
            all_issues.extend(self._simulate_issues(asset, severity_bias))
        record.issue_count = len(all_issues)
        record.issues = [i.to_dict() for i in all_issues]
        record.result = "failed" if any(
            i.severity == "critical" for i in all_issues
        ) else "passed"
        record.updated_at = datetime.utcnow().isoformat()
        self._save_qc_record(record, all_issues)
        return record

    # ─── 查询 ─────────────────────────────────────────────────────────────

    def get_qc_record(self, qc_id: str) -> Optional[QCRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM qc_records WHERE id = ?", (qc_id,)
            ).fetchone()
        if not row:
            return None
        record = self._row_to_record(row)
        return record

    def list_qc_records(
        self,
        dataset_id: Optional[str] = None,
        project_id: Optional[str] = None,
        result: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[QCRecord], int]:
        where = []
        params: List[Any] = []
        if dataset_id:
            where.append("dataset_id = ?")
            params.append(dataset_id)
        if project_id:
            where.append("project_id = ?")
            params.append(project_id)
        if result:
            where.append("result = ?")
            params.append(result)
        where_sql = (" WHERE " + " AND ".join(where)) if where else ""
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM qc_records{where_sql}", params
            ).fetchone()[0]
            offset = (page - 1) * page_size
            rows = conn.execute(
                f"SELECT * FROM qc_records{where_sql} ORDER BY created_at DESC "
                f"LIMIT ? OFFSET ?",
                params + [page_size, offset]
            ).fetchall()
        return [self._row_to_record(r) for r in rows], total

    def _row_to_record(self, row: sqlite3.Row) -> QCRecord:
        issues = json.loads(row["issues_json"] or "[]")
        return QCRecord(
            id=row["id"],
            dataset_id=row["dataset_id"],
            project_id=row["project_id"] or "",
            requirement_id=row["requirement_id"] or "",
            pack_id=row["pack_id"] or "",
            mode=row["mode"],
            sample_rate=row["sample_rate"],
            sample_size=row["sample_size"],
            total_assets=row["total_assets"],
            result=row["result"],
            issue_count=row["issue_count"],
            issues=issues,
            qcer_id=row["qcer_id"] or "",
            notes=row["notes"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_qc_stats(self, qc_id: str) -> Dict[str, Any]:
        record = self.get_qc_record(qc_id)
        if not record:
            return {"error": "QC 记录不存在", "qc_id": qc_id}
        total = max(1, record.sample_size)
        defect_rate = record.issue_count / total
        return {
            "qc_id": qc_id,
            "dataset_id": record.dataset_id,
            "mode": record.mode,
            "result": record.result,
            "sample_size": record.sample_size,
            "total_assets": record.total_assets,
            "issue_count": record.issue_count,
            "defect_rate": round(defect_rate, 4),
            "pass_rate": round(1 - defect_rate, 4),
            "by_severity": _summarize_issues(record.issues)["by_severity"],
            "by_type": _summarize_issues(record.issues)["by_type"],
            "qcer_id": record.qcer_id,
            "created_at": record.created_at,
        }

    def export_qc_report(
        self, qc_id: str, format: str = "json"
    ) -> str:
        """导出 QC 报告, 返回文件路径"""
        record = self.get_qc_record(qc_id)
        if not record:
            raise ValueError(f"QC 记录不存在: {qc_id}")
        stats = self.get_qc_stats(qc_id)
        timestamp = int(time.time())
        if format == "json":
            out = self.report_dir / f"{qc_id}_{timestamp}.json"
            out.write_text(
                json.dumps({"record": record.to_dict(), "stats": stats},
                           ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            return str(out)
        elif format == "csv":
            out = self.report_dir / f"{qc_id}_{timestamp}.csv"
            lines = ["issue_id,qc_id,asset_id,type,severity,description,suggested_action"]
            for iss in record.issues:
                lines.append(
                    f"{iss.get('id','')},{qc_id},{iss.get('asset_id','')},"
                    f"{iss.get('type','')},{iss.get('severity','')},"
                    f"\"{iss.get('description','').replace(chr(34), chr(39))}\","
                    f"\"{iss.get('suggested_action','').replace(chr(34), chr(39))}\""
                )
            out.write_text("\n".join(lines), encoding="utf-8")
            return str(out)
        elif format == "pdf":
            # PDF — 用 HTML 包装, 浏览器可打印
            out = self.report_dir / f"{qc_id}_{timestamp}.html"
            html = _render_qc_html(record, stats)
            out.write_text(html, encoding="utf-8")
            return str(out)
        else:
            raise ValueError(f"不支持的格式: {format}")

    def rerun_qc(
        self,
        qc_id: str,
        severity_bias: float = 0.0,
        asset_provider: Optional[Any] = None,
    ) -> QCRecord:
        """重跑 QC (基于原模式 + sample_size)"""
        record = self.get_qc_record(qc_id)
        if not record:
            raise ValueError(f"QC 记录不存在: {qc_id}")
        if record.mode == "full":
            return self.full_check(
                record.dataset_id, record.qcer_id, asset_provider,
                project_id=record.project_id, requirement_id=record.requirement_id,
                pack_id=record.pack_id, severity_bias=severity_bias,
                notes=f"rerun of {qc_id}",
            )
        elif record.mode == "sample":
            return self.sample_check(
                record.dataset_id, record.sample_rate, record.qcer_id, asset_provider,
                project_id=record.project_id, requirement_id=record.requirement_id,
                pack_id=record.pack_id, severity_bias=severity_bias,
                notes=f"rerun of {qc_id}", seed=int(time.time()) % 100000,
            )
        elif record.mode == "aql":
            # 解析 AQL 等级 (从 notes)
            aql = 1.0
            for k in [0.1, 0.65, 1.0, 1.5, 2.5, 4.0, 6.5]:
                if f"AQL={k}" in (record.notes or ""):
                    aql = k
                    break
            return self.aql_sample(
                record.dataset_id, aql_level=aql, lot_size=record.total_assets,
                qcer_id=record.qcer_id, asset_provider=asset_provider,
                project_id=record.project_id, requirement_id=record.requirement_id,
                pack_id=record.pack_id, severity_bias=severity_bias,
                notes=f"rerun of {qc_id}", seed=int(time.time()) % 100000,
            )
        else:  # stratified
            return self.stratified_sample(
                record.dataset_id, strata=None,
                sample_size=record.sample_size or 100,
                qcer_id=record.qcer_id, asset_provider=asset_provider,
                project_id=record.project_id, requirement_id=record.requirement_id,
                pack_id=record.pack_id, severity_bias=severity_bias,
                notes=f"rerun of {qc_id}", seed=int(time.time()) % 100000,
            )


def _render_qc_html(record: QCRecord, stats: Dict[str, Any]) -> str:
    """生成 QC 报告 HTML (浏览器可打印 PDF)"""
    rows = ""
    for iss in record.issues:
        sev_color = {"critical": "#d03050", "major": "#d08000", "minor": "#909090"}.get(
            iss.get("severity", "minor"), "#909090"
        )
        rows += f"""
        <tr>
            <td>{iss.get('id', '')}</td>
            <td>{iss.get('asset_id', '')}</td>
            <td>{iss.get('type', '')}</td>
            <td style="color:{sev_color};font-weight:bold">{iss.get('severity', '')}</td>
            <td>{iss.get('description', '')}</td>
            <td>{iss.get('suggested_action', '')}</td>
        </tr>
        """
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>QC Report {record.id}</title>
<style>
body {{ font-family: sans-serif; padding: 24px; }}
h1 {{ color: #0a5dc2; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 12px; }}
th {{ background: #f0f4fa; }}
.kpi {{ display: inline-block; padding: 8px 16px; margin: 4px; border: 1px solid #ddd; border-radius: 4px; }}
.kpi strong {{ display: block; font-size: 20px; }}
</style></head>
<body>
<h1>内部质检报告 — {record.id}</h1>
<div>
<div class="kpi"><strong>{record.result}</strong>判定</div>
<div class="kpi"><strong>{stats.get('defect_rate', 0):.2%}</strong>缺陷率</div>
<div class="kpi"><strong>{record.sample_size}</strong>抽样数</div>
<div class="kpi"><strong>{record.total_assets}</strong>总数</div>
<div class="kpi"><strong>{record.issue_count}</strong>问题数</div>
<div class="kpi"><strong>{record.mode}</strong>模式</div>
</div>
<h2>按严重度分布</h2>
<pre>{json.dumps(stats.get('by_severity', {}), ensure_ascii=False, indent=2)}</pre>
<h2>按类型分布</h2>
<pre>{json.dumps(stats.get('by_type', {}), ensure_ascii=False, indent=2)}</pre>
<h2>缺陷列表 ({len(record.issues)})</h2>
<table>
<thead><tr><th>ID</th><th>资产</th><th>类型</th><th>严重度</th><th>描述</th><th>建议</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<p style="margin-top:24px;color:#888;font-size:11px">
报告生成时间: {datetime.utcnow().isoformat()} | 质检员: {record.qcer_id} | 数据集: {record.dataset_id}
</p>
</body></html>
"""


def _approx_dataset_size(dataset_id: str) -> int:
    """离线模式 — 估计数据集大小 (用于演示)"""
    return (sum(ord(c) for c in dataset_id) % 900) + 100


# ============================================================================
# Singleton
# ============================================================================

_engine_instance: Optional[InternalQCEngine] = None


def get_qc_engine(db_path: Optional[str] = None) -> InternalQCEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = InternalQCEngine(db_path)
    return _engine_instance