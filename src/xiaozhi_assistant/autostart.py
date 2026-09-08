from __future__ import annotations

import os
import sys

APP_RUN_NAME = "XiaozhiDesktopAssistant"


def set_windows_autostart(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            command = f'"{sys.executable}" --minimized'
            winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, command)
        else:
            try:
                winreg.DeleteValue(key, APP_RUN_NAME)
            except FileNotFoundError:
                pass
