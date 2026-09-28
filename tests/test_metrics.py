"""Métricas: KPIs (RF17), gráficos G1–G12, capacidade (RN25), Monte Carlo (RN28), similaridade (RN27) e revisão semanal (RF51)."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest

from app.domain.rules import DomainError
from app.metrics import capacity, dashboard, forecast, similarity, weekly
from app.metrics.common import period_for, period_scope

from .factories import NOW, TODAY, TZ, at, goal, step, task

WEEK = date(2026, 9, 21)  # segunda-feira da semana de TODAY


# --- Período (RF18) ---------------------------------------------------------------------


def test_period_ranges_and_granularity():
    p7 = period_for("7d", TODAY, None)
    assert (p7.start, p7.end, p7.granularity) == (date(2026, 9, 17), TODAY, "day")
    assert p7.previous().end == date(2026, 9, 16) and p7.previous().days == 7
    p12 = period_for("12m", TODAY, None)
    assert p12.granularity == "week" and p12.buckets()[0].weekday() == 0
    assert period_for("all", TODAY, date(2026, 1, 1)).start == date(2026, 1, 1)
    assert period_for("all", TODAY, None).previous() is None
    with pytest.raises(DomainError):
        period_for("5d", TODAY, None)


def test_period_scope_keeps_pending_and_done_in_period():
    pending, recent, old = task(), task(completed=at(TODAY)), task(completed=at(TODAY - timedelta(days=60)))
    assert period_scope([pending, recent, old], period_for("30d", TODAY, None), TZ) == [pending, recent]


# --- KPIs ----------------------------------------------------------------------------------


def test_kpis():
    tasks = [
        task(due=TODAY - timedelta(days=2)),  # atrasada
        task(due=TODAY + timedelta(days=1)),  # vence em breve
        task(last_activity=NOW - timedelta(days=9)),  # parada
        task(created=at(TODAY - timedelta(days=4)), completed=at(TODAY - timedelta(days=2)), due=TODAY),
        task(created=at(TODAY - timedelta(days=6)), completed=at(TODAY - timedelta(days=2)), due=TODAY - timedelta(days=3)),
        task(created=at(TODAY - timedelta(days=50)), completed=at(TODAY - timedelta(days=40))),  # período anterior
    ]
    result = dashboard.kpis(tasks, period_for("30d", TODAY, None), TODAY, NOW, TZ, 5)
    assert result["pending"] == 3
    assert result["overdue"] == 1
    assert result["due_soon"] == 1
    assert result["stale"] == 3  # criadas há 10 dias sem atividade
    assert result["done"] == 2
    assert result["on_time_pct"] == 50.0 and result["on_time_base"] == 2
    assert result["avg_completion_days"] == 3.0
    assert result["previous"]["done"] == 1


# --- Gráficos --------------------------------------------------------------------------------


def test_g1_created_vs_done_with_backlog():
    period = period_for("7d", TODAY, None)
    tasks = [
        task(created=at(TODAY - timedelta(days=20))),  # backlog anterior
        task(created=at(TODAY - timedelta(days=1)), completed=at(TODAY)),
        task(created=at(TODAY)),
    ]
    chart = dashboard.chart_created_done(tasks, period, TZ)
    assert chart["granularity"] == "day" and len(chart["labels"]) == 7
    assert chart["created"][-2:] == [1, 1]
    assert chart["done"][-1] == 1
    assert chart["backlog"][0] == 1 and chart["backlog"][-1] == 2


def test_g2_g12_distributions():
    scope = [task(difficulty="facil", phase="beta"), task(difficulty="dificil"), task(difficulty="dificil", phase="beta")]
    g2 = dashboard.chart_difficulty(scope)
    assert g2["total"] == 3 and [i["value"] for i in g2["items"]] == [1, 0, 2]
    g12 = dashboard.chart_phases(scope)
    assert [i["key"] for i in g12["items"]] == ["planejamento", "producao", "alpha", "beta", "concluido"]
    assert [i["value"] for i in g12["items"]] == [1, 0, 0, 2, 0]


def test_g3_on_time_gauge():
    period = period_for("30d", TODAY, None)
    tasks = [task(due=TODAY, completed=at(TODAY)), task(due=TODAY - timedelta(days=5), completed=at(TODAY)), task(completed=at(TODAY))]
    assert dashboard.chart_on_time(tasks, period, TZ) == {"value": 50.0, "on_time": 1, "late": 1, "base": 2}
    assert dashboard.chart_on_time([], period, TZ)["value"] is None


def test_g4_requesters():
    period = period_for("30d", TODAY, None)
    tasks = [
        task(requester="Carlos", completed=at(TODAY)),
        task(requester="carlos"),
        task(requester="Carlos", due=TODAY - timedelta(days=1)),
        task(requester=""),
    ]
    items = dashboard.chart_requesters(tasks, period, TODAY, TZ)["items"]
    assert items[0]["requester"] == "Carlos" and (items[0]["done"], items[0]["pending"], items[0]["overdue"]) == (1, 1, 1)
    assert items[1]["requester"] == "Sem solicitante"


def test_g5_g7_steps_activity():
    period = period_for("30d", TODAY, None)
    t = task(steps=[step(True, at(TODAY)), step(True, at(TODAY)), step(True, at(TODAY - timedelta(days=1))), step(True, at(TODAY - timedelta(days=90))), step()])
    heat = dashboard.chart_heatmap([t], period, TZ)
    assert heat["days"] == [["2026-09-22", 1], ["2026-09-23", 2]] and heat["max"] == 2 and heat["total"] == 3
    radar = dashboard.chart_weekdays([t], period, TZ)
    assert radar["values"] == [0, 1, 2, 0, 0, 0, 0]  # terça e quarta


def test_g6_completion_time_by_difficulty():
    period = period_for("30d", TODAY, None)
    tasks = [
        task(difficulty="dificil", created=at(TODAY - timedelta(days=4)), completed=at(TODAY)),
        task(difficulty="dificil", created=at(TODAY - timedelta(days=2)), completed=at(TODAY)),
        task(difficulty="facil"),
    ]
    items = {i["key"]: i for i in dashboard.chart_completion_time(tasks, period, TZ)["items"]}
    assert items["dificil"]["avg_days"] == 3.0 and items["dificil"]["count"] == 2
    assert items["facil"]["avg_days"] is None


def test_g8_goals_progress():
    period = period_for("30d", TODAY, None)
    active = goal(title="Passar em Cálculo", target=TODAY - timedelta(days=1))
    finished_old = goal(title="Antiga", done=True, completed=at(TODAY - timedelta(days=90)))
    finished_new = goal(title="Recente", done=True, completed=at(TODAY))
    tasks = [task(goal_id=active.id, completed=NOW), task(goal_id=active.id), task(goal_id=finished_new.id, completed=NOW)]
    items = dashboard.chart_goals([active, finished_old, finished_new], tasks, period, TODAY, TZ)["items"]
    assert [i["title"] for i in items] == ["Passar em Cálculo", "Recente"]
    assert items[0]["progress"] == 50 and items[0]["overdue"] is True and items[0]["total"] == 2


def test_g9_delay_causes_sorted():
    period = period_for("30d", TODAY, None)
    history = [
        {"at": "2026-09-20T12:00:00.000Z", "kind": "adiamento", "reason": "prioridade"},
        {"at": "2026-09-21T12:00:00.000Z", "kind": "adiamento", "reason": "prioridade"},
        {"at": "2026-09-21T12:00:00.000Z", "kind": "antecipacao", "reason": None},
        {"at": "2025-01-01T12:00:00.000Z", "kind": "adiamento", "reason": "subestimei"},
    ]
    chart = dashboard.chart_delay_causes([task(due_history=history)], period, TZ)
    assert chart["total"] == 2 and chart["items"][0] == {"key": "prioridade", "label": "Mudança de prioridade", "value": 2}
    assert len(chart["items"]) == 4


def test_build_dashboard_contains_all_charts():
    tasks = [task(created=at(TODAY - timedelta(days=d)), completed=at(TODAY - timedelta(days=d - 1)) if d % 2 else None, difficulty=("facil", "medio", "dificil")[d % 3], due=TODAY + timedelta(days=d % 5 - 2)) for d in range(1, 60)]
    result = dashboard.build_dashboard(tasks, [goal()], "90d", NOW, TZ, 5, seed=1)
    assert set(result["charts"]) == {f"g{i}" for i in range(1, 13)}
    assert result["period"]["key"] == "90d"
    assert result["charts"]["g11"]["status"] == "ok"


def test_dashboard_with_1000_tasks_is_fast():
    """RNF09: dashboard com 1.000 tarefas — o cálculo no servidor deve ficar bem abaixo de 1 s."""
    tasks = []
    for i in range(1000):
        created = at(TODAY - timedelta(days=i % 300 + 1))
        done = at(TODAY - timedelta(days=i % 300)) if i % 3 else None
        steps = [step(True, done or NOW) for _ in range(3)] + [step()]
        tasks.append(task(created=created, completed=done, difficulty=("facil", "medio", "dificil")[i % 3], requester=f"P{i % 7}", due=TODAY + timedelta(days=i % 30 - 15), steps=steps))
    start = time.perf_counter()
    dashboard.build_dashboard(tasks, [], "all", NOW, TZ, 5, seed=3)
    assert time.perf_counter() - start < 1.0


# --- Drill-down (RF21) -----------------------------------------------------------------------


def test_drilldown():
    hard = task(difficulty="dificil", phase="beta", requester="Ana", due=TODAY - timedelta(days=1))
    easy = task(difficulty="facil", completed=at(TODAY), due=TODAY, steps=[step(True, at(TODAY))], due_history=[{"at": "2026-09-22T12:00:00.000Z", "kind": "adiamento", "reason": "dependencia"}])
    g = goal()
    linked = task(goal_id=g.id)
    tasks = [hard, easy, linked]

    def ids(chart, key):
        return dashboard.drilldown(tasks, [g], chart, key, "30d", NOW, TZ, 5)["task_ids"]

    assert ids("g2", "dificil") == [hard.id]
    assert ids("g3", "on_time") == [easy.id] and ids("g3", "late") == []
    assert ids("g4", "ana|overdue") == [hard.id]
    assert ids("g4", "sem solicitante|done") == [easy.id]
    assert ids("g4", "sem solicitante|pending") == [linked.id]
    assert ids("g5", TODAY.isoformat()) == [easy.id]
    assert ids("g6", "facil") == [easy.id]
    assert ids("g7", "2") == [easy.id]
    assert ids("g8", g.id) == [linked.id]
    assert ids("g9", "dependencia") == [easy.id]
    assert ids("g10", WEEK.isoformat()) == [hard.id]
    assert ids("g10", (WEEK - timedelta(days=7)).isoformat()) == []
    assert ids("g12", "beta") == [hard.id]
    assert ids("kpi", "overdue") == [hard.id]
    assert set(ids("kpi", "pending")) == {hard.id, linked.id}
    assert ids("kpi", "done") == [easy.id]
    for bad_chart, bad_key in (("kpi", "x"), ("g99", "x")):
        with pytest.raises(DomainError):
            ids(bad_chart, bad_key)


# --- Capacidade (RN25, G10) --------------------------------------------------------------------


def test_capacity_needs_two_complete_weeks():
    first_day = WEEK - timedelta(days=7)  # só uma semana completa
    assert capacity.capacity([], TODAY, TZ, first_day)["value"] is None


def test_capacity_average_of_last_four_weeks_and_overload():
    first_day = WEEK - timedelta(days=70)
    tasks = [
        task(difficulty="dificil", completed=at(WEEK - timedelta(days=3))),  # semana -1: 3 pts
        task(difficulty="medio", completed=at(WEEK - timedelta(days=10))),  # semana -2: 2 pts
        task(difficulty="facil", completed=at(WEEK - timedelta(days=40))),  # fora da janela
        task(difficulty="dificil", due=TODAY - timedelta(days=5)),  # atrasada: entra na carga
        task(difficulty="medio", due=WEEK + timedelta(days=6)),  # domingo desta semana
        task(difficulty="dificil", due=WEEK + timedelta(days=8)),  # semana que vem: fora
        task(difficulty="dificil"),  # sem data: fora
    ]
    cap = capacity.capacity(tasks, TODAY, TZ, first_day)
    assert cap == {"value": 1.25, "weeks": 4, "min_weeks": 2}
    assert capacity.current_load(tasks, TODAY) == 5
    status = capacity.overload(tasks, TODAY, TZ, first_day)
    assert status["overloaded"] is True and status["load"] == 5
    chart = capacity.chart_load_capacity(tasks, TODAY, TZ, first_day)
    assert len(chart["weeks"]) == 13 and chart["current_index"] == 8
    assert chart["done"][7] == 3 and chart["load"][8] == 5 and chart["load"][9] == 3


def test_capacity_uses_available_history_between_two_and_four_weeks():
    first_day = WEEK - timedelta(days=14)
    tasks = [task(difficulty="dificil", completed=at(WEEK - timedelta(days=2)))]
    assert capacity.capacity(tasks, TODAY, TZ, first_day)["value"] == 1.5


# --- Monte Carlo (RN28, G11, RNF24) -----------------------------------------------------------------


def test_throughput_requires_four_weeks():
    assert forecast.weekly_throughput([], TODAY, TZ, WEEK - timedelta(days=21)) is None
    assert forecast.weekly_throughput([], TODAY, TZ, None) is None
    tasks = [task(completed=at(WEEK - timedelta(days=1))), task(completed=at(WEEK - timedelta(days=2))), task(completed=at(WEEK - timedelta(days=15)))]
    sample = forecast.weekly_throughput(tasks, TODAY, TZ, WEEK - timedelta(days=200))
    assert len(sample) == 12 and sample[-1] == 2 and sample[-3] == 1


def test_simulation_edge_cases():
    assert forecast.simulate(0, [1, 2]) == [0] * forecast.SIMULATIONS
    assert forecast.simulate(3, [0, 0]) == [None] * forecast.SIMULATIONS
    assert set(forecast.simulate(4, [2], sims=10)) == {2}


def test_forecast_percentiles_are_ordered_and_fast():
    first_day = WEEK - timedelta(days=120)
    done = [task(completed=at(WEEK - timedelta(days=7 * w + 1))) for w in range(12) for _ in range(w % 3 + 1)]
    pending = [task() for _ in range(20)]
    start = time.perf_counter()
    result = forecast.forecast(done + pending, TODAY, TZ, first_day, seed=42)
    assert time.perf_counter() - start < 1.0  # RNF24
    assert result["status"] == "ok" and result["pending"] == 20
    weeks = [p["week"] for p in result["percentiles"]]
    assert weeks == sorted(weeks) and all(w is not None for w in weeks)
    probabilities = [c["probability"] for c in result["curve"]]
    assert probabilities == sorted(probabilities) and probabilities[-1] == 100


def test_forecast_statuses():
    first_day = WEEK - timedelta(days=120)
    assert forecast.forecast([task(completed=NOW)], TODAY, TZ, first_day)["status"] == "sem_pendentes"
    assert forecast.forecast([task()], TODAY, TZ, WEEK - timedelta(days=7))["status"] == "dados_insuficientes"
    stuck = forecast.forecast([task()], TODAY, TZ, first_day, seed=1)
    assert stuck["status"] == "ok" and all(p["beyond_horizon"] for p in stuck["percentiles"])


# --- Similaridade (RN27, RF53) ------------------------------------------------------------------------


def test_similarity_needs_five_done_tasks():
    tasks = [task(title="Relatório", completed=NOW) for _ in range(4)]
    assert similarity.suggest("Relatório", "", tasks, TODAY) == {"active": False, "done_count": 4, "min_done": 5}


def test_similarity_suggests_mode_and_median():
    def done(title, difficulty, days):
        return task(title=title, difficulty=difficulty, created=NOW - timedelta(days=days), completed=NOW)

    tasks = [
        done("Relatório mensal de vendas", "dificil", 4),
        done("Relatório de vendas trimestral", "dificil", 6),
        done("Relatório financeiro mensal", "medio", 2),
        done("Comprar café", "facil", 0.2),
        done("Atualizar planilha de horas", "facil", 1),
        done("Revisar contrato", "medio", 3),
    ]
    result = similarity.suggest("Relatório de vendas de outubro", "", tasks, TODAY)
    assert result["found"] and result["difficulty"] == "dificil"
    assert result["due_date"] == (TODAY + timedelta(days=4)).isoformat()
    assert result["based_on"][0]["title"].startswith("Relatório")
    no_match = similarity.suggest("xyzzy", "", tasks, TODAY)
    assert no_match["active"] and not no_match["found"]


def test_tfidf_helpers():
    assert similarity.tokenize("O Relatório de Vendas!") == ["relatorio", "vendas"]
    assert similarity.cosine({}, {"a": 1}) == 0.0
    idf = similarity.build_idf([["a", "b"], ["a"]])
    assert idf["b"] > idf["a"]


# --- Revisão semanal (RF51) ------------------------------------------------------------------------------


def test_weekly_review_compares_with_previous_week():
    last_week = WEEK - timedelta(days=7)
    tasks = [
        task(difficulty="dificil", completed=at(last_week + timedelta(days=1))),
        task(difficulty="facil", completed=at(last_week + timedelta(days=2))),
        task(due=last_week + timedelta(days=3)),  # não concluída: atrasada
        task(due=last_week + timedelta(days=3), completed=at(last_week + timedelta(days=4))),  # concluída depois do prazo
        task(completed=at(last_week - timedelta(days=3))),  # semana anterior
        task(due_history=[{"at": (last_week + timedelta(days=2)).isoformat() + "T15:00:00Z", "kind": "adiamento", "reason": "prioridade"}]),
    ]
    review = weekly.weekly_review(tasks, last_week, TZ)
    assert review["week_start"] == "2026-09-14" and review["week_end"] == "2026-09-20"
    current = review["current"]
    assert (current["done"], current["late"], current["postponed"]) == (3, 2, 1)
    assert current["points"] == 3 + 1 + 2
    assert review["previous"]["done"] == 1
    assert review["delta"]["done"] == 2
