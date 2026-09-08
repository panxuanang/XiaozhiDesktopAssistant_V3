from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from .paths import action_db_path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(action_db_path())
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            args_json TEXT NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL
        )
        """
    )
    return conn


def record(action: str, args: dict[str, Any] | None = None, status: str = "ok", detail: str = "") -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO actions(ts, action, args_json, status, detail) VALUES(?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), action, json.dumps(args or {}, ensure_ascii=False, default=str), status, detail[:4000]),
        )


def recent(limit: int = 100) -> list[dict[str, str]]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, action, args_json, status, detail FROM actions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(ts=r[0], action=r[1], args=r[2], status=r[3], detail=r[4]) for r in rows]
