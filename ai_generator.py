import requests
import os
import time

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "llama-3.3-70b-versatile"  # безкоштовна модель

DELAY = 3   # Groq набагато швидший — 3 секунди достатньо
MAX_RETRIES = 3

POST_PROMPT = """You are a technical blog writer specialising in cybersecurity and DevOps.

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

Return ONLY the article text, no explanations."""

def generate_post(article: dict) -> dict | None:
    if not GROQ_API_KEY:
        return None

    prompt = POST_PROMPT.format(
        title=article["title"],
        summary=article["summary"],
        source=article["source"],
        url=article["url"],
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.7,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(DELAY)
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)

            if resp.status_code == 429:
                wait = 15 * attempt
                print(f"   ⏳ Rate limit, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()

            tags, body = [], text
            if "Tags:" in text:
                parts = text.rsplit("Tags:", 1)
                body  = parts[0].strip()
                tags  = [t.strip() for t in parts[1].split(",") if t.strip()]

            return {
                "title":      article["title"],
                "body":       body,
                "tags":       tags,
                "source_url": article["url"],
            }

        except Exception as e:
            print(f"   ❌ Groq error (attempt {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    return None
