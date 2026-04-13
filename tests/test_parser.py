from __future__ import annotations

import json

from app_config import Settings
from parser import run_parse_cycle
from storage import ARTICLE_STATUS_QUEUED, Storage


class FakeTelegramClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def send_message(self, **payload):
        self.messages.append(payload)
        if "reply_markup" in payload:
            return {"result": {"message_id": 101}}
        return {"result": {"message_id": 202}}


def build_settings(tmp_path) -> Settings:
    feeds_path = tmp_path / "feeds.json"
    feeds_path.write_text(json.dumps([]), encoding="utf-8")
    return Settings(
        telegram_bot_token="token",
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


def test_run_parse_cycle_queues_articles_and_sends_summary(
    tmp_path,
    monkeypatch,
) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    telegram = FakeTelegramClient()

    storage.add_discovered_article(
        {
            "id": "article-1",
            "fingerprint": "fingerprint-1",
            "source": "Example Feed",
            "tags": ["AWS", "cloud"],
            "title": "Cloud update released",
            "url": "https://example.com/cloud",
            "summary": "A short update about a cloud release.",
            "article_text": "A longer body with release details.",
            "date": "09.04.2026",
        }
    )

    monkeypatch.setattr("parser.generate_story_assets", lambda settings, article: None)
    monkeypatch.setattr(
        "parser.generate_daily_summary",
        lambda settings, articles, metrics: None,
    )

    sent_count = run_parse_cycle(settings, storage, telegram)

    assert sent_count == 1
    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_QUEUED
    assert len(telegram.messages) == 2
    assert "Daily Briefing" in telegram.messages[-1]["text"]
    first_message = telegram.messages[0]
    reply_markup = first_message["reply_markup"]
    assert reply_markup["inline_keyboard"][0][1]["text"] == "Ask a question"
