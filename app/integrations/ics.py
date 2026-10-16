"""Feed de calendário .ics por conta (RF55): datas de entrega como eventos de dia inteiro e os eventos do
calendário com horário local "flutuante", repetição (RRULE) e ocorrências excluídas (EXDATE) — RFC 5545."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

from ..domain import rules
from ..domain.constants import DIFFICULTY_LABELS, PHASE_LABELS, PRIVATE_EVENT_TITLE
from ..domain.models import CalendarEntry, Task
from ..domain.timeutil import UTC, parse_date

RRULE_FREQ = {"diaria": "DAILY", "semanal": "WEEKLY", "mensal": "MONTHLY", "anual": "YEARLY"}
RRULE_DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


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


def _local(day: date, hhmm: str) -> str:
    return f"{day:%Y%m%d}T{hhmm.replace(':', '')}00"


def _rrule(entry: CalendarEntry) -> str:
    rule = entry.recurrence or {}
    parts = [f"FREQ={RRULE_FREQ[rule['freq']]}", f"INTERVAL={rule.get('interval') or 1}"]
    if rule["freq"] == "semanal":
        days = rule.get("weekdays") or [entry.start_date.weekday()]
        parts += [f"BYDAY={','.join(RRULE_DAYS[d] for d in days)}", "WKST=MO"]
    until = parse_date(rule.get("until"))
    if until is not None:
        # UNTIL acompanha o tipo do DTSTART: data no dia inteiro, data e hora local nos demais
        parts.append(f"UNTIL={until:%Y%m%d}" if entry.all_day else f"UNTIL={_local(until, '23:59')}")
    return "RRULE:" + ";".join(parts)


def _entry_event(entry: CalendarEntry, stamp: str, base_url: str) -> list[str]:
    """Evento do calendário. Particular aparece só como Ocupado: o endereço do feed não tem senha (RN11)."""
    lines = ["BEGIN:VEVENT", f"UID:agenda-{entry.id}@organizador-de-tarefas", f"DTSTAMP:{stamp}"]
    if entry.all_day:
        lines += [
            f"DTSTART;VALUE=DATE:{entry.start_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{entry.end_date + timedelta(days=1):%Y%m%d}",
            "TRANSP:TRANSPARENT",
        ]
    else:
        lines += [
            f"DTSTART:{_local(entry.start_date, entry.start_time or '00:00')}",
            f"DTEND:{_local(entry.end_date, entry.end_time or '00:00')}",
            "TRANSP:OPAQUE",
        ]
    if entry.private:
        lines += [f"SUMMARY:{PRIVATE_EVENT_TITLE}", "CLASS:PRIVATE"]
    else:
        lines.append(f"SUMMARY:{escape(entry.title)}")
        if entry.location:
            lines.append(f"LOCATION:{escape(entry.location)}")
        if entry.notes:
            lines.append(f"DESCRIPTION:{escape(entry.notes)}")
    if entry.recurrence:
        lines.append(_rrule(entry))
        if entry.exceptions:
            if entry.all_day:
                dates = ",".join(f"{parse_date(d):%Y%m%d}" for d in entry.exceptions)
                lines.append(f"EXDATE;VALUE=DATE:{dates}")
            else:
                dates = ",".join(_local(parse_date(d), entry.start_time or "00:00") for d in entry.exceptions)  # type: ignore[arg-type]
                lines.append(f"EXDATE:{dates}")
    if base_url:
        lines.append(f"URL:{base_url}/#/calendario?semana={entry.start_date.isoformat()}")
    lines.append("END:VEVENT")
    return lines


def build_calendar(
    account_name: str,
    tasks: list[Task],
    now: datetime,
    base_url: str = "",
    entries: Iterable[CalendarEntry] = (),
) -> str:
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Organizador de Tarefas//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape('Organizador — ' + account_name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for task in sorted((t for t in tasks if t.due_date), key=lambda t: (t.due_date, t.title)):
        lines.extend(_event(task, stamp, base_url))
    for entry in entries:
        lines.extend(_entry_event(entry, stamp, base_url))
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
