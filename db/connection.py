"""
db/connection.py — SQLAlchemy engine and session factory.

Uses DATABASE_URL from .env.
Connects via Supabase's Transaction Pooler (PgBouncer, port 6543).

PgBouncer transaction mode constraints applied:
  - prepare_threshold=None : disables server-side prepared statements, which
    are session-scoped and break under transaction pooling (connections are
    reassigned between transactions, so a prepared statement from one session
    won't exist on the next connection PgBouncer hands out).
  - pool_pre_ping=True     : rechecks connection liveness before each checkout
    since PgBouncer may silently drop idle connections.

Phase 3 will add the create_tables() call here after schema.sql is applied.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL: str = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    # Recycle connections after 60 s so they're discarded before PgBouncer's
    # idle-timeout (default 120 s) closes them out from under us.
    pool_recycle=60,
    connect_args={
        # Disable server-side prepared statements for PgBouncer transaction mode.
        # For psycopg2 (not psycopg3) the correct mechanism is a session-level
        # GUC: force_custom_plan prevents psycopg2 from sending PREPARE statements.
        "options": "-c plan_cache_mode=force_custom_plan",
    },
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session():
    """Context-managed DB session — use with 'with get_db_session() as session:'"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_db() -> bool:
    """Returns True if a SELECT 1 succeeds, False otherwise."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        print(f"[DB] Connection failed: {exc}")
        return False
