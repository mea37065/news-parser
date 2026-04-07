from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

import feedparser
import requests

from ai_generator import (
    generate_article_recap,
    generate_daily_summary,
    generate_linkedin_post,
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SEEN_FILE = Path(__file__).parent / "seen.json"
PENDING_FILE = Path(__file__).parent / "pending.json"

TELEGRAM_TIMEOUT_SECONDS = 10
MAX_ENTRIES_PER_FEED = 2

FEEDS = [
    {
        "name": "Red NVD High CVEs",
        "url": "https://cvefeed.io/rssfeed/severity/high.xml",
        "tags": ["CVE", "vulnerability"],
    },
    {
        "name": "Red The Hacker News",
        "url": "https://feeds.feedburner.com/TheHackersNews",
        "tags": ["cybersecurity"],
    },
    {
        "name": "Red Krebs on Security",
        "url": "https://krebsonsecurity.com/feed/",
        "tags": ["cybersecurity"],
    },
    {
        "name": "Orange Hacker News Top",
        "url": "https://hnrss.org/frontpage",
        "tags": ["hackernews", "tech"],
    },
    {
        "name": "Blue VMware Blog",
        "url": "https://blogs.vmware.com/feed",
        "tags": ["VMware"],
    },
    {
        "name": "Blue VMware Security",
        "url": "https://via.vmw.com/sec-advisories-rss",
        "tags": ["VMware", "CVE"],
    },
    {
        "name": "Purple SentinelOne Blog",
        "url": "https://www.sentinelone.com/blog/feed/",
        "tags": ["SentinelOne"],
    },
    {
        "name": "Cloud AWS News",
        "url": "https://aws.amazon.com/blogs/aws/feed/",
        "tags": ["AWS", "cloud"],
    },
    {
        "name": "Cloud Kubernetes Blog",
        "url": "https://kubernetes.io/feed.xml",
        "tags": ["Kubernetes", "DevOps"],
    },
]


def strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        with open(path, encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def _save_json(path: Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_seen() -> set[str]:
    return set(_load_json(SEEN_FILE, []))


def save_seen(seen: set[str]) -> None:
    _save_json(SEEN_FILE, sorted(seen))


def make_id(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def load_pending() -> dict[str, Any]:
    return _load_json(PENDING_FILE, {})


def save_pending(pending: dict[str, Any]) -> None:
    _save_json(PENDING_FILE, pending)


def parse_feeds() -> list[dict[str, Any]]:
    seen = load_seen()
    new_articles: list[dict[str, Any]] = []

    for feed_config in FEEDS:
        print(f"Parsing: {feed_config['name']}")
        try:
            feed = feedparser.parse(feed_config["url"])
        except Exception as error:
            print(f"   Feed error: {error}")
            continue

        for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
            url = entry.get("link", "")
            if not url:
                continue

            article_id = make_id(url)
            if article_id in seen:
                continue

            published_at = ""
            if getattr(entry, "published_parsed", None):
                published_at = datetime(
                    *entry.published_parsed[:6],
                    tzinfo=timezone.utc,
                ).strftime("%d.%m.%Y")

            new_articles.append(
                {
                    "id": article_id,
                    "source": feed_config["name"],
                    "tags": feed_config["tags"],
                    "title": entry.get("title", "No title"),
                    "url": url,
                    "summary": strip_html(entry.get("summary", ""))[:500].strip(),
                    "date": published_at,
                }
            )
            seen.add(article_id)

    save_seen(seen)
    print(f"\nNew articles found: {len(new_articles)}")
    return new_articles


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def normalize_hashtag(tag: str) -> str:
    clean_tag = re.sub(r"[^A-Za-z0-9]+", "", tag)
    return clean_tag or "news"


def build_fallback_recap(article: dict[str, Any]) -> str:
    summary = article["summary"].strip()
    if not summary:
        return article["title"]
    if article["title"].lower() in summary.lower():
        return summary
    return f"{article['title']}. {summary}"


def build_fallback_linkedin_post(article: dict[str, Any]) -> str:
    body = build_fallback_recap(article)
    hashtags = " ".join(
        f"#{normalize_hashtag(tag)}" for tag in article["tags"][:3]
    )
    return f"{body[:700].strip()}\n\n{hashtags}".strip()


def send_to_telegram_with_buttons(
    article: dict[str, Any],
    post: dict[str, Any],
    post_id: str,
) -> None:
    tags_str = " ".join(f"#{normalize_hashtag(tag)}" for tag in article["tags"])
    date_line = f"{article['date']}\n" if article["date"] else ""
    preview = post["body"][:300].strip()
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
                {"text": "Skip", "callback_data": f"skip:{post_id}"},
            ]
        ]
    }

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": json.dumps(keyboard),
            },
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
        if not response.ok:
            print(f"   Telegram send error: {response.text}")
    except Exception as error:
        print(f"   Telegram request error: {error}")


