"""Feed de calendário .ics por conta (RF55): datas de entrega como eventos de dia inteiro (RFC 5545)."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..domain import rules
from ..domain.constants import DIFFICULTY_LABELS, PHASE_LABELS
from ..domain.models import Task
from ..domain.timeutil import UTC


def escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Quebra linhas em blocos de até 75 octetos, sem partir caracteres UTF-8."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts: list[str] = []
    current = ""
    size = 0
    limit = 75
    for char in line:
        char_size = len(char.encode("utf-8"))
        if size + char_size > limit:
            parts.append(current)
            current, size, limit = "", 0, 74  # linhas de continuação começam com espaço
        current += char
        size += char_size
    parts.append(current)
    return "\r\n ".join(parts)


def _event(task: Task, stamp: str, base_url: str) -> list[str]:
    due = task.due_date
    assert due is not None
    title = ("✓ " if task.is_done else "") + task.title
    details = [
        f"Dificuldade: {DIFFICULTY_LABELS.get(task.difficulty, task.difficulty)}",
        f"Fase: {PHASE_LABELS.get(task.phase, task.phase)}",
        f"Progresso: {rules.progress(task)}%",
    ]
    if task.requester:
        details.append(f"Solicitante: {task.requester}")
    if task.description:
        details.append("")
        details.append(task.description)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{task.id}@organizador-de-tarefas",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
        f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{escape(title)}",
        f"DESCRIPTION:{escape(chr(10).join(details))}",
        f"CATEGORIES:{escape(DIFFICULTY_LABELS.get(task.difficulty, ''))}",
        "TRANSP:TRANSPARENT",
        f"STATUS:{'CONFIRMED'}",
    ]
    if base_url:
        lines.append(f"URL:{base_url}/#/tarefa/{task.id}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(account_name: str, tasks: list[Task], now: datetime, base_url: str = "") -> str:
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Organizador de Tarefas//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape('Entregas — ' + account_name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for task in sorted((t for t in tasks if t.due_date), key=lambda t: (t.due_date, t.title)):
        lines.extend(_event(task, stamp, base_url))
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
