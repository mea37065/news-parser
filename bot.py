from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from ai_generator import generate_article_answer, regenerate_linkedin_post
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
PENDING_QUESTION_KEY_PREFIX = "pending_question"


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
                    "text": "Regenerate",
                    "callback_data": f"linkedin_regenerate:{post_id}",
                }
            ],
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


def _pending_question_key(chat_id: str) -> str:
    return f"{PENDING_QUESTION_KEY_PREFIX}:{chat_id}"


def _set_pending_question(storage: Storage, chat_id: str, article_id: str) -> None:
    storage.set_state(_pending_question_key(chat_id), article_id)


def _clear_pending_question(storage: Storage, chat_id: str) -> None:
    storage.delete_state(_pending_question_key(chat_id))


def _get_pending_question_article(
    storage: Storage,
    chat_id: str,
) -> dict[str, object] | None:
    article_id = storage.get_state(_pending_question_key(chat_id))
    if not article_id:
        return None
    return storage.get_article(article_id)


def _build_fallback_answer(article: dict[str, object]) -> str:
    recap = str(article.get("recap") or article.get("summary") or "").strip()
    source = str(article.get("source") or "").strip()
    if recap:
        return (
            "I can only answer from the stored article details right now. "
            f"Here is the saved recap from {source}: {recap}"
        )
    return (
        "I do not have enough stored detail to answer that confidently. "
        "Try asking after the next parse cycle refreshes the article content."
    )


def _resolve_question_article(
    storage: Storage,
    chat_id: str,
    message: dict[str, object],
) -> dict[str, object] | None:
    reply_to = message.get("reply_to_message") if isinstance(message, dict) else None
    if isinstance(reply_to, dict):
        reply_message_id = reply_to.get("message_id")
        if isinstance(reply_message_id, int):
            article = storage.get_article_by_telegram_message_id(reply_message_id)
            if article:
                _set_pending_question(storage, chat_id, article["id"])
                return article

    return _get_pending_question_article(storage, chat_id)


def handle_message(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient,
    message: dict[str, object],
) -> None:
    chat_id = str(
        message.get("chat", {}).get("id", settings.telegram_chat_id)
        if isinstance(message.get("chat"), dict)
        else settings.telegram_chat_id
    )
    if chat_id != settings.telegram_chat_id:
        return

    text = str(message.get("text") or "").strip()
    if not text:
        return

    pending_article = _get_pending_question_article(storage, chat_id)
    if text.lower() in {"/done", "/stop", "/cancel"}:
        if pending_article:
            _clear_pending_question(storage, chat_id)
            telegram.send_message(
                chat_id=chat_id,
                text="Question mode closed for this story.",
                reply_to_message_id=message.get("message_id"),
            )
        return

    article = _resolve_question_article(storage, chat_id, message)
    if not article:
        return

    answer = generate_article_answer(settings, article, text)
    if not answer:
        answer = _build_fallback_answer(article)
    telegram.send_message(
        chat_id=chat_id,
        text=answer,
        reply_to_message_id=message.get("message_id"),
    )


def handle_callback(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient,
    callback: dict[str, object],
) -> None:
    data = str(callback.get("data", ""))
    callback_id = str(callback["id"])
    message = callback.get("message", {})
    message_id = message.get("message_id") if isinstance(message, dict) else None
    chat_id = str(
        message.get("chat", {}).get("id", settings.telegram_chat_id)
        if isinstance(message, dict) and isinstance(message.get("chat"), dict)
        else settings.telegram_chat_id
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
        return

    if data.startswith("linkedin_regenerate:"):
        post_id = data.split(":", 1)[1]
        post = storage.get_article(post_id)
        if post and post["status"] == ARTICLE_STATUS_REVIEWING:
            new_linkedin_body = regenerate_linkedin_post(settings, post)
            if not new_linkedin_body:
                telegram.answer_callback(
                    callback_id,
                    "Could not generate a new version.",
                )
                return

            storage.update_linkedin_body(post_id, new_linkedin_body)
            refreshed_post = storage.get_article(post_id) or {**post}
            refreshed_post["linkedin_body"] = new_linkedin_body
            telegram.answer_callback(callback_id, "Generated a new version.")
            if message_id:
                telegram.remove_buttons(chat_id=chat_id, message_id=message_id)
            send_linkedin_preview(telegram, post_id, refreshed_post)
        else:
            telegram.answer_callback(callback_id, "Review is no longer active.")
        return

    if data.startswith("linkedin_confirm:"):
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
                    "description": post.get("recap") or post.get("summary") or "",
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
        return

    if data.startswith("linkedin_cancel:"):
        post_id = data.split(":", 1)[1]
        post = storage.get_article(post_id)
        if post and post["status"] == ARTICLE_STATUS_REVIEWING:
            new_message_id = send_to_telegram_with_buttons(
                telegram,
                post,
                post_id=post_id,
                preview_text=str(post.get("recap") or post.get("linkedin_body") or ""),
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
        telegram.answer_callback(callback_id, "Cancelled. Review is available again.")
        return

    if data.startswith("ask:"):
        post_id = data.split(":", 1)[1]
        post = storage.get_article(post_id)
        if not post:
            telegram.answer_callback(callback_id, "This story is no longer available.")
            return

        _set_pending_question(storage, chat_id, post_id)
        telegram.answer_callback(callback_id, "Send your question in chat.")
        telegram.send_message(
            chat_id=chat_id,
            text=(
                f"Question mode is active for \"{post['title']}\".\n"
                "Send any follow-up question in this chat, or reply directly to the "
                "news message. Send /done when you want to stop."
            ),
            reply_to_message_id=message_id,
        )


def handle_callbacks(
    settings: Settings,
    storage: Storage,
    telegram: TelegramClient,
) -> None:
    offset = int(storage.get_state(TELEGRAM_OFFSET_KEY, "0") or "0")
    updates = telegram.get_updates(
        offset=offset,
        allowed_updates=["callback_query", "message"],
    )

    for update in updates:
        storage.set_state(TELEGRAM_OFFSET_KEY, str(update["update_id"] + 1))
        callback = update.get("callback_query")
        if callback:
            handle_callback(settings, storage, telegram, callback)
            continue

        message = update.get("message")
        if message:
            handle_message(settings, storage, telegram, message)


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
