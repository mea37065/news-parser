from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser

from ai_generator import generate_daily_summary, generate_story_assets
from app_config import Settings, load_feed_configs, load_settings
from content_fetcher import fetch_article_text
from logging_config import configure_logging
from storage import Storage
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)


def strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def normalize_hashtag(tag: str) -> str:
    clean_tag = re.sub(r"[^A-Za-z0-9]+", "", tag)
    return clean_tag or "news"


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", "")
    )


def make_id(url: str) -> str:
    return hashlib.md5(canonicalize_url(url).encode("utf-8")).hexdigest()


def make_fingerprint(title: str, published_at: str, url: str) -> str:
    basis = "|".join(
        [
            normalize_title(title),
            published_at.strip(),
            canonicalize_url(url),
        ]
    )
    return hashlib.md5(basis.encode("utf-8")).hexdigest()


def build_fallback_recap(article: dict[str, Any]) -> str:
    article_text = article.get("article_text", "").strip()
    summary = article["summary"].strip()
    body = article_text or summary
    if not body:
        return article["title"]
    if article["title"].lower() in body.lower():
        return body[:700].strip()
    return f"{article['title']}. {body[:650].strip()}".strip()


def build_fallback_linkedin_post(article: dict[str, Any]) -> str:
    body = strip_html(article.get("summary", "")).strip()
    if not body:
        body = build_fallback_recap(article)
    body = body[:220].rstrip(" .,;:")
    hashtags = " ".join(f"#{normalize_hashtag(tag)}" for tag in article["tags"][:3])
    return f"{body}\n\n{hashtags}".strip()


def _published_date(entry: Any) -> str:
    if getattr(entry, "published_parsed", None):
        return datetime(
            *entry.published_parsed[:6],
            tzinfo=UTC,
        ).strftime("%d.%m.%Y")
    return ""


def discover_articles(settings: Settings, storage: Storage) -> int:
    discovered = 0
    for feed_config in load_feed_configs(settings):
        logger.info("Parsing feed: %s", feed_config["name"])
        try:
            feed = feedparser.parse(feed_config["url"])
        except Exception as error:
            logger.warning("Feed error for %s: %s", feed_config["name"], error)
            continue

        if getattr(feed, "bozo", False):
            logger.warning(
                "Feed parser warning for %s: %s",
                feed_config["name"],
                feed.bozo_exception,
            )

        for entry in feed.entries[: settings.max_entries_per_feed]:
            url = str(entry.get("link", "")).strip()
            if not url:
                continue

            published_at = _published_date(entry)
            title = str(entry.get("title", "No title")).strip() or "No title"
            article = {
                "id": make_id(url),
                "fingerprint": make_fingerprint(title, published_at, url),
                "source": feed_config["name"],
                "tags": feed_config["tags"],
                "title": title,
                "url": url,
                "summary": strip_html(entry.get("summary", ""))[:800].strip(),
                "date": published_at,
            }
            article["article_text"] = fetch_article_text(
                url,
                timeout_seconds=settings.article_fetch_timeout_seconds,
                char_limit=settings.article_text_char_limit,
            )

            if storage.add_discovered_article(article):
                discovered += 1

    logger.info("New articles discovered: %s", discovered)
    return discovered


