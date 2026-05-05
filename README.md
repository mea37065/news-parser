# News Parser

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/)

News Parser collects general-interest stories from curated RSS feeds, rewrites them into concise recaps, sends them to Telegram for review, answers follow-up questions in chat, and publishes approved posts to LinkedIn with an article preview card.

## What It Does

- pulls new stories from curated RSS feeds across world, business, technology, science, health, and culture
- generates a factual recap, an at-a-glance review message, a short LinkedIn-ready version, and a full daily briefing
- sends review messages to Telegram with review and follow-up question actions
- lets you ask extra questions about a story directly in Telegram chat
- publishes approved items to LinkedIn as article shares with a richer link preview
- stores runtime state in SQLite

## Telegram Workflow

For each story, the bot sends:

- a short recap with `Review LinkedIn`
- an `Ask a question` action that opens question mode for that article

In question mode, send follow-up messages in the same chat. You can also reply directly to the article message. Use `/done` to close the active question context.

At the end of the run, the bot sends a larger daily briefing designed to replace reading every single item one by one.

## Requirements

- Python `3.11+`
- Telegram bot token and chat ID
- LinkedIn access token
- Groq API key if you want AI-generated recap and summary content

## Quick Start

Clone the repository:

```sh
git clone https://github.com/mea37065/news-parser.git
cd news-parser
```

Create a virtual environment and install dependencies:

```sh
python -m venv .venv
# Activate .venv in your shell, then:
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create your local config:

```sh
cp .env.example .env
```

Fill in `.env` with at least:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_ACCESS_TOKEN`
- `GROQ_API_KEY` if AI features should be enabled

Start the bot:

```sh
python bot.py
```

## Run Modes

Main bot loop:

```sh
python bot.py
```

One parsing cycle:

```sh
python parser.py
```

One Telegram callback poll:

```sh
python poll.py
```

`poll.py` now checks both inline button callbacks and regular chat messages so question mode works in the same loop.

## Configuration

Configuration is loaded in this order:

1. environment variables
2. `.env`

Important settings are listed in `.env.example`, including:

- `SCHEDULE_TIMEZONE`
- `DAILY_RUN_HOUR`
- `DAILY_RUN_MINUTE`
- `MAX_ENTRIES_PER_FEED`
- `STORAGE_PATH`
- `FEEDS_PATH`
- `NEWS_INTEREST_CATEGORIES`
- `FEED_FETCH_TIMEOUT_SECONDS`
- `ENABLE_ARTICLE_FETCH`
- `ARTICLE_FETCH_TIMEOUT_SECONDS`
- `GROQ_MODEL`
- `LINKEDIN_REQUEST_TIMEOUT_SECONDS`
- `LINKEDIN_MAX_RETRIES`
- `LINKEDIN_RETRY_BACKOFF_SECONDS`

`NEWS_INTEREST_CATEGORIES` controls the source mix. The default is:

```sh
NEWS_INTEREST_CATEGORIES=general,world,business,technology,science,health,culture
```

Useful starting profiles:

- broad daily digest: `general,world,business,technology,science,health,culture`
- serious overview: `general,world,business,science,health`
- innovation-focused: `technology,science,business`
- lighter read: `general,culture,science,technology`

If you are tuning the bot for yourself, answer these quick questions and keep
the matching categories:

- "What should I know to understand the day?" -> `general`, `world`
- "What affects work, money, companies, or markets?" -> `business`
- "What future tools or products are emerging?" -> `technology`
- "What discoveries, climate, or space stories are worth tracking?" -> `science`
- "What affects daily life and wellbeing?" -> `health`
- "What is culturally interesting but not urgent?" -> `culture`

You can also set `NEWS_INTEREST_CATEGORIES=all` to use every feed in `feeds.json`.

For constrained hosts, set `ENABLE_ARTICLE_FETCH=false` and
`MAX_ENTRIES_PER_FEED=1` while testing. The bot will rely on RSS summaries and
will reach Telegram faster.

## Development

Run checks:

```sh
python -m ruff check .
python -m pytest -q -o addopts="-p no:cacheprovider --basetemp=pytest_run_tmp"
```

GitHub Actions runs linting, tests, and syntax validation.

## LinkedIn Notes

- the LinkedIn post text is intentionally short and does not repeat the article title as a heading
- the source URL is attached as an article share so LinkedIn can render its own preview card
- the preview quality still depends on the target website exposing usable Open Graph metadata
- if LinkedIn times out, increase `LINKEDIN_REQUEST_TIMEOUT_SECONDS`; requests are retried according to `LINKEDIN_MAX_RETRIES` and `LINKEDIN_RETRY_BACKOFF_SECONDS`

## License

Apache License 2.0. See `LICENSE`.
