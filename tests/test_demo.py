"""Gerador de dados de demonstração: cria equipe coerente e recusa bancos já em uso."""

from __future__ import annotations

import pytest

from app import demo
from app.config import get_settings
from app.store import db, projector, repo


def test_demo_seed_builds_consistent_history(settings_env):
    result = demo.seed(tasks_per_member=12, seed_value=7)
    assert result == {"accounts": 5, "tasks": 48}

    conn = db.connect(get_settings().db_path)
    try:
        accounts = repo.list_accounts(conn)
        assert [a.role for a in accounts].count("gestor") == 1
        member = next(a for a in accounts if a.role == "membro")
        tasks = repo.list_tasks(conn, member.id)
        assert len(tasks) == 13  # 12 geradas + 1 atribuída pelo Gestor
        assert any(t.assigned_by for t in tasks)
        snapshot = [(t.id, t.status, t.due_date, len(t.steps)) for t in sorted(tasks, key=lambda t: t.id)]
        with db.write_transaction(conn):
            projector.rebuild_projections(conn)
        rebuilt = repo.list_tasks(conn, member.id)
        assert [(t.id, t.status, t.due_date, len(t.steps)) for t in sorted(rebuilt, key=lambda t: t.id)] == snapshot
    finally:
        conn.close()

    with pytest.raises(SystemExit):
        demo.seed(tasks_per_member=1)
