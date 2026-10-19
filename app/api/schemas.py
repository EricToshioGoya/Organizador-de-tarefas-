"""Modelos Pydantic da API: validam as entradas e documentam o contrato no OpenAPI (RNF21)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["facil", "medio", "dificil"]
Priority = Literal["baixa", "media", "alta", "muito_alta"]
Phase = Literal["planejamento", "producao", "alpha", "beta", "concluido"]
Role = Literal["membro", "gestor"]
PostponeReason = Literal["subestimei", "prioridade", "dependencia", "outro"]
Period = Literal["7d", "30d", "90d", "12m", "all"]
CalendarColor = Literal["azul", "verde", "amarelo", "laranja", "vermelho", "roxo", "cinza"]
RecurrenceFreq = Literal["diaria", "semanal", "mensal", "anual"]
ListKind = Literal["tarefas", "ranking"]
Weekday = Annotated[int, Field(ge=0, le=6)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------


class AccountCreate(Model):
    id: str | None = Field(None, description="ID gerado no cliente (opcional; permite reenvio idempotente).")
    name: str = Field(..., description="Nome único, sem distinção entre maiúsculas e minúsculas (RN10).", examples=["Pedro"])


class SettingsUpdate(Model):
    stale_days: int | None = Field(None, description="N dias sem atividade para considerar a tarefa parada (RN22).")
    email: str | None = None
    telegram_chat_id: str | None = None
    digest_enabled: bool | None = None
    digest_time: str | None = Field(None, examples=["08:00"])
    digest_channels: list[Literal["email", "telegram"]] | None = None
    timezone: str | None = Field(None, examples=["America/Sao_Paulo"])


class AccountUpdate(Model):
    name: str | None = None
    role: Role | None = Field(None, description="Membro ou Gestor (RF61).")
    settings: SettingsUpdate | None = None


class StepIn(Model):
    id: str | None = None
    text: str


class TaskCreate(Model):
    id: str | None = None
    title: str = Field(..., examples=["Apresentação do projeto"])
    description: str = ""
    difficulty: Difficulty = "medio"
    priority: Priority = Field("media", description="Ordena as pendentes: Muito alta primeiro.")
    due_date: date | None = None
    requester: str = ""
    goal_id: str | None = None
    notes: str = ""
    links: list[str] = []
    phase: Phase = "planejamento"
    steps: list[StepIn | str] = []
    source: Literal["form", "quickadd", "template", "ai"] | None = None
    template_name: str | None = None


class TaskUpdate(Model):
    title: str | None = None
    description: str | None = None
    difficulty: Difficulty | None = None
    priority: Priority | None = None
    due_date: date | None = Field(None, description="null remove a data de entrega.")
    due_reason: PostponeReason | None = Field(None, description="Obrigatório ao adiar a entrega (RN21, RF47).")
    due_reason_text: str | None = Field(None, description="Obrigatório quando o motivo é 'outro'.")
    requester: str | None = None
    goal_id: str | None = Field(None, description="null desvincula a tarefa da meta.")
    notes: str | None = None
    links: list[str] | None = None
    phase: Phase | None = None


class TaskStatusIn(Model):
    done: bool


class StepsAdd(Model):
    steps: list[StepIn | str]
    source: Literal["form", "paste", "ai"] | None = None


class StepUpdate(Model):
    text: str | None = None
    done: bool | None = None


class StepsOrder(Model):
    order: list[str]


class Top3In(Model):
    task_ids: list[str] = Field(..., description="Até 3 tarefas pendentes (RF39).")


class GoalCreate(Model):
    id: str | None = None
    title: str
    description: str = ""
    target_date: date | None = None
    task_ids: list[str] = []


class GoalUpdate(Model):
    title: str | None = None
    description: str | None = None
    target_date: date | None = None


class GoalLink(Model):
    task_ids: list[str]


class TemplateCreate(Model):
    id: str | None = None
    name: str | None = None
    title: str
    description: str = ""
    difficulty: Difficulty = "medio"
    steps: list[str] = []


class TemplateUpdate(Model):
    name: str | None = None
    title: str | None = None
    description: str | None = None
    difficulty: Difficulty | None = None
    steps: list[str] | None = None


class TemplateInstantiate(Model):
    id: str | None = None
    due_date: date | None = None
    requester: str | None = None
    goal_id: str | None = None
    phase: Phase | None = None


class SaveAsTemplate(Model):
    name: str | None = None


class CommentIn(Model):
    id: str | None = None
    text: str


class CommentUpdate(Model):
    text: str


class QuickAddIn(Model):
    text: str = Field(..., examples=["Apresentação sexta difícil @Carlos"])


class PasteStepsIn(Model):
    text: str


class AIStepsIn(Model):
    title: str
    description: str = ""


class SuggestionIn(Model):
    title: str
    description: str = ""


class DigestTestIn(Model):
    channel: Literal["email", "telegram"]


class RecurrenceIn(Model):
    freq: RecurrenceFreq = Field(..., description="Diária, semanal, mensal (mesmo dia do mês) ou anual.")
    interval: int = Field(1, ge=1, le=99, description="A cada N dias, semanas, meses ou anos.")
    weekdays: list[Weekday] = Field([], description="Semanal: dias da semana (0 = segunda … 6 = domingo). Vazio = dia do início.")
    until: date | None = Field(None, description="Último dia em que uma ocorrência pode começar (inclusive). null = sem fim.")


class CalendarEntryCreate(Model):
    id: str | None = Field(None, description="ID gerado no cliente (opcional; permite reenvio idempotente).")
    title: str = Field(..., examples=["Reunião com o cliente"])
    notes: str = Field("", description="Anotações livres.")
    location: str = ""
    all_day: bool = Field(False, description="Dia inteiro: datas inclusivas, sem horários.")
    start_date: date
    start_time: str | None = Field(None, examples=["14:00"], description="HH:MM (hora local, sem fuso). Ignorado no dia inteiro.")
    end_date: date | None = Field(None, description="Padrão: a data de início.")
    end_time: str | None = Field(None, examples=["15:00"])
    color: CalendarColor = "azul"
    private: bool = Field(False, description="Particular: para as outras contas, aparece só como Ocupado.")
    recurrence: RecurrenceIn | None = None


class CalendarEntryUpdate(Model):
    title: str | None = None
    notes: str | None = None
    location: str | None = None
    all_day: bool | None = None
    start_date: date | None = None
    start_time: str | None = None
    end_date: date | None = None
    end_time: str | None = None
    color: CalendarColor | None = None
    private: bool | None = None
    recurrence: RecurrenceIn | None = Field(None, description="null remove a repetição.")


class OccurrenceEdit(CalendarEntryUpdate):
    id: str | None = Field(None, description="ID do novo evento avulso, gerado no cliente (opcional).")


class DailyItemCreate(Model):
    id: str | None = Field(None, description="ID gerado no cliente (opcional; permite reenvio idempotente).")
    title: str = Field(..., examples=["Responder e-mails"])
    note: str = Field("", description="Anotação livre.")
    day: date | None = Field(None, description="Dia planejado. Padrão: o dia em que a ação ocorreu (fuso do navegador).")


class DailyItemUpdate(Model):
    title: str | None = None
    note: str | None = None
    day: date | None = Field(None, description="Move o item para outro dia.")
    done: bool | None = Field(None, description="Concluir (true) ou reabrir (false).")


class UserListCreate(Model):
    id: str | None = Field(None, description="ID gerado no cliente (opcional; permite reenvio idempotente).")
    name: str = Field(..., examples=["Lista de compras"])
    kind: ListKind = Field("tarefas", description="Modelo: tarefas (como a Daily) ou ranking (posição e quantidade).")


class UserListUpdate(Model):
    name: str | None = None
    kind: ListKind | None = None


class ListItemsOrder(Model):
    order: list[str] = Field(..., description="IDs dos itens na nova ordem do ranking (os omitidos seguem depois).")


class ListItemCreate(Model):
    id: str | None = Field(None, description="ID gerado no cliente (opcional; permite reenvio idempotente).")
    title: str = Field(..., examples=["Arroz"])
    note: str = Field("", description="Anotação livre.")
    quantity: float | None = Field(None, description="Quantidade (maior que zero).", examples=[2])
    unit: str = Field("", description="Unidade da quantidade.", examples=["kg"])
    position: int | None = Field(None, ge=0, description="Posição no ranking. Padrão: no fim.")


class ListItemUpdate(Model):
    title: str | None = None
    note: str | None = None
    quantity: float | None = Field(None, description="Nova quantidade; null remove.")
    unit: str | None = None
    done: bool | None = Field(None, description="Concluir (true) ou reabrir (false).")


# ---------------------------------------------------------------------------
# Saídas (documentação)
# ---------------------------------------------------------------------------


class StepOut(BaseModel):
    id: str
    text: str
    done: bool
    done_at: str | None
    position: float


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    created_at: str


class CommentStats(BaseModel):
    total: int
    unread: int


class TaskOut(BaseModel):
    id: str
    account_id: str
    title: str
    description: str
    difficulty: Difficulty
    priority: Priority
    due_date: str | None
    requester: str
    created_at: str
    completed_at: str | None
    status: Literal["pendente", "concluida"]
    goal_id: str | None
    notes: str
    links: list[str]
    phase: Phase
    last_activity_at: str
    due_history: list[dict]
    assigned_by: str | None
    assigned_by_name: str | None
    assigned_seen_at: str | None
    progress: int
    steps: list[StepOut]
    attachments: list[AttachmentOut]
    comments: CommentStats | None = Field(None, description="Presente apenas para o Gestor e o responsável (RN36).")


class AccountOut(BaseModel):
    id: str
    name: str
    initials: str
    color: str
    role: Role
    created_at: str | None
    pending_tasks: int | None = None
    overdue_tasks: int | None = None
    active_goals: int | None = None
    settings: dict | None = None


class GoalOut(BaseModel):
    id: str
    account_id: str
    title: str
    description: str
    target_date: str | None
    created_at: str
    completed_at: str | None
    status: Literal["andamento", "concluida"]
    progress: int
    done_tasks: int
    total_tasks: int
    overdue: bool


class TemplateOut(BaseModel):
    id: str
    account_id: str
    name: str
    title: str
    description: str
    difficulty: Difficulty
    steps: list[str]
    created_at: str
    updated_at: str


class CommentOut(BaseModel):
    id: str
    task_id: str
    author_id: str
    author_name: str
    text: str
    created_at: str
    edited_at: str | None


class TimelineItem(BaseModel):
    seq: int
    at: str
    type: str
    actor_id: str | None
    actor_name: str
    icon: str
    text: str
    detail: str | None
    count: int


class Top3Out(BaseModel):
    day: str
    task_ids: list[str]


class RecurrenceOut(BaseModel):
    freq: RecurrenceFreq
    interval: int
    weekdays: list[int]
    until: str | None


class CalendarEntryOut(BaseModel):
    id: str
    account_id: str
    title: str
    notes: str
    location: str
    all_day: bool
    start_date: str
    start_time: str | None
    end_date: str
    end_time: str | None
    color: CalendarColor
    private: bool
    redacted: bool = Field(..., description="Evento particular de outra conta: título, local e anotações ocultos.")
    recurrence: RecurrenceOut | None
    exceptions: list[str] = Field(..., description="Datas de ocorrências excluídas da série.")
    created_at: str
    updated_at: str


class OccurrenceOut(BaseModel):
    series: CalendarEntryOut
    entry: CalendarEntryOut


class DailyItemOut(BaseModel):
    id: str
    account_id: str
    day: str = Field(..., description="Dia planejado. Pendente de dia anterior aparece também em Hoje.")
    title: str
    note: str
    done: bool
    done_at: str | None
    created_at: str
    updated_at: str


class UserListOut(BaseModel):
    id: str
    account_id: str
    name: str
    kind: ListKind
    created_at: str
    updated_at: str


class ListItemOut(BaseModel):
    id: str
    list_id: str
    account_id: str
    title: str
    note: str
    quantity: float | None
    unit: str
    position: int = Field(..., description="Ordem no ranking (menor primeiro).")
    done: bool
    done_at: str | None
    created_at: str
    updated_at: str


class ListsOut(BaseModel):
    lists: list[UserListOut]
    items: list[ListItemOut]


class BoardOut(BaseModel):
    seq: int
    account: AccountOut
    own: bool
    can_comment: bool
    tasks: list[TaskOut]
    goals: list[GoalOut]
    templates: list[TemplateOut]
    top3: Top3Out
    requesters: list[str]
    overload: dict
    calendar: list[CalendarEntryOut]
    daily: list[DailyItemOut]
    lists: list[UserListOut] = Field(..., description="Listas da conta (vazio no quadro de outra conta: são privadas).")
    list_items: list[ListItemOut]


class ChangesOut(BaseModel):
    seq: int
    accounts: list[str]
    directory: bool


class QuickAddToken(BaseModel):
    text: str
    kind: Literal["title", "date", "difficulty", "requester"]


class QuickAddOut(BaseModel):
    title: str
    due_date: str | None
    difficulty: Difficulty | None
    requester: str | None
    tokens: list[QuickAddToken]
    errors: list[str]


class StepsOut(BaseModel):
    steps: list[str]


class DrilldownOut(BaseModel):
    title: str
    task_ids: list[str]


class MetaOut(BaseModel):
    version: str
    server_time: str
    timezone: str
    ai_enabled: bool
    ai_model: str | None
    email_enabled: bool
    telegram_enabled: bool
    max_upload_mb: int
    public_url: str
