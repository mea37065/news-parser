from __future__ import annotations

import logging
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
    parts = [
        post["title"].strip(),
        post["body"].strip(),
        post.get("source_url", "").strip(),
        " ".join(f"#{tag.replace(' ', '')}" for tag in post.get("tags", [])),
    ]
    text = "\n\n".join(part for part in parts if part).strip()
    if len(text) <= LINKEDIN_MAX_TEXT_LENGTH:
        return text

    overflow = len(text) - LINKEDIN_MAX_TEXT_LENGTH
    body = post["body"].strip()
    safe_body = body[:-overflow].rstrip() if overflow < len(body) else ""
    parts[1] = safe_body
    text = "\n\n".join(part for part in parts if part).strip()
    return text[:LINKEDIN_MAX_TEXT_LENGTH]


def publish_to_linkedin(
    settings: Settings,
    post: dict[str, Any],
) -> dict[str, Any] | None:
    urn = get_linkedin_urn(settings)
    if not urn:
        return None

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": build_linkedin_text(post)},
                "shareMediaCategory": "NONE",
            }
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
