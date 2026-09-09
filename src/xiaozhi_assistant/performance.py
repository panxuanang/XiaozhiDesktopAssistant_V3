from __future__ import annotations

import json
import time
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, asdict
from typing import Any, Iterator

from .action_log import recent, record
from .config import load_settings


@dataclass
class PerfEvent:
    stage: str
    elapsed_ms: int
    route: str = ""
    api_calls: int = 0
    tool_calls: int = 0
    detail: str = ""


_EVENTS: deque[PerfEvent] = deque(maxlen=80)
_API_CALLS: ContextVar[int] = ContextVar("xiaozhi_api_calls", default=0)


def mark_api_call(count: int = 1) -> None:
    _API_CALLS.set(_API_CALLS.get() + max(0, int(count)))


def api_call_count() -> int:
    return int(_API_CALLS.get())


def reset_api_counter() -> Token:
    return _API_CALLS.set(0)


def restore_api_counter(token: Token) -> None:
    _API_CALLS.reset(token)


def log_timing(
    stage: str,
    elapsed_ms: float,
    *,
    route: str = "",
    api_calls: int = 0,
    tool_calls: int = 0,
    detail: str = "",
) -> PerfEvent:
    event = PerfEvent(
        stage=stage,
        elapsed_ms=max(0, int(round(elapsed_ms))),
        route=route,
        api_calls=max(0, int(api_calls)),
        tool_calls=max(0, int(tool_calls)),
        detail=detail[:500],
    )
    _EVENTS.append(event)
    if load_settings().performance.timing_log_enabled:
        record("performance", asdict(event), detail=event.detail)
    return event


@contextmanager
def timed(stage: str, *, route: str = "", detail: str = "") -> Iterator[dict[str, Any]]:
    start = time.perf_counter()
    state: dict[str, Any] = {"api_calls": 0, "tool_calls": 0}
    try:
        yield state
    finally:
        log_timing(
            stage,
            (time.perf_counter() - start) * 1000,
            route=route,
            api_calls=int(state.get("api_calls", 0)),
            tool_calls=int(state.get("tool_calls", 0)),
            detail=detail,
        )


def performance_report(limit: int = 12) -> str:
    """Human-readable local timing report. No AI call."""
    limit = max(1, min(int(limit), 40))
    events = list(_EVENTS)[-limit:]
    if not events:
        # Process may have restarted; recover recent timing rows from SQLite.
        for row in reversed(recent(limit=200)):
            if row.get("action") != "performance":
                continue
            try:
                data = json.loads(row.get("args", "{}"))
                events.append(PerfEvent(**{k: data.get(k, getattr(PerfEvent("", 0), k)) for k in PerfEvent.__dataclass_fields__}))
            except Exception:
                continue
            if len(events) >= limit:
                break
    if not events:
        return "暂时没有性能记录。先执行几个电脑任务再查看。"
    lines = []
    for e in events[-limit:]:
        extras = []
        if e.route:
            extras.append(f"route={e.route}")
        if e.api_calls:
            extras.append(f"API={e.api_calls}")
        if e.tool_calls:
            extras.append(f"tools={e.tool_calls}")
        suffix = (" | " + ", ".join(extras)) if extras else ""
        lines.append(f"{e.stage}: {e.elapsed_ms}ms{suffix}")
    return "最近性能记录：\n" + "\n".join(lines)
