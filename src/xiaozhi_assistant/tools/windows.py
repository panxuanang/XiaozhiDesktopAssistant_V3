from __future__ import annotations

import os
import subprocess
from pathlib import Path

from ..action_log import record


def list_windows() -> list[str]:
    if os.name != "nt":
        return []
    from pywinauto import Desktop
    titles = []
    for win in Desktop(backend="uia").windows():
        try:
            title = win.window_text().strip()
            if title and win.is_visible():
                titles.append(title)
        except Exception:
            pass
    return titles[:100]


def _find_window(title_contains: str):
    from pywinauto import Desktop
    needle = title_contains.lower()
    matches = []
    for win in Desktop(backend="uia").windows():
        try:
            title = win.window_text()
            if needle in title.lower():
                matches.append(win)
        except Exception:
            continue
    if not matches:
        raise RuntimeError(f"没有找到窗口：{title_contains}")
    return matches[0]


def activate_window(title_contains: str) -> str:
    win = _find_window(title_contains)
    win.set_focus()
    record("activate_window", {"title": title_contains})
    return win.window_text()


def window_action(title_contains: str, action: str, confirmed: bool = False) -> str:
    win = _find_window(title_contains)
    action = action.lower()
    if action == "minimize":
        win.minimize()
    elif action == "maximize":
        win.maximize()
    elif action == "restore":
        win.restore()
    elif action == "close":
        if not confirmed:
            return f"CONFIRM_REQUIRED: 关闭窗口可能丢失未保存内容。请确认后再次调用 confirmed=true：{win.window_text()}"
        win.close()
    else:
        raise ValueError("action 必须是 minimize/maximize/restore/close")
    record("window_action", {"title": title_contains, "action": action})
    return f"已执行 {action}: {win.window_text()}"


def move_resize_window(title_contains: str, x: int, y: int, width: int, height: int) -> str:
    win = _find_window(title_contains)
    win.move_window(x=x, y=y, width=width, height=height, repaint=True)
    record("move_resize_window", {"title": title_contains, "x": x, "y": y, "width": width, "height": height})
    return f"已移动/缩放：{win.window_text()}"


def ui_tree(title_contains: str, max_nodes: int = 200) -> list[dict[str, str]]:
    win = _find_window(title_contains)
    nodes = []
    for ctrl in win.descendants()[:max_nodes]:
        try:
            info = ctrl.element_info
            nodes.append({
                "name": ctrl.window_text(),
                "type": str(info.control_type or ""),
                "automation_id": str(info.automation_id or ""),
            })
        except Exception:
            pass
    return nodes


def ui_click(title_contains: str, control_name: str, control_type: str = "") -> str:
    win = _find_window(title_contains)
    kwargs = {"title": control_name}
    if control_type:
        kwargs["control_type"] = control_type
    ctrl = win.child_window(**kwargs)
    ctrl.wait("exists enabled visible ready", timeout=5)
    ctrl.click_input()
    record("ui_click", {"window": title_contains, "control": control_name, "type": control_type})
    return f"已点击：{control_name}"


def open_program(path_or_name: str) -> str:
    if os.name == "nt":
        try:
            os.startfile(path_or_name)  # type: ignore[attr-defined]
        except OSError:
            subprocess.Popen(path_or_name, shell=True)
    else:
        subprocess.Popen([path_or_name])
    record("open_program", {"program": path_or_name})
    return f"已启动：{path_or_name}"
