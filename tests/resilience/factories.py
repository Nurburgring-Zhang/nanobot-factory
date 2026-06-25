"""R8-Worker-2 lightweight factory helpers.

The project doesn't ship factory_boy — installing it would balloon the
test deps. Instead, we provide a tiny factory_boy-style API built on top
of ``faker`` substitutes (uuid + counter, no external dep):

Usage::

    from factories import UserFactory, ProjectFactory, TaskFactory
    UserFactory.build_batch(50)
    UserFactory.create_batch(50, db_conn)  # writes to sqlite imdf.db
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Tiny faker replacement (no external dep) — just enough entropy for tests
# --------------------------------------------------------------------------- #
class _Faker:
    def __init__(self, seed: Optional[int] = None):
        self._seed = seed if seed is not None else int(time.time())
        # Linear congruential generator — not cryptographic, just varied.
        self._state = self._seed & 0xFFFFFFFF

    def _next(self) -> int:
        self._state = (self._state * 1103515245 + 12345) & 0x7FFFFFFF
        return self._state

    def name(self) -> str:
        firsts = ["Alice", "Bob", "Carol", "Dan", "Eve", "Frank", "Grace",
                  "Henry", "Ivy", "Jack", "Kate", "Leo", "Mia", "Nick",
                  "Olivia", "Paul", "Quinn", "Rita", "Sam", "Tina"]
        lasts = ["Smith", "Jones", "Brown", "Lee", "Wilson", "Taylor",
                 "Clark", "Hall", "Allen", "Young", "King", "Wright"]
        return f"{firsts[self._next() % len(firsts)]} {lasts[self._next() % len(lasts)]}"

    def email(self) -> str:
        return f"user_{self._next():08x}@nanobot.test"

    def sentence(self, nb_words: int = 6) -> str:
        nouns = ["project", "task", "render", "scene", "asset", "frame",
                 "node", "edge", "layer", "canvas", "shader", "image"]
        verbs = ["create", "render", "update", "validate", "ship", "test",
                 "design", "process", "review"]
        out = []
        for i in range(nb_words):
            pool = verbs if i % 2 == 0 else nouns
            out.append(pool[self._next() % len(pool)])
        return " ".join(out)

    def uuid(self) -> str:
        return str(uuid.UUID(int=self._next() * (2 ** 96) | self._next()))

    def choice(self, seq):
        return seq[self._next() % len(seq)]


_FAKER = _Faker(seed=42)


def faker() -> _Faker:
    return _FAKER


# --------------------------------------------------------------------------- #
# Factory base — factory_boy-style "build" / "create" without the package
# --------------------------------------------------------------------------- #
@dataclass
class _BaseFactory:
    _counter: int = 0
    _seq_lock: int = field(default=0, repr=False)

    @classmethod
    def _next_id(cls) -> int:
        cls._counter += 1
        return cls._counter

    @classmethod
    def build(cls, **overrides) -> Dict[str, Any]:
        d = cls._definition()
        d.update(overrides)
        return d

    @classmethod
    def build_batch(cls, count: int, **shared) -> List[Dict[str, Any]]:
        return [cls.build(**shared) for _ in range(count)]

    @classmethod
    def create(cls, db_conn: sqlite3.Connection, **overrides) -> Dict[str, Any]:
        d = cls.build(**overrides)
        cls._persist(db_conn, d)
        return d

    @classmethod
    def create_batch(cls, db_conn: sqlite3.Connection, count: int,
                     **shared) -> List[Dict[str, Any]]:
        return [cls.create(db_conn, **shared) for _ in range(count)]

    @classmethod
    def _definition(cls) -> Dict[str, Any]:  # pragma: no cover - overridden
        raise NotImplementedError

    @classmethod
    def _persist(cls, db_conn: sqlite3.Connection,
                 obj: Dict[str, Any]) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Concrete factories — 50 users, 100 projects, 200 tasks
# --------------------------------------------------------------------------- #
class UserFactory(_BaseFactory):
    @classmethod
    def _definition(cls) -> Dict[str, Any]:
        f = faker()
        return {
            "id": cls._next_id(),
            "username": f"user_{cls._counter:04d}",
            "email": f.email(),
            "display_name": f.name(),
            "role": f.choice(["admin", "editor", "viewer"]),
            "enabled": 1,
            "created_at": time.time(),
        }

    @classmethod
    def _persist(cls, db_conn: sqlite3.Connection, obj: Dict[str, Any]) -> None:
        db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factory_users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                email TEXT,
                display_name TEXT,
                role TEXT,
                enabled INTEGER,
                created_at REAL
            )
            """
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO factory_users VALUES "
            "(:id,:username,:email,:display_name,:role,:enabled,:created_at)",
            obj,
        )
        db_conn.commit()


class ProjectFactory(_BaseFactory):
    @classmethod
    def _definition(cls) -> Dict[str, Any]:
        f = faker()
        return {
            "id": cls._next_id(),
            "name": f.sentence(3),
            "owner_id": (cls._counter % 50) + 1,  # link to user pool
            "status": f.choice(["draft", "active", "archived", "review"]),
            "tags": json.dumps([f.choice(["video", "3d", "audio", "image", "annotation"])]),
            "created_at": time.time(),
        }

    @classmethod
    def _persist(cls, db_conn: sqlite3.Connection, obj: Dict[str, Any]) -> None:
        db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factory_projects (
                id INTEGER PRIMARY KEY,
                name TEXT,
                owner_id INTEGER,
                status TEXT,
                tags TEXT,
                created_at REAL
            )
            """
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO factory_projects VALUES "
            "(:id,:name,:owner_id,:status,:tags,:created_at)",
            obj,
        )
        db_conn.commit()


class TaskFactory(_BaseFactory):
    @classmethod
    def _definition(cls) -> Dict[str, Any]:
        f = faker()
        return {
            "id": cls._next_id(),
            "project_id": (cls._counter % 100) + 1,
            "kind": f.choice(["render", "transcode", "annotate", "classify",
                              "dedup", "upload", "download"]),
            "status": f.choice(["pending", "running", "done", "failed"]),
            "payload": json.dumps({"hint": f.sentence(2)}),
            "created_at": time.time(),
        }

    @classmethod
    def _persist(cls, db_conn: sqlite3.Connection, obj: Dict[str, Any]) -> None:
        db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS factory_tasks (
                id INTEGER PRIMARY KEY,
                project_id INTEGER,
                kind TEXT,
                status TEXT,
                payload TEXT,
                created_at REAL
            )
            """
        )
        db_conn.execute(
            "INSERT OR IGNORE INTO factory_tasks VALUES "
            "(:id,:project_id,:kind,:status,:payload,:created_at)",
            obj,
        )
        db_conn.commit()
