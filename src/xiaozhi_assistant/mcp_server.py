from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .logging_setup import setup_logging
from . import mcp_facade
from .workflow_templates import list_templates
from .tools import browser, files, office, pdf_tools, ppt, research, screen, system, wechat, windows, workmate

setup_logging()
logger = logging.getLogger(__name__)
settings = load_settings()
mcp = FastMCP("小智打工人搭子")

# The high-level Xiaozhi surface deliberately returns concise, speech-ready results.
# Full details remain available in task center/logs and through explicit read/summary tools.
mcp.tool(description="打工人搭子统一入口。优先直接执行；用户未要求总结/分析时，只返回一句简短结果，不主动朗读网页、文件或界面内容。") (
    mcp_facade.workmate
)
# Keep ONE generic execution fallback visible in normal mode.
# V0.3.1 hid this together with low-level tools, which could make Xiaozhi
# answer verbally instead of executing commands that workmate did not match.
# desktop_agent itself still uses the concise speech policy, so restoring it
# does not bring back the old verbose narration problem.
mcp.tool(description="通用电脑执行入口。用于 workmate 未覆盖的电脑任务；会实际执行本地工具，动作完成后只简短汇报。") (
    mcp_facade.desktop_agent
)
mcp.tool(description="任务中心：list 查看任务/定时发送，get 查看单个任务，process 处理任务，cancel_schedule 取消定时发送。")(
    workmate.task_center
)
mcp.tool(description="从指定老板/重要联系人微信会话中读取最近可访问文字，并自动关联近期工作附件，创建一个待处理任务。")(
    workmate.capture_wechat_task
)
mcp.tool(description="处理已捕获的工作任务。Excel 优先规则/本地计算；PDF/Word读取优先本地；只有语义改写等才调用用户自己的 AI API。")(
    workmate.process_work_task
)
mcp.tool(description="为最新已完成任务安排微信定时交付。定时发送是外部动作，需要用户明确确认后 confirmed=true。")(
    workmate.schedule_latest_task
)
mcp.tool(description="建立/更新本地办公文件索引。只读取本机文件，不调用 AI。") (workmate.index_work_files)
mcp.tool(description="搜索本地办公文件索引；没有索引时回退到文件名搜索。全程本地。") (workmate.search_work_files)
mcp.tool(description="本地提取式总结当前浏览器网页。只有用户明确要求总结页面时使用。") (workmate.local_summarize_current_webpage)
mcp.tool(description="本地提取式总结 PDF。只有用户明确要求总结时使用。") (workmate.local_summarize_pdf)
mcp.tool(description="列出内置打工人场景模板及示例口令。") (list_templates)
mcp.tool(description="多来源联网调研：本地浏览器搜索并逐页提取，本地先压缩；可选只调用一次用户API做综合，最终生成Word报告。") (research.web_research_report)
mcp.tool(description="联网调研并生成Word后准备发送微信；仍保留微信发送确认，不会绕过安全层。") (research.web_research_to_wechat)
mcp.tool(description="按某一列不同值把Excel拆成多个文件或同一工作簿多个Sheet，全程本地，不调用API。") (office.excel_split_by_column)
mcp.tool(description="对一个文件夹内多个Excel重复执行同一处理计划；计划只生成一次，批量执行全在本地。") (office.excel_batch_process_directory)


def _enabled(name: str) -> bool:
    return bool(getattr(settings.modules, name, True))


