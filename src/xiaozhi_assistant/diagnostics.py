from __future__ import annotations

import os
import platform
from pathlib import Path

from .config import load_settings
from .paths import file_index_db_path, work_db_path
from .secrets_store import get_api_key


def run_diagnostics() -> list[tuple[str, bool, str]]:
    settings = load_settings()
    out: list[tuple[str, bool, str]] = []
    out.append(("操作系统", os.name == "nt", platform.platform()))
    out.append(("小智 MCP 地址", settings.xiaozhi_endpoint.startswith(("ws://", "wss://")), "已配置" if settings.xiaozhi_endpoint else "未配置"))
    api_configured = bool(get_api_key() and settings.ai.base_url and settings.ai.model)
    out.append(("AI API（可选）", True, "已配置，可用于写作/模糊任务" if api_configured else "未配置；本地功能仍可使用"))
    out.append(("本地优先", bool(settings.local_first.enabled), "开启" if settings.local_first.enabled else "关闭"))
    out.append(("定时任务数据库", True, str(work_db_path())))
    out.append(("文件索引", True, str(file_index_db_path()) if file_index_db_path().exists() else "尚未建立，可在“打工人搭子”页建立"))
    try:
        from .tools.browser import _find_browser_executable
        browser = _find_browser_executable()
        out.append(("Chrome/Edge", True, browser))
    except Exception as exc:
        out.append(("Chrome/Edge", False, str(exc)))
    try:
        import docx, pandas, openpyxl, pypdf, pptx  # noqa: F401
        out.append(("Office/PDF/PPT 组件", True, "正常"))
    except Exception as exc:
        out.append(("Office/PDF/PPT 组件", False, str(exc)))
    try:
        from rapidocr_onnxruntime import RapidOCR  # noqa: F401
        out.append(("本地 OCR", True, "RapidOCR 可用"))
    except Exception as exc:
        out.append(("本地 OCR", False, str(exc)))
    if os.name == "nt":
        try:
            from pywinauto import Desktop  # noqa: F401
            out.append(("Windows UI Automation", True, "可用"))
        except Exception as exc:
            out.append(("Windows UI Automation", False, str(exc)))
        # WeChat is operational only when the user is logged in and the window is available.
        try:
            from pywinauto import Desktop
            titles = [w.window_text() for w in Desktop(backend="uia").windows()]
            found = any("微信" in t or "WeChat" in t for t in titles)
            out.append(("微信客户端", found, "已检测到窗口" if found else "未检测到微信窗口/可能未登录"))
        except Exception as exc:
            out.append(("微信客户端", False, str(exc)))
    return out
