from __future__ import annotations

import json
import time
from typing import Any, Callable

from .action_log import record
from .config import load_settings
from . import fast_browser
from .performance import log_timing, mark_api_call
from .llm import AIClient
from .local_index import search_index
from .speech_policy import compact_reply, compact_tool_result, is_action_only
from .tools import browser, files, office, pdf_tools, ppt, research, screen, system, wechat, windows
from .tools import workmate as workmate_tools


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False},
        },
    }


TOOLS: dict[str, tuple[Callable[..., Any], dict[str, Any]]] = {
    "search_files": (files.search_files, _schema("search_files", "按文件名搜索本机文件", {"query":{"type":"string"},"root":{"type":"string","default":"桌面"}}, ["query"])),
    "search_work_files": (workmate_tools.search_work_files, _schema("search_work_files", "搜索本地办公文件索引，优先于大范围遍历", {"query":{"type":"string"},"limit":{"type":"integer","default":20}}, ["query"])),
    "list_directory": (files.list_directory, _schema("list_directory", "列出目录内容", {"path":{"type":"string","default":"桌面"}})),
    "move_path": (files.move_path, _schema("move_path", "移动文件或文件夹", {"source":{"type":"string"},"destination":{"type":"string"},"overwrite":{"type":"boolean","default":False}}, ["source","destination"])),
    "copy_path": (files.copy_path, _schema("copy_path", "复制文件或文件夹", {"source":{"type":"string"},"destination":{"type":"string"},"overwrite":{"type":"boolean","default":False}}, ["source","destination"])),
    "create_word_document": (office.create_word_document, _schema("create_word_document", "创建Word文档。模型应先生成完整正文再调用。", {"path":{"type":"string"},"title":{"type":"string"},"content":{"type":"string"},"author":{"type":"string","default":""}}, ["path","title","content"])),
    "read_word_document": (office.read_word_document, _schema("read_word_document", "读取Word正文", {"path":{"type":"string"}}, ["path"])),
    "excel_profile": (office.excel_profile, _schema("excel_profile", "本地统计Excel，返回结构化摘要", {"path":{"type":"string"}}, ["path"])),
    "excel_local_analysis": (office.excel_local_analysis, _schema("excel_local_analysis", "纯本地分析Excel，不调用API", {"path":{"type":"string"},"sheet":{"type":"string","default":""}}, ["path"])),
    "excel_preview": (office.excel_preview, _schema("excel_preview", "预览Excel前若干行", {"path":{"type":"string"},"sheet":{"type":"string","default":""},"rows":{"type":"integer","default":20}}, ["path"])),
    "excel_process_instruction": (office.excel_process_instruction, _schema("excel_process_instruction", "按自然语言处理Excel；常见任务本地规则完成，模糊任务只让AI做规划，执行仍在本地", {"path":{"type":"string"},"instruction":{"type":"string"},"output_path":{"type":"string","default":""},"sheet":{"type":"string","default":""}}, ["path","instruction"])),
    "excel_split_by_column": (office.excel_split_by_column, _schema("excel_split_by_column", "按某列不同值把Excel拆成多个文件或多个Sheet，全程本地", {"path":{"type":"string"},"column":{"type":"string"},"mode":{"type":"string","enum":["files","sheets"],"default":"files"},"output_dir":{"type":"string","default":""},"output_path":{"type":"string","default":""}}, ["path","column"])),
    "excel_batch_process_directory": (office.excel_batch_process_directory, _schema("excel_batch_process_directory", "对文件夹里的Excel重复执行同一处理计划；计划只生成一次", {"input_dir":{"type":"string"},"instruction":{"type":"string"},"output_dir":{"type":"string","default":""},"recursive":{"type":"boolean","default":False}}, ["input_dir","instruction"])),
    "excel_lookup_merge": (office.excel_lookup_merge, _schema("excel_lookup_merge", "两个Excel按键值进行VLOOKUP式匹配合并，全程本地", {"left_path":{"type":"string"},"right_path":{"type":"string"},"left_key":{"type":"string"},"right_key":{"type":"string","default":""},"right_columns":{"type":"string","default":""},"output_path":{"type":"string","default":""}}, ["left_path","right_path","left_key"])),
    "read_pdf": (pdf_tools.read_pdf, _schema("read_pdf", "读取PDF文本", {"path":{"type":"string"},"max_chars":{"type":"integer","default":30000}}, ["path"])),
    "ocr_scanned_pdf": (pdf_tools.ocr_scanned_pdf, _schema("ocr_scanned_pdf", "扫描PDF本地OCR", {"path":{"type":"string"},"max_pages":{"type":"integer","default":30}}, ["path"])),
    "search_pdf": (pdf_tools.search_pdf, _schema("search_pdf", "搜索PDF关键词", {"path":{"type":"string"},"keyword":{"type":"string"}}, ["path","keyword"])),
    "create_presentation": (ppt.create_presentation, _schema("create_presentation", "根据结构化提纲本地生成PPTX", {"path":{"type":"string"},"title":{"type":"string"},"slides_json":{"type":"string"},"subtitle":{"type":"string","default":""}}, ["path","title","slides_json"])),
    "read_presentation": (ppt.read_presentation, _schema("read_presentation", "读取PPT文字", {"path":{"type":"string"}}, ["path"])),
    "browser_open": (fast_browser.quick_open, _schema("browser_open", "只打开网页，不读取、不总结页面内容", {"url":{"type":"string"}}, ["url"])),
    "browser_search": (fast_browser.quick_search, _schema("browser_search", "只执行网页搜索，不自动总结结果", {"query":{"type":"string"},"engine":{"type":"string","enum":["bing","baidu","google"],"default":"bing"}}, ["query"])),
    "web_research_report": (research.web_research_report, _schema("web_research_report", "多来源联网调研：本地收集/提炼网页，可选一次AI综合，生成Word报告", {"topic":{"type":"string"},"source_count":{"type":"integer","default":5},"output_path":{"type":"string","default":""},"engine":{"type":"string","enum":["bing","baidu","google"],"default":"bing"},"use_ai":{"type":"boolean","default":True}}, ["topic"])),
    "browser_current_page": (browser.browser_current_page, _schema("browser_current_page", "读取当前网页DOM正文。只有用户明确要求查看/总结/分析页面内容时才调用。", {"max_chars":{"type":"integer","default":24000}})),
    "local_summarize_current_webpage": (workmate_tools.local_summarize_current_webpage, _schema("local_summarize_current_webpage", "本地提取式总结当前网页，不调用API。只有用户明确要求总结时才调用。", {"max_sentences":{"type":"integer","default":6}})),
    "browser_click_text": (browser.browser_click_text, _schema("browser_click_text", "按可见文字点击网页按钮或链接", {"text":{"type":"string"}}, ["text"])),
    "browser_fill": (browser.browser_fill, _schema("browser_fill", "填写网页输入框", {"field":{"type":"string"},"value":{"type":"string"}}, ["field","value"])),
    "browser_extract_tables": (browser.browser_extract_tables, _schema("browser_extract_tables", "提取网页表格", {})),
    "browser_upload_file": (browser.browser_upload_file, _schema("browser_upload_file", "上传本机文件到网页", {"field":{"type":"string"},"file_path":{"type":"string"}}, ["field","file_path"])),
    "list_windows": (windows.list_windows, _schema("list_windows", "列出Windows窗口", {})),
    "activate_window": (windows.activate_window, _schema("activate_window", "激活窗口", {"title_contains":{"type":"string"}}, ["title_contains"])),
    "window_action": (windows.window_action, _schema("window_action", "最小化/最大化/恢复/关闭窗口。关闭需要确认。", {"title_contains":{"type":"string"},"action":{"type":"string","enum":["minimize","maximize","restore","close"]},"confirmed":{"type":"boolean","default":False}}, ["title_contains","action"])),
    "ui_tree": (windows.ui_tree, _schema("ui_tree", "读取窗口UI Automation控件", {"title_contains":{"type":"string"}}, ["title_contains"])),
    "ui_click": (windows.ui_click, _schema("ui_click", "用UI Automation点击桌面控件", {"title_contains":{"type":"string"},"control_name":{"type":"string"},"control_type":{"type":"string","default":""}}, ["title_contains","control_name"])),
    "open_program": (windows.open_program, _schema("open_program", "启动程序", {"path_or_name":{"type":"string"}}, ["path_or_name"])),
    "prepare_wechat_message": (wechat.prepare_wechat_message, _schema("prepare_wechat_message", "准备微信消息但不发送，必须让用户确认", {"contact":{"type":"string"},"message":{"type":"string"}}, ["contact","message"])),
    "prepare_wechat_file": (wechat.prepare_wechat_file, _schema("prepare_wechat_file", "准备给微信联系人发送文件但不立即发送", {"contact":{"type":"string"},"file_path":{"type":"string"},"caption":{"type":"string","default":""}}, ["contact","file_path"])),
    "wechat_confirm_send": (wechat.wechat_confirm_send, _schema("wechat_confirm_send", "仅当用户明确确认后发送已准备微信", {"pending_id":{"type":"string"}}, ["pending_id"])),
    "read_wechat_contact": (wechat.read_wechat_contact, _schema("read_wechat_contact", "打开并读取指定微信联系人UIA文字", {"contact":{"type":"string"},"max_nodes":{"type":"integer","default":320}}, ["contact"])),
    "find_recent_wechat_attachments": (wechat.find_recent_wechat_attachments, _schema("find_recent_wechat_attachments", "查找近期微信/下载目录里的工作附件", {"within_hours":{"type":"integer","default":72},"extensions":{"type":"string","default":".xlsx,.xls,.docx,.pdf,.pptx,.csv,.zip"}})),
    "schedule_latest_task": (workmate_tools.schedule_latest_task, _schema("schedule_latest_task", "给最新完成任务安排微信定时发送。必须在用户明确确认后 confirmed=true", {"contact":{"type":"string"},"send_at":{"type":"string"},"message":{"type":"string","default":""},"confirmed":{"type":"boolean","default":False}}, ["contact","send_at"])),
    "system_status": (system.system_status, _schema("system_status", "获取电脑状态", {})),
    "set_system_volume": (system.set_system_volume, _schema("set_system_volume", "设置系统音量", {"percent":{"type":"integer","minimum":0,"maximum":100}}, ["percent"])),
    "take_screenshot": (screen.take_screenshot, _schema("take_screenshot", "截屏并保存", {"path":{"type":"string","default":""}})),
    "local_ocr_screen": (screen.local_ocr_screen, _schema("local_ocr_screen", "仅在UIA/DOM不可用时OCR屏幕", {"keyword":{"type":"string","default":""}})),
}

