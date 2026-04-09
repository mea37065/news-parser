from __future__ import annotations

from app_config import load_settings
from bot import handle_callbacks
from logging_config import configure_logging
from storage import Storage
from telegram_client import TelegramClient


def main() -> None:
    configure_logging()
    settings = load_settings()
    storage = Storage(settings.storage_path)
    telegram = TelegramClient(settings)
    handle_callbacks(settings, storage, telegram)


if __name__ == "__main__":
    main()
