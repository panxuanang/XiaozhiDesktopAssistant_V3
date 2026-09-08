from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from ..action_log import record
from ..config import load_settings
from .files import resolve_user_path


def read_pdf(path: str, max_chars: int = 50000) -> str:
    target = resolve_user_path(path)
    reader = PdfReader(target)
    chunks: list[str] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        chunks.append(f"\n--- 第 {idx + 1} 页 ---\n{text}")
        if sum(map(len, chunks)) >= max_chars:
            break
    return "".join(chunks)[:max_chars]


def summarize_pdf(path: str, question: str = "总结这份 PDF 的核心内容") -> str:
    settings = load_settings()
    text = read_pdf(path, settings.safety.max_file_chars_for_ai)
    from ..llm import AIClient
    ai = AIClient()
    result = ai.complete(
        f"任务：{question}\n\nPDF 提取文本：\n{text}",
        system="你是文档分析助手。只依据提供的 PDF 文本回答；信息不足时明确说明。",
    )
    record("summarize_pdf", {"path": path, "question": question}, detail=result[:500])
    return result


def search_pdf(path: str, keyword: str, context_chars: int = 180) -> list[str]:
    text = read_pdf(path, max_chars=200000)
    lower = text.lower()
    key = keyword.lower()
    out: list[str] = []
    start = 0
    while len(out) < 20:
        idx = lower.find(key, start)
        if idx < 0:
            break
        out.append(text[max(0, idx - context_chars): idx + len(keyword) + context_chars])
        start = idx + len(keyword)
    return out


def merge_pdfs(paths: list[str], output_path: str) -> str:
    writer = PdfWriter()
    for path in paths:
        reader = PdfReader(resolve_user_path(path))
        for page in reader.pages:
            writer.add_page(page)
    target = resolve_user_path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as fh:
        writer.write(fh)
    record("merge_pdfs", {"paths": paths, "output": str(target)})
    return str(target)


def ocr_scanned_pdf(path: str, max_pages: int = 30) -> str:
    """Render PDF pages locally and OCR them. Intended for scanned PDFs."""
    import tempfile
    import fitz
    from rapidocr_onnxruntime import RapidOCR
    target = resolve_user_path(path)
    doc = fitz.open(target)
    engine = RapidOCR()
    chunks = []
    for index in range(min(len(doc), max(1, min(int(max_pages), 100)))):
        page = doc[index]
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        temp = Path(tempfile.gettempdir()) / f"xiaozhi_pdf_{index}.png"
        pix.save(temp)
        result, _ = engine(str(temp))
        text = "\n".join(str(item[1]) for item in (result or []))
        chunks.append(f"--- 第 {index + 1} 页 ---\n{text}")
        temp.unlink(missing_ok=True)
    output = "\n".join(chunks)
    record("ocr_scanned_pdf", {"path": str(target), "pages": min(len(doc), max_pages)}, detail=f"chars={len(output)}")
    return output[:120000]
