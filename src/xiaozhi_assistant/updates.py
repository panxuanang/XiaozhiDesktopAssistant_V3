from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import requests

from . import __version__
from .config import load_settings


def check_update() -> dict | None:
    url = load_settings().update_manifest_url.strip()
    if not url:
        return None
    response = requests.get(url, timeout=8)
    response.raise_for_status()
    data = response.json()
    if str(data.get("version", "")) <= __version__:
        return None
    return data


def download_update(manifest: dict) -> Path:
    url = manifest["url"]
    expected = str(manifest.get("sha256", "")).lower()
    target = Path(tempfile.gettempdir()) / Path(url).name
    response = requests.get(url, timeout=60, stream=True)
    response.raise_for_status()
    h = hashlib.sha256()
    with target.open("wb") as fh:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                fh.write(chunk)
                h.update(chunk)
    if expected and h.hexdigest().lower() != expected:
        target.unlink(missing_ok=True)
        raise RuntimeError("更新包 SHA256 校验失败。")
    return target
