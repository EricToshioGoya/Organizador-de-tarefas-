"""Criação rápida por texto (RF41, RN19).

Exemplo: "Apresentação sexta difícil @Carlos" →
título "Apresentação", entrega na próxima sexta (incluindo hoje), dificuldade Difícil, solicitante Carlos.

Quando um tipo de marcador aparece mais de uma vez, vale a última ocorrência (os atributos costumam
vir depois do título); as ocorrências anteriores permanecem no título.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable

from .constants import TITLE_MAX
from .rules import normalize_for_match

WEEKDAYS = {
    "segunda": 0,
    "terca": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "domingo": 6,
}
DIFFICULTY_WORDS = {"facil": "facil", "medio": "medio", "dificil": "dificil"}
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?$")
_EDGE_PUNCT = ".,;:!?()[]{}\"'"


@dataclass
class QuickAddToken:
    text: str
    kind: str  # title | date | difficulty | requester


@dataclass
class QuickAddResult:
    title: str
    due_date: date | None = None
    difficulty: str | None = None
    requester: str | None = None
    tokens: list[QuickAddToken] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _core(token: str) -> str:
    return token.strip(_EDGE_PUNCT)


def parse_date_word(word: str, today: date) -> date | None:
    key = normalize_for_match(word)
    if key == "hoje":
        return today
    if key == "amanha":
        return today + timedelta(days=1)
    if key.endswith("-feira"):
        key = key[: -len("-feira")]
    if key in WEEKDAYS:
        return today + timedelta(days=(WEEKDAYS[key] - today.weekday()) % 7)
    match = _DATE.match(key)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
        try:
            if year:
                full_year = int(year) + (2000 if len(year) == 2 else 0)
                return date(full_year, month, day)
            candidate = date(today.year, month, day)
            if candidate < today:  # próxima ocorrência, como nos dias da semana
                candidate = date(today.year + 1, month, day)
            return candidate
        except ValueError:
            return None
    return None


def _canonical_requester(name: str, known: Iterable[str]) -> str:
    wanted = normalize_for_match(name)
    for candidate in known:
        if normalize_for_match(candidate) == wanted:
            return candidate
    return name


def parse_quick_add(text: str, today: date, known_requesters: Iterable[str] = ()) -> QuickAddResult:
    raw_tokens = (text or "").split()
    kinds = ["title"] * len(raw_tokens)
    found: dict[str, int] = {}

    for index in range(len(raw_tokens) - 1, -1, -1):
        core = _core(raw_tokens[index])
        if not core:
            continue
        if "requester" not in found and raw_tokens[index].startswith("@") and len(core.lstrip("@")) > 0:
            found["requester"] = index
            kinds[index] = "requester"
            continue
        key = normalize_for_match(core)
        if "difficulty" not in found and key in DIFFICULTY_WORDS:
            found["difficulty"] = index
            kinds[index] = "difficulty"
            continue
        if "date" not in found and parse_date_word(core, today) is not None:
            found["date"] = index
            kinds[index] = "date"

    result = QuickAddResult(title="")
    if "requester" in found:
        name = _core(raw_tokens[found["requester"]]).lstrip("@").replace("_", " ")
        result.requester = _canonical_requester(" ".join(name.split()), known_requesters)
    if "difficulty" in found:
        result.difficulty = DIFFICULTY_WORDS[normalize_for_match(_core(raw_tokens[found["difficulty"]]))]
    if "date" in found:
        result.due_date = parse_date_word(_core(raw_tokens[found["date"]]), today)

    result.tokens = [QuickAddToken(tok, kind) for tok, kind in zip(raw_tokens, kinds)]
    result.title = " ".join(tok for tok, kind in zip(raw_tokens, kinds) if kind == "title").strip()
    if not result.title:
        result.errors.append("Informe um título além dos atributos.")
    elif len(result.title) > TITLE_MAX:
        result.errors.append(f"O título excede {TITLE_MAX} caracteres.")
    return result
