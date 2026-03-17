"""
Окремий скрипт для обробки натискань кнопок в Telegram.
Запускається кожні 5 хвилин через GitHub Actions.
"""
import requests
import json
import os
from pathlib import Path

from devto_publisher import publish_to_devto
from linkedin_publisher import publish_to_linkedin

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")
PENDING_FILE       = Path(__file__).parent / "pending.json"

def load_pending() -> dict:
    if PENDING_FILE.exists():
        with open(PENDING_FILE) as f:
            return json.load(f)
    return {}

def save_pending(pending: dict):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

def answer_callback(cb_id: str, text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": cb_id, "text": text},
        timeout=5,
    )

def edit_message_reply_markup(chat_id: str, message_id: int):
    """Прибирає кнопки з повідомлення після обробки."""
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageReplyMarkup",
        json={
            "chat_id":      chat_id,
            "message_id":   message_id,
            "reply_markup": json.dumps({"inline_keyboard": []}),
        },
        timeout=5,
    )

def main():
    pending = load_pending()

    if not pending:
        print("📭 No pending posts.")
        return

    print(f"⏳ Checking Telegram callbacks ({len(pending)} pending posts)...")

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"timeout": 3, "allowed_updates": ["callback_query"]},
            timeout=10,
        )
        updates = resp.json().get("result", [])
    except Exception as e:
        print(f"❌ getUpdates error: {e}")
        return

    if not updates:
        print("📭 No new callbacks.")
        return

    last_update_id = 0
    processed = 0

    for update in updates:
        last_update_id = update["update_id"]
        cb = update.get("callback_query")
        if not cb:
            continue

        data       = cb.get("data", "")
        cb_id      = cb["id"]
        message_id = cb.get("message", {}).get("message_id")

        if data.startswith("publish:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)

            if post:
                print(f"📤 Publishing to Dev.to: {post['title'][:60]}")
                result = publish_to_devto(post, published=False)

                if result:
                    answer_callback(cb_id, "✅ Saved as draft on Dev.to!")
                    if message_id:
                        edit_message_reply_markup(TELEGRAM_CHAT_ID, message_id)
                    del pending[post_id]
                    save_pending(pending)
                    processed += 1
                else:
                    answer_callback(cb_id, "❌ Publish failed, try again")
            else:
                answer_callback(cb_id, "⚠️ Already processed")

        elif data.startswith("linkedin:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)

            if post:
                print(f"🔵 Publishing to LinkedIn: {post['title'][:60]}")
                result = publish_to_linkedin(post)

                if result:
                    answer_callback(cb_id, "✅ Posted to LinkedIn!")
                    if message_id:
                        edit_message_reply_markup(TELEGRAM_CHAT_ID, message_id)
                    del pending[post_id]
                    save_pending(pending)
                    processed += 1
                else:
                    answer_callback(cb_id, "❌ LinkedIn failed, try again")
            else:
                answer_callback(cb_id, "⚠️ Already processed")

        elif data.startswith("skip:"):
            post_id = data.split(":", 1)[1]
            if post_id in pending:
                del pending[post_id]
                save_pending(pending)
                processed += 1
            if message_id:
                edit_message_reply_markup(TELEGRAM_CHAT_ID, message_id)
            answer_callback(cb_id, "⏭️ Skipped")

    # Підтверджуємо обробку апдейтів
    if last_update_id:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1},
            timeout=5,
        )

    print(f"✅ Processed {processed} callbacks.")

if __name__ == "__main__":
    main()
