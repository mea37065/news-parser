import feedparser
import requests
import json
import hashlib
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from html import unescape

from ai_generator import generate_post, generate_linkedin_post
from devto_publisher import publish_to_devto
from linkedin_publisher import publish_to_linkedin

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

SEEN_FILE    = Path(__file__).parent / "seen.json"
PENDING_FILE = Path(__file__).parent / "pending.json"

def strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# ─────────────────────────────────────────
#  RSS FEEDS
# ─────────────────────────────────────────
FEEDS = [
    {"name": "🔴 NVD High CVEs",     "url": "https://cvefeed.io/rssfeed/severity/high.xml",   "tags": ["CVE", "vulnerability"]},
    {"name": "🔴 The Hacker News",   "url": "https://feeds.feedburner.com/TheHackersNews",     "tags": ["cybersecurity"]},
    {"name": "🔴 Krebs on Security", "url": "https://krebsonsecurity.com/feed/",               "tags": ["cybersecurity"]},
    {"name": "🟠 Hacker News Top",   "url": "https://hnrss.org/frontpage",                    "tags": ["hackernews", "tech"]},
    {"name": "🔵 VMware Blog",       "url": "https://blogs.vmware.com/feed",                  "tags": ["VMware"]},
    {"name": "🔵 VMware Security",   "url": "https://via.vmw.com/sec-advisories-rss",         "tags": ["VMware", "CVE"]},
    {"name": "🟣 SentinelOne Blog",  "url": "https://www.sentinelone.com/blog/feed/",          "tags": ["SentinelOne"]},
    {"name": "☁️ AWS News",         "url": "https://aws.amazon.com/blogs/aws/feed/",          "tags": ["AWS", "cloud"]},
    {"name": "☁️ Kubernetes Blog",  "url": "https://kubernetes.io/feed.xml",                 "tags": ["Kubernetes", "DevOps"]},
]

# ─────────────────────────────────────────
#  DEDUPLICATION
# ─────────────────────────────────────────
def load_seen() -> set:
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen)), f, indent=2)

def make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def load_pending() -> dict:
    if PENDING_FILE.exists():
        with open(PENDING_FILE) as f:
            return json.load(f)
    return {}

def save_pending(pending: dict):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

# ─────────────────────────────────────────
#  PARSE RSS
# ─────────────────────────────────────────
def parse_feeds() -> list[dict]:
    seen = load_seen()
    new_articles = []
    for feed_cfg in FEEDS:
        print(f"⏳ Parsing: {feed_cfg['name']}")
        try:
            feed = feedparser.parse(feed_cfg["url"])
        except Exception as e:
            print(f"   ❌ Error: {e}")
            continue
        for entry in feed.entries[:2]:
            url = entry.get("link", "")
            if not url:
                continue
            article_id = make_id(url)
            if article_id in seen:
                continue
            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).strftime("%d.%m.%Y")
            new_articles.append({
                "id":      article_id,
                "source":  feed_cfg["name"],
                "tags":    feed_cfg["tags"],
                "title":   entry.get("title", "No title"),
                "url":     url,
                "summary": strip_html(entry.get("summary", ""))[:500].strip(),
                "date":    pub_date,
            })
            seen.add(article_id)
    save_seen(seen)
    print(f"\n✅ New articles found: {len(new_articles)}")
    return new_articles

# ─────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────
def escape_html(text: str) -> str:
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def send_to_telegram_with_buttons(article: dict, post: dict, post_id: str):
    tags_str = " ".join(f"#{t}" for t in article["tags"])
    date_str = f"📅 {article['date']}\n" if article["date"] else ""
    preview  = post["body"][:300].strip()
    text = (
        f"{article['source']}\n"
        f"{date_str}"
        f"<b>{escape_html(article['title'])}</b>\n\n"
        f"{escape_html(preview)}…\n\n"
        f"🔗 <a href=\"{article['url']}\">Original</a>\n"
        f"{tags_str}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Dev.to",    "callback_data": f"publish:{post_id}"},
            {"text": "🔵 LinkedIn", "callback_data": f"linkedin:{post_id}"},
            {"text": "❌ Skip",     "callback_data": f"skip:{post_id}"},
        ]]
    }
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id":      TELEGRAM_CHAT_ID,
                "text":         text,
                "parse_mode":   "HTML",
                "reply_markup": json.dumps(keyboard),
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"   ⚠️ Telegram error: {resp.text}")
    except Exception as e:
        print(f"   ❌ Send error: {e}")

def send_telegram_text(text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )

# ─────────────────────────────────────────
#  MAIN CYCLE (викликається з bot.py)
# ─────────────────────────────────────────
def run_parse_cycle():
    print(f"\n🚀 Parse cycle — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    articles = parse_feeds()
    if not articles:
        print("📭 No new articles.")
        send_telegram_text("📭 No new articles today.")
        return 0

    pending    = load_pending()
    sent_count = 0
    ai_count   = 0

    for i, article in enumerate(articles, 1):
        print(f"\n📰 ({i}/{len(articles)}) {article['title'][:60]}…")
        print(f"   🤖 Generating Dev.to post...")
        post = generate_post(article)

        if post:
            ai_count += 1
        else:
            print(f"   ⚠️ AI unavailable — using original summary")
            post = {
                "title":      article["title"],
                "body":       article["summary"] or "No summary available.",
                "tags":       article["tags"],
                "source_url": article["url"],
            }

        # Окремий короткий пост для LinkedIn
        print(f"   🔵 Generating LinkedIn post...")
        linkedin_body = generate_linkedin_post(article)
        if not linkedin_body:
            linkedin_body = f"{article['title']}\n\n{article['summary'][:200]}\n\n{article['url']}"
        post["linkedin_body"] = linkedin_body

        pending[article["id"]] = post
        save_pending(pending)
        send_to_telegram_with_buttons(article, post, article["id"])
        sent_count += 1
        print(f"   ✅ Sent to Telegram")

    ai_note = f"AI-generated: {ai_count}/{sent_count}" if ai_count < sent_count else "AI-generated: all"
    send_telegram_text(
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📰 *Digest {datetime.now().strftime('%d.%m.%Y')}*\n"
        f"Articles: {sent_count} | {ai_note}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

    print(f"\n✅ Done! {sent_count} articles sent ({ai_count} AI-generated).")
    return sent_count


def main():
    run_parse_cycle()

if __name__ == "__main__":
    main()