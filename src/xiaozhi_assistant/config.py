from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import config_path


@dataclass
class AISettings:
    provider: str = "自定义兼容API"
    base_url: str = ""
    model: str = ""
    api_mode: str = "auto"  # auto | responses | chat
    timeout_seconds: int = 120
    temperature: float = 0.3


@dataclass
class ModuleSettings:
    files: bool = True
    office: bool = True
    ppt: bool = True
    pdf: bool = True
    browser: bool = True
    windows: bool = True
    wechat: bool = True
    workmate: bool = True
    scheduler: bool = True
    indexer: bool = True
    ocr: bool = True
    screen: bool = True
    system: bool = True
    # Default to a compact MCP surface to avoid sending dozens of low-level tool schemas.
    expose_low_level_tools: bool = False


@dataclass
class SafetySettings:
    require_send_confirmation: bool = True
    require_delete_confirmation: bool = True
    require_command_confirmation: bool = True
    scheduled_send_requires_explicit_authorization: bool = True
    max_webpage_chars_for_ai: int = 24000
    max_file_chars_for_ai: int = 30000


@dataclass
class LocalFirstSettings:
    enabled: bool = True
    local_summary_enabled: bool = True
    prefer_local_excel: bool = True
    prefer_local_file_search: bool = True
    ai_for_writing: bool = True
    ai_for_ambiguous_tasks: bool = True
    show_api_usage_in_result: bool = True


@dataclass
class WorkMateSettings:
    enabled: bool = True
    priority_contacts: str = "老板,王总,李经理"
    work_roots: str = "桌面;下载;文档"
    wechat_file_roots: str = "文档/WeChat Files;下载"
    auto_scan_wechat: bool = False
    scan_interval_minutes: int = 10
    default_delivery_contact: str = ""
    default_report_dir: str = "桌面/小智工作结果"
    task_keywords: str = "处理,整理,汇总,分析,修改,补充,发我,给我,下午,明天,附件,表格,文件,报告,周报,日报"


@dataclass
class AppSettings:
    xiaozhi_endpoint: str = ""
    auto_connect: bool = True
    auto_start_windows: bool = False
    start_minimized: bool = False
    update_manifest_url: str = ""
    ai: AISettings = field(default_factory=AISettings)
    modules: ModuleSettings = field(default_factory=ModuleSettings)
    safety: SafetySettings = field(default_factory=SafetySettings)
    local_first: LocalFirstSettings = field(default_factory=LocalFirstSettings)
    workmate: WorkMateSettings = field(default_factory=WorkMateSettings)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppSettings":
        def _filtered(dc_cls, values: dict[str, Any]):
            allowed = {f.name for f in __import__("dataclasses").fields(dc_cls)}
            return dc_cls(**{k: v for k, v in (values or {}).items() if k in allowed})

        return cls(
            xiaozhi_endpoint=data.get("xiaozhi_endpoint", ""),
            auto_connect=bool(data.get("auto_connect", True)),
            auto_start_windows=bool(data.get("auto_start_windows", False)),
            start_minimized=bool(data.get("start_minimized", False)),
            update_manifest_url=data.get("update_manifest_url", ""),
            ai=_filtered(AISettings, data.get("ai", {})),
            modules=_filtered(ModuleSettings, data.get("modules", {})),
            safety=_filtered(SafetySettings, data.get("safety", {})),
            local_first=_filtered(LocalFirstSettings, data.get("local_first", {})),
            workmate=_filtered(WorkMateSettings, data.get("workmate", {})),
        )


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or config_path()
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppSettings.from_dict(data)
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# Presets intentionally leave the model blank. Model IDs change faster than the desktop client;
# the user can paste the exact model/deployment name from their provider console.
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": ""},
    "DeepSeek": {"base_url": "https://api.deepseek.com", "model": ""},
    "豆包方舟": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": ""},
    "自定义兼容API": {"base_url": "", "model": ""},
}
