"""数据集版本管理——git-like版本控制"""
import json, logging, uuid, hashlib, copy
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)

class DatasetVersion:
    """数据集版本——对标HuggingFace Datasets的git-like版本
    
    每个版本包含：
    - snapshot: 数据集的完整快照（实际存diff减少内存）
    - parent: 父版本ID（实现版本树/分支）
    - message: 版本描述消息
    - tags: 为重要版本打标签
    """
    
    _versions: Dict[str, dict] = {}  # version_id -> version data
    _branches: Dict[str, str] = {}   # branch_name -> head version_id
    _tags: Dict[str, str] = {}       # tag_name -> version_id
    
    def __init__(self, dataset_id: str, name: str = ""):
        self.dataset_id = dataset_id
        self.name = name or f"dataset_{dataset_id[:8]}"
        self._data: List[Dict] = []  # 当前版本的数据行
    
    def _gen_version_id(self) -> str:
        return hashlib.sha256(f"{self.dataset_id}{datetime.now().isoformat()}{uuid.uuid4()}".encode()).hexdigest()[:16]
    
    def commit(self, message: str = "", branch: str = "main") -> str:
        """提交当前数据为新版本"""
        version_id = self._gen_version_id()
        parent = self._branches.get(branch, "")
        
        version = {
            "version_id": version_id,
            "dataset_id": self.dataset_id,
            "parent": parent,
            "branch": branch,
            "message": message or f"Version {version_id[:8]}",
            "data_count": len(self._data),
            "snapshot": copy.deepcopy(self._data),
            "created_at": datetime.now().isoformat()
        }
        self._versions[version_id] = version
        self._branches[branch] = version_id
        return version_id
    
    def checkout(self, version_id: str) -> bool:
        """切换到指定版本"""
        version = self._versions.get(version_id)
        if not version:
            return False
        self._data = copy.deepcopy(version.get("snapshot", []))
        return True
    
    def checkout_branch(self, branch: str) -> bool:
        """切换到分支的最新版本"""
        head = self._branches.get(branch)
        if not head:
            return False
        return self.checkout(head)
    
    def diff(self, version_a: str, version_b: str) -> Dict:
        """比较两个版本的差异"""
        va = self._versions.get(version_a)
        vb = self._versions.get(version_b)
        if not va or not vb:
            return {"error": "Version not found"}
        
        data_a = va.get("snapshot", [])
        data_b = vb.get("snapshot", [])
        
        # 简化diff：找出新增/删除/修改的行
        ids_a = {d.get("id", i): d for i, d in enumerate(data_a)}
        ids_b = {d.get("id", i): d for i, d in enumerate(data_b)}
        
        added = [d for i, d in ids_b.items() if i not in ids_a]
        removed = [d for i, d in ids_a.items() if i not in ids_b]
        modified = [{"id": i, "old": ids_a[i], "new": ids_b[i]} 
                    for i in ids_a if i in ids_b and ids_a[i] != ids_b[i]]
        
        return {
            "version_a": version_a,
            "version_b": version_b,
            "added_count": len(added),
            "removed_count": len(removed),
            "modified_count": len(modified),
            "added": added[:5],
            "removed": removed[:5],
            "modified": modified[:5]
        }
    
    def create_branch(self, branch_name: str, from_version: str = "") -> bool:
        """从指定版本创建分支"""
        if branch_name in self._branches:
            return False  # 分支已存在
        
        source = from_version or self._branches.get("main", "")
        if source and source in self._versions:
            self._branches[branch_name] = source
            return True
        # 从当前数据创建
        version_id = self._gen_version_id()
        version = {
            "version_id": version_id,
            "dataset_id": self.dataset_id,
            "parent": "",
            "branch": branch_name,
            "message": f"Branch '{branch_name}' created",
            "data_count": len(self._data),
            "snapshot": copy.deepcopy(self._data),
            "created_at": datetime.now().isoformat()
        }
        self._versions[version_id] = version
        self._branches[branch_name] = version_id
        return True
    
    def merge(self, source_branch: str, target_branch: str = "main", strategy: str = "ours") -> Optional[str]:
        """合并分支（ours=以source为主, union=合并）"""
        source_head = self._branches.get(source_branch)
        target_head = self._branches.get(target_branch)
        if not source_head:
            return None
        
        source_data = self._versions[source_head].get("snapshot", [])
        target_data = self._versions.get(target_head, {}).get("snapshot", []) if target_head else []
        
        if strategy == "ours":
            merged = copy.deepcopy(source_data)
        else:  # union
            ids = {d.get("id", i): d for i, d in enumerate(target_data)}
            for d in source_data:
                did = d.get("id", len(ids))
                ids[did] = d
            merged = list(ids.values())
        
        self._data = merged
        version_id = self.commit(f"Merge branch '{source_branch}' into '{target_branch}'", target_branch)
        return version_id
    
    def tag(self, tag_name: str, version_id: str = "") -> bool:
        v = version_id or self._branches.get("main", "")
        if v and v in self._versions:
            self._tags[tag_name] = v
            return True
        return False
    
    def log(self, branch: str = "main", limit: int = 10) -> List[dict]:
        head = self._branches.get(branch)
        if not head:
            return []
        versions = []
        v = head
        while v and len(versions) < limit:
            version = self._versions.get(v)
            if not version:
                break
            versions.append({
                "version_id": version["version_id"],
                "message": version["message"],
                "branch": version["branch"],
                "data_count": version["data_count"],
                "created_at": version["created_at"],
                "parent": version.get("parent", "")
            })
            v = version.get("parent", "")
        return versions
    
    def get_data(self) -> List[Dict]:
        return self._data
    
    def add_row(self, row: Dict):
        self._data.append(row)
    
    def remove_row(self, row_id: str):
        self._data = [d for d in self._data if d.get("id") != row_id]
    
    def rollback(self, version_id: str) -> bool:
        """回滚到指定版本（相当于git revert）"""
        return self.checkout(version_id)


class DatasetVersionManager:
    """数据集版本管理器——管理多个数据集的版本"""
    _datasets: Dict[str, DatasetVersion] = {}
    
    @classmethod
    def get_or_create(cls, dataset_id: str, name: str = "") -> DatasetVersion:
        if dataset_id not in cls._datasets:
            cls._datasets[dataset_id] = DatasetVersion(dataset_id, name)
        return cls._datasets[dataset_id]
    
    @classmethod
    def list_datasets(cls) -> List[dict]:
        return [{"dataset_id": d.dataset_id, "name": d.name, "rows": len(d._data)} 
                for d in cls._datasets.values()]

_ver_manager = None
def get_version_manager():
    global _ver_manager
    if _ver_manager is None:
        _ver_manager = DatasetVersionManager()
    return _ver_manager
