"""Regras do calendário: validação de eventos, repetição e ocorrências (funções puras).

Horários são "flutuantes" (hora local, sem fuso): um evento das 14:00 às 15:00 aparece nesse horário para
qualquer conta, como numa agenda de papel. A semana vai de segunda a domingo (RN23). A interface repete
estas regras em `web/js/lib/calendar.js` (mesma validação e mesmo cálculo de ocorrências).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from .constants import (
    CALENDAR_COLORS,
    DEFAULT_CALENDAR_COLOR,
    EVENT_MAX_SPAN_DAYS,
    LOCATION_MAX,
    RECURRENCE_FREQS,
    RECURRENCE_MAX_INTERVAL,
    TEXT_MAX,
)
from .models import CalendarEntry
from .rules import DomainError, clean_text, clean_title
from .timeutil import date_iso, parse_date, week_start

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

# Início, término e "dia inteiro" são validados juntos e compartilham o carimbo de conflito "schedule" (RN30).
SCHEDULE_FIELDS = ("all_day", "start_date", "start_time", "end_date", "end_time")
ENTRY_FIELDS = ("title", "notes", "location", "color", "private", *SCHEDULE_FIELDS, "recurrence")


def _date(value: object, label: str) -> date:
    try:
        day = parse_date(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DomainError(f"{label} inválida.", code="data_invalida") from None
    if day is None:
        raise DomainError(f"Informe a {label.lower()}.", code="data_invalida")
    return day


def clean_time(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not _HHMM.match(text):
        raise DomainError(f"{label} inválido: use HH:MM.", code="horario_invalido")
    return text


def minutes(hhmm: str) -> int:
    hours, mins = hhmm.split(":")
    return int(hours) * 60 + int(mins)


def check_color(value: object) -> str:
    if value not in CALENDAR_COLORS:
        raise DomainError("Cor inválida.", code="cor_invalida")
    return str(value)


def clean_schedule(data: dict) -> dict:
    """Dia inteiro (datas inclusivas, sem horários) ou com horário (término depois do início)."""
    all_day = bool(data.get("all_day"))
    start = _date(data.get("start_date"), "Data de início")
    end = _date(data.get("end_date") or start, "Data de término")
    start_time = end_time = None
    if all_day:
        if end < start:
            raise DomainError("O término deve ser no mesmo dia do início ou depois.", code="periodo_invalido")
    else:
        start_time = clean_time(data.get("start_time"), "Horário de início")
        end_time = clean_time(data.get("end_time"), "Horário de término")
        if (end, minutes(end_time)) <= (start, minutes(start_time)):
            raise DomainError("O término deve ser depois do início.", code="periodo_invalido")
    if (end - start).days > EVENT_MAX_SPAN_DAYS:
        raise DomainError(f"Um evento pode durar no máximo {EVENT_MAX_SPAN_DAYS} dias.", code="periodo_invalido")
    return {
        "all_day": all_day,
        "start_date": start.isoformat(),
        "start_time": start_time,
        "end_date": end.isoformat(),
        "end_time": end_time,
    }


def merge_schedule(current: dict, changes: dict) -> dict:
    """Aplica mudanças de data/horário. Mover só o início leva o término junto, mantendo a duração."""
    merged = {field: changes.get(field, current[field]) for field in SCHEDULE_FIELDS}
    moves_start = "start_date" in changes or "start_time" in changes
    keeps_end = "end_date" not in changes and "end_time" not in changes
    if not (moves_start and keeps_end) or bool(merged["all_day"]) != bool(current["all_day"]):
        return merged
    try:
        old_start = _moment(current["start_date"], current["start_time"])
        old_end = _moment(current["end_date"], current["end_time"])
        new_end = _moment(merged["start_date"], merged["start_time"]) + (old_end - old_start)
    except (TypeError, ValueError):
        return merged  # entrada inválida: clean_schedule explica o erro
    merged["end_date"] = new_end.date().isoformat()
    if not merged["all_day"]:
        merged["end_time"] = f"{new_end:%H:%M}"
    return merged


def _moment(day: object, hhmm: object) -> datetime:
    parsed = parse_date(day)  # type: ignore[arg-type]
    if parsed is None:
        raise ValueError("sem data")
    return datetime.combine(parsed, time.fromisoformat(str(hhmm)) if hhmm else time())


def clean_recurrence(value: object, start: date) -> tuple[dict | None, date]:
    """Repetição normalizada e o início ajustado a ela.

    Na repetição semanal, se o dia do início não estiver entre os dias escolhidos, o evento passa a começar
    no primeiro dia escolhido a partir dele (como no Outlook). Sem dias escolhidos, vale o dia do início.
    """
    if not value:
        return None, start
    if not isinstance(value, dict):
        raise DomainError("Repetição inválida.", code="repeticao_invalida")
    freq = value.get("freq")
    if freq not in RECURRENCE_FREQS:
        raise DomainError("Repetição inválida: use diária, semanal, mensal ou anual.", code="repeticao_invalida")
    raw_interval = value.get("interval")
    try:
        interval = 1 if raw_interval is None else int(raw_interval)
    except (TypeError, ValueError):
        interval = 0
    if not 1 <= interval <= RECURRENCE_MAX_INTERVAL:
        raise DomainError(f"O intervalo da repetição vai de 1 a {RECURRENCE_MAX_INTERVAL}.", code="repeticao_invalida")
    weekdays: list[int] = []
    if freq == "semanal":
        try:
            weekdays = sorted({int(d) for d in value.get("weekdays") or [start.weekday()]})
        except (TypeError, ValueError):
            weekdays = [-1]
        if any(not 0 <= d <= 6 for d in weekdays):
            raise DomainError("Dia da semana inválido.", code="repeticao_invalida")
        start += timedelta(days=min((d - start.weekday()) % 7 for d in weekdays))
    until = _date(value["until"], "Data final da repetição") if value.get("until") else None
    if until is not None and until < start:
        raise DomainError("A repetição deve terminar no dia do início ou depois.", code="repeticao_invalida")
    return {"freq": freq, "interval": interval, "weekdays": weekdays, "until": date_iso(until)}, start


def clean_entry(data: dict) -> dict:
    """Valida e normaliza todos os campos de um evento (criação ou resultado de uma edição)."""
    schedule = clean_schedule(data)
    start = date.fromisoformat(schedule["start_date"])
    recurrence, first = clean_recurrence(data.get("recurrence"), start)
    if first != start:
        shift = first - start
        schedule["start_date"] = first.isoformat()
        schedule["end_date"] = (date.fromisoformat(schedule["end_date"]) + shift).isoformat()
    return {
        "title": clean_title(data.get("title")),
        "notes": clean_text(data.get("notes") or "", TEXT_MAX),
        "location": clean_text(data.get("location") or "", LOCATION_MAX, multiline=False),
        "color": check_color(data.get("color") or DEFAULT_CALENDAR_COLOR),
        "private": bool(data.get("private")),
        **schedule,
        "recurrence": recurrence,
    }


def entry_fields(entry: CalendarEntry) -> dict:
    """Campos editáveis do evento no mesmo formato de `clean_entry`."""
    return {
        "title": entry.title,
        "notes": entry.notes,
        "location": entry.location,
        "color": entry.color,
        "private": entry.private,
        "all_day": entry.all_day,
        "start_date": entry.start_date.isoformat(),
        "start_time": entry.start_time,
        "end_date": entry.end_date.isoformat(),
        "end_time": entry.end_time,
        "recurrence": entry.recurrence,
    }


def span_days(entry: CalendarEntry) -> int:
    return (entry.end_date - entry.start_date).days


def occurs_on(entry: CalendarEntry, day: date) -> bool:
    """Se uma ocorrência do evento começa em `day` (ocorrências excluídas não contam).

    Mensal e anual repetem o dia do início; meses sem esse dia (ex.: 31) e 29/02 fora de ano bissexto
    ficam sem ocorrência, como no Google Agenda e na regra RRULE do formato .ics (RFC 5545).
    """
    start = entry.start_date
    if day < start or day.isoformat() in entry.exceptions:
        return False
    rule = entry.recurrence
    if not rule:
        return day == start
    until = parse_date(rule.get("until"))
    if until is not None and day > until:
        return False
    interval = rule.get("interval") or 1
    freq = rule.get("freq")
    if freq == "diaria":
        return (day - start).days % interval == 0
    if freq == "semanal":
        weeks = (week_start(day) - week_start(start)).days // 7
        return day.weekday() in (rule.get("weekdays") or [start.weekday()]) and weeks % interval == 0
    if freq == "mensal":
        months = (day.year - start.year) * 12 + day.month - start.month
        return day.day == start.day and months % interval == 0
    if freq == "anual":
        return (day.month, day.day) == (start.month, start.day) and (day.year - start.year) % interval == 0
    return False


def occurrence_fields(entry: CalendarEntry, day: date) -> dict:
    """Campos de uma ocorrência da série como evento avulso (mesmo horário e duração, sem repetição)."""
    fields = entry_fields(entry)
    fields.update(
        start_date=day.isoformat(),
        end_date=(day + timedelta(days=span_days(entry))).isoformat(),
        recurrence=None,
    )
    return fields
