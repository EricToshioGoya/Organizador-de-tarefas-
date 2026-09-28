"""Dependências da API: cabeçalhos de contexto, conexões e execução de mutações idempotentes.

Cabeçalhos aceitos em todas as rotas:
- X-Account-Id: conta em uso (identificação apenas pelo nome, sem autenticação — RNF18).
- X-Timezone: fuso IANA do navegador (RNF16).
- X-Client-Time: instante em que a ação ocorreu no dispositivo (ações offline — RN30).
- Idempotency-Key: ID único da mutação; reenvios da fila local não duplicam efeitos (RF71).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from fastapi import Header
from fastapi.responses import JSONResponse, Response

from ..config import get_settings
from ..domain.rules import DomainError
from ..domain.timeutil import get_tz, parse_iso, to_iso, utcnow
from ..services.context import Ctx
from ..store import repo
from ..store.db import connect, write_transaction
from ..store.events import dumps

MAX_FUTURE_SKEW = timedelta(minutes=1)


@dataclass
class RequestContext:
    account_id: str | None
    tz: ZoneInfo
    client_time: datetime
    mutation_id: str | None


def client_time(value: str | None) -> datetime:
    now = utcnow()
    try:
        moment = parse_iso(value) if value else None
    except ValueError:
        moment = None
    if moment is None or moment > now + MAX_FUTURE_SKEW:
        return now
    return moment


def request_context(
    x_account_id: str | None = Header(None, alias="X-Account-Id", description="Conta em uso."),
    x_timezone: str | None = Header(None, alias="X-Timezone", description="Fuso IANA do navegador."),
    x_client_time: str | None = Header(None, alias="X-Client-Time", description="Instante da ação no dispositivo (ISO 8601)."),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", description="ID único da mutação (reenvio seguro)."),
) -> RequestContext:
    key = idempotency_key if idempotency_key and 8 <= len(idempotency_key) <= 100 else None
    return RequestContext(
        account_id=x_account_id or None,
        tz=get_tz(x_timezone, get_settings().timezone),
        client_time=client_time(x_client_time),
        mutation_id=key,
    )


def read_connection() -> Iterator[sqlite3.Connection]:
    conn = connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


def viewer_of(conn: sqlite3.Connection, rc: RequestContext):
    return repo.get_account(conn, rc.account_id)


def mutate(rc: RequestContext, fn: Callable[[Ctx], Any], status: int = 200) -> Response:
    """Executa um comando numa transação; respostas de mutações já processadas são reaproveitadas."""
    conn = connect(get_settings().db_path)
    try:
        with write_transaction(conn):
            if rc.mutation_id:
                stored = repo.get_mutation(conn, rc.mutation_id)
                if stored is not None:
                    if stored["status"] == 204:
                        return Response(status_code=204, headers={"X-Replayed": "1"})
                    return JSONResponse(json.loads(stored["response"]), status_code=stored["status"], headers={"X-Replayed": "1"})
            actor = repo.get_account(conn, rc.account_id)
            if rc.account_id and actor is None:
                raise DomainError("A conta selecionada não existe mais.", code="conta_inexistente", status=401)
            ctx = Ctx(conn=conn, actor=actor, occurred_at=rc.client_time, tz=rc.tz, mutation_id=rc.mutation_id)
            body = fn(ctx)
            final_status = 204 if body is None else status
            if rc.mutation_id:
                repo.save_mutation(conn, rc.mutation_id, to_iso(utcnow()), final_status, dumps(body))
        ctx.run_post_commit()
        if body is None:
            return Response(status_code=204)
        return JSONResponse(body, status_code=final_status)
    finally:
        conn.close()
