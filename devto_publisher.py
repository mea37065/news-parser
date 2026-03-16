import requests
import os

# ─────────────────────────────────────────
#  CONFIG
#  Отримай ключ: dev.to/settings/extensions
#  → "DEV Community API Keys" → Generate API Key
# ─────────────────────────────────────────
DEVTO_API_KEY = os.environ.get("DEVTO_API_KEY", "YOUR_DEVTO_API_KEY")
DEVTO_API     = "https://dev.to/api"

# ─────────────────────────────────────────
#  ПЕРЕВІРКА ПІДКЛЮЧЕННЯ (запускається один раз)
# ─────────────────────────────────────────
def check_devto_connection() -> bool:
    resp = requests.get(
        f"{DEVTO_API}/users/me",
        headers={"api-key": DEVTO_API_KEY},
        timeout=10,
    )
    if resp.ok:
        user = resp.json()
        print(f"✅ Connected to Dev.to as: @{user.get('username')} ({user.get('name')})")
        return True
    print(f"❌ Dev.to connection error: {resp.status_code} — {resp.text}")
    return False

# ─────────────────────────────────────────
#  ПУБЛІКАЦІЯ
# ─────────────────────────────────────────
def publish_to_devto(post: dict, published: bool = False) -> dict | None:
    """
    Публікує пост на Dev.to.

    post      — dict з ключами: title, body, tags, source_url
    published — False = зберегти як draft, True = одразу опублікувати
    """

    # Dev.to приймає теги тільки в нижньому регістрі, без пробілів, макс 4
    clean_tags = [
        t.lower().replace(" ", "").replace("-", "")
        for t in post.get("tags", [])
    ][:4]

    # Додаємо посилання на оригінал в кінці статті
    body_with_source = (
        post["body"]
        + f"\n\n---\n*Originally published at: {post.get('source_url', '')}*"
    )

    payload = {
        "article": {
            "title":             post["title"],
            "body_markdown":     body_with_source,
            "published":         published,
            "tags":              clean_tags,
            "canonical_url":     post.get("source_url", ""),
        }
    }

    try:
        resp = requests.post(
            f"{DEVTO_API}/articles",
            headers={
                "api-key":      DEVTO_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        status = "published" if published else "draft"
        print(f"✅ Posted to Dev.to as {status}!")
        print(f"   URL: {data.get('url', 'n/a')}")
        return data

    except Exception as e:
        print(f"❌ Dev.to publish error: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Details: {e.response.text}")
        return None


# ─────────────────────────────────────────
#  ТЕСТ
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("🔍 Checking Dev.to connection...\n")
    if check_devto_connection():
        test_post = {
            "title":      "Test Post from News Bot",
            "body":       "This is a test post generated automatically.\n\nIt works! 🎉",
            "tags":       ["cybersecurity", "devops", "automation"],
            "source_url": "https://example.com",
        }
        print("\n📤 Publishing test post as draft...\n")
        publish_to_devto(test_post, published=False)
