"""Rotas de produtividade (RF41, RF44, RF52, RF53), metadados e sincronização (RNF19)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from .. import __version__
from ..config import get_settings
from ..domain import rules
from ..domain.quickadd import parse_quick_add
from ..domain.rules import DomainError, not_found
from ..domain.timeutil import local_date, to_iso, utcnow
from ..integrations import ai
from ..metrics import similarity
from ..store import events, repo
from . import schemas
from .deps import RequestContext, read_connection, request_context, viewer_of

router = APIRouter(prefix="/api")


@router.get("/meta", response_model=schemas.MetaOut, tags=["Sistema"], summary="Configuração pública do servidor")
def meta():
    settings = get_settings()
    return JSONResponse(
        {
            "version": __version__,
            "server_time": to_iso(utcnow()),
            "timezone": settings.timezone,
            "ai_enabled": settings.ai_enabled,
            "ai_model": settings.anthropic_model if settings.ai_enabled else None,
            "email_enabled": settings.email_enabled,
            "telegram_enabled": settings.telegram_enabled,
            "max_upload_mb": settings.max_upload_mb,
            "public_url": settings.public_url,
        }
    )


@router.get("/changes", response_model=schemas.ChangesOut, tags=["Sistema"], summary="O que mudou desde um evento (RNF19)")
def changes(since: int = Query(0, ge=0), conn: sqlite3.Connection = Depends(read_connection)):
    return JSONResponse(events.changes_since(conn, since))


@router.post("/quick-add/parse", response_model=schemas.QuickAddOut, tags=["Produtividade"], summary="Interpretar criação rápida (RF41, RN19)")
def quick_add(body: schemas.QuickAddIn, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    today = local_date(utcnow(), rc.tz)
    known = repo.list_requesters(conn, rc.account_id) if rc.account_id else []
    result = parse_quick_add(body.text, today, known)
    return JSONResponse(
        {
            "title": result.title,
            "due_date": result.due_date.isoformat() if result.due_date else None,
            "difficulty": result.difficulty,
            "requester": result.requester,
            "tokens": [{"text": t.text, "kind": t.kind} for t in result.tokens],
            "errors": result.errors,
        }
    )


@router.post("/steps/parse", response_model=schemas.StepsOut, tags=["Produtividade"], summary="Converter texto colado em etapas (RF44)")
def parse_steps(body: schemas.PasteStepsIn):
    return JSONResponse({"steps": rules.parse_pasted_steps(body.text)})


@router.post("/ai/steps", response_model=schemas.StepsOut, tags=["Produtividade"], summary="Gerar etapas por IA para revisão (RF52, RN26)")
def ai_steps(body: schemas.AIStepsIn):
    title = rules.clean_title(body.title)
    description = rules.clean_text(body.description, 4000)
    try:
        steps = ai.generate_steps(get_settings(), title, description)
    except ai.AIError as exc:
        raise DomainError(exc.message, code="ia_indisponivel", status=exc.status) from None
    return JSONResponse({"steps": steps})


@router.post("/accounts/{account_id}/suggestions", tags=["Produtividade"], summary="Sugerir dificuldade e entrega (RF53, RN27)")
def suggestions(account_id: str, body: schemas.SuggestionIn, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    if repo.get_account(conn, account_id) is None:
        raise not_found("Conta")
    today = local_date(utcnow(), rc.tz)
    return JSONResponse(similarity.suggest(body.title, body.description, repo.list_tasks(conn, account_id), today))


@router.get("/whoami", tags=["Sistema"], summary="Conta identificada pelo cabeçalho X-Account-Id")
def whoami(rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    viewer = viewer_of(conn, rc)
    return JSONResponse({"account_id": viewer.id if viewer else None, "name": viewer.name if viewer else None})
