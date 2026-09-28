"""Linha do tempo da tarefa (RF48, RF60), montada a partir dos eventos imutáveis.

Comentários ficam fora: são visíveis apenas ao Gestor e ao responsável (RN36).
Edições seguidas do mesmo campo, pela mesma pessoa, em até 10 minutos, são agrupadas.
"""

from __future__ import annotations

from datetime import timedelta

from ..domain.constants import DIFFICULTY_LABELS, PHASE_LABELS, POSTPONE_REASONS
from ..domain.timeutil import fmt_date_br, parse_date, parse_iso

MERGE_WINDOW = timedelta(minutes=10)
HIDDEN = {"ComentarioAdicionado", "ComentarioEditado", "ComentarioExcluido", "ComentariosLidos"}


def _date(value: str | None) -> str:
    return fmt_date_br(parse_date(value)) if value else "—"


def _quote(text: str | None, limit: int = 80) -> str:
    text = (text or "").strip()
    return f"“{text[: limit - 1]}…”" if len(text) > limit else f"“{text}”"


def _describe_edit(changes: dict) -> tuple[str, str | None]:
    parts: list[str] = []
    for field, change in changes.items():
        old, new = change.get("old"), change.get("new")
        if field == "title":
            parts.append(f"Título alterado para {_quote(new)}")
        elif field == "description":
            parts.append("Descrição atualizada")
        elif field == "notes":
            parts.append("Anotações atualizadas")
        elif field == "requester":
            parts.append(f"Solicitante: {new or '—'}")
        elif field == "difficulty":
            parts.append(f"Dificuldade: {DIFFICULTY_LABELS.get(old, old)} → {DIFFICULTY_LABELS.get(new, new)}")
        elif field == "links":
            added = [u for u in new or [] if u not in (old or [])]
            removed = [u for u in old or [] if u not in (new or [])]
            if added:
                parts.append("Link adicionado: " + ", ".join(added))
            if removed:
                parts.append("Link removido: " + ", ".join(removed))
    merge_key = f"edit:{next(iter(changes))}" if len(changes) == 1 and set(changes) <= {"title", "description", "notes", "requester"} else None
    return "; ".join(parts) or "Tarefa editada", merge_key


