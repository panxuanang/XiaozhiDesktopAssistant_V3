from __future__ import annotations

import re
from typing import Any

from ..action_log import record
from ..config import load_settings
from ..local_text import concise_result_summary, extractive_summary
from .files import resolve_user_path
from . import office


def _safe_filename(text: str, limit: int = 48) -> str:
    clean = re.sub(r'[\\/:*?"<>|\r\n]+', '_', str(text)).strip(' ._')
    return (clean or '联网调研报告')[:limit]


def collect_web_sources(topic: str, source_count: int = 5, engine: str = 'bing') -> list[dict[str, Any]]:
    """Collect multiple web sources with local Chrome/Edge and locally reduce each page.

    This function does not call a model API. It only uses the user's browser/network.
    """
    from . import browser
    count = max(1, min(int(source_count), 12))
    results = browser.browser_search_results(topic, engine=engine, limit=max(count * 3, 8))
    sources: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    for item in results:
        if len(sources) >= count:
            break
        try:
            from urllib.parse import urlsplit
            domain = (urlsplit(item['url']).hostname or '').lower()
        except Exception:
            domain = ''
        if domain and domain in seen_domains and len(results) >= count * 2:
            continue
        try:
            page = browser.browser_read_url(item['url'], max_chars=50000, timeout_seconds=10)
        except Exception:
            continue
        text = page.get('text', '').strip()
        if len(text) < 180:
            continue
        summary = extractive_summary(text, max_sentences=9, max_chars=2600)
        sources.append({
            'index': len(sources) + 1,
            'title': page.get('title') or item.get('title') or item['url'],
            'url': page.get('url') or item['url'],
            'domain': domain,
            'description': page.get('description', ''),
            'local_summary': summary,
            'chars_read': len(text),
        })
        if domain:
            seen_domains.add(domain)
    record('collect_web_sources', {'topic': topic, 'source_count': len(sources), 'engine': engine})
    return sources


def _local_report(topic: str, sources: list[dict[str, Any]]) -> str:
    combined = '\n'.join(s['local_summary'] for s in sources)
    overview = extractive_summary(combined, max_sentences=8, max_chars=2200)
    lines = [
        '一、调研摘要',
        overview or '已完成多来源资料收集，以下按来源列出本地提炼结果。',
        '',
        '二、来源要点',
    ]
    for s in sources:
        lines += [f"【{s['index']}】{s['title']}", s['local_summary'], f"来源：{s['url']}", '']
    lines += ['三、信息来源']
    for s in sources:
        lines.append(f"[{s['index']}] {s['title']} - {s['url']}")
    lines += ['', '说明：本报告正文为本地提取式整理，未使用外部生成式 AI 进行综合推断。']
    return '\n'.join(lines)


def web_research_report(
    topic: str,
    source_count: int = 5,
    output_path: str = '',
    engine: str = 'bing',
    use_ai: bool = True,
) -> dict[str, Any]:
    """Search, collect, locally summarize and create a Word research report.

    If use_ai=True and the user configured an API, only the compact local summaries are
    sent once for final synthesis. If API is absent/unavailable, a local-only report is
    still produced.
    """
    topic = topic.strip()
    if not topic:
        raise ValueError('调研主题不能为空。')
    sources = collect_web_sources(topic, source_count=source_count, engine=engine)
    if not sources:
        raise RuntimeError('没有收集到可读取的搜索结果，请换关键词或搜索引擎后重试。')

    api_used = False
    body = ''
    if use_ai:
        try:
            from ..llm import AIClient
            source_notes = '\n\n'.join(
                f"[{s['index']}] 标题：{s['title']}\n网址：{s['url']}\n本地提炼：{s['local_summary']}"
                for s in sources
            )
            prompt = (
                f"调研主题：{topic}\n\n"
                f"以下资料已经由本机程序从多个公开网页读取并做了本地提炼：\n\n{source_notes}\n\n"
                "请写一份中文调研报告。要求：\n"
                "1. 只使用上述资料，不编造事实或数据。\n"
                "2. 对关键判断标注来源编号，例如[1][3]。\n"
                "3. 结构包含：核心结论、现状/背景、关键发现、趋势或风险、建议、信息来源。\n"
                "4. 若来源之间存在冲突，要明确指出。\n"
                "5. 信息来源中保留标题和完整网址。"
            )
            body = AIClient(timeout_seconds=45, max_retries=0).complete(
                prompt,
                system='你是严谨的中文研究助理。基于给定多来源摘要做综合，不得虚构来源、数字或结论。',
                max_output_tokens=5000,
            )
            api_used = True
        except Exception as exc:
            body = _local_report(topic, sources) + f"\n\nAI 综合未启用或不可用：{exc}"
    else:
        body = _local_report(topic, sources)

    cfg = load_settings()
    if output_path:
        target = resolve_user_path(output_path)
    else:
        target = resolve_user_path(cfg.workmate.default_report_dir) / f"{_safe_filename(topic)}_联网调研报告.docx"
    target.parent.mkdir(parents=True, exist_ok=True)
    saved = office.create_word_document(str(target), f"{topic} 调研报告", body)
    summary = concise_result_summary(body, 240)
    result = {
        'topic': topic,
        'report_path': saved,
        'summary': summary,
        'source_count': len(sources),
        'sources': [{'title': s['title'], 'url': s['url']} for s in sources],
        'api_used': api_used,
    }
    record('web_research_report', {'topic': topic, 'sources': len(sources), 'output': saved, 'api_used': api_used})
    return result


def web_research_to_wechat(
    topic: str,
    contact: str = '文件传输助手',
    source_count: int = 5,
    output_path: str = '',
    engine: str = 'bing',
    use_ai: bool = True,
) -> str:
    """Create a research report and prepare it for WeChat delivery.

    The existing WeChat confirmation layer is preserved; this function never auto-sends.
    """
    from . import wechat
    result = web_research_report(topic, source_count, output_path, engine, use_ai)
    caption = f"{topic} 调研已完成：{result['summary']}"[:260]
    preview = wechat.prepare_wechat_file(contact or '文件传输助手', result['report_path'], caption)
    api_note = '使用了 1 次 AI 综合写作。' if result['api_used'] else '全程未使用生成式 AI API。'
    return f"报告已生成：{result['report_path']}\n来源数：{result['source_count']}，{api_note}\n{preview}"
