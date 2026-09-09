from __future__ import annotations

import os
import subprocess
import threading
from urllib.parse import quote_plus

from .action_log import record
from .paths import browser_profile_dir


def _normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith(("about:", "chrome:", "edge:")):
        return url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _launch_debug_browser(url: str) -> None:
    # Import lazily: ordinary non-browser tasks should not pay pychrome import/startup cost.
    from .tools import browser

    exe = browser._find_browser_executable()  # intentionally reuse the project's browser discovery
    flags = [
        exe,
        f"--remote-debugging-port={browser.DEBUG_PORT}",
        f"--user-data-dir={browser_profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        url,
    ]
    if os.name == "nt":
        subprocess.Popen(flags, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def quick_open(url: str) -> str:
    """Open/navigate without waiting for page load. No AI call.

    If the DevTools browser is already alive, create a tab immediately. If it is
    cold, launch the same dedicated debug profile with the requested URL and
    return at once; later DOM operations can wait for DevTools only when needed.
    """
    url = _normalize_url(url)
    from .tools import browser

    if browser._port_open():
        try:
            b = browser.ensure_browser()  # fast when port is already open
            b.new_tab(url)
            record("browser_quick_open", {"url": url, "mode": "devtools-warm"})
            return f"已打开：{url}"
        except Exception:
            pass
    _launch_debug_browser(url)
    record("browser_quick_open", {"url": url, "mode": "devtools-cold-async"})
    return f"已打开：{url}"


def quick_search(query: str, engine: str = "bing") -> str:
    engines = {
        "bing": "https://www.bing.com/search?q=",
        "baidu": "https://www.baidu.com/s?wd=",
        "google": "https://www.google.com/search?q=",
    }
    url = engines.get(engine.lower(), engines["bing"]) + quote_plus(query)
    return quick_open(url)


def warmup_async() -> None:
    """Optional background warm-up; never blocks MCP startup."""
    def _worker() -> None:
        try:
            from .tools import browser
            if not browser._port_open():
                _launch_debug_browser("about:blank")
        except Exception:
            pass

    threading.Thread(target=_worker, name="xiaozhi-browser-warmup", daemon=True).start()
