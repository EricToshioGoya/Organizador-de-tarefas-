"""Criação rápida por texto (RF41, RN19)."""

from __future__ import annotations

from datetime import date

from app.domain.quickadd import parse_date_word, parse_quick_add

TODAY = date(2026, 9, 23)  # quarta-feira


def test_spec_example():
    result = parse_quick_add("Apresentação sexta difícil @Carlos", TODAY)
    assert result.title == "Apresentação"
    assert result.due_date == date(2026, 9, 25)
    assert result.difficulty == "dificil"
    assert result.requester == "Carlos"
    assert [t.kind for t in result.tokens] == ["title", "date", "difficulty", "requester"]
    assert result.errors == []


def test_accents_and_case_are_ignored():
    result = parse_quick_add("Revisar contrato AMANHA Facil", TODAY)
    assert result.title == "Revisar contrato"
    assert result.due_date == date(2026, 9, 24)
    assert result.difficulty == "facil"
    assert parse_quick_add("Planejar MÉDIO hoje", TODAY).difficulty == "medio"


def test_weekday_includes_today_and_accepts_feira_suffix():
    assert parse_date_word("quarta", TODAY) == TODAY
    assert parse_date_word("Terça-feira", TODAY) == date(2026, 9, 29)
    assert parse_date_word("sábado", TODAY) == date(2026, 9, 26)
    assert parse_date_word("domingo", TODAY) == date(2026, 9, 27)
    assert parse_date_word("hoje", TODAY) == TODAY


def test_explicit_dates():
    assert parse_date_word("30/09", TODAY) == date(2026, 9, 30)
    assert parse_date_word("5/1", TODAY) == date(2027, 1, 5)  # já passou neste ano: próxima ocorrência
    assert parse_date_word("10/10/2027", TODAY) == date(2027, 10, 10)
    assert parse_date_word("10/10/27", TODAY) == date(2027, 10, 10)
    assert parse_date_word("31/02", TODAY) is None
    assert parse_date_word("banana", TODAY) is None


def test_last_occurrence_wins_and_rest_stays_in_title():
    result = parse_quick_add("Relatório de sexta para segunda", TODAY)
    assert result.due_date == date(2026, 9, 28)
    assert result.title == "Relatório de sexta para"


def test_requester_matches_known_names_and_underscores():
    result = parse_quick_add("Ligar @carlos_silva", TODAY, known_requesters=["Carlos Silva"])
    assert result.requester == "Carlos Silva"
    assert parse_quick_add("Ligar @Ana,", TODAY).requester == "Ana"
    assert parse_quick_add("Enviar para joao@empresa.com", TODAY).requester is None


def test_title_is_required():
    result = parse_quick_add("amanhã difícil @Carlos", TODAY)
    assert result.title == ""
    assert result.errors
    assert parse_quick_add("x" * 121, TODAY).errors
    assert parse_quick_add("", TODAY).errors
