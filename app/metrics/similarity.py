"""Sugestão de dificuldade e prazo por similaridade (RF53, RN27).

TF-IDF (idf suavizado) com similaridade de cosseno entre a nova tarefa e as concluídas da conta.
- Ativação a partir de 5 tarefas concluídas.
- Dificuldade: a mais frequente entre as 5 mais semelhantes (empate: maior similaridade acumulada).
- Entrega: data atual + mediana do tempo de conclusão dessas tarefas (RN09), arredondada ao dia.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Iterable

from ..domain import rules
from ..domain.constants import DIFFICULTY_LABELS
from ..domain.models import Task

MIN_DONE = 5
TOP_K = 5

STOPWORDS = frozenset(
    """
    a o as os um uma uns umas de do da dos das em no na nos nas por pelo pela pelos pelas para pra pro
    com sem sob sobre entre ate apos e ou mas que se ao aos à às é ser foi são estar esta este essa esse
    isto isso aquilo aquele aquela seu sua seus suas meu minha nosso nossa lhe the and of to in for on
    """.split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    normalized = rules.normalize_for_match(text)
    return [t for t in _TOKEN.findall(normalized) if len(t) > 1 and t not in STOPWORDS]


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = sum(counts.values()) or 1
    return {term: n / total for term, n in counts.items()}


def build_idf(documents: list[list[str]]) -> dict[str, float]:
    df: dict[str, int] = defaultdict(int)
    for doc in documents:
        for term in set(doc):
            df[term] += 1
    n = len(documents)
    return {term: math.log((1 + n) / (1 + count)) + 1 for term, count in df.items()}


def vectorize(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    return {term: weight * idf[term] for term, weight in _tf(tokens).items() if term in idf}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(weight * b.get(term, 0.0) for term, weight in a.items())
    norm = math.sqrt(sum(w * w for w in a.values())) * math.sqrt(sum(w * w for w in b.values()))
    return dot / norm if norm else 0.0


def _document(task: Task) -> str:
    return f"{task.title} {task.description}"


def suggest(title: str, description: str, tasks: Iterable[Task], today: date) -> dict:
    done = [t for t in tasks if t.is_done and t.completed_at is not None]
    if len(done) < MIN_DONE:
        return {"active": False, "done_count": len(done), "min_done": MIN_DONE}

    corpus = [tokenize(_document(t)) for t in done]
    idf = build_idf(corpus)
    query = vectorize(tokenize(f"{title} {description}"), idf)
    scored = sorted(
        ((cosine(query, vectorize(tokens, idf)), task) for tokens, task in zip(corpus, done)),
        key=lambda pair: pair[0],
        reverse=True,
    )
    similar = [(score, task) for score, task in scored[:TOP_K] if score > 0]
    if not similar:
        return {"active": True, "done_count": len(done), "min_done": MIN_DONE, "found": False}

    votes: Counter = Counter()
    weight: dict[str, float] = defaultdict(float)
    for score, task in similar:
        votes[task.difficulty] += 1
        weight[task.difficulty] += score
    difficulty = max(votes, key=lambda d: (votes[d], weight[d]))

    durations = [rules.completion_days(task) or 0.0 for _, task in similar]
    days = math.floor(median(durations) + 0.5)
    return {
        "active": True,
        "found": True,
        "done_count": len(done),
        "min_done": MIN_DONE,
        "difficulty": difficulty,
        "difficulty_label": DIFFICULTY_LABELS[difficulty],
        "due_date": (today + timedelta(days=days)).isoformat(),
        "median_days": round(median(durations), 1),
        "based_on": [
            {"id": task.id, "title": task.title, "similarity": round(score, 3), "difficulty": task.difficulty,
             "days": round(rules.completion_days(task) or 0.0, 1)}
            for score, task in similar
        ],
    }
