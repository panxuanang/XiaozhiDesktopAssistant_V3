from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..action_log import record
from ..config import load_settings
from ..local_index import find_recent_files, index_roots, search_index
from ..local_text import concise_result_summary, extractive_summary, looks_like_work_task
from ..work_db import (
    authorize_scheduled,
    cancel_scheduled,
    create_task,
    get_task,
    latest_task,
    latest_pending_schedule,
    list_scheduled,
    list_tasks,
    recall,
    remember,
    schedule_action,
    update_task,
)
from .files import resolve_user_path, search_files
from . import office, pdf_tools, ppt, research


def _split_contacts(raw: str) -> list[str]:
    return [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]


def _parse_clock(text: str, now: datetime | None = None) -> datetime | None:
    """Parse common Chinese scheduling phrases in the user's local OS timezone."""
    now = now or datetime.now().astimezone()
    target_date = now.date()
    if "后天" in text:
        target_date = (now + timedelta(days=2)).date()
    elif "明天" in text:
        target_date = (now + timedelta(days=1)).date()
    elif "今天" in text:
        target_date = now.date()

    # Saturday etc. / 周六 / 星期六
    week_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    wm = re.search(r"(?:周|星期)([一二三四五六日天])", text)
    if wm:
        desired = week_map[wm.group(1)]
        delta = (desired - now.weekday()) % 7
        if delta == 0 and "下周" in text:
            delta = 7
        target_date = (now + timedelta(days=delta)).date()

    # Chinese/Arabic hour, optional half/quarter/minutes.
    cn_nums = {"零":0,"一":1,"二":2,"两":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"十一":11,"十二":12}
    m = re.search(r"(?:(上午|中午|下午|晚上|早上|凌晨)\s*)?([0-2]?\d|[一二两三四五六七八九十]{1,3})\s*[点时](半|一刻|三刻|\d{1,2}\s*分?)?", text)
    if not m:
        # ISO/local timestamp passthrough.
        m2 = re.search(r"(20\d{2}-\d{1,2}-\d{1,2})[ T](\d{1,2}):(\d{2})", text)
        if not m2:
            return None
        return datetime.fromisoformat(f"{m2.group(1)}T{int(m2.group(2)):02d}:{m2.group(3)}:00").replace(tzinfo=now.tzinfo)
    part, hour_raw, minute_raw = m.groups()
    try:
        hour = int(hour_raw)
    except ValueError:
        hour = cn_nums.get(hour_raw, 0)
        if not hour and hour_raw.startswith("十") and len(hour_raw) == 2:
            hour = 10 + cn_nums.get(hour_raw[1], 0)
    minute = 0
    if minute_raw:
        if minute_raw == "半": minute = 30
        elif minute_raw == "一刻": minute = 15
        elif minute_raw == "三刻": minute = 45
        else:
            minute = int(re.sub(r"\D", "", minute_raw) or 0)
    if part in {"下午", "晚上"} and hour < 12:
        hour += 12
    elif part == "中午" and hour < 11:
        hour += 12
    elif part == "凌晨" and hour == 12:
        hour = 0
    dt = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=now.tzinfo)
    # If no date clue and time already passed, interpret as next day.
    if not any(x in text for x in ["今天", "明天", "后天", "周", "星期", "下周"]) and dt <= now:
        dt += timedelta(days=1)
    return dt


def _extract_contact(text: str) -> str:
    cfg = load_settings()
    for name in _split_contacts(cfg.workmate.priority_contacts):
        if name and name in text:
            return name
    m = re.search(r"(?:给|发给|微信给)([\u4e00-\u9fffA-Za-z0-9_-]{2,12})(?:发|说|微信|，|,|\s)", text)
    return m.group(1) if m else (cfg.workmate.default_delivery_contact or "")


