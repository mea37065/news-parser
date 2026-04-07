from __future__ import annotations

import os
import time
from typing import Any

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

REQUEST_DELAY_SECONDS = 3
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3

ARTICLE_RECAP_SYSTEM_PROMPT = """
You rewrite news items into concise, factual recaps.

Your job is to preserve the original meaning of the news, not to transform it into an opinion piece, tutorial, marketing post, or long-form article.
Use only the facts provided in the input. If a detail is missing, leave it out.
Do not speculate, exaggerate, or add background that was not supplied.
""".strip()

LINKEDIN_SYSTEM_PROMPT = """
You write short LinkedIn posts that recap a news item in a clear, human, factual way.

Keep the meaning of the original news intact.
Do not turn the post into commentary, advice, or marketing copy.
Do not use emojis.
""".strip()

DAILY_SUMMARY_SYSTEM_PROMPT = """
You write a concise daily digest for a set of tech and cybersecurity news items.

Summarize the main themes that appeared across the provided stories and stay grounded in the supplied facts and metrics.
Do not invent trends, causes, or implications that are not supported by the input.
Do not use emojis or hype.
""".strip()


def _article_context(article: dict[str, Any]) -> str:
    return (
        f"Title: {article['title']}\n"
        f"Summary: {article['summary']}\n"
        f"Source: {article['source']}\n"
        f"Date: {article.get('date', '')}\n"
        f"Link: {article['url']}"
    )


def _call_groq(
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> str | None:
    if not GROQ_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(REQUEST_DELAY_SECONDS)
        try:
            response = requests.post(
                GROQ_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )

            if response.status_code == 429:
                wait_seconds = 15 * attempt
                print(
                    f"   Rate limit from Groq, waiting {wait_seconds}s "
                    f"(attempt {attempt}/{MAX_RETRIES})..."
                )
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()

        except Exception as error:
            print(f"   Groq error (attempt {attempt}/{MAX_RETRIES}): {error}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    return None


def generate_article_recap(article: dict[str, Any]) -> str | None:
    prompt = (
        "Rewrite this news item as a concise recap.\n\n"
        "Rules:\n"
        "- Language: English\n"
        "- Length: 90-140 words\n"
        "- Keep the original facts, scope, and tone intact\n"
        "- Focus on what happened and the key takeaway from the supplied text\n"
        "- Do not add opinions, speculation, extra background, recommendations, or clickbait\n"
        "- Do not use bullets, hashtags, markdown, or emojis\n"
        "- Use 1-2 short paragraphs\n"
        "- If the input is sparse, stay close to it and say less rather than inventing details\n\n"
        f"{_article_context(article)}\n\n"
        "Return only the recap text."
    )
    return _call_groq(
        system_prompt=ARTICLE_RECAP_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=260,
        temperature=0.2,
    )


def generate_linkedin_post(article: dict[str, Any]) -> str | None:
    prompt = (
        "Write a short LinkedIn post that recaps this news item.\n\n"
        "Rules:\n"
        "- Language: English\n"
        "- Length: 80-120 words total before hashtags\n"
        "- Start with the key fact from the story, not with a greeting or scene-setting line\n"
        "- Keep it factual and conversational\n"
        "- Rephrase the news faithfully instead of expanding it into broader commentary\n"
        "- No emojis anywhere in the post\n"
        "- No bullets and no markdown\n"
        "- No hashtags in the body text\n"
        "- End with exactly 2-3 relevant hashtags on the last line only\n\n"
        f"{_article_context(article)}\n\n"
        "Return only the LinkedIn post."
    )
    return _call_groq(
        system_prompt=LINKEDIN_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=220,
        temperature=0.3,
    )


def generate_daily_summary(
    articles: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> str | None:
    article_lines = []
    for index, article in enumerate(articles, start=1):
        article_lines.append(
            f"{index}. {article['title']} | Source: {article['source']} | "
            f"Summary: {article['summary']}"
        )

    prompt = (
        "Create a daily summary for today's collected news.\n\n"
        "Rules:\n"
        "- Language: English\n"
        "- Length: 120-180 words\n"
        "- Mention the strongest themes and what stood out across the set of stories\n"
        "- Keep the text neutral and information-dense\n"
        "- Do not mention that an AI wrote it\n"
        "- Do not use bullets, markdown, emojis, or hashtags\n"
        "- Use the supplied metrics naturally when relevant, but do not simply list them all\n\n"
        f"Metrics: {metrics}\n\n"
        "Articles:\n"
        f"{chr(10).join(article_lines)}\n\n"
        "Return only the summary text."
    )
    return _call_groq(
        system_prompt=DAILY_SUMMARY_SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=320,
        temperature=0.3,
    )
