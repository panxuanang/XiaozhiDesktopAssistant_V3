from pathlib import Path

from xiaozhi_assistant.tools.ppt import create_presentation, read_presentation


def test_ppt_roundtrip(tmp_path: Path):
    p = tmp_path / "demo.pptx"
    create_presentation(str(p), "销售汇报", [{"title":"结论", "bullets":["华东领先", "西南需提升"]}])
    assert p.exists()
    text = read_presentation(str(p))
    assert "销售汇报" in text
    assert "华东领先" in text
