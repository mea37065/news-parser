# News Parser

[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://telegram.org/)
[![Groq](https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/)
[![Windows](https://img.shields.io/badge/Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)

News Parser collects tech and cybersecurity stories from RSS feeds, rewrites them into concise recaps, sends them to Telegram for review, and publishes approved posts to LinkedIn.

## What It Does

- pulls new stories from curated RSS feeds
- generates a recap, a LinkedIn-ready version, and a daily summary
- sends review messages to Telegram
- publishes approved items to LinkedIn
- stores runtime state in SQLite

## Requirements

- Python `3.11+`
- Telegram bot token and chat ID
- LinkedIn access token
- Groq API key if you want AI-generated recap and summary content

## Quick Start

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

Create your local config:

```powershell
Copy-Item .env.example .env
```

Fill in `.env` with at least:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `LINKEDIN_ACCESS_TOKEN`
- `GROQ_API_KEY` if AI features should be enabled

Start the bot:

```powershell
py bot.py
```

Windows bootstrap script:

```powershell
.\start.bat
```

## Run Modes

Main bot loop:

```powershell
py bot.py
```

One parsing cycle:

```powershell
py parser.py
```

One Telegram callback poll:

```powershell
py poll.py
```

## Windows Service

For a long-running Windows setup, use `nssm`.

Do not use `start.bat` as the service command. It is interactive and meant for manual local runs.

Example:

```powershell
nssm install NewsParserBot "C:\path\to\news-parser\venv\Scripts\python.exe" "C:\path\to\news-parser\bot.py"
nssm set NewsParserBot AppDirectory "C:\path\to\news-parser"
nssm set NewsParserBot DisplayName "News Parser Bot"
nssm set NewsParserBot Description "Parses RSS feeds, sends Telegram review messages, and publishes approved posts to LinkedIn."
nssm set NewsParserBot Start SERVICE_AUTO_START
nssm set NewsParserBot AppStdout "C:\path\to\news-parser\service-out.log"
nssm set NewsParserBot AppStderr "C:\path\to\news-parser\service-error.log"
nssm set NewsParserBot AppRotateFiles 1
nssm start NewsParserBot
```

Useful commands:

```powershell
nssm status NewsParserBot
nssm restart NewsParserBot
nssm stop NewsParserBot
nssm remove NewsParserBot confirm
```

If the service account does not use Windows Credential Manager, keep a filled `.env` file in the project root.

## Configuration

Configuration is loaded in this order:

1. environment variables
2. `.env`
3. Windows Credential Manager targets in the `MyApp/<KEY>` format

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

```powershell
py -m ruff check .
py -m pytest -q -o addopts="-p no:cacheprovider --basetemp=pytest_run_tmp"
```

GitHub Actions runs linting, tests, and syntax validation.

## License

Apache License 2.0. See `LICENSE`.
