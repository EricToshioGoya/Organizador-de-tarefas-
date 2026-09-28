"""Modelos do domínio (seção 2.2 — tarefa; 2.8 — meta; 2.7 — conta)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .constants import (
    DEFAULT_DIFFICULTY,
    DEFAULT_PHASE,
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
