"""Regras de negócio da seção 3 (RN01–RN36) e validações de entrada (RNF13)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain import rules
from app.domain.constants import ACCOUNT_COLORS
from app.domain.models import Account
from app.domain.rules import DomainError
from app.domain.timeutil import fmt_date_br, get_tz, parse_date, parse_iso, to_iso, week_end, week_start

from .factories import NOW, TODAY, TZ, at, goal, step, task


# --- RN01, RN02, RN03, RN04 -------------------------------------------------


def test_progress_counts_done_steps_rounding_down():
    t = task(steps=[step(done=True, done_at=NOW), step(), step()])
    assert rules.progress(t) == 33
    t.steps[1].done = True
    assert rules.progress(t) == 66


def test_progress_without_steps_follows_status():
    assert rules.progress(task()) == 0
    assert rules.progress(task(completed=NOW)) == 100


def test_status_from_steps_completes_and_reopens():
    steps = [step(done=True, done_at=NOW), step(done=True, done_at=NOW)]
    assert rules.status_from_steps(steps, "pendente") == "concluida"  # RN02
    steps.append(step())  # RN04: nova etapa em tarefa concluída
    assert rules.status_from_steps(steps, "concluida") == "pendente"


def test_status_from_steps_keeps_status_without_steps():
    assert rules.status_from_steps([], "concluida") == "concluida"  # RN03
    assert rules.status_from_steps([], "pendente") == "pendente"


def test_next_pending_step_respects_order():
    first, second, third = step(done=True, done_at=NOW, position=0), step(position=2), step(position=1)
    t = task(steps=[first, second, third])
    assert rules.next_pending_step(t) is third  # RF45
    for s in t.steps:
        s.done = True
    assert rules.next_pending_step(t) is None


# --- RN06, RN07, RN08, RN09, RF15 ------------------------------------------


def test_overdue_and_due_soon():
    assert rules.is_overdue(task(due=TODAY - timedelta(days=1)), TODAY)
    assert not rules.is_overdue(task(due=TODAY), TODAY)
    assert not rules.is_overdue(task(due=TODAY - timedelta(days=1), completed=NOW), TODAY)
    assert not rules.is_overdue(task(), TODAY)
    assert rules.is_due_soon(task(due=TODAY), TODAY)
    assert rules.is_due_soon(task(due=TODAY + timedelta(days=2)), TODAY)
    assert not rules.is_due_soon(task(due=TODAY + timedelta(days=3)), TODAY)
    assert not rules.is_due_soon(task(due=TODAY - timedelta(days=1)), TODAY)
    assert not rules.is_due_soon(task(), TODAY)


def test_on_time_uses_local_end_of_day():
    due = TODAY
    assert rules.completed_on_time(task(due=due, completed=at(due, 23)), TZ) is True  # 23:00 local
    assert rules.completed_on_time(task(due=due, completed=at(due + timedelta(days=1), 0)), TZ) is False
    assert rules.completed_on_time(task(due=None, completed=NOW), TZ) is None
    assert rules.completed_on_time(task(due=due), TZ) is None


def test_on_time_rate_ignores_tasks_without_due_date():
    tasks = [
        task(due=TODAY, completed=at(TODAY)),
        task(due=TODAY - timedelta(days=2), completed=at(TODAY)),
        task(completed=at(TODAY)),
    ]
    assert rules.on_time_rate(tasks, TZ) == 50
    assert rules.on_time_rate([task(completed=NOW)], TZ) is None


def test_completion_days():
    t = task(created=at(TODAY - timedelta(days=3)), completed=at(TODAY))
    assert rules.completion_days(t) == pytest.approx(3)
    assert rules.completion_days(task()) is None


# --- RN21 --------------------------------------------------------------------


def test_classify_due_change():
    d = date(2026, 9, 25)
    assert rules.classify_due_change(d, d) is None
    assert rules.classify_due_change(None, d) == "definicao"
    assert rules.classify_due_change(d, None) == "remocao"
    assert rules.classify_due_change(d, d + timedelta(days=1)) == "adiamento"
    assert rules.classify_due_change(d, d - timedelta(days=1)) == "antecipacao"


def test_postponement_requires_reason():
    d = date(2026, 9, 25)
    with pytest.raises(DomainError) as err:
        rules.build_due_change(d, d + timedelta(days=2), None, None)
    assert err.value.code == "motivo_obrigatorio"
    with pytest.raises(DomainError):
        rules.build_due_change(d, d + timedelta(days=2), "outro", "  ")
    change = rules.build_due_change(d, d + timedelta(days=2), "outro", "Aguardando cliente")
    assert change == {"old": "2026-09-25", "new": "2026-09-27", "kind": "adiamento", "reason": "outro", "reason_text": "Aguardando cliente"}
    change = rules.build_due_change(d, d + timedelta(days=2), "prioridade", "ignorado")
    assert change["reason_text"] == ""


def test_anticipation_records_without_reason():
    d = date(2026, 9, 25)
    change = rules.build_due_change(d, d - timedelta(days=2), "prioridade", "x")
    assert change["kind"] == "antecipacao" and change["reason"] is None
    assert rules.build_due_change(d, d, None, None) is None


# --- RN22, RN24 ---------------------------------------------------------------


def test_stale_tasks():
    t = task(last_activity=NOW - timedelta(days=6))
    assert rules.is_stale(t, NOW, 5)
    assert not rules.is_stale(t, NOW, 7)
    assert not rules.is_stale(task(last_activity=NOW - timedelta(days=6), completed=NOW), NOW, 5)


def test_points():
    assert [rules.points(d) for d in ("facil", "medio", "dificil")] == [1, 2, 3]
    assert rules.points("desconhecido") == 2


def test_stale_days_validation():
    assert rules.clean_stale_days("7") == 7
    for bad in (0, 91, "x", None):
        with pytest.raises(DomainError):
            rules.clean_stale_days(bad)


# --- RF14 ----------------------------------------------------------------------


def test_sorting():
    low = task(priority="baixa", due=TODAY - timedelta(days=5))
    top = task(priority="muito_alta")
    high = task(priority="alta", due=TODAY + timedelta(days=9))
    older = task(created=NOW - timedelta(days=20))
    newer = task(created=NOW - timedelta(days=1), due=TODAY)
    # Prioridade primeiro (o prazo não conta); no empate, a criada antes vem primeiro.
    assert rules.sort_pending([low, newer, high, older, top]) == [top, high, older, newer, low]
    old, recent = task(completed=NOW - timedelta(days=2)), task(completed=NOW)
    assert rules.sort_done([old, recent]) == [recent, old]


# --- RN14, RN15, RN16 ------------------------------------------------------------


def test_goal_progress_and_status():
    assert rules.goal_progress([]) == 0
    assert rules.goal_status([]) == "andamento"
    done, pending = task(completed=NOW), task()
    assert rules.goal_progress([done, pending]) == 50
    assert rules.goal_status([done, pending]) == "andamento"
    assert rules.goal_status([done]) == "concluida"


def test_goal_overdue():
    assert rules.goal_is_overdue(goal(target=TODAY - timedelta(days=1)), TODAY)
    assert not rules.goal_is_overdue(goal(target=TODAY), TODAY)
    assert not rules.goal_is_overdue(goal(target=TODAY - timedelta(days=1), done=True, completed=NOW), TODAY)
    assert not rules.goal_is_overdue(goal(), TODAY)


# --- RF39, RN18 ------------------------------------------------------------------


def test_top3_only_for_the_same_day():
    assert rules.top3_for_day(TODAY, ["a"], TODAY) == ["a"]
    assert rules.top3_for_day(TODAY - timedelta(days=1), ["a"], TODAY) == []


def test_validate_top3():
    a, b, c, d = (task() for _ in range(4))
    done = task(completed=NOW)
    by_id = {t.id: t for t in (a, b, c, d, done)}
    assert rules.validate_top3([a.id, a.id, b.id], by_id, "acc-1") == [a.id, b.id]
    with pytest.raises(DomainError):
        rules.validate_top3([a.id, b.id, c.id, d.id], by_id, "acc-1")
    with pytest.raises(DomainError):
        rules.validate_top3([done.id], by_id, "acc-1")
    assert rules.validate_top3([done.id], by_id, "acc-1", already_selected=[done.id]) == [done.id]
    with pytest.raises(DomainError):
        rules.validate_top3(["nao-existe"], by_id, "acc-1")
    with pytest.raises(DomainError):
        rules.validate_top3([a.id], by_id, "outra-conta")


# --- RN20, RF44 --------------------------------------------------------------------


def test_task_from_template_does_not_copy_dates_or_marks():
    data = rules.task_from_template(
        {"title": "Relatório", "description": "Mensal", "difficulty": "dificil", "steps": ["Coletar", {"text": "Revisar"}], "due_date": "2026-01-01"}
    )
    assert data == {"title": "Relatório", "description": "Mensal", "difficulty": "dificil", "steps": ["Coletar", "Revisar"]}


def test_parse_pasted_steps():
    text = "- Coletar dados\n\n* Escrever\n1. Revisar\n2) Enviar\n• Arquivar\n- [ ] Conferir\n[x] Feito\na) Letra\n   \nTexto normal"
    assert rules.parse_pasted_steps(text) == [
        "Coletar dados",
        "Escrever",
        "Revisar",
        "Enviar",
        "Arquivar",
        "Conferir",
        "Feito",
        "Letra",
        "Texto normal",
    ]


# --- RN10, RF25 -----------------------------------------------------------------------


def test_name_key_is_case_insensitive():
    assert rules.name_key("  Pedro   Silva ") == rules.name_key("pedro silva")
    assert rules.name_key("José") != rules.name_key("Jose")


def test_initials():
    assert rules.initials("Pedro Henrique Silva") == "PS"
    assert rules.initials("pedro") == "P"
    assert rules.initials("") == "?"


def test_pick_color_prefers_least_used_and_is_stable():
    first = rules.pick_color("Ana", [])
    assert first in ACCOUNT_COLORS
    assert rules.pick_color("Ana", []) == first
    used = list(ACCOUNT_COLORS[:-1])
    assert rules.pick_color("Qualquer", used) == ACCOUNT_COLORS[-1]


# --- RF37, RN32, RN36 ------------------------------------------------------------------


def test_permissions():
    member = Account(id="m", name="Membro", color="#fff")
    other = Account(id="o", name="Outro", color="#fff")
    manager = Account(id="g", name="Gestora", color="#fff", role="gestor")
    assert rules.can_edit(member, "m") and not rules.can_edit(other, "m") and not rules.can_edit(None, "m")
    assert rules.can_assign(manager, "m") and not rules.can_assign(member, "o") and not rules.can_assign(manager, "g")
    assert rules.can_view_comments(member, "m") and rules.can_view_comments(manager, "m")
    assert not rules.can_view_comments(other, "m") and not rules.can_view_comments(None, "m")


# --- RNF13 -------------------------------------------------------------------------------


def test_clean_text_removes_control_chars_and_limits_size():
    assert rules.clean_text("a\x00b​c\r\nd") == "abc\nd"
    assert rules.clean_text("  a   b  ", multiline=False) == "a b"
    assert rules.clean_text(None) == ""
    with pytest.raises(DomainError):
        rules.clean_text("x" * 11, 10)


def test_clean_title_and_name():
    assert rules.clean_title("  Olá <b>mundo</b> ") == "Olá <b>mundo</b>"  # escapado na saída, não removido
    with pytest.raises(DomainError):
        rules.clean_title("   ")
    with pytest.raises(DomainError):
        rules.clean_title("x" * 121)
    with pytest.raises(DomainError):
        rules.clean_name("")
    with pytest.raises(DomainError):
        rules.clean_step_text(" ")
    with pytest.raises(DomainError):
        rules.clean_comment("\n ")


def test_clean_url_blocks_dangerous_schemes():
    assert rules.clean_url("exemplo.com/a") == "https://exemplo.com/a"
    assert rules.clean_url("mailto:ana@ex.com") == "mailto:ana@ex.com"
    for bad in ("javascript:alert(1)", "data:text/html,oi", "https://a.com/\"onmouseover", ""):
        with pytest.raises(DomainError):
            rules.clean_url(bad)
    assert rules.clean_links(["a.com", "https://a.com"]) == ["https://a.com"]
    with pytest.raises(DomainError):
        rules.clean_links([f"https://a.com/{i}" for i in range(51)])


def test_enum_checks():
    assert rules.check_difficulty("facil") == "facil"
    assert rules.check_phase("beta") == "beta"
    assert rules.check_role("gestor") == "gestor"
    for check in (rules.check_difficulty, rules.check_phase, rules.check_role):
        with pytest.raises(DomainError):
            check("x")


def test_settings_validation():
    assert rules.merge_settings({"stale_days": 3, "desconhecida": 1})["stale_days"] == 3
    cleaned = rules.clean_settings_changes(
        {
            "stale_days": "10",
            "email": "ana@ex.com",
            "telegram_chat_id": "-100123456",
            "digest_enabled": 1,
            "digest_time": "07:30",
            "digest_channels": ["email", "sms", "email"],
            "timezone": "America/Manaus",
        }
    )
    assert cleaned == {
        "stale_days": 10,
        "email": "ana@ex.com",
        "telegram_chat_id": "-100123456",
        "digest_enabled": True,
        "digest_time": "07:30",
        "digest_channels": ["email"],
        "timezone": "America/Manaus",
    }
    for bad in ({"email": "sem-arroba"}, {"telegram_chat_id": "abc"}, {"digest_time": "25:00"}, {"outra": 1}):
        with pytest.raises(DomainError):
            rules.clean_settings_changes(bad)


def test_normalize_for_match():
    assert rules.normalize_for_match("  DifÍcil  Amanhã ") == "dificil amanha"


# --- RN23, utilitários de data -------------------------------------------------------------


def test_week_boundaries_monday_to_sunday():
    assert week_start(TODAY) == date(2026, 9, 21)
    assert week_end(TODAY) == date(2026, 9, 27)
    assert week_start(date(2026, 9, 27)) == date(2026, 9, 21)


def test_time_helpers():
    assert to_iso(None) is None
    assert parse_iso(None) is None
    moment = parse_iso("2026-09-23T10:00:00Z")
    assert to_iso(moment) == "2026-09-23T10:00:00.000Z"
    assert parse_iso("2026-09-23T10:00:00").tzinfo is not None
    assert parse_date("2026-09-23T10:00") == TODAY
    assert parse_date(TODAY) == TODAY and parse_date("") is None
    assert fmt_date_br(TODAY) == "23/09/2026" and fmt_date_br(None) == "—"
    assert str(get_tz("Nao/Existe")) == "America/Sao_Paulo"
    assert str(get_tz(None, "UTC")) == "UTC"
