#!/usr/bin/env python3
"""
Nanobot Factory - Memory System
Long-term memory with vector database for RAG

@author MiniMax Agent
@date 2026-02-25
"""

import os
import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy not installed, using simplified similarity")

try:
    import sqlite3
except ImportError:
    # Fallback for environments without sqlite
    sqlite3 = None

@dataclass
class MemoryEntry:
    """Represents a memory entry"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    memory_type: str = "context"  # context, knowledge, history
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    accessed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0

class VectorStore:
    """Simple vector store for embeddings (fallback when no numpy)"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self._initialize()

    def _initialize(self):
        """Initialize the vector store database"""
        if sqlite3 is None:
            logger.error("sqlite3 not available")
            return

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript('''
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding BLOB,
                memory_type TEXT DEFAULT 'context',
                importance REAL DEFAULT 0.5,
                metadata TEXT,
                created_at TEXT NOT NULL,
                accessed_at TEXT NOT NULL,
                access_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
            CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
            CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
        ''')
        self.conn.commit()

    def add(self, entry: MemoryEntry) -> bool:
        """Add a memory entry"""
        if sqlite3 is None or self.conn is None:
            return False

        try:
            # Convert embedding to binary if available
            embedding_blob = None
            if entry.embedding and HAS_NUMPY:
                import numpy as np
                embedding_blob = np.array(entry.embedding, dtype=np.float32).tobytes()

            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO memories
                (id, content, embedding, memory_type, importance, metadata, created_at, accessed_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                entry.id,
                entry.content,
                embedding_blob,
                entry.memory_type,
                entry.importance,
                json.dumps(entry.metadata),
                entry.created_at,
                entry.accessed_at,
                entry.access_count
            ))
            self.conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            return False

    def search(
        self,
        query_embedding: Optional[List[float]] = None,
        query_text: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """Search memories by embedding similarity or text"""
        if sqlite3 is None or self.conn is None:
            return []

        try:
            cursor = self.conn.cursor()

            # Build query
            if query_text:
                # Text-based search
                sql = '''
                    SELECT * FROM memories
                    WHERE content LIKE ?
                '''
                params = [f'%{query_text}%']

                if memory_type:
                    sql += ' AND memory_type = ?'
                    params.append(memory_type)

                sql += ' ORDER BY importance DESC, access_count DESC LIMIT ?'
                params.append(limit)

                cursor.execute(sql, params)

            elif query_embedding and HAS_NUMPY:
                # Embedding-based search with REAL vector similarity computation
                import numpy as np
                
                # Convert query embedding to numpy array
                query_vec = np.array(query_embedding, dtype=np.float32)
                query_vec = query_vec / np.linalg.norm(query_vec)  # Normalize for cosine similarity
                
                # Fetch all memories with embeddings
                if memory_type:
                    sql = 'SELECT * FROM memories WHERE memory_type = ? AND embedding IS NOT NULL'
                    cursor.execute(sql, [memory_type])
                else:
                    sql = 'SELECT * FROM memories WHERE embedding IS NOT NULL'
                    cursor.execute(sql)
                
                rows = cursor.fetchall()
                
                # Calculate real similarity scores
                scored_results = []
                for row in rows:
                    try:
                        # Decode stored embedding
                        stored_embedding = np.frombuffer(row['embedding'], dtype=np.float32)
                        stored_vec = stored_embedding / np.linalg.norm(stored_embedding)  # Normalize
                        
                        # Compute cosine similarity: cos(θ) = (A·B) / (||A|| × ||B||)
                        # Since both are normalized: cos(θ) = A·B
                        cosine_sim = float(np.dot(query_vec, stored_vec))
                        
                        # Compute Euclidean distance: ||A - B||
                        euclidean_dist = float(np.linalg.norm(query_vec - stored_vec))
                        
                        # Convert distance to similarity (0-1 scale): 1 / (1 + distance)
                        euclidean_sim = 1.0 / (1.0 + euclidean_dist)
                        
                        # Compute dot product (unnormalized similarity)
                        dot_product = float(np.dot(query_vec * np.linalg.norm(query_vec), 
                                                   stored_vec * np.linalg.norm(stored_vec)))
                        
                        # Use cosine similarity as primary score
                        combined_score = cosine_sim
                        
                        scored_results.append({
                            'row': row,
                            'cosine_similarity': cosine_sim,
                            'euclidean_distance': euclidean_dist,
                            'dot_product': dot_product,
                            'score': combined_score
                        })
                    except Exception as e:
                        logger.warning(f"Error computing similarity for row {row['id']}: {e}")
                        continue
                
                # Sort by similarity score (highest first)
                scored_results.sort(key=lambda x: x['score'], reverse=True)
                
                # Take top 'limit' results
                top_results = scored_results[:limit]
                
                # Convert back to MemoryEntry objects
                for result in top_results:
                    row = result['row']
                    embedding = np.frombuffer(row['embedding'], dtype=np.float32).tolist()
                    
                    entry = MemoryEntry(
                        id=row['id'],
                        content=row['content'],
                        embedding=embedding,
                        memory_type=row['memory_type'],
                        importance=row['importance'],
                        metadata=json.loads(row['metadata']) if row['metadata'] else {},
                        created_at=row['created_at'],
                        accessed_at=row['accessed_at'],
                        access_count=row['access_count']
                    )
                    results.append(entry)
                
                # Batch update access counts
                if results:
                    entry_ids = [entry.id for entry in results]
                    now = datetime.now().isoformat()
                    placeholders = ','.join(['?' for _ in entry_ids])
                    cursor.execute(f'''
                        UPDATE memories
                        SET accessed_at = ?, access_count = access_count + 1
                        WHERE id IN ({placeholders})
                    ''', (now, *entry_ids))
                
                self.conn.commit()
                return results

            else:
                # Default: return recent/high importance
                sql = 'SELECT * FROM memories ORDER BY importance DESC, created_at DESC LIMIT ?'
                cursor.execute(sql, [limit])

            rows = cursor.fetchall()
            results = []

            for row in rows:
                # Decode embedding
                embedding = None
                if row['embedding']:
                    import numpy as np
                    embedding = np.frombuffer(row['embedding'], dtype=np.float32).tolist()

                entry = MemoryEntry(
                    id=row['id'],
                    content=row['content'],
                    embedding=embedding,
                    memory_type=row['memory_type'],
                    importance=row['importance'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    created_at=row['created_at'],
                    accessed_at=row['accessed_at'],
                    access_count=row['access_count']
                )
                results.append(entry)

            # Batch update access counts (fixes N+1 query issue)
            if results:
                entry_ids = [entry.id for entry in results]
                now = datetime.now().isoformat()
                # Use parameterized query with IN clause
                placeholders = ','.join(['?' for _ in entry_ids])
                cursor.execute(f'''
                    UPDATE memories
                    SET accessed_at = ?, access_count = access_count + 1
                    WHERE id IN ({placeholders})
                ''', (now, *entry_ids))

            self.conn.commit()
            return results

        except Exception as e:
            logger.error(f"Error searching memories: {e}")
            return []

    def delete(self, entry_id: str) -> bool:
        """Delete a memory entry"""
        if sqlite3 is None or self.conn is None:
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute('DELETE FROM memories WHERE id = ?', (entry_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting memory: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics"""
        if sqlite3 is None or self.conn is None:
            return {}

        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM memories')
        total = cursor.fetchone()[0]

        cursor.execute('SELECT memory_type, COUNT(*) as count FROM memories GROUP BY memory_type')
        by_type = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute('SELECT AVG(importance) as avg_importance FROM memories')
        avg_importance = cursor.fetchone()[0] or 0

        return {
            'total_memories': total,
            'by_type': by_type,
            'avg_importance': avg_importance
        }

    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()


class MemorySystem:
    """
    Long-term memory system with RAG capabilities.
    Provides context management, knowledge storage, and history tracking.
    """

    def __init__(self, db_path: str = "./memory.db"):
        self.vector_store = VectorStore(db_path)
        self.context_window = 5  # Number of recent entries to include in context

    def add_context(self, content: str, importance: float = 0.5, metadata: Dict[str, Any] = None) -> str:
        """Add context memory"""
        entry_id = hashlib.md5(f"{content}{datetime.now().isoformat()}".encode()).hexdigest()

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            memory_type="context",
            importance=importance,
            metadata=metadata or {}
        )

        self.vector_store.add(entry)
        logger.info(f"Added context memory: {entry_id}")
        return entry_id

    def add_knowledge(self, content: str, importance: float = 0.8, metadata: Dict[str, Any] = None) -> str:
        """Add knowledge memory (higher importance)"""
        entry_id = hashlib.md5(f"knowledge_{content}".encode()).hexdigest()

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            memory_type="knowledge",
            importance=importance,
            metadata=metadata or {}
        )

        self.vector_store.add(entry)
        logger.info(f"Added knowledge memory: {entry_id}")
        return entry_id

    def add_history(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """Add history memory"""
        entry_id = hashlib.md5(f"history_{content}{datetime.now().isoformat()}".encode()).hexdigest()

        entry = MemoryEntry(
            id=entry_id,
            content=content,
            memory_type="history",
            importance=0.3,  # Lower importance by default
            metadata=metadata or {}
        )

        self.vector_store.add(entry)
        logger.info(f"Added history memory: {entry_id}")
        return entry_id

    def get_relevant_context(self, query: str = None, limit: int = 5) -> List[MemoryEntry]:
        """Get relevant context for current task"""
        return self.vector_store.search(
            query_text=query,
            memory_type="context",
            limit=limit
        )

    def get_knowledge(self, query: str = None, limit: int = 5) -> List[MemoryEntry]:
        """Get relevant knowledge"""
        return self.vector_store.search(
            query_text=query,
            memory_type="knowledge",
            limit=limit
        )

    def get_history(self, limit: int = 10) -> List[MemoryEntry]:
        """Get recent history"""
        return self.vector_store.search(
            memory_type="history",
            limit=limit
        )

    def build_context_prompt(self, query: str = None) -> str:
        """Build a context prompt with relevant memories"""
        context_parts = []

        # Get relevant context
        context_memories = self.get_relevant_context(query, limit=3)
        if context_memories:
            context_parts.append("## Relevant Context")
            for mem in context_memories:
                context_parts.append(f"- {mem.content}")

        # Get relevant knowledge
        knowledge_memories = self.get_knowledge(query, limit=3)
        if knowledge_memories:
            context_parts.append("\n## Knowledge Base")
            for mem in knowledge_memories:
                context_parts.append(f"- {mem.content}")

        # Get recent history
        history_memories = self.get_history(limit=5)
        if history_memories:
            context_parts.append("\n## Recent History")
            for mem in history_memories:
                context_parts.append(f"- {mem.content}")

        return "\n".join(context_parts)

    def get_statistics(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        return self.vector_store.get_statistics()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    memory = MemorySystem("./test_memory.db")

    # Add some memories
    memory.add_context("User prefers dark theme UI", importance=0.7)
    memory.add_knowledge("API endpoint is http://localhost:8000", importance=0.9)
    memory.add_history("Generated 10 images yesterday")

    # Build context
    context = memory.build_context_prompt("images")
    print("Context Prompt:")
    print(context)

    # Stats
    stats = memory.get_statistics()
    print(f"\nStatistics: {stats}")

    memory.vector_store.close()
