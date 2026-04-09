from __future__ import annotations

from storage import (
    ARTICLE_STATUS_PUBLISHED,
    ARTICLE_STATUS_QUEUED,
    ARTICLE_STATUS_REVIEWING,
    Storage,
)


def test_storage_article_lifecycle(tmp_path) -> None:
    storage = Storage(tmp_path / "state.db")
    article = {
        "id": "article-1",
        "fingerprint": "fingerprint-1",
        "source": "Source",
        "tags": ["tag"],
        "title": "Title",
        "url": "https://example.com/post",
        "summary": "Summary",
        "article_text": "Longer article text",
        "date": "09.04.2026",
    }

    assert storage.add_discovered_article(article) is True
    assert storage.add_discovered_article({**article, "id": "article-2"}) is False

    queued = storage.get_articles_for_processing()
    assert [item["id"] for item in queued] == ["article-1"]

    storage.queue_article(
        "article-1",
        recap="Recap",
        linkedin_body="LinkedIn",
        telegram_message_id=42,
    )
    queued_article = storage.get_article("article-1")
    assert queued_article is not None
    assert queued_article["status"] == ARTICLE_STATUS_QUEUED
    assert queued_article["telegram_message_id"] == 42

    storage.set_reviewing("article-1")
    assert storage.get_article("article-1")["status"] == ARTICLE_STATUS_REVIEWING

    storage.mark_published("article-1", linkedin_post_id="urn:li:share:1")
    published_article = storage.get_article("article-1")
    assert published_article is not None
    assert published_article["status"] == ARTICLE_STATUS_PUBLISHED
    assert published_article["linkedin_post_id"] == "urn:li:share:1"


def test_storage_app_state_roundtrip(tmp_path) -> None:
    storage = Storage(tmp_path / "state.db")
    storage.set_state("telegram_offset", "12")
    assert storage.get_state("telegram_offset") == "12"
