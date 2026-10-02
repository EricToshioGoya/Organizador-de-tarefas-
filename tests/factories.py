"""Fábricas de objetos de domínio para os testes de regras e métricas."""

from __future__ import annotations

import itertools
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.models import Goal, Step, Task

TZ = ZoneInfo("America/Sao_Paulo")
TODAY = date(2026, 9, 23)  # quarta-feira
NOW = datetime.combine(TODAY, time(15, 0), TZ)
_ids = itertools.count(1)


def at(day: date, hour: int = 12) -> datetime:
    """Instante local (fuso de São Paulo) no dia informado."""
    return datetime.combine(day, time(hour, 0), TZ)


def step(done: bool = False, done_at: datetime | None = None, text: str | None = None, position: float = 0) -> Step:
    n = next(_ids)
    return Step(
        id=f"step-{n:05d}",
        text=text or f"Etapa {n}",
        position=position,
        done=done,
        done_at=done_at if done else None,
        created_at=NOW - timedelta(days=30),
    )


def task(
    *,
    title: str | None = None,
    created: datetime | None = None,
    completed: datetime | None = None,
    due: date | None = None,
    difficulty: str = "medio",
    priority: str = "media",
    requester: str = "",
    phase: str = "planejamento",
    steps: list[Step] | None = None,
    goal_id: str | None = None,
    account_id: str = "acc-1",
    last_activity: datetime | None = None,
    due_history: list[dict] | None = None,
    description: str = "",
) -> Task:
    n = next(_ids)
    created = created or NOW - timedelta(days=10)
    return Task(
        id=f"task-{n:05d}",
        account_id=account_id,
        title=title or f"Tarefa {n}",
        created_at=created,
        difficulty=difficulty,
        priority=priority,
        description=description,
        due_date=due,
        requester=requester,
        completed_at=completed,
        status="concluida" if completed else "pendente",
        goal_id=goal_id,
        phase=phase,
        last_activity_at=last_activity or created,
        due_history=due_history or [],
        steps=steps or [],
    )


def goal(*, title: str = "Meta", target: date | None = None, done: bool = False, completed: datetime | None = None, account_id: str = "acc-1") -> Goal:
    n = next(_ids)
    return Goal(
        id=f"goal-{n:05d}",
        account_id=account_id,
        title=title,
        created_at=NOW - timedelta(days=60),
        target_date=target,
        status="concluida" if done else "andamento",
        completed_at=completed if done else None,
    )
