from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

from ..action_log import record
from ..config import load_settings
from ..local_index import find_recent_files
from ..local_text import looks_like_work_task
from ..paths import pending_dir


def _pending_path(pid: str) -> Path:
    return pending_dir() / f"wechat_{pid}.json"


def _timing() -> tuple[float, float, float]:
    p = load_settings().performance
    return (
        max(0.4, float(p.wechat_search_timeout_seconds)),
        max(0.4, float(p.wechat_verify_timeout_seconds)),
        max(0.05, float(p.wechat_poll_interval_seconds)),
    )


def _activate_wechat() -> object:
    if os.name != "nt":
        raise RuntimeError("微信自动化仅支持 Windows。")
    from pywinauto import Desktop

    candidates = []
    for win in Desktop(backend="uia").windows():
        try:
            title = win.window_text()
            if "微信" in title or "WeChat" in title:
                candidates.append(win)
        except Exception:
            pass
    if not candidates:
        # Try to launch common WeChat/Weixin desktop executables. This happens only
        # when WeChat is not already running, so the extra polling is not paid on
        # normal send/read operations.
        pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        local = Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None
        exe_candidates = [
            pf / "Tencent" / "Weixin" / "Weixin.exe",
            pf / "Tencent" / "WeChat" / "WeChat.exe",
            pf86 / "Tencent" / "WeChat" / "WeChat.exe",
        ]
        if local:
            exe_candidates.extend([
                local / "Tencent" / "Weixin" / "Weixin.exe",
                local / "Tencent" / "WeChat" / "WeChat.exe",
            ])
        launched = False
        for exe in exe_candidates:
            if exe.exists():
                os.startfile(str(exe))  # type: ignore[attr-defined]
                launched = True
                break
        if launched:
            deadline = time.perf_counter() + 4.0
            while time.perf_counter() < deadline and not candidates:
                time.sleep(0.15)
                for win in Desktop(backend="uia").windows():
                    try:
                        title = win.window_text()
                        if "微信" in title or "WeChat" in title:
                            candidates.append(win)
                            break
                    except Exception:
                        pass
        if not candidates:
            raise RuntimeError("没有找到微信窗口，请先登录并打开微信。")
    win = candidates[0]
    try:
        win.restore()
    except Exception:
        pass
    try:
        win.set_focus()
    except Exception:
        pass
    # pywinauto set_focus is synchronous on most machines. Keep only a tiny grace
    # period instead of the old unconditional 350ms sleep.
    time.sleep(0.06)
    return win


def activate_wechat() -> str:
    win = _activate_wechat()
    record("activate_wechat", {})
    try:
        title = win.window_text()
    except Exception:
        title = "微信"
    return f"已激活：{title or '微信'}"


def _paste_text(text: str) -> None:
    import pyautogui
    import pyperclip

    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def _uia_lines(win: object, max_nodes: int = 240) -> list[str]:
    lines: list[str] = []
    try:
        controls = win.descendants()[:max_nodes]
    except Exception:
        controls = []
    for ctrl in controls:
        try:
            text = ctrl.window_text().strip()
            if text and (not lines or text != lines[-1]):
                lines.append(text)
        except Exception:
            pass
    return lines


def _wait_for_text(win: object, expected: str, timeout: float) -> bool:
    if not expected:
        return False
    _, _, poll = _timing()
    deadline = time.perf_counter() + max(0.05, timeout)
    while time.perf_counter() < deadline:
        if expected in "\n".join(_uia_lines(win, max_nodes=220)):
            return True
        time.sleep(poll)
    return False


def _open_wechat_contact_window(contact: str) -> object:
    import pyautogui

    search_timeout, _, _ = _timing()
    win = _activate_wechat()
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.08)
    _paste_text(contact)
    # Give the search field a short head start, then let UIA verification absorb
    # slower PCs. This replaces the old fixed 0.8s + 0.6s sleeps.
    time.sleep(0.18)
    pyautogui.press("enter")
    time.sleep(0.12)
    if not _wait_for_text(win, contact, min(search_timeout, 0.65)):
        # Some WeChat builds need the result list to settle before Enter.
        time.sleep(0.15)
        pyautogui.press("enter")
        _wait_for_text(win, contact, max(0.2, search_timeout - 0.65))
    record("open_wechat_contact", {"contact": contact})
    return win


