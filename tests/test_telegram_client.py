from __future__ import annotations

import logging

import requests

from app_config import Settings
from telegram_client import TelegramClient


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: dict[str, object],
        url: str,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.url = url

    def json(self) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} Client Error for url: {self.url}",
                response=self,
            )


def build_settings(tmp_path, *, token: str = "secret-token") -> Settings:
    feeds_path = tmp_path / "feeds.json"
    feeds_path.write_text("[]", encoding="utf-8")
    return Settings(
        telegram_bot_token=token,
        telegram_chat_id="chat-id",
        groq_api_key="",
        groq_model="model",
        linkedin_access_token="linkedin-token",
        telegram_timeout_seconds=5,
        poll_interval_seconds=3,
        schedule_timezone_name="Europe/Bratislava",
        daily_run_hour=8,
        daily_run_minute=0,
        max_entries_per_feed=2,
        storage_path=tmp_path / "state.db",
        feeds_path=feeds_path,
        article_fetch_timeout_seconds=5,
        article_text_char_limit=2000,
        groq_request_delay_seconds=0,
        groq_request_timeout_seconds=5,
        groq_max_retries=1,
    )


def test_get_updates_retries_after_telegram_rate_limit(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    client = TelegramClient(settings)
    responses = [
        FakeResponse(
            status_code=429,
            payload={
                "ok": False,
                "description": "Too Many Requests: retry after 7",
                "parameters": {"retry_after": 7},
            },
            url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
        ),
        FakeResponse(
            status_code=200,
            payload={"ok": True, "result": [{"update_id": 123}]},
            url=f"https://api.telegram.org/bot{settings.telegram_bot_token}/getUpdates",
        ),
    ]
    sleeps: list[int] = []

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("telegram_client.requests.get", fake_get)
    monkeypatch.setattr(
        "telegram_client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    updates = client.get_updates(offset=0, allowed_updates=["callback_query"])

    assert updates == [{"update_id": 123}]
    assert sleeps == [7]
    assert responses == []


def test_telegram_errors_do_not_log_bot_token(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    token = "secret-token"
    settings = build_settings(tmp_path, token=token)
    client = TelegramClient(settings)

    def fake_post(*args, **kwargs):
        return FakeResponse(
            status_code=404,
            payload={"ok": False, "description": "Not found"},
            url=f"https://api.telegram.org/bot{token}/sendMessage",
        )

    monkeypatch.setattr("telegram_client.requests.post", fake_post)

    with caplog.at_level(logging.ERROR):
        client.send_message(text="Hello")

    assert token not in caplog.text
    assert "<redacted>" in caplog.text