def _find_likely_attachment(message: str = "", within_hours: int = 24) -> str:
    cfg = load_settings()
    from . import wechat
    recent = wechat.find_recent_wechat_attachments(within_hours=within_hours)
    if not recent:
        recent = find_recent_files(cfg.workmate.work_roots, within_hours=within_hours, limit=30)
    # Prefer a filename mentioned in the message.
    for item in recent:
        name = str(item["name"])
        stem = Path(name).stem
        if name in message or (len(stem) >= 4 and stem in message):
            return str(item["path"])
    return str(recent[0]["path"]) if recent else ""


def capture_wechat_task(contact: str = "", attachment_path: str = "") -> dict[str, Any]:
    cfg = load_settings()
    contact = contact or (recall("last_contact", "") or (_split_contacts(cfg.workmate.priority_contacts)[0] if _split_contacts(cfg.workmate.priority_contacts) else ""))
    if not contact:
        raise ValueError("请先配置老板/重要联系人，或明确说联系人名称。")
    from . import wechat
    text = wechat.read_wechat_contact(contact)
    attachment_path = attachment_path or _find_likely_attachment(text, within_hours=24)
    due = _parse_clock(text)
    task_like = looks_like_work_task(text, cfg.workmate.task_keywords)
    task_id = create_task(
        source="wechat",
        contact=contact,
        source_text=text[-8000:],
        attachment_path=attachment_path,
        instruction=text[-5000:],
        due_at=due.isoformat(timespec="seconds") if due else "",
        status="captured" if task_like else "info",
        meta={"task_like": task_like},
    )
    remember("last_contact", contact)
    remember("last_task_id", task_id)
    result = {"task_id": task_id, "contact": contact, "attachment": attachment_path, "due_at": due.isoformat(timespec="minutes") if due else "", "task_like": task_like, "message_tail": text[-2500:]}
    record("capture_wechat_task", {"task_id": task_id, "contact": contact, "attachment": attachment_path})
    return result


