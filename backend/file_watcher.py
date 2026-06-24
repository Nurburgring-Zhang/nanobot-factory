#!/usr/bin/env python3
"""
Nanobot Factory - File Watcher Service
Real-time file system monitoring for automation

@author MiniMax Agent
@date 2026-02-25
@description 文件系统监控服务，支持目录监听、文件变化检测、自动处理
"""

import os
import logging
import time
import hashlib
import threading
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import chokidar
    HAS_CHOKIDAR = True
except ImportError:
    HAS_CHOKIDAR = False
    logger.debug("chokidar not installed, file watcher will use fallback mode")

import yaml


class WatchEventType(str, Enum):
    """File watch event types"""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


class FileCategory(str, Enum):
    """File categories for classification"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    DOCUMENT = "document"
    MODEL = "model"
    DATASET = "dataset"
    OTHER = "other"


@dataclass
class WatchedFile:
    """Represents a watched file"""
    path: str
    relative_path: str
    category: FileCategory
    size: int
    extension: str
    hash: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileEvent:
    """File system event"""
    event_type: WatchEventType
    path: str
    relative_path: str
    category: FileCategory
    size: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class FileWatcher:
    """
    File system watcher with:
    - Directory monitoring
    - File change detection
    - Automatic categorization
    - Event callbacks
    - Debouncing for rapid changes
    """

    # File extension mappings
    EXTENSION_MAP = {
        FileCategory.IMAGE: {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg', '.ico'},
        FileCategory.VIDEO: {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'},
        FileCategory.AUDIO: {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'},
        FileCategory.TEXT: {'.txt', '.md', '.json', '.yaml', '.yml', '.xml', '.csv', '.log'},
        FileCategory.DOCUMENT: {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'},
        FileCategory.MODEL: {'.pth', '.pt', '.ckpt', '.safetensors', '.onnx', '.pb', '.h5'},
        FileCategory.DATASET: {'.jsonl', '.parquet', '.arrow', '.feather'},
    }

    def __init__(self,
                 watch_paths: Optional[List[str]] = None,
                 ignore_paths: Optional[List[str]] = None,
                 debounce_delay: float = 1.0,
                 compute_hash: bool = False):
        self.watch_paths = watch_paths or []
        self.ignore_paths = ignore_paths or ['.git', '__pycache__', 'node_modules', '.venv']
        self.debounce_delay = debounce_delay
        self.compute_hash = compute_hash

        # Fallback mode when chokidar is not available
        self._use_fallback_mode = not HAS_CHOKIDAR

        # Watcher instance
        self._watcher: Optional[Any] = None

        # File registry
        self._files: Dict[str, WatchedFile] = {}
        self._file_locks: Dict[str, threading.Lock] = {}
        self._lock = threading.RLock()

        # Pending events (for debouncing)
        self._pending_events: Dict[str, FileEvent] = {}
        self._debounce_timers: Dict[str, threading.Timer] = {}

        # Event callbacks
        self._on_file_created: Optional[Callable] = None
        self._on_file_modified: Optional[Callable] = None
        self._on_file_deleted: Optional[Callable] = None
        self._on_file_moved: Optional[Callable] = None
        self._on_batch: Optional[Callable] = None

        # Statistics
        self._stats = {
            "files_created": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "files_moved": 0,
            "total_events": 0
        }

    def set_callbacks(self,
                     on_file_created: Optional[Callable] = None,
                     on_file_modified: Optional[Callable] = None,
                     on_file_deleted: Optional[Callable] = None,
                     on_file_moved: Optional[Callable] = None,
                     on_batch: Optional[Callable] = None):
        """Set event callbacks"""
        self._on_file_created = on_file_created
        self._on_file_modified = on_file_modified
        self._on_file_deleted = on_file_deleted
        self._on_file_moved = on_file_moved
        self._on_batch = on_batch

    def add_watch_path(self, path: str):
        """Add a path to watch"""
        if path not in self.watch_paths:
            self.watch_paths.append(path)
            logger.info(f"Added watch path: {path}")

    def remove_watch_path(self, path: str):
        """Remove a path from watch"""
        if path in self.watch_paths:
            self.watch_paths.remove(path)
            logger.info(f"Removed watch path: {path}")

    def _categorize_file(self, path: str) -> FileCategory:
        """Categorize file by extension"""
        ext = os.path.splitext(path)[1].lower()
        for category, extensions in self.EXTENSION_MAP.items():
            if ext in extensions:
                return category
        return FileCategory.OTHER

    def _compute_file_hash(self, path: str) -> Optional[str]:
        """Compute file hash"""
        if not self.compute_hash:
            return None

        try:
            hasher = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.warning(f"Failed to compute hash for {path}: {e}")
            return None

    def _get_file_info(self, path: str) -> Optional[WatchedFile]:
        """Get file information"""
        try:
            if not os.path.exists(path):
                return None

            stat = os.stat(path)
            rel_path = path

            # Find relative path
            for watch_path in self.watch_paths:
                if path.startswith(watch_path):
                    rel_path = os.path.relpath(path, watch_path)
                    break

            return WatchedFile(
                path=path,
                relative_path=rel_path,
                category=self._categorize_file(path),
                size=stat.st_size,
                extension=os.path.splitext(path)[1].lower(),
                hash=self._compute_file_hash(path) if os.path.isfile(path) else None,
                created_at=datetime.fromtimestamp(stat.st_ctime).isoformat(),
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat()
            )
        except Exception as e:
            logger.warning(f"Failed to get file info for {path}: {e}")
            return None

    def _should_ignore(self, path: str) -> bool:
        """Check if path should be ignored"""
        path_parts = Path(path).parts
        for ignore in self.ignore_paths:
            if ignore in path_parts:
                return True
        return False

    def _handle_event(self, event_type: WatchEventType, path: str):
        """Handle file event with debouncing"""
        if self._should_ignore(path):
            return

        # Create event
        file_info = self._get_file_info(path) if event_type != WatchEventType.DELETED else None

        event = FileEvent(
            event_type=event_type,
            path=path,
            relative_path=file_info.relative_path if file_info else "",
            category=file_info.category if file_info else FileCategory.OTHER,
            size=file_info.size if file_info else 0
        )

        # Update statistics
        self._stats["total_events"] += 1
        if event_type == WatchEventType.CREATED:
            self._stats["files_created"] += 1
        elif event_type == WatchEventType.MODIFIED:
            self._stats["files_modified"] += 1
        elif event_type == WatchEventType.DELETED:
            self._stats["files_deleted"] += 1
        elif event_type == WatchEventType.MOVED:
            self._stats["files_moved"] += 1

        # Debounce
        key = f"{event_type}:{path}"
        if key in self._debounce_timers:
            self._debounce_timers[key].cancel()

        self._pending_events[key] = event

        # Schedule debounced callback
        timer = threading.Timer(self.debounce_delay, self._process_event, args=[key])
        self._debounce_timers[key] = timer
        timer.start()

    def _process_event(self, key: str):
        """Process debounced event"""
        event = self._pending_events.pop(key, None)
        if not event:
            return

        # Update file registry
        with self._lock:
            if event.event_type == WatchEventType.CREATED:
                file_info = self._get_file_info(event.path)
                if file_info:
                    self._files[event.path] = file_info

            elif event.event_type == WatchEventType.MODIFIED:
                if event.path in self._files:
                    file_info = self._get_file_info(event.path)
                    if file_info:
                        self._files[event.path] = file_info

            elif event.event_type == WatchEventType.DELETED:
                self._files.pop(event.path, None)

            elif event.event_type == WatchEventType.MOVED:
                # Handle as delete + create
                self._files.pop(event.path, None)

        # Call appropriate callback
        try:
            if event.event_type == WatchEventType.CREATED and self._on_file_created:
                self._on_file_created(event)
            elif event.event_type == WatchEventType.MODIFIED and self._on_file_modified:
                self._on_file_modified(event)
            elif event.event_type == WatchEventType.DELETED and self._on_file_deleted:
                self._on_file_deleted(event)
            elif event.event_type == WatchEventType.MOVED and self._on_file_moved:
                self._on_file_moved(event)
        except Exception as e:
            logger.error(f"Error in file event callback: {e}")

    def start(self):
        """Start watching files"""
        if not self.watch_paths:
            logger.warning("No watch paths configured")
            return

        # Validate paths
        valid_paths = []
        for path in self.watch_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                logger.warning(f"Watch path does not exist: {path}")

        if not valid_paths:
            logger.error("No valid watch paths")
            return

        # Check if chokidar is available
        if not HAS_CHOKIDAR:
            logger.warning("chokidar not available, using fallback mode")
            self._use_fallback_mode = True
            return

        # Create watcher
        self._watcher = chokidar.watch(
            valid_paths,
            ignored=self.ignore_paths,
            persistent=True,
            ignore_initial=True,
            await_write_finish=True,
            write_interval=0.5
        )

        # Add listeners
        self._watcher.on('add', lambda p: self._handle_event(WatchEventType.CREATED, p))
        self._watcher.on('change', lambda p: self._handle_event(WatchEventType.MODIFIED, p))
        self._watcher.on('unlink', lambda p: self._handle_event(WatchEventType.DELETED, p))

        # Start watcher in background
        self._watcher_thread = threading.Thread(target=self._run_watcher, daemon=True)
        self._watcher_thread.start()

        logger.info(f"Started watching {len(valid_paths)} paths: {valid_paths}")

    def _run_watcher(self):
        """Run watcher in sync mode"""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._watcher.wait())
        except Exception as e:
            logger.error(f"Watcher error: {e}")

    def stop(self):
        """Stop watching files"""
        if self._watcher:
            self._watcher.close()
            self._watcher = None

        # Cancel pending timers
        for timer in self._debounce_timers.values():
            timer.cancel()
        self._debounce_timers.clear()

        logger.info("File watcher stopped")

    def get_files(self, category: Optional[FileCategory] = None) -> List[WatchedFile]:
        """Get all watched files"""
        with self._lock:
            files = list(self._files.values())
            if category:
                files = [f for f in files if f.category == category]
            return files

    def get_stats(self) -> Dict[str, Any]:
        """Get watcher statistics"""
        return {
            **self._stats,
            "watching_paths": self.watch_paths,
            "total_files": len(self._files),
            "files_by_category": self._get_category_counts()
        }

    def _get_category_counts(self) -> Dict[str, int]:
        """Get file counts by category"""
        counts = {}
        for file in self._files.values():
            category = file.category.value
            counts[category] = counts.get(category, 0) + 1
        return counts


class SkillWatcher:
    """
    Specialized watcher for skill files.
    Monitors skill directories and auto-reloads on changes.
    """

    def __init__(self, skills_path: str):
        self.skills_path = skills_path
        self._watcher: Optional[FileWatcher] = None
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._on_skill_loaded: Optional[Callable] = None
        self._on_skill_unloaded: Optional[Callable] = None

    def set_callbacks(self,
                    on_skill_loaded: Optional[Callable] = None,
                    on_skill_unloaded: Optional[Callable] = None):
        """Set callbacks"""
        self._on_skill_loaded = on_skill_loaded
        self._on_skill_unloaded = on_skill_unloaded

    def _parse_skill(self, path: str) -> Optional[Dict[str, Any]]:
        """Parse skill file (SKILL.md)"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse YAML frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    metadata = yaml.safe_load(parts[1])
                    return {
                        "path": path,
                        "name": metadata.get("name", os.path.basename(path)),
                        "version": metadata.get("version", "1.0.0"),
                        "description": metadata.get("description", ""),
                        "commands": metadata.get("commands", []),
                        "content": parts[2].strip()
                    }

            return {
                "path": path,
                "name": os.path.basename(path),
                "version": "1.0.0",
                "description": "",
                "commands": [],
                "content": content
            }
        except Exception as e:
            logger.warning(f"Failed to parse skill {path}: {e}")
            return None

    def _load_skill(self, path: str):
        """Load or reload a skill"""
        skill = self._parse_skill(path)
        if not skill:
            return

        skill_id = os.path.relpath(path, self.skills_path)
        self._skills[skill_id] = skill

        if self._on_skill_loaded:
            self._on_skill_loaded(skill_id, skill)

        logger.info(f"Loaded skill: {skill_id}")

    def _unload_skill(self, path: str):
        """Unload a skill"""
        skill_id = os.path.relpath(path, self.skills_path)

        if skill_id in self._skills:
            del self._skills[skill_id]

            if self._on_skill_unloaded:
                self._on_skill_unloaded(skill_id)

            logger.info(f"Unloaded skill: {skill_id}")

    def start(self):
        """Start watching skills"""
        if not os.path.exists(self.skills_path):
            os.makedirs(self.skills_path, exist_ok=True)

        self._watcher = FileWatcher(
            watch_paths=[self.skills_path],
            ignore_paths=['.git'],
            debounce_delay=0.5
        )

        self._watcher.set_callbacks(
            on_file_created=lambda e: self._load_skill(e.path) if e.path.endswith('.md') else None,
            on_file_modified=lambda e: self._load_skill(e.path) if e.path.endswith('.md') else None,
            on_file_deleted=lambda e: self._unload_skill(e.path) if e.path.endswith('.md') else None
        )

        # Initial load
        for root, _, files in os.walk(self.skills_path):
            for file in files:
                if file.endswith('.md'):
                    path = os.path.join(root, file)
                    self._load_skill(path)

        self._watcher.start()
        logger.info(f"Started skill watcher: {self.skills_path}")

    def stop(self):
        """Stop watching skills"""
        if self._watcher:
            self._watcher.stop()

    def get_skills(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded skills"""
        return self._skills


# Global instances
_file_watcher: Optional[FileWatcher] = None
_skill_watcher: Optional[SkillWatcher] = None


def get_file_watcher() -> FileWatcher:
    """Get global file watcher instance"""
    global _file_watcher
    if _file_watcher is None:
        _file_watcher = FileWatcher()
    return _file_watcher


def get_skill_watcher(skills_path: str = "skills") -> SkillWatcher:
    """Get global skill watcher instance"""
    global _skill_watcher
    if _skill_watcher is None:
        _skill_watcher = SkillWatcher(skills_path)
    return _skill_watcher


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    import tempfile

    logging.basicConfig(level=logging.INFO)

    # Use platform-independent temp directory
    test_dir = os.path.join(tempfile.gettempdir(), "nanobot_test_watch")

    # Create file watcher
    watcher = FileWatcher(
        watch_paths=[test_dir],
        debounce_delay=1.0
    )

    # Set up callbacks
    watcher.set_callbacks(
        on_file_created=lambda e: print(f"Created: {e.path}"),
        on_file_modified=lambda e: print(f"Modified: {e.path}"),
        on_file_deleted=lambda e: print(f"Deleted: {e.path}")
    )

    # Create test directory
    os.makedirs(test_dir, exist_ok=True)

    # Start watching
    watcher.start()

    # Test by creating a file
    time.sleep(1)
    test_file = os.path.join(test_dir, "test.txt")
    with open(test_file, "w") as f:
        f.write("Hello World")

    time.sleep(2)

    # Get stats
    print("\n=== Watcher Stats ===")
    stats = watcher.get_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Get files
    print("\n=== Watched Files ===")
    for file in watcher.get_files():
        print(f"  - {file.relative_path} ({file.category.value})")

    # Stop watching
    watcher.stop()
