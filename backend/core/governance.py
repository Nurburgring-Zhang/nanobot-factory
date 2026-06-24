"""数据治理层 — 血缘追踪/审计日志/备份恢复"""

import uuid, json, os, shutil, hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, field
from core.persistent_base import PersistentManager

class LineageRelation(str, Enum):
    SOURCE = "source"
    PROCESSED_BY = "processed_by"
    LABELED_BY = "labeled_by"
    INCLUDED_IN = "included_in"
    EXPORTED_TO = "exported_to"
    TRAINED_FROM = "trained_from"
    EVALUATED_ON = "evaluated_on"

@dataclass
class LineageRecord:
    id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    relation: LineageRelation
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

@dataclass
class AuditLog:
    id: str = ""
    timestamp: str = ""
    user_id: str = ""
    username: str = ""
    action: str = ""
    target_type: str = ""
    target_id: str = ""
    old_value: str = ""
    new_value: str = ""
    ip_address: str = ""
    details: str = ""

@dataclass
class BackupRecord:
    id: str
    type: str  # full/incremental
    path: str
    size_mb: float
    checksum: str
    created_at: str
    tables: List[str] = field(default_factory=list)

class GovernanceManager(PersistentManager):
    _db_table = "audit_logs"
    _db_fields = ["id","timestamp","user_id","username","action","target_type","target_id","old_value","new_value","ip_address","details"]

    def __init__(self, backup_dir: str = "/tmp/governance_backups"):
        self._lineage: List[LineageRecord] = []
        self._audit_logs: List[AuditLog] = []
        self._backups: Dict[str, BackupRecord] = {}
        self._backup_dir = backup_dir
        # 倒排索引加速血缘查询
        self._source_index: Dict[str, List[int]] = {}
        self._target_index: Dict[str, List[int]] = {}
        super().__init__()
        self._load_from_db()
        os.makedirs(backup_dir, exist_ok=True)

    def _load_from_db(self):
        for row in self._load_all():
            log = AuditLog(**row)
            self._audit_logs.append(log)

    def _index_key(self, typ: str, eid: str) -> str: return f"{typ}:{eid}"

    def add_lineage(self, source_type: str, source_id: str, target_type: str, target_id: str, relation: LineageRelation, metadata: dict = None) -> LineageRecord:
        record = LineageRecord(
            id=f"ln-{uuid.uuid4().hex[:8]}",
            source_type=source_type, source_id=source_id,
            target_type=target_type, target_id=target_id,
            relation=relation, metadata=metadata or {},
            created_at=datetime.now().isoformat(),
        )
        idx = len(self._lineage)
        self._lineage.append(record)
        # 更新倒排索引
        sk = self._index_key(source_type, source_id)
        self._source_index.setdefault(sk, []).append(idx)
        tk = self._index_key(target_type, target_id)
        self._target_index.setdefault(tk, []).append(idx)
        return record

    def get_lineage(self, entity_type: str, entity_id: str) -> List[LineageRecord]:
        key = self._index_key(entity_type, entity_id)
        idxs = set(self._source_index.get(key, []) + self._target_index.get(key, []))
        return [self._lineage[i] for i in sorted(idxs)]
    
    def build_lineage_graph(self, entity_type: str, entity_id: str) -> Dict:
        """构建血缘有向图(可视化用)"""
        records = self.get_lineage(entity_type, entity_id)
        nodes = set()
        edges = []
        for r in records:
            nodes.add((r.source_type, r.source_id))
            nodes.add((r.target_type, r.target_id))
            edges.append({"from": r.source_id, "to": r.target_id, "relation": r.relation.value})
        return {
            "nodes": [{"type": t, "id": i} for t, i in nodes],
            "edges": edges,
        }
    
    def log_audit(self, user_id: str, username: str, action: str, target_type: str, target_id: str, old: str = "", new: str = "", details: str = "") -> AuditLog:
        log = AuditLog(
            id=f"aud-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now().isoformat(),
            user_id=user_id, username=username,
            action=action, target_type=target_type, target_id=target_id,
            old_value=old, new_value=new, details=details,
        )
        self._audit_logs.append(log)
        self._save(log.id, {"id":log.id,"timestamp":log.timestamp,"user_id":log.user_id,"username":log.username,"action":log.action,"target_type":log.target_type,"target_id":log.target_id,"old_value":log.old_value,"new_value":log.new_value,"ip_address":log.ip_address,"details":log.details})
        return log
    
    def query_audit(self, user_id: str = "", action: str = "", target_type: str = "", limit: int = 100) -> List[AuditLog]:
        results = list(self._audit_logs)
        if user_id: results = [l for l in results if l.user_id == user_id]
        if action: results = [l for l in results if l.action == action]
        if target_type: results = [l for l in results if l.target_type == target_type]
        return sorted(results, key=lambda l: l.timestamp, reverse=True)[:limit]
    
    def create_backup(self, backup_type: str = "full", data: dict = None) -> BackupRecord:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{backup_type}_{ts}.json"
        path = os.path.join(self._backup_dir, filename)
        
        backup_data = {
            "type": backup_type,
            "created_at": datetime.now().isoformat(),
            "data": data or {},
            "lineage_count": len(self._lineage),
            "audit_count": len(self._audit_logs),
        }
        content = json.dumps(backup_data, ensure_ascii=False, default=str)
        with open(path, "w") as f:
            f.write(content)
        
        record = BackupRecord(
            id=f"bk-{uuid.uuid4().hex[:8]}",
            type=backup_type, path=path,
            size_mb=round(len(content) / (1024*1024), 3),
            checksum=hashlib.md5(content.encode()).hexdigest(),
            created_at=datetime.now().isoformat(),
        )
        self._backups[record.id] = record
        return record
    
    def list_backups(self) -> List[BackupRecord]:
        return sorted(self._backups.values(), key=lambda b: b.created_at, reverse=True)
    
    def restore_backup(self, backup_id: str) -> Optional[dict]:
        bk = self._backups.get(backup_id)
        if not bk or not os.path.exists(bk.path): return None
        with open(bk.path) as f:
            return json.load(f)
    
    def cleanup_old_backups(self, keep_days: int = 7):
        cutoff = datetime.now() - timedelta(days=keep_days)
        for bid, bk in list(self._backups.items()):
            bk_time = datetime.fromisoformat(bk.created_at)
            if bk_time < cutoff:
                if os.path.exists(bk.path):
                    os.remove(bk.path)
                del self._backups[bid]