SYSTEM_PROMPT = """你是运行在用户 Windows 电脑上的执行型桌面助手。目标是可靠完成任务，而不是讲解操作过程。
优先级：直接文件/API操作 > 本地结构化计算 > DOM/UI Automation > 快捷键 > 本地OCR > 坐标点击。
尽量减少外部AI调用：你自己已经是当前一次AI调用，所以不要把简单计算再次交给模型；Excel计算必须使用本地工具。

【动作、读取、汇报必须分开】
- 用户只说“打开/点击/搜索/输入/最小化/保存/移动”等动作时，只完成动作。
- 不要因为打开了网页就继续读取网页；不要因为读取了网页就自动总结。
- browser_open 之后，除非用户明确要求“看看内容/总结/分析/说什么”，否则禁止调用 browser_current_page 或总结工具。
- 用户没有要求了解内容时，不要主动描述网页、文件、窗口或控件。

规则：
1. 不编造文件、表格、网页或执行结果；先读取真实数据。
2. Word/PPT 直接生成文件，不要打开Office模拟打字。
3. Excel 常规整理优先 excel_process_instruction / excel_local_analysis；拆表、批处理、匹配合并使用专用本地工具。
4. 单页总结只在用户明确要求总结时使用 local_summarize_current_webpage；需要多来源调研报告时优先 web_research_report。
5. 微信发送必须 prepare 后等待用户确认。定时发送必须在明确确认后 confirmed=true。
6. 删除、支付、下单、管理员命令等高风险动作不自动执行。
7. 动作任务完成后只说一句结果，通常不超过20个汉字；不要复述工具输出。
8. 只有用户明确要求总结、分析、详细说明、汇报结果时才给较完整内容。
9. 失败只说失败原因和下一步，不向用户朗读堆栈或内部调试信息。
"""


