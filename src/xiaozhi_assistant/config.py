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
    # V0.4: a failed provider should not freeze a spoken task for two minutes.
    # Long writing/research jobs can still pass an explicit larger timeout.
    timeout_seconds: int = 45
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
    # Developer compatibility mode. Normal users should keep this off so the
    # Xiaozhi backend sees a very small MCP surface instead of dozens of schemas.
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
    # Internal execution details are kept in logs; do not make TTS read them.
    show_api_usage_in_result: bool = False


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
class PerformanceSettings:
    # Small deterministic commands should never touch the user's AI API.
    fast_route_enabled: bool = True
    # Generic desktop agent is the final fallback only. Its API call gets a much
    # smaller timeout than document writing/research.
    agent_timeout_seconds: int = 25
    agent_max_steps: int = 4
    agent_max_tools: int = 16
    # Browser navigation returns after launch/navigation is issued. DOM-reading
    # operations can wait later when the user actually asks to read the page.
    browser_start_timeout_seconds: float = 5.0
    browser_background_warmup: bool = False
    # WeChat uses short adaptive waits and UIA verification rather than long
    # fixed sleeps. These are conservative defaults for normal Windows PCs.
    wechat_search_timeout_seconds: float = 1.2
    wechat_verify_timeout_seconds: float = 1.4
    wechat_poll_interval_seconds: float = 0.10
    # Persist timing records in the existing action database for diagnostics.
    timing_log_enabled: bool = True


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
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)

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
            performance=_filtered(PerformanceSettings, data.get("performance", {})),
        )


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or config_path()
    if not path.exists():
        return AppSettings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        settings = AppSettings.from_dict(data)
        # Older builds persisted 120s. Preserve custom lower values but migrate the
        # legacy long timeout so an existing installation benefits immediately.
        if settings.ai.timeout_seconds > 60:
            settings.ai.timeout_seconds = 45
        return settings
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# Presets intentionally leave the model blank. Model IDs change faster than the
# desktop client; paste the exact model/deployment name from the provider console.
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": ""},
    "DeepSeek": {"base_url": "https://api.deepseek.com", "model": ""},
    "豆包方舟": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": ""},
    "自定义兼容API": {"base_url": "", "model": ""},
}
