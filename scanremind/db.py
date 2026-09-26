"""SQLite access and schema management."""

import sqlite3
from contextlib import closing

from flask import current_app, g

# Values of reminders.sent
STATUS_PENDING = 0
STATUS_SENT = 1
STATUS_FAILED = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    email TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    reminder_datetime TEXT NOT NULL,   -- next delivery time, UTC 'YYYY-MM-DD HH:MM'
    repeat TEXT NOT NULL DEFAULT 'none',
    sent INTEGER NOT NULL DEFAULT 0,   -- 0 pending, 1 sent, 2 failed
    timezone TEXT NOT NULL DEFAULT 'UTC',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_email ON reminders (email);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (sent, reminder_datetime);

CREATE TABLE IF NOT EXISTS otp_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_otp_email ON otp_codes (email);
"""

# Columns added after the first release. Databases created by older versions
# get them added automatically on startup, so no manual migration is needed.
_ADDED_COLUMNS = {
    "reminders": {
        "repeat": "TEXT NOT NULL DEFAULT 'none'",
        "timezone": "TEXT NOT NULL DEFAULT 'UTC'",
        "attempts": "INTEGER NOT NULL DEFAULT 0",
        "next_attempt_at": "TEXT",
        "last_error": "TEXT",
        "created_at": "TEXT",
    },
}


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_db() -> sqlite3.Connection:
    """Connection for the current request, closed automatically afterwards."""
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in _ADDED_COLUMNS.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def init_db(path: str) -> None:
    with closing(connect(path)) as conn:
        # Create the base table first so older databases can be migrated
        # before the indexes that depend on new columns are created.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "username TEXT NOT NULL, email TEXT NOT NULL, title TEXT NOT NULL, "
            "description TEXT NOT NULL, reminder_datetime TEXT NOT NULL, "
            "sent INTEGER NOT NULL DEFAULT 0)"
        )
        _migrate(conn)
        conn.executescript(SCHEMA)
        conn.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    init_db(app.config["DATABASE"])
