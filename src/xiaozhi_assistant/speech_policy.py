from __future__ import annotations

import json
import re
from typing import Any

# Computer-side reply policy. The goal is to keep Xiaozhi as an execution-oriented
# workmate: actions are acknowledged briefly; content is spoken only when requested.
_DETAIL_WORDS = (
    "总结", "概括", "主要讲", "说什么", "什么内容", "内容是什么", "分析", "解释",
    "详细", "汇报", "告诉我", "结果怎么样", "处理结果", "哪些", "列出", "对比",
    "原因", "为什么", "评价", "介绍", "读一下", "念一下", "看看内容",
)
_ACTION_WORDS = (
    "打开", "访问", "关闭", "最小化", "最大化", "恢复", "点击", "点开", "输入",
    "填写", "搜索", "搜一下", "截图", "移动", "复制", "重命名", "保存", "发送",
    "发给", "运行", "启动", "设置", "调到", "处理", "拆分", "拆开", "合并", "计算",
    "汇总", "筛选", "标记", "修改", "整理",
)
_CONFIRM_WORDS = ("确认", "是否发送", "是否确认", "需要确认", "confirm_required", "等待确认")
_ERROR_WORDS = ("失败", "错误", "异常", "未找到", "找不到", "无法", "请先", "安全阻止")


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def strip_internal_notes(text: str) -> str:
    """Remove implementation notes that are useful in logs but noisy in TTS."""
    # Clean accidental rich-citation wrappers that may exist in legacy string templates.
    text = text.replace("cite", "").replace("", "")
    text = re.sub(r"\n?\[执行方式：[^\]]+\]", "", text)
    text = re.sub(r"\n?任务ID[：:]?\s*[A-Za-z0-9_-]+", "", text, flags=re.I)
    text = re.sub(r"\n?pending_job[=:]\s*[A-Za-z0-9_-]+", "", text, flags=re.I)
    return text.strip()


def wants_details(instruction: str) -> bool:
    text = instruction.strip().lower()
    return any(word.lower() in text for word in _DETAIL_WORDS)


def is_action_only(instruction: str) -> bool:
    text = instruction.strip().lower()
    return any(word.lower() in text for word in _ACTION_WORDS) and not wants_details(text)


def _first_sentence(text: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    parts = re.split(r"(?<=[。！？!?])\s*", text)
    out = ""
    for part in parts:
        if not part:
            continue
        if len(out) + len(part) > max_chars:
            break
        out += part
        if len(out) >= max_chars // 2:
            break
    if out:
        return out.strip()
    return text[:max_chars].rstrip("，,；;：: ") + "……"


def _action_ack(instruction: str, raw: str) -> str:
    text = instruction.lower()
    # Confirmation/safety information must never be hidden.
    lower_raw = raw.lower()
    if any(word in lower_raw for word in _CONFIRM_WORDS):
        return _first_sentence(raw, 240)
    if any(word in raw for word in _ERROR_WORDS):
        return _first_sentence(raw, 260)

    if any(k in text for k in ("网页", "网站", "http://", "https://", "百度", "必应", "谷歌", "浏览器")):
        if any(k in text for k in ("搜索", "搜一下", "查一下")):
            return "已搜索。"
        if any(k in text for k in ("打开", "访问", "浏览")):
            return "已打开。"
    if "截图" in text:
        return "截图完成。"
    if any(k in text for k in ("最小化", "最大化", "恢复", "关闭")):
        return "已完成。"
    if any(k in text for k in ("excel", "表格", "xlsx", "拆分", "拆开", "合并", "汇总", "计算", "筛选", "标记")):
        return "处理好了。"
    if any(k in text for k in ("word", "文档", "pdf", "ppt", "文件")) and any(k in text for k in ("创建", "生成", "保存", "移动", "复制", "处理", "修改")):
        return "处理好了。"
    if any(k in text for k in ("微信", "发送", "发给")):
        return "已处理。"
    if any(k in text for k in ("打开", "启动", "运行")):
        return "已打开。"
    return "已完成。"


def compact_reply(instruction: str, value: Any, *, detail_limit: int = 650) -> str:
    """Return the text that is safe and useful for Xiaozhi to speak.

    Full execution details should be kept in local logs/task DB. This function is
    deliberately lossy for action-only commands so TTS does not narrate page/file/UI
    contents unless the user asked for them.
    """
    raw = strip_internal_notes(_text(value))
    if not raw:
        return "已完成。"

    lower_raw = raw.lower()
    if any(word in lower_raw for word in _CONFIRM_WORDS) or any(word in raw for word in _ERROR_WORDS):
        return _first_sentence(raw, 280)

    if is_action_only(instruction):
        return _action_ack(instruction, raw)

    if wants_details(instruction):
        limit = 1400 if "详细" in instruction else detail_limit
        return _first_sentence(raw, limit)

    # Research/report tasks should acknowledge completion rather than read the report aloud
    # unless the user explicitly asked for a verbal summary.
    text = instruction.lower()
    if any(k in text for k in ("报告", "调研")) and any(k in raw for k in ("报告", "来源", "report")):
        return _first_sentence(raw, 220)

    return _first_sentence(raw, 220)


def compact_tool_result(tool_name: str, value: Any) -> str:
    """Compact internal tool messages without starving content-reading tools."""
    raw = _text(value)
    content_tools = {
        "read_word_document", "excel_profile", "excel_local_analysis", "excel_preview",
        "read_pdf", "ocr_scanned_pdf", "read_presentation", "browser_current_page",
        "local_summarize_current_webpage", "ui_tree", "read_wechat_contact",
        "find_recent_wechat_attachments", "web_research_report",
    }
    limit = 24000 if tool_name in content_tools else 5000
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "...[截断]"
