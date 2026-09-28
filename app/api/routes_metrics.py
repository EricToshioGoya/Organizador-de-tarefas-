"""Rotas do dashboard de desempenho (RF17–RF22, G1–G12) e do painel da equipe (RF62)."""

from __future__ import annotations

import sqlite3
import threading
from collections import OrderedDict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..domain import rules
from ..domain.rules import not_found
from ..domain.timeutil import local_date, utcnow
from ..metrics import dashboard
from ..store import repo
from . import schemas, serializers
from .deps import RequestContext, read_connection, request_context

router = APIRouter(prefix="/api", tags=["Desempenho"])

_CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_SIZE = 64


def _account_seq(conn: sqlite3.Connection, account_id: str) -> int:
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) AS seq FROM events WHERE account_id = ?", (account_id,)).fetchone()
    return int(row["seq"])


def _stale_days(account) -> int:
    return rules.merge_settings(account.settings)["stale_days"]


@router.get("/accounts/{account_id}/dashboard", summary="KPIs e gráficos G1–G12 (RF17–RF20)")
def get_dashboard(
    account_id: str,
    period: schemas.Period = Query("30d", description="Filtro de período (RF18)."),
    rc: RequestContext = Depends(request_context),
    conn: sqlite3.Connection = Depends(read_connection),
):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    now = utcnow()
    # O resultado só muda quando chega um evento da conta, quando o dia vira ou com outro fuso/período.
    key = (account_id, _account_seq(conn, account_id), local_date(now, rc.tz).isoformat(), str(rc.tz), period)
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            _CACHE.move_to_end(key)
            return JSONResponse(cached)
    result = dashboard.build_dashboard(
        repo.list_tasks(conn, account_id), repo.list_goals(conn, account_id), period, now, rc.tz, _stale_days(account)
    )
    with _CACHE_LOCK:
        _CACHE[key] = result
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return JSONResponse(result)


@router.get("/accounts/{account_id}/dashboard/drilldown", response_model=schemas.DrilldownOut, summary="Tarefas do elemento clicado (RF21)")
def get_drilldown(
    account_id: str,
    chart: str = Query(..., description="g2, g3, g4, g5, g6, g7, g8, g9, g10, g12 ou kpi."),
    key: str = Query(..., description="Elemento clicado (ex.: 'dificil')."),
    period: schemas.Period = Query("30d"),
    rc: RequestContext = Depends(request_context),
    conn: sqlite3.Connection = Depends(read_connection),
):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    result = dashboard.drilldown(
        repo.list_tasks(conn, account_id),
        repo.list_goals(conn, account_id),
        chart,
        key,
        period,
        utcnow(),
        rc.tz,
        _stale_days(account),
    )
    return JSONResponse(result)


@router.get("/team/overview", tags=["Equipe"], summary="Painel da equipe do Gestor (RF62)")
def team_overview(
    period: schemas.Period = Query("30d"),
    rc: RequestContext = Depends(request_context),
    conn: sqlite3.Connection = Depends(read_connection),
):
    now = utcnow()
    counts = repo.account_counts(conn, local_date(now, rc.tz))
    all_tasks = repo.list_all_tasks(conn)
    by_account: dict[str, list] = {}
    for task in all_tasks:
        by_account.setdefault(task.account_id, []).append(task)
    members = []
    for account in repo.list_accounts(conn):
        members.append(
            {
                "account": serializers.account_json(account, counts.get(account.id, {})),
                "overview": dashboard.member_overview(by_account.get(account.id, []), period, now, rc.tz, _stale_days(account)),
            }
        )
    return JSONResponse({"period": period, "members": members})
