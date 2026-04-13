from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments
    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False

from credentials import load_credentials

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    groq_api_key: str
    groq_model: str
    linkedin_access_token: str
    telegram_timeout_seconds: int
    poll_interval_seconds: int
    schedule_timezone_name: str
    daily_run_hour: int
    daily_run_minute: int
    max_entries_per_feed: int
    storage_path: Path
    feeds_path: Path
    article_fetch_timeout_seconds: int
    article_text_char_limit: int
    groq_request_delay_seconds: int
    groq_request_timeout_seconds: int
    groq_max_retries: int

    @property
    def schedule_timezone(self) -> ZoneInfo:
        return ZoneInfo(self.schedule_timezone_name)


def _get_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"Environment variable {name} must be an integer.") from error


def load_runtime_environment() -> None:
    raw_env_file = os.environ.get("ENV_FILE", "").strip()
    env_candidates: list[Path] = []

    if raw_env_file:
        env_candidates.append(Path(raw_env_file).expanduser())
    env_candidates.extend(
        [
            BASE_DIR / ".env",
            BASE_DIR.parent / ".env",
        ]
    )

    loaded_env_file = False
    seen_paths: set[Path] = set()
    for candidate in env_candidates:
        if not candidate or candidate in seen_paths:
            continue
        seen_paths.add(candidate)
        if not candidate.exists():
            continue
        if load_dotenv(dotenv_path=candidate, override=False):
            logger.info("Loaded environment variables from %s", candidate)
        else:
            logger.info(
                "Environment file detected but nothing was loaded from %s",
                candidate,
            )
        loaded_env_file = True
        break

    if not loaded_env_file:
        logger.warning(
            "No .env file was found in %s or %s. "
            "The service will rely on environment variables "
            "or Windows Credential Manager.",
            BASE_DIR,
            BASE_DIR.parent,
        )

    load_credentials(required=False)


def load_settings(
    *,
    validate_secrets: bool = True,
    require_linkedin: bool = True,
) -> Settings:
    load_runtime_environment()

    settings = Settings(
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
        groq_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
        linkedin_access_token=os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip(),
        telegram_timeout_seconds=_get_int("TELEGRAM_TIMEOUT_SECONDS", 10),
        poll_interval_seconds=_get_int("POLL_INTERVAL_SECONDS", 3),
        schedule_timezone_name=os.environ.get(
            "SCHEDULE_TIMEZONE",
            "Europe/Bratislava",
        ).strip(),
        daily_run_hour=_get_int("DAILY_RUN_HOUR", 8),
        daily_run_minute=_get_int("DAILY_RUN_MINUTE", 0),
        max_entries_per_feed=_get_int("MAX_ENTRIES_PER_FEED", 2),
        storage_path=BASE_DIR
        / os.environ.get("STORAGE_PATH", "news_parser.db").strip(),
        feeds_path=BASE_DIR / os.environ.get("FEEDS_PATH", "feeds.json").strip(),
        article_fetch_timeout_seconds=_get_int("ARTICLE_FETCH_TIMEOUT_SECONDS", 10),
        article_text_char_limit=_get_int("ARTICLE_TEXT_CHAR_LIMIT", 4000),
        groq_request_delay_seconds=_get_int("GROQ_REQUEST_DELAY_SECONDS", 3),
        groq_request_timeout_seconds=_get_int("GROQ_REQUEST_TIMEOUT_SECONDS", 30),
        groq_max_retries=_get_int("GROQ_MAX_RETRIES", 3),
    )

    if validate_secrets:
        required = {
            "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
            "TELEGRAM_CHAT_ID": settings.telegram_chat_id,
        }
        if require_linkedin:
            required["LINKEDIN_ACCESS_TOKEN"] = settings.linkedin_access_token
        missing = [name for name, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"Missing required configuration values: {joined}")

    try:
        ZoneInfo(settings.schedule_timezone_name)
    except ZoneInfoNotFoundError as error:
        raise RuntimeError(
            "Missing timezone data for "
            f"{settings.schedule_timezone_name}. "
            "Install the tzdata package or set SCHEDULE_TIMEZONE to a valid timezone."
        ) from error

    return settings


def load_feed_configs(settings: Settings) -> list[dict[str, Any]]:
    with open(settings.feeds_path, encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, list):
        raise ValueError("feeds.json must contain a list of feed definitions.")

    feeds: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each feed definition must be an object.")
        name = str(item.get("name", "")).strip()
        url = str(item.get("url", "")).strip()
        tags = item.get("tags", [])
        if not name or not url or not isinstance(tags, list):
            raise ValueError("Each feed requires name, url, and tags fields.")
        feeds.append(
            {
                "name": name,
                "url": url,
                "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
            }
        )

    return feeds
