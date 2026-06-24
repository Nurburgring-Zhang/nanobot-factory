#!/usr/bin/env python3
"""
NanoBot Factory - MongoDB Database Manager
MongoDB Database Manager with GridFS Support

Features:
- MongoDB connection management
- Collection operations
- Index management
- Aggregation pipeline support
- Document validation
- GridFS file storage

@author Matrix Agent
@date 2026-04-23
"""

import os
import json
import logging
import threading
import uuid
from typing import Optional, List, Dict, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime
from contextlib import contextmanager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MongoDBManager")

# Dependency check
try:
    from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
    from pymongo.collection import Collection
    from pymongo.database import Database
    from pymongo.errors import PyMongoError
    from bson import ObjectId
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False
    from bson import ObjectId
    logger.warning("pymongo not installed. Run: pip install pymongo")


@dataclass
class MongoDBConfig:
    """MongoDB connection configuration"""
    host: str = "localhost"
    port: int = 27017
    user: str = ""
    password: str = ""
    database: str = "nanobot_db"
    auth_source: str = "admin"
    max_pool_size: int = 100
    min_pool_size: int = 10
    connect_timeout: int = 10000
    server_selection_timeout: int = 5000
    retry_writes: bool = True
    retry_reads: bool = True
    
    @property
    def connection_string(self) -> str:
        if self.user and self.password:
            return f"mongodb://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?authSource={self.auth_source}"
        return f"mongodb://{self.host}:{self.port}/{self.database}"
    
    @classmethod
    def from_env(cls) -> "MongoDBConfig":
        return cls(
            host=os.getenv("MONGODB_HOST", "localhost"),
            port=int(os.getenv("MONGODB_PORT", "27017")),
            user=os.getenv("MONGODB_USER", ""),
            password=os.getenv("MONGODB_PASSWORD", ""),
            database=os.getenv("MONGODB_DATABASE", "nanobot_db"),
            auth_source=os.getenv("MONGODB_AUTH_SOURCE", "admin"),
            max_pool_size=int(os.getenv("MONGODB_POOL_SIZE", "100")),
        )


