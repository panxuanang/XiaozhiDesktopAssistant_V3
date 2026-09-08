from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "XiaozhiDesktopAssistant"


def app_data_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def secrets_path() -> Path:
    return app_data_dir() / "secrets.bin"


def logs_dir() -> Path:
    p = app_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def action_db_path() -> Path:
    return app_data_dir() / "actions.sqlite3"


def work_db_path() -> Path:
    return app_data_dir() / "workmate.sqlite3"


def file_index_db_path() -> Path:
    return app_data_dir() / "file-index.sqlite3"


def browser_profile_dir() -> Path:
    p = app_data_dir() / "browser-profile"
    p.mkdir(parents=True, exist_ok=True)
    return p


def pending_dir() -> Path:
    p = app_data_dir() / "pending"
    p.mkdir(parents=True, exist_ok=True)
    return p


def generated_dir() -> Path:
    p = app_data_dir() / "generated"
    p.mkdir(parents=True, exist_ok=True)
    return p


def executable_command_for_mcp_server() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mcp-server"]
    return [sys.executable, "-m", "xiaozhi_assistant.mcp_server"]
