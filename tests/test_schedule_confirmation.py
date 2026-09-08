from pathlib import Path

import xiaozhi_assistant.work_db as db


def test_pending_schedule_can_be_authorized(tmp_path: Path, monkeypatch):
    path = tmp_path / "work.sqlite3"
    monkeypatch.setattr(db, "work_db_path", lambda: path)
    jid = db.schedule_action(action_type="wechat_send", run_at="2026-09-09T14:30:00+08:00", payload={"contact":"老板"}, authorized=False, status="pending_confirmation")
    pending = db.latest_pending_schedule()
    assert pending and pending["id"] == jid and pending["authorized"] is False
    assert db.authorize_scheduled(jid) is True
    job = db.list_scheduled()[0]
    assert job["status"] == "scheduled" and job["authorized"] is True
