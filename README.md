# News Parser

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/)
[![Linux](https://img.shields.io/badge/Linux_systemd-FCC624?style=for-the-badge&logo=linux&logoColor=black)](https://www.freedesktop.org/wiki/Software/systemd/)

News Parser collects tech and cybersecurity stories from RSS feeds, rewrites them into concise recaps, sends them to Telegram for review, answers follow-up questions in chat, and publishes approved posts to LinkedIn with an article preview card.

## What It Does

- pulls new stories from curated RSS feeds
- generates a factual recap, a short LinkedIn-ready version, and a full daily briefing
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

```bash
git clone https://github.com/mea37065/news-parser.git
cd news-parser
```

Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

Create your local config:

```bash
cp .env.example .env
```

Fill in `.env` with at least:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_ACCESS_TOKEN`
- `GROQ_API_KEY` if AI features should be enabled

Start the bot:

```bash
python bot.py
```

## Run Modes

Main bot loop:

```bash
python bot.py
```

One parsing cycle:

```bash
python parser.py
```

One Telegram callback poll:

```bash
python poll.py
```

`poll.py` now checks both inline button callbacks and regular chat messages so question mode works in the same loop.

## Linux Service With systemd

This branch is tailored for Linux and uses `systemd` for a long-running service.

Recommended deployment layout:

```bash
sudo mkdir -p /opt/news-parser
sudo rsync -a --delete ./ /opt/news-parser/
sudo cp /opt/news-parser/.env.example /opt/news-parser/.env
sudo nano /opt/news-parser/.env
sudo ./scripts/linux/install-systemd-service.sh
sudo systemctl start news-parser
```

Useful service commands:

```bash
sudo systemctl status news-parser
sudo systemctl restart news-parser
sudo systemctl stop news-parser
sudo journalctl -u news-parser -f
```

Keep a filled `.env` file in the project root or in `/opt/news-parser/.env` when using the provided unit.

## Configuration

Configuration is loaded in this order:

1. environment variables
2. `.env`
3. optional host-level secret injection through the service environment

Important settings are listed in `.env.example`, including:

- `SCHEDULE_TIMEZONE`
- `DAILY_RUN_HOUR`
- `DAILY_RUN_MINUTE`
- `MAX_ENTRIES_PER_FEED`
- `STORAGE_PATH`
- `FEEDS_PATH`
- `GROQ_MODEL`

## Development

Run checks:

```bash
python -m ruff check .
python -m pytest -q -o addopts="-p no:cacheprovider --basetemp=pytest_run_tmp"
```

GitHub Actions runs linting, tests, and syntax validation.

## LinkedIn Notes

- the LinkedIn post text is intentionally short and does not repeat the article title as a heading
- the source URL is attached as an article share so LinkedIn can render its own preview card
- the preview quality still depends on the target website exposing usable Open Graph metadata

## License

Apache License 2.0. See `LICENSE`.
