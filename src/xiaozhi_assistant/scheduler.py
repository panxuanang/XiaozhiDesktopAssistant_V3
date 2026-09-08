from __future__ import annotations

import hashlib
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

from .action_log import record
from .work_db import create_task, due_actions, recall, remember, update_scheduled, update_task

logger = logging.getLogger(__name__)


class SchedulerService:
    """Small persistent scheduler backed by SQLite.

    It intentionally runs inside the tray application. If the PC sleeps through a
    due time, the action is picked up when Windows/app resumes. Failed deliveries
    retry up to 3 times with a short backoff.
    """

    def __init__(self, notify: Callable[[str, str], None] | None = None, interval_seconds: int = 5):
        self.notify = notify or (lambda _title, _body: None)
        self.interval_seconds = max(2, interval_seconds)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_radar_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="xiaozhi-work-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_due_once()
                self._run_boss_radar_if_due()
            except Exception:
                logger.exception("scheduler iteration failed")
            self._stop.wait(self.interval_seconds)


    def _run_boss_radar_if_due(self) -> None:
        from .config import load_settings
        cfg = load_settings()
        if not (cfg.modules.wechat and cfg.workmate.enabled and cfg.workmate.auto_scan_wechat):
            return
        interval = max(2, int(cfg.workmate.scan_interval_minutes)) * 60
        if time.time() - self._last_radar_at < interval:
            return
        self._last_radar_at = time.time()
        try:
            from .tools.wechat import scan_priority_contacts, find_recent_wechat_attachments
            scans = scan_priority_contacts(cfg.workmate.priority_contacts)
            attachments = find_recent_wechat_attachments(within_hours=max(2, int(cfg.workmate.scan_interval_minutes) // 60 + 2))
            newest_attachment = str(attachments[0]["path"]) if attachments else ""
            for item in scans:
                if not item.get("task_like") or not item.get("text"):
                    continue
                contact = str(item.get("contact", ""))
                text = str(item.get("text", ""))
                digest = hashlib.sha256(text[-3000:].encode("utf-8", errors="ignore")).hexdigest()
                key = f"radar_hash:{contact}"
                if recall(key, "") == digest:
                    continue
                remember(key, digest)
                task_id = create_task(source="wechat_radar", contact=contact, source_text=text[-8000:], attachment_path=newest_attachment, instruction=text[-5000:], status="captured")
                self.notify("老板雷达", f"{contact} 可能发来了工作任务，已记录为 {task_id}")
        except Exception as exc:
            logger.warning("boss radar failed: %s", exc)

    def run_due_once(self) -> int:
        jobs = due_actions(limit=10)
        count = 0
        for job in jobs:
            count += 1
            try:
                self._execute(job)
                update_scheduled(job["id"], status="done", error="")
                if job.get("task_id"):
                    update_task(job["task_id"], status="delivered")
                self.notify("小智打工搭子", f"定时任务已完成：{job['action_type']}")
            except Exception as exc:
                attempts = int(job.get("attempts", 0)) + 1
                if attempts >= 3:
                    update_scheduled(job["id"], status="failed", error=str(exc), increment_attempts=True)
                    if job.get("task_id"):
                        update_task(job["task_id"], status="delivery_failed", result_summary=f"定时发送失败：{exc}")
                    self.notify("小智打工搭子", f"定时任务失败：{exc}")
                else:
                    retry_at = (datetime.now().astimezone() + timedelta(minutes=2 * attempts)).isoformat(timespec="seconds")
                    update_scheduled(job["id"], status="scheduled", error=str(exc), increment_attempts=True, run_at=retry_at)
                    record("scheduled_retry", {"job": job["id"], "attempt": attempts}, status="error", detail=str(exc))
        return count

    def _execute(self, job: dict) -> None:
        action = job["action_type"]
        payload = job["payload"]
        if action == "wechat_send":
            if not job.get("authorized"):
                raise RuntimeError("定时微信任务没有明确用户授权，已阻止发送。")
            from .tools.wechat import wechat_send_authorized
            result = wechat_send_authorized(
                contact=str(payload.get("contact", "")),
                message=str(payload.get("message", "")),
                file_path=str(payload.get("file_path", "")),
                authorization_note=str(payload.get("authorization_note", "")),
            )
            record("scheduled_wechat_send", {"job": job["id"], "contact": payload.get("contact")}, detail=result)
            return
        if action == "desktop_agent":
            from .agent import desktop_agent
            result = desktop_agent(str(payload.get("instruction", "")))
            record("scheduled_desktop_agent", {"job": job["id"]}, detail=result[:1000])
            return
        raise RuntimeError(f"未知定时任务类型：{action}")