def send_telegram_text(text: str, parse_mode: str | None = None) -> None:
    payload: dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
    except Exception as error:
        print(f"   Telegram text error: {error}")


def build_daily_metrics(
    articles: list[dict[str, Any]],
    ai_recap_count: int,
    ai_linkedin_count: int,
) -> dict[str, Any]:
    source_counts = Counter(article["source"] for article in articles)
    tag_counts = Counter(
        tag
        for article in articles
        for tag in article["tags"]
    )

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
        "ai_recap_count": ai_recap_count,
        "ai_linkedin_count": ai_linkedin_count,
    }


def build_fallback_daily_summary(metrics: dict[str, Any]) -> str:
    return (
        f"Today's batch included {metrics['total_articles']} stories from "
        f"{metrics['unique_sources']} sources. The busiest feed was "
        f"{metrics['top_source']} with {metrics['top_source_count']} items, "
        f"while the mix leaned toward {metrics['top_tag']} and related topics. "
        f"Security-focused stories accounted for {metrics['security_count']} items, "
        f"and cloud or platform updates appeared in {metrics['cloud_count']}."
    )


def format_daily_summary_message(
    summary_text: str,
    metrics: dict[str, Any],
) -> str:
    return (
        f"Daily Summary - {metrics['date']}\n\n"
        f"{summary_text}\n\n"
        "Metrics:\n"
        f"- Articles: {metrics['total_articles']}\n"
        f"- Sources: {metrics['unique_sources']}\n"
        f"- Most active source: {metrics['top_source']} ({metrics['top_source_count']})\n"
        f"- Dominant tag: {metrics['top_tag']}\n"
        f"- Security items: {metrics['security_count']}\n"
        f"- Cloud/DevOps items: {metrics['cloud_count']}\n"
        f"- Average recap size: {metrics['avg_recap_words']} words\n"
        f"- AI recap coverage: {metrics['ai_recap_count']}/{metrics['total_articles']}\n"
        f"- AI LinkedIn coverage: {metrics['ai_linkedin_count']}/{metrics['total_articles']}"
    )


def run_parse_cycle() -> int:
    print(f"\nParse cycle - {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    articles = parse_feeds()
    if not articles:
        print("No new articles.")
        send_telegram_text(
            f"Daily Summary - {datetime.now().strftime('%d.%m.%Y')}\n\n"
            "No new articles were found in today's run."
        )
        return 0

    pending = load_pending()
    processed_articles: list[dict[str, Any]] = []
    sent_count = 0
    ai_recap_count = 0
    ai_linkedin_count = 0

    for index, article in enumerate(articles, start=1):
        print(f"\nArticle {index}/{len(articles)}: {article['title'][:80]}")

        print("   Generating recap...")
        recap = generate_article_recap(article)
        if recap:
            ai_recap_count += 1
        else:
            print("   AI recap unavailable, using fallback recap.")
            recap = build_fallback_recap(article)

        print("   Generating LinkedIn post...")
        linkedin_body = generate_linkedin_post(article)
        if linkedin_body:
            ai_linkedin_count += 1
        else:
            print("   AI LinkedIn generation unavailable, using fallback post.")
            linkedin_body = build_fallback_linkedin_post(article)

        post = {
            "title": article["title"],
            "body": recap,
            "tags": article["tags"],
            "source_url": article["url"],
            "linkedin_body": linkedin_body,
        }

        pending[article["id"]] = post
        save_pending(pending)
        send_to_telegram_with_buttons(article, post, article["id"])

        processed_articles.append(
            {
                **article,
                "recap": recap,
                "linkedin_body": linkedin_body,
            }
        )
        sent_count += 1
        print("   Sent to Telegram.")

    metrics = build_daily_metrics(
        processed_articles,
        ai_recap_count=ai_recap_count,
        ai_linkedin_count=ai_linkedin_count,
    )
    summary_text = generate_daily_summary(processed_articles, metrics)
    if not summary_text:
        print("Daily summary AI generation unavailable, using fallback summary.")
        summary_text = build_fallback_daily_summary(metrics)

    send_telegram_text(format_daily_summary_message(summary_text, metrics))

    print(
        f"\nDone. Sent {sent_count} articles "
        f"({ai_recap_count} AI recaps, {ai_linkedin_count} AI LinkedIn posts)."
    )
    return sent_count


def main() -> None:
    run_parse_cycle()


if __name__ == "__main__":
    main()
