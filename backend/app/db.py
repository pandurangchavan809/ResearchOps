import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import Settings

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    credits_used INTEGER NOT NULL DEFAULT 0,
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    jti TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    family_id TEXT NOT NULL,
    expires_at INTEGER NOT NULL,
    rotated_at INTEGER,
    revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_refresh_family ON refresh_tokens(family_id);
"""

RESEARCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    question TEXT NOT NULL,
    title TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    credits_charged INTEGER NOT NULL DEFAULT 0,
    report_status TEXT NOT NULL DEFAULT 'none',
    report_title TEXT,
    report_path TEXT,
    report_count INTEGER NOT NULL DEFAULT 0,
    report_pages INTEGER,
    report_requested_pages INTEGER,
    source_texts_json TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_user ON runs(user_id, created_at DESC);
"""


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    """Open one short transaction. BEGIN IMMEDIATE makes read-then-write sequences atomic."""
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def init_databases(settings: Settings) -> None:
    settings.auth_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.research_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    for path, schema in ((settings.auth_db_path, AUTH_SCHEMA), (settings.research_db_path, RESEARCH_SCHEMA)):
        connection = sqlite3.connect(path)
        try:
            connection.executescript(schema)
        finally:
            connection.close()
    _add_missing_run_columns(settings.research_db_path)


def _add_missing_run_columns(path: Path) -> None:
    """Bring research.db files created by earlier versions up to date."""
    connection = sqlite3.connect(path)
    try:
        existing = {row[1] for row in connection.execute("PRAGMA table_info(runs)")}
        for name, kind in (("report_pages", "INTEGER"), ("report_requested_pages", "INTEGER"), ("source_texts_json", "TEXT")):
            if name not in existing:
                connection.execute(f"ALTER TABLE runs ADD COLUMN {name} {kind}")
        connection.commit()
    finally:
        connection.close()
