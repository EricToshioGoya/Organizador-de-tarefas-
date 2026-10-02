"""Conexões SQLite, esquema e transações de escrita."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 2

# Eventos (fonte da verdade) + projeções (modelos de leitura reconstruíveis a partir dos eventos).
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    aggregate TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    account_id TEXT,
    task_id TEXT,
    actor_id TEXT,
    actor_name TEXT,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    mutation_id TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_task ON events(task_id, seq);
CREATE INDEX IF NOT EXISTS ix_events_account ON events(account_id, seq);
CREATE INDEX IF NOT EXISTS ix_events_aggregate ON events(aggregate, aggregate_id, seq);

-- Imutabilidade garantida pelo banco: eventos não podem ser alterados nem apagados.
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'eventos sao imutaveis'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'eventos sao imutaveis'); END;

CREATE TABLE IF NOT EXISTS mutations (
    id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    status INTEGER NOT NULL,
    response TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'membro',
    created_at TEXT NOT NULL,
    settings TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'media',
    due_date TEXT,
    requester TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    goal_id TEXT,
    notes TEXT NOT NULL DEFAULT '',
    links TEXT NOT NULL DEFAULT '[]',
    phase TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    due_history TEXT NOT NULL DEFAULT '[]',
    assigned_by TEXT,
    assigned_by_name TEXT,
    assigned_seen_at TEXT,
    field_ts TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_tasks_account ON tasks(account_id);
CREATE INDEX IF NOT EXISTS ix_tasks_goal ON tasks(goal_id);

CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    position REAL NOT NULL,
    text TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    created_at TEXT NOT NULL,
    field_ts TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_steps_task ON steps(task_id);

CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attachments_task ON attachments(task_id);

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    target_date TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    field_ts TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_goals_account ON goals(account_id);

CREATE TABLE IF NOT EXISTS templates (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    name TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL,
    steps TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_templates_account ON templates(account_id);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    edited_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_comments_task ON comments(task_id, created_at);

CREATE TABLE IF NOT EXISTS comment_reads (
    account_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    read_at TEXT NOT NULL,
    PRIMARY KEY (account_id, task_id)
);

CREATE TABLE IF NOT EXISTS top3 (
    account_id TEXT NOT NULL,
    day TEXT NOT NULL,
    task_ids TEXT NOT NULL,
    PRIMARY KEY (account_id, day)
);

CREATE TABLE IF NOT EXISTS weekly_reviews (
    account_id TEXT NOT NULL,
    week_start TEXT NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    seen_at TEXT,
    PRIMARY KEY (account_id, week_start)
);

-- Operacional (não é estado de domínio): controle de envio do resumo diário (RF56).
CREATE TABLE IF NOT EXISTS digest_log (
    account_id TEXT NOT NULL,
    day TEXT NOT NULL,
    channel TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (account_id, day, channel)
);
"""

PROJECTION_TABLES = (
    "accounts",
    "tasks",
    "steps",
    "attachments",
    "goals",
    "templates",
    "comments",
    "comment_reads",
    "top3",
    "weekly_reviews",
)

WRITE_LOCK = threading.RLock()


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Colunas novas em bancos criados por versões anteriores (o CREATE TABLE IF NOT EXISTS não as adiciona)."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    if "priority" not in columns:
        conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'media'")


def init_db(path: Path | str) -> None:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    finally:
        conn.close()


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Transação de escrita serializada: eventos e projeções gravados atomicamente."""
    with WRITE_LOCK:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        else:
            conn.execute("COMMIT")
