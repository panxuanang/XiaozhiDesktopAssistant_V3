from __future__ import annotations

from typing import Any

TEMPLATES: dict[str, dict[str, Any]] = {
    "销售表整理": {
        "description": "逐行合计、按区域/门店汇总、标记低于目标项。",
        "needs": ["Excel文件"],
        "example": "把销售表每行合计，按区域汇总，并把低于目标的门店标出来。",
    },
    "销售日报": {
        "description": "本地分析销售Excel并生成简明日报；需要润色时才调用AI。",
        "needs": ["Excel文件"],
        "example": "分析今天销售表，列出前三、未达标、总完成情况。",
    },
    "会议通知": {
        "description": "根据时间、地点、议题生成Word会议通知。需要AI写作。",
        "needs": ["通知要求"],
        "example": "写一份明天下午两点预算会议通知，做成Word。",
    },
    "PDF速读": {
        "description": "本地读取并提取式总结PDF，不调用AI；扫描件走本地OCR。",
        "needs": ["PDF文件"],
        "example": "总结这个PDF的重点。",
    },
    "网页速读": {
        "description": "直接读取网页DOM并在本地做提取式总结，不用OCR和AI。",
        "needs": ["当前网页"],
        "example": "总结当前网页。",
    },
    "老板周末任务": {
        "description": "读取重要联系人微信、关联近期附件、处理文件、汇报结果、可安排定时发送。",
        "needs": ["微信联系人"],
        "example": "看看老板微信说什么，处理附件，做完告诉我，下午两点半发回去。",
    },
    "汇报PPT": {
        "description": "把材料整理成PPT提纲后本地生成PPTX；只有提纲生成用AI。",
        "needs": ["材料/分析结果"],
        "example": "把这份分析做成6页汇报PPT。",
    },
}


def list_templates() -> list[dict[str, Any]]:
    return [{"name": name, **meta} for name, meta in TEMPLATES.items()]
