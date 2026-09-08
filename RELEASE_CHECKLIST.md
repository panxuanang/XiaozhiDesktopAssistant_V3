# V0.3.0 商业发布检查清单

## 构建
- [ ] GitHub Actions Windows 构建成功
- [ ] Portable EXE 启动成功
- [ ] Inno Setup 安装/卸载成功
- [ ] VERSION/安装包版本均为 0.3.0
- [ ] 代码签名完成
- [ ] Defender/主流杀软测试

## 小智 MCP
- [ ] wss endpoint 可保存、重连
- [ ] 默认 compact 工具模式 tools/list 大小正常
- [ ] `workmate` 可被小智正确调用
- [ ] `xiaozhi-agent-prompt.txt` 已配置到目标智能体

## Local-first
- [ ] 未填写 API 时程序可以启动
- [ ] 文件搜索、Excel计算、网页读取、本地摘要不触发 API
- [ ] 返回结果正确显示“本地完成/使用API”
- [ ] 写材料时若未配 API 给出清晰提示
- [ ] 模糊 Excel 规划仅传列名/样例摘要，不执行模型代码

## 微信
- [ ] 目标微信版本固定并记录
- [ ] 联系人搜索
- [ ] 读取当前会话 UIA 文本
- [ ] 近期附件搜索目录正确
- [ ] 文本发送
- [ ] 文件发送
- [ ] 发送后 UIA 验证
- [ ] 同名联系人风险测试
- [ ] 微信未登录时失败信息清晰
- [ ] 老板雷达默认关闭
- [ ] 开启老板雷达时用户明确知晓会抢焦点

## 周末老板场景
- [ ] “看看老板微信说什么” → capture task
- [ ] 自动关联近期附件
- [ ] “处理吧” → status processing/completed
- [ ] Excel 按区域汇总/异常标记
- [ ] 结果文件生成到配置目录
- [ ] “下午两点半发” → 首次要求确认
- [ ] 明确确认后 schedule 入库
- [ ] 到点发送
- [ ] 失败重试 3 次
- [ ] PC 睡眠恢复后处理过期任务
- [ ] 任务中心显示最终状态

## Office
- [ ] DOCX 生成/读取/改写
- [ ] XLSX 10万行性能测试
- [ ] Excel row_total/group_sum/filter/mark/sort/split/dedupe/fill/replace/calculate
- [ ] Excel 分析写入新 sheet
- [ ] 按列拆多个文件 / 多 Sheet
- [ ] 两表键值匹配合并
- [ ] 文件夹批处理（计划复用）
- [ ] 整目录 Excel 合并
- [ ] 上期数据合并
- [ ] PPTX 本地生成/读取
- [ ] Excel → PPT local 模式

## PDF / OCR
- [ ] 文本 PDF
- [ ] 扫描 PDF RapidOCR
- [ ] PDF 合并
- [ ] 本地摘要

## 浏览器
- [ ] Chrome
- [ ] Edge
- [ ] 打开/搜索
- [ ] Bing/百度/Google 搜索结果提取
- [ ] 多来源调研至少 5 个来源
- [ ] 不同域名来源优先
- [ ] 纯本地调研报告（不配置 API）
- [ ] 单次 API 综合调研报告（配置 API）
- [ ] 报告来源编号与 URL 保留
- [ ] 联网调研报告 → 微信准备发送
- [ ] DOM 正文读取
- [ ] 本地网页摘要
- [ ] 点击/填写
- [ ] HTML table → Excel
- [ ] 上传/下载
- [ ] 登录态持久化

## 文件索引
- [ ] 首次索引
- [ ] 增量索引
- [ ] DOCX/PDF/XLSX/PPTX/TXT 搜索
- [ ] AppData 索引隐私说明
- [ ] 大目录/权限拒绝处理

## 安全
- [ ] 即时微信发送确认
- [ ] 定时发送明确授权
- [ ] 删除确认
- [ ] 命令确认
- [ ] 支付/下单不自动执行
- [ ] API Key DPAPI
- [ ] MCP token 不写日志
- [ ] 诊断包脱敏策略（正式版建议继续补）

## 隐私/许可
- [ ] 隐私政策
- [ ] 明确本地索引保存内容
- [ ] 明确哪些操作会把内容发送到用户配置的 API
- [ ] 上游 MIT 文本保留
- [ ] 第三方依赖许可证 inventory
