"""Rotas do calendário: eventos com horário ou de dia inteiro, repetição e ocorrências avulsas."""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..domain.rules import not_found
from ..services import commands
from ..store import repo
from . import schemas, serializers
from .deps import RequestContext, mutate, read_connection, request_context, viewer_of

router = APIRouter(prefix="/api", tags=["Calendário"])


def _entry_out(ctx, entry) -> dict:
    return serializers.calendar_entry_json(entry, ctx.actor)


@router.get(
    "/accounts/{account_id}/calendar",
    response_model=list[schemas.CalendarEntryOut],
    summary="Eventos do calendário da conta (de outra conta, em modo somente leitura)",
)
def list_entries(account_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    if repo.get_account(conn, account_id) is None:
        raise not_found("Conta")
    viewer = viewer_of(conn, rc)
    return JSONResponse([serializers.calendar_entry_json(e, viewer) for e in repo.list_calendar_entries(conn, account_id)])


@router.post("/accounts/{account_id}/calendar", status_code=201, response_model=schemas.CalendarEntryOut, summary="Criar evento")
def create_entry(account_id: str, body: schemas.CalendarEntryCreate, rc: RequestContext = Depends(request_context)):
    data = body.model_dump()
    return mutate(rc, lambda ctx: _entry_out(ctx, commands.create_calendar_entry(ctx, account_id, data)), status=201)


@router.get("/calendar/{entry_id}", response_model=schemas.CalendarEntryOut, summary="Detalhar evento")
def get_entry(entry_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    entry = repo.get_calendar_entry(conn, entry_id)
    if entry is None:
        raise not_found("Evento")
    return JSONResponse(serializers.calendar_entry_json(entry, viewer_of(conn, rc)))


@router.patch("/calendar/{entry_id}", response_model=schemas.CalendarEntryOut, summary="Editar evento (a série inteira, se repetir)")
def update_entry(entry_id: str, body: schemas.CalendarEntryUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: _entry_out(ctx, commands.update_calendar_entry(ctx, entry_id, changes)))


@router.delete("/calendar/{entry_id}", status_code=204, summary="Excluir evento (a série inteira, se repetir)")
def delete_entry(entry_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_calendar_entry(ctx, entry_id))


@router.delete(
    "/calendar/{entry_id}/occurrences/{occurrence}",
    response_model=schemas.CalendarEntryOut,
    summary="Excluir só uma ocorrência de um evento que se repete",
)
def delete_occurrence(entry_id: str, occurrence: date, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _entry_out(ctx, commands.exclude_occurrence(ctx, entry_id, occurrence)))


@router.post(
    "/calendar/{entry_id}/occurrences/{occurrence}",
    status_code=201,
    response_model=schemas.OccurrenceOut,
    summary="Alterar só uma ocorrência: ela sai da série e vira um evento avulso",
)
def edit_occurrence(entry_id: str, occurrence: date, body: schemas.OccurrenceEdit, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)

    def run(ctx):
        series, entry = commands.detach_occurrence(ctx, entry_id, occurrence, changes)
        return {"series": _entry_out(ctx, series), "entry": _entry_out(ctx, entry)}

    return mutate(rc, run, status=201)
