from __future__ import annotations

import math
import re
from collections import Counter

_STOP = set("的了和是在有也就都而及与着或一个没有我们你们他们这个那个以及进行通过对于可以需要已经如果因为所以并且然后但是其中目前相关工作问题情况内容数据文件任务结果用户进行使用" )


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 6]


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_.%-]+", text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def extractive_summary(text: str, max_sentences: int = 5, max_chars: int = 1200) -> str:
    """Small local extractive summarizer. No network and no model dependency."""
    sents = _sentences(text)
    if len(sents) <= max_sentences:
        return "\n".join(sents)[:max_chars]
    freq = Counter(_tokens(text))
    if not freq:
        return "\n".join(sents[:max_sentences])[:max_chars]
    maxf = max(freq.values())
    scores: list[tuple[float, int, str]] = []
    for i, sent in enumerate(sents):
        toks = _tokens(sent)
        if not toks:
            continue
        score = sum(freq[t] / maxf for t in toks) / math.sqrt(max(len(toks), 1))
        if i == 0:
            score *= 1.12
        scores.append((score, i, sent))
    selected = sorted(sorted(scores, reverse=True)[:max_sentences], key=lambda x: x[1])
    out = "\n".join(x[2] for x in selected)
    return out[:max_chars]


def looks_like_work_task(text: str, keywords: str = "") -> bool:
    default = "处理,整理,汇总,分析,修改,补充,发我,给我,下午,明天,附件,表格,文件,报告,周报,日报"
    terms = [x.strip() for x in (keywords or default).replace("，", ",").split(",") if x.strip()]
    low = text.lower()
    return any(term.lower() in low for term in terms)


def concise_result_summary(text: str, max_chars: int = 320) -> str:
    summary = extractive_summary(text, max_sentences=2, max_chars=max_chars)
    return summary or text.strip()[:max_chars]
