from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from . import fast_browser
from .config import load_settings
from .speech_policy import wants_details
from .tools import files, system, wechat, windows


KNOWN_SITES = {
    "百度": "https://www.baidu.com",
    "必应": "https://www.bing.com",
    "bing": "https://www.bing.com",
    "谷歌": "https://www.google.com",
    "google": "https://www.google.com",
    "淘宝": "https://www.taobao.com",
    "京东": "https://www.jd.com",
    "知乎": "https://www.zhihu.com",
    "微博": "https://weibo.com",
    "小红书": "https://www.xiaohongshu.com",
    "哔哩哔哩": "https://www.bilibili.com",
    "b站": "https://www.bilibili.com",
}

APP_ALIASES = {
    "记事本": "notepad.exe",
    "计算器": "calc.exe",
    "画图": "mspaint.exe",
    "任务管理器": "taskmgr.exe",
    "资源管理器": "explorer.exe",
    "文件资源管理器": "explorer.exe",
    "命令提示符": "cmd.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "excel": "excel.exe",
    "表格": "excel.exe",
    "word": "winword.exe",
    "ppt": "powerpnt.exe",
    "powerpoint": "powerpnt.exe",
}

_CONFIRM_WORDS = ("确认", "确认发送", "发吧", "发送吧", "到点发", "不用再确认")
_FILE_EXTS = "xlsx|xlsm|xls|docx|pdf|pptx|csv|txt|zip|png|jpg|jpeg"


def _contact(text: str) -> str:
    if "文件传输助手" in text or any(k in text for k in ("发我微信", "发到我微信", "微信发给我", "微信发我")):
        return "文件传输助手"
    cfg = load_settings()
    names = [x.strip() for x in cfg.workmate.priority_contacts.replace("，", ",").split(",") if x.strip()]
    for name in names:
        if name in text:
            return name
    m = re.search(r"(?:给|发给|微信给)([\u4e00-\u9fffA-Za-z0-9_-]{2,20}?)(?:发(?:微信|消息|文件)?|发送|微信|说|，|,|\s)", text)
    return m.group(1) if m else (cfg.workmate.default_delivery_contact or "")


def _resolve_spoken_file(text: str) -> str:
    # Full Windows path.
    m = re.search(rf"[A-Za-z]:\\[^\n\"']+?\.(?:{_FILE_EXTS})", text, flags=re.I)
    if m:
        p = Path(m.group(0))
        if p.exists():
            return str(p)
    # Desktop/Downloads/Documents spoken path, including '桌面的xx.xlsx'.
    m = re.search(rf"(桌面|下载|文档)(?:的|[/\\])?([^，。\n]+?\.(?:{_FILE_EXTS}))", text, flags=re.I)
    if m:
        p = files.resolve_user_path(f"{m.group(1)}/{m.group(2).strip()}")
        if p.exists():
            return str(p)
    # Bare filename: check common work roots deterministically.
    m = re.search(rf"([^\\/\s，。]+\.(?:{_FILE_EXTS}))", text, flags=re.I)
    if m:
        name = m.group(1)
        for root in ("桌面", "下载", "文档"):
            p = files.resolve_user_path(f"{root}/{name}")
            if p.exists():
                return str(p)
    return ""


def _browser_search(text: str) -> str | None:
    if wants_details(text) or any(k in text for k in ("报告", "调研", "多个来源", "几个来源", "整理成")):
        return None
    if not any(k in text for k in ("百度搜", "必应搜", "谷歌搜", "网页搜", "浏览器搜", "搜索一下", "搜一下")):
        return None
    engine = "baidu" if "百度" in text else ("google" if "谷歌" in text else "bing")
    q = re.sub(r"(小智|帮我|请|在浏览器|浏览器|网页|百度|必应|谷歌|搜索一下|搜一下|搜索|搜)", " ", text, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip(" ，,。")
    if not q:
        return None
    return fast_browser.quick_search(q, engine=engine)


def _browser_open(text: str) -> str | None:
    if wants_details(text):
        return None
    if not any(k in text for k in ("打开", "访问", "浏览")):
        return None
    lower = text.lower()
    # Opening a browser itself should be instant and keep the same DevTools profile.
    if any(k in lower for k in ("打开浏览器", "启动浏览器", "打开chrome", "启动chrome", "打开edge", "启动edge")):
        return fast_browser.quick_open("about:blank")
    m = re.search(r"https?://[^\s，。]+", text, flags=re.I)
    if m:
        return fast_browser.quick_open(m.group(0))
    for name, url in KNOWN_SITES.items():
        if name.lower() in lower:
            return fast_browser.quick_open(url)
    domain = re.search(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s，。]*)?", lower)
    if domain:
        return fast_browser.quick_open(domain.group(0))
    return None


