import os
import subprocess

KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GROQ_API_KEY",
    "LINKEDIN_ACCESS_TOKEN",
]


def _read_credential(target: str) -> str | None:
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
        print(f"Could not read {target}: {error}")
        return None


def load_credentials() -> None:
    print("Loading credentials from Windows Credential Manager...")
    missing: list[str] = []

    for key in KEYS:
        value = _read_credential(key)
        if value:
            os.environ[key] = value
            print(f"   OK {key}")
        else:
            missing.append(key)
            print(f"   Missing {key}")

    if missing:
        print(f"\nMissing credentials: {', '.join(missing)}")
        print("Add them with cmdkey and restart.\n")
        raise RuntimeError("Missing required credentials")

    print("All credentials loaded.\n")
