"""Comandos: validam regras (seção 3), emitem eventos imutáveis e aplicam regras derivadas.

Conflitos de sincronização (RN30): cada campo guarda o instante da última alteração; uma alteração
com `occurred_at` mais antigo que a já aplicada é descartada — prevalece a mais recente.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Iterable

from ..domain import rules
from ..domain.constants import (
    DEFAULT_DIFFICULTY,
    DEFAULT_PHASE,
    DONE,
    GOAL_DONE,
    TEXT_MAX,
    TITLE_MAX,
)
from ..domain.models import Account, Goal, Task
from ..domain.rules import DomainError, not_found, read_only
from ..domain.timeutil import date_iso, local_date, parse_date, today_in, utcnow, week_start
from ..metrics import weekly
from ..store import repo
from .context import Ctx, clean_id, new_id

MAX_STEPS = 200
REQUESTER_MAX = 120
TASK_SOURCES = {"form", "quickadd", "template", "ai", "assign", "import"}


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _require_actor(ctx: Ctx) -> Account:
    if ctx.actor is None:
        raise DomainError("Selecione uma conta para continuar.", code="sem_conta", status=401)
    return ctx.actor


def _own(ctx: Ctx, owner_id: str) -> Account:
    actor = _require_actor(ctx)
    if not rules.can_edit(actor, owner_id):
        raise read_only()
    return actor


def _date(value: object, label: str = "Data") -> object:
    try:
        return parse_date(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DomainError(f"{label} inválida.", code="data_invalida") from None


def _newer(ctx: Ctx, stamps: dict, field: str) -> bool:
    return ctx.ts >= stamps.get(field, "")


def _task_for_edit(ctx: Ctx, task_id: str) -> Task:
    task = repo.get_task(ctx.conn, task_id)
    if task is None:
        raise not_found("Tarefa")
    _own(ctx, task.account_id)
    return task


def _goal_for(ctx: Ctx, account_id: str, goal_id: object) -> Goal | None:
    if not goal_id:
        return None
    goal = repo.get_goal(ctx.conn, str(goal_id))
    if goal is None or goal.account_id != account_id:
        raise DomainError("Meta inválida para esta conta.", code="meta_invalida")
    return goal


def _sync_goal_status(ctx: Ctx, goal_id: str | None) -> None:
    """RN15: meta concluída quando todas as tarefas vinculadas estão concluídas."""
    if not goal_id:
        return
    goal = repo.get_goal(ctx.conn, goal_id)
    if goal is None:
        return
    status = rules.goal_status(repo.list_goal_tasks(ctx.conn, goal_id))
    if status != goal.status:
        ctx.emit(
            "MetaConcluida" if status == GOAL_DONE else "MetaReaberta",
            "goal",
            goal_id,
            account_id=goal.account_id,
            payload={"title": goal.title},
        )


def _sync_task_status(ctx: Ctx, task_id: str) -> Task:
    """RN02/RN04: com etapas, o status acompanha as marcações."""
    task = repo.get_task(ctx.conn, task_id)
    assert task is not None
    status = rules.status_from_steps(task.steps, task.status)
    if status != task.status:
        ctx.emit(
            "TarefaConcluida" if status == DONE else "TarefaReaberta",
            "task",
            task_id,
            account_id=task.account_id,
            task_id=task_id,
            payload={"auto": True},
        )
        _sync_goal_status(ctx, task.goal_id)
        task = repo.get_task(ctx.conn, task_id)
        assert task is not None
    return task


def _remove_files(paths: Iterable[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Contas (RF23–RF28, RF61, RN10–RN13)
# ---------------------------------------------------------------------------


def create_account(ctx: Ctx, name: object, account_id: object = None) -> Account:
    clean = rules.clean_name(name)
    key = rules.name_key(clean)
    wanted_id = clean_id(account_id)
    if wanted_id:
        existing = repo.get_account(ctx.conn, wanted_id)
        if existing is not None:
            return existing
    if repo.find_account_by_key(ctx.conn, key):
        raise DomainError(f"Já existe uma conta chamada “{clean}”.", code="nome_em_uso", status=409)
    new_account_id = wanted_id or new_id()
    color = rules.pick_color(clean, repo.account_colors(ctx.conn))
    ctx.emit(
        "ContaCriada",
        "account",
        new_account_id,
        account_id=new_account_id,
        payload={"name": clean, "name_key": key, "color": color, "role": "membro"},
        actor=(new_account_id, clean),
    )
    account = repo.get_account(ctx.conn, new_account_id)
    assert account is not None
    return account


def rename_account(ctx: Ctx, account_id: str, name: object) -> Account:
    _own(ctx, account_id)
    account = repo.get_account(ctx.conn, account_id)
    assert account is not None
    clean = rules.clean_name(name)
    key = rules.name_key(clean)
    other = repo.find_account_by_key(ctx.conn, key)
    if other is not None and other.id != account_id:
        raise DomainError(f"Já existe uma conta chamada “{clean}”.", code="nome_em_uso", status=409)
    if clean != account.name:
        ctx.emit(
            "ContaRenomeada",
            "account",
            account_id,
            account_id=account_id,
            payload={"name": clean, "name_key": key, "old_name": account.name},
        )
    return repo.get_account(ctx.conn, account_id)  # type: ignore[return-value]


def change_role(ctx: Ctx, account_id: str, role: object) -> Account:
    _own(ctx, account_id)
    account = repo.get_account(ctx.conn, account_id)
    assert account is not None
    new_role = rules.check_role(role)
    if new_role != account.role:
        ctx.emit(
            "PerfilAlterado",
            "account",
            account_id,
            account_id=account_id,
            payload={"role": new_role, "old_role": account.role},
        )
    return repo.get_account(ctx.conn, account_id)  # type: ignore[return-value]


def update_settings(ctx: Ctx, account_id: str, changes: dict) -> Account:
    _own(ctx, account_id)
    cleaned = rules.clean_settings_changes(changes or {})
    if cleaned:
        ctx.emit("ConfiguracoesAlteradas", "account", account_id, account_id=account_id, payload={"changes": cleaned})
    return repo.get_account(ctx.conn, account_id)  # type: ignore[return-value]


def delete_account(ctx: Ctx, account_id: str, uploads_dir: Path) -> None:
    """RF27/RN13: exclui a conta com suas tarefas, metas e templates."""
    _own(ctx, account_id)
    account = repo.get_account(ctx.conn, account_id)
    assert account is not None
    task_ids = [t.id for t in repo.list_tasks(ctx.conn, account_id)]
    files = [uploads_dir / a["id"] for items in repo.attachments_by_task(ctx.conn, task_ids).values() for a in items]
    ctx.emit("ContaExcluida", "account", account_id, account_id=account_id, payload={"name": account.name})
    ctx.post_commit.append(lambda: _remove_files(files))


# ---------------------------------------------------------------------------
# Tarefas (RF01–RF06, RF46, RF57, RF64, RN21, RN31, RN33)
# ---------------------------------------------------------------------------


def _clean_steps_input(items: Iterable[object], start: int = 0) -> list[dict]:
    steps: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            text, step_id = item.get("text"), clean_id(item.get("id"))
        else:
            text, step_id = item, None
        if text is None or not str(text).strip():
            continue
        steps.append({"id": step_id or new_id(), "text": rules.clean_step_text(text), "position": start + len(steps)})
    return steps


def create_task(ctx: Ctx, account_id: str, data: dict) -> Task:
    actor = _require_actor(ctx)
    if repo.get_account(ctx.conn, account_id) is None:
        raise not_found("Conta")
    assigned = False
    if not rules.can_edit(actor, account_id):
        if not rules.can_assign(actor, account_id):
            raise read_only()
        assigned = True

    task_id = clean_id(data.get("id")) or new_id()
    existing = repo.get_task(ctx.conn, task_id)
    if existing is not None:
        if existing.account_id == account_id:
            return existing  # reenvio da fila offline (RF71)
        raise DomainError("Identificador de tarefa já utilizado.", code="conflito", status=409)

    goal = _goal_for(ctx, account_id, data.get("goal_id"))
    steps = _clean_steps_input(data.get("steps") or [])
    if len(steps) > MAX_STEPS:
        raise DomainError(f"Limite de {MAX_STEPS} etapas por tarefa.", code="limite_etapas")
    source = data.get("source") if data.get("source") in TASK_SOURCES else "form"
    requester = rules.clean_text(data.get("requester") or "", REQUESTER_MAX, multiline=False)
    payload = {
        "title": rules.clean_title(data.get("title")),
        "description": rules.clean_text(data.get("description") or "", TEXT_MAX),
        "difficulty": rules.check_difficulty(data.get("difficulty") or DEFAULT_DIFFICULTY),
        "due_date": date_iso(_date(data.get("due_date"), "Data de entrega")),  # type: ignore[arg-type]
        "requester": requester,
        "goal_id": goal.id if goal else None,
        "notes": rules.clean_text(data.get("notes") or "", TEXT_MAX),
        "links": rules.clean_links(data.get("links") or []),
        "phase": rules.check_phase(data.get("phase") or DEFAULT_PHASE),
        "steps": steps,
        "source": source,
    }
    if data.get("template_name"):
        payload["template_name"] = rules.clean_text(data["template_name"], TITLE_MAX, multiline=False)
    if assigned:
        # RN33: pertence ao membro destinatário, com o Gestor como solicitante.
        payload.update(
            requester=actor.name,
            assigned_by=actor.id,
            assigned_by_name=actor.name,
            source="assign",
        )
    ctx.emit("TarefaCriada", "task", task_id, account_id=account_id, task_id=task_id, payload=payload)
    _sync_goal_status(ctx, payload["goal_id"])
    return repo.get_task(ctx.conn, task_id)  # type: ignore[return-value]


def update_task(ctx: Ctx, task_id: str, changes: dict) -> Task:
    task = _task_for_edit(ctx, task_id)
    stamps = repo.task_field_ts(ctx.conn, task_id)

    text_changes: dict[str, dict] = {}
    cleaners = {
        "title": rules.clean_title,
        "description": lambda v: rules.clean_text(v or "", TEXT_MAX),
        "notes": lambda v: rules.clean_text(v or "", TEXT_MAX),
        "requester": lambda v: rules.clean_text(v or "", REQUESTER_MAX, multiline=False),
        "difficulty": rules.check_difficulty,
        "links": lambda v: rules.clean_links(v or []),
    }
    for field, clean in cleaners.items():
        if field in changes and _newer(ctx, stamps, field):
            new_value = clean(changes[field])
            old_value = getattr(task, field)
            if new_value != old_value:
                text_changes[field] = {"old": old_value, "new": new_value}
    if text_changes:
        ctx.emit("TarefaEditada", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"changes": text_changes})

    if "phase" in changes and _newer(ctx, stamps, "phase"):
        phase = rules.check_phase(changes["phase"])
        if phase != task.phase:
            ctx.emit("FaseAlterada", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"old": task.phase, "new": phase})

    if "due_date" in changes and _newer(ctx, stamps, "due_date"):
        new_due = _date(changes["due_date"], "Data de entrega")
        change = rules.build_due_change(task.due_date, new_due, changes.get("due_reason"), changes.get("due_reason_text"))  # type: ignore[arg-type]
        if change:
            ctx.emit("PrazoAlterado", "task", task_id, account_id=task.account_id, task_id=task_id, payload=change)

    if "goal_id" in changes and _newer(ctx, stamps, "goal_id"):
        new_goal = _goal_for(ctx, task.account_id, changes["goal_id"])
        new_goal_id = new_goal.id if new_goal else None
        if new_goal_id != task.goal_id:
            old_goal = repo.get_goal(ctx.conn, task.goal_id) if task.goal_id else None
            if new_goal is not None:
                ctx.emit(
                    "MetaVinculada",
                    "task",
                    task_id,
                    account_id=task.account_id,
                    task_id=task_id,
                    payload={
                        "goal_id": new_goal.id,
                        "goal_title": new_goal.title,
                        "old_goal_id": task.goal_id,
                        "old_goal_title": old_goal.title if old_goal else None,
                    },
                )
            else:
                ctx.emit(
                    "MetaDesvinculada",
                    "task",
                    task_id,
                    account_id=task.account_id,
                    task_id=task_id,
                    payload={"old_goal_id": task.goal_id, "goal_title": old_goal.title if old_goal else None},
                )
            _sync_goal_status(ctx, task.goal_id)
            _sync_goal_status(ctx, new_goal_id)

    return repo.get_task(ctx.conn, task_id)  # type: ignore[return-value]


def set_task_done(ctx: Ctx, task_id: str, done: bool) -> Task:
    """RN03: sem etapas, conclui/reabre pelo checkbox. Com etapas, concluir marca as restantes (RN02)."""
    task = _task_for_edit(ctx, task_id)
    if task.steps:
        if done:
            for step in rules.ordered_steps(task.steps):
                if not step.done:
                    ctx.emit(
                        "EtapaConcluida",
                        "task",
                        task_id,
                        account_id=task.account_id,
                        task_id=task_id,
                        payload={"step_id": step.id, "text": step.text},
                    )
            return _sync_task_status(ctx, task_id)
        if task.is_done:
            raise DomainError(
                "Esta tarefa tem etapas: desmarque uma etapa para reabri-la.",
                code="reabrir_por_etapa",
            )
        return task

    stamps = repo.task_field_ts(ctx.conn, task_id)
    if not _newer(ctx, stamps, "status"):
        return task
    if done and task.is_pending:
        ctx.emit("TarefaConcluida", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"auto": False})
    elif not done and task.is_done:
        ctx.emit("TarefaReaberta", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"auto": False})
    else:
        return task
    _sync_goal_status(ctx, task.goal_id)
    return repo.get_task(ctx.conn, task_id)  # type: ignore[return-value]


def delete_task(ctx: Ctx, task_id: str, uploads_dir: Path) -> None:
    task = repo.get_task(ctx.conn, task_id)
    if task is None:
        return  # já excluída (reenvio)
    _own(ctx, task.account_id)
    files = [uploads_dir / a["id"] for a in repo.attachments_by_task(ctx.conn, [task_id]).get(task_id, [])]
    ctx.emit("TarefaExcluida", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"title": task.title})
    _sync_goal_status(ctx, task.goal_id)
    ctx.post_commit.append(lambda: _remove_files(files))


def mark_assignment_seen(ctx: Ctx, task_id: str) -> Task:
    """RF65: o destaque da tarefa atribuída some na primeira visualização pelo responsável."""
    task = repo.get_task(ctx.conn, task_id)
    if task is None:
        raise not_found("Tarefa")
    actor = _require_actor(ctx)
    if actor.id == task.account_id and task.assigned_by and task.assigned_seen_at is None:
        ctx.emit("AtribuicaoVisualizada", "task", task_id, account_id=task.account_id, task_id=task_id)
        task = repo.get_task(ctx.conn, task_id)  # type: ignore[assignment]
    return task  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Etapas (RF07–RF11, RF44, RF52)
# ---------------------------------------------------------------------------


def add_steps(ctx: Ctx, task_id: str, items: Iterable[object], source: str | None = None) -> Task:
    task = _task_for_edit(ctx, task_id)
    existing_ids = {s.id for s in task.steps}
    start = int(max((s.position for s in task.steps), default=-1)) + 1
    steps = [s for s in _clean_steps_input(items, start) if s["id"] not in existing_ids]
    if len(task.steps) + len(steps) > MAX_STEPS:
        raise DomainError(f"Limite de {MAX_STEPS} etapas por tarefa.", code="limite_etapas")
    for step in steps:
        payload = {"step_id": step["id"], "text": step["text"], "position": step["position"]}
        if source:
            payload["source"] = source
        ctx.emit("EtapaAdicionada", "task", task_id, account_id=task.account_id, task_id=task_id, payload=payload)
    return _sync_task_status(ctx, task_id)


def update_step(ctx: Ctx, task_id: str, step_id: str, changes: dict) -> Task:
    task = _task_for_edit(ctx, task_id)
    step = next((s for s in task.steps if s.id == step_id), None)
    if step is None:
        raise not_found("Etapa")
    stamps = repo.step_field_ts(ctx.conn, step_id)
    if "text" in changes and _newer(ctx, stamps, "text"):
        text = rules.clean_step_text(changes["text"])
        if text != step.text:
            ctx.emit(
                "EtapaEditada",
                "task",
                task_id,
                account_id=task.account_id,
                task_id=task_id,
                payload={"step_id": step_id, "text": text, "old_text": step.text},
            )
    if "done" in changes and _newer(ctx, stamps, "done"):
        done = bool(changes["done"])
        if done != step.done:
            ctx.emit(
                "EtapaConcluida" if done else "EtapaDesmarcada",
                "task",
                task_id,
                account_id=task.account_id,
                task_id=task_id,
                payload={"step_id": step_id, "text": step.text},
            )
    return _sync_task_status(ctx, task_id)


def delete_step(ctx: Ctx, task_id: str, step_id: str) -> Task:
    task = _task_for_edit(ctx, task_id)
    step = next((s for s in task.steps if s.id == step_id), None)
    if step is None:
        return task
    ctx.emit(
        "EtapaRemovida",
        "task",
        task_id,
        account_id=task.account_id,
        task_id=task_id,
        payload={"step_id": step_id, "text": step.text},
    )
    return _sync_task_status(ctx, task_id)


def reorder_steps(ctx: Ctx, task_id: str, order: list[str]) -> Task:
    task = _task_for_edit(ctx, task_id)
    current = [s.id for s in rules.ordered_steps(task.steps)]
    wanted = [sid for sid in dict.fromkeys(order or []) if sid in current]
    wanted += [sid for sid in current if sid not in wanted]
    stamps = repo.task_field_ts(ctx.conn, task_id)
    if wanted != current and _newer(ctx, stamps, "order"):
        ctx.emit("EtapasReordenadas", "task", task_id, account_id=task.account_id, task_id=task_id, payload={"order": wanted})
    return repo.get_task(ctx.conn, task_id)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Anexos (RF46)
# ---------------------------------------------------------------------------


def add_attachment(ctx: Ctx, task_id: str, attachment_id: str, filename: str, content_type: str, size: int) -> Task:
    task = _task_for_edit(ctx, task_id)
    name = rules.clean_text(filename, 255, multiline=False).replace("/", "_").replace("\\", "_") or "arquivo"
    ctx.emit(
        "AnexoAdicionado",
        "task",
        task_id,
        account_id=task.account_id,
        task_id=task_id,
        payload={"attachment_id": attachment_id, "filename": name, "content_type": content_type, "size": size},
    )
    return repo.get_task(ctx.conn, task_id)  # type: ignore[return-value]


def remove_attachment(ctx: Ctx, attachment_id: str, uploads_dir: Path) -> Task | None:
    attachment = repo.get_attachment(ctx.conn, attachment_id)
    if attachment is None:
        return None
    task = _task_for_edit(ctx, attachment["task_id"])
    ctx.emit(
        "AnexoRemovido",
        "task",
        task.id,
        account_id=task.account_id,
        task_id=task.id,
        payload={"attachment_id": attachment_id, "filename": attachment["filename"]},
    )
    ctx.post_commit.append(lambda: _remove_files([uploads_dir / attachment_id]))
    return repo.get_task(ctx.conn, task.id)


# ---------------------------------------------------------------------------
# Metas (RF29–RF33, RN14–RN17)
# ---------------------------------------------------------------------------


def create_goal(ctx: Ctx, account_id: str, data: dict) -> Goal:
    _own(ctx, account_id)
    goal_id = clean_id(data.get("id")) or new_id()
    existing = repo.get_goal(ctx.conn, goal_id)
    if existing is not None:
        if existing.account_id == account_id:
            return existing
        raise DomainError("Identificador de meta já utilizado.", code="conflito", status=409)
    target = _date(data.get("target_date"), "Data-alvo")
    payload = {
        "title": rules.clean_title(data.get("title")),
        "description": rules.clean_text(data.get("description") or "", TEXT_MAX),
        "target_date": date_iso(target),  # type: ignore[arg-type]
    }
    ctx.emit("MetaCriada", "goal", goal_id, account_id=account_id, payload=payload)
    for task_id in data.get("task_ids") or []:
        update_task(ctx, str(task_id), {"goal_id": goal_id})
    return repo.get_goal(ctx.conn, goal_id)  # type: ignore[return-value]


def update_goal(ctx: Ctx, goal_id: str, changes: dict) -> Goal:
    goal = repo.get_goal(ctx.conn, goal_id)
    if goal is None:
        raise not_found("Meta")
    _own(ctx, goal.account_id)
    stamps = repo.goal_field_ts(ctx.conn, goal_id)
    diff: dict[str, dict] = {}
    if "title" in changes and _newer(ctx, stamps, "title"):
        title = rules.clean_title(changes["title"])
        if title != goal.title:
            diff["title"] = {"old": goal.title, "new": title}
    if "description" in changes and _newer(ctx, stamps, "description"):
        description = rules.clean_text(changes["description"] or "", TEXT_MAX)
        if description != goal.description:
            diff["description"] = {"old": goal.description, "new": description}
    if "target_date" in changes and _newer(ctx, stamps, "target_date"):
        target = date_iso(_date(changes["target_date"], "Data-alvo"))  # type: ignore[arg-type]
        if target != date_iso(goal.target_date):
            diff["target_date"] = {"old": date_iso(goal.target_date), "new": target}
    if diff:
        ctx.emit("MetaEditada", "goal", goal_id, account_id=goal.account_id, payload={"changes": diff})
    return repo.get_goal(ctx.conn, goal_id)  # type: ignore[return-value]


def delete_goal(ctx: Ctx, goal_id: str) -> None:
    goal = repo.get_goal(ctx.conn, goal_id)
    if goal is None:
        return
    _own(ctx, goal.account_id)
    for task in repo.list_goal_tasks(ctx.conn, goal_id):
        ctx.emit(
            "MetaDesvinculada",
            "task",
            task.id,
            account_id=task.account_id,
            task_id=task.id,
            payload={"old_goal_id": goal_id, "goal_title": goal.title, "reason": "meta_excluida"},
        )
    ctx.emit("MetaExcluida", "goal", goal_id, account_id=goal.account_id, payload={"title": goal.title})


# ---------------------------------------------------------------------------
# Templates (RF42, RF43, RN20)
# ---------------------------------------------------------------------------


def _template_payload(data: dict) -> dict:
    title = rules.clean_title(data.get("title"))
    name = rules.clean_text(data.get("name") or title, TITLE_MAX, multiline=False) or title
    steps = [s["text"] for s in _clean_steps_input(data.get("steps") or [])]
    if len(steps) > MAX_STEPS:
        raise DomainError(f"Limite de {MAX_STEPS} etapas por template.", code="limite_etapas")
    return {
        "name": name,
        "title": title,
        "description": rules.clean_text(data.get("description") or "", TEXT_MAX),
        "difficulty": rules.check_difficulty(data.get("difficulty") or DEFAULT_DIFFICULTY),
        "steps": steps,
    }


def create_template(ctx: Ctx, account_id: str, data: dict) -> dict:
    _own(ctx, account_id)
    template_id = clean_id(data.get("id")) or new_id()
    if repo.get_template(ctx.conn, template_id) is not None:
        return repo.get_template(ctx.conn, template_id)  # type: ignore[return-value]
    ctx.emit("TemplateCriado", "template", template_id, account_id=account_id, payload=_template_payload(data))
    return repo.get_template(ctx.conn, template_id)  # type: ignore[return-value]


def create_template_from_task(ctx: Ctx, task_id: str, name: object = None) -> dict:
    """RF42: salva a tarefa e suas etapas como modelo."""
    task = _task_for_edit(ctx, task_id)
    return create_template(
        ctx,
        task.account_id,
        {
            "name": name or task.title,
            "title": task.title,
            "description": task.description,
            "difficulty": task.difficulty,
            "steps": [s.text for s in rules.ordered_steps(task.steps)],
        },
    )


def update_template(ctx: Ctx, template_id: str, changes: dict) -> dict:
    template = repo.get_template(ctx.conn, template_id)
    if template is None:
        raise not_found("Template")
    _own(ctx, template["account_id"])
    merged = {k: changes.get(k, template[k]) for k in ("name", "title", "description", "difficulty", "steps")}
    payload = _template_payload(merged)
    diff = {k: {"old": template[k], "new": v} for k, v in payload.items() if template[k] != v}
    if diff:
        ctx.emit("TemplateEditado", "template", template_id, account_id=template["account_id"], payload={"changes": diff})
    return repo.get_template(ctx.conn, template_id)  # type: ignore[return-value]


def delete_template(ctx: Ctx, template_id: str) -> None:
    template = repo.get_template(ctx.conn, template_id)
    if template is None:
        return
    _own(ctx, template["account_id"])
    ctx.emit("TemplateExcluido", "template", template_id, account_id=template["account_id"], payload={"name": template["name"]})


def create_task_from_template(ctx: Ctx, template_id: str, overrides: dict) -> Task:
    """RN20: copia título, descrição, dificuldade e etapas; datas e marcações não são copiadas."""
    template = repo.get_template(ctx.conn, template_id)
    if template is None:
        raise not_found("Template")
    _own(ctx, template["account_id"])
    data = rules.task_from_template(template)
    for key in ("id", "due_date", "requester", "goal_id", "phase"):
        if key in overrides:
            data[key] = overrides[key]
    data.update(source="template", template_name=template["name"])
    return create_task(ctx, template["account_id"], data)


# ---------------------------------------------------------------------------
# Top 3 do dia (RF39, RN18)
# ---------------------------------------------------------------------------


def set_top3(ctx: Ctx, account_id: str, task_ids: list[str]) -> list[str]:
    _own(ctx, account_id)
    day = ctx.action_day
    tasks = {t.id: t for t in repo.list_tasks(ctx.conn, account_id)}
    already = repo.get_top3(ctx.conn, account_id, day)
    ids = rules.validate_top3([str(t) for t in task_ids or []], tasks, account_id, already)
    if ids != already:
        ctx.emit(
            "Top3Definido",
            "top3",
            f"{account_id}:{day.isoformat()}",
            account_id=account_id,
            payload={"day": day.isoformat(), "task_ids": ids},
        )
    return ids


# ---------------------------------------------------------------------------
# Comentários (RF66–RF68, RN36)
# ---------------------------------------------------------------------------


def _task_for_comments(ctx: Ctx, task_id: str) -> tuple[Account, Task]:
    actor = _require_actor(ctx)
    task = repo.get_task(ctx.conn, task_id)
    if task is None:
        raise not_found("Tarefa")
    if not rules.can_view_comments(actor, task.account_id):
        raise DomainError(
            "Comentários são restritos ao Gestor e ao responsável pela tarefa.",
            code="comentario_restrito",
            status=403,
        )
    return actor, task


def add_comment(ctx: Ctx, task_id: str, text: object, comment_id: object = None) -> dict:
    actor, task = _task_for_comments(ctx, task_id)
    cid = clean_id(comment_id) or new_id()
    existing = repo.get_comment(ctx.conn, cid)
    if existing is not None:
        return existing
    body = rules.clean_comment(text)
    ctx.emit(
        "ComentarioAdicionado",
        "comment",
        cid,
        account_id=task.account_id,
        task_id=task_id,
        payload={"comment_id": cid, "text": body, "author_name": actor.name},
    )
    ctx.emit("ComentariosLidos", "comment", cid, account_id=task.account_id, task_id=task_id, payload={"read_at": ctx.ts})
    return repo.get_comment(ctx.conn, cid)  # type: ignore[return-value]


def _own_comment(ctx: Ctx, comment_id: str) -> tuple[dict, Task]:
    comment = repo.get_comment(ctx.conn, comment_id)
    if comment is None:
        raise not_found("Comentário")
    actor, task = _task_for_comments(ctx, comment["task_id"])
    if actor.id != comment["author_id"]:
        raise DomainError("Você só pode alterar os seus próprios comentários.", code="comentario_alheio", status=403)
    return comment, task


def edit_comment(ctx: Ctx, comment_id: str, text: object) -> dict:
    comment, task = _own_comment(ctx, comment_id)
    body = rules.clean_comment(text)
    if body != comment["text"]:
        ctx.emit(
            "ComentarioEditado",
            "comment",
            comment_id,
            account_id=task.account_id,
            task_id=task.id,
            payload={"comment_id": comment_id, "text": body},
        )
    return repo.get_comment(ctx.conn, comment_id)  # type: ignore[return-value]


def delete_comment(ctx: Ctx, comment_id: str) -> None:
    comment = repo.get_comment(ctx.conn, comment_id)
    if comment is None:
        return
    _, task = _own_comment(ctx, comment_id)
    ctx.emit("ComentarioExcluido", "comment", comment_id, account_id=task.account_id, task_id=task.id, payload={"comment_id": comment_id})


def mark_comments_read(ctx: Ctx, task_id: str) -> None:
    actor, task = _task_for_comments(ctx, task_id)
    last_read = repo.last_comment_read(ctx.conn, actor.id, task_id) or ""
    unread = [
        c for c in repo.list_comments(ctx.conn, task_id) if c["author_id"] != actor.id and c["created_at"] > last_read
    ]
    if unread:
        newest = max(c["created_at"] for c in unread)
        ctx.emit(
            "ComentariosLidos",
            "comment",
            task_id,
            account_id=task.account_id,
            task_id=task_id,
            payload={"read_at": max(newest, ctx.ts)},
        )


# ---------------------------------------------------------------------------
# Revisão semanal (RF51)
# ---------------------------------------------------------------------------


def ensure_weekly_review(ctx: Ctx, account_id: str) -> dict | None:
    """Gera (uma vez) a revisão da semana anterior, exibida no primeiro acesso da semana."""
    _own(ctx, account_id)
    account = repo.get_account(ctx.conn, account_id)
    assert account is not None
    today = today_in(ctx.tz, utcnow())
    current_week = week_start(today)
    last_week = current_week - timedelta(days=7)
    if account.created_at is None or local_date(account.created_at, ctx.tz) >= current_week:
        return None
    existing = repo.get_weekly_review(ctx.conn, account_id, last_week)
    if existing is not None:
        return existing
    summary = weekly.weekly_review(repo.list_tasks(ctx.conn, account_id), last_week, ctx.tz)
    ctx.emit(
        "RevisaoSemanalGerada",
        "review",
        f"{account_id}:{last_week.isoformat()}",
        account_id=account_id,
        payload={"week_start": last_week.isoformat(), "summary": summary},
    )
    return repo.get_weekly_review(ctx.conn, account_id, last_week)


def mark_review_seen(ctx: Ctx, account_id: str, week: str) -> None:
    _own(ctx, account_id)
    week_date = _date(week, "Semana")
    review = repo.get_weekly_review(ctx.conn, account_id, week_date)  # type: ignore[arg-type]
    if review is not None and not review["seen_at"]:
        ctx.emit(
            "RevisaoSemanalVista",
            "review",
            f"{account_id}:{week_date}",
            account_id=account_id,
            payload={"week_start": review["week_start"]},
        )
