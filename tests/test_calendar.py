"""Calendário: validação de eventos, repetição e ocorrências, API, permissões, privacidade e feed .ics."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from app.config import get_settings
from app.domain import calendar
from app.domain.models import CalendarEntry
from app.domain.rules import DomainError
from app.store import db, projector


def entry(start: str = "2026-10-12", end: str | None = None, recurrence: dict | None = None, exceptions=(), **extra) -> CalendarEntry:
    return CalendarEntry(
        id="e1",
        account_id="a1",
        title="Evento",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end or start),
        recurrence=recurrence,
        exceptions=list(exceptions),
        **extra,
    )


def rule(freq: str, interval: int = 1, weekdays=(), until: str | None = None) -> dict:
    return {"freq": freq, "interval": interval, "weekdays": list(weekdays), "until": until}


# --- Regras (funções puras) -------------------------------------------------------------------------------------


def test_schedule_all_day_and_timed():
    assert calendar.clean_schedule({"all_day": True, "start_date": "2026-10-12", "start_time": "09:00"}) == {
        "all_day": True,
        "start_date": "2026-10-12",
        "start_time": None,
        "end_date": "2026-10-12",
        "end_time": None,
    }
    overnight = calendar.clean_schedule({"start_date": "2026-10-12", "start_time": "22:00", "end_date": "2026-10-13", "end_time": "02:00"})
    assert overnight["end_date"] == "2026-10-13" and overnight["end_time"] == "02:00"

    invalid = [
        ({"all_day": True, "start_date": "2026-10-12", "end_date": "2026-10-11"}, "periodo_invalido"),
        ({"start_date": "2026-10-12", "start_time": "10:00", "end_time": "10:00"}, "periodo_invalido"),
        ({"start_date": "2026-10-12", "start_time": "10:00", "end_time": "09:59"}, "periodo_invalido"),
        ({"start_date": "2026-10-12", "start_time": "9h", "end_time": "10:00"}, "horario_invalido"),
        ({"start_date": "2026-10-12", "start_time": "24:00", "end_time": "10:00"}, "horario_invalido"),
        ({"start_date": "2026-10-12", "start_time": "09:00"}, "horario_invalido"),
        ({"start_date": "12/10/2026", "start_time": "09:00", "end_time": "10:00"}, "data_invalida"),
        ({"start_time": "09:00", "end_time": "10:00"}, "data_invalida"),
        ({"all_day": True, "start_date": "2026-01-01", "end_date": "2027-01-03"}, "periodo_invalido"),
    ]
    for data, code in invalid:
        with pytest.raises(DomainError) as error:
            calendar.clean_schedule(data)
        assert error.value.code == code, data


def test_weekly_recurrence_moves_start_to_first_chosen_day():
    # 2026-10-13 é terça; escolhendo segunda e quinta, o evento começa na quinta (como no Outlook)
    cleaned = calendar.clean_entry(
        {
            "title": "Aula",
            "start_date": "2026-10-13",
            "start_time": "22:00",
            "end_date": "2026-10-14",
            "end_time": "01:00",
            "recurrence": {"freq": "semanal", "weekdays": [3, 0, 3]},
        }
    )
    assert (cleaned["start_date"], cleaned["end_date"]) == ("2026-10-15", "2026-10-16")
    assert cleaned["recurrence"] == {"freq": "semanal", "interval": 1, "weekdays": [0, 3], "until": None}
    assert calendar.clean_recurrence({"freq": "semanal"}, date(2026, 10, 13))[0]["weekdays"] == [1]
    assert calendar.clean_recurrence({"freq": "mensal", "interval": 2}, date(2026, 10, 13)) == (
        {"freq": "mensal", "interval": 2, "weekdays": [], "until": None},
        date(2026, 10, 13),
    )
    assert calendar.clean_recurrence(None, date(2026, 10, 13)) == (None, date(2026, 10, 13))

    for bad in (
        {"freq": "horaria"},
        {"freq": "diaria", "interval": 0},
        {"freq": "diaria", "interval": 100},
        {"freq": "semanal", "weekdays": [7]},
        {"freq": "semanal", "weekdays": ["seg"]},
        {"freq": "diaria", "interval": "dois"},
        {"freq": "diaria", "until": "2026-10-12"},
        "semanal",
    ):
        with pytest.raises(DomainError) as error:
            calendar.clean_recurrence(bad, date(2026, 10, 13))
        assert error.value.code == "repeticao_invalida", bad


def test_clean_entry_validates_every_field():
    base = {"title": " Reunião ", "start_date": "2026-10-12", "all_day": True}
    cleaned = calendar.clean_entry(base)
    assert cleaned["title"] == "Reunião" and cleaned["color"] == "azul" and cleaned["private"] is False
    assert calendar.clean_entry({**base, "location": "Sala\n 3", "color": "roxo"})["location"] == "Sala 3"
    for data, code in (
        ({**base, "title": "  "}, "titulo_obrigatorio"),
        ({**base, "color": "rosa"}, "cor_invalida"),
        ({**base, "location": "x" * 201}, "texto_longo"),
    ):
        with pytest.raises(DomainError) as error:
            calendar.clean_entry(data)
        assert error.value.code == code


def test_moving_only_the_start_keeps_the_duration():
    current = {"all_day": False, "start_date": "2026-10-12", "start_time": "23:00", "end_date": "2026-10-13", "end_time": "00:30"}
    assert calendar.merge_schedule(current, {"start_time": "10:00"}) == {**current, "start_time": "10:00", "end_date": "2026-10-12", "end_time": "11:30"}
    assert calendar.merge_schedule(current, {"start_date": "2026-10-20"})["end_date"] == "2026-10-21"
    assert calendar.merge_schedule(current, {"start_time": "10:00", "end_time": "12:00"})["end_time"] == "12:00"
    all_day = calendar.merge_schedule(current, {"all_day": True, "start_date": "2026-10-14"})
    assert all_day["end_date"] == "2026-10-13"  # trocou o tipo: o término informado vale como está
    days = {"all_day": True, "start_date": "2026-10-12", "start_time": None, "end_date": "2026-10-14", "end_time": None}
    assert calendar.merge_schedule(days, {"start_date": "2026-10-19"})["end_date"] == "2026-10-21"
    assert calendar.merge_schedule(current, {"start_time": "xx"})["end_time"] == "00:30"


def test_occurrences_follow_the_rule():
    def days(item, first="2026-10-01", last="2026-12-31"):
        start, end = date.fromisoformat(first), date.fromisoformat(last)
        span = (start + timedelta(days=i) for i in range((end - start).days + 1))
        return [d.isoformat() for d in span if calendar.occurs_on(item, d)]

    assert days(entry("2026-10-12")) == ["2026-10-12"]
    daily = entry("2026-10-12", recurrence=rule("diaria", 3, until="2026-10-24"), exceptions=["2026-10-18"])
    assert days(daily) == ["2026-10-12", "2026-10-15", "2026-10-21", "2026-10-24"]
    # quinzenal às segundas e quartas, contando semanas de segunda a domingo (RN23)
    biweekly = entry("2026-10-14", recurrence=rule("semanal", 2, weekdays=[0, 2]))
    assert days(biweekly, last="2026-11-12") == ["2026-10-14", "2026-10-26", "2026-10-28", "2026-11-09", "2026-11-11"]
    monthly = entry("2026-10-31", recurrence=rule("mensal"))
    assert days(monthly, last="2027-03-31") == ["2026-10-31", "2026-12-31", "2027-01-31", "2027-03-31"]
    leap = entry("2028-02-29", recurrence=rule("anual"))
    assert [y for y in range(2028, 2037) if calendar.occurs_on(leap, date(y, 2, 29) if y % 4 == 0 else date(y, 2, 28))] == [2028, 2032, 2036]
    every_other_year = entry("2026-10-12", recurrence=rule("anual", 2))
    assert [calendar.occurs_on(every_other_year, date(y, 10, 12)) for y in (2026, 2027, 2028)] == [True, False, True]
    assert not calendar.occurs_on(entry("2026-10-12", recurrence=rule("semanal", weekdays=[0])), date(2026, 10, 5))
    assert not calendar.occurs_on(entry("2026-10-12", recurrence=rule("quinzenal")), date(2026, 10, 12))
    assert calendar.span_days(entry("2026-10-12", "2026-10-15")) == 3


# --- API ------------------------------------------------------------------------------------------------------------


def create(api, account_id: str, actor_id: str | None = None, **data):
    data.setdefault("title", "Reunião")
    data.setdefault("start_date", "2026-10-12")
    if not data.get("all_day"):
        data.setdefault("start_time", "09:00")
        data.setdefault("end_time", "10:00")
    return api.post(f"/api/accounts/{account_id}/calendar", actor_id or account_id, json=data)


def test_calendar_crud(api):
    ana = api.account("Ana")
    response = create(api, ana["id"], title="Planejamento", notes="Levar números", location="Sala 2", color="verde")
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["start_time"] == "09:00" and item["end_date"] == "2026-10-12" and item["recurrence"] is None
    assert item["redacted"] is False and item["exceptions"] == []

    path = f"/api/calendar/{item['id']}"
    edited = api.patch(path, ana["id"], json={"title": "Planejamento Q4", "start_time": "14:00"}).json()
    assert edited["title"] == "Planejamento Q4" and (edited["start_time"], edited["end_time"]) == ("14:00", "15:00")
    all_day = api.patch(path, ana["id"], json={"all_day": True, "end_date": "2026-10-13"}).json()
    assert all_day["all_day"] is True and all_day["start_time"] is None and all_day["end_date"] == "2026-10-13"
    back = api.patch(path, ana["id"], json={"all_day": False})
    assert back.status_code == 422 and back.json()["code"] == "horario_invalido"
    repeating = api.patch(path, ana["id"], json={"recurrence": {"freq": "semanal", "weekdays": [0, 4]}}).json()
    assert repeating["recurrence"]["weekdays"] == [0, 4]
    assert api.patch(path, ana["id"], json={"recurrence": None}).json()["recurrence"] is None

    assert api.get(path).json()["title"] == "Planejamento Q4"
    listing = api.get(f"/api/accounts/{ana['id']}/calendar", ana["id"]).json()
    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert [e["id"] for e in listing] == [e["id"] for e in board["calendar"]] == [item["id"]]

    assert api.delete(path, ana["id"]).status_code == 204
    assert api.delete(path, ana["id"]).status_code == 204  # reenvio
    assert api.get(path).status_code == 404
    assert api.patch(path, ana["id"], json={"title": "x"}).status_code == 404
    assert api.get("/api/accounts/x/calendar").status_code == 404


def test_calendar_validation_messages(api):
    ana = api.account("Ana")
    late = create(api, ana["id"], start_time="10:00", end_time="09:00")
    assert late.status_code == 422 and late.json()["detail"] == "O término deve ser depois do início."
    bad = create(api, ana["id"], recurrence={"freq": "semanal", "weekdays": [9]})
    assert bad.status_code == 422 and bad.json()["detail"] == "Dados inválidos: verifique dias da semana."
    color = create(api, ana["id"], color="rosa")
    assert color.status_code == 422 and "cor" in color.json()["detail"]
    occurrence = api.delete("/api/calendar/x/occurrences/31-02-2026", ana["id"])
    assert occurrence.status_code == 422 and occurrence.json()["detail"] == "Dados inválidos: verifique data da ocorrência."


def test_calendar_is_read_only_for_other_accounts(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    gestor = api.account("Gil", role="gestor")
    item = create(api, ana["id"]).json()
    for actor in (bia, gestor):
        denied = [
            create(api, ana["id"], actor["id"]),
            api.patch(f"/api/calendar/{item['id']}", actor["id"], json={"title": "x"}),
            api.delete(f"/api/calendar/{item['id']}", actor["id"]),
        ]
        assert [r.status_code for r in denied] == [403, 403, 403]
        assert {r.json()["code"] for r in denied} == {"somente_leitura"}
    anonymous = api.post(f"/api/accounts/{ana['id']}/calendar", json={"title": "x", "start_date": "2026-10-12", "all_day": True})
    assert anonymous.status_code == 401  # sem conta selecionada
    # Colegas veem o calendário em modo somente leitura
    assert api.get(f"/api/accounts/{ana['id']}/board", bia["id"]).json()["calendar"][0]["title"] == "Reunião"


def test_private_events_show_only_busy_time_to_others(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    item = create(api, ana["id"], title="Consulta médica", notes="Levar exames", location="Clínica", color="vermelho", private=True).json()
    assert item["title"] == "Consulta médica" and item["redacted"] is False  # o dono vê tudo

    seen = api.get(f"/api/calendar/{item['id']}", bia["id"]).json()
    assert (seen["title"], seen["notes"], seen["location"], seen["color"]) == ("Ocupado", "", "", "cinza")
    assert seen["redacted"] is True and seen["private"] is True and seen["start_time"] == "09:00"
    assert api.get(f"/api/accounts/{ana['id']}/board", bia["id"]).json()["calendar"][0]["title"] == "Ocupado"
    assert api.get(f"/api/accounts/{ana['id']}/calendar").json()[0]["title"] == "Ocupado"  # sem conta

    feed = api.get(f"/api/accounts/{ana['id']}/calendar.ics").text
    assert "SUMMARY:Ocupado" in feed and "CLASS:PRIVATE" in feed
    assert "Consulta" not in feed and "Clínica" not in feed and "exames" not in feed


def test_occurrences_can_be_removed_or_changed_alone(api):
    ana = api.account("Ana")
    series = create(api, ana["id"], title="Daily", start_date="2026-10-12", recurrence={"freq": "diaria"}).json()
    path = f"/api/calendar/{series['id']}/occurrences"

    removed = api.delete(f"{path}/2026-10-14", ana["id"])
    assert removed.status_code == 200 and removed.json()["exceptions"] == ["2026-10-14"]
    assert api.delete(f"{path}/2026-10-14", ana["id"]).json()["exceptions"] == ["2026-10-14"]  # reenvio
    before_start = api.delete(f"{path}/2026-10-11", ana["id"])
    assert before_start.status_code == 422 and before_start.json()["code"] == "ocorrencia_invalida"

    moved = api.post(f"{path}/2026-10-15", ana["id"], json={"id": "ocorrencia-avulsa-1", "start_time": "15:00", "notes": "Remarcada"})
    assert moved.status_code == 201, moved.text
    body = moved.json()
    assert body["series"]["exceptions"] == ["2026-10-14", "2026-10-15"]
    single = body["entry"]
    assert single["id"] == "ocorrencia-avulsa-1" and single["recurrence"] is None and single["title"] == "Daily"
    assert (single["start_date"], single["start_time"], single["end_time"], single["notes"]) == ("2026-10-15", "15:00", "16:00", "Remarcada")
    replay = api.post(f"{path}/2026-10-15", ana["id"], json={"id": "ocorrencia-avulsa-1", "start_time": "15:00"})
    assert replay.status_code == 201 and replay.json()["entry"]["id"] == "ocorrencia-avulsa-1"
    assert len(api.get(f"/api/accounts/{ana['id']}/calendar", ana["id"]).json()) == 2
    again = api.post(f"{path}/2026-10-15", ana["id"], json={"start_time": "16:00"})
    assert again.status_code == 422 and again.json()["code"] == "ocorrencia_invalida"

    single_path = f"/api/calendar/{single['id']}/occurrences/2026-10-15"
    assert api.delete(single_path, ana["id"]).json()["code"] == "ocorrencia_invalida"  # evento avulso
    bia = api.account("Bia")
    assert api.delete(f"{path}/2026-10-16", bia["id"]).status_code == 403
    other = create(api, bia["id"], id="evento-da-bia", recurrence={"freq": "diaria"}).json()
    taken = api.post(f"/api/calendar/{other['id']}/occurrences/2026-10-13", bia["id"], json={"id": "ocorrencia-avulsa-1"})
    assert taken.status_code == 409 and taken.json()["code"] == "conflito"


def test_calendar_ids_and_conflicts(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    payload = {"id": "evento-offline-1", "title": "Criado offline"}
    created_at = {"X-Client-Time": "2026-01-01T00:00:00Z"}
    first = api.post(f"/api/accounts/{ana['id']}/calendar", ana["id"], json={**payload, "start_date": "2026-10-12", "all_day": True}, **created_at)
    again = create(api, ana["id"], **payload)
    assert first.status_code == again.status_code == 201 and again.json()["id"] == "evento-offline-1"
    taken = create(api, bia["id"], **payload)
    assert taken.status_code == 409 and taken.json()["code"] == "conflito"
    assert create(api, ana["id"], id="../x").status_code == 422

    path = "/api/calendar/evento-offline-1"
    newer = api.patch(path, ana["id"], json={"title": "Mais recente", "all_day": False, "start_time": "11:00", "end_time": "12:00"})
    assert newer.json()["title"] == "Mais recente"
    offline = {"X-Client-Time": "2026-06-01T00:00:00Z"}  # depois da criação, antes da última edição
    older = api.patch(path, ana["id"], json={"title": "Antigo", "start_time": "08:00", "location": "Sala 1"}, **offline)
    assert older.status_code == 200
    body = older.json()
    # RN30: título e horário mais recentes prevalecem; o local, alterado só na criação, recebe a mudança
    assert (body["title"], body["start_time"], body["location"]) == ("Mais recente", "11:00", "Sala 1")
    stale = api.patch(path, ana["id"], json={"location": "Sala 9"}, **{"X-Client-Time": "2025-01-01T00:00:00Z"})
    assert stale.json()["location"] == "Sala 1"


def test_calendar_rebuilds_and_leaves_with_the_account(api):
    ana = api.account("Ana")
    series = create(api, ana["id"], recurrence={"freq": "semanal", "weekdays": [0, 2], "until": "2026-12-31"}).json()
    api.delete(f"/api/calendar/{series['id']}/occurrences/2026-10-14", ana["id"])
    api.post(f"/api/calendar/{series['id']}/occurrences/2026-10-19", ana["id"], json={"start_time": "13:00"})
    api.patch(f"/api/calendar/{series['id']}", ana["id"], json={"color": "roxo", "private": True})
    create(api, ana["id"], title="Feriado", all_day=True, start_date="2026-11-02")
    removed = create(api, ana["id"], title="Removido").json()
    api.delete(f"/api/calendar/{removed['id']}", ana["id"])
    before = api.get(f"/api/accounts/{ana['id']}/calendar", ana["id"]).json()
    assert len(before) == 3

    conn = db.connect(get_settings().db_path)
    try:
        with db.write_transaction(conn):
            projector.rebuild_projections(conn)
    finally:
        conn.close()
    assert api.get(f"/api/accounts/{ana['id']}/calendar", ana["id"]).json() == before

    changes = api.get("/api/changes").json()
    create(api, ana["id"])
    assert api.get("/api/changes", since=changes["seq"]).json() == {"seq": changes["seq"] + 1, "accounts": [ana["id"]], "directory": False}

    assert api.delete(f"/api/accounts/{ana['id']}", ana["id"]).status_code == 204
    conn = db.connect(get_settings().db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM calendar_entries").fetchone()[0] == 0
    finally:
        conn.close()


def test_existing_database_gets_calendar_table(settings_env):
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    start = db.SCHEMA.index("-- Calendário")
    end = db.SCHEMA.index("-- Operacional")
    conn.executescript(db.SCHEMA[:start] + db.SCHEMA[end:])  # esquema v2, sem o calendário (nem a Daily)
    conn.close()

    db.init_db(path)
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM calendar_entries").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()["value"] == str(db.SCHEMA_VERSION)
    finally:
        conn.close()


def test_calendar_feed_includes_events(api, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://tarefas.exemplo.com/")
    get_settings.cache_clear()
    ana = api.account("Ana")
    api.task(ana["id"], title="Entrega", due_date="2026-10-02")
    weekly = create(
        api,
        ana["id"],
        title="Reunião, semanal; equipe",
        location="Sala 3",
        notes="Pauta:\nnúmeros",
        recurrence={"freq": "semanal", "interval": 2, "weekdays": [0, 2], "until": "2026-12-31"},
    ).json()
    api.delete(f"/api/calendar/{weekly['id']}/occurrences/2026-10-14", ana["id"])
    holiday = create(api, ana["id"], title="Feriado", all_day=True, start_date="2026-11-02", end_date="2026-11-03", recurrence={"freq": "anual", "until": "2030-11-02"}).json()
    api.post(f"/api/calendar/{holiday['id']}/occurrences/2027-11-02", ana["id"], json={"title": "Feriado (ponte)"})
    api.delete(f"/api/calendar/{holiday['id']}/occurrences/2028-11-02", ana["id"])

    response = api.get(f"/api/accounts/{ana['id']}/calendar.ics")
    body = response.text.replace("\r\n ", "")  # desfaz as quebras de linha longas (RFC 5545)
    assert 'filename="agenda.ics"' in response.headers["content-disposition"]
    assert "X-WR-CALNAME:Organizador — Ana" in body and "DTSTART;VALUE=DATE:20261002" in body
    assert "DTSTART:20261012T090000\r\nDTEND:20261012T100000\r\nTRANSP:OPAQUE" in body
    assert "SUMMARY:Reunião\\, semanal\\; equipe\r\nLOCATION:Sala 3\r\nDESCRIPTION:Pauta:\\nnúmeros" in body
    assert "RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;WKST=MO;UNTIL=20261231T235900" in body
    assert "EXDATE:20261014T090000" in body
    assert "DTSTART;VALUE=DATE:20261102\r\nDTEND;VALUE=DATE:20261104\r\nTRANSP:TRANSPARENT" in body
    assert "RRULE:FREQ=YEARLY;INTERVAL=1;UNTIL=20301102" in body
    assert "EXDATE;VALUE=DATE:20271102,20281102" in body
    assert "SUMMARY:Feriado (ponte)" in body and "DTSTART;VALUE=DATE:20271102" in body
    assert f"URL:https://tarefas.exemplo.com/#/calendario?semana=2026-10-12" in body
    assert body.count("BEGIN:VEVENT") == 4
