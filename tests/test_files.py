from pathlib import Path

from xiaozhi_assistant.tools.files import create_text_file, list_directory


def test_create_text_file(tmp_path: Path):
    target = tmp_path / "hello.txt"
    result = create_text_file(str(target), "你好")
    assert Path(result).read_text(encoding="utf-8") == "你好"
    names = [x["name"] for x in list_directory(str(tmp_path))]
    assert "hello.txt" in names
