# News Parser

`news-parser` collects fresh tech and cybersecurity items from a curated RSS list, rewrites them into short factual recaps, sends each item to Telegram for review, and lets you publish selected posts to LinkedIn.

## What It Does

- Runs one parsing cycle per day at `08:00` in the `Europe/Bratislava` timezone (`CET` in winter, `CEST` in summer)
- Pulls items from RSS feeds focused on security, cloud, infrastructure, and engineering news
- Generates:
  - a concise news recap
  - a LinkedIn-ready version of the same story
  - a daily summary with metrics after the full batch is processed
- Sends each item to Telegram with review buttons
- Publishes approved items to LinkedIn

## Project Structure

- `bot.py` - scheduler and Telegram callback loop
- `parser.py` - feed parsing, recap generation, Telegram delivery, daily summary
- `ai_generator.py` - prompts and Groq client wrapper
- `linkedin_publisher.py` - LinkedIn API publishing
- `credentials.py` - Windows Credential Manager loading
- `poll.py` - optional one-shot callback polling entry point

## Requirements

- Python `3.11+`
- Windows PowerShell
- A Telegram bot token and chat ID
- A Groq API key
- A LinkedIn access token with permission to create posts

## Configuration

The project reads secrets from Windows Credential Manager.

Create credentials with targets in the format `MyApp/<KEY>` for:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GROQ_API_KEY`
- `LINKEDIN_ACCESS_TOKEN`

You can keep a local `.env` for reference, but secrets should not be committed.

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

The included `start.bat` bootstraps the environment and starts the bot on Windows.

## Notes For Public Use

- Runtime state files are ignored and are not meant to be versioned
- The repository does not include secrets
- If you want to open-source this project formally, add a license that matches how you want others to use it
