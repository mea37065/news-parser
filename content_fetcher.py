from __future__ import annotations

import logging
import re
from html import unescape

import requests

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_article_text(
    url: str,
    *,
    timeout_seconds: int,
    char_limit: int,
) -> str:
    try:
        response = requests.get(
            url,
            timeout=timeout_seconds,
            headers={"User-Agent": "news-parser/1.0"},
        )
        response.raise_for_status()
    except Exception as error:
        logger.warning("Article fetch failed for %s: %s", url, error)
        return ""

    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type.lower():
        return ""

    html = response.text
    html = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>",
        " ",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    article_match = re.search(
        r"<article\b[^>]*>(.*?)</article>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    source_html = article_match.group(1) if article_match else html
    paragraphs = re.findall(
        r"<p\b[^>]*>(.*?)</p>",
        source_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    cleaned = [
        _strip_html(paragraph)
        for paragraph in paragraphs
    ]
    cleaned = [paragraph for paragraph in cleaned if len(paragraph) >= 40]

    if not cleaned and source_html is not html:
        paragraphs = re.findall(
            r"<p\b[^>]*>(.*?)</p>",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        cleaned = [_strip_html(paragraph) for paragraph in paragraphs]
        cleaned = [paragraph for paragraph in cleaned if len(paragraph) >= 40]

    article_text = "\n\n".join(cleaned)
    return article_text[:char_limit].strip()
