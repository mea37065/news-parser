from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from credentials import load_credentials

load_credentials()

from linkedin_publisher import check_linkedin_connection, publish_to_linkedin
from parser import escape_html, load_pending, run_parse_cycle, save_pending

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

POLL_INTERVAL_SECONDS = 3
SCHEDULE_TIMEZONE = ZoneInfo("Europe/Bratislava")
SCHEDULE_LABEL = "Europe/Bratislava (CET/CEST)"
DAILY_RUN_HOUR = 8
DAILY_RUN_MINUTE = 0

OFFSET_FILE = Path(__file__).parent / "tg_offset.txt"
SCHEDULE_STATE_FILE = Path(__file__).parent / "schedule_state.json"


def load_offset() -> int:
    if OFFSET_FILE.exists():
        try:
            return int(OFFSET_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
    return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset), encoding="utf-8")


def load_schedule_state() -> dict[str, str]:
    if not SCHEDULE_STATE_FILE.exists():
        return {}

    try:
        return json.loads(SCHEDULE_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_schedule_state(*, last_run_at: datetime) -> None:
    payload = {
        "last_run_date": last_run_at.date().isoformat(),
        "last_run_at": last_run_at.isoformat(),
    }
    SCHEDULE_STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def tg_post(method: str, **kwargs) -> dict:
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
            json=kwargs,
            timeout=10,
        )
        return response.json()
    except Exception as error:
        print(f"Telegram {method} error: {error}")
        return {}


def answer_callback(callback_id: str, text: str) -> None:
    tg_post("answerCallbackQuery", callback_query_id=callback_id, text=text)


def remove_buttons(chat_id: str, message_id: int) -> None:
    tg_post(
        "editMessageReplyMarkup",
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=json.dumps({"inline_keyboard": []}),
    )


def send_linkedin_preview(post_id: str, post: dict) -> None:
    linkedin_body = post.get("linkedin_body", post.get("body", ""))[:1000]
    text = (
        "<b>LinkedIn Preview</b>\n"
        "----------------------\n"
        f"{escape_html(linkedin_body)}\n"
        "----------------------\n"
        f"{escape_html(post.get('source_url', ''))}"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "Publish to LinkedIn",
                    "callback_data": f"linkedin_confirm:{post_id}",
                },
                {
                    "text": "Cancel",
                    "callback_data": f"linkedin_cancel:{post_id}",
                },
            ]
        ]
    }
    tg_post(
        "sendMessage",
        chat_id=TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=json.dumps(keyboard),
    )


def handle_callbacks() -> None:
    offset = load_offset()
    pending = load_pending()

    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={
                "offset": offset,
                "timeout": 2,
                "allowed_updates": ["callback_query"],
            },
            timeout=10,
        )
        updates = response.json().get("result", [])
    except Exception as error:
        print(f"getUpdates error: {error}")
        return

    for update in updates:
        save_offset(update["update_id"] + 1)

        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        callback_id = callback["id"]
        message_id = callback.get("message", {}).get("message_id")
        chat_id = callback.get("message", {}).get("chat", {}).get("id", TELEGRAM_CHAT_ID)

        if data.startswith("linkedin:"):
            post_id = data.split(":", 1)[1]
            post = pending.get(post_id)
            if post:
                answer_callback(callback_id, "Check the LinkedIn preview below.")
                if message_id:
                    remove_buttons(chat_id, message_id)
                send_linkedin_preview(post_id, post)
            else:
                answer_callback(callback_id, "Already processed.")

        elif data.startswith("linkedin_confirm:"):
            post_id = data.split(":", 1)[1]
            post = pending.get(post_id)
            if post:
                print(f"LinkedIn publish: {post['title'][:80]}")
                linkedin_post = {**post, "body": post.get("linkedin_body", post["body"])}
                result = publish_to_linkedin(linkedin_post)
                if result:
                    answer_callback(callback_id, "Published to LinkedIn.")
                    if message_id:
                        remove_buttons(chat_id, message_id)
                    del pending[post_id]
                    save_pending(pending)
                else:
                    answer_callback(callback_id, "LinkedIn publish failed, try again.")
            else:
                answer_callback(callback_id, "Already processed.")

        elif data.startswith("linkedin_cancel:"):
            if message_id:
                remove_buttons(chat_id, message_id)
            answer_callback(callback_id, "Cancelled.")

        elif data.startswith("skip:"):
            post_id = data.split(":", 1)[1]
            if post_id in pending:
                del pending[post_id]
                save_pending(pending)
            if message_id:
                remove_buttons(chat_id, message_id)
            answer_callback(callback_id, "Skipped.")


def get_scheduled_time(reference: datetime) -> datetime:
    return reference.replace(
        hour=DAILY_RUN_HOUR,
        minute=DAILY_RUN_MINUTE,
        second=0,
        microsecond=0,
    )


def scheduler_thread() -> None:
    state = load_schedule_state()
    last_run_date = state.get("last_run_date")
    last_announced_next_run: str | None = None

    while True:
        now_local = datetime.now(SCHEDULE_TIMEZONE)
        today_run = get_scheduled_time(now_local)
        today_key = now_local.date().isoformat()

        if now_local >= today_run and last_run_date != today_key:
            print(
                f"\nScheduled parse started at "
                f"{now_local.strftime('%d.%m.%Y %H:%M:%S %Z')}\n"
            )
            try:
                run_parse_cycle()
                save_schedule_state(last_run_at=now_local)
                last_run_date = today_key
            except Exception as error:
                print(f"Parse error: {error}")
            last_announced_next_run = None
            time.sleep(5)
            continue

        next_run = today_run if now_local < today_run else today_run + timedelta(days=1)
        next_run_key = next_run.isoformat()
        if last_announced_next_run != next_run_key:
            print(
                "Next parse scheduled for "
                f"{next_run.strftime('%d.%m.%Y %H:%M:%S %Z')} "
                f"({SCHEDULE_LABEL})"
            )
            last_announced_next_run = next_run_key

        seconds_until_next_run = max(5, int((next_run - now_local).total_seconds()))
        time.sleep(min(60, seconds_until_next_run))


def main() -> None:
    print("=" * 60)
    print("News AI Parser Bot starting")
    print(
        f"Daily parse schedule: {DAILY_RUN_HOUR:02d}:{DAILY_RUN_MINUTE:02d} "
        f"{SCHEDULE_LABEL}"
    )
    print(f"Telegram poll interval: {POLL_INTERVAL_SECONDS} seconds")
    print("=" * 60)

    print("\nChecking connections...")
    check_linkedin_connection()
    print()

    scheduler = threading.Thread(target=scheduler_thread, daemon=True)
    scheduler.start()

    print("Listening for Telegram callbacks...\n")
    while True:
        try:
            handle_callbacks()
        except Exception as error:
            print(f"Main loop error: {error}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
