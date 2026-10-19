"""Rotas das Listas: listas com nome (modelo tarefas ou ranking) e seus itens, visíveis só para a própria conta."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..domain.rules import not_found, read_only
from ..services import commands
from ..store import repo
from . import schemas, serializers
from .deps import RequestContext, mutate, read_connection, request_context, viewer_of

router = APIRouter(prefix="/api", tags=["Listas"])


@router.get("/accounts/{account_id}/lists", response_model=schemas.ListsOut, summary="Listas da conta e seus itens (só a própria conta)")
def get_lists(account_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    if repo.get_account(conn, account_id) is None:
        raise not_found("Conta")
    viewer = viewer_of(conn, rc)
    if viewer is None or viewer.id != account_id:
        raise read_only()
    return JSONResponse(serializers.lists_json(conn, account_id))


@router.post("/accounts/{account_id}/lists", status_code=201, response_model=schemas.UserListOut, summary="Criar lista")
def create_list(account_id: str, body: schemas.UserListCreate, rc: RequestContext = Depends(request_context)):
    data = body.model_dump()
    return mutate(rc, lambda ctx: serializers.user_list_json(commands.create_user_list(ctx, account_id, data)), status=201)


@router.patch("/lists/{list_id}", response_model=schemas.UserListOut, summary="Renomear lista ou trocar o modelo")
def update_list(list_id: str, body: schemas.UserListUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: serializers.user_list_json(commands.update_user_list(ctx, list_id, changes)))


@router.delete("/lists/{list_id}", status_code=204, summary="Excluir lista com todos os itens")
def delete_list(list_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_user_list(ctx, list_id))


@router.put("/lists/{list_id}/order", response_model=list[schemas.ListItemOut], summary="Reordenar o ranking")
def reorder_items(list_id: str, body: schemas.ListItemsOrder, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: [serializers.list_item_json(i) for i in commands.reorder_list_items(ctx, list_id, body.order)])


@router.post("/lists/{list_id}/items", status_code=201, response_model=schemas.ListItemOut, summary="Adicionar item à lista")
def create_item(list_id: str, body: schemas.ListItemCreate, rc: RequestContext = Depends(request_context)):
    data = body.model_dump()
    return mutate(rc, lambda ctx: serializers.list_item_json(commands.create_list_item(ctx, list_id, data)), status=201)


@router.patch("/list-items/{item_id}", response_model=schemas.ListItemOut, summary="Editar, concluir ou reabrir item")
def update_item(item_id: str, body: schemas.ListItemUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: serializers.list_item_json(commands.update_list_item(ctx, item_id, changes)))


@router.delete("/list-items/{item_id}", status_code=204, summary="Excluir item da lista")
def delete_item(item_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_list_item(ctx, item_id))
