"""
P0-4: Search / Filter Engine (SQLite FTS5)
===========================================
Full-text search using SQLite FTS5 with BM25 ranking and prefix matching.
"""

import sqlite3
from typing import List, Dict, Any


class FTSHelper:
    """SQLite FTS5全文搜索助手"""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")

    def create_index(self, table: str, columns: List[str]) -> None:
        """创建FTS5全文搜索索引

        Args:
            table: 虚拟表名 (会添加 _fts 后缀)
            columns: 要建立索引的列名列表
        """
        fts_table = f"{table}_fts"
        col_defs = ", ".join(columns)
        self._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS \"{fts_table}\" "
            f"USING fts5({col_defs})"
        )
        self._conn.commit()

    def _list_fts_tables(self) -> List[str]:
        """获取所有FTS虚拟表"""
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
        ).fetchall()
        return [r[0] for r in rows]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """执行全文搜索

        Supports:
          - BM25 ranking (ORDER BY rank)
          - Prefix matching (via * suffix)

        Args:
            query: 搜索关键词 (支持FTS5语法)
            limit: 返回最大条数

        Returns:
            匹配结果列表
        """
        results = []
        for fts_table in self._list_fts_tables():
            try:
                cursor = self._conn.execute(
                    f"SELECT rank, * FROM \"{fts_table}\" WHERE \"{fts_table}\" MATCH ? "
                    f"ORDER BY rank LIMIT ?",
                    (query, limit)
                )
                columns = [desc[0] for desc in cursor.description]
                for row in cursor.fetchall():
                    results.append(dict(zip(columns, row)))
            except sqlite3.OperationalError:
                continue
        # Sort all results by rank (BM25)
        results.sort(key=lambda r: r.get("rank", 999))
        return results[:limit]

    def add_document(self, fts_table: str, rowid: int, content_dict: Dict[str, str]) -> None:
        """添加文档到FTS索引

        Args:
            fts_table: FTS虚拟表名 (含 _fts 后缀)
            rowid: 对应内容表的rowid
            content_dict: {列名: 文本内容}
        """
        cols = ", ".join(content_dict.keys())
        placeholders = ", ".join(["?"] * len(content_dict))
        values = list(content_dict.values())
        self._conn.execute(
            f"INSERT OR REPLACE INTO \"{fts_table}\" (rowid, {cols}) "
            f"VALUES (?, {placeholders})",
            [rowid] + values
        )
        self._conn.commit()

    def delete_document(self, fts_table: str, rowid: int) -> None:
        """从FTS索引删除文档

        Args:
            fts_table: FTS虚拟表名 (含 _fts 后缀)
            rowid: 要删除的rowid
        """
        self._conn.execute(
            f"DELETE FROM \"{fts_table}\" WHERE rowid = ?",
            (rowid,)
        )
        self._conn.commit()

    def close(self) -> None:
        """关闭数据库连接"""
        self._conn.close()
