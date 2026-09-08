# 从 V0.2.0 升级到 V0.3.0

直接用 V0.3.0 完整工程覆盖仓库代码即可，用户配置文件结构没有破坏性变化。

建议步骤：
1. 备份当前仓库。
2. 覆盖 `src/`、`tests/`、`README.md`、`pyproject.toml`、`VERSION`、安装器和文档。
3. 保留你自己的品牌图标/公司信息（如果已经修改）。
4. GitHub Actions 重新运行 `Build Windows EXE`。
5. 真机重点测试：Chrome/Edge 搜索结果提取、5 来源调研报告、微信确认发送、Excel 按列拆表、Excel 文件夹批处理。

V0.3.0 没有新增 Python 第三方依赖，原 `requirements.txt` 可继续使用。
