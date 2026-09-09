# 从 V0.3.0 升级到 V0.3.1

把本补丁包中的文件按原目录覆盖到 V0.3.0 仓库根目录，然后重新运行 GitHub Actions 的 **Build Windows EXE**。

新增文件：
- `src/xiaozhi_assistant/speech_policy.py`
- `src/xiaozhi_assistant/mcp_facade.py`
- `tests/test_speech_policy.py`

替换文件：
- `src/xiaozhi_assistant/agent.py`
- `src/xiaozhi_assistant/mcp_server.py`
- `VERSION`
- `pyproject.toml`
- `installer/XiaozhiAssistant.iss`

建议 V0.3.1 真机验证：
1. “打开百度” -> 只应回复“已打开。”，不应介绍网页。
2. “总结一下这个网页” -> 才应给出网页摘要。
3. “百度搜一下人工智能” -> 只应回复“已搜索。”。
4. “看看老板刚才说什么” -> 应保留必要消息摘要，因为这是用户明确要求读取内容。
5. “下午两点半发给王总” -> 必须保留确认提示，不能被静默策略压掉。

注意：这版先解决电脑端输出与工具路由。小智后台的智能体提示词以后仍建议再做一轮“少说、先做”的配套优化。
