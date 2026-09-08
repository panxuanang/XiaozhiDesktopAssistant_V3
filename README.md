# 小智打工人搭子 V0.3.0

这是一个面向 Windows 的 **本地优先（Local-first）工作搭子**。核心目标不是“让 AI 到处点鼠标”，而是：

> **帮我看看老板说什么 → 帮我把活干了 → 干完告诉我 → 到时间帮我交差。**

小智负责语音入口和 MCP 路由；真正的文件、Excel、Word、PDF、PPT、网页、Windows、微信和定时任务都在本机执行。

## 这版和 V0.2.0 最大的区别

V0.3.0 延续 `workmate(instruction)` 的本地优先架构，并新增两块面向真实办公的核心能力：

1. **多来源联网调研**：本地 Chrome/Edge 搜索多个公开网页、逐页提取正文、先做本地摘要；只有最终“综合写成一份像样的报告”时才可选调用一次用户 API，随后本地生成 Word，并可准备微信发送。
2. **Excel 重复劳动引擎**：支持按列拆多个文件/Sheet、去重、填空、替换、条件修改、派生列计算、VLOOKUP/XLOOKUP 式两表匹配、文件夹批处理和整目录合并。

默认仍然是 **本地能解决的事情不调用 AI API**：

- 找文件 / 文件索引：本地
- Excel 求和、汇总、筛选、标记异常、排序：本地
- Excel 统计分析：本地 pandas/openpyxl
- 网页正文读取：本地 Chrome/Edge DevTools
- 网页/PDF 快速摘要：本地提取式摘要
- 扫描 PDF：本地 RapidOCR
- PPTX 文件生成：本地 python-pptx
- Word/PDF/PPT 读取：本地
- 截图、窗口、UI Automation、音量：本地
- 微信读取/发送自动化：本地 Windows UIA/快捷键
- 定时交付与失败重试：本地 SQLite + 后台调度

只有这些场景才默认需要用户自己的 API：

- 真正“写一篇材料/通知/方案”
- Word 语义润色/重写
- Excel 指令过于模糊，规则无法安全映射时：**AI 只生成受限 JSON 操作计划，真正修改 Excel 仍在本地**
- 通用 `desktop_agent` 兜底
- 视觉模型理解截图（OCR 本身不需要 API）

每次 `workmate` 返回结果会标记：

```text
[执行方式：本地完成，未调用 AI API]
```

或：

```text
[执行方式：使用了配置的 AI API]
```

---

## 招牌场景：周六老板突然发活

理想交互：

```text
你：小智，看看老板刚才微信说什么。

电脑端：
- 打开老板微信会话
- 读取 UIA 可访问文本
- 在微信文件目录/下载目录里找最近工作附件
- 创建任务中心记录

小智：老板让你把销售表按区域重新汇总，标出异常门店，下午给他。我找到了附件。

你：处理吧，按他说的做。

电脑端：
- Excel 规则解析
- 本地 pandas/openpyxl 计算
- 生成“_小智已处理.xlsx”
- 本地生成结果摘要

小智：处理好了，结果保存在……

你：下午两点半发给老板，到点发，不用再确认。

电脑端：
- 把联系人、配文、附件、发送时间写进本地 SQLite
- 到点唤醒任务
- 检查文件存在
- 打开微信并发送
- UIA 尝试验证消息/文件名是否出现在会话中
- 失败最多重试 3 次
```

> 注意：普通 MCP 是请求-响应式，后台定时任务执行后，本版可以弹 Windows 托盘通知；如果希望“小智硬件在无人发起对话时主动开口播报”，还需要小智服务端支持主动推送/通知协议，这不是单纯 MCP 客户端可以可靠实现的能力。

---

## GUI

安装后双击客户端，可以配置：

### 连接
- 小智 MCP `wss://...` 接入地址
- 自动重连
- Windows 开机自启
- 托盘常驻

### 打工人搭子
- 本地优先总开关
- 本地网页/PDF 摘要
- 是否允许 AI 写材料
- 是否允许 AI 为“模糊任务”只做规划
- 老板/重要联系人
- 工作文件目录
- 微信附件目录
- 处理结果目录
- 老板雷达自动扫描（实验性，默认关闭）
- 本地文件索引

### AI API（可选）
支持：
- OpenAI
- DeepSeek
- 豆包方舟
- 任意 OpenAI-compatible API

填写：
- Base URL
- API Key
- Model / Deployment 名称
- `auto / responses / chat`

**模型名称不硬编码**，因为供应商模型 ID 更新很快，直接填写控制台当前有效名称更可靠。

Windows 下 API Key 使用 DPAPI 加密存储到当前用户上下文，不写进普通 config.json。

### 任务中心
可以看到：
- 已捕获
- 正在处理
- 已完成
- 已安排发送
- 已交付
- 交付失败

以及：
- 定时发送时间
- 联系人
- 文件
- 最后错误
- 取消未执行的定时任务

---

# 功能清单

## 1. 微信 / 老板雷达

