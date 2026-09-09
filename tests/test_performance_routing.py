from __future__ import annotations

import json
from pathlib import Path


def test_legacy_ai_timeout_is_migrated(tmp_path):
    from xiaozhi_assistant.config import load_settings

    p = tmp_path / "config.json"
    p.write_text(json.dumps({"ai": {"timeout_seconds": 120}}, ensure_ascii=False), encoding="utf-8")
    cfg = load_settings(p)
    assert cfg.ai.timeout_seconds == 45


def test_fast_router_open_baidu_uses_zero_api_path(monkeypatch):
    from xiaozhi_assistant import fast_router

    calls = []
    monkeypatch.setattr(fast_router.fast_browser, "quick_open", lambda url: calls.append(url) or "ok")
    result = fast_router.try_fast_route("打开百度")
    assert result == ("browser_open", "ok")
    assert calls == ["https://www.baidu.com"]


def test_fast_router_does_not_steal_summary_request(monkeypatch):
    from xiaozhi_assistant import fast_router

    monkeypatch.setattr(fast_router.fast_browser, "quick_open", lambda url: (_ for _ in ()).throw(AssertionError("should not open")))
    assert fast_router.try_fast_route("打开百度并总结这个网页") is None


def test_fast_router_prepares_wechat_text_without_ai(monkeypatch):
    from xiaozhi_assistant import fast_router

    captured = {}

    def fake_prepare(contact, message):
        captured.update(contact=contact, message=message)
        return "CONFIRM_REQUIRED: ok"

    monkeypatch.setattr(fast_router.wechat, "prepare_wechat_message", fake_prepare)
    result = fast_router.try_fast_route("给张三发微信，说我晚点到")
    assert result[0] == "wechat_prepare"
    assert captured == {"contact": "张三", "message": "我晚点到"}


def test_fast_router_file_send_uses_existing_desktop_file(tmp_path, monkeypatch):
    from xiaozhi_assistant import fast_router

    f = tmp_path / "测试表.xlsx"
    f.write_bytes(b"x")

    def fake_resolve(path: str):
        if path.endswith("测试表.xlsx"):
            return f
        return tmp_path

    captured = {}
    monkeypatch.setattr(fast_router.files, "resolve_user_path", fake_resolve)
    monkeypatch.setattr(
        fast_router.wechat,
        "prepare_wechat_file",
        lambda contact, file_path, caption="": captured.update(contact=contact, file_path=file_path, caption=caption) or "CONFIRM_REQUIRED: file",
    )
    result = fast_router.try_fast_route("把桌面的测试表.xlsx发给文件传输助手")
    assert result[0] == "wechat_prepare"
    assert captured["contact"] == "文件传输助手"
    assert Path(captured["file_path"]).name == "测试表.xlsx"


def test_auto_api_fallback_skips_timeout_and_auth():
    from xiaozhi_assistant.llm.client import AIClient

    assert AIClient._should_try_fallback(RuntimeError("404 endpoint not found")) is True
    assert AIClient._should_try_fallback(RuntimeError("request timed out")) is False
    assert AIClient._should_try_fallback(RuntimeError("401 unauthorized")) is False


def test_fast_router_open_browser_uses_same_devtools_profile(monkeypatch):
    from xiaozhi_assistant import fast_router

    calls = []
    monkeypatch.setattr(fast_router.fast_browser, "quick_open", lambda url: calls.append(url) or "ok")
    result = fast_router.try_fast_route("打开浏览器")
    assert result == ("browser_open", "ok")
    assert calls == ["about:blank"]


def test_api_counter_context_is_restorable():
    from xiaozhi_assistant.performance import api_call_count, mark_api_call, reset_api_counter, restore_api_counter

    token = reset_api_counter()
    try:
        assert api_call_count() == 0
        mark_api_call(); mark_api_call(2)
        assert api_call_count() == 3
    finally:
        restore_api_counter(token)


def test_material_fallback_title_is_local():
    from xiaozhi_assistant.fast_office import _fallback_title

    title = _fallback_title("帮我写一份关于安全生产的工作总结，做成Word放桌面")
    assert title
    assert len(title) <= 28
