# News Parser

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/)
[![Windows](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)

News Parser is a small automation tool that collects fresh tech and cybersecurity stories from RSS feeds, rewrites them into concise factual recaps, sends them to Telegram for review, and lets you publish approved items to LinkedIn.

## Overview

- Runs one parsing cycle per day at `08:00` in the `Europe/Bratislava` timezone
- Pulls new items from curated RSS feeds
- Generates:
  - a short recap of each story
  - a LinkedIn-ready version of the same story
  - a daily summary with simple metrics
- Sends review previews to Telegram
- Publishes approved posts to LinkedIn

## How It Works

1. `parser.py` loads RSS feeds and detects new articles.
2. `ai_generator.py` rewrites each story into a factual recap and LinkedIn post.
3. `bot.py` sends previews to Telegram and handles callback actions.
4. `linkedin_publisher.py` publishes approved items to LinkedIn.
5. After the batch is finished, the bot sends a daily summary.

## Project Files

- `bot.py` - scheduler and Telegram callback loop
- `parser.py` - feed parsing, recap generation, Telegram delivery, and summary creation
- `ai_generator.py` - Groq client wrapper and prompts
- `linkedin_publisher.py` - LinkedIn publishing logic
- `credentials.py` - Windows Credential Manager integration
- `poll.py` - one-shot callback polling entry point
- `start.bat` - Windows bootstrap script

## Requirements

- Python `3.11+`
- Windows PowerShell
- Telegram bot token and chat ID
- Groq API key
- LinkedIn access token with permission to create posts

## Configuration

The project reads secrets from Windows Credential Manager.

Create credentials using the `MyApp/<KEY>` target format for:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GROQ_API_KEY`
- `LINKEDIN_ACCESS_TOKEN`

`.env.example` is included only as a reference template. Do not commit real secrets.

## Install

```powershell
py -m venv venv
.\venv\Scripts\activate
py -m pip install -r requirements.txt
```

## Run

```powershell
py bot.py
```

If you prefer, you can start it through:

```powershell
.\start.bat
```

## CI

GitHub Actions runs a lightweight validation workflow that installs dependencies and checks Python syntax for the main project files.

## Public Repository Notes

- Runtime state files such as `pending.json`, `seen.json`, `tg_offset.txt`, and `schedule_state.json` are ignored
- Local secrets are not tracked
- The repository currently does not include a license file
