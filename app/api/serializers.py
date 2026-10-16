"""Conversão de modelos de domínio para JSON da API."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ..domain import rules
from ..domain.constants import PRIVATE_EVENT_COLOR, PRIVATE_EVENT_TITLE
from ..domain.models import Account, CalendarEntry, DailyItem, Goal, Task
from ..domain.timeutil import date_iso, local_date, to_iso
from ..metrics import capacity
from ..metrics.common import first_activity_day
from ..store import events, repo


def account_json(account: Account, counts: dict | None = None, *, own: bool = False) -> dict:
    data = {
        "id": account.id,
        "name": account.name,
        "initials": rules.initials(account.name),
        "color": account.color,
        "role": account.role,
        "created_at": to_iso(account.created_at),
    }
    if counts is not None:
        data.update(
            pending_tasks=counts.get("pending_tasks", 0),
            overdue_tasks=counts.get("overdue_tasks", 0),
            active_goals=counts.get("active_goals", 0),
        )
    if own:
        data["settings"] = rules.merge_settings(account.settings)
    return data


def task_json(task: Task, attachments: list[dict] | None = None, comments: dict | None = None) -> dict:
    return {
        "id": task.id,
        "account_id": task.account_id,
        "title": task.title,
        "description": task.description,
        "difficulty": task.difficulty,
        "priority": task.priority,
        "due_date": date_iso(task.due_date),
        "requester": task.requester,
        "created_at": to_iso(task.created_at),
        "completed_at": to_iso(task.completed_at),
        "status": task.status,
        "goal_id": task.goal_id,
        "notes": task.notes,
        "links": task.links,
        "phase": task.phase,
        "last_activity_at": to_iso(task.last_activity_at),
        "due_history": task.due_history,
        "assigned_by": task.assigned_by,
        "assigned_by_name": task.assigned_by_name,
        "assigned_seen_at": to_iso(task.assigned_seen_at),
        "progress": rules.progress(task),
        "steps": [
            {
                "id": s.id,
                "text": s.text,
                "done": s.done,
                "done_at": to_iso(s.done_at),
                "position": s.position,
            }
            for s in rules.ordered_steps(task.steps)
        ],
        "attachments": [
            {
                "id": a["id"],
                "filename": a["filename"],
                "content_type": a["content_type"],
                "size": a["size"],
                "created_at": a["created_at"],
            }
            for a in attachments or []
        ],
        "comments": comments,
    }


def goal_json(goal: Goal, tasks: list[Task], today: date) -> dict:
    linked = [t for t in tasks if t.goal_id == goal.id]
    return {
        "id": goal.id,
        "account_id": goal.account_id,
        "title": goal.title,
        "description": goal.description,
        "target_date": date_iso(goal.target_date),
        "created_at": to_iso(goal.created_at),
        "completed_at": to_iso(goal.completed_at),
        "status": goal.status,
        "progress": rules.goal_progress(linked),
        "done_tasks": sum(1 for t in linked if t.is_done),
        "total_tasks": len(linked),
        "overdue": rules.goal_is_overdue(goal, today),
    }


def template_json(template: dict) -> dict:
    return {
        "id": template["id"],
        "account_id": template["account_id"],
        "name": template["name"],
        "title": template["title"],
        "description": template["description"],
        "difficulty": template["difficulty"],
        "steps": template["steps"],
        "created_at": template["created_at"],
        "updated_at": template["updated_at"],
    }


def comment_json(comment: dict) -> dict:
    return {
        "id": comment["id"],
        "task_id": comment["task_id"],
        "author_id": comment["author_id"],
        "author_name": comment["author_name"],
        "text": comment["text"],
        "created_at": comment["created_at"],
        "edited_at": comment["edited_at"],
    }


def calendar_entry_json(entry: CalendarEntry, viewer: Account | None) -> dict:
    """Evento particular visto por outra conta mostra só o horário (não é controle de acesso — RN11)."""
    hidden = entry.private and not rules.can_edit(viewer, entry.account_id)
    return {
        "id": entry.id,
        "account_id": entry.account_id,
        "title": PRIVATE_EVENT_TITLE if hidden else entry.title,
        "notes": "" if hidden else entry.notes,
        "location": "" if hidden else entry.location,
        "all_day": entry.all_day,
        "start_date": date_iso(entry.start_date),
        "start_time": entry.start_time,
        "end_date": date_iso(entry.end_date),
        "end_time": entry.end_time,
        "color": PRIVATE_EVENT_COLOR if hidden else entry.color,
        "private": entry.private,
        "redacted": hidden,
        "recurrence": entry.recurrence,
        "exceptions": entry.exceptions,
        "created_at": to_iso(entry.created_at),
        "updated_at": to_iso(entry.updated_at),
    }


def daily_item_json(item: DailyItem) -> dict:
    return {
        "id": item.id,
        "account_id": item.account_id,
        "day": date_iso(item.day),
        "title": item.title,
        "note": item.note,
        "done": item.done,
        "done_at": to_iso(item.done_at),
        "created_at": to_iso(item.created_at),
        "updated_at": to_iso(item.updated_at),
    }


def task_payload(conn: sqlite3.Connection, task: Task, viewer: Account | None) -> dict:
    attachments = repo.attachments_by_task(conn, [task.id]).get(task.id, [])
    comments = None
    if rules.can_view_comments(viewer, task.account_id):
        comments = repo.comment_stats(conn, viewer.id if viewer else None, task.account_id, task.id).get(
            task.id, {"total": 0, "unread": 0}
        )
    return task_json(task, attachments, comments)


def board_json(conn: sqlite3.Connection, account: Account, viewer: Account | None, now: datetime, tz: ZoneInfo) -> dict:
    """Tudo o que a interface precisa para exibir uma conta (própria ou em modo somente leitura)."""
    own = viewer is not None and viewer.id == account.id
    today = local_date(now, tz)
    tasks = repo.list_tasks(conn, account.id)
    task_ids = {t.id for t in tasks}
    attachments = repo.attachments_by_task(conn, list(task_ids))
    can_comment = rules.can_view_comments(viewer, account.id)
    stats = repo.comment_stats(conn, viewer.id if viewer else None, account.id) if can_comment else {}
    counts = repo.account_counts(conn, today).get(account.id, {})
    return {
        "seq": events.max_seq(conn),
        "account": account_json(account, counts, own=own),
        "own": own,
        "can_comment": can_comment,
        "tasks": [
            task_json(t, attachments.get(t.id, []), stats.get(t.id, {"total": 0, "unread": 0}) if can_comment else None)
            for t in tasks
        ],
        "goals": [goal_json(g, tasks, today) for g in repo.list_goals(conn, account.id)],
        "templates": [template_json(t) for t in repo.list_templates(conn, account.id)] if own else [],
        "top3": {
            "day": today.isoformat(),
            "task_ids": [i for i in repo.get_top3(conn, account.id, today) if i in task_ids],
        },
        "requesters": repo.list_requesters(conn, account.id) if own else [],
        "overload": capacity.overload(tasks, today, tz, first_activity_day(tasks, tz)),
        "calendar": [calendar_entry_json(e, viewer) for e in repo.list_calendar_entries(conn, account.id)],
        "daily": [daily_item_json(i) for i in repo.list_daily_items(conn, account.id)],
    }
