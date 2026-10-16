"""Daily: tarefas simples do dia — criação, conclusão, mudança de dia, permissões, conflitos e projeções."""

from __future__ import annotations

import sqlite3

from app.config import get_settings
from app.store import db, projector


def add(api, account_id: str, actor_id: str | None = None, **data):
    data.setdefault("title", "Responder e-mails")
    return api.post(f"/api/accounts/{account_id}/daily", account_id if actor_id is None else actor_id, json=data)


def test_daily_item_lifecycle(api):
    ana = api.account("Ana")
    response = add(api, ana["id"], title="  Ligar para o fornecedor ", note="Pedir prazo", day="2026-10-16")
    assert response.status_code == 201, response.text
    item = response.json()
    assert (item["title"], item["note"], item["day"], item["done"], item["done_at"]) == ("Ligar para o fornecedor", "Pedir prazo", "2026-10-16", False, None)

    path = f"/api/daily/{item['id']}"
    done = api.patch(path, ana["id"], json={"done": True}).json()
    assert done["done"] is True and done["done_at"]
    again = api.patch(path, ana["id"], json={"done": True}).json()
    assert again["done_at"] == done["done_at"]  # concluir de novo não muda nada
    reopened = api.patch(path, ana["id"], json={"done": False, "title": "Ligar para o fornecedor (2ª vez)"}).json()
    assert reopened["done"] is False and reopened["done_at"] is None and reopened["title"].endswith("(2ª vez)")
    moved = api.patch(path, ana["id"], json={"day": "2026-10-17", "note": ""}).json()
    assert (moved["day"], moved["note"]) == ("2026-10-17", "")

    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    listing = api.get(f"/api/accounts/{ana['id']}/daily").json()
    assert board["daily"] == listing == [moved]

    assert api.delete(path, ana["id"]).status_code == 204
    assert api.delete(path, ana["id"]).status_code == 204  # reenvio
    assert api.patch(path, ana["id"], json={"done": True}).status_code == 404
    assert api.get(f"/api/accounts/{ana['id']}/daily").json() == []
    assert api.get("/api/accounts/x/daily").status_code == 404


def test_daily_defaults_to_the_day_of_the_action(api):
    ana = api.account("Ana")
    late_night = {"X-Client-Time": "2026-10-17T02:30:00Z"}  # 23:30 de 16/10 em São Paulo
    item = api.post(f"/api/accounts/{ana['id']}/daily", ana["id"], json={"title": "Fechar o dia"}, **late_night).json()
    assert item["day"] == "2026-10-16"


def test_daily_validation(api):
    ana = api.account("Ana")
    blank = add(api, ana["id"], title="   ")
    assert blank.status_code == 422 and blank.json()["code"] == "titulo_obrigatorio"
    bad_day = add(api, ana["id"], day="16/10/2026")
    assert bad_day.status_code == 422 and bad_day.json()["detail"] == "Dados inválidos: verifique data."
    item = add(api, ana["id"]).json()
    no_day = api.patch(f"/api/daily/{item['id']}", ana["id"], json={"day": None})
    assert no_day.status_code == 422 and no_day.json()["detail"] == "Informe a data."
    long_title = api.patch(f"/api/daily/{item['id']}", ana["id"], json={"title": "x" * 121})
    assert long_title.status_code == 422 and long_title.json()["code"] == "texto_longo"
    extra = api.patch(f"/api/daily/{item['id']}", ana["id"], json={"important": True})
    assert extra.status_code == 422


