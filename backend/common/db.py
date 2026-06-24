"""backend/common/db — SQLAlchemy session Depends for the 12 services (P4-1-W1).

Why does this exist when ``imdf.db`` already exposes ``get_db``?
  * The 12 services run as separate processes and need a *fast*, *isolated*
    ``get_db`` that doesn't drag in pgvector / Celery config that the
    services don't need.
  * This module tries ``imdf.db`` first (so prod picks up the full ORM +
    models registered there); falls back to a self-contained SQLite engine
    when imdf isn't importable (smoke tests, fresh clones, etc.).

Public surface:
  * ``get_db``      — FastAPI Depends yielding a ``Session``
  * ``init_db``     — create_all helper (dev only)
  * ``ping``        — ``SELECT 1`` health probe
  * ``setup_db``    — configures the engine + Optionally creates tables
  * ``DB_READY``    — boolean: True if engine is reachable

Usage in a service ``main.py``::

    from common import setup_db, get_db

    app = FastAPI()
    setup_db(app, "user_service")     # mounts /healthz probe later anyway

    @router.get("/api/v1/users")
    def list_users(db: Session = Depends(get_db)):
        ...
"""
from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Will be populated by ``setup_db``
_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None
DB_READY: bool = False


def _build_engine(db_url: str) -> Engine:
    """Construct an Engine; auto-tune SQLite pragmas."""
    if db_url.startswith("sqlite"):
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
            except Exception:  # pragma: no cover
                pass
        return engine

    if db_url.startswith(("postgres", "postgresql")):
        # Try to use the imdf Postgres helper if present
        try:
            from db.postgres import build_pg_engine_kwargs, is_postgres_url, normalize_pg_url  # type: ignore

            url = normalize_pg_url(db_url) if is_postgres_url(db_url) else db_url
            return create_engine(url, **build_pg_engine_kwargs(url))
        except Exception as exc:  # pragma: no cover
            logger.warning("PG helper unavailable (%s); using default create_engine", exc)
            return create_engine(db_url, pool_pre_ping=True)

    # Fallback — treat as plain URL
    return create_engine(db_url, pool_pre_ping=True)


def setup_db(
    app: Optional[object] = None,
    service_name: Optional[str] = None,
    db_url: Optional[str] = None,
    *,
    auto_create: bool = False,
) -> Engine:
    """Initialize the SQLAlchemy engine for this process.

    * If *db_url* is given, use it directly.
    * Else try ``IMDF_P2_DB_URL`` env, then ``DATABASE_URL`` env, then
      SQLite under ``backend/data/imdf_common.db``.
    * When *auto_create* is True, run ``Base.metadata.create_all`` so dev
      smoke tests don't need alembic.
    """
    global _engine, _SessionLocal, DB_READY

    from .config import get_service_config

    name = service_name or os.environ.get("SERVICE_NAME", "unknown_service")
    cfg = get_service_config(name)

    url = (
        db_url
        or os.environ.get("IMDF_P2_DB_URL", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
        or cfg.db_url
    )

    # For SQLite URLs that look like relative paths, absolutize them.
    if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
        # sqlite:///relative.db  →  backend/data/<...>
        rel = url.replace("sqlite:///", "", 1)
        if not Path(rel).is_absolute():
            url = f"sqlite:///{(cfg.data_dir / rel).as_posix()}"

    _engine = _build_engine(url)

    _SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=_engine, expire_on_commit=False,
    )

    if auto_create:
        try:
            from sqlalchemy.orm import DeclarativeBase

            class _TmpBase(DeclarativeBase):
                pass

            _TmpBase.metadata.create_all(bind=_engine)
        except Exception as exc:  # pragma: no cover
            logger.warning("auto_create failed: %s", exc)

    DB_READY = ping()
    logger.info("setup_db complete: service=%s url=%s ready=%s", name, url, DB_READY)

    # Optionally stash the engine on the FastAPI app for later access
    if app is not None and hasattr(app, "state"):
        app.state.db_engine = _engine
        app.state.db_session_factory = _SessionLocal

    return _engine


def get_engine() -> Engine:
    if _engine is None:
        # Lazy setup so callers can ``Depends(get_db)`` without explicit setup_db
        setup_db()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker:
    if _SessionLocal is None:
        setup_db()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends: yield a Session, rollback on error, always close."""
    factory = get_session_factory()
    db: Session = factory()
    try:
        yield db
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("get_db rollback: %s", exc)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def ping() -> bool:
    """Quick ``SELECT 1`` health probe against the configured engine."""
    eng = _engine
    if eng is None:
        # No engine yet — try a one-off connection to the default DB path
        try:
            default = f"sqlite:///{(Path(__file__).resolve().parent.parent / 'data' / 'imdf_common.db').as_posix()}"
            tmp = create_engine(default, connect_args={"check_same_thread": False})
            with tmp.connect() as conn:
                return conn.execute(text("SELECT 1")).scalar() == 1
        except Exception:
            return False
    try:
        with eng.connect() as conn:
            return conn.execute(text("SELECT 1")).scalar() == 1
    except Exception as exc:
        logger.warning("db.ping failed: %s", exc)
        return False


def init_db() -> bool:
    """``create_all`` against any registered metadata; dev only."""
    eng = get_engine()
    try:
        from db import Base as ImdfBase  # type: ignore

        ImdfBase.metadata.create_all(bind=eng)
        logger.info("init_db: created imdf tables on %s", eng.url)
    except Exception:
        # No imdf.metadata registered — try a tiny local Base
        try:
            from sqlalchemy.orm import DeclarativeBase

            class _LocalBase(DeclarativeBase):
                pass

            _LocalBase.metadata.create_all(bind=eng)
            logger.info("init_db: created local Base tables on %s", eng.url)
        except Exception as exc:
            logger.warning("init_db failed: %s", exc)
            return False
    return True


__all__ = [
    "get_db",
    "get_engine",
    "get_session_factory",
    "ping",
    "init_db",
    "setup_db",
    "DB_READY",
]