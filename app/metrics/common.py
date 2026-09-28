"""Período do filtro (RF18) e recortes de tarefas usados por KPIs e gráficos.

Semântica adotada para "indicadores de período":
- Pendentes e atrasadas refletem o estado atual (não dependem do período).
- Concluídas, % no prazo e tempo médio consideram as tarefas concluídas dentro do período.
- Gráficos de distribuição (G2, G4, G12) usam o "escopo do período": pendentes + concluídas no período.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain.constants import PERIODS
from ..domain.models import Task
from ..domain.rules import DomainError
from ..domain.timeutil import local_date, week_start

PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "12m": 365}
PERIOD_LABELS = {
    "7d": "7 dias",
    "30d": "30 dias",
    "90d": "90 dias",
    "12m": "12 meses",
    "all": "Todo o histórico",
}


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def granularity(self) -> str:
        return "day" if self.days <= 92 else "week"

    def contains(self, value: date | None) -> bool:
        return value is not None and self.start <= value <= self.end

    def previous(self) -> "Period | None":
        if self.key == "all":
            return None
        end = self.start - timedelta(days=1)
        return Period(self.key, end - timedelta(days=self.days - 1), end)

    def buckets(self) -> list[date]:
        if self.granularity == "day":
            return [self.start + timedelta(days=i) for i in range(self.days)]
        first, last = week_start(self.start), week_start(self.end)
        return [first + timedelta(days=7 * i) for i in range((last - first).days // 7 + 1)]

    def bucket_of(self, value: date) -> date:
        return value if self.granularity == "day" else week_start(value)

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": PERIOD_LABELS[self.key],
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "granularity": self.granularity,
        }


def first_activity_day(tasks: Iterable[Task], tz: ZoneInfo) -> date | None:
    days = [local_date(t.created_at, tz) for t in tasks]
    return min(days) if days else None


def period_for(key: str, today: date, first_day: date | None) -> Period:
    if key not in PERIODS:
        raise DomainError("Período inválido.", code="periodo_invalido")
    if key == "all":
        start = min(first_day or today, today)
    else:
        start = today - timedelta(days=PERIOD_DAYS[key] - 1)
    return Period(key, start, today)


def done_in(task: Task, period: Period, tz: ZoneInfo) -> bool:
    return task.is_done and task.completed_at is not None and period.contains(local_date(task.completed_at, tz))


def period_scope(tasks: Iterable[Task], period: Period, tz: ZoneInfo) -> list[Task]:
    return [t for t in tasks if t.is_pending or done_in(t, period, tz)]