def test_daily_is_read_only_for_other_accounts(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    gestor = api.account("Gil", role="gestor")
    item = add(api, ana["id"], note="Detalhes").json()
    for actor in (bia, gestor):
        denied = [
            add(api, ana["id"], actor["id"]),
            api.patch(f"/api/daily/{item['id']}", actor["id"], json={"done": True}),
            api.delete(f"/api/daily/{item['id']}", actor["id"]),
        ]
        assert [r.status_code for r in denied] == [403, 403, 403]
        assert {r.json()["code"] for r in denied} == {"somente_leitura"}
        # colegas e Gestor veem a Daily (com anotações) em modo somente leitura
        assert api.get(f"/api/accounts/{ana['id']}/board", actor["id"]).json()["daily"][0]["note"] == "Detalhes"
    anonymous = api.post(f"/api/accounts/{ana['id']}/daily", json={"title": "x"})
    assert anonymous.status_code == 401


def test_daily_ids_replays_and_conflicts(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    payload = {"id": "daily-offline-1", "title": "Criado offline", "day": "2026-10-16"}
    first = api.post(f"/api/accounts/{ana['id']}/daily", ana["id"], json=payload, **{"X-Client-Time": "2026-10-01T12:00:00Z"})
    again = add(api, ana["id"], **payload)
    assert first.status_code == again.status_code == 201 and again.json()["id"] == "daily-offline-1"
    taken = add(api, bia["id"], **payload)
    assert taken.status_code == 409 and taken.json()["code"] == "conflito"
    assert add(api, ana["id"], id="../x").status_code == 422

    path = "/api/daily/daily-offline-1"
    api.patch(path, ana["id"], json={"title": "Mais recente", "done": True})
    offline = {"X-Client-Time": "2026-10-05T12:00:00Z"}  # depois da criação, antes da última edição
    body = api.patch(path, ana["id"], json={"title": "Antigo", "done": False, "note": "Anotação offline"}, **offline).json()
    # RN30: título e conclusão mais recentes prevalecem; a anotação, alterada só na criação, recebe a mudança
    assert (body["title"], body["done"], body["note"]) == ("Mais recente", True, "Anotação offline")

    # Excluir e recriar com o mesmo ID (desfazer a exclusão)
    assert api.delete(path, ana["id"]).status_code == 204
    restored = add(api, ana["id"], **payload)
    assert restored.status_code == 201 and restored.json()["done"] is False


def test_daily_rebuilds_and_leaves_with_the_account(api):
    ana = api.account("Ana")
    keep = add(api, ana["id"], title="Fica", day="2026-10-15").json()
    api.patch(f"/api/daily/{keep['id']}", ana["id"], json={"done": True, "note": "Feito"})
    moved = add(api, ana["id"], title="Muda de dia", day="2026-10-15").json()
    api.patch(f"/api/daily/{moved['id']}", ana["id"], json={"day": "2026-10-16"})
    gone = add(api, ana["id"], title="Sai").json()
    api.delete(f"/api/daily/{gone['id']}", ana["id"])
    restored = add(api, ana["id"], id=gone["id"], title="Volta", day="2026-10-16").json()
    before = api.get(f"/api/accounts/{ana['id']}/daily").json()
    assert [(i["title"], i["day"], i["done"]) for i in before] == [("Fica", "2026-10-15", True), ("Muda de dia", "2026-10-16", False), ("Volta", "2026-10-16", False)]
    assert restored["id"] == gone["id"]

    conn = db.connect(get_settings().db_path)
    try:
        with db.write_transaction(conn):
            projector.rebuild_projections(conn)
    finally:
        conn.close()
    assert api.get(f"/api/accounts/{ana['id']}/daily").json() == before

    changes = api.get("/api/changes").json()
    add(api, ana["id"])
    assert api.get("/api/changes", since=changes["seq"]).json() == {"seq": changes["seq"] + 1, "accounts": [ana["id"]], "directory": False}

    assert api.delete(f"/api/accounts/{ana['id']}", ana["id"]).status_code == 204
    conn = db.connect(get_settings().db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM daily_items").fetchone()[0] == 0
    finally:
        conn.close()


def test_existing_database_gets_daily_table(settings_env):
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    start = db.SCHEMA.index("-- Daily")
    end = db.SCHEMA.index("-- Operacional")
    conn.executescript(db.SCHEMA[:start] + db.SCHEMA[end:])  # esquema v3, com o calendário e sem a Daily
    conn.close()

    db.init_db(path)
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM daily_items").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM calendar_entries").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()["value"] == "4"
    finally:
        conn.close()
