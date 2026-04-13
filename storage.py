from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTICLE_STATUS_DISCOVERED = "discovered"
ARTICLE_STATUS_DELIVERY_FAILED = "delivery_failed"
ARTICLE_STATUS_QUEUED = "queued"
ARTICLE_STATUS_REVIEWING = "reviewing"
ARTICLE_STATUS_PUBLISHED = "published"
ARTICLE_STATUS_SKIPPED = "skipped"

REPROCESSABLE_STATUSES = (
    ARTICLE_STATUS_DISCOVERED,
    ARTICLE_STATUS_DELIVERY_FAILED,
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Storage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    article_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    source TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    article_text TEXT NOT NULL DEFAULT '',
                    published_date TEXT NOT NULL DEFAULT '',
                    recap TEXT NOT NULL DEFAULT '',
                    linkedin_body TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    linkedin_post_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_articles_status
                ON articles(status);

                CREATE INDEX IF NOT EXISTS idx_articles_fingerprint
                ON articles(fingerprint);

                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

    def _row_to_article(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["article_id"],
            "fingerprint": row["fingerprint"],
            "source": row["source"],
            "tags": json.loads(row["tags_json"]),
            "title": row["title"],
            "url": row["url"],
            "summary": row["summary"],
            "article_text": row["article_text"],
            "date": row["published_date"],
            "recap": row["recap"],
            "linkedin_body": row["linkedin_body"],
            "status": row["status"],
            "telegram_message_id": row["telegram_message_id"],
            "linkedin_post_id": row["linkedin_post_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def article_exists(self, *, article_id: str, fingerprint: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT article_id
                FROM articles
                WHERE article_id = ? OR fingerprint = ?
                LIMIT 1
                """,
                (article_id, fingerprint),
            ).fetchone()
        return row is not None

    def add_discovered_article(self, article: dict[str, Any]) -> bool:
        if self.article_exists(
            article_id=article["id"],
            fingerprint=article["fingerprint"],
        ):
            return False

        timestamp = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO articles (
                    article_id,
                    fingerprint,
                    source,
                    tags_json,
                    title,
                    url,
                    summary,
                    article_text,
                    published_date,
                    recap,
                    linkedin_body,
                    status,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?, ?)
                """,
                (
                    article["id"],
                    article["fingerprint"],
                    article["source"],
                    json.dumps(article["tags"], ensure_ascii=False),
                    article["title"],
                    article["url"],
                    article["summary"],
                    article.get("article_text", ""),
                    article.get("date", ""),
                    ARTICLE_STATUS_DISCOVERED,
                    timestamp,
                    timestamp,
                ),
            )
        return True

    def get_articles_for_processing(self) -> list[dict[str, Any]]:
        placeholders = ", ".join("?" for _ in REPROCESSABLE_STATUSES)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM articles
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                REPROCESSABLE_STATUSES,
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def get_article(self, article_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE article_id = ?",
                (article_id,),
            ).fetchone()
        return self._row_to_article(row) if row else None

    def get_article_by_telegram_message_id(
        self,
        telegram_message_id: int,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM articles WHERE telegram_message_id = ?",
                (telegram_message_id,),
            ).fetchone()
        return self._row_to_article(row) if row else None

    def mark_delivery_failed(
        self,
        article_id: str,
        *,
        recap: str,
        linkedin_body: str,
    ) -> None:
        self._update_article(
            article_id,
            status=ARTICLE_STATUS_DELIVERY_FAILED,
            recap=recap,
            linkedin_body=linkedin_body,
        )

    def queue_article(
        self,
        article_id: str,
        *,
        recap: str,
        linkedin_body: str,
        telegram_message_id: int | None,
    ) -> None:
        self._update_article(
            article_id,
            status=ARTICLE_STATUS_QUEUED,
            recap=recap,
            linkedin_body=linkedin_body,
            telegram_message_id=telegram_message_id,
        )

    def set_reviewing(self, article_id: str) -> None:
        self._update_article(article_id, status=ARTICLE_STATUS_REVIEWING)

    def restore_queued(self, article_id: str) -> None:
        self._update_article(article_id, status=ARTICLE_STATUS_QUEUED)

    def mark_published(self, article_id: str, *, linkedin_post_id: str = "") -> None:
        self._update_article(
            article_id,
            status=ARTICLE_STATUS_PUBLISHED,
            linkedin_post_id=linkedin_post_id,
        )

    def mark_skipped(self, article_id: str) -> None:
        self._update_article(article_id, status=ARTICLE_STATUS_SKIPPED)

    def _update_article(self, article_id: str, **changes: Any) -> None:
        if not changes:
            return

        changes["updated_at"] = _utc_now()
        assignments = ", ".join(f"{column} = ?" for column in changes)
        values = list(changes.values()) + [article_id]
        with self._connect() as connection:
            connection.execute(
                f"UPDATE articles SET {assignments} WHERE article_id = ?",
                values,
            )

    def get_state(self, key: str, default: str = "") -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def set_state(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO app_state(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def delete_state(self, key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM app_state WHERE key = ?",
                (key,),
            )
