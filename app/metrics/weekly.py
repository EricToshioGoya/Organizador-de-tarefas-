"""Revisão semanal (RF51): concluídas, atrasadas e adiadas na semana, comparadas à semana anterior."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain import rules
from ..domain.models import Task
from ..domain.timeutil import local_date, parse_iso

COMPARED = ("done", "late", "postponed", "points")


def week_summary(tasks: Iterable[Task], week: date, tz: ZoneInfo) -> dict:
    """Atrasadas = entregas previstas na semana que não foram concluídas até a data de entrega."""
    tasks = list(tasks)
    end = week + timedelta(days=6)
    done = [
        t for t in tasks if t.is_done and t.completed_at is not None and week <= local_date(t.completed_at, tz) <= end
    ]
    late = [
        t
        for t in tasks
        if t.due_date is not None
        and week <= t.due_date <= end
        and (t.completed_at is None or not t.is_done or local_date(t.completed_at, tz) > t.due_date)
    ]
    postponed = []
    for task in tasks:
        for entry in task.due_history:
            when = parse_iso(entry.get("at"))
            if entry.get("kind") == "adiamento" and when is not None and week <= local_date(when, tz) <= end:
                postponed.append(task)
    return {
        "week_start": week.isoformat(),
        "week_end": end.isoformat(),
        "done": len(done),
        "late": len(late),
        "postponed": len(postponed),
        "points": sum(rules.points(t.difficulty) for t in done),
        "done_titles": [t.title for t in sorted(done, key=lambda t: t.completed_at)][:8],
        "late_titles": [t.title for t in late][:8],
        "postponed_titles": list(dict.fromkeys(t.title for t in postponed))[:8],
    }


def weekly_review(tasks: Iterable[Task], week: date, tz: ZoneInfo) -> dict:
    tasks = list(tasks)
    current = week_summary(tasks, week, tz)
    previous = week_summary(tasks, week - timedelta(days=7), tz)
    return {
        "week_start": current["week_start"],
        "week_end": current["week_end"],
        "current": current,
        "previous": previous,
        "delta": {key: current[key] - previous[key] for key in COMPARED},
    }