- `read_wechat_contact`
- `scan_priority_contacts`
- `find_recent_wechat_attachments`
- `capture_wechat_task`
- `prepare_wechat_message`
- `prepare_wechat_file`
- `wechat_confirm_send`
- 定时授权发送 + UIA 发送后验证

老板雷达默认关闭，因为扫描联系人需要在桌面微信上切换会话，可能短暂抢焦点。

本版没有逆向微信本地数据库，也没有绕过微信安全机制；它使用 UI Automation、快捷键和本地文件目录，微信版本变化可能需要适配。

## 2. 工作上下文

SQLite 记录最近任务，可支持：

- “处理吧” → 处理刚刚捕获的任务
- “照旧” / “跟上次一样” → 复用上一任务处理要求，并关联最新附件
- 任务结果、附件、联系人、输出文件、定时时间持久化

## 3. Excel，本地优先

已实现：

- 读取/预览
- 数据画像
- 纯本地统计摘要
- 每行求和并写回
- 按指定列汇总
- 筛选区域/分类到独立工作表
- 标记低于目标行
- 排序
- 多 Excel 行合并（例如“把上个月数据也加上”）
- 按某列不同值拆成多个独立 Excel 文件
- 按某列不同值拆成同一工作簿的多个 Sheet
- 去重 / 填空 / 精确替换 / 条件修改部分行
- 安全派生列计算：求和、差值、乘积、比率、百分比
- 两表按键值匹配合并（类似 VLOOKUP/XLOOKUP）
- 文件夹内多 Excel 批量执行同一处理计划（计划只生成一次）
- 合并文件夹内所有 Excel，并可添加来源文件列
- 将分析写入独立“AI分析”工作表
- 自然语言 → 本地规则操作计划
- 本地规则不足时 → AI 只返回受限 JSON 操作计划
- 执行仍使用 pandas/openpyxl

受限计划只允许：

```text
row_total
group_sum
filter
mark_below_target
sort
split_by_column
deduplicate
fill_missing
replace
calculate
modify_where
```

不会让模型直接执行任意 Python 代码。

## 4. Word

- 创建 DOCX
- 读取 DOCX
- 写材料（需要 API）
- 润色/改写（需要 API）

Word 生成使用 python-docx，不打开 Word 模拟输入。

## 5. PPT

- 按结构化提纲本地生成 PPTX
- 读取 PPTX
- 从 Excel 本地统计直接生成简版汇报 PPT（不调用 API）
- 从任意长材料生成更自然的 PPT 提纲（此步骤可选用 API），文件生成仍在本地

## 6. PDF

- 本地文本提取
- 本地关键词搜索
- 本地提取式摘要
- 扫描 PDF → 本地 RapidOCR → 本地摘要
- PDF 合并
- 深度语义问答/总结可选 API

## 7. 网页

优先 DevTools/DOM，不用 OCR 找坐标：

- Chrome/Edge 独立用户配置目录
- 打开 URL
- Bing/百度/Google 搜索
- 搜索结果结构化提取
- 多来源联网调研（默认 5 个来源，可调）
- 逐页打开并提取正文，优先不同域名来源
- 每个来源先本地提取式压缩，避免整页扔给 API
- 可选一次 AI 综合写作，并在报告中保留来源编号与 URL
- 一键生成 Word 调研报告，并可进入微信确认发送流程
- 读取当前网页 DOM 文本
- 本地摘要
- 点击可见文字
- 填写输入框
- 提取 HTML table
- 网页 table 直接保存 Excel（本地）
- 文件上传
- 下载
- 深度网页分析可选 API

## 8. Windows

- 启动程序
- 窗口列表
- 激活/最小化/最大化/恢复/关闭
- 移动和缩放
- Windows UI Automation 控件树
- 按控件名点击
- 系统状态
- 音量

优先顺序：

```text
直接文件/API操作
> pandas/openpyxl/python-docx/python-pptx
> 浏览器 DOM / Windows UI Automation
> 快捷键
> 本地 OCR
> 坐标点击兜底
```

## 9. 文件智能搜索

本机 SQLite 索引：

- 文件名
- TXT/MD/CSV/JSON
- DOCX
- PDF
- XLSX/XLSM
- PPTX

用户可以说：

> 找一下上个月王总的报价单。

首次使用在客户端点击“建立/更新文件索引”。索引内容保存在本机 AppData，不上传云端。

## 10. 截图 / OCR / 微信

例如：

> 把当前屏幕截图发微信给我，再带上刚才的分析总结。

本地流程：

```text
截图
→ 读取最近完成任务摘要
→ prepare_wechat_file
→ 用户确认
→ 微信发送
```

不需要 API。

## 11. 定时交差

SQLite 持久化调度器：

- 定时微信文字
- 定时微信附件 + 配文
- 用户明确授权后才入队
- PC 睡眠错过时间：程序恢复后补执行
- 失败最多重试 3 次
- Windows 托盘通知
- 可在任务中心取消

如果电脑关机、微信未登录或文件被删除，任务无法保证按时成功，任务中心会留下失败原因。

