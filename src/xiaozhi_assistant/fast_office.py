from __future__ import annotations

import json
import re
from pathlib import Path

from .action_log import record
from .llm import AIClient


def _fallback_title(requirement: str) -> str:
    text = re.sub(r"[\r\n]+", " ", requirement).strip()
    # Prefer a user-supplied title/name when present.
    for pat in (
        r"(?:标题|题目|名称)[：:]\s*[《\"“]?([^》\"”。，；;]{2,40})",
        r"(?:写|起草|生成|做)(?:一份|个)?\s*([^，。；;]{2,24}?)(?:通知|总结|报告|方案|汇报|材料|纪要)",
    ):
        m = re.search(pat, text)
        if m:
            candidate = m.group(1).strip()
            if 2 <= len(candidate) <= 40:
                return candidate
    # Build a short descriptive title without a second model request.
    cleaned = re.sub(r"^(?:小智|帮我|请|给我|写|起草|生成|做|一份|一个)+", "", text)
    cleaned = re.sub(r"(?:放桌面|保存到.*|做成word.*|生成word.*)$", "", cleaned, flags=re.I).strip(" ，,。")
    if not cleaned:
        return "工作材料"
    return cleaned[:28].rstrip(" ，,。") or "工作材料"


def write_material_one_call(requirement: str, path: str = "桌面/材料.docx", title: str = "") -> str:
    """Generate content + title in one model request, then create the DOCX locally.

    V0.3's write_material used one API call for the body and a second call merely to
    invent a title.  For a spoken assistant that extra round-trip is noticeable.
    """
    ai = AIClient(max_retries=0)
    requested_title = title.strip()
    prompt = f"""请根据以下要求撰写一份可直接交付的中文材料。\n\n用户要求：{requirement}\n\n要求：\n1. 结构完整、事实不编造、语言符合用户要求；\n2. 不解释写作过程；\n3. 一次返回标题和完整正文；\n4. 只输出严格 JSON，格式：{{\"title\":\"标题\",\"content\":\"完整正文\"}}。"""
    raw = ai.complete(prompt, system="你是一名专业中文材料写作助手。输出可直接使用的成品，并严格遵守 JSON 输出格式。")
    content = raw
    model_title = ""
    try:
        cleaned = raw.strip().strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
        data = json.loads(cleaned)
        model_title = str(data.get("title", "")).strip().strip("《》")
        content = str(data.get("content", "")).strip()
    except Exception:
        # Some compatible providers do not reliably obey JSON mode. Keep the useful
        # generated body instead of issuing another model request.
        content = raw.strip()
    final_title = requested_title or model_title or _fallback_title(requirement)
    if not content:
        raise RuntimeError("模型没有返回材料正文。")
    from .tools import office
    saved = office.create_word_document(path, final_title, content)
    record("write_material_one_call", {"path": saved, "title": final_title}, detail=f"chars={len(content)}; api_calls=1")
    return f"材料已生成并保存：{saved}"
