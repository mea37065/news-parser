from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable

logger = logging.getLogger(__name__)

KEYS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "GROQ_API_KEY",
    "LINKEDIN_ACCESS_TOKEN",
]
DEFAULT_TARGET_PREFIX = "NewsParser"
LEGACY_TARGET_PREFIXES = ("MyApp",)
CRED_TYPE_GENERIC = 1
ERROR_NOT_FOUND = 1168


def _credential_target_prefix() -> str:
    return os.environ.get("CREDENTIAL_TARGET_PREFIX", DEFAULT_TARGET_PREFIX).strip(
        " \\/"
    ) or DEFAULT_TARGET_PREFIX


def _credential_target_names(key: str) -> Iterable[str]:
    prefixes = [_credential_target_prefix()]
    for prefix in LEGACY_TARGET_PREFIXES:
        if prefix not in prefixes:
            prefixes.append(prefix)

    for prefix in prefixes:
        yield f"{prefix}/{key}"


def _looks_utf16le(raw: bytes) -> bool:
    if len(raw) < 2 or len(raw) % 2:
        return False
    high_bytes = raw[1::2]
    if not high_bytes:
        return False
    return high_bytes.count(0) / len(high_bytes) >= 0.4


def _decode_credential_blob(raw: bytes) -> str | None:
    if not raw:
        return None

    encodings = (
        ("utf-16-le", "utf-8") if _looks_utf16le(raw) else ("utf-8", "utf-16-le")
    )
    for encoding in encodings:
        try:
            value = raw.decode(encoding).rstrip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if value:
            return value
    return None


def _read_credential(target: str) -> str | None:
    if sys.platform != "win32":
        return None

    import ctypes
    from ctypes import wintypes

    class Credential(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    try:
        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None

        for target_name in _credential_target_names(target):
            credential_pointer = ctypes.POINTER(Credential)()
            if not advapi32.CredReadW(
                target_name,
                CRED_TYPE_GENERIC,
                0,
                ctypes.byref(credential_pointer),
            ):
                error_code = ctypes.get_last_error()
                if error_code != ERROR_NOT_FOUND:
                    logger.warning(
                        "Could not read credential %s from Windows Credential "
                        "Manager: error %s",
                        target_name,
                        error_code,
                    )
                continue

            try:
                credential = credential_pointer.contents
                raw_value = ctypes.string_at(
                    credential.CredentialBlob,
                    credential.CredentialBlobSize,
                )
                value = _decode_credential_blob(raw_value)
                if value:
                    return value
            finally:
                advapi32.CredFree(credential_pointer)
    except Exception as error:
        logger.warning(
            "Could not read credential %s from Windows Credential Manager: %s",
            target,
            error,
        )
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
            logger.info("Loaded credential from host credential store: %s", key)
        else:
            missing.append(key)
            logger.debug(
                "Credential not found in environment or host credential store: %s",
                key,
            )

    if required and missing:
        joined = ", ".join(missing)
        prefix = _credential_target_prefix()
        raise RuntimeError(
            f"Missing required credentials: {joined}. "
            "Provide them via environment variables, .env, or Windows Credential "
            f"Manager targets like {prefix}/TELEGRAM_BOT_TOKEN."
        )
