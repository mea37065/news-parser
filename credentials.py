from __future__ import annotations

import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GROQ_API_KEY",
    "LINKEDIN_ACCESS_TOKEN",
]


def _read_credential(target: str) -> str | None:
    if sys.platform != "win32":
        return None

    try:
        script = f"""
        $cred = Get-StoredCredential -Target 'MyApp/{target}' 2>$null
        if ($cred) {{ $cred.GetNetworkCredential().Password }}
        """
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
        )
        value = result.stdout.strip()
        return value or None
    except Exception as error:
        logger.warning("Could not read credential %s: %s", target, error)
        return None


def load_credentials(*, required: bool = True) -> None:
    logger.info("Loading credentials from available sources")
    missing: list[str] = []

    for key in KEYS:
        if os.environ.get(key):
            logger.info("Credential already present in environment: %s", key)
            continue

        value = _read_credential(key)
        if value:
            os.environ[key] = value
            logger.info("Loaded credential from Windows Credential Manager: %s", key)
        else:
            missing.append(key)
            logger.info("Credential not found in Windows Credential Manager: %s", key)

    if required and missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Missing required credentials: {joined}. "
            "Provide them via environment variables, .env, "
            "or Windows Credential Manager."
        )
