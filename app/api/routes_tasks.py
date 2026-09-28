"""Rotas de tarefas, etapas, anexos, comentários, linha do tempo, metas e templates."""

from __future__ import annotations

import mimetypes
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..config import get_settings
from ..domain import rules
from ..domain.rules import DomainError, not_found
from ..domain.timeutil import local_date, utcnow
from ..services import commands
from ..services.timeline import build_timeline
from ..store import events, repo
from . import schemas, serializers
from .deps import RequestContext, mutate, read_connection, request_context, viewer_of

router = APIRouter(prefix="/api")

SAFE_INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf", "text/plain"}


def _task_out(ctx, task) -> dict:
    return serializers.task_payload(ctx.conn, task, ctx.actor)


# ---------------------------------------------------------------------------
# Tarefas
# ---------------------------------------------------------------------------


@router.post(
    "/accounts/{account_id}/tasks",
    status_code=201,
    response_model=schemas.TaskOut,
    tags=["Tarefas"],
    summary="Criar tarefa (RF01) ou atribuir a um membro, se Gestor (RF64)",
)
def create_task(account_id: str, body: schemas.TaskCreate, rc: RequestContext = Depends(request_context)):
    data = body.model_dump()
    return mutate(rc, lambda ctx: _task_out(ctx, commands.create_task(ctx, account_id, data)), status=201)


