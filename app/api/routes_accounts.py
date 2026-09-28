"""Rotas de contas (RF23–RF28, RF61), quadro da conta, Top 3, revisão semanal e integrações por conta."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response

from ..config import get_settings
from ..domain.rules import DomainError, not_found
from ..domain.timeutil import get_tz, local_date, utcnow
from ..domain import rules
from ..integrations import ics, notify
from ..services import commands
from ..store import repo
from . import schemas, serializers
from .deps import RequestContext, mutate, read_connection, request_context, viewer_of

router = APIRouter(prefix="/api", tags=["Contas"])


@router.get("/accounts", response_model=list[schemas.AccountOut], summary="Listar contas (RF23, RF34)")
def list_accounts(rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    today = local_date(utcnow(), rc.tz)
    counts = repo.account_counts(conn, today)
    return JSONResponse(
        [serializers.account_json(a, counts.get(a.id, {}), own=a.id == rc.account_id) for a in repo.list_accounts(conn)]
    )


@router.post("/accounts", status_code=201, response_model=schemas.AccountOut, summary="Criar conta apenas com o nome (RF24)")
def create_account(body: schemas.AccountCreate, rc: RequestContext = Depends(request_context)):
    def run(ctx):
        account = commands.create_account(ctx, body.name, body.id)
        return serializers.account_json(account, {}, own=True)

    return mutate(RequestContext(None, rc.tz, rc.client_time, rc.mutation_id), run, status=201)


@router.get("/accounts/{account_id}", response_model=schemas.AccountOut, summary="Detalhar conta")
def get_account(account_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    counts = repo.account_counts(conn, local_date(utcnow(), rc.tz)).get(account_id, {})
    return JSONResponse(serializers.account_json(account, counts, own=account_id == rc.account_id))


@router.patch("/accounts/{account_id}", response_model=schemas.AccountOut, summary="Editar nome, perfil ou configurações (RF27, RF61)")
def update_account(account_id: str, body: schemas.AccountUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)

    def run(ctx):
        account = None
        if "name" in changes:
            account = commands.rename_account(ctx, account_id, changes["name"])
        if "role" in changes:
            account = commands.change_role(ctx, account_id, changes["role"])
        if changes.get("settings"):
            account = commands.update_settings(ctx, account_id, changes["settings"])
        if account is None:
            commands._own(ctx, account_id)
            account = repo.get_account(ctx.conn, account_id)
        return serializers.account_json(account, {}, own=True)

    return mutate(rc, run)


@router.delete("/accounts/{account_id}", status_code=204, summary="Excluir conta com tarefas, metas e templates (RF27, RN13)")
def delete_account(account_id: str, rc: RequestContext = Depends(request_context)):
    uploads = get_settings().uploads_dir
    return mutate(rc, lambda ctx: commands.delete_account(ctx, account_id, uploads))


@router.get("/accounts/{account_id}/board", response_model=schemas.BoardOut, summary="Quadro completo da conta")
def board(account_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    return JSONResponse(serializers.board_json(conn, account, viewer_of(conn, rc), utcnow(), rc.tz))


@router.put("/accounts/{account_id}/top3", response_model=schemas.Top3Out, summary="Definir o Top 3 do dia (RF39, RN18)")
def set_top3(account_id: str, body: schemas.Top3In, rc: RequestContext = Depends(request_context)):
    def run(ctx):
        ids = commands.set_top3(ctx, account_id, body.task_ids)
        return {"day": ctx.action_day.isoformat(), "task_ids": ids}

    return mutate(rc, run)


@router.post("/accounts/{account_id}/weekly-review", summary="Revisão da semana anterior (RF51)")
def weekly_review(account_id: str, rc: RequestContext = Depends(request_context)):
    def run(ctx):
        review = commands.ensure_weekly_review(ctx, account_id)
        return {"review": review}

    return mutate(RequestContext(rc.account_id, rc.tz, utcnow(), None), run)


@router.get("/accounts/{account_id}/weekly-reviews", summary="Histórico de revisões semanais (RF51)")
def weekly_reviews(account_id: str, conn: sqlite3.Connection = Depends(read_connection)):
    return JSONResponse(repo.list_weekly_reviews(conn, account_id))


@router.post("/accounts/{account_id}/weekly-reviews/{week}/seen", status_code=204, summary="Marcar revisão como vista")
def weekly_review_seen(account_id: str, week: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.mark_review_seen(ctx, account_id, week))


@router.get(
    "/accounts/{account_id}/calendar.ics",
    tags=["Integrações"],
    summary="Feed de calendário assinável (RF55)",
    response_class=Response,
    responses={200: {"content": {"text/calendar": {}}}},
)
def calendar_feed(account_id: str, conn: sqlite3.Connection = Depends(read_connection)):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    body = ics.build_calendar(account.name, repo.list_tasks(conn, account_id), utcnow(), get_settings().public_url)
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'inline; filename="entregas.ics"', "Cache-Control": "no-cache"},
    )


@router.post("/accounts/{account_id}/digest/test", tags=["Integrações"], summary="Enviar o resumo diário agora (RF56)")
def digest_test(account_id: str, body: schemas.DigestTestIn, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    account = repo.get_account(conn, account_id)
    if account is None:
        raise not_found("Conta")
    if rc.account_id != account_id:
        raise rules.read_only()
    tz = get_tz(rules.merge_settings(account.settings)["timezone"], get_settings().timezone)
    today = local_date(utcnow(), tz)
    try:
        notify.send_digest(
            get_settings(), account, body.channel, repo.list_tasks(conn, account_id), repo.get_top3(conn, account_id, today), today
        )
    except notify.NotifyError as exc:
        raise DomainError(str(exc), code="envio_falhou", status=502) from None
    return JSONResponse({"sent": True, "channel": body.channel})
