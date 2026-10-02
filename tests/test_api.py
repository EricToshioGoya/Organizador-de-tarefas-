"""Fluxos completos pela API REST: contas, tarefas, etapas, metas, templates, Gestor, comentários e sincronização."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from app.config import get_settings
from app.store import db, projector


# --- Contas (RF23–RF28, RF61, RN10, RN13) --------------------------------------------------------


def test_account_lifecycle(api):
    pedro = api.account("Pedro")
    assert pedro["initials"] == "P" and pedro["role"] == "membro" and pedro["settings"]["stale_days"] == 5

    duplicate = api.post("/api/accounts", json={"name": "  PEDRO "})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "nome_em_uso"

    renamed = api.patch(f"/api/accounts/{pedro['id']}", pedro["id"], json={"name": "Pedro Henrique", "role": "gestor", "settings": {"stale_days": 3}})
    assert renamed.status_code == 200
    body = renamed.json()
    assert body["name"] == "Pedro Henrique" and body["initials"] == "PH" and body["role"] == "gestor"
    assert body["settings"]["stale_days"] == 3

    listing = api.get("/api/accounts").json()
    assert [a["name"] for a in listing] == ["Pedro Henrique"]
    assert "settings" not in listing[0]  # configurações só para a própria conta
    assert api.get(f"/api/accounts/{pedro['id']}", pedro["id"]).json()["settings"]["stale_days"] == 3
    assert api.get("/api/accounts/nao-existe").status_code == 404


def test_account_edit_is_restricted_to_itself(api):
    ana, bia = api.account("Ana"), api.account("Bia")
    response = api.patch(f"/api/accounts/{ana['id']}", bia["id"], json={"name": "Hackeada"})
    assert response.status_code == 403 and response.json()["code"] == "somente_leitura"
    assert api.patch(f"/api/accounts/{ana['id']}", ana["id"], json={}).status_code == 200


def test_delete_account_removes_tasks_goals_templates(api, client):
    ana = api.account("Ana")
    task = api.task(ana["id"], title="Com anexo")
    api.post(f"/api/accounts/{ana['id']}/goals", ana["id"], json={"title": "Meta"})
    api.post(f"/api/accounts/{ana['id']}/templates", ana["id"], json={"title": "Modelo"})
    upload = client.post(
        f"/api/tasks/{task['id']}/attachments", files={"file": ("nota.txt", b"conteudo", "text/plain")}, headers=api.headers(ana["id"])
    )
    attachment_id = upload.json()["attachments"][0]["id"]
    assert (get_settings().uploads_dir / attachment_id).exists()

    assert api.delete(f"/api/accounts/{ana['id']}", ana["id"]).status_code == 204
    assert api.get("/api/accounts").json() == []
    assert api.get(f"/api/tasks/{task['id']}").status_code == 404
    assert not (get_settings().uploads_dir / attachment_id).exists()


def test_unknown_actor_is_rejected(api):
    ana = api.account("Ana")
    api.delete(f"/api/accounts/{ana['id']}", ana["id"])
    response = api.post("/api/accounts/x/tasks", ana["id"], json={"title": "x"})
    assert response.status_code == 401 and response.json()["code"] == "conta_inexistente"


# --- Tarefas e etapas (RF01–RF11, RN01–RN05, RN21) --------------------------------------------------


def test_task_crud_and_validation(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], title="Relatório", description="Mensal", due_date="2026-10-01", requester="Carlos", links=["exemplo.com"], steps=["A", {"text": "B"}, "  "])
    assert task["difficulty"] == "medio" and task["phase"] == "planejamento" and task["status"] == "pendente"
    assert task["priority"] == "media"
    assert [s["text"] for s in task["steps"]] == ["A", "B"]
    assert task["links"] == ["https://exemplo.com"]
    assert task["comments"] == {"total": 0, "unread": 0}

    bad = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"title": "   "})
    assert bad.status_code == 422 and bad.json()["detail"] == "O título é obrigatório."
    invalid = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"title": "x", "difficulty": "extrema"})
    assert invalid.status_code == 422 and "dificuldade" in invalid.json()["detail"]
    invalid = api.patch(f"/api/tasks/{task['id']}", ana["id"], json={"priority": "urgente"})
    assert invalid.status_code == 422 and "prioridade" in invalid.json()["detail"]

    edited = api.patch(f"/api/tasks/{task['id']}", ana["id"], json={"title": "Relatório final", "phase": "beta", "difficulty": "dificil", "notes": "ok"}).json()
    assert (edited["title"], edited["phase"], edited["difficulty"], edited["notes"]) == ("Relatório final", "beta", "dificil", "ok")

    assert api.delete(f"/api/tasks/{task['id']}", ana["id"]).status_code == 204
    assert api.get(f"/api/tasks/{task['id']}").status_code == 404
    assert api.delete(f"/api/tasks/{task['id']}", ana["id"]).status_code == 204  # idempotente


def test_priority_is_editable_and_logged(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], priority="alta")
    assert task["priority"] == "alta"
    edited = api.patch(f"/api/tasks/{task['id']}", ana["id"], json={"priority": "muito_alta"}).json()
    assert edited["priority"] == "muito_alta"
    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert board["tasks"][0]["priority"] == "muito_alta"
    timeline = api.get(f"/api/tasks/{task['id']}/timeline").json()
    assert any(item["text"] == "Prioridade: Alta → Muito alta" for item in timeline)


def test_existing_database_gets_priority_column(settings_env):
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(db.SCHEMA.replace("    priority TEXT NOT NULL DEFAULT 'media',\n", ""))  # esquema v1
    conn.execute(
        "INSERT INTO tasks(id, account_id, title, difficulty, created_at, status, phase, last_activity_at) "
        "VALUES ('t1', 'a1', 'Antiga', 'medio', '2026-09-01T12:00:00Z', 'pendente', 'planejamento', '2026-09-01T12:00:00Z')"
    )
    conn.commit()
    assert "priority" not in {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
    conn.close()

    db.init_db(path)
    db.init_db(path)  # idempotente
    conn = db.connect(path)
    try:
        assert conn.execute("SELECT priority FROM tasks WHERE id = 't1'").fetchone()["priority"] == "media"
    finally:
        conn.close()


def test_steps_drive_status(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], steps=["Um", "Dois"])
    one, two = (s["id"] for s in task["steps"])
    base = f"/api/tasks/{task['id']}"

    after_one = api.patch(f"{base}/steps/{one}", ana["id"], json={"done": True}).json()
    assert after_one["progress"] == 50 and after_one["status"] == "pendente"
    done = api.patch(f"{base}/steps/{two}", ana["id"], json={"done": True}).json()
    assert done["status"] == "concluida" and done["completed_at"]  # RN02

    reopened = api.patch(f"{base}/steps/{two}", ana["id"], json={"done": False}).json()
    assert reopened["status"] == "pendente" and reopened["completed_at"] is None  # RN04

    api.patch(f"{base}/steps/{two}", ana["id"], json={"done": True})
    with_new = api.post(f"{base}/steps", ana["id"], json={"steps": ["Três"]}).json()
    assert with_new["status"] == "pendente" and len(with_new["steps"]) == 3  # RN04: nova etapa

    three = with_new["steps"][2]["id"]
    removed = api.delete(f"{base}/steps/{three}", ana["id"]).json()
    assert removed["status"] == "concluida"  # sobram apenas etapas marcadas

    renamed = api.patch(f"{base}/steps/{one}", ana["id"], json={"text": "Um (revisado)"}).json()
    assert renamed["steps"][0]["text"] == "Um (revisado)"
    reordered = api.put(f"{base}/steps/order", ana["id"], json={"order": [two, one]}).json()
    assert [s["id"] for s in reordered["steps"]] == [two, one]

    blocked = api.post(f"{base}/status", ana["id"], json={"done": False})
    assert blocked.status_code == 422 and blocked.json()["code"] == "reabrir_por_etapa"
    assert api.patch(f"{base}/steps/nao-existe", ana["id"], json={"done": True}).status_code == 404


def test_checkbox_for_tasks_without_steps(api):
    ana = api.account("Ana")
    task = api.task(ana["id"])
    done = api.post(f"/api/tasks/{task['id']}/status", ana["id"], json={"done": True}).json()
    assert done["status"] == "concluida" and done["progress"] == 100  # RN03
    again = api.post(f"/api/tasks/{task['id']}/status", ana["id"], json={"done": True}).json()
    assert again["completed_at"] == done["completed_at"]
    reopened = api.post(f"/api/tasks/{task['id']}/status", ana["id"], json={"done": False}).json()
    assert reopened["status"] == "pendente"


def test_complete_task_with_steps_marks_all(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], steps=["A", "B", "C"])
    done = api.post(f"/api/tasks/{task['id']}/status", ana["id"], json={"done": True}).json()
    assert done["status"] == "concluida" and all(s["done"] for s in done["steps"])


def test_due_date_changes_and_history(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], due_date="2026-09-25")
    path = f"/api/tasks/{task['id']}"
    missing = api.patch(path, ana["id"], json={"due_date": "2026-09-30"})
    assert missing.status_code == 422 and missing.json()["code"] == "motivo_obrigatorio"
    postponed = api.patch(path, ana["id"], json={"due_date": "2026-09-30", "due_reason": "outro", "due_reason_text": "Cliente viajou"}).json()
    anticipated = api.patch(path, ana["id"], json={"due_date": "2026-09-28"}).json()
    removed = api.patch(path, ana["id"], json={"due_date": None}).json()
    kinds = [h["kind"] for h in removed["due_history"]]
    assert postponed["due_date"] == "2026-09-30" and anticipated["due_date"] == "2026-09-28" and removed["due_date"] is None
    assert kinds == ["adiamento", "antecipacao", "remocao"]
    assert removed["due_history"][0]["reason_text"] == "Cliente viajou"


# --- Somente leitura, Gestor e comentários (RF37, RF61–RF68, RN32–RN36) --------------------------------------


def test_read_only_for_other_accounts(api):
    ana, bia = api.account("Ana"), api.account("Bia")
    task = api.task(ana["id"], steps=["A"])
    step_id = task["steps"][0]["id"]
    attempts = [
        api.post(f"/api/accounts/{ana['id']}/tasks", bia["id"], json={"title": "Intrusa"}),
        api.patch(f"/api/tasks/{task['id']}", bia["id"], json={"title": "x"}),
        api.patch(f"/api/tasks/{task['id']}/steps/{step_id}", bia["id"], json={"done": True}),
        api.delete(f"/api/tasks/{task['id']}", bia["id"]),
        api.post(f"/api/accounts/{ana['id']}/goals", bia["id"], json={"title": "x"}),
        api.put(f"/api/accounts/{ana['id']}/top3", bia["id"], json={"task_ids": [task["id"]]}),
        api.post(f"/api/tasks/{task['id']}/comments", bia["id"], json={"text": "oi"}),
    ]
    assert [r.status_code for r in attempts] == [403] * len(attempts)
    board = api.get(f"/api/accounts/{ana['id']}/board", bia["id"]).json()
    assert board["own"] is False and board["can_comment"] is False
    assert board["tasks"][0]["comments"] is None and board["templates"] == [] and board["requesters"] == []


def test_manager_assigns_task_and_member_sees_it(api):
    gestora = api.account("Gestora", role="gestor")
    ana = api.account("Ana")
    assigned = api.task(ana["id"], actor_id=gestora["id"], title="Revisar proposta", requester="ignorado")
    assert assigned["account_id"] == ana["id"]
    assert assigned["requester"] == "Gestora" and assigned["assigned_by"] == gestora["id"]  # RN33
    assert assigned["assigned_seen_at"] is None

    # Gestor continua em modo somente leitura para editar (RN32)
    assert api.patch(f"/api/tasks/{assigned['id']}", gestora["id"], json={"title": "x"}).status_code == 403
    # O gestor não marca a visualização pelo membro
    assert api.post(f"/api/tasks/{assigned['id']}/seen", gestora["id"]).json()["assigned_seen_at"] is None
    seen = api.post(f"/api/tasks/{assigned['id']}/seen", ana["id"]).json()
    assert seen["assigned_seen_at"] is not None  # RF65

    timeline = api.get(f"/api/tasks/{assigned['id']}/timeline").json()
    assert timeline[0]["text"] == "Tarefa atribuída por Gestora"


def test_comments_visibility_unread_and_ownership(api):
    gestora = api.account("Gestora", role="gestor")
    ana, bia = api.account("Ana"), api.account("Bia")
    task = api.task(ana["id"])
    path = f"/api/tasks/{task['id']}/comments"

    comment = api.post(path, gestora["id"], json={"text": "Como está?"})
    assert comment.status_code == 201
    comment_id = comment.json()["id"]

    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert board["tasks"][0]["comments"] == {"total": 1, "unread": 1}  # RF67
    assert api.get(path, bia["id"]).status_code == 403  # RN36
    assert [c["text"] for c in api.get(path, ana["id"]).json()] == ["Como está?"]

    assert api.post(f"{path}/read", ana["id"]).status_code == 204
    assert api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()["tasks"][0]["comments"]["unread"] == 0

    reply = api.post(path, ana["id"], json={"text": "Quase pronto"}).json()
    gestora_view = api.get(f"/api/tasks/{task['id']}", gestora["id"]).json()
    assert gestora_view["comments"] == {"total": 2, "unread": 1}

    assert api.patch(f"/api/comments/{comment_id}", ana["id"], json={"text": "x"}).status_code == 403  # RF68
    edited = api.patch(f"/api/comments/{reply['id']}", ana["id"], json={"text": "Pronto!"}).json()
    assert edited["text"] == "Pronto!" and edited["edited_at"]
    assert api.delete(f"/api/comments/{reply['id']}", ana["id"]).status_code == 204
    assert len(api.get(path, gestora["id"]).json()) == 1
    empty = api.post(path, ana["id"], json={"text": "   "})
    assert empty.status_code == 422


# --- Metas (RF29–RF33, RN14–RN17) -----------------------------------------------------------------------


def test_goal_status_follows_tasks(api):
    ana = api.account("Ana")
    t1, t2 = api.task(ana["id"], title="T1"), api.task(ana["id"], title="T2")
    goal = api.post(f"/api/accounts/{ana['id']}/goals", ana["id"], json={"title": "Passar em Cálculo", "target_date": "2026-12-01", "task_ids": [t1["id"]]}).json()
    assert goal["total_tasks"] == 1 and goal["status"] == "andamento"

    api.post(f"/api/tasks/{t1['id']}/status", ana["id"], json={"done": True})
    assert api.get(f"/api/goals/{goal['id']}").json()["status"] == "concluida"  # RN15

    linked = api.post(f"/api/goals/{goal['id']}/tasks", ana["id"], json={"task_ids": [t2["id"]]}).json()
    assert linked["status"] == "andamento" and linked["progress"] == 50  # vinculação de pendente reabre

    api.patch(f"/api/tasks/{t2['id']}", ana["id"], json={"goal_id": None})
    assert api.get(f"/api/goals/{goal['id']}").json()["status"] == "concluida"

    api.post(f"/api/tasks/{t1['id']}/status", ana["id"], json={"done": False})
    assert api.get(f"/api/goals/{goal['id']}").json()["status"] == "andamento"  # reabertura

    edited = api.patch(f"/api/goals/{goal['id']}", ana["id"], json={"title": "Cálculo I", "target_date": None}).json()
    assert edited["title"] == "Cálculo I" and edited["target_date"] is None

    assert api.delete(f"/api/goals/{goal['id']}", ana["id"]).status_code == 204
    assert api.get(f"/api/tasks/{t1['id']}").json()["goal_id"] is None  # RN17
    timeline = api.get(f"/api/tasks/{t1['id']}/timeline").json()
    assert timeline[-1]["text"].endswith("(meta excluída)")


def test_goal_must_belong_to_account(api):
    ana, bia = api.account("Ana"), api.account("Bia")
    goal = api.post(f"/api/accounts/{bia['id']}/goals", bia["id"], json={"title": "Da Bia"}).json()
    response = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"title": "x", "goal_id": goal["id"]})
    assert response.status_code == 422 and response.json()["code"] == "meta_invalida"


# --- Templates (RF42, RF43, RN20) ---------------------------------------------------------------------------


def test_templates(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], title="Onboarding", difficulty="dificil", due_date="2026-10-01", steps=["Conta", "Crachá"])
    api.post(f"/api/tasks/{task['id']}/status", ana["id"], json={"done": True})
    template = api.post(f"/api/tasks/{task['id']}/template", ana["id"], json={"name": "Novo colaborador"}).json()
    assert template["steps"] == ["Conta", "Crachá"] and template["difficulty"] == "dificil"

    created = api.post(f"/api/templates/{template['id']}/tasks", ana["id"], json={"requester": "RH"}).json()
    assert created["title"] == "Onboarding" and created["due_date"] is None and created["requester"] == "RH"
    assert all(not s["done"] for s in created["steps"])  # RN20: marcações não são copiadas

    updated = api.patch(f"/api/templates/{template['id']}", ana["id"], json={"steps": ["Conta", "Crachá", "Treinamento"]}).json()
    assert len(updated["steps"]) == 3
    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert [t["name"] for t in board["templates"]] == ["Novo colaborador"]
    assert api.delete(f"/api/templates/{template['id']}", ana["id"]).status_code == 204
    assert api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()["templates"] == []


# --- Top 3 (RF39, RN18) --------------------------------------------------------------------------------------


def test_top3(api):
    ana = api.account("Ana")
    tasks = [api.task(ana["id"], title=f"T{i}") for i in range(4)]
    ids = [t["id"] for t in tasks]
    response = api.put(f"/api/accounts/{ana['id']}/top3", ana["id"], json={"task_ids": ids[:3]})
    assert response.status_code == 200 and response.json()["task_ids"] == ids[:3]
    too_many = api.put(f"/api/accounts/{ana['id']}/top3", ana["id"], json={"task_ids": ids})
    assert too_many.status_code == 422
    api.post(f"/api/tasks/{ids[0]}/status", ana["id"], json={"done": True})
    kept = api.put(f"/api/accounts/{ana['id']}/top3", ana["id"], json={"task_ids": ids[:2]})
    assert kept.status_code == 200  # concluída depois de escolhida pode permanecer
    board = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert board["top3"]["task_ids"] == ids[:2]


# --- Offline, idempotência e conflitos (RF71, RN30, RNF22) ------------------------------------------------------


def test_idempotent_replay(api):
    ana = api.account("Ana")
    headers = {"Idempotency-Key": "mutacao-0001"}
    first = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"title": "Uma vez"}, **headers)
    second = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"title": "Uma vez"}, **headers)
    assert first.status_code == second.status_code == 201
    assert second.headers.get("X-Replayed") == "1" and first.json()["id"] == second.json()["id"]
    assert len(api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()["tasks"]) == 1

    task_id = first.json()["id"]
    removal = {"Idempotency-Key": "mutacao-0002"}
    assert api.delete(f"/api/tasks/{task_id}", ana["id"], **removal).status_code == 204
    replay = api.delete(f"/api/tasks/{task_id}", ana["id"], **removal)
    assert replay.status_code == 204 and replay.headers.get("X-Replayed") == "1"


def test_client_generated_ids_make_creation_idempotent(api):
    ana = api.account("Ana")
    payload = {"id": "tarefa-offline-1", "title": "Criada offline"}
    api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json=payload)
    again = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json=payload)
    assert again.status_code == 201 and again.json()["id"] == "tarefa-offline-1"
    bad = api.post(f"/api/accounts/{ana['id']}/tasks", ana["id"], json={"id": "../x", "title": "x"})
    assert bad.status_code == 422


def test_last_write_wins_on_conflicts(api):
    ana = api.account("Ana")
    task = api.task(ana["id"], title="Original", steps=["A"])
    path = f"/api/tasks/{task['id']}"
    newer = api.patch(path, ana["id"], json={"title": "Mais recente"}, **{"X-Client-Time": "2030-01-01T00:00:00Z"})
    assert newer.json()["title"] == "Mais recente"  # horário no futuro é limitado ao do servidor
    older = api.patch(path, ana["id"], json={"title": "Antiga (offline)"}, **{"X-Client-Time": "2020-01-01T00:00:00Z"})
    assert older.status_code == 200 and older.json()["title"] == "Mais recente"  # RN30

    step_id = task["steps"][0]["id"]
    api.patch(f"{path}/steps/{step_id}", ana["id"], json={"done": True})
    stale = api.patch(f"{path}/steps/{step_id}", ana["id"], json={"done": False}, **{"X-Client-Time": "2020-01-01T00:00:00Z"})
    assert stale.json()["steps"][0]["done"] is True


def test_events_are_immutable_and_projections_rebuild(api):
    ana = api.account("Ana")
    gestor = api.account("Gil", role="gestor")
    task = api.task(ana["id"], steps=["A", "B"], due_date="2026-10-01")
    api.patch(f"/api/tasks/{task['id']}/steps/{task['steps'][0]['id']}", ana["id"], json={"done": True})
    api.patch(f"/api/tasks/{task['id']}", ana["id"], json={"due_date": "2026-10-05", "due_reason": "subestimei", "phase": "alpha"})
    api.post(f"/api/tasks/{task['id']}/comments", gestor["id"], json={"text": "Ok"})
    goal = api.post(f"/api/accounts/{ana['id']}/goals", ana["id"], json={"title": "Meta", "task_ids": [task["id"]]}).json()
    api.put(f"/api/accounts/{ana['id']}/top3", ana["id"], json={"task_ids": [task["id"]]})
    before = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()

    conn = db.connect(get_settings().db_path)
    try:
        with pytest.raises(Exception):
            conn.execute("UPDATE events SET type = 'x'")
        with pytest.raises(Exception):
            conn.execute("DELETE FROM events")
        with db.write_transaction(conn):
            count = projector.rebuild_projections(conn)
        assert count > 10
    finally:
        conn.close()

    after = api.get(f"/api/accounts/{ana['id']}/board", ana["id"]).json()
    assert after["tasks"] == before["tasks"] and after["goals"] == before["goals"] and after["top3"] == before["top3"]
    assert goal["id"] == after["goals"][0]["id"]


def test_changes_endpoint(api):
    assert api.get("/api/changes").json() == {"seq": 0, "accounts": [], "directory": False}
    ana = api.account("Ana")
    first = api.get("/api/changes").json()
    assert first["accounts"] == [ana["id"]] and first["directory"] is True
    assert api.get("/api/changes", since=first["seq"]).json()["accounts"] == []
    api.task(ana["id"])
    assert api.get("/api/changes", since=first["seq"]).json()["accounts"] == [ana["id"]]


# --- Revisão semanal (RF51) -------------------------------------------------------------------------------------


def test_weekly_review_lifecycle(api, monkeypatch):
    ana = api.account("Ana")
    # Conta criada nesta semana: ainda não há semana anterior completa.
    assert api.post(f"/api/accounts/{ana['id']}/weekly-review", ana["id"]).json() == {"review": None}

    from app.services import commands

    real_today = commands.today_in
    monkeypatch.setattr(commands, "today_in", lambda tz, now=None: real_today(tz, now) + timedelta(days=7))
    review = api.post(f"/api/accounts/{ana['id']}/weekly-review", ana["id"]).json()["review"]
    assert review["seen_at"] is None and "current" in review["summary"]
    again = api.post(f"/api/accounts/{ana['id']}/weekly-review", ana["id"]).json()["review"]
    assert again["week_start"] == review["week_start"]
    assert api.post(f"/api/accounts/{ana['id']}/weekly-reviews/{review['week_start']}/seen", ana["id"]).status_code == 204
    history = api.get(f"/api/accounts/{ana['id']}/weekly-reviews").json()
    assert len(history) == 1 and history[0]["seen_at"]


# --- Dashboard, painel e integrações --------------------------------------------------------------------------------


def test_dashboard_drilldown_and_team_overview(api):
    gestora = api.account("Gestora", role="gestor")
    ana = api.account("Ana")
    hard = api.task(ana["id"], difficulty="dificil", phase="producao", due_date=(date.today() - timedelta(days=2)).isoformat())
    api.task(ana["id"], difficulty="facil")
    dash = api.get(f"/api/accounts/{ana['id']}/dashboard", gestora["id"], period="7d").json()
    assert dash["kpis"]["pending"] == 2 and dash["kpis"]["overdue"] == 1
    assert dash["charts"]["g2"]["total"] == 2
    cached = api.get(f"/api/accounts/{ana['id']}/dashboard", gestora["id"], period="7d").json()
    assert cached == dash
    drill = api.get(f"/api/accounts/{ana['id']}/dashboard/drilldown", gestora["id"], chart="g2", key="dificil", period="7d").json()
    assert drill["task_ids"] == [hard["id"]] and drill["title"] == "Dificuldade: Difícil"
    assert api.get(f"/api/accounts/{ana['id']}/dashboard", gestora["id"], period="2d").status_code == 422

    overview = api.get("/api/team/overview", gestora["id"], period="30d").json()
    ana_card = next(m for m in overview["members"] if m["account"]["id"] == ana["id"])
    assert ana_card["overview"]["pending"] == 2 and ana_card["overview"]["overdue"] == 1
    assert {p["key"]: p["value"] for p in ana_card["overview"]["phases"]}["producao"] == 1


def test_calendar_feed(api):
    ana = api.account("Ana")
    api.task(ana["id"], title="Entrega, final; v2", due_date="2026-10-02")
    api.task(ana["id"], title="Sem data")
    response = api.get(f"/api/accounts/{ana['id']}/calendar.ics")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
    body = response.text
    assert "DTSTART;VALUE=DATE:20261002" in body and "DTEND;VALUE=DATE:20261003" in body
    assert "SUMMARY:Entrega\\, final\\; v2" in body and "Sem data" not in body
    assert api.get("/api/accounts/x/calendar.ics").status_code == 404


def test_quick_add_paste_ai_and_suggestions(api):
    ana = api.account("Ana")
    api.task(ana["id"], requester="Carlos Souza")
    parsed = api.post("/api/quick-add/parse", ana["id"], json={"text": "Ligar @carlos_souza amanhã"}).json()
    assert parsed["requester"] == "Carlos Souza" and parsed["title"] == "Ligar" and parsed["due_date"]
    pasted = api.post("/api/steps/parse", json={"text": "- a\n\n2. b"}).json()
    assert pasted["steps"] == ["a", "b"]
    ai = api.post("/api/ai/steps", json={"title": "Planejar evento"})
    assert ai.status_code == 503 and ai.json()["code"] == "ia_indisponivel"
    suggestion = api.post(f"/api/accounts/{ana['id']}/suggestions", json={"title": "Ligar"}).json()
    assert suggestion["active"] is False
    meta = api.get("/api/meta").json()
    assert meta["ai_enabled"] is False and meta["version"]


def test_attachments(api, client):
    ana, bia = api.account("Ana"), api.account("Bia")
    task = api.task(ana["id"])
    upload = client.post(f"/api/tasks/{task['id']}/attachments", files={"file": ("pagina.html", b"<script>alert(1)</script>", "text/html")}, headers=api.headers(ana["id"]))
    assert upload.status_code == 200
    attachment = upload.json()["attachments"][0]
    download = client.get(f"/api/attachments/{attachment['id']}")
    assert download.status_code == 200 and download.content.startswith(b"<script>")
    assert download.headers["content-type"] == "application/octet-stream"  # nunca renderizado como HTML
    assert download.headers["content-disposition"].startswith("attachment")

    forbidden = client.post(f"/api/tasks/{task['id']}/attachments", files={"file": ("x.txt", b"x", "text/plain")}, headers=api.headers(bia["id"]))
    assert forbidden.status_code == 403
    assert len(list(get_settings().uploads_dir.iterdir())) == 1  # arquivo recusado não fica no disco

    removed = api.delete(f"/api/attachments/{attachment['id']}", ana["id"]).json()
    assert removed["attachments"] == []
    assert client.get(f"/api/attachments/{attachment['id']}").status_code == 404


def test_attachment_size_limit(api, client, monkeypatch):
    ana = api.account("Ana")
    task = api.task(ana["id"])
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    big = b"0" * (1024 * 1024 + 1)
    response = client.post(f"/api/tasks/{task['id']}/attachments", files={"file": ("grande.bin", big, "application/octet-stream")}, headers=api.headers(ana["id"]))
    assert response.status_code == 413


def test_service_worker_gets_precache_list_and_version(client):
    body = client.get("/sw.js").text
    assert "__PRECACHE__" not in body and "__VERSION__" not in body
    assert '"/js/main.js"' in body and '"/vendor/echarts.esm.min.js"' in body and '"/"' in body
    assert "licenses" not in body


def test_frontend_is_served_with_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/sw.js").status_code == 200
    assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
    assert client.get("/api/nada").status_code == 404
    assert client.get("/api/docs").status_code == 200
