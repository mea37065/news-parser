from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from app_config import Settings, load_settings
from linkedin_publisher import check_linkedin_connection, publish_to_linkedin
from logging_config import configure_logging
from parser import escape_html, run_parse_cycle, send_to_telegram_with_buttons
from storage import (
    ARTICLE_STATUS_QUEUED,
    ARTICLE_STATUS_REVIEWING,
    Storage,
)
from telegram_client import TelegramClient

logger = logging.getLogger(__name__)

TELEGRAM_OFFSET_KEY = "telegram_offset"
LAST_RUN_DATE_KEY = "last_run_date"
LAST_RUN_AT_KEY = "last_run_at"


def send_linkedin_preview(
    telegram: TelegramClient,
    post_id: str,
    post: dict[str, object],
) -> None:
    linkedin_body = str(post.get("linkedin_body") or post.get("recap") or "")[:1000]
    text = (
        "<b>LinkedIn Preview</b>\n"
        "----------------------\n"
        f"{escape_html(linkedin_body)}\n"
        "----------------------\n"
        f"{escape_html(str(post.get('url', '')))}"
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
    telegram.send_message(
        text=text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


def handle_callbacks(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient,
) -> None:
    offset = int(storage.get_state(TELEGRAM_OFFSET_KEY, "0") or "0")
    updates = telegram.get_updates(offset=offset, allowed_updates=["callback_query"])

    for update in updates:
        storage.set_state(TELEGRAM_OFFSET_KEY, str(update["update_id"] + 1))
        callback = update.get("callback_query")
        if not callback:
            continue

        data = callback.get("data", "")
        callback_id = callback["id"]
        message_id = callback.get("message", {}).get("message_id")
        chat_id = str(
            callback.get("message", {})
            .get("chat", {})
            .get("id", settings.telegram_chat_id)
        )

        if data.startswith("linkedin:"):
            post_id = data.split(":", 1)[1]
            post = storage.get_article(post_id)
            if post and post["status"] in {
                ARTICLE_STATUS_QUEUED,
                ARTICLE_STATUS_REVIEWING,
            }:
                storage.set_reviewing(post_id)
                telegram.answer_callback(
                    callback_id,
                    "Check the LinkedIn preview below.",
                )
                if message_id:
                    telegram.remove_buttons(chat_id=chat_id, message_id=message_id)
                send_linkedin_preview(telegram, post_id, post)
            else:
                telegram.answer_callback(callback_id, "Already processed.")

        elif data.startswith("linkedin_confirm:"):
            post_id = data.split(":", 1)[1]
            post = storage.get_article(post_id)
            if post and post["status"] in {
                ARTICLE_STATUS_QUEUED,
                ARTICLE_STATUS_REVIEWING,
            }:
                logger.info("LinkedIn publish: %s", post["title"][:80])
                result = publish_to_linkedin(
                    settings,
                    {
                        "title": post["title"],
                        "body": post.get("linkedin_body") or post.get("recap") or "",
                        "tags": post["tags"],
                        "source_url": post["url"],
                    },
                )
                if result:
                    telegram.answer_callback(callback_id, "Published to LinkedIn.")
                    if message_id:
                        telegram.remove_buttons(chat_id=chat_id, message_id=message_id)
                    storage.mark_published(
                        post_id,
                        linkedin_post_id=str(result.get("id", "")),
                    )
                else:
                    telegram.answer_callback(
                        callback_id,
                        "LinkedIn publish failed, try again.",
                    )
            else:
                telegram.answer_callback(callback_id, "Already processed.")

        elif data.startswith("linkedin_cancel:"):
            post_id = data.split(":", 1)[1]
            post = storage.get_article(post_id)
            if post and post["status"] == ARTICLE_STATUS_REVIEWING:
                new_message_id = send_to_telegram_with_buttons(
                    telegram,
                    post,
                    post_id=post_id,
                    preview_text=str(
                        post.get("recap") or post.get("linkedin_body") or ""
                    ),
                )
                if new_message_id is not None:
                    storage.queue_article(
                        post_id,
                        recap=str(post.get("recap") or ""),
                        linkedin_body=str(post.get("linkedin_body") or ""),
                        telegram_message_id=new_message_id,
                    )
                else:
                    storage.restore_queued(post_id)
            if message_id:
                telegram.remove_buttons(chat_id=chat_id, message_id=message_id)
            telegram.answer_callback(callback_id, "Cancelled.")

        elif data.startswith("skip:"):
            post_id = data.split(":", 1)[1]
            if storage.get_article(post_id):
                storage.mark_skipped(post_id)
            if message_id:
                telegram.remove_buttons(chat_id=chat_id, message_id=message_id)
            telegram.answer_callback(callback_id, "Skipped.")


def get_scheduled_time(settings: Settings, reference: datetime) -> datetime:
    return reference.replace(
        hour=settings.daily_run_hour,
        minute=settings.daily_run_minute,
        second=0,
        microsecond=0,
    )


def run_scheduler_tick(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient,
) -> str | None:
    last_run_date = storage.get_state(LAST_RUN_DATE_KEY)
    now_local = datetime.now(settings.schedule_timezone)
    today_run = get_scheduled_time(settings, now_local)
    today_key = now_local.date().isoformat()

    if now_local >= today_run and last_run_date != today_key:
        logger.info(
            "Scheduled parse started at %s",
            now_local.strftime("%d.%m.%Y %H:%M:%S %Z"),
        )
        try:
            run_parse_cycle(settings, storage, telegram)
            storage.set_state(LAST_RUN_DATE_KEY, today_key)
            storage.set_state(LAST_RUN_AT_KEY, now_local.isoformat())
        except Exception as error:
            logger.exception("Parse error: %s", error)
        return None

    next_run = today_run if now_local < today_run else today_run + timedelta(days=1)
    return next_run.isoformat()


def main() -> None:
    configure_logging()
    settings = load_settings()
    storage = Storage(settings.storage_path)
    telegram = TelegramClient(settings)

    logger.info("News AI Parser Bot starting")
    logger.info(
        "Daily parse schedule: %02d:%02d %s",
        settings.daily_run_hour,
        settings.daily_run_minute,
        settings.schedule_timezone_name,
    )
    logger.info("Telegram poll interval: %s seconds", settings.poll_interval_seconds)

    check_linkedin_connection(settings)

    last_announced_next_run: str | None = None
    while True:
        try:
            next_run_key = run_scheduler_tick(settings, storage, telegram)
            if next_run_key is None:
                last_announced_next_run = None
            if next_run_key and next_run_key != last_announced_next_run:
                next_run = datetime.fromisoformat(next_run_key)
                logger.info(
                    "Next parse scheduled for %s (%s)",
                    next_run.strftime("%d.%m.%Y %H:%M:%S %Z"),
                    settings.schedule_timezone_name,
                )
                last_announced_next_run = next_run_key
            handle_callbacks(settings, storage, telegram)
        except Exception as error:
            logger.exception("Main loop error: %s", error)
        time.sleep(settings.poll_interval_seconds)


if __name__ == "__main__":
    main()