def open_wechat_contact(contact: str) -> str:
    _open_wechat_contact_window(contact)
    return f"已打开微信联系人/会话：{contact}"


def _focus_message_box(win: object) -> bool:
    """Focus the chat composer using UIA; fall back to a window-relative click.

    The fallback is deliberately relative to the current WeChat window, never a
    fixed screen coordinate, so it survives resolution/window-position changes.
    """
    try:
        wr = win.rectangle()
        candidates = []
        for ctrl in win.descendants()[:240]:
            try:
                info = ctrl.element_info
                ctype = str(info.control_type or "")
                if ctype not in {"Edit", "Document"}:
                    continue
                r = ctrl.rectangle()
                if r.width() < 120 or r.height() < 28:
                    continue
                if r.mid_point().y < wr.top + wr.height() * 0.45:
                    continue
                candidates.append((r.mid_point().y, r.width() * r.height(), ctrl))
            except Exception:
                continue
        if candidates:
            _, _, ctrl = max(candidates, key=lambda x: (x[0], x[1]))
            try:
                ctrl.set_focus()
            except Exception:
                ctrl.click_input()
            return True
    except Exception:
        pass

    try:
        import pyautogui
        r = win.rectangle()
        x = int(r.left + r.width() * 0.70)
        y = int(r.top + r.height() * 0.86)
        pyautogui.click(x, y)
        time.sleep(0.05)
        return True
    except Exception:
        return False


def read_wechat_ui(max_nodes: int = 300) -> str:
    win = _activate_wechat()
    return "\n".join(_uia_lines(win, max_nodes=max_nodes))[-24000:]


def read_wechat_contact(contact: str, max_nodes: int = 320) -> str:
    win = _open_wechat_contact_window(contact)
    return "\n".join(_uia_lines(win, max_nodes=max_nodes))[-24000:]


def scan_priority_contacts(contacts: str = "") -> list[dict[str, object]]:
    cfg = load_settings()
    raw = contacts or cfg.workmate.priority_contacts
    names = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]
    out = []
    for name in names[:20]:
        try:
            text = read_wechat_contact(name)
            tail = text[-5000:]
            out.append({"contact": name, "task_like": looks_like_work_task(tail, cfg.workmate.task_keywords), "text": tail})
        except Exception as exc:
            out.append({"contact": name, "task_like": False, "error": str(exc)})
    record("scan_priority_contacts", {"contacts": names}, detail=f"scanned={len(out)}")
    return out


def find_recent_wechat_attachments(within_hours: int = 72, extensions: str = ".xlsx,.xls,.docx,.pdf,.pptx,.csv,.zip") -> list[dict[str, object]]:
    cfg = load_settings()
    roots = cfg.workmate.wechat_file_roots or "文档/WeChat Files;下载"
    return find_recent_files(roots, extensions=extensions, within_hours=within_hours, limit=50)


