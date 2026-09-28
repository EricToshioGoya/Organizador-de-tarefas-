from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

TZ_HEADER = {"X-Timezone": "America/Sao_Paulo"}


class Api:
    """Atalhos para chamar a API como uma conta específica."""

    def __init__(self, client: TestClient):
        self.client = client

    def headers(self, account_id: str | None = None, **extra: str) -> dict:
        headers = dict(TZ_HEADER)
        if account_id:
            headers["X-Account-Id"] = account_id
        headers.update(extra)
        return headers

    def account(self, name: str, role: str | None = None) -> dict:
        response = self.client.post("/api/accounts", json={"name": name}, headers=self.headers())
        assert response.status_code == 201, response.text
        account = response.json()
        if role:
            response = self.client.patch(f"/api/accounts/{account['id']}", json={"role": role}, headers=self.headers(account["id"]))
            assert response.status_code == 200, response.text
            account = response.json()
        return account

    def task(self, account_id: str, actor_id: str | None = None, **data) -> dict:
        data.setdefault("title", "Tarefa de teste")
        response = self.client.post(
            f"/api/accounts/{account_id}/tasks", json=data, headers=self.headers(actor_id or account_id)
        )
        assert response.status_code == 201, response.text
        return response.json()

    def get(self, path: str, account_id: str | None = None, **params):
        return self.client.get(path, params=params, headers=self.headers(account_id))

    def post(self, path: str, account_id: str | None = None, json=None, **extra):
        return self.client.post(path, json=json, headers=self.headers(account_id, **extra))

    def patch(self, path: str, account_id: str | None = None, json=None, **extra):
        return self.client.patch(path, json=json, headers=self.headers(account_id, **extra))

    def put(self, path: str, account_id: str | None = None, json=None, **extra):
        return self.client.put(path, json=json, headers=self.headers(account_id, **extra))

    def delete(self, path: str, account_id: str | None = None, **extra):
        return self.client.delete(path, headers=self.headers(account_id, **extra))


@pytest.fixture()
def settings_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "AI_ENABLED", "SMTP_HOST", "SMTP_FROM", "TELEGRAM_BOT_TOKEN", "PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture()
def client(settings_env):
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def api(client) -> Api:
    return Api(client)
