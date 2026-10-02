"""Consultas às projeções, convertendo linhas em modelos de domínio."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Iterable

from ..domain.models import Account, Goal, Step, Task
from ..domain.timeutil import parse_date, parse_iso


def _json(value: str | None, default):
    if not value:
        return default
    return json.loads(value)


# ---------------------------------------------------------------------------
# Conversões
# ---------------------------------------------------------------------------


def account_from_row(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        name=row["name"],
        color=row["color"],
        role=row["role"],
        created_at=parse_iso(row["created_at"]),
        settings=_json(row["settings"], {}),
    )


def step_from_row(row: sqlite3.Row) -> Step:
    return Step(
        id=row["id"],
        text=row["text"],
        position=row["position"],
        done=bool(row["done"]),
        done_at=parse_iso(row["done_at"]),
        created_at=parse_iso(row["created_at"]),
    )


def task_from_row(row: sqlite3.Row, steps: list[Step] | None = None) -> Task:
    return Task(
        id=row["id"],
        account_id=row["account_id"],
        title=row["title"],
        created_at=parse_iso(row["created_at"]),
        difficulty=row["difficulty"],
        priority=row["priority"],
        description=row["description"],
        due_date=parse_date(row["due_date"]),
        requester=row["requester"],
        completed_at=parse_iso(row["completed_at"]),
        status=row["status"],
        goal_id=row["goal_id"],
        notes=row["notes"],
        links=_json(row["links"], []),
        phase=row["phase"],
        last_activity_at=parse_iso(row["last_activity_at"]),
        due_history=_json(row["due_history"], []),
        steps=sorted(steps or [], key=lambda s: (s.position, s.created_at)),
        assigned_by=row["assigned_by"],
        assigned_by_name=row["assigned_by_name"],
        assigned_seen_at=parse_iso(row["assigned_seen_at"]),
    )


def goal_from_row(row: sqlite3.Row) -> Goal:
    return Goal(
        id=row["id"],
        account_id=row["account_id"],
        title=row["title"],
        created_at=parse_iso(row["created_at"]),
        description=row["description"],
        target_date=parse_date(row["target_date"]),
        completed_at=parse_iso(row["completed_at"]),
        status=row["status"],
    )


# ---------------------------------------------------------------------------
# Contas
# ---------------------------------------------------------------------------


def get_account(conn: sqlite3.Connection, account_id: str | None) -> Account | None:
    if not account_id:
        return None
    row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return account_from_row(row) if row else None


def find_account_by_key(conn: sqlite3.Connection, key: str) -> Account | None:
    row = conn.execute("SELECT * FROM accounts WHERE name_key = ?", (key,)).fetchone()
    return account_from_row(row) if row else None


def list_accounts(conn: sqlite3.Connection) -> list[Account]:
    rows = conn.execute("SELECT * FROM accounts ORDER BY name COLLATE NOCASE").fetchall()
    return [account_from_row(r) for r in rows]


def account_colors(conn: sqlite3.Connection) -> list[str]:
    return [r["color"] for r in conn.execute("SELECT color FROM accounts")]


def account_counts(conn: sqlite3.Connection, today: date) -> dict[str, dict]:
    """Contadores da aba Equipe (RF34): pendentes, atrasadas e metas em andamento."""
    counts: dict[str, dict] = defaultdict(lambda: {"pending_tasks": 0, "overdue_tasks": 0, "active_goals": 0})
    for row in conn.execute(
        "SELECT account_id, COUNT(*) AS n, SUM(CASE WHEN due_date IS NOT NULL AND due_date < ? THEN 1 ELSE 0 END) AS late "
        "FROM tasks WHERE status = 'pendente' GROUP BY account_id",
        (today.isoformat(),),
    ):
        counts[row["account_id"]]["pending_tasks"] = row["n"]
        counts[row["account_id"]]["overdue_tasks"] = row["late"] or 0
    for row in conn.execute("SELECT account_id, COUNT(*) AS n FROM goals WHERE status = 'andamento' GROUP BY account_id"):
        counts[row["account_id"]]["active_goals"] = row["n"]
    return counts


# ---------------------------------------------------------------------------
# Tarefas e etapas
# ---------------------------------------------------------------------------


def _steps_for(conn: sqlite3.Connection, where: str, params: Iterable) -> dict[str, list[Step]]:
    by_task: dict[str, list[Step]] = defaultdict(list)
    for row in conn.execute(f"SELECT * FROM steps WHERE {where}", tuple(params)):
        by_task[row["task_id"]].append(step_from_row(row))
    return by_task


def get_task(conn: sqlite3.Connection, task_id: str | None) -> Task | None:
    if not task_id:
        return None
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    steps = _steps_for(conn, "task_id = ?", (task_id,)).get(task_id, [])
    return task_from_row(row, steps)


def list_tasks(conn: sqlite3.Connection, account_id: str) -> list[Task]:
    rows = conn.execute("SELECT * FROM tasks WHERE account_id = ?", (account_id,)).fetchall()
    steps = _steps_for(conn, "task_id IN (SELECT id FROM tasks WHERE account_id = ?)", (account_id,))
    return [task_from_row(r, steps.get(r["id"], [])) for r in rows]


def list_all_tasks(conn: sqlite3.Connection) -> list[Task]:
    rows = conn.execute("SELECT * FROM tasks").fetchall()
    steps = _steps_for(conn, "1 = 1", ())
    return [task_from_row(r, steps.get(r["id"], [])) for r in rows]


def list_goal_tasks(conn: sqlite3.Connection, goal_id: str) -> list[Task]:
    rows = conn.execute("SELECT * FROM tasks WHERE goal_id = ?", (goal_id,)).fetchall()
    steps = _steps_for(conn, "task_id IN (SELECT id FROM tasks WHERE goal_id = ?)", (goal_id,))
    return [task_from_row(r, steps.get(r["id"], [])) for r in rows]


def task_field_ts(conn: sqlite3.Connection, task_id: str) -> dict:
    row = conn.execute("SELECT field_ts FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _json(row["field_ts"], {}) if row else {}


def step_field_ts(conn: sqlite3.Connection, step_id: str) -> dict:
    row = conn.execute("SELECT field_ts FROM steps WHERE id = ?", (step_id,)).fetchone()
    return _json(row["field_ts"], {}) if row else {}


def goal_field_ts(conn: sqlite3.Connection, goal_id: str) -> dict:
    row = conn.execute("SELECT field_ts FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return _json(row["field_ts"], {}) if row else {}


def task_versions(conn: sqlite3.Connection, account_id: str) -> dict[str, int]:
    return {r["id"]: r["version"] for r in conn.execute("SELECT id, version FROM tasks WHERE account_id = ?", (account_id,))}


def list_requesters(conn: sqlite3.Connection, account_id: str) -> list[str]:
    """RF05: solicitantes já cadastrados na conta + nomes da equipe."""
    names: dict[str, str] = {}
    for row in conn.execute(
        "SELECT requester, MAX(created_at) AS last FROM tasks WHERE account_id = ? AND requester <> '' "
        "GROUP BY requester ORDER BY last DESC",
        (account_id,),
    ):
        names.setdefault(row["requester"].casefold(), row["requester"])
    for row in conn.execute("SELECT name FROM accounts ORDER BY name COLLATE NOCASE"):
        names.setdefault(row["name"].casefold(), row["name"])
    return list(names.values())


# ---------------------------------------------------------------------------
# Anexos e comentários
# ---------------------------------------------------------------------------


def attachments_by_task(conn: sqlite3.Connection, task_ids: list[str]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = defaultdict(list)
    if not task_ids:
        return result
    for chunk_start in range(0, len(task_ids), 500):
        chunk = task_ids[chunk_start : chunk_start + 500]
        marks = ",".join("?" * len(chunk))
        for row in conn.execute(
            f"SELECT * FROM attachments WHERE task_id IN ({marks}) ORDER BY created_at", chunk
        ):
            result[row["task_id"]].append(dict(row))
    return result


def get_attachment(conn: sqlite3.Connection, attachment_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    return dict(row) if row else None


def list_comments(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM comments WHERE task_id = ? ORDER BY created_at, id", (task_id,)).fetchall()
    return [dict(r) for r in rows]


def get_comment(conn: sqlite3.Connection, comment_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
    return dict(row) if row else None


def comment_stats(
    conn: sqlite3.Connection, viewer_id: str | None, account_id: str, task_id: str | None = None
) -> dict[str, dict]:
    """Total de comentários e não lidos (RF67) por tarefa da conta, do ponto de vista de `viewer_id`."""
    stats: dict[str, dict] = {}
    params: list = [viewer_id or "", viewer_id or "", account_id]
    task_filter = ""
    if task_id is not None:
        task_filter = " AND c.task_id = ?"
        params.append(task_id)
    rows = conn.execute(
        "SELECT c.task_id, COUNT(*) AS total, "
        "SUM(CASE WHEN c.author_id <> ? AND (r.read_at IS NULL OR c.created_at > r.read_at) THEN 1 ELSE 0 END) AS unread "
        "FROM comments c JOIN tasks t ON t.id = c.task_id "
        "LEFT JOIN comment_reads r ON r.task_id = c.task_id AND r.account_id = ? "
        f"WHERE t.account_id = ?{task_filter} GROUP BY c.task_id",
        params,
    )
    for row in rows:
        stats[row["task_id"]] = {"total": row["total"], "unread": row["unread"] or 0}
    return stats


def last_comment_read(conn: sqlite3.Connection, account_id: str, task_id: str) -> str | None:
    row = conn.execute(
        "SELECT read_at FROM comment_reads WHERE account_id = ? AND task_id = ?", (account_id, task_id)
    ).fetchone()
    return row["read_at"] if row else None


# ---------------------------------------------------------------------------
# Metas, templates, Top 3 e revisões
# ---------------------------------------------------------------------------


def get_goal(conn: sqlite3.Connection, goal_id: str | None) -> Goal | None:
    if not goal_id:
        return None
    row = conn.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
    return goal_from_row(row) if row else None


def list_goals(conn: sqlite3.Connection, account_id: str) -> list[Goal]:
    rows = conn.execute("SELECT * FROM goals WHERE account_id = ? ORDER BY created_at", (account_id,)).fetchall()
    return [goal_from_row(r) for r in rows]


def template_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["steps"] = _json(data["steps"], [])
    return data


def get_template(conn: sqlite3.Connection, template_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone()
    return template_from_row(row) if row else None


def list_templates(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM templates WHERE account_id = ? ORDER BY name COLLATE NOCASE", (account_id,)
    ).fetchall()
    return [template_from_row(r) for r in rows]


def get_top3(conn: sqlite3.Connection, account_id: str, day: date) -> list[str]:
    row = conn.execute(
        "SELECT task_ids FROM top3 WHERE account_id = ? AND day = ?", (account_id, day.isoformat())
    ).fetchone()
    return _json(row["task_ids"], []) if row else []


def get_weekly_review(conn: sqlite3.Connection, account_id: str, week_start: date) -> dict | None:
    row = conn.execute(
        "SELECT * FROM weekly_reviews WHERE account_id = ? AND week_start = ?",
        (account_id, week_start.isoformat()),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["summary"] = _json(data["summary"], {})
    return data


def list_weekly_reviews(conn: sqlite3.Connection, account_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM weekly_reviews WHERE account_id = ? ORDER BY week_start DESC", (account_id,)
    ).fetchall()
    result = []
    for row in rows:
        data = dict(row)
        data["summary"] = _json(data["summary"], {})
        result.append(data)
    return result


# ---------------------------------------------------------------------------
# Idempotência (RF71): respostas de mutações já processadas
# ---------------------------------------------------------------------------


def get_mutation(conn: sqlite3.Connection, mutation_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM mutations WHERE id = ?", (mutation_id,)).fetchone()
    return dict(row) if row else None


def save_mutation(conn: sqlite3.Connection, mutation_id: str, recorded_at: str, status: int, response: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO mutations(id, recorded_at, status, response) VALUES (?, ?, ?, ?)",
        (mutation_id, recorded_at, status, response),
    )
