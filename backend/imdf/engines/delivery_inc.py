"""增量交付引擎-版本差分+增量包"""
import os, json, hashlib
from pathlib import Path
from typing import List, Optional

DELIVERY_DIR = Path("data/deliveries")
DELIVERY_DIR.mkdir(parents=True, exist_ok=True)

class IncrementalDelivery:
    @staticmethod
    def snapshot(dataset_id: str, files: List[str]) -> str:
        snap = {}
        for f in files:
            if os.path.exists(f):
                snap[f] = hashlib.md5(open(f, "rb").read(8192)).hexdigest()
        snap_id = f"{dataset_id}_{len(os.listdir(DELIVERY_DIR))}"
        (DELIVERY_DIR / f"{snap_id}.json").write_text(json.dumps(snap, indent=2))
        return snap_id
    
    @staticmethod
    def diff(old_snap_id: str, new_files: List[str]) -> dict:
        snap_file = DELIVERY_DIR / f"{old_snap_id}.json"
        if not snap_file.exists():
            return {"error": f"snapshot {old_snap_id} not found"}
        old = json.loads(snap_file.read_text())
        added, modified, deleted = [], [], []
        new_snap = {}
        for f in new_files:
            if os.path.exists(f):
                h = hashlib.md5(open(f, "rb").read(8192)).hexdigest()
                new_snap[f] = h
                if f not in old:
                    added.append(f)
                elif old[f] != h:
                    modified.append(f)
        for f in old:
            if f not in new_snap:
                deleted.append(f)
        return {
            "added": added, "modified": modified, "deleted": deleted,
            "total_changes": len(added) + len(modified) + len(deleted),
        }
    
    @staticmethod
    def create_patch(old_snap_id: str, new_files: List[str], output_dir: str = "data/patches") -> Optional[str]:
        import tarfile, io
        diff_data = IncrementalDelivery.diff(old_snap_id, new_files)
        if diff_data.get("total_changes", 0) == 0:
            return None
        patch_id = f"patch_{hashlib.md5(str(diff_data).encode()).hexdigest()[:8]}"
        patch_path = Path(output_dir) / f"{patch_id}.tar.gz"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(str(patch_path), "w:gz") as tar:
            for f in diff_data.get("added", []) + diff_data.get("modified", []):
                tar.add(f, arcname=os.path.basename(f))
            meta = json.dumps(diff_data, indent=2)
            info = tarfile.TarInfo(name="diff.json")
            info.size = len(meta.encode())
            tar.addfile(info, io.BytesIO(meta.encode()))
        return str(patch_path)
