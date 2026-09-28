"""Integrações: IA (RF52), .ics (RF55), resumo diário (RF56), agendador e linha do tempo (RF48)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import load_settings
from app.domain.models import Account
from app.integrations import ai, ics, notify, scheduler
from app.services.timeline import build_timeline, describe

from .factories import NOW, TODAY, step, task


@pytest.fixture()
def settings(settings_env):
    return settings_env


# --- IA -------------------------------------------------------------------------------------------------------------


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, messages):
        self.messages = messages
        self.beta = SimpleNamespace(messages=messages)

    def with_options(self, **_):
        return self


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="fallback"), SimpleNamespace(type="text", text=text)])


def test_ai_disabled_without_credentials(settings):
    with pytest.raises(ai.AIError) as err:
        ai.generate_steps(settings, "Título", "")
    assert err.value.status == 503


def test_ai_generates_and_cleans_steps(settings, monkeypatch):
    enabled = replace(settings, anthropic_api_key="teste")
    messages = FakeMessages(_response(json.dumps({"steps": ["1. Definir escopo", "- Definir escopo", "  Reservar sala  ", ""]})))
    monkeypatch.setattr(ai, "_get_client", lambda _: FakeClient(messages))
    assert ai.generate_steps(enabled, "Planejar evento", "Com 50 pessoas") == ["Definir escopo", "Reservar sala"]
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5" and call["fallbacks"] == "default"
    assert call["output_config"]["effort"] == "low" and call["output_config"]["format"]["type"] == "json_schema"
    assert "<titulo>Planejar evento</titulo>" in call["messages"][0]["content"]


def test_ai_other_models_skip_fallbacks(settings, monkeypatch):
    enabled = replace(settings, anthropic_api_key="teste", anthropic_model="claude-haiku-4-5")
    messages = FakeMessages(_response('{"steps": ["Um"]}'))
    monkeypatch.setattr(ai, "_get_client", lambda _: FakeClient(messages))
    assert ai.generate_steps(enabled, "T", "") == ["Um"]
    assert "fallbacks" not in messages.calls[0] and "effort" not in messages.calls[0]["output_config"]


@pytest.mark.parametrize(
    ("response", "status"),
    [
        (_response("", "refusal"), 422),
        (_response('{"steps": [', "max_tokens"), 502),
        (_response("não é json"), 502),
        (_response('{"steps": []}'), 422),
    ],
)
def test_ai_bad_responses(settings, monkeypatch, response, status):
    enabled = replace(settings, anthropic_api_key="teste")
    monkeypatch.setattr(ai, "_get_client", lambda _: FakeClient(FakeMessages(response)))
    with pytest.raises(ai.AIError) as err:
        ai.generate_steps(enabled, "T", "")
    assert err.value.status == status


def test_ai_errors_are_translated(settings, monkeypatch):
    import anthropic
    import httpx2

    enabled = replace(settings, anthropic_api_key="teste")
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    errors = [
        (anthropic.APITimeoutError(request=request), 504),
        (anthropic.APIConnectionError(request=request), 503),
        (anthropic.RateLimitError("limite", response=httpx2.Response(429, request=request), body=None), 429),
        (anthropic.AuthenticationError("chave", response=httpx2.Response(401, request=request), body=None), 503),
        (anthropic.InternalServerError("falha", response=httpx2.Response(500, request=request), body=None), 502),
    ]
    for error, status in errors:
        monkeypatch.setattr(ai, "_get_client", lambda _, e=error: FakeClient(FakeMessages(error=e)))
        with pytest.raises(ai.AIError) as err:
            ai.generate_steps(enabled, "T", "")
        assert err.value.status == status


# --- Calendário -------------------------------------------------------------------------------------------------------


def test_ics_escape_and_fold():
    assert ics.escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"
    long_line = "SUMMARY:" + "ç" * 60
    folded = ics.fold(long_line)
    assert all(len(part.encode("utf-8")) <= 75 for part in folded.split("\r\n"))
    assert folded.replace("\r\n ", "") == long_line


def test_ics_calendar_marks_done_tasks():
    done = task(title="Feita", due=TODAY, completed=NOW, requester="Ana", description="Detalhes")
    body = ics.build_calendar("Ana", [done, task(title="Sem data")], NOW, "https://tarefas.exemplo")
    assert "SUMMARY:✓ Feita" in body and "URL:https://tarefas.exemplo/#/tarefa/" in body
    assert body.count("BEGIN:VEVENT") == 1 and body.endswith("END:VCALENDAR\r\n")


# --- Resumo diário ---------------------------------------------------------------------------------------------------------


ACCOUNT = Account(id="acc-1", name="Ana", color="#fff", settings={"email": "ana@ex.com", "telegram_chat_id": "12345"})


def _tasks():
    late = task(title="Atrasada <b>", due=TODAY - timedelta(days=2), requester="Carlos", steps=[step(True, NOW), step()])
    today = task(title="Para hoje", due=TODAY)
    top = task(title="Prioridade")
    return [late, today, top], [top.id]


def test_digest_content():
    tasks, top3 = _tasks()
    digest = notify.build_digest(tasks, top3, TODAY)
    assert [len(digest[k]) for k in ("overdue", "due_today", "top3")] == [1, 1, 1]
    text = notify.digest_text(ACCOUNT, digest, TODAY, "https://app")
    assert "atrasada há 2 dias" in text and "50%" in text and "@Carlos" in text and "https://app" in text
    html_body = notify.digest_html(ACCOUNT, digest, TODAY, "https://app")
    assert "Atrasada &lt;b&gt;" in html_body  # conteúdo do usuário escapado (RNF13)
    empty = notify.digest_text(ACCOUNT, notify.build_digest([], [], TODAY), TODAY)
    assert empty.count("Nada por aqui.") == 3


def test_send_email_and_telegram(settings, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, **_):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, message):
            sent["to"] = message["To"]

    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    configured = replace(settings, smtp_host="smtp.ex.com", smtp_from="bot@ex.com", smtp_user="bot", smtp_password="x", telegram_bot_token="tok")
    tasks, top3 = _tasks()
    notify.send_digest(configured, ACCOUNT, "email", tasks, top3, TODAY)
    assert sent == {"server": ("smtp.ex.com", 587), "tls": True, "login": "bot", "to": "ana@ex.com"}

    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted.update(url=url, json=json)
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True}, text="")

    monkeypatch.setattr(notify.httpx, "post", fake_post)
    notify.send_digest(configured, ACCOUNT, "telegram", tasks, top3, TODAY)
    assert posted["url"].endswith("/bottok/sendMessage") and posted["json"]["chat_id"] == "12345"

    monkeypatch.setattr(notify.httpx, "post", lambda *a, **k: SimpleNamespace(status_code=400, json=lambda: {"description": "chat not found"}, text=""))
    with pytest.raises(notify.NotifyError, match="chat not found"):
        notify.send_digest(configured, ACCOUNT, "telegram", tasks, top3, TODAY)


def test_send_digest_requires_configuration(settings):
    tasks, top3 = _tasks()
    with pytest.raises(notify.NotifyError, match="SMTP"):
        notify.send_digest(settings, ACCOUNT, "email", tasks, top3, TODAY)
    with pytest.raises(notify.NotifyError, match="TELEGRAM"):
        notify.send_digest(settings, ACCOUNT, "telegram", tasks, top3, TODAY)
    blank = Account(id="x", name="X", color="#fff")
    configured = replace(settings, smtp_host="h", smtp_from="f", telegram_bot_token="t")
    with pytest.raises(notify.NotifyError, match="e-mail"):
        notify.send_digest(configured, blank, "email", [], [], TODAY)
    with pytest.raises(notify.NotifyError, match="Telegram"):
        notify.send_digest(configured, blank, "telegram", [], [], TODAY)
    with pytest.raises(notify.NotifyError):
        notify.send_digest(configured, blank, "sms", [], [], TODAY)


def test_scheduler_picks_accounts_at_their_time(api, settings, monkeypatch):
    ana = api.account("Ana")
    api.patch(
        f"/api/accounts/{ana['id']}",
        ana["id"],
        json={"settings": {"digest_enabled": True, "digest_time": "08:00", "digest_channels": ["email"], "email": "ana@ex.com", "timezone": "America/Sao_Paulo"}},
    )
    api.account("Bia")  # sem resumo configurado
    at_time = datetime(2026, 9, 23, 11, 5, tzinfo=timezone.utc)  # 08:05 em São Paulo
    assert scheduler.due_digests(settings, at_time) == [(ana["id"], "email", "2026-09-23")]
    assert scheduler.due_digests(settings, at_time - timedelta(hours=1)) == []
    assert scheduler.due_digests(settings, at_time + timedelta(hours=3)) == []

    assert scheduler.deliver(settings, ana["id"], "email", "2026-09-23") == "falhou"  # SMTP não configurado
    assert scheduler.due_digests(settings, at_time) == []  # registrado: não reenvia no mesmo dia
    assert scheduler.deliver(settings, "nao-existe", "email", "2026-09-23") == "conta_inexistente"


def test_digest_test_endpoint(api):
    ana, bia = api.account("Ana"), api.account("Bia")
    response = api.post(f"/api/accounts/{ana['id']}/digest/test", ana["id"], json={"channel": "email"})
    assert response.status_code == 502 and "SMTP" in response.json()["detail"]
    assert api.post(f"/api/accounts/{ana['id']}/digest/test", bia["id"], json={"channel": "email"}).status_code == 403


# --- Linha do tempo --------------------------------------------------------------------------------------------------------


def _event(seq, kind, payload=None, minutes=0, actor="a1", mutation="m"):
    return {
        "seq": seq,
        "type": kind,
        "payload": payload or {},
        "occurred_at": (NOW + timedelta(minutes=minutes)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "actor_id": actor,
        "actor_name": "Ana",
        "mutation_id": mutation,
    }


def test_timeline_descriptions_cover_all_events():
    samples = [
        ("TarefaCriada", {"source": "template", "template_name": "Modelo", "steps": [{}, {}]}),
        ("TarefaCriada", {"source": "quickadd"}),
        ("TarefaCriada", {}),
        ("TarefaEditada", {"changes": {"difficulty": {"old": "facil", "new": "dificil"}, "links": {"old": ["https://a"], "new": ["https://b"]}}}),
        ("TarefaEditada", {"changes": {"requester": {"old": "", "new": "Carlos"}}}),
        ("TarefaEditada", {"changes": {"description": {"old": "", "new": "x"}}}),
        ("PrazoAlterado", {"kind": "adiamento", "old": "2026-09-25", "new": "2026-09-30", "reason": "outro", "reason_text": "Viagem"}),
        ("PrazoAlterado", {"kind": "antecipacao", "old": "2026-09-30", "new": "2026-09-28"}),
        ("PrazoAlterado", {"kind": "definicao", "new": "2026-09-28"}),
        ("PrazoAlterado", {"kind": "remocao", "old": "2026-09-28"}),
        ("FaseAlterada", {"old": "planejamento", "new": "producao"}),
        ("MetaVinculada", {"goal_title": "Nova", "old_goal_title": "Velha"}),
        ("MetaVinculada", {"goal_title": "Nova"}),
        ("MetaDesvinculada", {"goal_title": "Velha"}),
        ("TarefaConcluida", {"auto": False}),
        ("TarefaReaberta", {"auto": True}),
        ("EtapaEditada", {"step_id": "s", "old_text": "a", "text": "b"}),
        ("EtapaConcluida", {"text": "x" * 100}),
        ("EtapaDesmarcada", {"text": "x"}),
        ("EtapaRemovida", {"text": "x"}),
        ("EtapasReordenadas", {}),
        ("AnexoAdicionado", {"filename": "a.pdf"}),
        ("AnexoRemovido", {"filename": "a.pdf"}),
        ("AtribuicaoVisualizada", {}),
    ]
    for kind, payload in samples:
        entry = describe(_event(1, kind, payload))
        assert entry is not None and entry["text"], kind
    assert describe(_event(1, "ComentarioAdicionado", {"text": "segredo"})) is None  # RN36
    assert describe(_event(1, "Desconhecido")) is None
    assert "Motivo: Outro — Viagem" == describe(_event(1, *samples[6]))["detail"]
    assert describe(_event(1, *samples[0]))["text"] == "Tarefa criada a partir de “Modelo”"  # cópia de outra tarefa
    assert describe(_event(1, "EtapaConcluida", {"text": "x" * 100}))["text"].endswith("…”")


def test_timeline_merges_consecutive_edits_and_bulk_steps():
    events = [
        _event(1, "TarefaEditada", {"changes": {"notes": {"old": "", "new": "a"}}}, 0),
        _event(2, "TarefaEditada", {"changes": {"notes": {"old": "a", "new": "ab"}}}, 5),
        _event(3, "TarefaEditada", {"changes": {"notes": {"old": "ab", "new": "abc"}}}, 30),
        _event(4, "EtapaAdicionada", {"text": "1", "source": "ai"}, 31, mutation="lote"),
        _event(5, "EtapaAdicionada", {"text": "2"}, 31, mutation="lote"),
        _event(6, "ComentariosLidos", {}, 32),
    ]
    items = build_timeline(events)
    assert [i["count"] for i in items] == [2, 1, 2]
    assert items[2]["text"] == "2 etapas adicionadas" and items[2]["detail"] == "Sugerida por IA e confirmada"


def test_load_settings_reads_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("AI_ENABLED", "sim")
    monkeypatch.setenv("PUBLIC_URL", "https://app/")
    loaded = load_settings()
    assert loaded.db_path == tmp_path / "organizador.sqlite3" and loaded.uploads_dir == tmp_path / "uploads"
    assert loaded.smtp_port == 465 and loaded.ai_enabled and loaded.public_url == "https://app"
    assert not loaded.email_enabled and not loaded.telegram_enabled
