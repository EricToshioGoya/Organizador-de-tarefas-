"""Listas: listas com nome (modelo tarefas ou ranking) — itens, ranking, quantidades, privacidade, conflitos e projeções."""

from __future__ import annotations

import sqlite3

from app.config import get_settings
from app.store import db, projector


def new_list(api, account_id: str, actor_id: str | None = None, **data):
    data.setdefault("name", "Lista de compras")
    return api.post(f"/api/accounts/{account_id}/lists", account_id if actor_id is None else actor_id, json=data)


def add(api, list_id: str, account_id: str, **data):
    data.setdefault("title", "Arroz")
    return api.post(f"/api/lists/{list_id}/items", account_id, json=data)


def lists_of(api, account_id: str) -> dict:
    return api.get(f"/api/accounts/{account_id}/lists", account_id).json()


def test_list_lifecycle(api):
    ana = api.account("Ana")
    response = new_list(api, ana["id"], name="  Lista de   compras ")
    assert response.status_code == 201, response.text
    lst = response.json()
    assert (lst["name"], lst["kind"]) == ("Lista de compras", "tarefas")

    renamed = api.patch(f"/api/lists/{lst['id']}", ana["id"], json={"name": "Mercado", "kind": "ranking"}).json()
    assert (renamed["name"], renamed["kind"]) == ("Mercado", "ranking")

    item = add(api, lst["id"], ana["id"], title=" Arroz ", note="Integral", quantity=2, unit="kg").json()
    assert (item["title"], item["note"], item["quantity"], item["unit"], item["position"], item["done"]) == ("Arroz", "Integral", 2, "kg", 0, False)
    path = f"/api/list-items/{item['id']}"
    done = api.patch(path, ana["id"], json={"done": True}).json()
    assert done["done"] is True and done["done_at"]
    again = api.patch(path, ana["id"], json={"done": True}).json()
    assert again["done_at"] == done["done_at"]  # concluir de novo não muda nada
    edited = api.patch(path, ana["id"], json={"done": False, "quantity": 1.5, "unit": "", "title": "Arroz branco"}).json()
    assert (edited["done"], edited["done_at"], edited["quantity"], edited["unit"], edited["title"]) == (False, None, 1.5, "", "Arroz branco")
    cleared = api.patch(path, ana["id"], json={"quantity": None}).json()
    assert cleared["quantity"] is None

    listing = lists_of(api, ana["id"])
    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert listing == {"lists": [renamed | {"updated_at": listing["lists"][0]["updated_at"]}], "items": [cleared]}
    assert (board["lists"], board["list_items"]) == (listing["lists"], listing["items"])

    assert api.delete(path, ana["id"]).status_code == 204
    assert api.delete(path, ana["id"]).status_code == 204  # reenvio
    assert api.patch(path, ana["id"], json={"done": True}).status_code == 404
    assert lists_of(api, ana["id"])["items"] == []

    add(api, lst["id"], ana["id"], title="Feijão")
    assert api.delete(f"/api/lists/{lst['id']}", ana["id"]).status_code == 204
    assert api.delete(f"/api/lists/{lst['id']}", ana["id"]).status_code == 204  # reenvio
    assert lists_of(api, ana["id"]) == {"lists": [], "items": []}  # a lista sai com os itens
    assert add(api, lst["id"], ana["id"]).status_code == 404
    assert api.get("/api/accounts/x/lists", ana["id"]).status_code == 404