class MongoDBConnection:
    """MongoDB connection wrapper"""
    
    def __init__(self, config: MongoDBConfig):
        self.config = config
        self._client: Optional[Any] = None
        self._db: Optional[Database] = None
    
    def connect(self) -> bool:
        if not HAS_PYMONGO:
            logger.error("pymongo not installed")
            return False
        
        try:
            self._client = MongoClient(
                self.config.connection_string,
                maxPoolSize=self.config.max_pool_size,
                minPoolSize=self.config.min_pool_size,
                connectTimeoutMS=self.config.connect_timeout,
                serverSelectionTimeoutMS=self.config.server_selection_timeout,
                retryWrites=self.config.retry_writes,
                retryReads=self.config.retry_reads,
            )
            self._db = self._client[self.config.database]
            # Test connection
            self._client.admin.command('ping')
            logger.info(f"[MongoDB] Connected: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Connection failed: {e}")
            return False
    
    def is_connected(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.admin.command('ping')
            return True
        except Exception:
            return False
    
    def get_database(self) -> Database:
        if self._db is None:
            self.connect()
        return self._db
    
    def get_collection(self, name: str) -> Collection:
        return self.get_database()[name]
    
    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
            self._db = None


class MongoDBManager:
    """MongoDB database manager"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, config: MongoDBConfig = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: MongoDBConfig = None):
        if self._initialized:
            return
        self._initialized = True
        self.config = config or MongoDBConfig.from_env()
        self._conn = MongoDBConnection(self.config)
        self._conn.connect()
        self._gridfs = None
        self._init_collections()
        logger.info("[MongoDB] MongoDBManager initialized")
    
    def _init_collections(self):
        """Initialize collections with indexes"""
        collections = {
            "users": [
                [("username", ASCENDING), {"unique": True}],
                [("email", ASCENDING), {"unique": True}],
                [("created_at", DESCENDING)],
                [("status", ASCENDING)],
],
            "projects": [
                [("user_id", ASCENDING)],
                [("created_at", DESCENDING)],
                [("status", ASCENDING)],
            ],
            "assets": [
                [("user_id", ASCENDING)],
                [("project_id", ASCENDING)],
                [("asset_type", ASCENDING)],
                [("created_at", DESCENDING)],
                [("tags", ASCENDING)],
            ],
            "audit_logs": [
                [("user_id", ASCENDING)],
                [("created_at", DESCENDING)],
                [("action", ASCENDING)],
                [("resource_type", ASCENDING), ("resource_id", ASCENDING)],
            ],
            "annotation_tasks": [
                [("project_id", ASCENDING)],
                [("image_id", ASCENDING)],
                [("annotator_id", ASCENDING)],
                [("status", ASCENDING)],
                [("created_at", DESCENDING)],
            ],
            "generation_tasks": [
                [("user_id", ASCENDING)],
                [("project_id", ASCENDING)],
                [("status", ASCENDING)],
                [("created_at", DESCENDING)],
            ],
        }
        
        try:
            db = self._conn.get_database()
            for coll_name, indexes in collections.items():
                coll = db[coll_name]
                for index_spec, options in indexes:
                    coll.create_index(index_spec, **options)
            logger.info("[MongoDB] Collections initialized")
        except Exception as e:
            logger.error(f"[MongoDB] Collection init failed: {e}")
    
    @property
    def db(self) -> Database:
        return self._conn.get_database()
    
    def collection(self, name: str) -> Collection:
        return self._conn.get_collection(name)
    
    # ==================== CRUD Operations ====================
    
    def insert_one(self, collection: str, document: Dict[str, Any]) -> Optional[str]:
        """Insert a single document"""
        if "_id" not in document:
            document["_id"] = str(uuid.uuid4())
        document["created_at"] = datetime.now()
        document["updated_at"] = datetime.now()
        
        try:
            result = self.collection(collection).insert_one(document)
            return str(document["_id"])
        except Exception as e:
            logger.error(f"[MongoDB] Insert failed: {e}")
            return None
    
    def insert_many(self, collection: str, documents: List[Dict[str, Any]]) -> List[str]:
        """Insert multiple documents"""
        for doc in documents:
            if "_id" not in doc:
                doc["_id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.now()
            doc["updated_at"] = datetime.now()
        
        try:
            result = self.collection(collection).insert_many(documents)
            return [str(id) for id in result.inserted_ids]
        except Exception as e:
            logger.error(f"[MongoDB] Insert many failed: {e}")
            return []
    
    def find_one(self, collection: str, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find a single document"""
        try:
            doc = self.collection(collection).find_one(query)
            return doc
        except Exception as e:
            logger.error(f"[MongoDB] Find one failed: {e}")
            return None
    
    def find_by_id(self, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """Find document by ID"""
        return self.find_one(collection, {"_id": doc_id})
    
    def find(
        self,
        collection: str,
        query: Dict[str, Any] = None,
        projection: List[str] = None,
        sort: List[Tuple[str, int]] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        """Find documents"""
        query = query or {}
        
        try:
            coll = self.collection(collection)
            cursor = coll.find(query)
            
            if projection:
                cursor = cursor.project(projection)
            if sort:
                cursor = cursor.sort(sort)
            if skip:
                cursor = cursor.skip(skip)
            if limit:
                cursor = cursor.limit(limit)
            
            return list(cursor)
        except Exception as e:
            logger.error(f"[MongoDB] Find failed: {e}")
            return []
    
    def count(self, collection: str, query: Dict[str, Any] = None) -> int:
        """Count documents"""
        query = query or {}
        try:
            return self.collection(collection).count_documents(query)
        except Exception as e:
            logger.error(f"[MongoDB] Count failed: {e}")
            return 0
    
    def update_one(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> bool:
        """Update a single document"""
        update["updated_at"] = datetime.now()
        try:
            result = self.collection(collection).update_one(query, {"$set": update})
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"[MongoDB] Update one failed: {e}")
            return False
    
    def update_by_id(self, collection: str, doc_id: str, update: Dict[str, Any]) -> bool:
        """Update document by ID"""
        return self.update_one(collection, {"_id": doc_id}, update)
    
    def update_many(self, collection: str, query: Dict[str, Any], update: Dict[str, Any]) -> int:
        """Update multiple documents"""
        update["updated_at"] = datetime.now()
        try:
            result = self.collection(collection).update_many(query, {"$set": update})
            return result.modified_count
        except Exception as e:
            logger.error(f"[MongoDB] Update many failed: {e}")
            return 0
    
    def delete_one(self, collection: str, query: Dict[str, Any]) -> bool:
        """Delete a single document"""
        try:
            result = self.collection(collection).delete_one(query)
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"[MongoDB] Delete one failed: {e}")
            return False
    
    def delete_by_id(self, collection: str, doc_id: str) -> bool:
        """Delete document by ID"""
        return self.delete_one(collection, {"_id": doc_id})
    
    def delete_many(self, collection: str, query: Dict[str, Any]) -> int:
        """Delete multiple documents"""
        try:
            result = self.collection(collection).delete_many(query)
            return result.deleted_count
        except Exception as e:
            logger.error(f"[MongoDB] Delete many failed: {e}")
            return 0
    
    # ==================== Aggregation ====================
    
    def aggregate(self, collection: str, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute aggregation pipeline"""
        try:
            return list(self.collection(collection).aggregate(pipeline))
        except Exception as e:
            logger.error(f"[MongoDB] Aggregate failed: {e}")
            return []
    
    def group(
        self,
        collection: str,
        key: str,
        accumulator: Dict[str, str],
        query: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """Group documents"""
        pipeline = []
        if query:
            pipeline.append({"$match": query})
        pipeline.append({
            "$group": {
                "_id": f"${key}",
                **accumulator
            }
        })
        return self.aggregate(collection, pipeline)
    
    # ==================== Text Search ====================
    
    def create_text_index(self, collection: str, fields: List[str]) -> bool:
        """Create text search index"""
        try:
            index_spec = [(f, TEXT) for f in fields]
            self.collection(collection).create_index(index_spec)
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Create text index failed: {e}")
            return False
    
    def text_search(self, collection: str, search_text: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search using text index"""
        try:
            return list(self.collection(collection).find(
                {"$text": {"$search": search_text}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit))
        except Exception as e:
            logger.error(f"[MongoDB] Text search failed: {e}")
            return []
    
    # ==================== GridFS ====================
    
    @property
    def gridfs(self):
        """Get GridFS instance"""
        if self._gridfs is None:
            from gridfs import GridFS
            self._gridfs = GridFS(self.db)
        return self._gridfs
    
    def store_file(
        self,
        file_data: bytes,
        filename: str,
        metadata: Dict[str, Any] = None,
        content_type: str = "application/octet-stream",
    ) -> Optional[str]:
        """Store file in GridFS"""
        try:
            file_id = self.gridfs.put(
                file_data,
                filename=filename,
                content_type=content_type,
                metadata=metadata or {}
            )
            return str(file_id)
        except Exception as e:
            logger.error(f"[MongoDB] Store file failed: {e}")
            return None
    
    def get_file(self, file_id: str) -> Optional[bytes]:
        """Retrieve file from GridFS"""
        try:
            from bson.objectid import ObjectId
            oid = ObjectId(file_id) if len(file_id) == 24 else file_id
            grid_out = self.gridfs.get(oid)
            return grid_out.read()
        except Exception as e:
            logger.error(f"[MongoDB] Get file failed: {e}")
            return None
    
    def delete_file(self, file_id: str) -> bool:
        """Delete file from GridFS"""
        try:
            from bson.objectid import ObjectId
            oid = ObjectId(file_id) if len(file_id) == 24 else file_id
            self.gridfs.delete(oid)
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Delete file failed: {e}")
            return False
    
    def list_files(self, query: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """List files in GridFS"""
        try:
            query = query or {}
            files = []
            for f in self.gridfs.find(query):
                files.append({
                    "_id": str(f._id),
                    "filename": f.filename,
                    "content_type": f.content_type,
                    "length": f.length,
                    "upload_date": f.upload_date,
                    "metadata": f.metadata,
                })
            return files
        except Exception as e:
            logger.error(f"[MongoDB] List files failed: {e}")
            return []
    
    # ==================== Index Management ====================
    
    def create_index(
        self,
        collection: str,
        keys: List[Tuple[str, int]],
        **kwargs
    ) -> bool:
        """Create index on collection"""
        try:
            self.collection(collection).create_index(keys, **kwargs)
            return True
        except Exception as e:
            logger.error(f"[MongoDB] Create index failed: {e}")
            return False
    
    def list_indexes(self, collection: str) -> List[Dict[str, Any]]:
        """List indexes for collection"""
        try:
            return list(self.collection(collection).list_indexes())
        except Exception as e:
            logger.error(f"[MongoDB] List indexes failed: {e}")
            return []
    
    # ==================== Utilities ====================
    
    def health_check(self) -> Dict[str, Any]:
        """Health check"""
        try:
            self._conn._client.admin.command('ping')
            return {
                "status": "healthy",
                "connected": True,
                "database": self.config.database,
                "host": f"{self.config.host}:{self.config.port}",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
            }
    
    def get_stats(self, collection: str = None) -> Dict[str, Any]:
        """Get database/collection stats"""
        try:
            if collection:
                return dict(self.collection(collection).aggregate([
                    {"$collStats": {"count": {}, "storageStats": {}}}
                ]))
            return dict(self.db.command("dbStats"))
        except Exception as e:
            logger.error(f"[MongoDB] Get stats failed: {e}")
            return {}
    
    def close(self):
        """Close connection"""
        if self._conn:
            self._conn.close()
        MongoDBManager._instance = None
        self._initialized = False


_mongodb_manager: Optional[MongoDBManager] = None


def get_mongodb_manager(config: MongoDBConfig = None) -> MongoDBManager:
    """Get MongoDB manager singleton"""
    global _mongodb_manager
    if _mongodb_manager is None:
        _mongodb_manager = MongoDBManager(config)
    return _mongodb_manager


def init_mongodb(config: MongoDBConfig) -> MongoDBManager:
    """Initialize MongoDB manager"""
    global _mongodb_manager
    if _mongodb_manager:
        _mongodb_manager.close()
    _mongodb_manager = MongoDBManager(config)
    return _mongodb_manager


if __name__ == "__main__":
    print("=== MongoDB Manager Test ===")
    
    config = MongoDBConfig(
        host=os.getenv("MONGODB_HOST", "localhost"),
        port=int(os.getenv("MONGODB_PORT", "27017")),
        user=os.getenv("MONGODB_USER", ""),
        password=os.getenv("MONGODB_PASSWORD", ""),
        database=os.getenv("MONGODB_DATABASE", "nanobot_db"),
    )
    
    mongo = MongoDBManager(config)
    health = mongo.health_check()
    print(f"Health: {health}")
    
    if health["connected"]:
        # Test CRUD
        uid = mongo.insert_one("users", {
            "username": "test_user",
            "email": "test@example.com",
            "role": "user",
        })
        print(f"Inserted: {uid}")
        
        user = mongo.find_by_id("users", uid)
        print(f"Retrieved: {user}")
        
        mongo.update_by_id("users", uid, {"display_name": "Test User"})
        
        users = mongo.find("users", {"status": {"$exists": False}}, limit=10)
        print(f"Users found: {len(users)}")
        
        count = mongo.count("users")
        print(f"Total users: {count}")
        
        mongo.delete_by_id("users", uid)
        print("Deleted")
        
        # Test aggregation
        pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        groups = mongo.aggregate("users", pipeline)
        print(f"Groups: {groups}")
        
        mongo.close()
    
    print("=== Test Complete ===")
