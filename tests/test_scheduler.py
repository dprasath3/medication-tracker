"""Stage 4 — scheduler wiring (REMINDER_ENGINE.md).

The scheduler is thin orchestration: it registers a per-minute tick + a weekly
cron, hands the engine a naive local ``now``, and never lets an engine error
crash the worker. These assert that wiring without waiting on real time.
"""

from datetime import datetime

import pytest

from services import scheduler as scheduler_mod
from services.scheduler import MedicationScheduler


class FakeDB:
    def get_users(self):
        return []


@pytest.fixture
def sched():
    s = MedicationScheduler(FakeDB())
    try:
        yield s
    finally:
        s.stop()


def test_start_registers_tick_and_weekly_jobs(sched):
    sched.start()
    ids = {j.id for j in sched.scheduler.get_jobs()}
    assert "reminder_tick" in ids
    assert "weekly_reports" in ids


def test_now_is_naive_local_wall_clock(sched):
    now = sched._now()
    assert isinstance(now, datetime)
    assert now.tzinfo is None  # the shape reminder_engine.tick expects


def test_run_tick_calls_engine_with_db_and_notifier(sched, monkeypatch):
    seen = {}

    def fake_tick(db, notifier, now):
        seen.update(db=db, notifier=notifier, now=now)
        return [{"stage": "patient_reminder", "patient_id": 1, "medication": "M",
                 "scheduled_time": "08:00", "result": "sent"}]

    monkeypatch.setattr(scheduler_mod.reminder_engine, "tick", fake_tick)
    sched._run_tick()
    assert seen["db"] is sched.db
    assert seen["notifier"] is sched.notification_service
    assert seen["now"].tzinfo is None


def test_run_tick_swallows_engine_errors(sched, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(scheduler_mod.reminder_engine, "tick", boom)
    sched._run_tick()  # must not raise — a bad tick can't take down the worker


def test_run_tick_drives_the_real_engine_end_to_end(tmp_path, monkeypatch):
    """Integration: scheduler -> real reminder_engine -> real DB + ledger."""
    from datetime import date, time

    from utils.database import MedicationDB

    db = MedicationDB(db_path=str(tmp_path / "t.db"))
    patient = db.add_user("Pat", email="p@x.com", role="patient", phone="+14155550100")
    db.add_medication(patient, patient, "Metformin", "500mg", "daily", ["08:00"])

    sched = MedicationScheduler(db)
    try:
        calls = []

        class FakeNotifier:
            def send_dose_reminder(self, p, m, t):
                calls.append(("reminder", t)); return True

            def send_dose_followup(self, p, m, t):
                calls.append(("followup", t)); return True

            def send_caregiver_alert(self, c, p, m, t):
                calls.append(("alert", t)); return True

        sched.notification_service = FakeNotifier()
        monkeypatch.setattr(sched, "_now", lambda: datetime.combine(date.today(), time(8, 0)))

        sched._run_tick()

        assert ("reminder", "08:00") in calls
        assert db.notification_sent(
            patient, "Metformin", "08:00", date.today().isoformat(), "patient_reminder"
        )
    finally:
        sched.stop()


def test_invalid_timezone_falls_back_to_utc(monkeypatch):
    monkeypatch.setattr(scheduler_mod, "APP_TIMEZONE", "Not/AZone")
    s = MedicationScheduler(FakeDB())
    try:
        assert str(s._tz) == "UTC"
    finally:
        s.stop()


def test_weekly_report_uses_configured_timezone(monkeypatch):
    monkeypatch.setattr(scheduler_mod, "APP_TIMEZONE", "America/New_York")
    s = MedicationScheduler(FakeDB())
    try:
        s.start()
        trigger = s.scheduler.get_job("weekly_reports").trigger
        assert str(trigger.timezone) == "America/New_York"
    finally:
        s.stop()
