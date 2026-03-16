import requests
import os
import time

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_ENABLED = bool(GEMINI_API_KEY and GEMINI_API_KEY != "YOUR_GEMINI_API_KEY")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent?key=" + GEMINI_API_KEY
) if GEMINI_ENABLED else ""

DELAY_BETWEEN_REQUESTS = 5
MAX_RETRIES            = 2

POST_PROMPT = """
You are a technical blog writer specialising in cybersecurity and DevOps.

Based on this news item, write a complete blog article:

Title: {title}
Summary: {summary}
Source: {source}
Link: {url}

Requirements:
- Language: English
- Length: 300-500 words
- Structure: intro -> core issue -> what it means for practitioners -> conclusion
- Tone: professional but readable
- Add 3-5 relevant tags at the end in this format: Tags: tag1, tag2, tag3
- Do NOT use markdown headings (#), use plain paragraphs only

Return ONLY the article text, no explanations.
"""

def _call_gemini(prompt: str) -> str | None:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024},
    }
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(DELAY_BETWEEN_REQUESTS)
        try:
            resp = requests.post(GEMINI_URL, json=payload, timeout=30)
            if resp.status_code == 429:
                wait = 20 * attempt
                print(f"   ⏳ Rate limit, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            if resp.status_code == 503:
                print(f"   ⏳ Gemini unavailable, waiting 15s...")
                time.sleep(15)
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            print(f"   ❌ Gemini error (attempt {attempt}): {e}")
            time.sleep(10)
    return None

def generate_post(article: dict) -> dict | None:
    """
    Генерує пост через Gemini.
    Якщо Gemini вимкнений або не відповідає — повертає None,
    і parser використає fallback (оригінальний summary).
    """
    if not GEMINI_ENABLED:
        print(f"   ℹ️  Gemini disabled — using original summary")
        return None

    prompt = POST_PROMPT.format(
        title=article["title"],
        summary=article["summary"],
        source=article["source"],
        url=article["url"],
    )

    text = _call_gemini(prompt)
    if not text:
        return None

    tags = []
    body = text
    if "Tags:" in text:
        parts = text.rsplit("Tags:", 1)
        body     = parts[0].strip()
        raw_tags = parts[1].strip()
        tags     = [t.strip() for t in raw_tags.split(",") if t.strip()]

    return {
        "title":      article["title"],
        "body":       body,
        "tags":       tags,
        "source_url": article["url"],
    }
