import requests
import os
import time

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL     = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
)

DELAY_BETWEEN_REQUESTS = 5   # секунд між запитами (ліміт 15 req/min)
MAX_RETRIES            = 3

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

def generate_post(article: dict) -> dict | None:
    if not GEMINI_API_KEY:
        return None

    prompt  = POST_PROMPT.format(
        title=article["title"],
        summary=article["summary"],
        source=article["source"],
        url=article["url"],
    )
    payload = {
        "contents":         [{"parts": [{"text": prompt}]}],
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
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

            tags, body = [], text
            if "Tags:" in text:
                parts    = text.rsplit("Tags:", 1)
                body     = parts[0].strip()
                tags     = [t.strip() for t in parts[1].split(",") if t.strip()]

            return {
                "title":      article["title"],
                "body":       body,
                "tags":       tags,
                "source_url": article["url"],
            }

        except Exception as e:
            print(f"   ❌ Gemini error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    return None
