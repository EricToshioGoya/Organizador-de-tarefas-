"""Regras de negócio (seção 3) como funções puras, testáveis sem banco nem HTTP."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

from .constants import (
    ACCOUNT_COLORS,
    COMMENT_MAX,
    DEFAULT_STALE_DAYS,
    DIFFICULTIES,
    DIFFICULTY_POINTS,
    DONE,
    GOAL_ACTIVE,
    GOAL_DONE,
    NAME_MAX,
    PENDING,
    PHASES,
    POSTPONE_REASONS,
    ROLES,
    STEP_MAX,
    TEXT_MAX,
    TITLE_MAX,
    URL_MAX,
)
from .models import Account, Goal, Step, Task
from .timeutil import date_iso, days_between, local_date


class DomainError(ValueError):
    """Violação de regra de negócio. A mensagem é exibida ao usuário, em pt-BR."""

    def __init__(self, message: str, code: str = "invalido", status: int = 422):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def not_found(what: str = "Registro") -> DomainError:
    return DomainError(f"{what} não encontrado(a).", code="nao_encontrado", status=404)


def read_only() -> DomainError:
    return DomainError(
        "Modo somente leitura: esta ação só pode ser feita pela conta responsável.",
        code="somente_leitura",
        status=403,
    )


# ---------------------------------------------------------------------------
# Texto e validação de entrada (RNF13). A saída é sempre escapada na interface;
# aqui removemos caracteres de controle, normalizamos Unicode e limitamos tamanhos.
# ---------------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​  ﻿]")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_SAFE_URL = re.compile(r"^(?:https?://[^\s<>\"'`]+|mailto:[^\s<>\"'`]+)$", re.IGNORECASE)
_EMAIL = re.compile(r"^[^@\s<>\"']+@[^@\s<>\"']+\.[^@\s<>\"']+$")
_TELEGRAM_CHAT = re.compile(r"^(?:-?\d{3,20}|@[A-Za-z][A-Za-z0-9_]{3,40})$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def clean_text(value: object, max_len: int = TEXT_MAX, *, multiline: bool = True) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL_CHARS.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    if multiline:
        text = text.replace("\t", "    ")
    else:
        text = " ".join(text.split())
    if len(text) > max_len:
        raise DomainError(f"O texto excede o limite de {max_len} caracteres.", code="texto_longo")
    return text


def clean_title(value: object) -> str:
    title = clean_text(value, TITLE_MAX, multiline=False)
    if not title:
        raise DomainError("O título é obrigatório.", code="titulo_obrigatorio")
    return title


def clean_name(value: object) -> str:
    name = clean_text(value, NAME_MAX, multiline=False)
    if not name:
        raise DomainError("Informe o nome.", code="nome_obrigatorio")
    return name


def clean_step_text(value: object) -> str:
    text = clean_text(value, STEP_MAX, multiline=False)
    if not text:
        raise DomainError("A etapa precisa de uma descrição.", code="etapa_vazia")
    return text


def clean_comment(value: object) -> str:
    text = clean_text(value, COMMENT_MAX).strip()
    if not text:
        raise DomainError("O comentário está vazio.", code="comentario_vazio")
    return text


def clean_url(value: object) -> str:
    url = clean_text(value, URL_MAX, multiline=False)
    if not url:
        raise DomainError("Informe a URL.", code="url_invalida")
    if not _SCHEME.match(url):
        url = "https://" + url
    if not _SAFE_URL.match(url):
        raise DomainError("URL inválida: use um endereço http://, https:// ou mailto:.", code="url_invalida")
    return url


def clean_links(values: Iterable[object]) -> list[str]:
    links: list[str] = []
    for value in values or []:
        url = clean_url(value)
        if url not in links:
            links.append(url)
    if len(links) > 50:
        raise DomainError("Limite de 50 links por tarefa.", code="limite_links")
    return links


def check_difficulty(value: object) -> str:
    if value not in DIFFICULTIES:
        raise DomainError("Dificuldade inválida: use Fácil, Médio ou Difícil.", code="dificuldade_invalida")
    return str(value)


def check_phase(value: object) -> str:
    if value not in PHASES:
        raise DomainError("Fase inválida.", code="fase_invalida")
    return str(value)


def check_role(value: object) -> str:
    if value not in ROLES:
        raise DomainError("Perfil inválido: use Membro ou Gestor.", code="perfil_invalido")
    return str(value)


def normalize_for_match(text: str) -> str:
    """Sem acentos e sem distinção de maiúsculas (RN19, RF05)."""
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.casefold().split())


# ---------------------------------------------------------------------------
# Contas (RN10, RF25)
# ---------------------------------------------------------------------------


def name_key(name: str) -> str:
    """Chave de unicidade do nome: sem distinção entre maiúsculas e minúsculas (RN10)."""
    return " ".join((name or "").split()).casefold()


def initials(name: str) -> str:
    words = [w for w in re.split(r"[\s\-_.]+", name or "") if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[-1][0]).upper()


def pick_color(name: str, colors_in_use: Iterable[str]) -> str:
    """Cor própria por conta (RF25): a menos usada; empate decidido de forma estável pelo nome."""
    usage = Counter(c for c in colors_in_use if c in ACCOUNT_COLORS)
    least = min(usage.get(c, 0) for c in ACCOUNT_COLORS)
    candidates = [c for c in ACCOUNT_COLORS if usage.get(c, 0) == least]
    digest = int(hashlib.sha1(name_key(name).encode("utf-8")).hexdigest(), 16)
    return candidates[digest % len(candidates)]


# ---------------------------------------------------------------------------
# Progresso e status (RN01–RN05)
# ---------------------------------------------------------------------------


def progress(task: Task) -> int:
    """RN01: etapas concluídas ÷ total × 100 (arredondado para baixo; 100% só quando tudo marcado)."""
    total = len(task.steps)
    if total == 0:
        return 100 if task.is_done else 0
    done = sum(1 for s in task.steps if s.done)
    return math.floor(done * 100 / total)


def ordered_steps(steps: Sequence[Step]) -> list[Step]:
    return sorted(steps, key=lambda s: (s.position, s.created_at or datetime.min))


def next_pending_step(task: Task) -> Step | None:
    """RF45: primeira etapa não marcada, na ordem da lista."""
    for step in ordered_steps(task.steps):
        if not step.done:
            return step
    return None


def status_from_steps(steps: Sequence[Step], current_status: str) -> str:
    """RN02/RN04: com etapas, o status é derivado delas; sem etapas, mantém o atual (RN03)."""
    if not steps:
        return current_status
    return DONE if all(s.done for s in steps) else PENDING


# ---------------------------------------------------------------------------
# Prazos (RN06–RN09, RF15, RN21)
# ---------------------------------------------------------------------------


def is_overdue(task: Task, today: date) -> bool:
    """RN06: pendente com data de entrega anterior à data atual."""
    return task.is_pending and task.due_date is not None and task.due_date < today


def is_due_soon(task: Task, today: date, days: int = 2) -> bool:
    """RF15: pendente com entrega entre hoje e daqui a `days` dias."""
    if not task.is_pending or task.due_date is None:
        return False
    delta = (task.due_date - today).days
    return 0 <= delta <= days


def completed_on_time(task: Task, tz: ZoneInfo) -> bool | None:
    """RN07: concluída até 23:59 da data de entrega (no fuso local). None se não se aplica."""
    if not task.is_done or task.completed_at is None or task.due_date is None:
        return None
    return local_date(task.completed_at, tz) <= task.due_date


def on_time_rate(tasks: Iterable[Task], tz: ZoneInfo) -> float | None:
    """RN08: concluídas no prazo ÷ concluídas com data de entrega (em %)."""
    flags = [f for f in (completed_on_time(t, tz) for t in tasks) if f is not None]
    if not flags:
        return None
    return sum(flags) * 100 / len(flags)


def completion_days(task: Task) -> float | None:
    """RN09: data de conclusão − data de criação, em dias."""
    if not task.is_done or task.completed_at is None:
        return None
    return max(0.0, days_between(task.created_at, task.completed_at))


def classify_due_change(old: date | None, new: date | None) -> str | None:
    if old == new:
        return None
    if old is None:
        return "definicao"
    if new is None:
        return "remocao"
    return "adiamento" if new > old else "antecipacao"


def build_due_change(
    old: date | None,
    new: date | None,
    reason: str | None,
    reason_text: str | None,
) -> dict | None:
    """RN21: adiamento exige motivo (RF47); antecipações e demais mudanças são registradas sem motivo."""
    kind = classify_due_change(old, new)
    if kind is None:
        return None
    text = clean_text(reason_text or "", 500, multiline=False)
    if kind == "adiamento":
        if reason not in POSTPONE_REASONS:
            raise DomainError("Informe o motivo do adiamento.", code="motivo_obrigatorio")
        if reason == "outro" and not text:
            raise DomainError("Descreva o motivo do adiamento.", code="motivo_obrigatorio")
        if reason != "outro":
            text = ""
    else:
        reason, text = None, ""
    return {"old": date_iso(old), "new": date_iso(new), "kind": kind, "reason": reason, "reason_text": text}


def points(difficulty: str) -> int:
    """RN24: Fácil = 1 · Médio = 2 · Difícil = 3."""
    return DIFFICULTY_POINTS.get(difficulty, DIFFICULTY_POINTS["medio"])


# ---------------------------------------------------------------------------
# Tarefa parada (RN22)
# ---------------------------------------------------------------------------


def clean_stale_days(value: object) -> int:
    try:
        days = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise DomainError("Informe um número de dias entre 1 e 90.", code="dias_invalidos") from None
    if not 1 <= days <= 90:
        raise DomainError("Informe um número de dias entre 1 e 90.", code="dias_invalidos")
    return days


def is_stale(task: Task, now: datetime, stale_days: int = DEFAULT_STALE_DAYS) -> bool:
    if not task.is_pending or task.last_activity_at is None:
        return False
    return now - task.last_activity_at > timedelta(days=stale_days)


# ---------------------------------------------------------------------------
# Ordenação (RF14)
# ---------------------------------------------------------------------------


def sort_pending(tasks: Iterable[Task]) -> list[Task]:
    """Pendentes por data de entrega (mais próxima primeiro); sem data ao final."""
    return sorted(tasks, key=lambda t: (t.due_date is None, t.due_date or date.max, t.created_at))


def sort_done(tasks: Iterable[Task]) -> list[Task]:
    """Concluídas por data de conclusão (mais recente primeiro)."""
    return sorted(tasks, key=lambda t: t.completed_at or datetime.min.replace(tzinfo=t.created_at.tzinfo), reverse=True)


# ---------------------------------------------------------------------------
# Metas (RN14–RN17)
# ---------------------------------------------------------------------------


def goal_progress(tasks: Sequence[Task]) -> int:
    """RN14: tarefas concluídas ÷ tarefas vinculadas × 100; sem tarefas: 0%."""
    if not tasks:
        return 0
    return math.floor(sum(1 for t in tasks if t.is_done) * 100 / len(tasks))


def goal_status(tasks: Sequence[Task]) -> str:
    """RN15: concluída quando tem ao menos uma tarefa e todas estão concluídas."""
    if tasks and all(t.is_done for t in tasks):
        return GOAL_DONE
    return GOAL_ACTIVE


def goal_is_overdue(goal: Goal, today: date) -> bool:
    """RN16: em andamento com data-alvo anterior à data atual."""
    return goal.status == GOAL_ACTIVE and goal.target_date is not None and goal.target_date < today


# ---------------------------------------------------------------------------
# Top 3 do dia (RF39, RN18)
# ---------------------------------------------------------------------------


def top3_for_day(record_day: date | None, task_ids: Sequence[str], today: date) -> list[str]:
    return list(task_ids) if record_day == today else []


def validate_top3(
    task_ids: Sequence[str],
    tasks_by_id: dict[str, Task],
    account_id: str,
    already_selected: Sequence[str] = (),
) -> list[str]:
    """RF39: até 3 tarefas pendentes. Tarefas já escolhidas hoje e concluídas depois podem permanecer."""
    unique: list[str] = []
    for task_id in task_ids:
        if task_id not in unique:
            unique.append(task_id)
    if len(unique) > 3:
        raise DomainError("O Top 3 aceita no máximo 3 tarefas.", code="top3_limite")
    for task_id in unique:
        task = tasks_by_id.get(task_id)
        if task is None or task.account_id != account_id:
            raise not_found("Tarefa")
        if not task.is_pending and task_id not in already_selected:
            raise DomainError("Somente tarefas pendentes podem entrar no Top 3.", code="top3_pendente")
    return unique


# ---------------------------------------------------------------------------
# Templates (RN20) e colagem de etapas (RF44)
# ---------------------------------------------------------------------------


def task_from_template(template: dict) -> dict:
    """RN20: título, descrição, dificuldade e etapas; datas e marcações não são copiadas."""
    return {
        "title": template.get("title", ""),
        "description": template.get("description", ""),
        "difficulty": template.get("difficulty") or "medio",
        "steps": [s if isinstance(s, str) else s.get("text", "") for s in template.get("steps", [])],
    }


_LIST_MARKER = re.compile(
    r"^\s*(?:[-*•·◦▪▫‣⁃–—+>]|\[\s?[xX✓]?\s?\]|\(?\d{1,3}[.)]|[a-z]\))\s+"
)


def parse_pasted_steps(text: str) -> list[str]:
    """RF44: uma etapa por linha, descartando linhas vazias e marcadores de lista."""
    steps: list[str] = []
    for raw in (text or "").splitlines():
        line = raw
        for _ in range(2):  # ex.: "- [ ] item"
            stripped = _LIST_MARKER.sub("", line, count=1)
            if stripped == line:
                break
            line = stripped
        line = " ".join(_CONTROL_CHARS.sub("", line).split())
        if line:
            steps.append(line[:STEP_MAX])
    return steps


# ---------------------------------------------------------------------------
# Perfis e permissões de interface (RF37, RN11, RN32, RN33, RN36)
# ---------------------------------------------------------------------------


def can_edit(actor: Account | None, owner_id: str) -> bool:
    """RF37/RN32: somente a própria conta cria, edita, marca e exclui."""
    return actor is not None and actor.id == owner_id


def can_assign(actor: Account | None, target_id: str) -> bool:
    """RF64/RN32: o Gestor pode criar tarefas na conta de outro membro."""
    return actor is not None and actor.is_manager and actor.id != target_id


def can_view_comments(viewer: Account | None, owner_id: str) -> bool:
    """RN36: comentários visíveis somente ao Gestor e ao membro responsável."""
    return viewer is not None and (viewer.id == owner_id or viewer.is_manager)


# ---------------------------------------------------------------------------
# Configurações da conta (RN22, RN29, RF56)
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS: dict = {
    "stale_days": DEFAULT_STALE_DAYS,
    "email": "",
    "telegram_chat_id": "",
    "digest_enabled": False,
    "digest_time": "08:00",
    "digest_channels": [],
    "timezone": "",
}


def merge_settings(stored: dict | None) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in (stored or {}).items() if k in DEFAULT_SETTINGS})
    return merged


def clean_settings_changes(changes: dict) -> dict:
    cleaned: dict = {}
    for key, value in changes.items():
        if key == "stale_days":
            cleaned[key] = clean_stale_days(value)
        elif key == "email":
            email = clean_text(value, 200, multiline=False)
            if email and not _EMAIL.match(email):
                raise DomainError("E-mail inválido.", code="email_invalido")
            cleaned[key] = email
        elif key == "telegram_chat_id":
            chat = clean_text(value, 60, multiline=False)
            if chat and not _TELEGRAM_CHAT.match(chat):
                raise DomainError("ID de chat do Telegram inválido.", code="telegram_invalido")
            cleaned[key] = chat
        elif key == "digest_enabled":
            cleaned[key] = bool(value)
        elif key == "digest_time":
            text = clean_text(value, 5, multiline=False)
            if not _HHMM.match(text):
                raise DomainError("Horário inválido: use HH:MM.", code="horario_invalido")
            cleaned[key] = text
        elif key == "digest_channels":
            channels = [c for c in (value or []) if c in ("email", "telegram")]
            cleaned[key] = sorted(set(channels))
        elif key == "timezone":
            cleaned[key] = clean_text(value, 64, multiline=False)
        else:
            raise DomainError(f"Configuração desconhecida: {key}.", code="configuracao_invalida")
    return cleaned
