from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .paths import work_db_path


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(work_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            source TEXT NOT NULL,
            contact TEXT NOT NULL,
            source_text TEXT NOT NULL,
            attachment_path TEXT NOT NULL,
            instruction TEXT NOT NULL,
            status TEXT NOT NULL,
            result_summary TEXT NOT NULL,
            output_paths_json TEXT NOT NULL,
            due_at TEXT NOT NULL,
            meta_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status, updated_at);

        CREATE TABLE IF NOT EXISTS scheduled_actions (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            run_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            authorized INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scheduled_due ON scheduled_actions(status, run_at);

        CREATE TABLE IF NOT EXISTS work_memory (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    return conn


def create_task(
    *,
    source: str = "manual",
    contact: str = "",
    source_text: str = "",
    attachment_path: str = "",
    instruction: str = "",
    due_at: str = "",
    status: str = "pending",
    meta: dict[str, Any] | None = None,
) -> str:
    task_id = "task_" + uuid.uuid4().hex[:12]
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO tasks(id,created_at,updated_at,source,contact,source_text,attachment_path,instruction,status,result_summary,output_paths_json,due_at,meta_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (task_id, now, now, source, contact, source_text, attachment_path, instruction, status, "", "[]", due_at, json.dumps(meta or {}, ensure_ascii=False)),
        )
    return task_id


def update_task(task_id: str, **changes: Any) -> None:
    allowed = {"contact", "source_text", "attachment_path", "instruction", "status", "result_summary", "due_at"}
    sets: list[str] = ["updated_at=?"]
    values: list[Any] = [_now()]
    for key, value in changes.items():
        if key == "output_paths":
            sets.append("output_paths_json=?")
            values.append(json.dumps(value or [], ensure_ascii=False))
        elif key == "meta":
            sets.append("meta_json=?")
            values.append(json.dumps(value or {}, ensure_ascii=False))
        elif key in allowed:
            sets.append(f"{key}=?")
            values.append(value)
    if len(sets) == 1:
        return
    values.append(task_id)
    with _conn() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", values)


def get_task(task_id: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    return _task_dict(row) if row else None


def latest_task(statuses: tuple[str, ...] | None = None) -> dict[str, Any] | None:
    with _conn() as conn:
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            row = conn.execute(f"SELECT * FROM tasks WHERE status IN ({placeholders}) ORDER BY updated_at DESC LIMIT 1", statuses).fetchone()
        else:
            row = conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT 1").fetchone()
    return _task_dict(row) if row else None


def list_tasks(limit: int = 100, status: str = "") -> list[dict[str, Any]]:
    with _conn() as conn:
        if status:
            rows = conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY updated_at DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return [_task_dict(r) for r in rows]


def _task_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["output_paths"] = json.loads(d.pop("output_paths_json") or "[]")
    d["meta"] = json.loads(d.pop("meta_json") or "{}")
    return d


def schedule_action(
    *,
    action_type: str,
    run_at: str,
    payload: dict[str, Any],
    task_id: str = "",
    authorized: bool = False,
    status: str = "scheduled",
) -> str:
    action_id = "job_" + uuid.uuid4().hex[:12]
    now = _now()
    with _conn() as conn:
        conn.execute(
            """INSERT INTO scheduled_actions(id,task_id,action_type,run_at,payload_json,authorized,status,attempts,last_error,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (action_id, task_id, action_type, run_at, json.dumps(payload, ensure_ascii=False), 1 if authorized else 0, status, 0, "", now, now),
        )
    return action_id


def list_scheduled(limit: int = 100, status: str = "") -> list[dict[str, Any]]:
    with _conn() as conn:
        if status:
            rows = conn.execute("SELECT * FROM scheduled_actions WHERE status=? ORDER BY run_at ASC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM scheduled_actions ORDER BY run_at ASC LIMIT ?", (limit,)).fetchall()
    return [_job_dict(r) for r in rows]


def due_actions(now_iso: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    now_iso = now_iso or _now()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_actions WHERE status='scheduled' AND run_at<=? ORDER BY run_at ASC LIMIT ?",
            (now_iso, limit),
        ).fetchall()
    return [_job_dict(r) for r in rows]


def _job_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["payload"] = json.loads(d.pop("payload_json") or "{}")
    d["authorized"] = bool(d["authorized"])
    return d


def update_scheduled(action_id: str, *, status: str | None = None, error: str | None = None, increment_attempts: bool = False, run_at: str | None = None) -> None:
    sets = ["updated_at=?"]
    values: list[Any] = [_now()]
    if status is not None:
        sets.append("status=?"); values.append(status)
    if error is not None:
        sets.append("last_error=?"); values.append(error[:2000])
    if increment_attempts:
        sets.append("attempts=attempts+1")
    if run_at is not None:
        sets.append("run_at=?"); values.append(run_at)
    values.append(action_id)
    with _conn() as conn:
        conn.execute(f"UPDATE scheduled_actions SET {', '.join(sets)} WHERE id=?", values)


def cancel_scheduled(action_id: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("UPDATE scheduled_actions SET status='cancelled', updated_at=? WHERE id=? AND status IN ('scheduled','pending_confirmation')", (_now(), action_id))
    return cur.rowcount > 0


def remember(key: str, value: Any) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO work_memory(key,value_json,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )


def recall(key: str, default: Any = None) -> Any:
    with _conn() as conn:
        row = conn.execute("SELECT value_json FROM work_memory WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def latest_pending_schedule() -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM scheduled_actions WHERE status='pending_confirmation' ORDER BY created_at DESC LIMIT 1").fetchone()
    return _job_dict(row) if row else None


def authorize_scheduled(action_id: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("UPDATE scheduled_actions SET authorized=1,status='scheduled',updated_at=? WHERE id=? AND status='pending_confirmation'", (_now(), action_id))
    return cur.rowcount > 0