# Content tools normally need a model round after execution; pure action tools do not.
_CONTENT_TOOLS = {
    "read_word_document", "excel_profile", "excel_local_analysis", "excel_preview",
    "read_pdf", "ocr_scanned_pdf", "search_pdf", "read_presentation",
    "browser_current_page", "local_summarize_current_webpage", "browser_extract_tables",
    "ui_tree", "read_wechat_contact", "find_recent_wechat_attachments", "web_research_report",
    "system_status",
}

_DOMAIN_TOOLS = {
    "wechat": [
        "prepare_wechat_message", "prepare_wechat_file", "wechat_confirm_send",
        "read_wechat_contact", "find_recent_wechat_attachments", "schedule_latest_task", "search_files",
        "search_work_files", "take_screenshot", "activate_window", "open_program",
    ],
    "browser": [
        "browser_open", "browser_search", "browser_current_page", "local_summarize_current_webpage",
        "browser_click_text", "browser_fill", "browser_extract_tables", "browser_upload_file",
        "web_research_report", "take_screenshot",
    ],
    "excel": [
        "search_files", "search_work_files", "excel_profile", "excel_local_analysis", "excel_preview",
        "excel_process_instruction", "excel_split_by_column", "excel_batch_process_directory",
        "excel_lookup_merge", "create_presentation", "prepare_wechat_file",
    ],
    "document": [
        "search_files", "search_work_files", "create_word_document", "read_word_document",
        "read_pdf", "ocr_scanned_pdf", "search_pdf", "create_presentation", "read_presentation",
        "prepare_wechat_file",
    ],
    "windows": [
        "open_program", "list_windows", "activate_window", "window_action", "ui_tree", "ui_click",
        "system_status", "set_system_volume", "take_screenshot", "local_ocr_screen",
    ],
    "files": [
        "search_files", "search_work_files", "list_directory", "move_path", "copy_path",
        "open_program", "prepare_wechat_file",
    ],
}


