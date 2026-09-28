"""Datas, horários e fusos (RN23 — semana de segunda a domingo; RNF16 — fuso local)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
DEFAULT_TZ = "America/Sao_Paulo"


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime | None) -> str | None:
    """Serializa um instante em ISO 8601 UTC com milissegundos (ex.: 2026-09-23T14:05:00.000Z)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    """Lê um instante ISO 8601; sem fuso, assume UTC. Levanta ValueError se inválido."""
    if not value:
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value.strip()[:10])


def date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def get_tz(name: str | None, default: str = DEFAULT_TZ) -> ZoneInfo:
    """Fuso IANA informado pelo navegador; nomes inválidos caem no padrão do servidor."""
    for candidate in (name, default, DEFAULT_TZ):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


def local_date(dt: datetime, tz: ZoneInfo) -> date:
    return dt.astimezone(tz).date()


def today_in(tz: ZoneInfo, now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(tz).date()


def week_start(d: date) -> date:
    """Segunda-feira da semana de `d` (RN23)."""
    return d - timedelta(days=d.weekday())


def week_end(d: date) -> date:
    """Domingo da semana de `d` (RN23)."""
    return week_start(d) + timedelta(days=6)


def fmt_date_br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def days_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 86_400