# Developer compatibility mode only controls the MANY low-level schemas.
# The single high-level desktop_agent above stays visible in normal mode so
# arbitrary spoken computer tasks can still execute without exposing dozens
# of MCP tools (which could otherwise bloat the tool list).
if settings.modules.expose_low_level_tools:
    if _enabled("files"):
        mcp.tool(description="按名称在电脑目录中搜索文件或文件夹。") (files.search_files)
        mcp.tool(description="查看一个目录中的文件和子目录。") (files.list_directory)
        mcp.tool(description="创建 UTF-8 文本文件。") (files.create_text_file)
        mcp.tool(description="移动文件或文件夹。") (files.move_path)
        mcp.tool(description="复制文件或文件夹。") (files.copy_path)
        mcp.tool(description="删除文件或文件夹；confirmed=true 前不会执行。") (files.delete_path)
        mcp.tool(description="按扩展名整理目录；confirmed=true 前不会执行。") (files.organize_by_extension)
    if _enabled("office"):
        mcp.tool(description="直接生成真正的 .docx Word 文件。") (office.create_word_document)
        mcp.tool(description="用配置的 AI API 撰写材料并生成 Word。") (office.write_material)
        mcp.tool(description="读取 Word 文档正文。") (office.read_word_document)
        mcp.tool(description="用配置的 AI API 修改 Word 并另存。") (office.rewrite_word_document)
        mcp.tool(description="本地读取 Excel 并返回结构化统计摘要。") (office.excel_profile)
        mcp.tool(description="本地规则优先分析 Excel；仅语言结论可用 AI。") (office.analyze_excel)
        mcp.tool(description="读取 Excel 前若干行。") (office.excel_preview)
        mcp.tool(description="Excel 逐行求和并写回。") (office.excel_calculate_row_totals)
        mcp.tool(description="把演示分析结果写入 Excel。") (office.excel_write_analysis)
        mcp.tool(description="纯本地 Excel 摘要，不调用 API。") (office.excel_local_analysis)
        mcp.tool(description="把自然语言 Excel 要求转成受限操作计划；常见任务本地规则完成，模糊任务才调用 API。") (office.excel_plan_from_instruction)
        mcp.tool(description="执行受限 Excel 操作计划，全部本地。") (office.excel_apply_plan)
        mcp.tool(description="按自然语言处理 Excel，规则优先、AI 只做必要规划。") (office.excel_process_instruction)
        mcp.tool(description="把分析文字写入 Excel 的独立分析工作表。") (office.excel_write_analysis_sheet)
        mcp.tool(description="按某列不同值拆分Excel为多个文件或多个Sheet。") (office.excel_split_by_column)
        mcp.tool(description="按条件修改Excel部分行。") (office.excel_modify_rows)
        mcp.tool(description="替换Excel某列中的指定值。") (office.excel_replace_values)
        mcp.tool(description="填充Excel某列空白值。") (office.excel_fill_missing)
        mcp.tool(description="Excel本地去重。") (office.excel_deduplicate)
        mcp.tool(description="用安全固定运算计算Excel新列。") (office.excel_calculate_column)
        mcp.tool(description="两个Excel按键值匹配合并，类似VLOOKUP/XLOOKUP。") (office.excel_lookup_merge)
        mcp.tool(description="合并文件夹里的多个Excel。") (office.excel_merge_folder)
        mcp.tool(description="批量处理文件夹里的多个Excel，计划只生成一次。") (office.excel_batch_process_directory)
    if _enabled("ppt"):
        mcp.tool(description="按结构化提纲本地生成 PPTX。") (ppt.create_presentation)
        mcp.tool(description="读取 PPT 文字。") (ppt.read_presentation)
        mcp.tool(description="让 AI 只生成 PPT 提纲，再在本地生成 PPTX。") (ppt.create_ppt_from_text)
    if _enabled("pdf"):
        mcp.tool(description="读取 PDF 可提取文本。") (pdf_tools.read_pdf)
        mcp.tool(description="用 AI 总结 PDF 或问答。") (pdf_tools.summarize_pdf)
        mcp.tool(description="在 PDF 中搜索关键词。") (pdf_tools.search_pdf)
        mcp.tool(description="对扫描 PDF 做本地 OCR。") (pdf_tools.ocr_scanned_pdf)
        mcp.tool(description="合并 PDF。") (pdf_tools.merge_pdfs)
    if _enabled("browser"):
        mcp.tool(description="只打开网页，不读取、不总结。") (browser.browser_open)
        mcp.tool(description="只搜索网页，不自动总结。") (browser.browser_search)
        mcp.tool(description="读取当前网页 DOM 正文。仅用户明确要求查看内容时使用。") (browser.browser_current_page)
        mcp.tool(description="用 AI 总结当前网页。仅用户明确要求总结时使用。") (browser.summarize_current_webpage)
        mcp.tool(description="按可见文字点击网页按钮或链接。") (browser.browser_click_text)
        mcp.tool(description="填写网页输入框。") (browser.browser_fill)
        mcp.tool(description="提取网页表格。") (browser.browser_extract_tables)
        mcp.tool(description="上传本机文件到网页。") (browser.browser_upload_file)
        mcp.tool(description="读取搜索结果链接列表。") (browser.browser_search_results)
        mcp.tool(description="在临时浏览器标签页读取指定URL正文。") (browser.browser_read_url)
        mcp.tool(description="多来源联网调研并生成Word。") (research.web_research_report)
        mcp.tool(description="点击网页文字并下载。") (browser.browser_download_by_text)
    if _enabled("windows"):
        mcp.tool(description="列出 Windows 窗口。") (windows.list_windows)
        mcp.tool(description="激活窗口。") (windows.activate_window)
        mcp.tool(description="最小化/最大化/恢复/关闭窗口。") (windows.window_action)
        mcp.tool(description="移动缩放窗口。") (windows.move_resize_window)
        mcp.tool(description="读取 UI Automation 控件树。") (windows.ui_tree)
        mcp.tool(description="按控件名称点击。") (windows.ui_click)
        mcp.tool(description="启动程序。") (windows.open_program)
    if _enabled("wechat"):
        mcp.tool(description="准备微信文本，发送前需要确认。") (wechat.prepare_wechat_message)
        mcp.tool(description="准备微信文件，发送前需要确认。") (wechat.prepare_wechat_file)
        mcp.tool(description="确认并发送已准备微信。") (wechat.wechat_confirm_send)
        mcp.tool(description="读取当前微信 UIA 文字。") (wechat.read_wechat_ui)
        mcp.tool(description="打开并读取指定微信联系人。") (wechat.read_wechat_contact)
        mcp.tool(description="扫描重要联系人并本地标记疑似工作消息。") (wechat.scan_priority_contacts)
        mcp.tool(description="查找近期微信/下载目录附件。") (wechat.find_recent_wechat_attachments)
    if _enabled("ocr"):
        mcp.tool(description="本地截屏 OCR，仅作兜底。") (screen.local_ocr_screen)
    if _enabled("screen"):
        mcp.tool(description="截取全部屏幕。") (screen.take_screenshot)
        mcp.tool(description="把截图交给配置的视觉模型分析。") (screen.analyze_screen)
    if _enabled("system"):
        mcp.tool(description="获取 CPU/内存/磁盘状态。") (system.system_status)
        mcp.tool(description="设置 Windows 主音量。") (system.set_system_volume)
        mcp.tool(description="执行系统命令，危险操作必须 confirmed=true。") (system.run_command)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
