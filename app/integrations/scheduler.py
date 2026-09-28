"""Agendador do resumo diário (RF56): verifica a cada 30 s quem deve receber o resumo no horário configurado."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from ..config import Settings
from ..domain import rules
from ..domain.timeutil import get_tz, to_iso, utcnow
from ..store import repo
from ..store.db import connect
from . import notify

log = logging.getLogger("organizador.scheduler")
CATCH_UP = timedelta(hours=2)  # envia atrasado se o servidor estava fora do ar no horário, por até 2 h
INTERVAL_S = 30


def due_digests(settings: Settings, now: datetime) -> list[tuple[str, str, str]]:
    """Retorna (conta, canal, dia) que devem ser enviados agora."""
    conn = connect(settings.db_path)
    try:
        pending: list[tuple[str, str, str]] = []
        for account in repo.list_accounts(conn):
            config = rules.merge_settings(account.settings)
            if not config["digest_enabled"] or not config["digest_channels"]:
                continue
            tz = get_tz(config["timezone"], settings.timezone)
            local_now = now.astimezone(tz)
            hour, minute = (int(x) for x in config["digest_time"].split(":"))
            scheduled = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if not (scheduled <= local_now <= scheduled + CATCH_UP):
                continue
            day = local_now.date().isoformat()
            for channel in config["digest_channels"]:
                sent = conn.execute(
                    "SELECT 1 FROM digest_log WHERE account_id = ? AND day = ? AND channel = ?",
                    (account.id, day, channel),
                ).fetchone()
                if sent is None:
                    pending.append((account.id, channel, day))
        return pending
    finally:
        conn.close()


def deliver(settings: Settings, account_id: str, channel: str, day: str) -> str:
    conn = connect(settings.db_path)
    try:
        account = repo.get_account(conn, account_id)
        if account is None:
            return "conta_inexistente"
        tz = get_tz(rules.merge_settings(account.settings)["timezone"], settings.timezone)
        today = utcnow().astimezone(tz).date()
        tasks = repo.list_tasks(conn, account_id)
        top3 = repo.get_top3(conn, account_id, today)
        status, detail = "enviado", ""
        try:
            notify.send_digest(settings, account, channel, tasks, top3, today)
        except notify.NotifyError as exc:
            status, detail = "falhou", str(exc)
            log.warning("Resumo diário não enviado (%s, %s): %s", account.name, channel, exc)
        conn.execute(
            "INSERT OR REPLACE INTO digest_log(account_id, day, channel, sent_at, status, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (account_id, day, channel, to_iso(utcnow()), status, detail),
        )
        return status
    finally:
        conn.close()


async def run_scheduler(settings: Settings, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            for account_id, channel, day in await asyncio.to_thread(due_digests, settings, utcnow()):
                await asyncio.to_thread(deliver, settings, account_id, channel, day)
        except Exception:  # pragma: no cover - o agendador nunca deve derrubar o servidor
            log.exception("Erro no agendador do resumo diário")
        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_S)
        except asyncio.TimeoutError:
            pass
