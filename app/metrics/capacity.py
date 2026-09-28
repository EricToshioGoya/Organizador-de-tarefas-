"""Carga × capacidade (RN24, RN25, RF50, G10)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain import rules
from ..domain.models import Task
from ..domain.timeutil import local_date, week_end, week_start

CAPACITY_WEEKS = 4
CAPACITY_MIN_WEEKS = 2
HISTORY_WEEKS = 8
FUTURE_WEEKS = 4


def weekly_done_points(tasks: Iterable[Task], tz: ZoneInfo) -> dict[date, int]:
    points: dict[date, int] = defaultdict(int)
    for task in tasks:
        if task.is_done and task.completed_at is not None:
            points[week_start(local_date(task.completed_at, tz))] += rules.points(task.difficulty)
    return points


def complete_weeks_available(first_day: date | None, today: date) -> int:
    if first_day is None:
        return 0
    return max(0, (week_start(today) - week_start(first_day)).days // 7)


def capacity(tasks: list[Task], today: date, tz: ZoneInfo, first_day: date | None) -> dict:
    """Média de pontos concluídos por semana nas últimas 4 semanas completas (mínimo de 2)."""
    weeks_available = complete_weeks_available(first_day, today)
    weeks_used = min(CAPACITY_WEEKS, weeks_available)
    if weeks_used < CAPACITY_MIN_WEEKS:
        return {"value": None, "weeks": weeks_used, "min_weeks": CAPACITY_MIN_WEEKS}
    current = week_start(today)
    points = weekly_done_points(tasks, tz)
    total = sum(points.get(current - timedelta(days=7 * (i + 1)), 0) for i in range(weeks_used))
    return {"value": round(total / weeks_used, 2), "weeks": weeks_used, "min_weeks": CAPACITY_MIN_WEEKS}


def current_load(tasks: Iterable[Task], today: date) -> int:
    """Pontos das pendentes com entrega até o fim da semana corrente, incluídas as atrasadas."""
    limit = week_end(today)
    return sum(
        rules.points(t.difficulty) for t in tasks if t.is_pending and t.due_date is not None and t.due_date <= limit
    )


def overload(tasks: list[Task], today: date, tz: ZoneInfo, first_day: date | None) -> dict:
    cap = capacity(tasks, today, tz, first_day)
    load = current_load(tasks, today)
    return {
        "load": load,
        "capacity": cap["value"],
        "capacity_weeks": cap["weeks"],
        "overloaded": cap["value"] is not None and load > cap["value"],
    }


def chart_load_capacity(tasks: list[Task], today: date, tz: ZoneInfo, first_day: date | None) -> dict:
    """G10: pontos concluídos nas semanas passadas e carga das semanas corrente e seguintes."""
    current = week_start(today)
    past = [current - timedelta(days=7 * k) for k in range(HISTORY_WEEKS, 0, -1)]
    upcoming = [current + timedelta(days=7 * k) for k in range(0, FUTURE_WEEKS + 1)]
    done_points = weekly_done_points(tasks, tz)

    load_by_week: dict[date, int] = defaultdict(int)
    for task in tasks:
        if task.is_pending and task.due_date is not None:
            bucket = max(week_start(task.due_date), current)  # atrasadas contam na semana corrente
            load_by_week[bucket] += rules.points(task.difficulty)

    status = overload(tasks, today, tz, first_day)
    return {
        "weeks": [w.isoformat() for w in past + upcoming],
        "current_index": len(past),
        "done": [done_points.get(w, 0) for w in past] + [None] * len(upcoming),
        "load": [None] * len(past) + [load_by_week.get(w, 0) for w in upcoming],
        "current_load": status["load"],
        "capacity": status["capacity"],
        "capacity_weeks": status["capacity_weeks"],
        "overloaded": status["overloaded"],
    }