def _wechat_prepare(text: str) -> str | None:
    if not ("微信" in text or "文件传输助手" in text or "发给" in text):
        return None
    # Confirmation must go through workmate so it can also confirm scheduled jobs.
    if any(k in text for k in _CONFIRM_WORDS):
        return None
    if not any(k in text for k in ("发", "发送")):
        return None
    contact = _contact(text)
    if not contact:
        return None
    file_path = _resolve_spoken_file(text)
    if file_path:
        caption = ""
        m = re.search(r"(?:配文|顺便说|并说|再说)[：:]?(.{2,180})", text)
        if m:
            caption = m.group(1).strip()
        return wechat.prepare_wechat_file(contact, file_path, caption)
    # Text message: require an explicit message tail, otherwise do not guess.
    m = re.search(r"(?:说|内容是|消息是|发一句|发消息)[：:]?(.{1,500})", text)
    if m:
        return wechat.prepare_wechat_message(contact, m.group(1).strip())
    return None



def _wechat_open_contact(text: str) -> str | None:
    if "微信" not in text or wants_details(text) or any(k in text for k in ("发", "发送")):
        return None
    if not any(k in text for k in ("打开", "找到", "搜索", "进入")):
        return None
    # Examples: 打开微信里的张三 / 微信里找到张三 / 进入张三的微信会话
    patterns = [
        r"(?:打开|找到|搜索|进入)(?:微信(?:里|里的|中)?|)([\u4e00-\u9fffA-Za-z0-9_-]{2,20})(?:的)?(?:聊天|会话|微信)?",
        r"微信(?:里|里的|中)(?:打开|找到|搜索|进入)?([\u4e00-\u9fffA-Za-z0-9_-]{2,20})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            if name and name not in {"微信", "联系人", "聊天", "会话"}:
                return wechat.open_wechat_contact(name)
    return None


def _uia_click(text: str) -> str | None:
    if not any(k in text for k in ("点击", "点一下", "点开")):
        return None
    # Deterministic form: 在<窗口>里点击<控件>. Without an explicit window name
    # we do not guess which application should receive the click.
    m = re.search(r"(?:在|到)([^，。]{1,24}?)(?:里|中|窗口).*?(?:点击|点一下|点开)[‘“\"']?([^’”\"'，。]{1,30})", text)
    if not m:
        return None
    window_name = m.group(1).strip()
    control_name = m.group(2).strip()
    if window_name and control_name:
        return windows.ui_click(window_name, control_name)
    return None

def _window_action(text: str) -> str | None:
    actions = {"最小化": "minimize", "最大化": "maximize", "恢复": "restore"}
    for zh, action in actions.items():
        if zh not in text:
            continue
        title = re.sub(r"(帮我|请|小智|把|将|窗口|一下|最小化|最大化|恢复)", " ", text).strip(" ，,。")
        if title:
            return windows.window_action(title, action)
    return None


def _volume(text: str) -> str | None:
    if "音量" not in text:
        return None
    m = re.search(r"(\d{1,3})\s*%?", text)
    if m and any(k in text for k in ("调", "设", "设置", "改成", "到")):
        return system.set_system_volume(int(m.group(1)))
    return None



def _destination_path(text: str) -> str:
    m = re.search(r"(?:到|至|放到|移到|复制到)\s*([A-Za-z]:\\[^，。\n\"]+)", text)
    if m:
        return m.group(1).strip()
    for alias in ("桌面", "下载", "文档"):
        if re.search(rf"(?:到|至|放到|移到|复制到).{{0,3}}{alias}", text):
            return str(files.resolve_user_path(alias))
    return ""


def _file_move_copy(text: str) -> str | None:
    if not any(k in text for k in ("移动", "移到", "放到", "复制", "复制到")):
        return None
    source = _resolve_spoken_file(text)
    destination = _destination_path(text)
    if not source or not destination:
        return None
    if "复制" in text:
        return files.copy_path(source, destination, overwrite=False)
    return files.move_path(source, destination, overwrite=False)

def _open_local(text: str) -> str | None:
    if not any(k in text for k in ("打开", "启动", "运行")):
        return None
    if any(k in text for k in ("网页", "网站", "http://", "https://")):
        return None
    if "微信" in text and not wants_details(text):
        return wechat.activate_wechat()
    fp = _resolve_spoken_file(text)
    if fp:
        return windows.open_program(fp)
    for name, exe in APP_ALIASES.items():
        if name.lower() in text.lower():
            return windows.open_program(exe)
    return None


def try_fast_route(instruction: str) -> tuple[str, str] | None:
    """Return (route_name, result) for deterministic zero-API commands."""
    cfg = load_settings()
    if not cfg.performance.fast_route_enabled:
        return None
    text = instruction.strip()
    if not text:
        return None

    routes: tuple[tuple[str, Callable[[str], str | None]], ...] = (
        ("wechat_prepare", _wechat_prepare),
        ("browser_search", _browser_search),
        ("browser_open", _browser_open),
        ("wechat_open_contact", _wechat_open_contact),
        ("uia_click", _uia_click),
        ("window_action", _window_action),
        ("volume", _volume),
        ("file_move_copy", _file_move_copy),
        ("open_local", _open_local),
    )
    if "截图" in text and "微信" not in text and not wants_details(text):
        from .tools import screen
        return "screenshot", screen.take_screenshot()
    for route_name, route in routes:
        result = route(text)
        if result is not None:
            return route_name, result
    return None