@router.get("/tasks/{task_id}", response_model=schemas.TaskOut, tags=["Tarefas"], summary="Detalhes da tarefa (RF04)")
def get_task(task_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    task = repo.get_task(conn, task_id)
    if task is None:
        raise not_found("Tarefa")
    return JSONResponse(serializers.task_payload(conn, task, viewer_of(conn, rc)))


@router.patch("/tasks/{task_id}", response_model=schemas.TaskOut, tags=["Tarefas"], summary="Editar atributos (RF02, RF47, RF57)")
def update_task(task_id: str, body: schemas.TaskUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: _task_out(ctx, commands.update_task(ctx, task_id, changes)))


@router.delete("/tasks/{task_id}", status_code=204, tags=["Tarefas"], summary="Excluir tarefa (RF03)")
def delete_task(task_id: str, rc: RequestContext = Depends(request_context)):
    uploads = get_settings().uploads_dir
    return mutate(rc, lambda ctx: commands.delete_task(ctx, task_id, uploads))


@router.post("/tasks/{task_id}/status", response_model=schemas.TaskOut, tags=["Tarefas"], summary="Concluir ou reabrir (RN02, RN03)")
def set_status(task_id: str, body: schemas.TaskStatusIn, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _task_out(ctx, commands.set_task_done(ctx, task_id, body.done)))


@router.post("/tasks/{task_id}/seen", response_model=schemas.TaskOut, tags=["Tarefas"], summary="Registrar a primeira visualização de tarefa atribuída (RF65)")
def mark_seen(task_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _task_out(ctx, commands.mark_assignment_seen(ctx, task_id)))


@router.get("/tasks/{task_id}/timeline", response_model=list[schemas.TimelineItem], tags=["Tarefas"], summary="Linha do tempo (RF48, RF60)")
def timeline(task_id: str, conn: sqlite3.Connection = Depends(read_connection)):
    if repo.get_task(conn, task_id) is None:
        raise not_found("Tarefa")
    return JSONResponse(build_timeline(events.task_events(conn, task_id)))


@router.post("/tasks/{task_id}/template", status_code=201, response_model=schemas.TemplateOut, tags=["Templates"], summary="Salvar tarefa como template (RF42)")
def save_as_template(task_id: str, body: schemas.SaveAsTemplate, rc: RequestContext = Depends(request_context)):
    return mutate(
        rc,
        lambda ctx: serializers.template_json(commands.create_template_from_task(ctx, task_id, body.name)),
        status=201,
    )


# ---------------------------------------------------------------------------
# Etapas
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/steps", response_model=schemas.TaskOut, tags=["Etapas"], summary="Incluir etapas (RF07, RF44, RF52)")
def add_steps(task_id: str, body: schemas.StepsAdd, rc: RequestContext = Depends(request_context)):
    items = [s if isinstance(s, str) else s.model_dump() for s in body.steps]
    return mutate(rc, lambda ctx: _task_out(ctx, commands.add_steps(ctx, task_id, items, body.source)))


@router.patch("/tasks/{task_id}/steps/{step_id}", response_model=schemas.TaskOut, tags=["Etapas"], summary="Editar ou marcar etapa (RF08, RF09)")
def update_step(task_id: str, step_id: str, body: schemas.StepUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: _task_out(ctx, commands.update_step(ctx, task_id, step_id, changes)))


@router.delete("/tasks/{task_id}/steps/{step_id}", response_model=schemas.TaskOut, tags=["Etapas"], summary="Remover etapa (RF08)")
def delete_step(task_id: str, step_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _task_out(ctx, commands.delete_step(ctx, task_id, step_id)))


@router.put("/tasks/{task_id}/steps/order", response_model=schemas.TaskOut, tags=["Etapas"], summary="Reordenar etapas (RF11)")
def reorder_steps(task_id: str, body: schemas.StepsOrder, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _task_out(ctx, commands.reorder_steps(ctx, task_id, body.order)))


# ---------------------------------------------------------------------------
# Anexos (RF46)
# ---------------------------------------------------------------------------


@router.post("/tasks/{task_id}/attachments", response_model=schemas.TaskOut, tags=["Anexos"], summary="Anexar arquivo (RF46)")
def upload_attachment(task_id: str, file: UploadFile = File(...), rc: RequestContext = Depends(request_context)):
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    attachment_id = str(uuid.uuid4())
    target = settings.uploads_dir / attachment_id
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise DomainError(f"O arquivo excede o limite de {settings.max_upload_mb} MB.", code="arquivo_grande", status=413)
                out.write(chunk)
        content_type = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
        response = mutate(
            RequestContext(rc.account_id, rc.tz, rc.client_time, None),
            lambda ctx: _task_out(
                ctx, commands.add_attachment(ctx, task_id, attachment_id, file.filename or "arquivo", content_type, size)
            ),
        )
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return response


@router.get("/attachments/{attachment_id}", tags=["Anexos"], summary="Baixar anexo")
def download_attachment(attachment_id: str, conn: sqlite3.Connection = Depends(read_connection)):
    attachment = repo.get_attachment(conn, attachment_id)
    path = get_settings().uploads_dir / attachment_id
    if attachment is None or not path.exists():
        raise not_found("Anexo")
    inline = attachment["content_type"] in SAFE_INLINE_TYPES
    return FileResponse(
        path,
        media_type=attachment["content_type"] if inline else "application/octet-stream",
        filename=attachment["filename"],
        content_disposition_type="inline" if inline else "attachment",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"},
    )


@router.delete("/attachments/{attachment_id}", tags=["Anexos"], summary="Remover anexo")
def delete_attachment(attachment_id: str, rc: RequestContext = Depends(request_context)):
    uploads = get_settings().uploads_dir

    def run(ctx):
        task = commands.remove_attachment(ctx, attachment_id, uploads)
        return _task_out(ctx, task) if task else None

    return mutate(rc, run)


# ---------------------------------------------------------------------------
# Comentários (RF66–RF68)
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}/comments", response_model=list[schemas.CommentOut], tags=["Comentários"], summary="Listar comentários (RN36)")
def list_comments(task_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    task = repo.get_task(conn, task_id)
    if task is None:
        raise not_found("Tarefa")
    if not rules.can_view_comments(viewer_of(conn, rc), task.account_id):
        raise DomainError("Comentários são restritos ao Gestor e ao responsável pela tarefa.", code="comentario_restrito", status=403)
    return JSONResponse([serializers.comment_json(c) for c in repo.list_comments(conn, task_id)])


@router.post("/tasks/{task_id}/comments", status_code=201, response_model=schemas.CommentOut, tags=["Comentários"], summary="Comentar (RF66)")
def add_comment(task_id: str, body: schemas.CommentIn, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: serializers.comment_json(commands.add_comment(ctx, task_id, body.text, body.id)), status=201)


@router.post("/tasks/{task_id}/comments/read", status_code=204, tags=["Comentários"], summary="Marcar comentários como lidos (RF67)")
def read_comments(task_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(RequestContext(rc.account_id, rc.tz, utcnow(), None), lambda ctx: commands.mark_comments_read(ctx, task_id))


@router.patch("/comments/{comment_id}", response_model=schemas.CommentOut, tags=["Comentários"], summary="Editar o próprio comentário (RF68)")
def edit_comment(comment_id: str, body: schemas.CommentUpdate, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: serializers.comment_json(commands.edit_comment(ctx, comment_id, body.text)))


@router.delete("/comments/{comment_id}", status_code=204, tags=["Comentários"], summary="Excluir o próprio comentário (RF68)")
def delete_comment(comment_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_comment(ctx, comment_id))


# ---------------------------------------------------------------------------
# Metas (RF29–RF33)
# ---------------------------------------------------------------------------


def _goal_out(ctx, goal) -> dict:
    tasks = repo.list_goal_tasks(ctx.conn, goal.id)
    return serializers.goal_json(goal, tasks, local_date(utcnow(), ctx.tz))


@router.post("/accounts/{account_id}/goals", status_code=201, response_model=schemas.GoalOut, tags=["Metas"], summary="Criar meta (RF29)")
def create_goal(account_id: str, body: schemas.GoalCreate, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: _goal_out(ctx, commands.create_goal(ctx, account_id, body.model_dump())), status=201)


@router.get("/goals/{goal_id}", response_model=schemas.GoalOut, tags=["Metas"], summary="Detalhar meta (RF33)")
def get_goal(goal_id: str, rc: RequestContext = Depends(request_context), conn: sqlite3.Connection = Depends(read_connection)):
    goal = repo.get_goal(conn, goal_id)
    if goal is None:
        raise not_found("Meta")
    return JSONResponse(serializers.goal_json(goal, repo.list_goal_tasks(conn, goal_id), local_date(utcnow(), rc.tz)))


@router.patch("/goals/{goal_id}", response_model=schemas.GoalOut, tags=["Metas"], summary="Editar meta (RF31)")
def update_goal(goal_id: str, body: schemas.GoalUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: _goal_out(ctx, commands.update_goal(ctx, goal_id, changes)))


@router.delete("/goals/{goal_id}", status_code=204, tags=["Metas"], summary="Excluir meta mantendo as tarefas (RF31, RN17)")
def delete_goal(goal_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_goal(ctx, goal_id))


@router.post("/goals/{goal_id}/tasks", response_model=schemas.GoalOut, tags=["Metas"], summary="Vincular tarefas à meta (RF30)")
def link_tasks(goal_id: str, body: schemas.GoalLink, rc: RequestContext = Depends(request_context)):
    def run(ctx):
        goal = repo.get_goal(ctx.conn, goal_id)
        if goal is None:
            raise not_found("Meta")
        for task_id in body.task_ids:
            commands.update_task(ctx, task_id, {"goal_id": goal_id})
        return _goal_out(ctx, repo.get_goal(ctx.conn, goal_id))

    return mutate(rc, run)


# ---------------------------------------------------------------------------
# Templates (RF42, RF43)
# ---------------------------------------------------------------------------


@router.post("/accounts/{account_id}/templates", status_code=201, response_model=schemas.TemplateOut, tags=["Templates"], summary="Criar template (RF42)")
def create_template(account_id: str, body: schemas.TemplateCreate, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: serializers.template_json(commands.create_template(ctx, account_id, body.model_dump())), status=201)


@router.patch("/templates/{template_id}", response_model=schemas.TemplateOut, tags=["Templates"], summary="Editar template (RF43)")
def update_template(template_id: str, body: schemas.TemplateUpdate, rc: RequestContext = Depends(request_context)):
    changes = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: serializers.template_json(commands.update_template(ctx, template_id, changes)))


@router.delete("/templates/{template_id}", status_code=204, tags=["Templates"], summary="Excluir template (RF43)")
def delete_template(template_id: str, rc: RequestContext = Depends(request_context)):
    return mutate(rc, lambda ctx: commands.delete_template(ctx, template_id))


@router.post("/templates/{template_id}/tasks", status_code=201, response_model=schemas.TaskOut, tags=["Templates"], summary="Criar tarefa a partir do template (RF42, RN20)")
def instantiate_template(template_id: str, body: schemas.TemplateInstantiate, rc: RequestContext = Depends(request_context)):
    overrides = body.model_dump(exclude_unset=True)
    return mutate(rc, lambda ctx: _task_out(ctx, commands.create_task_from_template(ctx, template_id, overrides)), status=201)
