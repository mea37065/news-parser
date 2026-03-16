import feedparser
import requests
import json
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from ai_generator import generate_post
from devto_publisher import publish_to_devto

# ─────────────────────────────────────────
#  CONFIG — читається з env variables
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "YOUR_CHAT_ID")

SEEN_FILE    = Path(__file__).parent / "seen.json"
PENDING_FILE = Path(__file__).parent / "pending.json"

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
        for entry in feed.entries[:2]:  # 2 з кожного джерела = ~18 max
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
                "summary": entry.get("summary", "")[:500].strip(),
                "date":    pub_date,
            })
            seen.add(article_id)
    save_seen(seen)
    print(f"\n✅ New articles found: {len(new_articles)}")
    return new_articles

# ─────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────
def escape_md(text: str) -> str:
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)

def send_to_telegram_with_buttons(article: dict, post: dict, post_id: str):
    tags_str = " ".join(f"#{t}" for t in article["tags"])
    date_str = f"📅 {article['date']}\n" if article["date"] else ""
    preview  = post["body"][:300].strip()
    text = (
        f"{article['source']}\n"
        f"{date_str}"
        f"*{escape_md(article['title'])}*\n\n"
        f"{escape_md(preview)}…\n\n"
        f"🔗 [Original]({article['url']})\n"
        f"{tags_str}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Publish to Dev.to", "callback_data": f"publish:{post_id}"},
            {"text": "❌ Skip",              "callback_data": f"skip:{post_id}"},
        ]]
    }
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id":      TELEGRAM_CHAT_ID,
                "text":         text,
                "parse_mode":   "MarkdownV2",
                "reply_markup": json.dumps(keyboard),
            },
            timeout=10,
        )
        if not resp.ok:
            print(f"   ⚠️ Telegram error: {resp.text}")
    except Exception as e:
        print(f"   ❌ Send error: {e}")

def poll_telegram_once():
    """Перевіряє нові натискання кнопок і публікує якщо ✅"""
    pending = load_pending()
    if not pending:
        return
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 5, "allowed_updates": ["callback_query"]},
            timeout=10,
        )
        updates = resp.json().get("result", [])
    except Exception as e:
        print(f"❌ getUpdates error: {e}")
        return

    last_update_id = 0
    for update in updates:
        last_update_id = update["update_id"]
        cb = update.get("callback_query")
        if not cb:
            continue
        data  = cb.get("data", "")
        cb_id = cb["id"]

        if data.startswith("publish:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)
            if post:
                print(f"📤 Publishing to Dev.to: {post['title'][:60]}")
                result      = publish_to_devto(post, published=False)
                answer_text = "✅ Saved as draft on Dev.to!" if result else "❌ Publish error"
                if result:
                    del pending[post_id]
                    save_pending(pending)
            else:
                answer_text = "⚠️ Already processed"

        elif data.startswith("skip:"):
            post_id = data.split(":", 1)[1]
            if post_id in pending:
                del pending[post_id]
                save_pending(pending)
            answer_text = "⏭️ Skipped"
        else:
            continue

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": cb_id, "text": answer_text},
            timeout=5,
        )

    if last_update_id:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1},
            timeout=5,
        )

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def main():
    print(f"\n🚀 News Parser started — {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    print("🔄 Checking pending approvals...\n")
    poll_telegram_once()

    articles = parse_feeds()
    if not articles:
        print("📭 No new articles.")
        return

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       f"━━━━━━━━━━━━━━━━━━━━━━\n📰 *Digest {datetime.now().strftime('%d.%m.%Y')}*\nNew articles: {len(articles)}\n━━━━━━━━━━━━━━━━━━━━━━",
            "parse_mode": "Markdown",
        },
        timeout=10,
    )

    pending = load_pending()
    for i, article in enumerate(articles, 1):
        print(f"\n📰 ({i}/{len(articles)}) {article['title'][:60]}…")
        print(f"   🤖 Generating post via Gemini...")
        post = generate_post(article)
        if not post:
            print(f"   ⚠️ Skipping — generation failed")
            continue
        pending[article["id"]] = post
        save_pending(pending)
        send_to_telegram_with_buttons(article, post, article["id"])
        print(f"   ✅ Sent to Telegram")

    print(f"\n✅ Done! Press ✅ in Telegram to publish to Dev.to.")

if __name__ == "__main__":
    main()
