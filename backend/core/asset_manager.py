"""资产管理系统 — 文件夹/标签/智能文件夹/预览 (功能设计文档第4-6章)"""

import uuid, os, json
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel
from core.persistent_base import PersistentManager


class AssetType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    MODEL_3D = "3d"
    DOCUMENT = "document"
    FONT = "font"


class Asset(BaseModel):
    id: str
    name: str
    type: AssetType
    file_path: str = ""
    file_size: int = 0
    file_hash: str = ""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    folder_id: str = ""
    tags: List[str] = []
    score: float = 0.0
    description: str = ""
    metadata: Dict[str, Any] = {}
    created_at: str = ""
    updated_at: str = ""


class Folder(BaseModel):
    id: str
    name: str
    parent_id: str = ""
    project_id: str = ""
    color: str = ""
    cover_image: str = ""
    child_count: int = 0
    asset_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class Tag(BaseModel):
    id: str
    name: str
    parent_id: str = ""
    color: str = ""
    aliases: List[str] = []


class SmartFolder(BaseModel):
    id: str
    name: str
    project_id: str = ""
    rules: Dict[str, Any] = {}  # 过滤规则
    created_at: str = ""


class AssetManager(PersistentManager):
    _db_table = "assets"
    _db_fields = ["id","name","type","file_path","file_size","file_hash","width","height","duration","folder_id","tags","score","description","metadata","created_at","updated_at"]

    def __init__(self):
        self._assets: Dict[str, Asset] = {}
        self._folders: Dict[str, Folder] = {}
        self._tags: Dict[str, Tag] = {}
        self._smart_folders: Dict[str, SmartFolder] = {}
        self._tag_index: Dict[str, List[str]] = {}
        super().__init__()
        self._load_from_db()

    def _load_from_db(self):
        for row in self._load_all():
            asset = Asset(**row)
            self._assets[asset.id] = asset
            for t in asset.tags:
                self._tag_index.setdefault(t, []).append(asset.id)

    # ---- 资产管理 ----
    def add_asset(self, name: str, type: AssetType, file_path: str = "", folder_id: str = "", tags: List[str] = None) -> Asset:
        asset = Asset(
            id=f"ast-{uuid.uuid4().hex[:8]}",
            name=name, type=type, file_path=file_path,
            folder_id=folder_id, tags=tags or [],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._assets[asset.id] = asset
        for t in asset.tags:
            self._tag_index.setdefault(t, []).append(asset.id)
        self._save(asset.id, asset.model_dump())
        return asset

    def get_asset(self, asset_id: str) -> Optional[Asset]: return self._assets.get(asset_id)

    def search_assets(self, query: str = "", tags: List[str] = None, type: Optional[AssetType] = None,
                      folder_id: str = "", min_score: float = 0, limit: int = 100) -> List[Asset]:
        results = list(self._assets.values())
        if query:
            q = query.lower()
            results = [a for a in results if q in a.name.lower() or q in a.description.lower()]
        if tags:
            tag_set = set(tags)
            results = [a for a in results if tag_set.intersection(set(a.tags))]
        if type: results = [a for a in results if a.type == type]
        if folder_id: results = [a for a in results if a.folder_id == folder_id]
        if min_score > 0: results = [a for a in results if a.score >= min_score]
        return sorted(results, key=lambda a: a.created_at, reverse=True)[:limit]

    def update_asset_tags(self, asset_id: str, tags: List[str]) -> bool:
        asset = self._assets.get(asset_id)
        if not asset: return False
        for t in asset.tags:
            if asset.id in self._tag_index.get(t, []):
                self._tag_index[t].remove(asset.id)
        asset.tags = tags
        for t in tags:
            self._tag_index.setdefault(t, []).append(asset.id)
        asset.updated_at = datetime.now().isoformat()
        self._save(asset.id, asset.model_dump())
        return True

    def delete_asset(self, asset_id: str) -> bool:
        asset = self._assets.pop(asset_id, None)
        if not asset: return False
        for t in asset.tags:
            if asset.id in self._tag_index.get(t, []):
                self._tag_index[t].remove(asset.id)
        self._delete(asset_id)
        return True

    # ---- 文件夹管理 ----
    def create_folder(self, name: str, project_id: str = "", parent_id: str = "") -> Folder:
        folder = Folder(
            id=f"fld-{uuid.uuid4().hex[:8]}",
            name=name, project_id=project_id, parent_id=parent_id,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        self._folders[folder.id] = folder
        self._save(folder.id, folder.model_dump())
        return folder

    def get_folder(self, folder_id: str) -> Optional[Folder]: return self._folders.get(folder_id)

    def get_folder_tree(self, project_id: str = "") -> List[dict]:
        folders = [f for f in self._folders.values() if not project_id or f.project_id == project_id]
        tree = {}
        for f in folders:
            child = {"id": f.id, "name": f.name, "children": [], "asset_count": f.asset_count}
            if not f.parent_id:
                tree.setdefault("root", []).append(child)
            else:
                tree.setdefault(f.parent_id, []).append(child)
        # 递归构建树
        def _build(parent_id):
            children = []
            for f in folders:
                if f.parent_id == parent_id:
                    node = {"id": f.id, "name": f.name, "children": _build(f.id), "asset_count": f.asset_count}
                    children.append(node)
            return children
        return _build("")

    # ---- 标签管理 ----
    def create_tag(self, name: str, color: str = "", parent_id: str = "") -> Tag:
        tag = Tag(id=f"tag-{uuid.uuid4().hex[:6]}", name=name, color=color, parent_id=parent_id)
        self._tags[tag.id] = tag
        return tag

    def get_all_tags(self) -> List[Tag]: return list(self._tags.values())

    def search_by_tag(self, tag_name: str) -> List[Asset]:
        asset_ids = self._tag_index.get(tag_name, [])
        return [self._assets[aid] for aid in asset_ids if aid in self._assets]

    # ---- 智能文件夹 ----
    def create_smart_folder(self, name: str, project_id: str, rules: Dict[str, Any]) -> SmartFolder:
        sf = SmartFolder(
            id=f"sf-{uuid.uuid4().hex[:6]}",
            name=name, project_id=project_id, rules=rules,
            created_at=datetime.now().isoformat(),
        )
        self._smart_folders[sf.id] = sf
        self._save(sf.id, sf.model_dump())
        return sf

    def query_smart_folder(self, sf_id: str) -> List[Asset]:
        sf = self._smart_folders.get(sf_id)
        if not sf: return []
        results = list(self._assets.values())
        rules = sf.rules
        if rules.get("tags"):
            tag_set = set(rules["tags"])
            results = [a for a in results if tag_set.intersection(set(a.tags))]
        if rules.get("type"):
            results = [a for a in results if a.type.value == rules["type"]]
        if rules.get("min_score", 0) > 0:
            results = [a for a in results if a.score >= rules["min_score"]]
        if rules.get("date_range"):
            # 简单日期过滤
            pass
        return results

    # ---- 统计 ----
    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_assets": len(self._assets),
            "total_folders": len(self._folders),
            "total_tags": len(self._tags),
            "type_distribution": {t.value: sum(1 for a in self._assets.values() if a.type == t) for t in AssetType},
        }
