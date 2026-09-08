from __future__ import annotations

import os
import subprocess

import psutil

from ..action_log import record


def system_status() -> dict[str, object]:
    root = os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
    disk = psutil.disk_usage(root)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_gb": round(psutil.virtual_memory().available / 1024**3, 2),
        "disk_free_gb": round(disk.free / 1024**3, 2),
        "disk_percent": disk.percent,
    }


def set_system_volume(percent: int) -> str:
    if os.name != "nt":
        raise RuntimeError("音量控制仅支持 Windows。")
    percent = max(0, min(100, int(percent)))
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    device = AudioUtilities.GetSpeakers()
    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    volume = cast(interface, POINTER(IAudioEndpointVolume))
    volume.SetMasterVolumeLevelScalar(percent / 100.0, None)
    record("set_system_volume", {"percent": percent})
    return f"系统音量已设置为 {percent}%"


def run_command(command: str, confirmed: bool = False, timeout: int = 30) -> str:
    if not confirmed:
        return f"CONFIRM_REQUIRED: 执行命令可能修改系统。请向用户确认后再次调用并设置 confirmed=true。命令：{command}"
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    output = (proc.stdout + "\n" + proc.stderr).strip()[:12000]
    record("run_command", {"command": command}, status="ok" if proc.returncode == 0 else "error", detail=output[:1000])
    return f"exit={proc.returncode}\n{output}"
