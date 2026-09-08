from pathlib import Path

from xiaozhi_assistant.config import AppSettings, load_settings, save_settings


def test_config_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    s = AppSettings()
    s.xiaozhi_endpoint = "wss://example.test/mcp?token=x"
    s.ai.provider = "DeepSeek"
    s.ai.model = "deepseek-v4-flash"
    save_settings(s, path)
    loaded = load_settings(path)
    assert loaded.xiaozhi_endpoint.startswith("wss://")
    assert loaded.ai.provider == "DeepSeek"
    assert loaded.ai.model == "deepseek-v4-flash"
