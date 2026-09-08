from pathlib import Path

import xiaozhi_assistant.local_index as idx


def test_local_file_index(tmp_path: Path, monkeypatch):
    db = tmp_path / "idx.sqlite3"
    monkeypatch.setattr(idx, "file_index_db_path", lambda: db)
    root = tmp_path / "docs"; root.mkdir()
    (root / "王总报价单.txt").write_text("华南区域 报价 付款周期30天", encoding="utf-8")
    stats = idx.index_roots([str(root)])
    assert stats["indexed"] == 1
    results = idx.search_index("王总 付款周期")
    assert results and results[0]["name"] == "王总报价单.txt"
