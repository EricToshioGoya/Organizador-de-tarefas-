"""Contexto de execução de um comando: quem age, quando, em que fuso, e os eventos emitidos."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

from ..domain.models import Account
from ..domain.rules import DomainError
from ..domain.timeutil import local_date, to_iso, utcnow
from ..store import events as event_store
from ..store import projector

_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def new_id() -> str:
    return str(uuid.uuid4())


def clean_id(value: object) -> str | None:
    """IDs gerados no cliente (criação offline) precisam ter formato seguro."""
    if value in (None, ""):
        return None
    text = str(value)
    if not _ID.match(text):
        raise DomainError("Identificador inválido.", code="id_invalido")
    return text


@dataclass
class Ctx:
    conn: sqlite3.Connection
    actor: Account | None
    occurred_at: datetime
    tz: ZoneInfo
    mutation_id: str | None = None
    events: list[dict] = field(default_factory=list)
    post_commit: list[Callable[[], None]] = field(default_factory=list)

    @property
    def ts(self) -> str:
        return to_iso(self.occurred_at)  # type: ignore[return-value]

    @property
    def action_day(self) -> date:
        """Data local em que a ação ocorreu (pode ser anterior à sincronização, se feita offline)."""
        return local_date(self.occurred_at, self.tz)

    def emit(
        self,
        event_type: str,
        aggregate: str,
        aggregate_id: str,
        *,
        account_id: str | None = None,
        task_id: str | None = None,
        payload: dict | None = None,
        actor: tuple[str, str] | None = None,
    ) -> dict:
        actor_id, actor_name = actor or ((self.actor.id, self.actor.name) if self.actor else (None, None))
        event = {
            "id": new_id(),
            "type": event_type,
            "aggregate": aggregate,
            "aggregate_id": aggregate_id,
            "account_id": account_id,
            "task_id": task_id,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "occurred_at": self.ts,
            "recorded_at": to_iso(utcnow()),
            "mutation_id": self.mutation_id,
            "payload": payload or {},
        }
        event["seq"] = event_store.append_event(self.conn, event)
        projector.apply_event(self.conn, event)
        self.events.append(event)
        return event

    def run_post_commit(self) -> None:
        for callback in self.post_commit:
            try:
                callback()
            except OSError:
                pass
