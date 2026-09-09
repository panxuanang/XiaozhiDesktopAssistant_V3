from __future__ import annotations

import time
from typing import Any

from .fast_router import try_fast_route
from .performance import (
    api_call_count, log_timing, performance_report as _performance_report,
    reset_api_counter, restore_api_counter,
)
from .speech_policy import compact_reply


def _install_performance_shims() -> None:
    """Patch only legacy action functions, lazily.

    Normal fast-lane commands should not import pandas/python-docx/pychrome merely to
    open Notepad or change volume.  These shims are therefore installed only after
    the deterministic fast router misses and the legacy workmate path is actually
    needed.
    """
    try:
        from .tools import browser as browser_tools
        from . import fast_browser
        browser_tools.browser_open = fast_browser.quick_open
        browser_tools.browser_search = fast_browser.quick_search
    except Exception:
        pass
    try:
        from .tools import office as office_tools
        from .fast_office import write_material_one_call
        office_tools.write_material = write_material_one_call
    except Exception:
        pass


def workmate(instruction: str) -> str:
    """Single Xiaozhi-facing execution entry.

    Order: zero-API deterministic route -> local-first workmate -> generic AI only as
    workmate's final fallback.  Heavy Office/research modules are not imported for a
    fast command.
    """
    started = time.perf_counter()
    route = "workmate"
    api_token = reset_api_counter()
    try:
        fast = try_fast_route(instruction)
        if fast is not None:
            route, raw = fast
        else:
            # Heavy office/research imports live behind this branch.
            from .tools import workmate as workmate_tools
            _install_performance_shims()
            raw = workmate_tools.workmate(instruction)
            route = "local_workmate"
        return compact_reply(instruction, raw)
    finally:
        log_timing(
            "xiaozhi_workmate",
            (time.perf_counter() - started) * 1000,
            route=route,
            api_calls=api_call_count(),
            tool_calls=1,
            detail=instruction[:180],
        )
        restore_api_counter(api_token)


def task_center(action: str = "list", task_id: str = "", job_id: str = "", limit: int = 30) -> Any:
    from .tools import workmate as workmate_tools
    return workmate_tools.task_center(action=action, task_id=task_id, job_id=job_id, limit=limit)


def search_work_files(query: str, limit: int = 20) -> list[dict[str, object]]:
    from .tools import workmate as workmate_tools
    return workmate_tools.search_work_files(query=query, limit=limit)


def desktop_agent(instruction: str, max_steps: int = 4) -> str:
    """Developer/last-resort generic agent; not exposed in normal MCP mode."""
    from .agent import desktop_agent as _desktop_agent
    return compact_reply(instruction, _desktop_agent(instruction, max_steps=max_steps))


def performance_report(limit: int = 12) -> str:
    return _performance_report(limit=limit)