def send_to_telegram_with_buttons(
    telegram: TelegramClient,
    article: dict[str, Any],
    *,
    post_id: str,
    preview_text: str,
) -> int | None:
    tags_str = " ".join(f"#{normalize_hashtag(tag)}" for tag in article["tags"])
    date_line = f"{article['date']}\n" if article["date"] else ""
    preview = preview_text[:300].strip()
    text = (
        f"{escape_html(article['source'])}\n"
        f"{escape_html(date_line)}"
        f"<b>{escape_html(article['title'])}</b>\n\n"
        f"{escape_html(preview)}...\n\n"
        f"Source: <a href=\"{article['url']}\">Original article</a>\n"
        f"{escape_html(tags_str)}"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Review LinkedIn", "callback_data": f"linkedin:{post_id}"},
                {"text": "Ask a question", "callback_data": f"ask:{post_id}"},
            ]
        ]
    }
    response = telegram.send_message(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    result = response.get("result", {})
    message_id = result.get("message_id")
    return int(message_id) if message_id is not None else None


def build_daily_metrics(
    articles: list[dict[str, Any]],
    ai_story_count: int,
) -> dict[str, Any]:
    source_counts = Counter(article["source"] for article in articles)
    tag_counts = Counter(tag for article in articles for tag in article["tags"])

    total_articles = len(articles)
    top_source, top_source_count = ("n/a", 0)
    if source_counts:
        top_source, top_source_count = source_counts.most_common(1)[0]

    security_tags = {"cybersecurity", "cve", "vulnerability", "sentinelone"}
    cloud_tags = {"aws", "cloud", "kubernetes", "devops", "vmware"}

    security_count = sum(
        1
        for article in articles
        if any(tag.lower() in security_tags for tag in article["tags"])
    )
    cloud_count = sum(
        1
        for article in articles
        if any(tag.lower() in cloud_tags for tag in article["tags"])
    )
    avg_recap_words = 0
    if total_articles:
        avg_recap_words = round(
            sum(len(article["recap"].split()) for article in articles) / total_articles
        )

    return {
        "date": datetime.now().strftime("%d.%m.%Y"),
        "total_articles": total_articles,
        "unique_sources": len(source_counts),
        "top_source": top_source,
        "top_source_count": top_source_count,
        "top_tag": tag_counts.most_common(1)[0][0] if tag_counts else "n/a",
        "security_count": security_count,
        "cloud_count": cloud_count,
        "avg_recap_words": avg_recap_words,
        "ai_story_count": ai_story_count,
    }


def build_fallback_daily_summary(
    articles: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str:
    story_lines = []
    for article in articles:
        recap = str(article.get("recap") or article.get("summary") or "").strip()
        condensed = recap[:180].rstrip(" .,;:")
        story_lines.append(
            f"{article['title']} from {article['source']} focused on {condensed}."
        )

    opening = (
        f"Today's briefing covered {metrics['total_articles']} fresh stories from "
        f"{metrics['unique_sources']} sources. The busiest source was "
        f"{metrics['top_source']} with {metrics['top_source_count']} items, and the "
        f"overall mix leaned toward {metrics['top_tag']}, security, and cloud updates."
    )
    coverage = " ".join(story_lines)
    close = (
        f"Security-related coverage accounted for {metrics['security_count']} items, "
        f"cloud and platform changes appeared in {metrics['cloud_count']}, and the "
        f"average recap length landed at about {metrics['avg_recap_words']} words."
    )
    return f"{opening}\n\n{coverage}\n\n{close}".strip()


def format_daily_summary_message(
    summary_text: str,
    metrics: dict[str, Any],
) -> str:
    return (
        f"Daily Briefing - {metrics['date']}\n\n"
        f"{summary_text}\n\n"
        "Quick metrics:\n"
        f"- Articles: {metrics['total_articles']}\n"
        f"- Sources: {metrics['unique_sources']}\n"
        f"- Most active source: {metrics['top_source']} "
        f"({metrics['top_source_count']})\n"
        f"- Dominant tag: {metrics['top_tag']}\n"
        f"- Security items: {metrics['security_count']}\n"
        f"- Cloud/DevOps items: {metrics['cloud_count']}\n"
        f"- Average recap size: {metrics['avg_recap_words']} words\n"
        f"- AI story coverage: {metrics['ai_story_count']}/{metrics['total_articles']}"
    )


def run_parse_cycle(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient | None = None,
) -> int:
    telegram_client = telegram or TelegramClient(settings)
    logger.info("Parse cycle started at %s", datetime.now().strftime("%d.%m.%Y %H:%M"))

    discover_articles(settings, storage)
    articles = storage.get_articles_for_processing()
    if not articles:
        logger.info("No new articles to process.")
        telegram_client.send_message(
            text=(
                f"Daily Briefing - {datetime.now().strftime('%d.%m.%Y')}\n\n"
                "No new articles were found in today's run."
            )
        )
        return 0

    processed_articles: list[dict[str, Any]] = []
    sent_count = 0
    ai_story_count = 0

    for index, article in enumerate(articles, start=1):
        logger.info(
            "Processing article %s/%s: %s",
            index,
            len(articles),
            article["title"][:80],
        )

        assets = generate_story_assets(settings, article)
        if assets:
            recap = assets["recap"]
            linkedin_body = assets["linkedin_post"]
            ai_story_count += 1
        else:
            logger.warning(
                "AI assets unavailable, using fallback text for %s",
                article["title"],
            )
            recap = build_fallback_recap(article)
            linkedin_body = build_fallback_linkedin_post(article)

        message_id = send_to_telegram_with_buttons(
            telegram_client,
            article,
            post_id=article["id"],
            preview_text=recap,
        )
        if message_id is None:
            storage.mark_delivery_failed(
                article["id"],
                recap=recap,
                linkedin_body=linkedin_body,
            )
            logger.error("Telegram delivery failed for article: %s", article["title"])
            continue

        storage.queue_article(
            article["id"],
            recap=recap,
            linkedin_body=linkedin_body,
            telegram_message_id=message_id,
        )
        processed_articles.append(
            {
                **article,
                "recap": recap,
                "linkedin_body": linkedin_body,
            }
        )
        sent_count += 1

    if processed_articles:
        metrics = build_daily_metrics(processed_articles, ai_story_count=ai_story_count)
        summary_text = generate_daily_summary(settings, processed_articles, metrics)
        if not summary_text:
            logger.warning(
                "Daily summary AI generation unavailable, using fallback summary."
            )
            summary_text = build_fallback_daily_summary(processed_articles, metrics)
        telegram_client.send_message(
            text=format_daily_summary_message(summary_text, metrics)
        )

    logger.info(
        "Parse cycle finished. Sent %s articles (%s AI-generated asset bundles).",
        sent_count,
        ai_story_count,
    )
    return sent_count


def main() -> None:
    configure_logging()
    settings = load_settings(require_linkedin=False)
    storage = Storage(settings.storage_path)
    run_parse_cycle(settings, storage)


if __name__ == "__main__":
    main()
