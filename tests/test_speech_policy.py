from xiaozhi_assistant.speech_policy import compact_reply, strip_internal_notes


def test_open_webpage_does_not_narrate_page():
    raw = "已打开：https://www.baidu.com\n页面标题：百度一下，你就知道\n页面正文：这里有很多内容"
    assert compact_reply("打开百度", raw) == "已打开。"


def test_search_is_short():
    assert compact_reply("百度搜一下人工智能", "已打开：https://www.baidu.com/s?wd=人工智能") == "已搜索。"


def test_explicit_summary_keeps_content():
    raw = "这个网页主要介绍三个方面：第一是市场规模。第二是主要厂商。第三是行业趋势。"
    result = compact_reply("总结一下这个网页主要讲什么", raw)
    assert "市场规模" in result
    assert len(result) > 20


def test_confirmation_is_not_hidden():
    raw = "CONFIRM_REQUIRED: 将在 2026-09-10 14:30 自动给王总发送微信和文件。确认后我会启用定时任务。pending_job=abc123"
    result = compact_reply("下午两点半发给王总", raw)
    assert "14:30" in result
    assert "王总" in result
    assert "确认" in result


def test_internal_api_note_removed():
    assert strip_internal_notes("已打开。\n[执行方式：本地完成，未调用 AI API]") == "已打开。"


def test_error_is_spoken_concisely():
    result = compact_reply("打开微信", "工具执行失败：RuntimeError: 微信没有登录，请先登录微信后重试。内部调试内容" * 20)
    assert "失败" in result
    assert len(result) <= 282
