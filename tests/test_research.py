from pathlib import Path

from xiaozhi_assistant.tools import research


def test_local_research_report_without_ai(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(research, "collect_web_sources", lambda topic, source_count=5, engine="bing": [
        {"index": 1, "title": "来源一", "url": "https://example.com/a", "local_summary": "行业需求持续增长。主要厂商正在增加研发投入。"},
        {"index": 2, "title": "来源二", "url": "https://example.org/b", "local_summary": "市场竞争加剧。产品价格出现下降趋势。"},
    ])
    out = tmp_path / "report.docx"
    result = research.web_research_report("测试行业", source_count=2, output_path=str(out), use_ai=False)
    assert Path(result["report_path"]).exists()
    assert result["source_count"] == 2
    assert result["api_used"] is False
    assert "测试行业" in result["topic"]