## 12. 场景模板

内置场景说明：

- 销售表整理
- 销售日报
- 会议通知
- PDF速读
- 网页速读
- 老板周末任务
- 汇报PPT

MCP 工具 `list_templates` 可让小智查看推荐场景。

---

# MCP 工具数量控制

V0.2.0 默认关闭“暴露全部低层工具”。

正常情况下只给小智十来个高层工具，例如：

```text
workmate
task_center
capture_wechat_task
process_work_task
schedule_latest_task
index_work_files
search_work_files
local_summarize_current_webpage
local_summarize_pdf
list_templates
desktop_agent
```

这能明显减小 `tools/list`，也降低小智后台模型在几十个低层工具之间选错工具的概率。

如果开发调试需要，可以在 GUI “功能”页开启：

> 开发者兼容模式：把全部低层工具暴露给小智

---

# 推荐的小智提示词

项目根目录：

`xiaozhi-agent-prompt.txt`

核心原则是：

> 电脑任务先把用户完整原话交给 `workmate`，不要在小智后台自行拆成几十个低层点击。

---

# Windows 构建

客户不需要 Python。

开发/构建机器：

- Windows 10/11 x64
- Python 3.12
- 可选 Inno Setup 6

本地：

```bat
build_windows.bat
```

GitHub：

```text
Actions
→ Build Windows EXE
→ Run workflow
```

产物：

```text
dist/XiaozhiDesktopAssistant.exe
dist/installer/XiaozhiDesktopAssistant-Setup-0.3.0.exe
```

---

# 测试

```bash
pytest -q
```

V0.3.0 源码交付时包含：

- 配置 roundtrip
- 文件创建
- Word roundtrip
- Excel profile
- Excel 写回
- Excel 本地规则计划
- 中文定时时间解析
- SQLite 任务/定时队列
- PPT roundtrip
- 本地摘要/工作消息识别

注意：Linux/CI 单元测试无法代替 Windows 真机 UI 自动化回归测试。

---

# 商业发布前必须做的 Windows 真机回归

至少验证：

1. Windows 10/11
2. 微信你准备支持的固定版本
3. 微信联系人搜索、文本、文件、发送验证
4. Chrome 和 Edge 当前稳定版
5. Office/WPS 环境同时存在/不存在的情况
6. 大 Excel（10万行级）
7. 扫描 PDF
8. 中文/空格/超长路径
9. PC 睡眠后定时任务恢复
10. 微信退出登录时重试/失败提示
11. Defender/常见安全软件误报
12. EXE 代码签名
13. 自动更新签名/哈希
14. 隐私政策：本地索引存什么、什么时候内容会发给用户自己的 API

---

# 已知边界

- **微信个人版没有为本项目提供稳定官方桌面自动化 API**，当前采用 UIA/快捷键，本质上比文件/Excel API 更脆弱。正式卖之前必须固定测试版本并做持续适配。
- MCP 本身不等于“主动通知协议”。后台定时发送完成后可以弹 Windows 通知，但小智硬件若要无人发起对话时主动播报，需要服务端额外支持。
- 本地提取式摘要免费、私密、快，但语言质量不等同于大模型深度总结；用户可以按需启用 API。
- 自动网页操作无法保证所有网站，验证码、登录风控、复杂 Canvas 页面需要用户介入。
- 涉及支付、下单、删除、系统命令等高风险行为不应设计成无确认自动执行。

---

# 许可

工程保留上游 `qaqbuyan/xiaozhi-mcp-computer` 的 MIT 许可文本：

`LICENSE-UPSTREAM-XIAOZHI-MCP-COMPUTER.txt`

第三方说明：

`THIRD_PARTY_NOTICES.md`

正式商业发布前请针对实际锁定依赖版本做完整许可证审查。


## V0.3.0 典型口令

### 联网调研

```text
小智，网上查一下最近 AI 眼镜行业的发展情况，找 5 个不同来源，整理成一份报告发我微信。
```

执行：本地浏览器搜索 → 本地逐页提取 → 本地压缩 → 可选一次 API 综合 → 本地生成 Word → 微信准备发送 → 用户确认。

### Excel 拆表

```text
小智，把桌面的销售明细.xlsx 按部门的不同值拆成多个小表格，每个部门一个文件。
```

全程本地，无 API。

### Excel 批量重复劳动

```text
小智，把 D:\月报 这个文件夹里的所有 Excel 都按订单号去重，然后每行算一个含税金额。
```

同一处理计划只生成一次，然后在本机批量执行。

### 两表匹配

```text
把订单表和客户表按客户ID匹配，把客户名称和所属区域补到订单表。
```

使用本地 pandas merge，类似 VLOOKUP/XLOOKUP，不需要 API。

> Excel 高级对象提醒：普通 `.xlsx` 数据表最适合本地结构化处理。含 VBA、Power Query、复杂数据透视表、外部链接或特殊图表的 `.xlsm/.xlsx` 正式商用前必须针对目标模板做真机回归，避免结构化重写破坏高级对象。
