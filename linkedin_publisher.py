from __future__ import annotations

import logging
import re
from typing import Any

import requests

from app_config import Settings, load_settings
from logging_config import configure_logging

logger = logging.getLogger(__name__)

LINKEDIN_API = "https://api.linkedin.com/v2"
LINKEDIN_MAX_TEXT_LENGTH = 3000


def _auth_headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.linkedin_access_token}"}


def get_linkedin_urn(settings: Settings) -> str | None:
    try:
        response = requests.get(
            f"{LINKEDIN_API}/userinfo",
            headers=_auth_headers(settings),
            timeout=10,
        )
        response.raise_for_status()
    except Exception as error:
        logger.error("LinkedIn auth error: %s", error)
        return None

    subject = response.json().get("sub")
    if not subject:
        return None
    return f"urn:li:person:{subject}" if not subject.startswith("urn") else subject


def check_linkedin_connection(settings: Settings) -> bool:
    try:
        response = requests.get(
            f"{LINKEDIN_API}/userinfo",
            headers=_auth_headers(settings),
            timeout=10,
        )
        response.raise_for_status()
    except Exception as error:
        logger.error("LinkedIn connection error: %s", error)
        return False

    data = response.json()
    logger.info(
        "Connected to LinkedIn as: %s (%s)",
        data.get("name"),
        data.get("email"),
    )
    return True


def build_linkedin_text(post: dict[str, Any]) -> str:
    body = str(post.get("body") or "").strip()
    hashtag_line = " ".join(f"#{tag.replace(' ', '')}" for tag in post.get("tags", []))
    if hashtag_line and not re.search(r"#\w+", body):
        body = f"{body}\n\n{hashtag_line}".strip()

    text = body
    if len(text) <= LINKEDIN_MAX_TEXT_LENGTH:
        return text

    lines = [line for line in body.splitlines() if line.strip()]
    trailing_hashtags = lines[-1] if lines and re.search(r"#\w+", lines[-1]) else ""
    prose_lines = lines[:-1] if trailing_hashtags else lines
    prose = "\n".join(prose_lines).strip()
    reserve = len(trailing_hashtags) + 2 if trailing_hashtags else 0
    safe_prose_limit = max(LINKEDIN_MAX_TEXT_LENGTH - reserve, 0)
    trimmed_prose = prose[:safe_prose_limit].rstrip()
    if trailing_hashtags:
        combined = f"{trimmed_prose}\n\n{trailing_hashtags}".strip()
        return combined[:LINKEDIN_MAX_TEXT_LENGTH]
    return trimmed_prose[:LINKEDIN_MAX_TEXT_LENGTH]


def publish_to_linkedin(
    settings: Settings,
    post: dict[str, Any],
) -> dict[str, Any] | None:
    urn = get_linkedin_urn(settings)
    if not urn:
        return None

    share_content: dict[str, Any] = {
        "shareCommentary": {"text": build_linkedin_text(post)},
        "shareMediaCategory": "NONE",
    }
    source_url = str(post.get("source_url") or "").strip()
    if source_url:
        share_content = {
            "shareCommentary": {"text": build_linkedin_text(post)},
            "shareMediaCategory": "ARTICLE",
            "media": [
                {
                    "status": "READY",
                    "originalUrl": source_url,
                    "title": {"text": str(post.get("title") or "").strip()},
                    "description": {
                        "text": str(
                            post.get("description") or post.get("body") or ""
                        ).strip()[:220]
                    },
                }
            ],
        }

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": share_content
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
        },
    }

    try:
        response = requests.post(
            f"{LINKEDIN_API}/ugcPosts",
            headers={
                **_auth_headers(settings),
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        logger.info("Posted to LinkedIn. Post ID: %s", data.get("id", "n/a"))
        return data
    except Exception as error:
        logger.error("LinkedIn publish error: %s", error)
        if hasattr(error, "response") and error.response is not None:
            logger.error("LinkedIn details: %s", error.response.text)
        return None


if __name__ == "__main__":
    configure_logging()
    current_settings = load_settings()
    if check_linkedin_connection(current_settings):
        publish_to_linkedin(
            current_settings,
            {
                "title": "Test Post from News AI Parser",
                "body": "This is a test post generated automatically.",
                "tags": ["cybersecurity", "devops", "automation"],
                "source_url": "https://example.com",
            },
        )