def _output_for(src: Path) -> Path:
    cfg = load_settings()
    root = resolve_user_path(cfg.workmate.default_report_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{src.stem}_小智已处理{src.suffix}"


def process_work_task(task_id: str = "", instruction_override: str = "") -> dict[str, Any]:
    task = get_task(task_id) if task_id else latest_task(("captured", "pending", "failed"))
    if not task:
        raise RuntimeError("没有待处理工作任务。")
    instruction = instruction_override.strip() or task.get("instruction", "") or task.get("source_text", "")
    attachment = task.get("attachment_path", "")
    update_task(task["id"], status="processing")
    outputs: list[str] = []
    api_used = False
    try:
        if attachment:
            src = Path(attachment)
            ext = src.suffix.lower()
            if ext in {".xlsx", ".xlsm"}:
                source_for_processing = src
                # Common boss wording: "上个月的数据也加上". Find a recent sibling workbook and merge rows locally.
                if any(k in instruction for k in ["上个月", "上月数据", "上期数据", "上一次的数据"]):
                    cfg = load_settings()
                    candidates = find_recent_files(cfg.workmate.work_roots, extensions=".xlsx,.xlsm", within_hours=24*120, limit=30)
                    other = next((Path(str(x["path"])) for x in candidates if Path(str(x["path"])).resolve() != src.resolve()), None)
                    if other:
                        merged_path = _output_for(src).with_name(src.stem + "_含上期合并.xlsx")
                        office.excel_merge_files([str(other), str(src)], str(merged_path))
                        source_for_processing = merged_path
                out = _output_for(source_for_processing)
                result = office.excel_process_instruction(str(source_for_processing), instruction, output_path=str(out))
                if not result.get("ok"):
                    # A semantic request such as "改得更合理" cannot be safely guessed locally.
                    raise RuntimeError(result.get("message", "Excel 本地规划失败") + " " + str(result.get("plan", {}).get("note", "")))
                outputs.append(str(result["file"]))
                outputs.extend([str(x) for x in result.get("extra_outputs", [])])
                summary = result.get("local_analysis", "")
                if any(k in instruction for k in ["写到表格", "写进表格", "表格里做个分析", "分析写回", "分析页"]):
                    office.excel_write_analysis_sheet(str(result["file"]), summary)
                api_used = result.get("plan_source") == "ai_plan"
            elif ext == ".pdf":
                text = pdf_tools.read_pdf(str(src), max_chars=60000)
                summary = extractive_summary(text, max_sentences=6, max_chars=1600)
            elif ext == ".docx":
                text = office.read_word_document(str(src), max_chars=50000)
                # Reading/summarizing is local; actual semantic rewriting uses AI only if requested.
                if any(k in instruction for k in ["修改", "润色", "重写", "补充", "改成", "写成"]):
                    cfg = load_settings()
                    if not cfg.local_first.ai_for_writing:
                        raise RuntimeError("该任务需要语义改写，但当前已禁用 AI 写作。")
                    out = _output_for(src)
                    result_text = office.rewrite_word_document(str(src), instruction, str(out))
                    outputs.append(str(out))
                    summary = result_text
                    api_used = True
                else:
                    summary = extractive_summary(text, max_sentences=6, max_chars=1600)
            elif ext == ".pptx":
                text = ppt.read_presentation(str(src))
                summary = extractive_summary(text, max_sentences=6, max_chars=1600)
            else:
                summary = f"已找到附件：{src.name}。当前版本没有针对 {ext} 的结构化处理器。"
        else:
            # No attachment: use AI only for true writing/semantic work.
            if any(k in instruction for k in ["写", "起草", "材料", "通知", "总结", "方案", "汇报"]):
                cfg = load_settings()
                if not cfg.local_first.ai_for_writing:
                    raise RuntimeError("该任务需要写作，但当前已禁用 AI 写作。")
                out = resolve_user_path(cfg.workmate.default_report_dir) / f"小智材料_{datetime.now():%Y%m%d_%H%M}.docx"
                result_text = office.write_material(instruction, str(out))
                outputs.append(str(out))
                summary = result_text
                api_used = True
            else:
                summary = "任务已记录，但没有检测到附件，也没有匹配到可直接本地执行的操作。"

        concise = concise_result_summary(summary, 500)
        update_task(task["id"], status="completed", result_summary=concise, output_paths=outputs)
        remember("last_task_id", task["id"])
        record("process_work_task", {"task_id": task["id"], "api_used": api_used}, detail=concise)
        return {"task_id": task["id"], "status": "completed", "outputs": outputs, "summary": concise, "api_used": api_used}
    except Exception as exc:
        update_task(task["id"], status="failed", result_summary=str(exc))
        record("process_work_task", {"task_id": task["id"]}, status="error", detail=str(exc))
        raise


def schedule_task_delivery(
    contact: str,
    send_at: str,
    message: str = "",
    file_path: str = "",
    task_id: str = "",
    confirmed: bool = False,
) -> str:
    cfg = load_settings()
    dt = _parse_clock(send_at) or datetime.fromisoformat(send_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    if dt <= datetime.now().astimezone():
        raise ValueError("定时发送时间必须晚于当前时间。")
    if file_path:
        p = resolve_user_path(file_path)
        if not p.exists():
            raise FileNotFoundError(p)
        file_path = str(p)
    if not task_id:
        latest = latest_task()
        task_id = latest["id"] if latest else ""
    needs_confirm = cfg.safety.scheduled_send_requires_explicit_authorization and not confirmed
    job_id = schedule_action(
        action_type="wechat_send",
        run_at=dt.isoformat(timespec="seconds"),
        task_id=task_id,
        authorized=not needs_confirm,
        status="pending_confirmation" if needs_confirm else "scheduled",
        payload={"contact": contact, "message": message, "file_path": file_path, "authorization_note": (f"用户明确授权定时发送：{datetime.now().astimezone().isoformat(timespec='seconds')}" if not needs_confirm else "")},
    )
    if task_id:
        update_task(task_id, status="awaiting_delivery_confirmation" if needs_confirm else "scheduled", due_at=dt.isoformat(timespec="seconds"))
    record("schedule_task_delivery", {"job": job_id, "contact": contact, "run_at": dt.isoformat(), "file": file_path, "pending_confirmation": needs_confirm})
    if needs_confirm:
        return f"CONFIRM_REQUIRED: 将在【{dt.strftime('%Y-%m-%d %H:%M')}】自动给【{contact}】发送微信{('和文件 '+file_path) if file_path else ''}。确认后我会启用定时任务。pending_job={job_id}"
    return f"已安排：{dt.strftime('%Y-%m-%d %H:%M')} 给【{contact}】发送。任务ID：{job_id}"


def schedule_latest_task(contact: str, send_at: str, message: str = "", confirmed: bool = False) -> str:
    task = latest_task(("completed", "scheduled"))
    if not task:
        raise RuntimeError("没有已完成的任务可发送。")
    file_path = task.get("output_paths", [""])[0] if task.get("output_paths") else ""
    if not message:
        message = task.get("result_summary", "")[:180]
    return schedule_task_delivery(contact, send_at, message, file_path, task["id"], confirmed=confirmed)


def work_inbox(limit: int = 30) -> dict[str, Any]:
    return {"tasks": list_tasks(limit=limit), "scheduled": list_scheduled(limit=limit)}


def task_center(action: str = "list", task_id: str = "", job_id: str = "", limit: int = 30) -> Any:
    if action == "list":
        return work_inbox(limit)
    if action == "get":
        return get_task(task_id)
    if action == "process":
        return process_work_task(task_id)
    if action == "cancel_schedule":
        return {"cancelled": cancel_scheduled(job_id)}
    raise ValueError("action 支持 list/get/process/cancel_schedule")


def index_work_files(roots: str = "") -> dict[str, int]:
    cfg = load_settings()
    return index_roots(roots or cfg.workmate.work_roots)


def search_work_files(query: str, limit: int = 20) -> list[dict[str, object]]:
    results = search_index(query, limit=limit)
    if results:
        return results
    # First use is useful even before indexing.
    cfg = load_settings()
    fallback: list[dict[str, object]] = []
    for root in [x.strip() for x in cfg.workmate.work_roots.split(";") if x.strip()]:
        for p in search_files(query, root=root, max_results=limit):
            fallback.append({"path": p, "name": Path(p).name})
            if len(fallback) >= limit:
                return fallback
    return fallback


def local_summarize_current_webpage(max_sentences: int = 6) -> str:
    from . import browser
    page = json.loads(browser.browser_current_page(max_chars=50000))
    text = str(page.get("text", ""))
    return f"{page.get('title','')}\n{extractive_summary(text, max_sentences=max_sentences, max_chars=1800)}"


def local_summarize_pdf(path: str, max_sentences: int = 6) -> str:
    text = pdf_tools.read_pdf(path, max_chars=60000)
    if len(text.strip()) < 80:
        # Scanned PDF: stay local and fall back to RapidOCR.
        text = pdf_tools.ocr_scanned_pdf(path, max_pages=30)
    return extractive_summary(text, max_sentences=max_sentences, max_chars=1800)


def _extract_research_topic(text: str) -> str:
    topic = text
    patterns = [
        r"小智", r"帮我", r"请", r"在网上", r"网上", r"全网", r"联网",
        r"搜索一下", r"搜一下", r"搜索", r"查一下", r"查查", r"查找", r"调研一下", r"调研",
        r"找\d+个(?:不同)?来源", r"找几个(?:不同)?来源", r"多来源",
        r"总结(?:一下)?", r"整理(?:一下)?", r"写成(?:一份)?(?:word)?报告", r"生成(?:一份)?(?:word)?报告",
        r"做成(?:一份)?(?:word)?报告", r"报告", r"然后", r"最后",
        r"微信发给我", r"发到我微信", r"发我微信", r"微信发回去", r"微信发回", r"发给我", r"发回去",
    ]
    for pat in patterns:
        topic = re.sub(pat, " ", topic, flags=re.I)
    topic = re.sub(r"\s+", " ", topic).strip(" ，,。；;：:")
    return topic[:180] or text[:180]


def _api_note(api_used: bool) -> str:
    cfg = load_settings()
    if not cfg.local_first.show_api_usage_in_result:
        return ""
    return "\n[执行方式：使用了配置的 AI API]" if api_used else "\n[执行方式：本地完成，未调用 AI API]"


def workmate(instruction: str) -> str:
    """High-level local-first entry for Xiaozhi.

    It handles common computer/work tasks locally. API is used only for writing,
    ambiguous spreadsheet planning, or other semantic operations that cannot be
    reliably derived with deterministic code.
    """
    text = instruction.strip()
    cfg = load_settings()
    if not text:
        return "请告诉我需要处理什么工作。"

    # Explicit confirmation for a pending immediate WeChat send.
    normalized = text.lower()
    if normalized in {"确认", "确认发送", "发吧", "发送吧", "可以发", "就这样发", "确认发出", "确认定时"} or "确认，到点发" in normalized:
        from . import wechat
        pending = wechat.latest_pending_message()
        if pending:
            return wechat.wechat_confirm_send(pending["pending_id"]) + _api_note(False)
        pending_job = latest_pending_schedule()
        if pending_job and authorize_scheduled(pending_job["id"]):
            if pending_job.get("task_id"):
                update_task(pending_job["task_id"], status="scheduled")
            return f"已确认并启用定时发送：{pending_job['run_at']}，任务ID：{pending_job['id']}" + _api_note(False)

    # Inbox/status.
    if any(k in text for k in ["任务中心", "今天有什么工作", "待办", "哪些活", "工作任务"]):
        tasks = list_tasks(limit=12)
        if not tasks:
            return "目前没有记录的工作任务。" + _api_note(False)
        lines = [f"{t['id']} [{t['status']}] {t['contact'] or t['source']}：{concise_result_summary(t['source_text'] or t['instruction'], 90)}" for t in tasks]
        return "\n".join(lines) + _api_note(False)

    # "老板刚才说什么 / 看看微信".
    if ("微信" in text or any(k in text for k in ["老板", "领导", "王总", "经理"])) and any(k in text for k in ["看看", "看下", "找我", "说什么", "消息", "刚才", "发了什么"]):
        contact = _extract_contact(text)
        if not contact:
            names = _split_contacts(cfg.workmate.priority_contacts)
            contact = names[0] if names else ""
        captured = capture_wechat_task(contact)
        verdict = "检测到疑似工作任务" if captured.get("task_like") else "暂未检测到明确工作任务"
        return f"已查看【{captured['contact']}】的微信：{verdict}。记录ID {captured['task_id']}。\n最近内容：\n{captured['message_tail']}\n附件：{captured['attachment'] or '未自动找到'}" + _api_note(False)

    # Ask for the latest task result without another API call.
    if any(k in text for k in ["告诉我结果", "结果怎么样", "处理结果", "做完了吗", "弄好了吗", "结果给我说"]):
        latest = latest_task()
        if not latest:
            return "还没有记录到工作任务。" + _api_note(False)
        outputs = ", ".join(latest.get("output_paths", [])) or "无新文件"
        return f"最近任务状态：{latest['status']}。\n{latest.get('result_summary','')}\n输出：{outputs}" + _api_note(False)

    # "照旧/跟上次一样" reuses the previous task instruction as lightweight work context.
    if any(k in text for k in ["照旧", "跟上次一样", "按上次", "还是老样子"]):
        previous = latest_task(("completed", "delivered", "scheduled"))
        if previous:
            recent = _find_likely_attachment(text, within_hours=48)
            task_id = create_task(source="context_reuse", contact=previous.get("contact", ""), source_text=text, attachment_path=recent, instruction=previous.get("instruction", ""), status="captured", meta={"reused_from": previous["id"]})
            remember("last_task_id", task_id)
            result = process_work_task(task_id)
            return f"已按上次任务方式处理。{result['summary']}\n输出：{', '.join(result['outputs']) if result['outputs'] else '无新文件'}" + _api_note(bool(result["api_used"]))

    # "处理吧 / 按老板意思处理" uses the captured task.
    if any(k in text for k in ["处理吧", "帮我处理", "按他说的处理", "按老板的意思", "把这个活干了", "照他说的做"]):
        result = process_work_task(instruction_override="" if len(text) < 20 else text)
        return f"处理完成。{result['summary']}\n输出：{', '.join(result['outputs']) if result['outputs'] else '无新文件'}" + _api_note(bool(result["api_used"]))

    # Scheduled delivery. The user's current sentence itself is explicit authorization intent;
    # the tool returns a confirmation unless it contains an explicit confirm word.
    if "发" in text and any(k in text for k in ["定时", "下午", "晚上", "明天", "后天", "点", "时"]):
        contact = _extract_contact(text) or (latest_task() or {}).get("contact", "")
        dt = _parse_clock(text)
        if contact and dt:
            explicit = any(k in text for k in ["确认", "就这么发", "不用再确认", "直接发", "到点发"])
            msg_match = re.search(r"(?:顺便说|配文|跟他说|消息)[：:]?(.{2,200})", text)
            msg = msg_match.group(1).strip() if msg_match else ""
            return schedule_latest_task(contact, dt.isoformat(timespec="minutes"), msg, confirmed=explicit) + _api_note(False)

    # Screenshot + WeChat delivery is fully local; use latest task summary as caption.
    if "截图" in text and "微信" in text and "发" in text:
        from . import screen, wechat
        shot = screen.take_screenshot()
        contact = _extract_contact(text)
        if not contact and any(k in text for k in ["发给我", "发我", "微信给我"]):
            contact = "文件传输助手"
        if not contact:
            contact = cfg.workmate.default_delivery_contact or "文件传输助手"
        latest = latest_task(("completed", "scheduled", "delivered"))
        caption = latest.get("result_summary", "")[:180] if latest else ""
        preview = wechat.prepare_wechat_file(contact, shot, caption)
        return preview + _api_note(False)

    # Local file index/search.
    if any(k in text for k in ["找文件", "找一下", "在哪里", "哪个文件"]):
        q = re.sub(r"(帮我|小智|找文件|找一下|在哪里|哪个文件|桌面|下载|文档)", " ", text).strip(" ，,。")
        results = search_work_files(q or text, limit=12)
        if results:
            return "找到：\n" + "\n".join(str(x.get("path", "")) for x in results) + _api_note(False)
        return "没有找到匹配文件。建议先在客户端点一次“建立/更新文件索引”。" + _api_note(False)

    # Multi-source web research -> local extraction -> optional one-shot AI synthesis -> Word -> optional WeChat preparation.
    research_intent = (
        any(k in text for k in ["网上", "全网", "联网", "搜索", "查一下", "查查", "调研", "多个来源", "几个来源", "不同来源"])
        and any(k in text for k in ["报告", "调研", "总结", "整理", "多个来源", "几个来源", "不同来源"])
    )
    if research_intent:
        topic = _extract_research_topic(text)
        m_count = re.search(r"(?:找|看|取)?(\d{1,2})个(?:不同)?来源", text)
        source_count = max(2, min(int(m_count.group(1)), 10)) if m_count else 5
        engine = "baidu" if "百度" in text else ("google" if "谷歌" in text else "bing")
        use_ai = cfg.local_first.ai_for_writing and not any(k in text for k in ["不用API", "不要API", "纯本地", "不调用API"])
        if any(k in text for k in ["微信", "发给我", "发回去", "发我"]):
            contact = _extract_contact(text)
            if not contact and any(k in text for k in ["发给我", "发我", "发回去", "微信给我"]):
                contact = "文件传输助手"
            return research.web_research_to_wechat(topic, contact or "文件传输助手", source_count=source_count, engine=engine, use_ai=use_ai)
        result = research.web_research_report(topic, source_count=source_count, engine=engine, use_ai=use_ai)
        return f"联网调研已完成，收集 {result['source_count']} 个来源。\n报告：{result['report_path']}\n摘要：{result['summary']}" + _api_note(bool(result['api_used']))

    # Browser navigation/search/click are local DevTools operations.
    url_match = re.search(r"https?://[^\s，。]+", text)
    if url_match and any(k in text for k in ["打开", "访问", "浏览"]):
        from . import browser
        return browser.browser_open(url_match.group(0)) + _api_note(False)
    if any(k in text for k in ["网页搜", "浏览器搜", "百度搜", "必应搜", "谷歌搜", "搜索一下", "搜一下"]):
        from . import browser
        q = re.sub(r"(小智|帮我|在浏览器|浏览器|网页|百度|必应|谷歌|搜索一下|搜一下|搜索|搜)", " ", text).strip(" ，,。")
        engine = "baidu" if "百度" in text else ("google" if "谷歌" in text else "bing")
        if q:
            return browser.browser_search(q, engine=engine) + _api_note(False)
    click_match = re.search(r"(?:网页|页面).{0,10}(?:点击|点一下|点开)[“\"']?([^”\"'，。]{1,30})", text)
    if click_match:
        from . import browser
        return browser.browser_click_text(click_match.group(1).strip()) + _api_note(False)

    # Save HTML tables from the current page to Excel locally.
    if any(k in text for k in ["网页", "这个页面", "当前页面"]) and any(k in text for k in ["表格保存", "表格导出", "保存成Excel", "保存成 excel", "表格做成Excel"]):
        from . import browser
        out = browser.browser_tables_to_excel()
        return f"网页表格已本地保存：{out}" + _api_note(False)

    # Current web page local summary.
    if any(k in text for k in ["网页", "这个页面", "当前页面"]) and any(k in text for k in ["总结", "主要讲", "说什么", "概括"]):
        return local_summarize_current_webpage() + _api_note(False)

    # Screenshot is local.
    if "截图" in text and "微信" not in text:
        from . import screen
        return screen.take_screenshot() + _api_note(False)

    # System status is local.
    if any(k in text for k in ["电脑状态", "内存多少", "CPU", "磁盘空间"]):
        from . import system
        return json.dumps(system.system_status(), ensure_ascii=False) + _api_note(False)

    # Direct PDF/Word/PPT reading and quick summaries stay local.
    file_match = re.search(r"[A-Za-z]:\\[^\n\"']+?\.(?:pdf|docx|pptx)|[^\s，。]+\.(?:pdf|docx|pptx)", text, flags=re.I)
    if file_match and any(k in text for k in ["总结", "看看", "主要内容", "说什么", "概括", "速读"]):
        fp = file_match.group(0)
        ext = Path(fp).suffix.lower()
        if ext == ".pdf":
            return local_summarize_pdf(fp) + _api_note(False)
        if ext == ".docx":
            raw = office.read_word_document(fp, max_chars=60000)
            return extractive_summary(raw, max_sentences=6, max_chars=1800) + _api_note(False)
        if ext == ".pptx":
            raw = ppt.read_presentation(fp, max_chars=60000)
            return extractive_summary(raw, max_sentences=6, max_chars=1800) + _api_note(False)

    # Repetitive folder-level Excel work. The same plan is created once and reused locally.
    if any(k in text.lower() for k in ["excel", "表格", "xlsx"]) and any(k in text for k in ["文件夹", "所有表", "全部表", "批量"]):
        dir_match = re.search(r"([A-Za-z]:\\[^，。\n\"]+)|((?:桌面|下载|文档)[/\\][^，。\n\"]+)", text)
        if dir_match:
            folder = (dir_match.group(1) or dir_match.group(2)).strip()
            if "合并" in text and any(k in text for k in ["所有表", "全部表", "文件夹"]):
                result = office.excel_merge_folder(folder)
                return f"已本地合并 {result['files_merged']} 个 Excel，共 {result['rows']} 行：{result['file']}" + _api_note(False)
            result = office.excel_batch_process_directory(folder, text)
            if result.get("ok"):
                return f"批量处理完成：成功 {result['processed']} 个，失败 {result['failed_count']} 个。输出目录：{result['output_dir']}" + _api_note(result.get("plan_source") == "ai_plan")
            return str(result.get("message", "批量处理没有生成安全计划。")) + _api_note(result.get("plan", {}).get("source") == "ai_plan")

    # Common direct Excel instruction if a path/name appears or a recent Excel exists.
    if any(k in text.lower() for k in ["excel", "表格", ".xlsx", "销售表"]):
        candidates = re.findall(r"[A-Za-z]:\\[^\n\"']+?\.xlsx|[^\s，。]+\.xlsx", text, flags=re.I)
        path = candidates[0] if candidates else ""
        if not path:
            recent = find_recent_files(cfg.workmate.work_roots, extensions=".xlsx,.xlsm,.xls", within_hours=168, limit=5)
            path = str(recent[0]["path"]) if recent else ""
        if path:
            if any(k in text for k in ["算", "汇总", "筛选", "标", "整理", "处理", "总数", "合计", "拆分", "拆开", "拆成", "去重", "替换", "空白", "空值", "匹配", "计算", "批量"]):
                result = office.excel_process_instruction(path, text)
                if result.get("ok"):
                    api_used = result.get("plan_source") == "ai_plan"
                    extras = result.get("extra_outputs", [])
                    extra_text = ("\n另外生成：\n" + "\n".join(extras[:20])) if extras else ""
                    return f"Excel 已处理：{result['file']}{extra_text}\n{concise_result_summary(result['local_analysis'], 700)}" + _api_note(api_used)
            if any(k in text for k in ["PPT", "ppt", "演示文稿", "汇报PPT"]):
                out = ppt.create_ppt_from_excel_local(path)
                return f"已根据本地 Excel 统计生成 PPT：{out}" + _api_note(False)
            if any(k in text for k in ["分析", "看看", "情况", "怎么样"]):
                return office.excel_local_analysis(path) + _api_note(False)

    # Open an app locally.
    m = re.search(r"打开(?:一下)?(.{1,30})", text)
    if m and not any(k in text for k in ["网页", "网站", "文件"]):
        from . import windows
        return windows.open_program(m.group(1).strip()) + _api_note(False)

    # True writing/semantic work: use API as a fallback, not the default execution engine.
    if any(k in text for k in ["写", "起草", "润色", "改写", "方案", "材料", "通知", "汇报"]):
        if not cfg.local_first.ai_for_writing:
            return "这个任务需要内容生成，但你已关闭“AI 写作”。"
        from ..llm import AIClient
        answer = AIClient().complete(text, system="你是打工人的办公搭子。直接给出可用成品，避免空话，不编造事实。")
        return answer + _api_note(True)

    # Final fallback to the general agent only when configured to allow ambiguous AI tasks.
    if cfg.local_first.enabled and not cfg.local_first.ai_for_ambiguous_tasks:
        return "这个指令没有匹配到本地确定性能力。你已关闭“模糊任务使用 AI”，因此没有调用 API。"
    from ..agent import desktop_agent
    return desktop_agent(text) + _api_note(True)
