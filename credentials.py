# credentials.py
import subprocess
import os
import json

KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GROQ_API_KEY",
    "DEVTO_API_KEY",
    "LINKEDIN_ACCESS_TOKEN",
]

def _read_credential(target: str) -> str | None:
    """Читає пароль з Windows Credential Manager через cmdkey."""
    try:
        # Використовуємо PowerShell для читання через CredentialManager
        script = f"""
        $cred = Get-StoredCredential -Target 'MyApp/{target}' 2>$null
        if ($cred) {{ $cred.GetNetworkCredential().Password }}
        """
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True
        )
        value = result.stdout.strip()
        return value if value else None
    except Exception as e:
        print(f"⚠️  Could not read {target}: {e}")
        return None

def load_credentials():
    """Завантажує всі ключі з Credential Manager в os.environ."""
    print("🔐 Loading credentials from Windows Credential Manager...")
    missing = []

    for key in KEYS:
        value = _read_credential(key)
        if value:
            os.environ[key] = value
            print(f"   ✅ {key}")
        else:
            missing.append(key)
            print(f"   ❌ {key} — not found!")

    if missing:
        print(f"\n⛔ Missing credentials: {', '.join(missing)}")
        print("   Run cmdkey to add them and restart.\n")
        raise RuntimeError("Missing required credentials")

    print("   All credentials loaded.\n")