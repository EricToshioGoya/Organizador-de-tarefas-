"""Rotas da Daily: tarefas simples do dia (título, anotação, dia e conclusão)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..domain.rules import not_found
from ..services import commands
from ..store import repo
from . import schemas, serializers
from .deps import RequestContext, mutate, read_connection, request_context

router = APIRouter(prefix="/api", tags=["Daily"])


@router.get(
    "/accounts/{account_id}/daily",
    response_model=list[schemas.DailyItemOut],
    summary="Itens da Daily da conta (de outra conta, em modo somente leitura)",
)
def list_items(account_id: str, conn: sqlite3.Connection = Depends(read_connection)):
    if repo.get_account(conn, account_id) is None:
        raise not_found("Conta")
    return JSONResponse([serializers.daily_item_json(i) for i in repo.list_daily_items(conn, account_id)])


@router.post("/accounts/{account_id}/daily", status_code=201, response_model=schemas.DailyItemOut, summary="Adicionar item à Daily")
def create_item(account_id: str, body: schemas.DailyItemCreate, rc: RequestContext = Depends(request_context)):
    data = body.model_dump()
    return mutate(rc, lambda ctx: serializers.daily_item_json(commands.create_daily_item(ctx, account_id, data)), status=201)


@router.patch("/daily/{item_id}", response_model=schemas.DailyItemOut, summary="Editar, mover de dia, concluir ou reabrir item")
def update_item(item_id: str, body: schemas.DailyItemUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: serializers.daily_item_json(commands.update_daily_item(ctx, item_id, changes)))


@router.delete("/daily/{item_id}", status_code=204, summary="Excluir item da Daily")
def delete_item(item_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_daily_item(ctx, item_id))
