from __future__ import annotations

import base64
import json
import os
from typing import Any

from .paths import secrets_path


def _protect(data: bytes) -> bytes:
    if os.name == "nt":
        import win32crypt
        return win32crypt.CryptProtectData(data, "XiaozhiDesktopAssistant", None, None, None, 0)
    return base64.b64encode(data)


def _unprotect(data: bytes) -> bytes:
    if os.name == "nt":
        import win32crypt
        return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
    return base64.b64decode(data)


def load_secrets() -> dict[str, Any]:
    path = secrets_path()
    if not path.exists():
        return {}
    try:
        return json.loads(_unprotect(path.read_bytes()).decode("utf-8"))
    except Exception:
        return {}


def save_secrets(values: dict[str, Any]) -> None:
    path = secrets_path()
    raw = json.dumps(values, ensure_ascii=False).encode("utf-8")
    path.write_bytes(_protect(raw))


def get_api_key() -> str:
    return str(load_secrets().get("api_key", ""))


def set_api_key(value: str) -> None:
    data = load_secrets()
    data["api_key"] = value.strip()
    save_secrets(data)
