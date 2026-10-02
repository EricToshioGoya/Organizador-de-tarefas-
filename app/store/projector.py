"""Projeções: aplicam eventos às tabelas de leitura.

Cada handler depende apenas do evento — assim as projeções podem ser reconstruídas do zero
(`rebuild_projections`) e as regras de negócio ficam no domínio/serviços, não aqui.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable

from .db import PROJECTION_TABLES
from .events import dumps, iter_events

Handler = Callable[[sqlite3.Connection, dict, dict], None]
HANDLERS: dict[str, Handler] = {}

TASK_TEXT_FIELDS = {"title", "description", "difficulty", "priority", "requester", "notes", "links"}
GOAL_FIELDS = {"title", "description", "target_date"}
TEMPLATE_FIELDS = {"name", "title", "description", "difficulty", "steps"}


def handles(*types: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        for event_type in types:
            HANDLERS[event_type] = fn
        return fn

    return register


def apply_event(conn: sqlite3.Connection, event: dict) -> None:
    handler = HANDLERS.get(event["type"])
    if handler is not None:
        handler(conn, event, event.get("payload") or {})


def rebuild_projections(conn: sqlite3.Connection) -> int:
    """Apaga as projeções e reaplica todos os eventos (recálculo a partir do histórico)."""
    for table in PROJECTION_TABLES:
        conn.execute(f"DELETE FROM {table}")
    count = 0
    for event in iter_events(conn):
        apply_event(conn, event)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _merge_field_ts(conn: sqlite3.Connection, table: str, row_id: str, fields, ts: str) -> None:
    row = conn.execute(f"SELECT field_ts FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        return
    stamps = json.loads(row["field_ts"] or "{}")
    for name in fields:
        if ts >= stamps.get(name, ""):
            stamps[name] = ts
    conn.execute(f"UPDATE {table} SET field_ts = ? WHERE id = ?", (dumps(stamps), row_id))


def _touch_task(conn: sqlite3.Connection, event: dict, *, activity: bool = True) -> None:
    """Versão da tarefa (sincronização) e última atividade (RN22)."""
    if not event.get("task_id"):
        return
    if activity:
        conn.execute(
            "UPDATE tasks SET version = ?, last_activity_at = MAX(last_activity_at, ?) WHERE id = ?",
            (event["seq"], event["occurred_at"], event["task_id"]),
        )
    else:
        conn.execute("UPDATE tasks SET version = ? WHERE id = ?", (event["seq"], event["task_id"]))


def _delete_task_rows(conn: sqlite3.Connection, task_ids: list[str]) -> None:
    if not task_ids:
        return
    marks = ",".join("?" * len(task_ids))
    for table in ("steps", "attachments", "comments", "comment_reads"):
        conn.execute(f"DELETE FROM {table} WHERE task_id IN ({marks})", task_ids)
    conn.execute(f"DELETE FROM tasks WHERE id IN ({marks})", task_ids)


# ---------------------------------------------------------------------------
# Contas
# ---------------------------------------------------------------------------


@handles("ContaCriada")
def _account_created(conn, ev, p):
    conn.execute(
        "INSERT INTO accounts(id, name, name_key, color, role, created_at, settings, version) "
        "VALUES (?, ?, ?, ?, ?, ?, '{}', ?)",
        (ev["aggregate_id"], p["name"], p["name_key"], p["color"], p.get("role", "membro"), ev["occurred_at"], ev["seq"]),
    )


@handles("ContaRenomeada")
def _account_renamed(conn, ev, p):
    conn.execute(
        "UPDATE accounts SET name = ?, name_key = ?, version = ? WHERE id = ?",
        (p["name"], p["name_key"], ev["seq"], ev["aggregate_id"]),
    )


@handles("PerfilAlterado")
def _role_changed(conn, ev, p):
    conn.execute("UPDATE accounts SET role = ?, version = ? WHERE id = ?", (p["role"], ev["seq"], ev["aggregate_id"]))


@handles("ConfiguracoesAlteradas")
def _settings_changed(conn, ev, p):
    row = conn.execute("SELECT settings FROM accounts WHERE id = ?", (ev["aggregate_id"],)).fetchone()
    if row is None:
        return
    settings = json.loads(row["settings"] or "{}")
    settings.update(p.get("changes") or {})
    conn.execute(
        "UPDATE accounts SET settings = ?, version = ? WHERE id = ?",
        (dumps(settings), ev["seq"], ev["aggregate_id"]),
    )


@handles("ContaExcluida")
def _account_deleted(conn, ev, p):
    """RN13: a exclusão da conta leva junto tarefas, metas e templates."""
    account_id = ev["aggregate_id"]
    task_ids = [r["id"] for r in conn.execute("SELECT id FROM tasks WHERE account_id = ?", (account_id,))]
    _delete_task_rows(conn, task_ids)
    for table in ("goals", "templates", "top3", "weekly_reviews", "comment_reads"):
        conn.execute(f"DELETE FROM {table} WHERE account_id = ?", (account_id,))
    conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


# ---------------------------------------------------------------------------
# Tarefas
# ---------------------------------------------------------------------------


@handles("TarefaCriada")
def _task_created(conn, ev, p):
    ts = ev["occurred_at"]
    stamps = {name: ts for name in ("title", "description", "difficulty", "priority", "requester", "notes", "links", "due_date", "phase", "goal_id", "status")}
    conn.execute(
        "INSERT INTO tasks(id, account_id, title, description, difficulty, priority, due_date, requester, created_at, "
        "completed_at, status, goal_id, notes, links, phase, last_activity_at, due_history, assigned_by, "
        "assigned_by_name, assigned_seen_at, field_ts, version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pendente', ?, ?, ?, ?, ?, '[]', ?, ?, NULL, ?, ?)",
        (
            ev["aggregate_id"],
            ev["account_id"],
            p["title"],
            p.get("description", ""),
            p["difficulty"],
            p.get("priority", "media"),  # eventos anteriores à prioridade
            p.get("due_date"),
            p.get("requester", ""),
            ts,
            p.get("goal_id"),
            p.get("notes", ""),
            dumps(p.get("links") or []),
            p["phase"],
            ts,
            p.get("assigned_by"),
            p.get("assigned_by_name"),
            dumps(stamps),
            ev["seq"],
        ),
    )
    for step in p.get("steps") or []:
        conn.execute(
            "INSERT INTO steps(id, task_id, position, text, done, done_at, created_at, field_ts) "
            "VALUES (?, ?, ?, ?, 0, NULL, ?, '{}')",
            (step["id"], ev["aggregate_id"], step["position"], step["text"], ts),
        )


@handles("TarefaEditada")
def _task_edited(conn, ev, p):
    changes = {k: v for k, v in (p.get("changes") or {}).items() if k in TASK_TEXT_FIELDS}
    for field, change in changes.items():
        value = change.get("new")
        if field == "links":
            value = dumps(value or [])
        conn.execute(f"UPDATE tasks SET {field} = ? WHERE id = ?", (value, ev["task_id"]))
    _merge_field_ts(conn, "tasks", ev["task_id"], changes.keys(), ev["occurred_at"])
    _touch_task(conn, ev)


@handles("PrazoAlterado")
def _due_changed(conn, ev, p):
    row = conn.execute("SELECT due_history FROM tasks WHERE id = ?", (ev["task_id"],)).fetchone()
    if row is None:
        return
    history = json.loads(row["due_history"] or "[]")
    history.append(
        {
            "at": ev["occurred_at"],
            "old": p.get("old"),
            "new": p.get("new"),
            "kind": p.get("kind"),
            "reason": p.get("reason"),
            "reason_text": p.get("reason_text", ""),
            "actor_name": ev.get("actor_name"),
        }
    )
    conn.execute(
        "UPDATE tasks SET due_date = ?, due_history = ? WHERE id = ?",
        (p.get("new"), dumps(history), ev["task_id"]),
    )
    _merge_field_ts(conn, "tasks", ev["task_id"], ["due_date"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("FaseAlterada")
def _phase_changed(conn, ev, p):
    conn.execute("UPDATE tasks SET phase = ? WHERE id = ?", (p["new"], ev["task_id"]))
    _merge_field_ts(conn, "tasks", ev["task_id"], ["phase"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("MetaVinculada")
def _goal_linked(conn, ev, p):
    conn.execute("UPDATE tasks SET goal_id = ? WHERE id = ?", (p["goal_id"], ev["task_id"]))
    _merge_field_ts(conn, "tasks", ev["task_id"], ["goal_id"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("MetaDesvinculada")
def _goal_unlinked(conn, ev, p):
    conn.execute("UPDATE tasks SET goal_id = NULL WHERE id = ?", (ev["task_id"],))
    _merge_field_ts(conn, "tasks", ev["task_id"], ["goal_id"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("TarefaConcluida")
def _task_done(conn, ev, p):
    conn.execute(
        "UPDATE tasks SET status = 'concluida', completed_at = ? WHERE id = ?",
        (ev["occurred_at"], ev["task_id"]),
    )
    if not p.get("auto"):
        _merge_field_ts(conn, "tasks", ev["task_id"], ["status"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("TarefaReaberta")
def _task_reopened(conn, ev, p):
    conn.execute("UPDATE tasks SET status = 'pendente', completed_at = NULL WHERE id = ?", (ev["task_id"],))
    if not p.get("auto"):
        _merge_field_ts(conn, "tasks", ev["task_id"], ["status"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("TarefaExcluida")
def _task_deleted(conn, ev, p):
    _delete_task_rows(conn, [ev["task_id"]])


@handles("AtribuicaoVisualizada")
def _assignment_seen(conn, ev, p):
    conn.execute(
        "UPDATE tasks SET assigned_seen_at = COALESCE(assigned_seen_at, ?) WHERE id = ?",
        (ev["occurred_at"], ev["task_id"]),
    )
    _touch_task(conn, ev, activity=False)


# ---------------------------------------------------------------------------
# Etapas
# ---------------------------------------------------------------------------


@handles("EtapaAdicionada")
def _step_added(conn, ev, p):
    conn.execute(
        "INSERT INTO steps(id, task_id, position, text, done, done_at, created_at, field_ts) "
        "VALUES (?, ?, ?, ?, 0, NULL, ?, ?)",
        (p["step_id"], ev["task_id"], p["position"], p["text"], ev["occurred_at"], dumps({"text": ev["occurred_at"], "done": ev["occurred_at"]})),
    )
    _touch_task(conn, ev)


@handles("EtapaEditada")
def _step_edited(conn, ev, p):
    conn.execute("UPDATE steps SET text = ? WHERE id = ?", (p["text"], p["step_id"]))
    _merge_field_ts(conn, "steps", p["step_id"], ["text"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("EtapaConcluida")
def _step_done(conn, ev, p):
    conn.execute("UPDATE steps SET done = 1, done_at = ? WHERE id = ?", (ev["occurred_at"], p["step_id"]))
    _merge_field_ts(conn, "steps", p["step_id"], ["done"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("EtapaDesmarcada")
def _step_undone(conn, ev, p):
    conn.execute("UPDATE steps SET done = 0, done_at = NULL WHERE id = ?", (p["step_id"],))
    _merge_field_ts(conn, "steps", p["step_id"], ["done"], ev["occurred_at"])
    _touch_task(conn, ev)


@handles("EtapaRemovida")
def _step_removed(conn, ev, p):
    conn.execute("DELETE FROM steps WHERE id = ?", (p["step_id"],))
    _touch_task(conn, ev)


@handles("EtapasReordenadas")
def _steps_reordered(conn, ev, p):
    for index, step_id in enumerate(p.get("order") or []):
        conn.execute("UPDATE steps SET position = ? WHERE id = ? AND task_id = ?", (index, step_id, ev["task_id"]))
    _merge_field_ts(conn, "tasks", ev["task_id"], ["order"], ev["occurred_at"])
    _touch_task(conn, ev)


# ---------------------------------------------------------------------------
# Anexos
# ---------------------------------------------------------------------------


@handles("AnexoAdicionado")
def _attachment_added(conn, ev, p):
    conn.execute(
        "INSERT INTO attachments(id, task_id, filename, content_type, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (p["attachment_id"], ev["task_id"], p["filename"], p["content_type"], p["size"], ev["occurred_at"]),
    )
    _touch_task(conn, ev)


@handles("AnexoRemovido")
def _attachment_removed(conn, ev, p):
    conn.execute("DELETE FROM attachments WHERE id = ?", (p["attachment_id"],))
    _touch_task(conn, ev)


# ---------------------------------------------------------------------------
# Comentários (RF66–RF68)
# ---------------------------------------------------------------------------


@handles("ComentarioAdicionado")
def _comment_added(conn, ev, p):
    conn.execute(
        "INSERT INTO comments(id, task_id, author_id, author_name, text, created_at, edited_at) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (p["comment_id"], ev["task_id"], ev["actor_id"], p.get("author_name") or ev.get("actor_name") or "", p["text"], ev["occurred_at"]),
    )
    _touch_task(conn, ev, activity=False)


@handles("ComentarioEditado")
def _comment_edited(conn, ev, p):
    conn.execute("UPDATE comments SET text = ?, edited_at = ? WHERE id = ?", (p["text"], ev["occurred_at"], p["comment_id"]))
    _touch_task(conn, ev, activity=False)


@handles("ComentarioExcluido")
def _comment_deleted(conn, ev, p):
    conn.execute("DELETE FROM comments WHERE id = ?", (p["comment_id"],))
    _touch_task(conn, ev, activity=False)


@handles("ComentariosLidos")
def _comments_read(conn, ev, p):
    conn.execute(
        "INSERT INTO comment_reads(account_id, task_id, read_at) VALUES (?, ?, ?) "
        "ON CONFLICT(account_id, task_id) DO UPDATE SET read_at = MAX(read_at, excluded.read_at)",
        (ev["actor_id"], ev["task_id"], p.get("read_at") or ev["occurred_at"]),
    )


# ---------------------------------------------------------------------------
# Metas (RN14–RN17)
# ---------------------------------------------------------------------------


@handles("MetaCriada")
def _goal_created(conn, ev, p):
    ts = ev["occurred_at"]
    conn.execute(
        "INSERT INTO goals(id, account_id, title, description, target_date, created_at, completed_at, status, field_ts, version) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, 'andamento', ?, ?)",
        (
            ev["aggregate_id"],
            ev["account_id"],
            p["title"],
            p.get("description", ""),
            p.get("target_date"),
            ts,
            dumps({"title": ts, "description": ts, "target_date": ts}),
            ev["seq"],
        ),
    )


@handles("MetaEditada")
def _goal_edited(conn, ev, p):
    changes = {k: v for k, v in (p.get("changes") or {}).items() if k in GOAL_FIELDS}
    for field, change in changes.items():
        conn.execute(f"UPDATE goals SET {field} = ?, version = ? WHERE id = ?", (change.get("new"), ev["seq"], ev["aggregate_id"]))
    _merge_field_ts(conn, "goals", ev["aggregate_id"], changes.keys(), ev["occurred_at"])


@handles("MetaConcluida")
def _goal_done(conn, ev, p):
    conn.execute(
        "UPDATE goals SET status = 'concluida', completed_at = ?, version = ? WHERE id = ?",
        (ev["occurred_at"], ev["seq"], ev["aggregate_id"]),
    )


@handles("MetaReaberta")
def _goal_reopened(conn, ev, p):
    conn.execute(
        "UPDATE goals SET status = 'andamento', completed_at = NULL, version = ? WHERE id = ?",
        (ev["seq"], ev["aggregate_id"]),
    )


@handles("MetaExcluida")
def _goal_deleted(conn, ev, p):
    # RN17: as tarefas permanecem, sem meta.
    conn.execute("UPDATE tasks SET goal_id = NULL WHERE goal_id = ?", (ev["aggregate_id"],))
    conn.execute("DELETE FROM goals WHERE id = ?", (ev["aggregate_id"],))


# ---------------------------------------------------------------------------
# Templates (RF42, RF43)
# ---------------------------------------------------------------------------


@handles("TemplateCriado")
def _template_created(conn, ev, p):
    conn.execute(
        "INSERT INTO templates(id, account_id, name, title, description, difficulty, steps, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ev["aggregate_id"],
            ev["account_id"],
            p["name"],
            p["title"],
            p.get("description", ""),
            p["difficulty"],
            dumps(p.get("steps") or []),
            ev["occurred_at"],
            ev["occurred_at"],
        ),
    )


@handles("TemplateEditado")
def _template_edited(conn, ev, p):
    changes = {k: v for k, v in (p.get("changes") or {}).items() if k in TEMPLATE_FIELDS}
    for field, change in changes.items():
        value = change.get("new")
        if field == "steps":
            value = dumps(value or [])
        conn.execute(f"UPDATE templates SET {field} = ?, updated_at = ? WHERE id = ?", (value, ev["occurred_at"], ev["aggregate_id"]))


@handles("TemplateExcluido")
def _template_deleted(conn, ev, p):
    conn.execute("DELETE FROM templates WHERE id = ?", (ev["aggregate_id"],))


# ---------------------------------------------------------------------------
# Top 3 (RN18) e revisão semanal (RF51)
# ---------------------------------------------------------------------------


@handles("Top3Definido")
def _top3_set(conn, ev, p):
    conn.execute(
        "INSERT INTO top3(account_id, day, task_ids) VALUES (?, ?, ?) "
        "ON CONFLICT(account_id, day) DO UPDATE SET task_ids = excluded.task_ids",
        (ev["account_id"], p["day"], dumps(p.get("task_ids") or [])),
    )


@handles("RevisaoSemanalGerada")
def _review_generated(conn, ev, p):
    conn.execute(
        "INSERT OR IGNORE INTO weekly_reviews(account_id, week_start, summary, created_at, seen_at) VALUES (?, ?, ?, ?, NULL)",
        (ev["account_id"], p["week_start"], dumps(p.get("summary") or {}), ev["occurred_at"]),
    )


@handles("RevisaoSemanalVista")
def _review_seen(conn, ev, p):
    conn.execute(
        "UPDATE weekly_reviews SET seen_at = COALESCE(seen_at, ?) WHERE account_id = ? AND week_start = ?",
        (ev["occurred_at"], ev["account_id"], p["week_start"]),
    )
