# News Parser

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/)
[![Windows](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)

News Parser is a small automation tool that collects fresh tech and cybersecurity stories from RSS feeds, rewrites them into concise factual recaps, sends them to Telegram for review, and lets you publish approved items to LinkedIn.

## Overview

- Runs one parsing cycle per day at `08:00` in the `Europe/Bratislava` timezone by default
- Pulls new items from curated RSS feeds
- Generates:
  - a short recap of each story
  - a LinkedIn-ready version of the same story
  - a daily summary with simple metrics
- Sends review previews to Telegram
- Publishes approved posts to LinkedIn
- Retries articles that were discovered but failed before Telegram delivery

## Project Files

- `bot.py` - main loop with scheduler and Telegram callback handling
- `parser.py` - feed discovery, AI generation, Telegram delivery, and daily summary
- `ai_generator.py` - Groq client wrapper and prompt orchestration
- `linkedin_publisher.py` - LinkedIn publishing logic
- `telegram_client.py` - Telegram HTTP client wrapper
- `storage.py` - SQLite-backed persistence and lifecycle state
- `content_fetcher.py` - optional article page text extraction
- `app_config.py` - centralized configuration loading
- `credentials.py` - credential loading from env, `.env`, and Windows Credential Manager
- `feeds.json` - editable feed catalog
- `poll.py` - one-shot callback polling entry point

## Architecture Notes

- Runtime state lives in SQLite instead of multiple JSON files
- Articles move through explicit statuses: `discovered`, `delivery_failed`, `queued`, `reviewing`, `published`, `skipped`
- Feed definitions are stored in `feeds.json`
- Story generation uses one AI request for recap + LinkedIn copy
- The parser can fetch article page text to improve prompt quality
- CI runs linting, tests, and syntax validation

## Requirements

- Python `3.11+`
- Telegram bot token and chat ID
- Groq API key
- LinkedIn access token with permission to create posts

## Quick Start From Zero

Clone the repository:

```powershell
git clone https://github.com/mea37065/news-parser.git
cd news-parser
```

Create a virtual environment and install dependencies:

```powershell
py -m venv venv
.\venv\Scripts\activate
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt
```

Create a local config file from the example:

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in at least:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_ACCESS_TOKEN`
- `GROQ_API_KEY` if you want AI-generated recap and summary content

Run the app:

```powershell
py bot.py
```

If you want the simple Windows bootstrap flow instead:

```powershell
.\start.bat
```

## Configuration

The app loads configuration in this order:

1. existing environment variables
2. `.env`
3. Windows Credential Manager targets in the `MyApp/<KEY>` format

The project is currently Windows-first because it supports Windows Credential Manager out of the box. If those credentials are not available, environment variables or `.env` still work.

Required secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_ACCESS_TOKEN`

Optional secret:

- `GROQ_API_KEY`

Useful runtime settings are listed in `.env.example`, including:

- `SCHEDULE_TIMEZONE`
- `DAILY_RUN_HOUR`
- `DAILY_RUN_MINUTE`
- `MAX_ENTRIES_PER_FEED`
- `STORAGE_PATH`
- `FEEDS_PATH`
- `GROQ_MODEL`

## Install

```powershell
py -m venv venv
.\venv\Scripts\activate
py -m pip install -r requirements.txt
py -m pip install -r requirements-dev.txt
```

## Run

Start the bot loop:

```powershell
py bot.py
```

Run one parsing cycle directly:

```powershell
py parser.py
```

Process Telegram callbacks once:

```powershell
py poll.py
```

## Testing

```powershell
py -m ruff check .
py -m pytest -q -o addopts="-p no:cacheprovider --basetemp=pytest_run_tmp"
```

## CI

GitHub Actions now performs:

- dependency installation
- `ruff` linting
- `pytest` execution
- Python syntax validation

## Notes

- Runtime state is stored in `news_parser.db` by default
- Local secrets and temporary test directories are ignored by git
- The project is licensed under Apache License 2.0
