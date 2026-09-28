"""Armazenamento de eventos imutáveis (RNF22): base da linha do tempo, da sincronização e das métricas."""

from __future__ import annotations

import json
import sqlite3
from typing import Iterator

EVENT_COLUMNS = (
    "id",
    "type",
    "aggregate",
    "aggregate_id",
    "account_id",
    "task_id",
    "actor_id",
    "actor_name",
    "occurred_at",
    "recorded_at",
    "mutation_id",
    "payload",
)


def dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def append_event(conn: sqlite3.Connection, event: dict) -> int:
    values = [event.get(col) for col in EVENT_COLUMNS]
    values[-1] = dumps(event.get("payload") or {})
    cur = conn.execute(
        f"INSERT INTO events({', '.join(EVENT_COLUMNS)}) VALUES ({', '.join('?' * len(EVENT_COLUMNS))})",
        values,
    )
    return int(cur.lastrowid)


def row_to_event(row: sqlite3.Row) -> dict:
    event = dict(row)
    event["payload"] = json.loads(event["payload"] or "{}")
    return event


def iter_events(conn: sqlite3.Connection, since: int = 0) -> Iterator[dict]:
    for row in conn.execute("SELECT * FROM events WHERE seq > ? ORDER BY seq", (since,)):
        yield row_to_event(row)


def task_events(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM events WHERE task_id = ? ORDER BY seq", (task_id,)).fetchall()
    return [row_to_event(r) for r in rows]


def max_seq(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM events").fetchone()
    return int(row["seq"])


def changes_since(conn: sqlite3.Connection, since: int) -> dict:
    """Resumo do que mudou desde `since` (RNF19): contas afetadas e se o diretório de contas mudou."""
    latest = max_seq(conn)
    if since >= latest:
        return {"seq": latest, "accounts": [], "directory": False}
    rows = conn.execute(
        "SELECT DISTINCT account_id, aggregate FROM events WHERE seq > ?",
        (since,),
    ).fetchall()
    accounts = sorted({r["account_id"] for r in rows if r["account_id"]})
    # Contagens exibidas na Equipe (RF34) mudam com qualquer tarefa ou meta.
    directory = any(r["aggregate"] in ("account", "task", "goal") for r in rows)
    return {"seq": latest, "accounts": accounts, "directory": directory}
