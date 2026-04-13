from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests

from app_config import Settings

logger = logging.getLogger(__name__)

STORY_ASSETS_SYSTEM_PROMPT = """
You rewrite news items into concise, factual text assets.

Preserve the original meaning of the news. Use only the facts provided in the input.
Do not speculate, exaggerate, add unsupported context,
or turn the text into advice or marketing.
Return valid JSON only.
""".strip()

DAILY_SUMMARY_SYSTEM_PROMPT = """
You write a concise daily digest for a set of tech and cybersecurity news items.

Summarize the main themes that appeared across the provided stories
and stay grounded in the supplied facts and metrics.
Do not invent trends, causes, or implications that are not supported by the input.
Do not use emojis or hype.
""".strip()

FOLLOW_UP_ANSWER_SYSTEM_PROMPT = """
You answer follow-up questions about a specific news item.

Use only the supplied article facts, recap text, and summary.
If the answer is not supported by the provided material, say so clearly.
Do not speculate or add outside information.
Do not use emojis.
""".strip()


def _article_context(article: dict[str, Any]) -> str:
    article_text = article.get("article_text", "").strip()
    return (
        f"Title: {article['title']}\n"
        f"Summary: {article['summary']}\n"
        f"Article text: {article_text or 'Not available'}\n"
        f"Source: {article['source']}\n"
        f"Date: {article.get('date', '')}\n"
        f"Tags: {', '.join(article.get('tags', []))}\n"
        f"Link: {article['url']}"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _call_groq(
    settings: Settings,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str | None:
    if not settings.groq_api_key:
        return None

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(1, settings.groq_max_retries + 1):
        time.sleep(settings.groq_request_delay_seconds)
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=settings.groq_request_timeout_seconds,
            )

            if response.status_code == 429:
                wait_seconds = 15 * attempt
                logger.warning(
                    "Rate limit from Groq, waiting %ss (attempt %s/%s)",
                    wait_seconds,
                    attempt,
                    settings.groq_max_retries,
                )
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as error:
            logger.warning(
                "Groq error on attempt %s/%s: %s",
                attempt,
                settings.groq_max_retries,
                error,
            )
            if attempt < settings.groq_max_retries:
                time.sleep(10)

    return None


def generate_story_assets(
    settings: Settings,
    article: dict[str, Any],
) -> dict[str, str] | None:
    prompt = (
        "Create two text assets for this news item and return JSON with keys "
        '"recap" and "linkedin_post".\n\n'
        "Rules for recap:\n"
        "- Language: English\n"
        "- Length: 90-140 words\n"
        "- Keep the original facts, scope, and tone intact\n"
        "- Focus on what happened and the key takeaway from the supplied text\n"
        "- Do not add opinions, speculation, extra background, "
        "recommendations, or clickbait\n"
        "- Do not use bullets, hashtags, markdown, or emojis\n"
        "- Use 1-2 short paragraphs\n\n"
        "Rules for linkedin_post:\n"
        "- Language: English\n"
        "- Length: 35-60 words total before hashtags\n"
        "- Start with the key fact from the story\n"
        "- Keep it factual and conversational\n"
        "- Do not include the article title as a heading or first standalone line\n"
        "- No emojis, bullets, or markdown\n"
        "- No hashtags in the body text\n"
        "- End with exactly 2-3 relevant hashtags on the last line only\n"
        "- Do not repeat the source URL in the post\n\n"
        f"{_article_context(article)}"
    )
    response_text = _call_groq(
        settings,
        system_prompt=STORY_ASSETS_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=420,
        temperature=0.25,
    )
    if not response_text:
        return None

    payload = _extract_json_object(response_text)
    if not payload:
        logger.warning("Groq returned invalid JSON for article: %s", article["title"])
        return None

    recap = str(payload.get("recap", "")).strip()
    linkedin_post = str(payload.get("linkedin_post", "")).strip()
    if not recap or not linkedin_post:
        return None

    return {
        "recap": recap,
        "linkedin_post": linkedin_post,
    }


def generate_daily_summary(
    settings: Settings,
    articles: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str | None:
    if not settings.groq_api_key:
        return None

    article_lines = []
    for index, article in enumerate(articles, start=1):
        article_lines.append(
            f"{index}. {article['title']} | Source: {article['source']} | "
            f"Summary: {article['summary']} | Recap: {article.get('recap', '')}"
        )

    prompt = (
        "Create a daily briefing for today's collected news.\n\n"
        "Rules:\n"
        "- Language: English\n"
        "- Length: 260-420 words\n"
        "- Write it for the reader who wants to understand the full batch "
        "without opening every article\n"
        "- Cover the main themes and briefly mention each important story "
        "at least once\n"
        "- Keep it neutral, crisp, and information-dense\n"
        "- Do not mention that an AI wrote it\n"
        "- Do not use bullets, markdown, emojis, or hashtags\n"
        "- Prefer 3-5 short paragraphs\n"
        "- Use the supplied metrics naturally when relevant, "
        "but do not turn the answer into a metric list\n\n"
        f"Metrics: {metrics}\n\n"
        "Articles:\n"
        f"{chr(10).join(article_lines)}\n\n"
        "Return JSON with a single key named summary."
    )
    response_text = _call_groq(
        settings,
        system_prompt=DAILY_SUMMARY_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=650,
        temperature=0.3,
    )
    if not response_text:
        return None

    payload = _extract_json_object(response_text)
    if not payload:
        return None

    summary = str(payload.get("summary", "")).strip()
    return summary or None


def generate_article_answer(
    settings: Settings,
    article: dict[str, Any],
    question: str,
) -> str | None:
    if not settings.groq_api_key:
        return None

    prompt = (
        "Answer the user's follow-up question about this news item.\n\n"
        "Rules:\n"
        "- Answer in the same language as the user's question when possible\n"
        "- Length: 50-120 words\n"
        "- Stay strictly grounded in the supplied article details\n"
        "- If the supplied material does not answer the question, say that clearly\n"
        "- Do not add outside facts or speculation\n"
        "- Do not use bullets, markdown, or emojis\n\n"
        f"Question: {question}\n\n"
        f"{_article_context(article)}\n"
        f"Recap: {article.get('recap', '')}\n"
        f"LinkedIn draft: {article.get('linkedin_body', '')}\n\n"
        'Return JSON with a single key named "answer".'
    )
    response_text = _call_groq(
        settings,
        system_prompt=FOLLOW_UP_ANSWER_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=220,
        temperature=0.2,
    )
    if not response_text:
        return None

    payload = _extract_json_object(response_text)
    if not payload:
        return None

    answer = str(payload.get("answer", "")).strip()
    return answer or None
