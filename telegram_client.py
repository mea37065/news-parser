from __future__ import annotations

import json
import logging
from typing import Any

import requests

from app_config import Settings

logger = logging.getLogger(__name__)


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    def post(self, method: str, **payload: Any) -> dict[str, Any]:
        try:
            response = requests.post(
                f"{self.base_url}/{method}",
                json=payload,
                timeout=self.settings.telegram_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except Exception as error:
            logger.error("Telegram %s error: %s", method, error)
            return {}

    def get_updates(
        self,
        *,
        offset: int,
        allowed_updates: list[str],
    ) -> list[dict[str, Any]]:
        try:
            response = requests.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 2,
                    "allowed_updates": json.dumps(allowed_updates),
                },
                timeout=self.settings.telegram_timeout_seconds,
            )
            response.raise_for_status()
            return response.json().get("result", [])
        except Exception as error:
            logger.error("Telegram getUpdates error: %s", error)
            return []

    def send_message(
        self,
        *,
        text: str,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        chat_id: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id or self.settings.telegram_chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return self.post("sendMessage", **payload)

    def answer_callback(self, callback_id: str, text: str) -> None:
        self.post("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def remove_buttons(self, *, chat_id: str, message_id: int) -> None:
        self.post(
            "editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=json.dumps({"inline_keyboard": []}),
        )
