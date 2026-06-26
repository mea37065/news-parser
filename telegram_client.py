from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from app_config import Settings

logger = logging.getLogger(__name__)

MAX_TELEGRAM_ATTEMPTS = 2


class TelegramClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    def _safe_error_message(self, error: Exception) -> str:
        message = str(error)
        token = self.settings.telegram_bot_token
        if token:
            message = message.replace(token, "<redacted>")
        return message

    def _retry_after_seconds(self, response: requests.Response) -> int | None:
        retry_after: object | None = None
        description = ""

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if isinstance(payload, dict):
            parameters = payload.get("parameters")
            if isinstance(parameters, dict):
                retry_after = parameters.get("retry_after")
            description = str(payload.get("description") or "")

        if retry_after is None and description:
            match = re.search(r"retry after (\d+)", description, flags=re.I)
            if match:
                retry_after = match.group(1)

        try:
            seconds = int(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            return None

        return max(seconds, 1) if seconds is not None else None

    def _request_json(self, method: str, request: Any) -> dict[str, Any]:
        for attempt in range(1, MAX_TELEGRAM_ATTEMPTS + 1):
            try:
                response = request()
                if response.status_code == 429 and attempt < MAX_TELEGRAM_ATTEMPTS:
                    retry_after = self._retry_after_seconds(response) or 1
                    logger.warning(
                        "Telegram %s rate limited. Retrying after %s seconds.",
                        method,
                        retry_after,
                    )
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    if payload.get("ok") is False:
                        logger.error(
                            "Telegram %s error: %s",
                            method,
                            payload.get("description", "API response was not ok"),
                        )
                        return {}
                    return payload
                logger.error("Telegram %s error: unexpected JSON response.", method)
                return {}
            except Exception as error:
                logger.error(
                    "Telegram %s error: %s",
                    method,
                    self._safe_error_message(error),
                )
                return {}

        return {}

    def post(self, method: str, **payload: Any) -> dict[str, Any]:
        return self._request_json(
            method,
            lambda: requests.post(
                f"{self.base_url}/{method}",
                json=payload,
                timeout=self.settings.telegram_timeout_seconds,
            ),
        )

    def get_updates(
        self,
        *,
        offset: int,
        allowed_updates: list[str],
    ) -> list[dict[str, Any]]:
        payload = self._request_json(
            "getUpdates",
            lambda: requests.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": offset,
                    "timeout": 2,
                    "allowed_updates": json.dumps(allowed_updates),
                },
                timeout=self.settings.telegram_timeout_seconds,
            ),
        )
        result = payload.get("result", [])
        return result if isinstance(result, list) else []

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