def test_ranking_order(api):
    ana = api.account("Ana")
    lst = new_list(api, ana["id"], name="Prioridades", kind="ranking").json()
    a, b, c = (add(api, lst["id"], ana["id"], title=t).json() for t in ("A", "B", "C"))
    assert [i["position"] for i in (a, b, c)] == [0, 1, 2]  # novos itens entram no fim do ranking

    order = api.put(f"/api/lists/{lst['id']}/order", ana["id"], json={"order": [c["id"], a["id"], "desconhecido", c["id"]]})
    assert order.status_code == 200, order.text
    assert [(i["title"], i["position"]) for i in order.json()] == [("C", 0), ("A", 1), ("B", 2)]  # omitidos seguem depois
    assert [i["title"] for i in lists_of(api, ana["id"])["items"]] == ["C", "A", "B"]

    # Desfazer a exclusão: o item volta com o mesmo ID e a posição de antes
    api.delete(f"/api/list-items/{a['id']}", ana["id"])
    restored = add(api, lst["id"], ana["id"], id=a["id"], title="A", position=1)
    assert restored.status_code == 201 and restored.json()["position"] == 1
    assert [i["title"] for i in lists_of(api, ana["id"])["items"]] == ["C", "A", "B"]

    other = new_list(api, ana["id"], name="Outra").json()
    moved = api.put(f"/api/lists/{other['id']}/order", ana["id"], json={"order": [a["id"]]}).json()
    assert moved == []  # itens de outra lista são ignorados


def test_list_validation(api):
    ana = api.account("Ana")
    blank = new_list(api, ana["id"], name="  ")
    assert blank.status_code == 422 and blank.json()["code"] == "nome_obrigatorio"
    bad_kind = new_list(api, ana["id"], kind="kanban")
    assert bad_kind.status_code == 422 and "modelo da lista" in bad_kind.json()["detail"]
    lst = new_list(api, ana["id"]).json()
    assert api.patch(f"/api/lists/{lst['id']}", ana["id"], json={"name": "x" * 61}).json()["code"] == "texto_longo"

    blank_item = add(api, lst["id"], ana["id"], title=" ")
    assert blank_item.status_code == 422 and blank_item.json()["code"] == "titulo_obrigatorio"
    for quantity in (0, -1, 10**7):
        response = add(api, lst["id"], ana["id"], quantity=quantity)
        assert response.status_code == 422 and response.json()["code"] == "quantidade_invalida", quantity
    assert add(api, lst["id"], ana["id"], quantity="muitos").status_code == 422
    assert add(api, lst["id"], ana["id"], unit="x" * 21).json()["code"] == "texto_longo"
    assert add(api, lst["id"], ana["id"], position=-1).status_code == 422
    assert add(api, lst["id"], ana["id"], quantity=0.3333).json()["quantity"] == 0.333
    item = add(api, lst["id"], ana["id"]).json()
    extra = api.patch(f"/api/list-items/{item['id']}", ana["id"], json={"day": "2026-10-19"})
    assert extra.status_code == 422