def describe(event: dict) -> dict | None:
    kind = event["type"]
    p = event.get("payload") or {}
    detail = None
    merge_key = None
    icon = "edit"

    if kind in HIDDEN:
        return None
    if kind == "TarefaCriada":
        icon = "create"
        source = p.get("source")
        if source == "assign":
            text = f"Tarefa atribuída por {p.get('assigned_by_name') or 'Gestor'}"
        elif source == "template":
            # Cópia de outra tarefa (ou de um modelo salvo antes da junção de templates com tarefas)
            text = f"Tarefa criada a partir de {_quote(p.get('template_name'))}"
        elif source == "quickadd":
            text = "Tarefa criada pela criação rápida"
        else:
            text = "Tarefa criada"
        steps = len(p.get("steps") or [])
        if steps:
            detail = f"{steps} etapa{'s' if steps > 1 else ''}"
    elif kind == "TarefaEditada":
        text, merge_key = _describe_edit(p.get("changes") or {})
        icon = "notes" if merge_key == "edit:notes" else "edit"
    elif kind == "PrazoAlterado":
        icon = "calendar"
        change = p.get("kind")
        if change == "adiamento":
            text = f"Prazo adiado de {_date(p.get('old'))} para {_date(p.get('new'))}"
            reason = POSTPONE_REASONS.get(p.get("reason") or "", "Outro")
            detail = f"Motivo: {reason}" + (f" — {p.get('reason_text')}" if p.get("reason_text") else "")
            icon = "postpone"
        elif change == "antecipacao":
            text = f"Prazo antecipado de {_date(p.get('old'))} para {_date(p.get('new'))}"
        elif change == "definicao":
            text = f"Prazo definido para {_date(p.get('new'))}"
        else:
            text = f"Prazo removido (era {_date(p.get('old'))})"
    elif kind == "FaseAlterada":
        icon = "phase"
        text = f"Fase: {PHASE_LABELS.get(p.get('old'), p.get('old'))} → {PHASE_LABELS.get(p.get('new'), p.get('new'))}"
    elif kind == "MetaVinculada":
        icon = "goal"
        if p.get("old_goal_title"):
            text = f"Movida da meta {_quote(p.get('old_goal_title'))} para {_quote(p.get('goal_title'))}"
        else:
            text = f"Vinculada à meta {_quote(p.get('goal_title'))}"
    elif kind == "MetaDesvinculada":
        icon = "goal"
        text = f"Desvinculada da meta {_quote(p.get('goal_title'))}"
        if p.get("reason") == "meta_excluida":
            text += " (meta excluída)"
    elif kind == "TarefaConcluida":
        icon = "done"
        text = "Tarefa concluída automaticamente: todas as etapas marcadas" if p.get("auto") else "Tarefa concluída"
    elif kind == "TarefaReaberta":
        icon = "reopen"
        text = "Tarefa reaberta automaticamente" if p.get("auto") else "Tarefa reaberta"
    elif kind == "EtapaAdicionada":
        icon = "step"
        text = f"Etapa adicionada: {_quote(p.get('text'))}"
        if p.get("source") == "ai":
            detail = "Sugerida por IA e confirmada"
        merge_key = f"add:{event.get('mutation_id') or event['seq']}"
    elif kind == "EtapaEditada":
        icon = "step"
        text = f"Etapa renomeada: {_quote(p.get('old_text'))} → {_quote(p.get('text'))}"
        merge_key = f"step:{p.get('step_id')}"
    elif kind == "EtapaConcluida":
        icon = "check"
        text = f"Etapa concluída: {_quote(p.get('text'))}"
    elif kind == "EtapaDesmarcada":
        icon = "uncheck"
        text = f"Etapa desmarcada: {_quote(p.get('text'))}"
    elif kind == "EtapaRemovida":
        icon = "delete"
        text = f"Etapa removida: {_quote(p.get('text'))}"
    elif kind == "EtapasReordenadas":
        icon = "reorder"
        text = "Etapas reordenadas"
        merge_key = "reorder"
    elif kind == "AnexoAdicionado":
        icon = "attach"
        text = f"Anexo adicionado: {p.get('filename')}"
    elif kind == "AnexoRemovido":
        icon = "attach"
        text = f"Anexo removido: {p.get('filename')}"
    elif kind == "AtribuicaoVisualizada":
        icon = "seen"
        text = "Tarefa atribuída visualizada pelo responsável"
    else:
        return None
    return {"icon": icon, "text": text, "detail": detail, "merge_key": merge_key}


def build_timeline(events: list[dict]) -> list[dict]:
    items: list[dict] = []
    for event in events:
        entry = describe(event)
        if entry is None:
            continue
        at = event["occurred_at"]
        last = items[-1] if items else None
        if (
            last is not None
            and entry["merge_key"] is not None
            and last["merge_key"] == entry["merge_key"]
            and last["actor_id"] == event.get("actor_id")
            and parse_iso(at) - parse_iso(last["at"]) <= MERGE_WINDOW  # type: ignore[operator]
        ):
            last["count"] += 1
            last["at"] = max(last["at"], at)
            if entry["merge_key"].startswith("add:"):
                last["text"] = f"{last['count']} etapas adicionadas"
            else:
                last["text"] = entry["text"]
            continue
        items.append(
            {
                "seq": event["seq"],
                "at": at,
                "type": event["type"],
                "actor_id": event.get("actor_id"),
                "actor_name": event.get("actor_name") or "—",
                "icon": entry["icon"],
                "text": entry["text"],
                "detail": entry["detail"],
                "merge_key": entry["merge_key"],
                "count": 1,
            }
        )
    for item in items:
        item.pop("merge_key", None)
    return items
