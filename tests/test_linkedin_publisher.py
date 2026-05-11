from __future__ import annotations

import json

from app_config import Settings
from linkedin_publisher import extract_preview_image_url, publish_to_linkedin


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


def test_extract_preview_image_url_prefers_open_graph_image() -> None:
    html = """
    <html>
      <head>
        <meta name="twitter:image" content="https://cdn.example.com/twitter.jpg">
        <meta property="og:image" content="/images/preview.jpg">
      </head>
    </html>
    """

    assert (
        extract_preview_image_url(html, "https://example.com/articles/story")
        == "https://example.com/images/preview.jpg"
    )


def test_publish_to_linkedin_includes_article_thumbnail(
    tmp_path,
    monkeypatch,
) -> None:
    settings = build_settings(tmp_path)
    captured_payload: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"id": "share-1"}

    def fake_post(*args, **kwargs):
        captured_payload.update(kwargs["json"])
        return FakeResponse()

    monkeypatch.setattr(
        "linkedin_publisher.get_linkedin_urn",
        lambda settings: "urn:li:person:123",
    )
    monkeypatch.setattr("linkedin_publisher.requests.post", fake_post)

    result = publish_to_linkedin(
        settings,
        {
            "title": "Cloud update",
            "body": "A short LinkedIn post.",
            "tags": ["cloud"],
            "source_url": "https://example.com/cloud",
            "thumbnail_url": "https://example.com/images/cloud.jpg",
        },
    )

    assert result == {"id": "share-1"}
    share_content = captured_payload["specificContent"][
        "com.linkedin.ugc.ShareContent"
    ]
    media = share_content["media"][0]
    assert media["thumbnails"] == [
        {
            "url": "https://example.com/images/cloud.jpg",
            "altText": "Cloud update",
        }
    ]
