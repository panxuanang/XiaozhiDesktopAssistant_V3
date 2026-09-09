from __future__ import annotations

import re

from .agent import desktop_agent as _desktop_agent
from .speech_policy import compact_reply
from .tools import browser
from .tools import workmate as workmate_tools

_KNOWN_SITES = {
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


def _simple_browser_open(instruction: str) -> str | None:
    text = instruction.strip()
    if not any(k in text for k in ("打开", "访问", "浏览")):
        return None
    # Explicit URL.
    match = re.search(r"https?://[^\s，。]+", text, flags=re.I)
    if match:
        return browser.browser_open(match.group(0))
    # Common spoken site names. This avoids sending simple navigation through an AI agent.
    lower = text.lower()
    for name, url in _KNOWN_SITES.items():
        if name.lower() in lower:
            return browser.browser_open(url)
    # A spoken domain such as example.com.
    domain = re.search(r"\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s，。]*)?", lower)
    if domain:
        return browser.browser_open(domain.group(0))
    return None


def workmate(instruction: str) -> str:
    """Xiaozhi-facing high-level entry with computer-side concise speech policy."""
    raw = _simple_browser_open(instruction)
    if raw is None:
        raw = workmate_tools.workmate(instruction)
    return compact_reply(instruction, raw)


def desktop_agent(instruction: str, max_steps: int = 10) -> str:
    """Developer-mode fallback with the same concise speech policy."""
    return compact_reply(instruction, _desktop_agent(instruction, max_steps=max_steps))
