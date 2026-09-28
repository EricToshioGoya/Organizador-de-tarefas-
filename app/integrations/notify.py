"""Resumo diário por e-mail ou Telegram (RF56, RN29): atrasadas, vencimentos do dia e Top 3."""

from __future__ import annotations

import html
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage

import httpx

from ..config import Settings
from ..domain import rules
from ..domain.models import Account, Task
from ..domain.timeutil import fmt_date_br


class NotifyError(Exception):
    pass


def build_digest(tasks: list[Task], top3_ids: list[str], today: date) -> dict:
    by_id = {t.id: t for t in tasks}
    overdue = sorted((t for t in tasks if rules.is_overdue(t, today)), key=lambda t: t.due_date)
    due_today = [t for t in tasks if t.is_pending and t.due_date == today]
    top3 = [by_id[i] for i in top3_ids if i in by_id]
    return {"overdue": overdue, "due_today": due_today, "top3": top3}


def _line(task: Task, today: date) -> str:
    extra = []
    if task.due_date and task.due_date < today:
        days = (today - task.due_date).days
        extra.append(f"atrasada há {days} dia{'s' if days > 1 else ''}")
    if task.steps:
        extra.append(f"{rules.progress(task)}%")
    if task.requester:
        extra.append(f"@{task.requester}")
    return f"• {task.title}" + (f" ({', '.join(extra)})" if extra else "")


def digest_text(account: Account, digest: dict, today: date, app_url: str = "") -> str:
    lines = [f"Resumo do dia — {fmt_date_br(today)}", f"Olá, {account.name}!", ""]
    sections = (
        ("Atrasadas", digest["overdue"]),
        ("Vencem hoje", digest["due_today"]),
        ("Top 3 do dia", digest["top3"]),
    )
    for label, items in sections:
        lines.append(f"{label} ({len(items)})")
        lines.extend(_line(t, today) for t in items[:15])
        if not items:
            lines.append("• Nada por aqui.")
        if len(items) > 15:
            lines.append(f"• … e mais {len(items) - 15}")
        lines.append("")
    if app_url:
        lines.append(f"Abrir o organizador: {app_url}")
    return "\n".join(lines).strip() + "\n"


def digest_html(account: Account, digest: dict, today: date, app_url: str = "") -> str:
    esc = html.escape
    parts = [
        "<div style=\"font-family:Segoe UI,Arial,sans-serif;color:#111827\">",
        f"<h2 style=\"margin:0 0 4px\">Resumo do dia — {esc(fmt_date_br(today))}</h2>",
        f"<p style=\"margin:0 0 16px;color:#4b5563\">Olá, {esc(account.name)}!</p>",
    ]
    for label, items in (("Atrasadas", digest["overdue"]), ("Vencem hoje", digest["due_today"]), ("Top 3 do dia", digest["top3"])):
        parts.append(f"<h3 style=\"margin:16px 0 6px\">{esc(label)} ({len(items)})</h3><ul style=\"margin:0;padding-left:20px\">")
        if not items:
            parts.append("<li style=\"color:#6b7280\">Nada por aqui.</li>")
        for task in items[:15]:
            parts.append(f"<li>{esc(_line(task, today)[2:])}</li>")
        parts.append("</ul>")
    if app_url:
        parts.append(f"<p style=\"margin-top:20px\"><a href=\"{esc(app_url)}\">Abrir o organizador</a></p>")
    parts.append("</div>")
    return "".join(parts)


def send_email(settings: Settings, to: str, subject: str, text: str, html_body: str) -> None:
    if not settings.email_enabled:
        raise NotifyError("Envio de e-mail não configurado no servidor (SMTP).")
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ssl.create_default_context(), timeout=20) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotifyError(f"Falha no envio do e-mail: {exc}") from exc


def send_telegram(settings: Settings, chat_id: str, text: str) -> None:
    if not settings.telegram_enabled:
        raise NotifyError("Envio pelo Telegram não configurado no servidor (TELEGRAM_BOT_TOKEN).")
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise NotifyError(f"Falha ao contatar o Telegram: {exc.__class__.__name__}") from exc
    if response.status_code != 200:
        try:
            description = response.json().get("description", "")
        except ValueError:
            description = response.text[:200]
        raise NotifyError(f"O Telegram recusou a mensagem: {description}")


def send_digest(settings: Settings, account: Account, channel: str, tasks: list[Task], top3_ids: list[str], today: date) -> None:
    config = rules.merge_settings(account.settings)
    digest = build_digest(tasks, top3_ids, today)
    text = digest_text(account, digest, today, settings.public_url)
    if channel == "email":
        if not settings.email_enabled:
            raise NotifyError("Envio de e-mail não configurado no servidor (SMTP).")
        if not config["email"]:
            raise NotifyError("Informe um e-mail nas configurações da conta.")
        subject = f"Resumo do dia — {fmt_date_br(today)}: {len(digest['overdue'])} atrasada(s), {len(digest['due_today'])} para hoje"
        send_email(settings, config["email"], subject, text, digest_html(account, digest, today, settings.public_url))
    elif channel == "telegram":
        if not settings.telegram_enabled:
            raise NotifyError("Envio pelo Telegram não configurado no servidor (TELEGRAM_BOT_TOKEN).")
        if not config["telegram_chat_id"]:
            raise NotifyError("Informe o ID do chat do Telegram nas configurações da conta.")
        send_telegram(settings, config["telegram_chat_id"], text)
    else:
        raise NotifyError("Canal inválido.")
