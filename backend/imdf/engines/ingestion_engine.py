"""数据导入引擎-支持CSV/JSON/Excel格式"""
import csv, json, os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class IngestionEngine:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "imdf.db")
    
    def import_csv(self, file_path: str, table: str = "imported_data") -> dict:
        import sqlite3
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return {"success": False, "error": "空文件"}
        return self._insert_rows(rows, table)
    
    def import_json(self, file_path: str, table: str = "imported_data") -> dict:
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = [data]
        return self._insert_rows(data, table)
    
    def import_excel(self, file_path: str, table: str = "imported_data") -> dict:
        try:
            import openpyxl
        except ImportError:
            return {"success": False, "error": "需要安装openpyxl: pip install openpyxl"}
        if not os.path.exists(file_path):
            return {"success": False, "error": f"文件不存在: {file_path}"}
        wb = openpyxl.load_workbook(file_path, read_only=True)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            rows.append({headers[i]: row[i] for i in range(len(headers)) if i < len(headers)})
        return self._insert_rows(rows, table)
    
    def _insert_rows(self, rows: List[Dict], table: str) -> dict:
        import sqlite3
        if not rows:
            return {"success": False, "error": "无数据"}
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cols = list(rows[0].keys())
        col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
        cursor.execute(f"CREATE TABLE IF NOT EXISTS [{table}] (id INTEGER PRIMARY KEY AUTOINCREMENT, _imported_at TEXT, {col_defs})")
        placeholders = ", ".join(["?" for _ in cols + ["_imported_at"]])
        ts = datetime.now().isoformat()
        inserted = 0
        for row in rows:
            try:
                values = [str(row.get(c, "")) for c in cols] + [ts]
                cols_str = ", ".join([f'"{c}"' for c in cols])
                vals_str = ", ".join(["?" for _ in cols + ["_imported_at"]])
                cursor.execute(f"INSERT INTO [{table}] ({cols_str}, _imported_at) VALUES ({vals_str})", values)
                inserted += 1
            except Exception as e:
                logger.error(f"Operation failed: {e}")
        conn.commit()
        conn.close()
        return {"success": True, "data": {"table": table, "rows_imported": inserted, "columns": cols, "total_in_file": len(rows)}}
