"""Dashboard de desempenho: KPIs (RF17), gráficos G1–G12 (seção 2.6) e drill-down (RF21)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain import rules
from ..domain.constants import DIFFICULTIES, DIFFICULTY_LABELS, PHASE_LABELS, PHASES, POSTPONE_REASONS
from ..domain.models import Goal, Task
from ..domain.rules import DomainError
from ..domain.timeutil import local_date, parse_iso, week_start
from . import capacity, forecast
from .common import Period, done_in, first_activity_day, period_for, period_scope

WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
NO_REQUESTER = "Sem solicitante"
MAX_REQUESTERS = 12


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


# ---------------------------------------------------------------------------
# KPIs (RF17)
# ---------------------------------------------------------------------------


def _period_indicators(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    done = [t for t in tasks if done_in(t, period, tz)]
    with_due = [t for t in done if t.due_date is not None]
    durations = [d for d in (rules.completion_days(t) for t in done) if d is not None]
    return {
        "done": len(done),
        "on_time_pct": _round(rules.on_time_rate(done, tz)),
        "on_time_base": len(with_due),
        "avg_completion_days": _round(mean(durations)) if durations else None,
    }


def kpis(tasks: list[Task], period: Period, today: date, now: datetime, tz: ZoneInfo, stale_days: int) -> dict:
    pending = [t for t in tasks if t.is_pending]
    result = {
        "pending": len(pending),
        "overdue": sum(1 for t in pending if rules.is_overdue(t, today)),
        "due_soon": sum(1 for t in pending if rules.is_due_soon(t, today)),
        "stale": sum(1 for t in pending if rules.is_stale(t, now, stale_days)),
        **_period_indicators(tasks, period, tz),
    }
    previous = period.previous()
    result["previous"] = _period_indicators(tasks, previous, tz) if previous else None
    return result


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------


def chart_created_done(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G1: criadas × concluídas por dia ou semana, com o backlog ao fim de cada intervalo."""
    buckets = period.buckets()
    index = {b: i for i, b in enumerate(buckets)}
    created = [0] * len(buckets)
    done = [0] * len(buckets)
    backlog_start = 0
    for task in tasks:
        created_day = local_date(task.created_at, tz)
        done_day = local_date(task.completed_at, tz) if task.is_done and task.completed_at else None
        if period.contains(created_day):
            created[index[period.bucket_of(created_day)]] += 1
        elif created_day < period.start and (done_day is None or done_day >= period.start):
            backlog_start += 1
        if done_day is not None and period.contains(done_day):
            done[index[period.bucket_of(done_day)]] += 1
    backlog, running = [], backlog_start
    for c, d in zip(created, done):
        running += c - d
        backlog.append(running)
    return {
        "granularity": period.granularity,
        "labels": [b.isoformat() for b in buckets],
        "created": created,
        "done": done,
        "backlog": backlog,
    }


def chart_difficulty(scope: list[Task]) -> dict:
    """G2: quantidade de tarefas por nível (donut com total no centro)."""
    counts = Counter(t.difficulty for t in scope)
    return {
        "items": [{"key": d, "label": DIFFICULTY_LABELS[d], "value": counts.get(d, 0)} for d in DIFFICULTIES],
        "total": len(scope),
    }


