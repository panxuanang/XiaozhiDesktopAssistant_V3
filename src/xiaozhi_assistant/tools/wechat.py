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
        raise RuntimeError("没有找到微信窗口，请先登录并打开微信。")
    win = candidates[0]
    try:
        win.restore()
    except Exception:
        pass
    win.set_focus()
    time.sleep(0.35)
    return win


def _paste_text(text: str) -> None:
    import pyautogui
    import pyperclip
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")


def open_wechat_contact(contact: str) -> str:
    import pyautogui
    _activate_wechat()
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.35)
    _paste_text(contact)
    time.sleep(0.8)
    pyautogui.press("enter")
    time.sleep(0.6)
    record("open_wechat_contact", {"contact": contact})
    return f"已打开微信联系人/会话：{contact}"


def read_wechat_ui(max_nodes: int = 300) -> str:
    win = _activate_wechat()
    lines = []
    for ctrl in win.descendants()[:max_nodes]:
        try:
            text = ctrl.window_text().strip()
            if text:
                lines.append(text)
        except Exception:
            pass
    # De-duplicate consecutive labels without losing order.
    clean: list[str] = []
    for line in lines:
        if not clean or line != clean[-1]:
            clean.append(line)
    return "\n".join(clean)[-24000:]


def read_wechat_contact(contact: str, max_nodes: int = 320) -> str:
    open_wechat_contact(contact)
    return read_wechat_ui(max_nodes=max_nodes)


def scan_priority_contacts(contacts: str = "") -> list[dict[str, object]]:
    """Read configured contacts through UIA and locally flag task-like messages.

    This intentionally avoids reverse-engineering WeChat's local database. It may
    bring WeChat to the foreground while scanning.
    """
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
    _pending_path(pid).write_text(json.dumps({"kind": "text", "contact": contact, "message": message, "created_at": time.time()}, ensure_ascii=False), encoding="utf-8")
    record("prepare_wechat_message", {"contact": contact, "message_len": len(message)}, detail=f"pending={pid}")
    return f"CONFIRM_REQUIRED: 准备给【{contact}】发送微信：\n{message}\n\n请向用户确认。用户明确确认后调用 wechat_confirm_send，pending_id={pid}"


def prepare_wechat_file(contact: str, file_path: str, caption: str = "") -> str:
    target = Path(file_path).expanduser().resolve()
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(target)
    pid = uuid.uuid4().hex[:12]
    _pending_path(pid).write_text(json.dumps({"kind": "file", "contact": contact, "file_path": str(target), "message": caption, "created_at": time.time()}, ensure_ascii=False), encoding="utf-8")
    record("prepare_wechat_file", {"contact": contact, "file": str(target)}, detail=f"pending={pid}")
    return f"CONFIRM_REQUIRED: 准备给【{contact}】发送文件【{target.name}】。请向用户确认后调用 wechat_confirm_send，pending_id={pid}"


def _set_file_clipboard(file_path: Path) -> None:
    import win32clipboard
    import win32con
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_HDROP, (str(file_path),))
    finally:
        win32clipboard.CloseClipboard()


def _send_payload(data: dict, verify: bool = True) -> dict[str, object]:
    import pyautogui
    contact = data["contact"]
    message = data.get("message", "")
    open_wechat_contact(contact)
    if data.get("kind") == "file":
        file_path = Path(data["file_path"])
        if not file_path.exists():
            raise FileNotFoundError(file_path)
        _set_file_clipboard(file_path)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.6)
        pyautogui.press("enter")
        if message:
            time.sleep(0.5)
            _paste_text(message)
            pyautogui.press("enter")
        expected = file_path.name
    else:
        _paste_text(message)
        time.sleep(0.2)
        pyautogui.press("enter")
        expected = message[-40:]
    time.sleep(0.7)
    verified = False
    if verify:
        try:
            ui = read_wechat_ui(max_nodes=360)
            verified = bool(expected and expected in ui)
        except Exception:
            verified = False
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
        return f"已发送给【{data['contact']}】，并在微信界面检测到发送内容。"
    return f"已执行发送给【{data['contact']}】，但未能从 UIA 确认发送结果，请查看微信窗口。"


def wechat_send_authorized(contact: str, message: str = "", file_path: str = "", authorization_note: str = "") -> str:
    """Low-level entry used only by an explicitly authorized scheduled job."""
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
