from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    bot_name: str = "Sin Trade AI"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1/chat/completions"
    openai_site_url: str = ""
    openai_app_name: str = "Sin Trade AI"
    openai_timeout_seconds: float = 20.0


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Missing TELEGRAM_BOT_TOKEN. Add it to your environment or a .env file."
        )
    return Settings(
        telegram_bot_token=token,
        openai_api_key=get_openai_api_key(),
        openai_model=get_openai_model(),
        openai_base_url=get_openai_base_url(),
        openai_site_url=get_openai_site_url(),
        openai_app_name=get_openai_app_name(),
        openai_timeout_seconds=get_openai_timeout_seconds(),
    )


def get_openai_api_key() -> str:
    return os.getenv("OPENAI_API_KEY", "").strip()


def get_openai_model() -> str:
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    return model or "gpt-4.1-mini"


def get_openai_base_url() -> str:
    base_url = os.getenv(
        "OPENAI_BASE_URL",
        "https://api.openai.com/v1/chat/completions",
    ).strip()
    return base_url or "https://api.openai.com/v1/chat/completions"


def get_openai_site_url() -> str:
    return os.getenv("OPENAI_SITE_URL", "").strip()


def get_openai_app_name() -> str:
    app_name = os.getenv("OPENAI_APP_NAME", "Sin Trade AI").strip()
    return app_name or "Sin Trade AI"


def get_openai_timeout_seconds() -> float:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "20").strip()
    try:
        value = float(raw)
    except ValueError:
        return 20.0
    return max(3.0, min(value, 60.0))

