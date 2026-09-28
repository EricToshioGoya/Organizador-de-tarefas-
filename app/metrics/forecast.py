"""Previsão de conclusão por simulação de Monte Carlo (RF54, RN28, G11, RNF24).

- Amostra: throughput semanal (tarefas concluídas por semana) das últimas 12 semanas completas,
  ou do histórico disponível, com mínimo de 4 semanas.
- 10.000 simulações sorteiam semanas com reposição até cobrir o total de pendentes (horizonte de 52).
- Resultado: probabilidade acumulada por semana e percentis 50%, 85% e 95%.
Independe do filtro de período (RF18).
"""

from __future__ import annotations

import random
from bisect import bisect_left
from collections import Counter
from datetime import date, timedelta
from itertools import accumulate
from typing import Iterable
from zoneinfo import ZoneInfo

from ..domain.models import Task
from ..domain.timeutil import local_date, week_start

SIMULATIONS = 10_000
HORIZON_WEEKS = 52
SAMPLE_WEEKS = 12
MIN_SAMPLE_WEEKS = 4
PERCENTILES = (50, 85, 95)


def weekly_throughput(tasks: Iterable[Task], today: date, tz: ZoneInfo, first_day: date | None) -> list[int] | None:
    tasks = list(tasks)
    if first_day is None:
        return None
    current = week_start(today)
    available = (current - week_start(first_day)).days // 7
    weeks = min(SAMPLE_WEEKS, available)
    if weeks < MIN_SAMPLE_WEEKS:
        return None
    done_weeks = Counter(
        week_start(local_date(t.completed_at, tz)) for t in tasks if t.is_done and t.completed_at is not None
    )
    return [done_weeks.get(current - timedelta(days=7 * (i + 1)), 0) for i in range(weeks)][::-1]


def simulate(pending: int, samples: list[int], sims: int = SIMULATIONS, horizon: int = HORIZON_WEEKS, seed: int | None = None) -> list[int | None]:
    """Semanas necessárias em cada simulação (None quando não conclui dentro do horizonte)."""
    if pending <= 0:
        return [0] * sims
    if not samples or max(samples) <= 0:
        return [None] * sims
    rng = random.Random(seed)
    choices = rng.choices
    results: list[int | None] = []
    append = results.append
    for _ in range(sims):
        cumulative = list(accumulate(choices(samples, k=horizon)))
        index = bisect_left(cumulative, pending)
        append(index + 1 if index < horizon else None)
    return results


def forecast(tasks: list[Task], today: date, tz: ZoneInfo, first_day: date | None, seed: int | None = None) -> dict:
    pending = sum(1 for t in tasks if t.is_pending)
    samples = weekly_throughput(tasks, today, tz, first_day)
    base = {
        "pending": pending,
        "simulations": SIMULATIONS,
        "horizon_weeks": HORIZON_WEEKS,
        "sample": samples or [],
        "min_weeks": MIN_SAMPLE_WEEKS,
    }
    if pending == 0:
        return {**base, "status": "sem_pendentes", "curve": [], "percentiles": []}
    if samples is None:
        return {**base, "status": "dados_insuficientes", "curve": [], "percentiles": []}

    results = simulate(pending, samples, seed=seed)
    finished = Counter(r for r in results if r is not None)
    curve = []
    cumulative = 0
    for week in range(1, HORIZON_WEEKS + 1):
        cumulative += finished.get(week, 0)
        curve.append(
            {
                "week": week,
                "date": (today + timedelta(days=7 * week)).isoformat(),
                "probability": round(cumulative * 100 / len(results), 2),
            }
        )
    percentiles = []
    for p in PERCENTILES:
        point = next((c for c in curve if c["probability"] >= p), None)
        percentiles.append(
            {
                "p": p,
                "week": point["week"] if point else None,
                "date": point["date"] if point else None,
                "beyond_horizon": point is None,
            }
        )
    return {**base, "status": "ok", "curve": curve, "percentiles": percentiles}
