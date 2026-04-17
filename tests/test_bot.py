from __future__ import annotations

import json

from app_config import Settings
from bot import handle_callbacks
from storage import (
    ARTICLE_STATUS_PUBLISHED,
    ARTICLE_STATUS_REVIEWING,
    Storage,
)


class FakeTelegramClient:
    def __init__(self, updates):
        self._updates = updates
        self.messages: list[dict[str, object]] = []
        self.answered: list[str] = []
        self.removed: list[tuple[str, int]] = []

    def get_updates(self, *, offset: int, allowed_updates: list[str]):
        return self._updates

    def answer_callback(self, callback_id: str, text: str) -> None:
        self.answered.append(text)

    def remove_buttons(self, *, chat_id: str, message_id: int) -> None:
        self.removed.append((chat_id, message_id))

    def send_message(self, **payload):
        self.messages.append(payload)
        return {"result": {"message_id": 999}}


def build_settings(tmp_path) -> Settings:
    feeds_path = tmp_path / "feeds.json"
    feeds_path.write_text(json.dumps([]), encoding="utf-8")
    return Settings(
        telegram_bot_token="token",
        telegram_chat_id="chat-id",
        groq_api_key="groq-key",
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


def queue_article(storage: Storage) -> None:
    storage.add_discovered_article(
        {
            "id": "article-1",
            "fingerprint": "fingerprint-1",
            "source": "Example Feed",
            "tags": ["cloud"],
            "title": "Cloud update",
            "url": "https://example.com/cloud",
            "summary": "Summary",
            "article_text": "Longer article text.",
            "date": "09.04.2026",
        }
    )
    storage.queue_article(
        "article-1",
        recap="Recap",
        linkedin_body="Short LinkedIn text\n\n#cloud #news",
        telegram_message_id=10,
    )


def test_handle_callbacks_moves_article_to_reviewing(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "linkedin:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_REVIEWING
    assert telegram.messages


def test_handle_callbacks_publishes_to_linkedin(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "linkedin_confirm:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )
    monkeypatch.setattr(
        "bot.publish_to_linkedin",
        lambda settings, post: {"id": "share-1"},
    )

    handle_callbacks(settings, storage, telegram)

    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_PUBLISHED
    assert article["linkedin_post_id"] == "share-1"


def test_handle_callbacks_cancel_requeues_article(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_reviewing("article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "linkedin_cancel:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            },
            {
                "update_id": 2,
                "callback_query": {
                    "id": "cb-2",
                    "data": "linkedin:article-1",
                    "message": {
                        "message_id": 999,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_REVIEWING
    assert article["telegram_message_id"] == 999
    assert len(telegram.messages) == 2
    assert telegram.answered[:2] == [
        "Cancelled. Review is available again.",
        "Check the LinkedIn preview below.",
    ]


def test_handle_callbacks_regenerates_linkedin_preview(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_reviewing("article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "linkedin_regenerate:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )
    monkeypatch.setattr(
        "bot.regenerate_linkedin_post",
        lambda settings, article: "Fresh LinkedIn wording\n\n#cloud #update",
    )

    handle_callbacks(settings, storage, telegram)

    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_REVIEWING
    assert article["linkedin_body"] == "Fresh LinkedIn wording\n\n#cloud #update"
    assert telegram.answered == ["Generated a new version."]
    assert telegram.removed == [("chat-id", 321)]
    assert telegram.messages
    assert "Fresh LinkedIn wording" in str(telegram.messages[-1]["text"])


def test_handle_callbacks_enters_edit_mode(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_reviewing("article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "linkedin_edit:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    assert storage.get_state("pending_edit:chat-id") == "article-1"
    assert telegram.answered == ["Send the replacement text in chat."]
    assert telegram.messages
    assert "Edit mode is active" in str(telegram.messages[-1]["text"])


def test_handle_callbacks_saves_manual_linkedin_edit(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_reviewing("article-1")
    storage.set_state("pending_edit:chat-id", "article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "message": {
                    "message_id": 555,
                    "chat": {"id": "chat-id"},
                    "text": "Manual LinkedIn rewrite\n\n#cloud #infra",
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    article = storage.get_article("article-1")
    assert article is not None
    assert article["status"] == ARTICLE_STATUS_REVIEWING
    assert article["linkedin_body"] == "Manual LinkedIn rewrite\n\n#cloud #infra"
    assert storage.get_state("pending_edit:chat-id") == ""
    assert len(telegram.messages) == 2
    assert (
        telegram.messages[0]["text"]
        == "Draft updated. Here is the refreshed LinkedIn preview."
    )
    assert "Manual LinkedIn rewrite" in str(telegram.messages[1]["text"])


def test_handle_callbacks_closes_edit_mode_on_cancel_command(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_reviewing("article-1")
    storage.set_state("pending_edit:chat-id", "article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "message": {
                    "message_id": 556,
                    "chat": {"id": "chat-id"},
                    "text": "/cancel",
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    assert storage.get_state("pending_edit:chat-id") == ""
    assert telegram.messages
    assert (
        telegram.messages[-1]["text"]
        == "Edit mode closed. Review is still available for this story."
    )


def test_handle_callbacks_enters_question_mode(tmp_path) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "callback_query": {
                    "id": "cb-1",
                    "data": "ask:article-1",
                    "message": {
                        "message_id": 321,
                        "chat": {"id": "chat-id"},
                    },
                },
            }
        ]
    )

    handle_callbacks(settings, storage, telegram)

    assert storage.get_state("pending_question:chat-id") == "article-1"
    assert telegram.messages
    assert "Question mode is active" in str(telegram.messages[-1]["text"])


def test_handle_callbacks_answers_follow_up_question(tmp_path, monkeypatch) -> None:
    settings = build_settings(tmp_path)
    storage = Storage(settings.storage_path)
    queue_article(storage)
    storage.set_state("pending_question:chat-id", "article-1")
    telegram = FakeTelegramClient(
        [
            {
                "update_id": 1,
                "message": {
                    "message_id": 444,
                    "chat": {"id": "chat-id"},
                    "text": "What changed here?",
                },
            }
        ]
    )
    monkeypatch.setattr(
        "bot.generate_article_answer",
        lambda settings, article, question: "The update focused on a cloud release.",
    )

    handle_callbacks(settings, storage, telegram)

    assert telegram.messages
    assert telegram.messages[-1]["text"] == "The update focused on a cloud release."
    assert telegram.messages[-1]["reply_to_message_id"] == 444