def _detect_domains(instruction: str) -> list[str]:
    t = instruction.lower()
    out: list[str] = []
    # Put the primary work domain before delivery/control domains so a capped
    # schema still contains the tools that actually do the work.
    if any(k in t for k in ("excel", "xlsx", "xls", "表格", "销售表", "工作簿", "sheet")):
        out.append("excel")
    if any(k in t for k in ("网页", "网站", "浏览器", "百度", "必应", "谷歌", "http://", "https://", "搜索", "调研")):
        out.append("browser")
    if any(k in t for k in ("word", "docx", "pdf", "ppt", "pptx", "文档", "材料", "报告")):
        out.append("document")
    if any(k in t for k in ("微信", "联系人", "文件传输助手", "发给", "发消息")):
        out.append("wechat")
    if any(k in t for k in ("窗口", "最小化", "最大化", "音量", "截图", "电脑状态", "cpu", "内存", "打开软件", "启动")):
        out.append("windows")
    if any(k in t for k in ("文件", "文件夹", "桌面", "下载", "移动", "复制", "找一下")):
        out.append("files")
    return out or ["windows", "files"]

def _selected_tool_names(instruction: str) -> list[str]:
    cfg = load_settings()
    names: list[str] = []
    for domain in _detect_domains(instruction):
        for name in _DOMAIN_TOOLS[domain]:
            if name in TOOLS and name not in names:
                names.append(name)
    max_tools = max(6, min(int(cfg.performance.agent_max_tools), 24))
    return names[:max_tools]


def _safe_to_finish_without_second_ai(instruction: str, tool_results: list[tuple[str, str]]) -> bool:
    if not is_action_only(instruction) or not tool_results:
        return False
    for name, result in tool_results:
        lower = result.lower()
        if name in _CONTENT_TOOLS:
            return False
        if "confirm_required" in lower or "安全阻止" in result or "工具执行失败" in result:
            return False
    return True


