import requests
import os

# ─────────────────────────────────────────
#  CONFIG
#  Отримай токен через OAuth 2.0
#  і збережи в змінній середовища LINKEDIN_ACCESS_TOKEN
# ─────────────────────────────────────────
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")
LINKEDIN_API          = "https://api.linkedin.com/v2"

# ─────────────────────────────────────────
#  ОТРИМАТИ URN поточного користувача
# ─────────────────────────────────────────
def get_linkedin_urn() -> str | None:
    resp = requests.get(
        f"{LINKEDIN_API}/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=10,
    )
    if resp.ok:
        sub = resp.json().get("sub")  # sub = "urn:li:person:XXXXXXX"
        return f"urn:li:person:{sub}" if sub and not sub.startswith("urn") else sub
    print(f"❌ LinkedIn auth error: {resp.status_code} — {resp.text}")
    return None

# ─────────────────────────────────────────
#  ПЕРЕВІРКА ПІДКЛЮЧЕННЯ
# ─────────────────────────────────────────
def check_linkedin_connection() -> bool:
    resp = requests.get(
        f"{LINKEDIN_API}/userinfo",
        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
        timeout=10,
    )
    if resp.ok:
        data = resp.json()
        print(f"✅ Connected to LinkedIn as: {data.get('name')} ({data.get('email')})")
        return True
    print(f"❌ LinkedIn connection error: {resp.status_code} — {resp.text}")
    return False

# ─────────────────────────────────────────
#  ПУБЛІКАЦІЯ
# ─────────────────────────────────────────
def publish_to_linkedin(post: dict) -> dict | None:
    """
    Публікує пост у LinkedIn.

    post — dict з ключами: title, body, tags, source_url
    """
    urn = get_linkedin_urn()
    if not urn:
        return None

    # Формуємо текст поста
    tags_str = " ".join(f"#{t.replace(' ', '')}" for t in post.get("tags", []))
    text = (
        f"{post['title']}\n\n"
        f"{post['body'][:2800]}\n\n"
        f"🔗 {post.get('source_url', '')}\n\n"
        f"{tags_str}"
    ).strip()

    payload = {
        "author":          urn,
        "lifecycleState":  "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": text
                },
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    try:
        resp = requests.post(
            f"{LINKEDIN_API}/ugcPosts",
            headers={
                "Authorization":  f"Bearer {LINKEDIN_ACCESS_TOKEN}",
                "Content-Type":   "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data   = resp.json()
        post_id = data.get("id", "n/a")
        print(f"✅ Posted to LinkedIn!")
        print(f"   Post ID: {post_id}")
        return data

    except Exception as e:
        print(f"❌ LinkedIn publish error: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"   Details: {e.response.text}")
        return None


# ─────────────────────────────────────────
#  ТЕСТ
# ─────────────────────────────────────────
if __name__ == "__main__":
    print("🔍 Checking LinkedIn connection...\n")
    if check_linkedin_connection():
        test_post = {
            "title":      "Test Post from News AI Parser",
            "body":       "This is a test post generated automatically.\n\nIt works! 🎉",
            "tags":       ["cybersecurity", "devops", "automation"],
            "source_url": "https://example.com",
        }
        print("\n📤 Publishing test post...\n")
        publish_to_linkedin(test_post)
