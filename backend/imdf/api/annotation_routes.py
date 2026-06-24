"""标注保存路由 - 真实数据库实现"""
from fastapi import APIRouter
from pydantic import BaseModel
import sqlite3, os, json
from datetime import datetime

router = APIRouter(prefix="/api/annotations", tags=["annotations"])

_ANNOTATION_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "data", "annotation_history.db")

class AnnotationSave(BaseModel):
    item_id: str
    annotations: list
    annotator: str
    confidence: float = 1.0

@router.post("/save")
async def save_annotation(req: AnnotationSave):
    """保存标注到 annotation_history.db 的 annotation_log 表"""
    try:
        conn = sqlite3.connect(_ANNOTATION_DB)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        # 每条 annotation 写入一行
        saved = 0
        for ann in req.annotations:
            # ann 可能是 dict(string) 或者纯字符串
            label = ann if isinstance(ann, str) else ann.get("label", str(ann))
            element_id = ann.get("element_id", "") if isinstance(ann, dict) else ""
            metadata = json.dumps(ann) if isinstance(ann, dict) else json.dumps({"value": ann})
            cursor.execute("""
                INSERT INTO annotation_log (dataset_id, element_id, action, label, labeler_id, confidence, metadata, created_at)
                VALUES (?, ?, 'annotate', ?, ?, ?, ?, ?)
            """, (req.item_id, element_id or f"elem_{saved}", label, req.annotator, req.confidence, metadata, now))
            saved += 1
        conn.commit()
        conn.close()
        return {"success": True, "saved": saved, "item_id": req.item_id, "source": "annotation_history.db"}
    except Exception as e:
        return {"success": False, "error": str(e), "item_id": req.item_id}

@router.get("/history")
async def annotation_history(item_id: str = ""):
    """查询标注历史"""
    try:
        conn = sqlite3.connect(_ANNOTATION_DB)
        cursor = conn.cursor()
        if item_id:
            rows = cursor.execute(
                "SELECT id, dataset_id, element_id, action, label, labeler_id, confidence, created_at FROM annotation_log WHERE dataset_id=? ORDER BY created_at DESC",
                (item_id,)).fetchall()
        else:
            rows = cursor.execute(
                "SELECT id, dataset_id, element_id, action, label, labeler_id, confidence, created_at FROM annotation_log ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        conn.close()
        records = []
        for r in rows:
            records.append({
                "id": r[0], "dataset_id": r[1], "element_id": r[2], "action": r[3],
                "label": r[4], "labeler_id": r[5], "confidence": r[6], "created_at": r[7]
            })
        return {"success": True, "records": records, "total": len(records)}
    except Exception as e:
        return {"success": False, "error": str(e)}
