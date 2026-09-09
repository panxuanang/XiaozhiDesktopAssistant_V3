from __future__ import annotations


def test_excel_agent_schema_is_compact():
    from xiaozhi_assistant.agent import _selected_tool_names

    names = _selected_tool_names("把这个Excel按部门拆开，再发微信给文件传输助手")
    assert "excel_process_instruction" in names
    assert "prepare_wechat_file" in names
    assert len(names) <= 16


def test_browser_agent_schema_excludes_unrelated_excel_tools():
    from xiaozhi_assistant.agent import _selected_tool_names

    names = _selected_tool_names("打开网页，点登录，再填写搜索框")
    assert "browser_open" in names
    assert "browser_click_text" in names
    assert "excel_profile" not in names
