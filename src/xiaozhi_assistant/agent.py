from __future__ import annotations

import json
from typing import Any, Callable

from .action_log import record
from .llm import AIClient
from .local_index import search_index
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
    "browser_open": (browser.browser_open, _schema("browser_open", "打开网页", {"url":{"type":"string"}}, ["url"])),
    "browser_search": (browser.browser_search, _schema("browser_search", "搜索网页", {"query":{"type":"string"},"engine":{"type":"string","enum":["bing","baidu","google"],"default":"bing"}}, ["query"])),
    "web_research_report": (research.web_research_report, _schema("web_research_report", "多来源联网调研：本地收集/提炼网页，可选一次AI综合，生成Word报告", {"topic":{"type":"string"},"source_count":{"type":"integer","default":5},"output_path":{"type":"string","default":""},"engine":{"type":"string","enum":["bing","baidu","google"],"default":"bing"},"use_ai":{"type":"boolean","default":True}}, ["topic"])),
    "browser_current_page": (browser.browser_current_page, _schema("browser_current_page", "读取当前网页DOM正文", {"max_chars":{"type":"integer","default":24000}})),
    "local_summarize_current_webpage": (workmate_tools.local_summarize_current_webpage, _schema("local_summarize_current_webpage", "本地提取式总结当前网页，不调用API", {"max_sentences":{"type":"integer","default":6}})),
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

SYSTEM_PROMPT = """你是运行在用户 Windows 电脑上的执行型桌面助手。目标是可靠完成任务，而不是只给教程。
优先级：直接文件/API操作 > 本地结构化计算 > DOM/UI Automation > 快捷键 > 本地OCR > 坐标点击。
尽量减少外部AI调用：你自己已经是当前一次AI调用，所以不要把简单计算再次交给模型；Excel计算必须使用本地工具。
规则：
1. 不编造文件、表格、网页或执行结果；先读取真实数据。
2. Word/PPT 直接生成文件，不要打开Office模拟打字。
3. Excel 常规整理优先 excel_process_instruction / excel_local_analysis；拆表、批处理、匹配合并使用专用本地工具。
4. 单页总结优先 local_summarize_current_webpage；需要多来源调研报告时优先 web_research_report。
5. 微信发送必须 prepare 后等待用户确认。定时发送必须在明确确认后 confirmed=true。
6. 删除、支付、下单、管理员命令等高风险动作不自动执行。
7. 最终简洁说明完成了什么、文件在哪里、是否使用API；失败说明具体原因。
"""


def _tool_result(value: Any, max_chars: int = 24000) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    return text[:max_chars] + ("...[截断]" if len(text) > max_chars else "")


def desktop_agent(instruction: str, max_steps: int = 10) -> str:
    normalized = instruction.strip().lower()
    explicit_wechat_confirm = normalized in {"确认", "确认发送", "发吧", "发送吧", "可以发", "就这样发", "确认发出"} or "确认发送" in normalized
    if explicit_wechat_confirm:
        pending = wechat.latest_pending_message()
        if pending:
            return wechat.wechat_confirm_send(pending["pending_id"])
    ai = AIClient()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]
    tool_specs = [spec for _, spec in TOOLS.values()]
    for _ in range(max(1, min(max_steps, 16))):
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
            answer = msg.content or "任务已结束，但模型没有返回文字结果。"
            record("desktop_agent", {"instruction": instruction}, detail=str(answer)[:1000])
            return str(answer)
        messages.append(msg.model_dump(exclude_none=True))
        for call in msg.tool_calls:
            name = call.function.name
            if name not in TOOLS:
                result = f"未知工具：{name}"
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
                        result = _tool_result(func(**args))
                except Exception as exc:
                    result = f"工具执行失败：{type(exc).__name__}: {exc}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
    return "任务步骤超过上限，已停止。请把任务拆成更小步骤后重试。"
