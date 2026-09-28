"""Configuração lida de variáveis de ambiente (arquivo .env opcional na raiz do projeto)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file, override=False)
        except ImportError:  # pragma: no cover - python-dotenv é dependência declarada
            pass


def _default_data_dir() -> Path:
    # No Windows, os dados ficam fora do OneDrive: sincronizar um SQLite em uso pode corrompê-lo.
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "OrganizadorDeTarefas" / "data"
    return BASE_DIR / "data"


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "sim", "yes", "on")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    timezone: str
    public_url: str
    anthropic_api_key: str
    anthropic_model: str
    ai_timeout_s: float
    ai_force_enabled: bool
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    telegram_bot_token: str
    max_upload_mb: int
    scheduler_enabled: bool

    @property
    def db_path(self) -> Path:
        return self.data_dir / "organizador.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def ai_enabled(self) -> bool:
        # AI_ENABLED=true cobre credenciais resolvidas pelo SDK sem variável de chave (ex.: `ant auth login`).
        return bool(self.anthropic_api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN") or self.ai_force_enabled)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)


def load_settings() -> Settings:
    _load_dotenv()
    env = os.environ.get
    return Settings(
        data_dir=Path(env("DATA_DIR") or _default_data_dir()),
        timezone=env("APP_TIMEZONE") or "America/Sao_Paulo",
        public_url=(env("PUBLIC_URL") or "").rstrip("/"),
        anthropic_api_key=env("ANTHROPIC_API_KEY") or "",
        anthropic_model=env("ANTHROPIC_MODEL") or "claude-opus-5",
        ai_timeout_s=float(env("AI_TIMEOUT_S") or 10),
        ai_force_enabled=_bool(env("AI_ENABLED"), False),
        smtp_host=env("SMTP_HOST") or "",
        smtp_port=int(env("SMTP_PORT") or 587),
        smtp_user=env("SMTP_USER") or "",
        smtp_password=env("SMTP_PASSWORD") or "",
        smtp_from=env("SMTP_FROM") or "",
        smtp_starttls=_bool(env("SMTP_STARTTLS"), True),
        telegram_bot_token=env("TELEGRAM_BOT_TOKEN") or "",
        max_upload_mb=int(env("MAX_UPLOAD_MB") or 20),
        scheduler_enabled=_bool(env("SCHEDULER_ENABLED"), True),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
