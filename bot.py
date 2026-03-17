"""
bot.py — Фоновий Telegram бот.
Запускається на вашому ПК і працює безперервно.

Що робить:
  • Кожні 6 годин запускає парсер і надсилає нові статті в Telegram
  • Постійно слухає натискання кнопок (Dev.to / LinkedIn / Skip)
  • Для LinkedIn — показує превью поста і просить підтвердження
"""
import time
import threading
import json
import os
import requests
from pathlib import Path
from datetime import datetime

# Завантажуємо .env якщо є
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from devto_publisher import publish_to_devto, check_devto_connection
from linkedin_publisher import publish_to_linkedin, check_linkedin_connection
from parser import run_parse_cycle, load_pending, save_pending, escape_html

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

POLL_INTERVAL    = 3      # секунди між перевірками Telegram
PARSE_INTERVAL   = 6      # години між запусками парсера
OFFSET_FILE      = Path(__file__).parent / "tg_offset.txt"

# ─────────────────────────────────────────
#  OFFSET (щоб не обробляти старі апдейти)
# ─────────────────────────────────────────
def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text().strip())
        except Exception:
            pass
    return 0

def save_offset(offset: int):
    OFFSET_FILE.write_text(str(offset))

# ─────────────────────────────────────────
#  TELEGRAM HELPERS
# ─────────────────────────────────────────
def tg_post(method: str, **kwargs):
    try:
        return requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
            json=kwargs,
            timeout=10,
        ).json()
    except Exception as e:
        print(f"❌ Telegram {method} error: {e}")
        return {}

def answer_callback(cb_id: str, text: str):
    tg_post("answerCallbackQuery", callback_query_id=cb_id, text=text)

def remove_buttons(chat_id: str, message_id: int):
    tg_post("editMessageReplyMarkup",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=json.dumps({"inline_keyboard": []}))

def send_linkedin_preview(post_id: str, post: dict):
    """Надсилає превью LinkedIn поста з кнопками підтвердження."""
    linkedin_body = post.get("linkedin_body", post.get("body", ""))[:1000]
    text = (
        f"🔵 <b>LinkedIn Preview</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{escape_html(linkedin_body)}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 {post.get('source_url', '')}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Опублікувати",  "callback_data": f"linkedin_confirm:{post_id}"},
            {"text": "✏️ Пропустити",   "callback_data": f"linkedin_cancel:{post_id}"},
        ]]
    }
    tg_post("sendMessage",
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=json.dumps(keyboard))

# ─────────────────────────────────────────
#  CALLBACK HANDLER
# ─────────────────────────────────────────
def handle_callbacks():
    offset  = load_offset()
    pending = load_pending()

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={
                "offset":          offset,
                "timeout":         2,
                "allowed_updates": ["callback_query"],
            },
            timeout=10,
        )
        updates = resp.json().get("result", [])
    except Exception as e:
        print(f"❌ getUpdates error: {e}")
        return

    for update in updates:
        new_offset = update["update_id"] + 1
        save_offset(new_offset)

        cb = update.get("callback_query")
        if not cb:
            continue

        data       = cb.get("data", "")
        cb_id      = cb["id"]
        message_id = cb.get("message", {}).get("message_id")
        chat_id    = cb.get("message", {}).get("chat", {}).get("id", TELEGRAM_CHAT_ID)

        # ── Dev.to ─────────────────────────────
        if data.startswith("publish:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)
            if post:
                print(f"📤 Dev.to: {post['title'][:60]}")
                result = publish_to_devto(post, published=False)
                if result:
                    answer_callback(cb_id, "✅ Збережено як чернетка на Dev.to!")
                    remove_buttons(chat_id, message_id)
                    del pending[post_id]
                    save_pending(pending)
                else:
                    answer_callback(cb_id, "❌ Помилка публікації, спробуй ще")
            else:
                answer_callback(cb_id, "⚠️ Вже оброблено")

        # ── LinkedIn — крок 1: показати превью ─
        elif data.startswith("linkedin:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)
            if post:
                answer_callback(cb_id, "👀 Перевір превью нижче")
                remove_buttons(chat_id, message_id)
                send_linkedin_preview(post_id, post)
            else:
                answer_callback(cb_id, "⚠️ Вже оброблено")

        # ── LinkedIn — крок 2: підтвердження ───
        elif data.startswith("linkedin_confirm:"):
            post_id = data.split(":", 1)[1]
            post    = pending.get(post_id)
            if post:
                print(f"🔵 LinkedIn: {post['title'][:60]}")
                # Публікуємо linkedin_body, не devto body
                linkedin_post = {**post, "body": post.get("linkedin_body", post["body"])}
                result = publish_to_linkedin(linkedin_post)
                if result:
                    answer_callback(cb_id, "✅ Опубліковано в LinkedIn!")
                    remove_buttons(chat_id, message_id)
                    del pending[post_id]
                    save_pending(pending)
                else:
                    answer_callback(cb_id, "❌ Помилка LinkedIn, спробуй ще")
            else:
                answer_callback(cb_id, "⚠️ Вже оброблено")

        # ── LinkedIn — скасування превью ────────
        elif data.startswith("linkedin_cancel:"):
            remove_buttons(chat_id, message_id)
            answer_callback(cb_id, "↩️ Скасовано")

        # ── Skip ────────────────────────────────
        elif data.startswith("skip:"):
            post_id = data.split(":", 1)[1]
            if post_id in pending:
                del pending[post_id]
                save_pending(pending)
            remove_buttons(chat_id, message_id)
            answer_callback(cb_id, "⏭️ Пропущено")

# ─────────────────────────────────────────
#  SCHEDULER THREAD
# ─────────────────────────────────────────
_last_parse = 0.0

def scheduler_thread():
    global _last_parse
    # Перший запуск одразу при старті
    print(f"\n📡 Running initial parse...\n")
    try:
        run_parse_cycle()
    except Exception as e:
        print(f"❌ Parse error: {e}")
    _last_parse = time.time()

    while True:
        time.sleep(60)
        elapsed_hours = (time.time() - _last_parse) / 3600
        if elapsed_hours >= PARSE_INTERVAL:
            print(f"\n⏰ {PARSE_INTERVAL}h passed — running parse cycle...\n")
            try:
                run_parse_cycle()
            except Exception as e:
                print(f"❌ Parse error: {e}")
            _last_parse = time.time()

# ─────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────
def main():
    print("=" * 50)
    print("🤖 News AI Parser Bot starting...")
    print(f"   Parse interval: every {PARSE_INTERVAL} hours")
    print(f"   Poll interval:  every {POLL_INTERVAL} seconds")
    print("=" * 50)

    # Перевірка підключень
    print("\n🔍 Checking connections...")
    check_devto_connection()
    check_linkedin_connection()
    print()

    # Запускаємо планувальник у фоновому потоці
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

    # Основний цикл — слухаємо Telegram
    print("👂 Listening for Telegram callbacks...\n")
    while True:
        try:
            handle_callbacks()
        except Exception as e:
            print(f"❌ Main loop error: {e}")
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()