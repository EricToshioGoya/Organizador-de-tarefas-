"""Modelos do domínio (seção 2.2 — tarefa; 2.8 — meta; 2.7 — conta; evento do calendário; item da Daily; listas)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .constants import (
    DEFAULT_CALENDAR_COLOR,
    DEFAULT_DIFFICULTY,
    DEFAULT_LIST_KIND,
    DEFAULT_PHASE,
    DEFAULT_PRIORITY,
    DONE,
    GOAL_ACTIVE,
    GOAL_DONE,
    PENDING,
    ROLE_MANAGER,
    ROLE_MEMBER,
)


@dataclass
class Step:
    id: str
    text: str
    position: float = 0.0
    done: bool = False
    done_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class Task:
    id: str
    account_id: str
    title: str
    created_at: datetime
    difficulty: str = DEFAULT_DIFFICULTY
    priority: str = DEFAULT_PRIORITY
    description: str = ""
    due_date: date | None = None
    requester: str = ""
    completed_at: datetime | None = None
    status: str = PENDING
    goal_id: str | None = None
    notes: str = ""
    links: list[str] = field(default_factory=list)
    phase: str = DEFAULT_PHASE
    last_activity_at: datetime | None = None
    due_history: list[dict] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    assigned_by: str | None = None
    assigned_by_name: str | None = None
    assigned_seen_at: datetime | None = None

    @property
    def is_done(self) -> bool:
        return self.status == DONE

    @property
    def is_pending(self) -> bool:
        return self.status == PENDING


@dataclass
class Goal:
    id: str
    account_id: str
    title: str
    created_at: datetime
    description: str = ""
    target_date: date | None = None
    completed_at: datetime | None = None
    status: str = GOAL_ACTIVE

    @property
    def is_done(self) -> bool:
        return self.status == GOAL_DONE


@dataclass
class Account:
    id: str
    name: str
    color: str
    role: str = ROLE_MEMBER
    created_at: datetime | None = None
    settings: dict = field(default_factory=dict)

    @property
    def is_manager(self) -> bool:
        return self.role == ROLE_MANAGER


@dataclass
class CalendarEntry:
    """Evento do calendário. Datas e horários são locais e "flutuantes" (sem fuso), como numa agenda.

    Dia inteiro: `start_date` a `end_date`, inclusive, sem horários. Com horário: de `start_date start_time`
    até `end_date end_time` (o término pode cair em outro dia). `recurrence` repete o evento a partir do
    início; `exceptions` são as datas de ocorrências excluídas da série.
    """

    id: str
    account_id: str
    title: str
    start_date: date
    end_date: date
    created_at: datetime | None = None
    updated_at: datetime | None = None
    notes: str = ""
    location: str = ""
    all_day: bool = False
    start_time: str | None = None
    end_time: str | None = None
    color: str = DEFAULT_CALENDAR_COLOR
    private: bool = False
    recurrence: dict | None = None
    exceptions: list[str] = field(default_factory=list)

    @property
    def is_recurring(self) -> bool:
        return bool(self.recurrence)


@dataclass
class DailyItem:
    """Item da Daily: tarefa simples planejada para um dia, como no Microsoft To Do.

    Enquanto não for concluído, um item de dia anterior aparece também no dia de hoje (a interface o mostra
    no topo); `day` continua sendo o dia em que foi planejado.
    """

    id: str
    account_id: str
    title: str
    day: date
    note: str = ""
    done: bool = False
    done_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class UserList:
    """Lista com nome (ex.: "Lista de compras"), visível só para a própria conta.

    `kind` define o modelo: "tarefas" (como a Daily) ou "ranking" (itens em posição reordenável, com quantidade).
    """

    id: str
    account_id: str
    name: str
    kind: str = DEFAULT_LIST_KIND
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class ListItem:
    """Item de uma lista. `position` ordena o ranking; quantidade e unidade são opcionais."""

    id: str
    list_id: str
    account_id: str
    title: str
    note: str = ""
    quantity: float | None = None
    unit: str = ""
    position: int = 0
    done: bool = False
    done_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