def prepare_wechat_message(contact: str, message: str) -> str:
    pid = uuid.uuid4().hex[:12]
    _pending_path(pid).write_text(
        json.dumps({"kind": "text", "contact": contact, "message": message, "created_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    record("prepare_wechat_message", {"contact": contact, "message_len": len(message)}, detail=f"pending={pid}")
    return f"CONFIRM_REQUIRED: 准备给{contact}发送微信：{message}。请向用户确认后发送，pending_id={pid}"


def prepare_wechat_file(contact: str, file_path: str, caption: str = "") -> str:
    target = Path(file_path).expanduser().resolve()
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(target)
    pid = uuid.uuid4().hex[:12]
    _pending_path(pid).write_text(
        json.dumps({"kind": "file", "contact": contact, "file_path": str(target), "message": caption, "created_at": time.time()}, ensure_ascii=False),
        encoding="utf-8",
    )
    record("prepare_wechat_file", {"contact": contact, "file": str(target)}, detail=f"pending={pid}")
    return f"CONFIRM_REQUIRED: 准备给{contact}发送文件{target.name}。请向用户确认后发送，pending_id={pid}"


def _set_file_clipboard(file_path: Path) -> None:
    import win32clipboard
    import win32con

    # Clipboard can transiently be locked by WeChat/Office. Retry briefly instead
    # of immediately failing or adding a long fixed sleep.
    last_exc: Exception | None = None
    for _ in range(5):
        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32con.CF_HDROP, (str(file_path),))
            finally:
                win32clipboard.CloseClipboard()
            return
        except Exception as exc:
            last_exc = exc
            time.sleep(0.05)
    if last_exc:
        raise last_exc


def _send_payload(data: dict, verify: bool = True) -> dict[str, object]:
    import pyautogui

    _, verify_timeout, poll = _timing()
    contact = data["contact"]
    message = data.get("message", "")
    win = _open_wechat_contact_window(contact)
    _focus_message_box(win)

    if data.get("kind") == "file":
        file_path = Path(data["file_path"])
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        _set_file_clipboard(file_path)
        pyautogui.hotkey("ctrl", "v")
        # Wait only until the file preview becomes visible, with a small ceiling.
        if not _wait_for_text(win, file_path.name, min(0.75, verify_timeout)):
            time.sleep(0.12)
        pyautogui.press("enter")
        if message:
            time.sleep(0.12)
            _focus_message_box(win)
            _paste_text(message)
            pyautogui.press("enter")
        expected = file_path.name
    else:
        _paste_text(message)
        time.sleep(0.08)
        pyautogui.press("enter")
        expected = message[-40:]

    verified = False
    if verify and expected:
        deadline = time.perf_counter() + verify_timeout
        while time.perf_counter() < deadline:
            if expected in "\n".join(_uia_lines(win, max_nodes=220)):
                verified = True
                break
            time.sleep(poll)
    return {"contact": contact, "kind": data.get("kind", "text"), "verified": verified, "expected": expected}


def wechat_confirm_send(pending_id: str) -> str:
    path = _pending_path(pending_id)
    if not path.exists():
        raise RuntimeError("确认请求不存在或已过期。")
    data = json.loads(path.read_text(encoding="utf-8"))
    if time.time() - float(data.get("created_at", 0)) > 600:
        path.unlink(missing_ok=True)
        raise RuntimeError("这条待发送微信已超过10分钟，请重新准备。")
    result = _send_payload(data, verify=True)
    path.unlink(missing_ok=True)
    record("wechat_confirm_send", {"contact": data["contact"], "kind": data.get("kind", "text")}, detail=json.dumps(result, ensure_ascii=False))
    if result["verified"]:
        return f"已发送给{data['contact']}，并确认发送成功。"
    return f"已执行发送给{data['contact']}，但未能从微信界面确认结果，请查看微信。"


def wechat_send_authorized(contact: str, message: str = "", file_path: str = "", authorization_note: str = "") -> str:
    if not authorization_note:
        raise RuntimeError("定时发送缺少用户授权记录。")
    data = {"kind": "file" if file_path else "text", "contact": contact, "message": message, "created_at": time.time()}
    if file_path:
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(p)
        data["file_path"] = str(p)
    result = _send_payload(data, verify=True)
    record("wechat_send_authorized", {"contact": contact, "file": file_path}, detail=json.dumps(result, ensure_ascii=False))
    return f"定时发送已执行：{contact}；验证={'成功' if result['verified'] else '未确认'}"


def latest_pending_message() -> dict | None:
    items = sorted(pending_dir().glob("wechat_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not items:
        return None
    data = json.loads(items[0].read_text(encoding="utf-8"))
    if time.time() - float(data.get("created_at", 0)) > 600:
        items[0].unlink(missing_ok=True)
        return None
    data["pending_id"] = items[0].stem.replace("wechat_", "")
    return data