def desktop_agent(instruction: str, max_steps: int | None = None) -> str:
    """Last-resort agent with domain-sized schemas and one-round action completion.

    V0.3 sent every tool schema on every model round and asked the model to speak again
    after a simple tool succeeded. V0.4 selects only the relevant domain tools and returns
    directly for action-only commands, cutting one entire API round in the common case.
    """
    normalized = instruction.strip().lower()
    explicit_wechat_confirm = normalized in {"确认", "确认发送", "发吧", "发送吧", "可以发", "就这样发", "确认发出"} or "确认发送" in normalized
    if explicit_wechat_confirm:
        pending = wechat.latest_pending_message()
        if pending:
            return compact_reply(instruction, wechat.wechat_confirm_send(pending["pending_id"]))

    cfg = load_settings()
    step_limit = max_steps if max_steps is not None else cfg.performance.agent_max_steps
    step_limit = max(1, min(int(step_limit), 8))
    selected_names = _selected_tool_names(instruction)
    tool_specs = [TOOLS[name][1] for name in selected_names]
    ai = AIClient(timeout_seconds=cfg.performance.agent_timeout_seconds, max_retries=0)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    started = time.perf_counter()
    api_calls = 0
    total_tool_calls = 0
    try:
        for _ in range(step_limit):
            api_calls += 1
            mark_api_call()
            response = ai.client.chat.completions.create(
                model=ai.settings.model,
                messages=messages,
                tools=tool_specs,
                tool_choice="auto",
            )
            if not response.choices:
                raise RuntimeError("AI Agent 没有返回结果。")
            msg = response.choices[0].message
            if not msg.tool_calls:
                answer = compact_reply(instruction, msg.content or "任务已结束。")
                record("desktop_agent", {"instruction": instruction, "tools": selected_names, "api_calls": api_calls}, detail=str(answer)[:1000])
                return str(answer)

            messages.append(msg.model_dump(exclude_none=True))
            round_results: list[tuple[str, str]] = []
            for call in msg.tool_calls:
                total_tool_calls += 1
                name = call.function.name
                if name not in TOOLS or name not in selected_names:
                    result = f"未知或当前域未开放的工具：{name}"
                else:
                    func = TOOLS[name][0]
                    try:
                        args = json.loads(call.function.arguments or "{}")
                        if name == "wechat_confirm_send" and not explicit_wechat_confirm:
                            result = "安全阻止：当前用户输入没有明确确认发送微信。请先结束本轮并让用户确认。"
                        elif name == "schedule_latest_task" and args.get("confirmed") and not any(k in normalized for k in ["确认", "直接发", "到点发", "不用再确认", "就这么发"]):
                            result = "安全阻止：定时发送尚未获得明确授权。请先让用户确认。"
                        elif name == "window_action" and args.get("action") == "close" and args.get("confirmed") and "确认" not in normalized:
                            result = "安全阻止：当前用户输入没有明确确认关闭窗口。"
                        else:
                            result = compact_tool_result(name, func(**args))
                    except Exception as exc:
                        result = f"工具执行失败：{type(exc).__name__}: {exc}"
                round_results.append((name, str(result)))
                messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})

            # Confirmation and errors should be spoken immediately; do not spend another API call.
            for _, result in round_results:
                low = result.lower()
                if "confirm_required" in low or "安全阻止" in result or "工具执行失败" in result:
                    return compact_reply(instruction, result)

            # Most spoken computer commands are simple actions. The successful tool result is
            # enough evidence; asking the model to say "done" again only adds latency and cost.
            if _safe_to_finish_without_second_ai(instruction, round_results):
                return compact_reply(instruction, round_results[-1][1])

        return "任务步骤超过上限，已停止。请把任务拆成更小步骤后重试。"
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        log_timing(
            "desktop_agent",
            elapsed,
            route="+".join(_detect_domains(instruction)),
            api_calls=api_calls,
            tool_calls=total_tool_calls,
            detail=f"tools={','.join(selected_names)}; instruction={instruction[:160]}",
        )
