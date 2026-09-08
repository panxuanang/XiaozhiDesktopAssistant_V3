from __future__ import annotations

import json
import logging
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..action_log import recent
from ..autostart import set_windows_autostart
from ..config import PROVIDER_PRESETS, load_settings, save_settings
from ..diagnostics import run_diagnostics
from ..gateway import McpGateway
from ..llm import AIClient
from ..scheduler import SchedulerService
from ..secrets_store import get_api_key, set_api_key
from ..tools import wechat, workmate
from ..work_db import cancel_scheduled, list_scheduled, list_tasks

logger = logging.getLogger(__name__)


class GatewaySignals(QObject):
    status = Signal(str)


class WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(str)


class FunctionWorker(QRunnable):
    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.success.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:
            self.signals.error.emit(f"{type(exc).__name__}: {exc}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("小智打工人搭子")
        self.resize(900, 760)
        self.settings = load_settings()
        self.gateway: McpGateway | None = None
        self.signals = GatewaySignals()
        self.signals.status.connect(self._set_status)
        self.pool = QThreadPool.globalInstance()
        self._build_ui()
        self._load_values()
        self._build_tray()
        self.scheduler = SchedulerService(notify=self._notify)
        if self.settings.modules.scheduler:
            self.scheduler.start()
        self.refresh_tasks()
        if self.settings.auto_connect and self.settings.xiaozhi_endpoint:
            self.start_gateway()

    def _build_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._connection_tab(), "连接")
        tabs.addTab(self._workmate_tab(), "打工人搭子")
        tabs.addTab(self._ai_tab(), "AI API")
        tabs.addTab(self._modules_tab(), "功能")
        tabs.addTab(self._tasks_tab(), "任务中心")
        tabs.addTab(self._diagnostics_tab(), "诊断/日志")

    def _connection_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        box = QGroupBox("小智 MCP 连接"); form = QFormLayout(box)
        self.endpoint = QLineEdit(); self.endpoint.setPlaceholderText("wss://...token=...")
        self.status_label = QLabel("未连接")
        self.auto_connect = QCheckBox("启动软件后自动连接")
        self.auto_start = QCheckBox("Windows 登录后自动启动")
        self.start_minimized = QCheckBox("开机启动时最小化到托盘")
        form.addRow("MCP 接入地址", self.endpoint)
        form.addRow("状态", self.status_label)
        form.addRow("", self.auto_connect)
        form.addRow("", self.auto_start)
        form.addRow("", self.start_minimized)
        layout.addWidget(box)
        note = QLabel("小智后台只需要把语音任务路由到 workmate。真正的本地文件/Excel/网页/微信执行发生在这台 Windows 电脑上。")
        note.setWordWrap(True); layout.addWidget(note)
        buttons = QHBoxLayout()
        save = QPushButton("保存设置"); save.clicked.connect(self.save)
        connect = QPushButton("连接/重连"); connect.clicked.connect(self.start_gateway)
        stop = QPushButton("停止连接"); stop.clicked.connect(self.stop_gateway)
        buttons.addWidget(save); buttons.addWidget(connect); buttons.addWidget(stop)
        layout.addLayout(buttons); layout.addStretch(1)
        return w

    def _workmate_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        box = QGroupBox("本地优先策略"); form = QFormLayout(box)
        self.local_first = QCheckBox("本地能做的绝不调用 API")
        self.local_summary = QCheckBox("网页/PDF 优先本地提取式总结")
        self.ai_writing = QCheckBox("允许写材料/改稿时调用 AI API")
        self.ai_ambiguous = QCheckBox("本地规则无法判断时，允许 AI 只做任务规划")
        form.addRow("", self.local_first)
        form.addRow("", self.local_summary)
        form.addRow("", self.ai_writing)
        form.addRow("", self.ai_ambiguous)
        layout.addWidget(box)

        box2 = QGroupBox("老板雷达 / 工作目录"); form2 = QFormLayout(box2)
        self.priority_contacts = QLineEdit(); self.priority_contacts.setPlaceholderText("老板,王总,李经理")
        self.work_roots = QLineEdit(); self.work_roots.setPlaceholderText("桌面;下载;文档")
        self.wechat_roots = QLineEdit(); self.wechat_roots.setPlaceholderText("文档/WeChat Files;下载")
        self.report_dir = QLineEdit(); self.report_dir.setPlaceholderText("桌面/小智工作结果")
        self.auto_scan_wechat = QCheckBox("自动扫描重要联系人（实验性，会短暂激活微信窗口）")
        self.scan_interval = QSpinBox(); self.scan_interval.setRange(2, 240); self.scan_interval.setSuffix(" 分钟")
        form2.addRow("重要联系人", self.priority_contacts)
        form2.addRow("工作文件目录", self.work_roots)
        form2.addRow("微信附件目录", self.wechat_roots)
        form2.addRow("处理结果目录", self.report_dir)
        form2.addRow("", self.auto_scan_wechat)
        form2.addRow("扫描间隔", self.scan_interval)
        layout.addWidget(box2)

        row = QHBoxLayout()
        b1 = QPushButton("保存搭子设置"); b1.clicked.connect(self.save)
        b2 = QPushButton("建立/更新文件索引"); b2.clicked.connect(self.build_index)
        b3 = QPushButton("现在扫描重要联系人"); b3.clicked.connect(self.scan_contacts)
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3)
        layout.addLayout(row)
        self.work_status = QTextEdit(); self.work_status.setReadOnly(True); self.work_status.setMaximumHeight(180)
        layout.addWidget(self.work_status)
        help_text = QLabel("典型口令：①“小智，看看老板刚才微信说什么” ②“处理吧，按他说的做” ③“下午两点半发给老板，到点发，不用再确认”。定时发送只有在用户明确授权后才会入队。")
        help_text.setWordWrap(True); layout.addWidget(help_text); layout.addStretch(1)
        return w

    def _ai_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        box = QGroupBox("可选 AI API：只用于真正需要语言理解/写作的任务"); form = QFormLayout(box)
        self.provider = QComboBox(); self.provider.addItems(PROVIDER_PRESETS.keys()); self.provider.currentTextChanged.connect(self._provider_changed)
        self.base_url = QLineEdit(); self.model = QLineEdit(); self.model.setPlaceholderText("填写供应商控制台里的模型/部署名称")
        self.api_key = QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password)
        self.api_mode = QComboBox(); self.api_mode.addItems(["auto", "responses", "chat"])
        form.addRow("供应商", self.provider); form.addRow("Base URL", self.base_url); form.addRow("API Key", self.api_key); form.addRow("模型", self.model); form.addRow("接口模式", self.api_mode)
        layout.addWidget(box)
        row = QHBoxLayout(); save = QPushButton("保存 API"); save.clicked.connect(self.save); self.api_test_button = QPushButton("测试连接"); self.api_test_button.clicked.connect(self.test_api)
        row.addWidget(save); row.addWidget(self.api_test_button); layout.addLayout(row)
        self.api_test_status = QLabel(""); self.api_test_status.setWordWrap(True); layout.addWidget(self.api_test_status)
        note = QLabel("API 不是必填。找文件、Excel计算/拆分/批处理、网页抓取与本地提炼、截图、窗口控制、定时任务等都可以不调用 API；联网调研只有最终综合写作才可选调用一次 API。模型名不硬编码，避免供应商换模型后客户端失效。")
        note.setWordWrap(True); layout.addWidget(note); layout.addStretch(1)
        return w

    def _modules_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        self.module_checks: dict[str, QCheckBox] = {}
        labels = {
            "files":"文件助手", "office":"Word / Excel（含拆表/批处理）", "ppt":"PPT", "pdf":"PDF", "browser":"网页自动化/多来源联网调研/总结",
            "windows":"Windows UI Automation/窗口", "wechat":"微信助手", "workmate":"打工人搭子工作流", "scheduler":"定时任务",
            "indexer":"本地文件索引", "ocr":"本地 OCR 兜底", "screen":"截图/视觉分析", "system":"系统状态/音量/命令",
            "expose_low_level_tools":"开发者兼容模式：把全部低层工具暴露给小智（默认关闭）",
        }
        for key, label in labels.items():
            cb = QCheckBox(label); self.module_checks[key] = cb; layout.addWidget(cb)
        warn = QLabel("建议保持“开发者兼容模式”关闭：默认只向小智暴露约 10 个高层工具，减少 tools/list 体积和模型选错工具的概率。删除、命令、微信发送仍有安全确认。")
        warn.setWordWrap(True); layout.addWidget(warn)
        btn = QPushButton("保存并重连"); btn.clicked.connect(self.save_and_restart); layout.addWidget(btn); layout.addStretch(1)
        return w

    def _tasks_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        layout.addWidget(QLabel("工作任务"))
        self.tasks_table = QTableWidget(0, 6)
        self.tasks_table.setHorizontalHeaderLabels(["任务ID", "状态", "联系人/来源", "附件", "结果", "更新时间"])
        self.tasks_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tasks_table)
        row = QHBoxLayout()
        refresh = QPushButton("刷新"); refresh.clicked.connect(self.refresh_tasks)
        process = QPushButton("处理选中任务"); process.clicked.connect(self.process_selected_task)
        row.addWidget(refresh); row.addWidget(process); layout.addLayout(row)

        layout.addWidget(QLabel("定时发送"))
        self.jobs_table = QTableWidget(0, 6)
        self.jobs_table.setHorizontalHeaderLabels(["任务ID", "状态", "执行时间", "联系人", "文件", "错误"])
        self.jobs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.jobs_table)
        row2 = QHBoxLayout(); cancel = QPushButton("取消选中定时任务"); cancel.clicked.connect(self.cancel_selected_job); row2.addWidget(cancel); layout.addLayout(row2)
        return w

    def _diagnostics_tab(self):
        w = QWidget(); layout = QVBoxLayout(w)
        self.diag_text = QTextEdit(); self.diag_text.setReadOnly(True)
        row = QHBoxLayout(); run = QPushButton("一键自检"); run.clicked.connect(self.run_diag); logs = QPushButton("刷新操作记录"); logs.clicked.connect(self.show_logs)
        row.addWidget(run); row.addWidget(logs); layout.addLayout(row); layout.addWidget(self.diag_text)
        return w

    def _load_values(self):
        s = self.settings
        self.endpoint.setText(s.xiaozhi_endpoint)
        self.auto_connect.setChecked(s.auto_connect); self.auto_start.setChecked(s.auto_start_windows); self.start_minimized.setChecked(s.start_minimized)
        idx = self.provider.findText(s.ai.provider); self.provider.setCurrentIndex(max(0, idx))
        self.base_url.setText(s.ai.base_url); self.model.setText(s.ai.model); self.api_key.setText(get_api_key())
        idx = self.api_mode.findText(s.ai.api_mode); self.api_mode.setCurrentIndex(max(0, idx))
        for key, cb in self.module_checks.items(): cb.setChecked(bool(getattr(s.modules, key)))
        self.local_first.setChecked(s.local_first.enabled)
        self.local_summary.setChecked(s.local_first.local_summary_enabled)
        self.ai_writing.setChecked(s.local_first.ai_for_writing)
        self.ai_ambiguous.setChecked(s.local_first.ai_for_ambiguous_tasks)
        self.priority_contacts.setText(s.workmate.priority_contacts)
        self.work_roots.setText(s.workmate.work_roots)
        self.wechat_roots.setText(s.workmate.wechat_file_roots)
        self.report_dir.setText(s.workmate.default_report_dir)
        self.auto_scan_wechat.setChecked(s.workmate.auto_scan_wechat)
        self.scan_interval.setValue(s.workmate.scan_interval_minutes)

    def _provider_changed(self, name: str):
        preset = PROVIDER_PRESETS.get(name, {})
        if name != "自定义兼容API":
            self.base_url.setText(preset.get("base_url", ""))
            # Keep the user's model if present; presets intentionally don't pin volatile model IDs.
            if preset.get("model"):
                self.model.setText(preset["model"])

    def _persist_settings(self, show_message: bool = True):
        s = self.settings
        s.xiaozhi_endpoint = self.endpoint.text().strip(); s.auto_connect = self.auto_connect.isChecked(); s.auto_start_windows = self.auto_start.isChecked(); s.start_minimized = self.start_minimized.isChecked()
        s.ai.provider = self.provider.currentText(); s.ai.base_url = self.base_url.text().strip(); s.ai.model = self.model.text().strip(); s.ai.api_mode = self.api_mode.currentText()
        for key, cb in self.module_checks.items(): setattr(s.modules, key, cb.isChecked())
        s.local_first.enabled = self.local_first.isChecked(); s.local_first.local_summary_enabled = self.local_summary.isChecked(); s.local_first.ai_for_writing = self.ai_writing.isChecked(); s.local_first.ai_for_ambiguous_tasks = self.ai_ambiguous.isChecked()
        s.workmate.priority_contacts = self.priority_contacts.text().strip(); s.workmate.work_roots = self.work_roots.text().strip(); s.workmate.wechat_file_roots = self.wechat_roots.text().strip(); s.workmate.default_report_dir = self.report_dir.text().strip(); s.workmate.auto_scan_wechat = self.auto_scan_wechat.isChecked(); s.workmate.scan_interval_minutes = self.scan_interval.value()
        save_settings(s); set_api_key(self.api_key.text()); set_windows_autostart(s.auto_start_windows)
        self.settings = s
        if hasattr(self, "scheduler"):
            if s.modules.scheduler: self.scheduler.start()
            else: self.scheduler.stop()
        if show_message:
            QMessageBox.information(self, "保存", "设置已保存。API Key 在 Windows 下使用 DPAPI 加密存储。")

    def save(self):
        self._persist_settings(show_message=True)

    def save_and_restart(self):
        self._persist_settings(show_message=True); self.start_gateway()

    def test_api(self):
        try:
            self._persist_settings(show_message=False)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc)); return
        self.api_test_button.setEnabled(False); self.api_test_button.setText("测试中…")
        self.api_test_status.setText("正在后台连接模型接口，单次请求最长约 12 秒。")
        worker = FunctionWorker(lambda: AIClient(timeout_seconds=12, max_retries=0).test())
        worker.signals.success.connect(self._api_test_success); worker.signals.error.connect(self._api_test_error); self.pool.start(worker)

    def _api_test_success(self, answer: object):
        self.api_test_button.setEnabled(True); self.api_test_button.setText("测试连接"); self.api_test_status.setText("✅ API 连接成功")
        QMessageBox.information(self, "API 测试", f"连接成功：{answer}")

    def _api_test_error(self, error: str):
        self.api_test_button.setEnabled(True); self.api_test_button.setText("测试连接"); self.api_test_status.setText("❌ API 连接失败。")
        QMessageBox.critical(self, "API 测试失败", error)

    def build_index(self):
        self._persist_settings(show_message=False); self.work_status.setPlainText("正在本地建立文件索引……不会上传文件。")
        worker = FunctionWorker(workmate.index_work_files)
        worker.signals.success.connect(lambda result: self.work_status.setPlainText("文件索引完成：\n" + json.dumps(result, ensure_ascii=False, indent=2)))
        worker.signals.error.connect(lambda error: self.work_status.setPlainText("索引失败：" + error)); self.pool.start(worker)

    def scan_contacts(self):
        self._persist_settings(show_message=False); self.work_status.setPlainText("正在扫描重要联系人。注意：微信窗口可能被临时激活。")
        worker = FunctionWorker(wechat.scan_priority_contacts, self.priority_contacts.text().strip())
        worker.signals.success.connect(self._scan_contacts_done); worker.signals.error.connect(lambda error: self.work_status.setPlainText("扫描失败：" + error)); self.pool.start(worker)

    def _scan_contacts_done(self, result: object):
        self.work_status.setPlainText(json.dumps(result, ensure_ascii=False, indent=2)[:12000]); self.refresh_tasks()

    def start_gateway(self):
        endpoint = self.endpoint.text().strip()
        if not endpoint.startswith(("ws://", "wss://")):
            QMessageBox.warning(self, "MCP 地址", "请先填写以 ws:// 或 wss:// 开头的小智 MCP 接入地址。"); return
        self.stop_gateway(); self.gateway = McpGateway(endpoint, on_status=self.signals.status.emit); self.gateway.start()

    def stop_gateway(self):
        if self.gateway:
            self.gateway.stop(); self.gateway = None

    def _set_status(self, text: str):
        self.status_label.setText(text)
        if hasattr(self, "tray"):
            self.tray.setToolTip(f"小智打工人搭子 · {text}")

    def refresh_tasks(self):
        tasks = list_tasks(limit=100)
        self.tasks_table.setRowCount(len(tasks))
        for r, t in enumerate(tasks):
            vals = [t["id"], t["status"], t["contact"] or t["source"], PathLike.name(t.get("attachment_path", "")), t.get("result_summary", ""), t.get("updated_at", "")]
            for c, v in enumerate(vals): self.tasks_table.setItem(r, c, QTableWidgetItem(str(v)))
        jobs = list_scheduled(limit=100)
        self.jobs_table.setRowCount(len(jobs))
        for r, j in enumerate(jobs):
            payload = j.get("payload", {})
            vals = [j["id"], j["status"], j["run_at"], payload.get("contact", ""), PathLike.name(payload.get("file_path", "")), j.get("last_error", "")]
            for c, v in enumerate(vals): self.jobs_table.setItem(r, c, QTableWidgetItem(str(v)))

    def process_selected_task(self):
        row = self.tasks_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "任务中心", "请先选中一个任务。"); return
        task_id = self.tasks_table.item(row, 0).text()
        worker = FunctionWorker(workmate.process_work_task, task_id)
        worker.signals.success.connect(lambda result: (QMessageBox.information(self, "处理完成", json.dumps(result, ensure_ascii=False, indent=2)[:4000]), self.refresh_tasks()))
        worker.signals.error.connect(lambda error: QMessageBox.critical(self, "处理失败", error)); self.pool.start(worker)

    def cancel_selected_job(self):
        row = self.jobs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "任务中心", "请先选中一个定时任务。"); return
        job_id = self.jobs_table.item(row, 0).text()
        if cancel_scheduled(job_id):
            self.refresh_tasks(); QMessageBox.information(self, "任务中心", "已取消。")
        else:
            QMessageBox.warning(self, "任务中心", "该任务已经执行/取消，无法再次取消。")

    def run_diag(self):
        lines = []
        for name, ok, detail in run_diagnostics(): lines.append(f"{'✅' if ok else '❌'} {name}: {detail}")
        self.diag_text.setPlainText("\n".join(lines))

    def show_logs(self):
        rows = recent(150)
        self.diag_text.setPlainText("\n".join(f"{r['ts']} [{r['status']}] {r['action']} {r['detail']}" for r in rows))

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self); self.tray.setToolTip("小智打工人搭子")
        menu = __import__("PySide6.QtWidgets", fromlist=["QMenu"]).QMenu()
        show = QAction("打开", self); show.triggered.connect(self.show_normal)
        reconnect = QAction("重新连接小智", self); reconnect.triggered.connect(self.start_gateway)
        refresh = QAction("刷新任务中心", self); refresh.triggered.connect(self.refresh_tasks)
        pause = QAction("暂停 MCP", self); pause.triggered.connect(self.stop_gateway)
        quit_action = QAction("退出", self); quit_action.triggered.connect(self.quit_app)
        for act in [show, reconnect, refresh, pause]: menu.addAction(act)
        menu.addSeparator(); menu.addAction(quit_action)
        self.tray.setContextMenu(menu); self.tray.activated.connect(lambda reason: self.show_normal() if reason == QSystemTrayIcon.DoubleClick else None); self.tray.show()

    def _notify(self, title: str, body: str):
        if hasattr(self, "tray"):
            self.tray.showMessage(title, body, QSystemTrayIcon.Information, 5000)

    def show_normal(self):
        self.show(); self.raise_(); self.activateWindow()

    def closeEvent(self, event):
        event.ignore(); self.hide(); self._notify("小智打工人搭子", "程序仍在后台运行，定时任务和老板雷达会继续工作。")

    def quit_app(self):
        self.stop_gateway(); self.scheduler.stop(); self.tray.hide(); QApplication.quit()


class PathLike:
    @staticmethod
    def name(value: str) -> str:
        if not value: return ""
        try:
            import os
            return os.path.basename(value)
        except Exception:
            return str(value)
