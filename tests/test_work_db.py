from pathlib import Path

import xiaozhi_assistant.work_db as db


def test_task_and_schedule_roundtrip(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "work.sqlite3"
    monkeypatch.setattr(db, "work_db_path", lambda: db_path)
    tid = db.create_task(source="wechat", contact="老板", source_text="处理表格", instruction="汇总", status="captured")
    task = db.get_task(tid)
    assert task and task["contact"] == "老板"
    db.update_task(tid, status="completed", result_summary="完成", output_paths=["a.xlsx"])
    task = db.get_task(tid)
    assert task["status"] == "completed"
    assert task["output_paths"] == ["a.xlsx"]
    jid = db.schedule_action(action_type="wechat_send", run_at="2026-09-09T14:30:00+08:00", payload={"contact":"老板"}, task_id=tid, authorized=True)
    jobs = db.list_scheduled()
    assert jobs[0]["id"] == jid and jobs[0]["authorized"] is True
    assert db.cancel_scheduled(jid) is True