def chart_on_time(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G3: % de tarefas concluídas até a data de entrega (RN07, RN08)."""
    flags = [rules.completed_on_time(t, tz) for t in tasks if done_in(t, period, tz)]
    flags = [f for f in flags if f is not None]
    on_time = sum(flags)
    return {
        "value": _round(on_time * 100 / len(flags)) if flags else None,
        "on_time": on_time,
        "late": len(flags) - on_time,
        "base": len(flags),
    }


def _requester_key(task: Task) -> str:
    return task.requester.strip() or NO_REQUESTER


def chart_requesters(tasks: list[Task], period: Period, today: date, tz: ZoneInfo) -> dict:
    """G4: concluídas (no período), pendentes e atrasadas por solicitante."""
    groups: dict[str, dict] = defaultdict(lambda: {"done": 0, "pending": 0, "overdue": 0})
    names: dict[str, str] = {}
    for task in tasks:
        name = _requester_key(task)
        key = rules.normalize_for_match(name)
        names.setdefault(key, name)
        if task.is_pending:
            groups[key]["overdue" if rules.is_overdue(task, today) else "pending"] += 1
        elif done_in(task, period, tz):
            groups[key]["done"] += 1
    items = [
        {"key": key, "requester": names[key], **values, "total": sum(values.values())}
        for key, values in groups.items()
        if sum(values.values()) > 0
    ]
    items.sort(key=lambda i: (-i["total"], i["requester"].casefold()))
    return {"items": items[:MAX_REQUESTERS], "hidden": max(0, len(items) - MAX_REQUESTERS)}


def _steps_done(tasks: Iterable[Task], period: Period, tz: ZoneInfo):
    for task in tasks:
        for step in task.steps:
            if step.done and step.done_at is not None:
                day = local_date(step.done_at, tz)
                if period.contains(day):
                    yield task, day


def chart_heatmap(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G5: etapas concluídas por dia (heatmap de calendário)."""
    counts = Counter(day for _, day in _steps_done(tasks, period, tz))
    return {
        "start": period.start.isoformat(),
        "end": period.end.isoformat(),
        "days": [[d.isoformat(), n] for d, n in sorted(counts.items())],
        "max": max(counts.values(), default=0),
        "total": sum(counts.values()),
    }


def chart_completion_time(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G6: dias entre criação e conclusão, por nível (RN09)."""
    durations: dict[str, list[float]] = defaultdict(list)
    for task in tasks:
        if done_in(task, period, tz):
            days = rules.completion_days(task)
            if days is not None:
                durations[task.difficulty].append(days)
    return {
        "items": [
            {
                "key": d,
                "label": DIFFICULTY_LABELS[d],
                "avg_days": _round(mean(durations[d])) if durations[d] else None,
                "count": len(durations[d]),
            }
            for d in DIFFICULTIES
        ]
    }


def chart_weekdays(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G7: etapas concluídas por dia da semana (radar)."""
    counts = Counter(day.weekday() for _, day in _steps_done(tasks, period, tz))
    return {"labels": WEEKDAY_LABELS, "values": [counts.get(i, 0) for i in range(7)]}


def chart_goals(goals: list[Goal], tasks: list[Task], period: Period, today: date, tz: ZoneInfo) -> dict:
    """G8: % de tarefas concluídas por meta (em andamento + concluídas no período)."""
    by_goal: dict[str, list[Task]] = defaultdict(list)
    for task in tasks:
        if task.goal_id:
            by_goal[task.goal_id].append(task)
    items = []
    for goal in goals:
        if goal.is_done and not (goal.completed_at and period.contains(local_date(goal.completed_at, tz))):
            continue
        linked = by_goal.get(goal.id, [])
        items.append(
            {
                "id": goal.id,
                "title": goal.title,
                "progress": rules.goal_progress(linked),
                "done": sum(1 for t in linked if t.is_done),
                "total": len(linked),
                "status": goal.status,
                "overdue": rules.goal_is_overdue(goal, today),
                "target_date": goal.target_date.isoformat() if goal.target_date else None,
            }
        )
    items.sort(key=lambda g: (g["status"] != "andamento", g["target_date"] or "9999", g["title"].casefold()))
    return {"items": items}


def _postponements(tasks: Iterable[Task], period: Period, tz: ZoneInfo):
    for task in tasks:
        for entry in task.due_history:
            when = parse_iso(entry.get("at"))
            if entry.get("kind") == "adiamento" and when is not None and period.contains(local_date(when, tz)):
                yield task, entry


def chart_delay_causes(tasks: list[Task], period: Period, tz: ZoneInfo) -> dict:
    """G9: quantidade de adiamentos por motivo, em ordem decrescente."""
    counts = Counter(entry.get("reason") or "outro" for _, entry in _postponements(tasks, period, tz))
    items = [{"key": key, "label": label, "value": counts.get(key, 0)} for key, label in POSTPONE_REASONS.items()]
    items.sort(key=lambda i: -i["value"])
    return {"items": items, "total": sum(counts.values())}


def chart_phases(scope: list[Task]) -> dict:
    """G12: tarefas em cada fase, na ordem das fases."""
    counts = Counter(t.phase for t in scope)
    return {"items": [{"key": p, "label": PHASE_LABELS[p], "value": counts.get(p, 0)} for p in PHASES]}


# ---------------------------------------------------------------------------
# Montagem do dashboard
# ---------------------------------------------------------------------------


def build_dashboard(
    tasks: list[Task],
    goals: list[Goal],
    period_key: str,
    now: datetime,
    tz: ZoneInfo,
    stale_days: int,
    *,
    seed: int | None = None,
) -> dict:
    today = local_date(now, tz)
    first_day = first_activity_day(tasks, tz)
    period = period_for(period_key, today, first_day)
    scope = period_scope(tasks, period, tz)
    return {
        "period": period.as_dict(),
        "today": today.isoformat(),
        "kpis": kpis(tasks, period, today, now, tz, stale_days),
        "charts": {
            "g1": chart_created_done(tasks, period, tz),
            "g2": chart_difficulty(scope),
            "g3": chart_on_time(tasks, period, tz),
            "g4": chart_requesters(tasks, period, today, tz),
            "g5": chart_heatmap(tasks, period, tz),
            "g6": chart_completion_time(tasks, period, tz),
            "g7": chart_weekdays(tasks, period, tz),
            "g8": chart_goals(goals, tasks, period, today, tz),
            "g9": chart_delay_causes(tasks, period, tz),
            "g10": capacity.chart_load_capacity(tasks, today, tz, first_day),
            "g11": forecast.forecast(tasks, today, tz, first_day, seed=seed),
            "g12": chart_phases(scope),
        },
    }


# ---------------------------------------------------------------------------
# Drill-down (RF21): tarefas correspondentes ao elemento clicado
# ---------------------------------------------------------------------------


def drilldown(
    tasks: list[Task],
    goals: list[Goal],
    chart: str,
    key: str,
    period_key: str,
    now: datetime,
    tz: ZoneInfo,
    stale_days: int,
) -> dict:
    today = local_date(now, tz)
    first_day = first_activity_day(tasks, tz)
    period = period_for(period_key, today, first_day)
    scope = period_scope(tasks, period, tz)
    title = ""
    selected: list[Task]

    if chart == "kpi":
        options = {
            "pending": ("Tarefas pendentes", [t for t in tasks if t.is_pending]),
            "overdue": ("Tarefas atrasadas", [t for t in tasks if rules.is_overdue(t, today)]),
            "done": ("Concluídas no período", [t for t in tasks if done_in(t, period, tz)]),
            "stale": ("Tarefas paradas", [t for t in tasks if rules.is_stale(t, now, stale_days)]),
            "due_soon": ("Vencem em até 2 dias", [t for t in tasks if rules.is_due_soon(t, today)]),
        }
        if key not in options:
            raise DomainError("Indicador inválido.", code="drill_invalido")
        title, selected = options[key]
    elif chart == "g2":
        selected = [t for t in scope if t.difficulty == key]
        title = f"Dificuldade: {DIFFICULTY_LABELS.get(key, key)}"
    elif chart == "g3":
        flags = {t.id: rules.completed_on_time(t, tz) for t in tasks if done_in(t, period, tz)}
        wanted = key == "on_time"
        selected = [t for t in tasks if flags.get(t.id) is wanted]
        title = "Entregues no prazo" if wanted else "Entregues com atraso"
    elif chart == "g4":
        requester_key, _, category = key.partition("|")
        selected = []
        for task in tasks:
            if rules.normalize_for_match(_requester_key(task)) != requester_key:
                continue
            if category == "done" and done_in(task, period, tz):
                selected.append(task)
            elif category == "overdue" and rules.is_overdue(task, today):
                selected.append(task)
            elif category == "pending" and task.is_pending and not rules.is_overdue(task, today):
                selected.append(task)
        labels = {"done": "concluídas", "pending": "pendentes", "overdue": "atrasadas"}
        name = next((_requester_key(t) for t in selected), requester_key)
        title = f"{name}: {labels.get(category, category)}"
    elif chart == "g5":
        day = date.fromisoformat(key)
        selected = list({t.id: t for t, d in _steps_done(tasks, period, tz) if d == day}.values())
        title = f"Etapas concluídas em {day.strftime('%d/%m/%Y')}"
    elif chart == "g6":
        selected = [t for t in tasks if done_in(t, period, tz) and t.difficulty == key]
        title = f"Concluídas no período: {DIFFICULTY_LABELS.get(key, key)}"
    elif chart == "g7":
        weekday = int(key)
        selected = list({t.id: t for t, d in _steps_done(tasks, period, tz) if d.weekday() == weekday}.values())
        title = f"Etapas concluídas às {WEEKDAY_LABELS[weekday]}"
    elif chart == "g8":
        goal = next((g for g in goals if g.id == key), None)
        selected = [t for t in tasks if t.goal_id == key]
        title = f"Meta: {goal.title}" if goal else "Meta"
    elif chart == "g9":
        selected = list({t.id: t for t, e in _postponements(tasks, period, tz) if (e.get("reason") or "outro") == key}.values())
        title = f"Adiamentos: {POSTPONE_REASONS.get(key, key)}"
    elif chart == "g10":
        week = date.fromisoformat(key)
        current = week_start(today)
        end = week + timedelta(days=6)
        if week < current:
            selected = [
                t for t in tasks if t.is_done and t.completed_at and week <= local_date(t.completed_at, tz) <= end
            ]
            title = f"Concluídas na semana de {week.strftime('%d/%m')}"
        else:
            selected = [
                t
                for t in tasks
                if t.is_pending
                and t.due_date is not None
                and (week <= t.due_date <= end or (week == current and t.due_date < current))
            ]
            title = f"Carga da semana de {week.strftime('%d/%m')}"
    elif chart == "g12":
        selected = [t for t in scope if t.phase == key]
        title = f"Fase: {PHASE_LABELS.get(key, key)}"
    else:
        raise DomainError("Gráfico inválido.", code="drill_invalido")

    return {"title": title, "task_ids": [t.id for t in selected]}


# ---------------------------------------------------------------------------
# Painel da equipe (RF62)
# ---------------------------------------------------------------------------


def member_overview(tasks: list[Task], period_key: str, now: datetime, tz: ZoneInfo, stale_days: int) -> dict:
    today = local_date(now, tz)
    first_day = first_activity_day(tasks, tz)
    period = period_for(period_key, today, first_day)
    pending = [t for t in tasks if t.is_pending]
    scope = period_scope(tasks, period, tz)
    return {
        "pending": len(pending),
        "overdue": sum(1 for t in pending if rules.is_overdue(t, today)),
        "stale": sum(1 for t in pending if rules.is_stale(t, now, stale_days)),
        "done_in_period": sum(1 for t in tasks if done_in(t, period, tz)),
        "phases": chart_phases(scope)["items"],
        "overload": capacity.overload(tasks, today, tz, first_day),
    }
