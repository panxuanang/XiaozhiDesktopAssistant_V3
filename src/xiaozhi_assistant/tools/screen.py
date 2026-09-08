from __future__ import annotations

import tempfile
from pathlib import Path

import mss
from PIL import Image

from ..action_log import record
from ..llm import AIClient


def take_screenshot(path: str = "") -> str:
    target = Path(path).expanduser().resolve() if path else Path(tempfile.gettempdir()) / "xiaozhi_screen.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        img.save(target)
    record("take_screenshot", {"path": str(target)})
    return str(target)


def local_ocr_screen(keyword: str = "") -> str:
    image_path = take_screenshot()
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:
        raise RuntimeError("本地 OCR 组件未正确打包/安装。") from exc
    engine = RapidOCR()
    result, _ = engine(image_path)
    if not result:
        return "未识别到文字。"
    lines = []
    for item in result:
        box, text, score = item
        if keyword and keyword.lower() not in str(text).lower():
            continue
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        lines.append(f"{text} | score={float(score):.3f} | center=({sum(xs)/len(xs):.0f},{sum(ys)/len(ys):.0f})")
    return "\n".join(lines[:200]) or "没有匹配文字。"


def analyze_screen(question: str = "请解释当前屏幕内容") -> str:
    image_path = take_screenshot()
    ai = AIClient()
    result = ai.complete_with_image(image_path, question)
    record("analyze_screen", {"question": question}, detail=result[:500])
    return result