def test_lists_are_private(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    gestor = api.account("Gil", role="gestor")
    lst = new_list(api, ana["id"]).json()
    item = add(api, lst["id"], ana["id"]).json()
    for actor in (bia, gestor):
        denied = [
            new_list(api, ana["id"], actor["id"]),
            api.patch(f"/api/lists/{lst['id']}", actor["id"], json={"name": "x"}),
            api.delete(f"/api/lists/{lst['id']}", actor["id"]),
            api.put(f"/api/lists/{lst['id']}/order", actor["id"], json={"order": []}),
            add(api, lst["id"], actor["id"]),
            api.patch(f"/api/list-items/{item['id']}", actor["id"], json={"done": True}),
            api.delete(f"/api/list-items/{item['id']}", actor["id"]),
            api.get(f"/api/accounts/{ana['id']}/lists", actor["id"]),
        ]
        assert [r.status_code for r in denied] == [403] * 8
        assert {r.json()["code"] for r in denied} == {"somente_leitura"}
        # nem colegas nem o Gestor veem as listas no quadro da conta
        board = api.get(f"/api/accounts/{ana['id']}/board", actor["id"]).json()
        assert (board["lists"], board["list_items"]) == ([], [])
    assert api.get(f"/api/accounts/{ana['id']}/lists").status_code == 403
    assert api.post(f"/api/accounts/{ana['id']}/lists", json={"name": "x"}).status_code == 401


def test_list_ids_replays_and_conflicts(api):
    ana = api.account("Ana")
    bia = api.account("Bia")
    payload = {"id": "list-offline-1", "name": "Criada offline"}
    first = api.post(f"/api/accounts/{ana['id']}/lists", ana["id"], json=payload, **{"X-Client-Time": "2026-10-01T12:00:00Z"})
    again = new_list(api, ana["id"], **payload)
    assert first.status_code == again.status_code == 201 and again.json()["id"] == "list-offline-1"
    taken = new_list(api, bia["id"], **payload)
    assert taken.status_code == 409 and taken.json()["code"] == "conflito"
    assert new_list(api, ana["id"], id="../x").status_code == 422

    item_payload = {"id": "item-offline-1", "title": "Leite"}
    first_item = api.post("/api/lists/list-offline-1/items", ana["id"], json=item_payload, **{"X-Client-Time": "2026-10-01T12:00:00Z"})
    assert first_item.status_code == add(api, "list-offline-1", ana["id"], **item_payload).status_code == 201
    bia_list = new_list(api, bia["id"]).json()
    assert add(api, bia_list["id"], bia["id"], **item_payload).status_code == 409

    path = "/api/list-items/item-offline-1"
    api.patch(path, ana["id"], json={"title": "Mais recente", "done": True})
    offline = {"X-Client-Time": "2026-10-05T12:00:00Z"}  # depois da criação, antes da última edição
    body = api.patch(path, ana["id"], json={"title": "Antigo", "done": False, "quantity": 3, "unit": "L"}, **offline).json()
    # RN30: título e conclusão mais recentes prevalecem; quantidade e unidade, alteradas só na criação, recebem a mudança
    assert (body["title"], body["done"], body["quantity"], body["unit"]) == ("Mais recente", True, 3, "L")

    api.patch("/api/lists/list-offline-1", ana["id"], json={"name": "Nome novo"})
    stale = api.patch("/api/lists/list-offline-1", ana["id"], json={"name": "Nome antigo", "kind": "ranking"}, **offline).json()
    assert (stale["name"], stale["kind"]) == ("Nome novo", "ranking")


def test_lists_rebuild_and_leave_with_the_account(api):
    ana = api.account("Ana")
    keep = new_list(api, ana["id"], name="Fica", kind="ranking").json()
    a = add(api, keep["id"], ana["id"], title="A", quantity=2, unit="un").json()
    b = add(api, keep["id"], ana["id"], title="B").json()
    api.patch(f"/api/list-items/{a['id']}", ana["id"], json={"done": True, "note": "Feito"})
    api.put(f"/api/lists/{keep['id']}/order", ana["id"], json={"order": [b["id"], a["id"]]})
    gone = new_list(api, ana["id"], name="Sai").json()
    add(api, gone["id"], ana["id"], title="Some junto")
    api.delete(f"/api/lists/{gone['id']}", ana["id"])
    before = lists_of(api, ana["id"])
    assert [lst["name"] for lst in before["lists"]] == ["Fica"]
    assert [(i["title"], i["position"], i["done"], i["quantity"]) for i in before["items"]] == [("B", 0, False, None), ("A", 1, True, 2)]

    conn = db.connect(get_settings().db_path)
    try:
        with db.write_transaction(conn):
            projector.rebuild_projections(conn)
    finally:
        conn.close()
    assert lists_of(api, ana["id"]) == before

    changes = api.get("/api/changes").json()
    add(api, keep["id"], ana["id"])
    assert api.get("/api/changes", since=changes["seq"]).json() == {"seq": changes["seq"] + 1, "accounts": [ana["id"]], "directory": False}

    assert api.delete(f"/api/accounts/{ana['id']}", ana["id"]).status_code == 204
    conn = db.connect(get_settings().db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM list_items").fetchone()[0] == 0
    finally:
        conn.close()


def test_existing_database_gets_list_tables(settings_env):
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    start = db.SCHEMA.index("-- Listas")
    end = db.SCHEMA.index("-- Operacional")
    conn.executescript(db.SCHEMA[:start] + db.SCHEMA[end:])  # esquema v4, com a Daily e sem as listas
    conn.close()

    db.init_db(path)
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM lists").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM list_items").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()["value"] == "5"
    finally:
        conn.close()
