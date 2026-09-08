from pathlib import Path

import pandas as pd

from xiaozhi_assistant.tools.office import create_word_document, excel_profile, read_word_document


def test_word_roundtrip(tmp_path: Path):
    path = tmp_path / "a.docx"
    create_word_document(str(path), "测试标题", "第一段\n第二段")
    text = read_word_document(str(path))
    assert "测试标题" in text
    assert "第一段" in text


def test_excel_profile(tmp_path: Path):
    path = tmp_path / "a.xlsx"
    pd.DataFrame({"区域": ["华东", "华南"], "销售额": [10, 20]}).to_excel(path, index=False)
    result = excel_profile(str(path))
    sheet = next(iter(result["sheets"].values()))
    assert sheet["rows"] == 2
    assert "销售额" in sheet["columns"]
