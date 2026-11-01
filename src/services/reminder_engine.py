"""Reminder escalation engine — the reconciliation tick.

See REMINDER_ENGINE.md for the full design. Every minute the scheduler calls
``tick(db, notifier, now)``. The tick recomputes what should have been sent
from the DB (it holds no in-memory timers). Completed ledger entries suppress
repeat sends in sequential ticks; send-before-record crashes and concurrent
workers can still duplicate SMS. See the delivery limits in REMINDER_ENGINE.md.

``now`` is a *naive* datetime representing local wall-clock time in
APP_TIMEZONE. The timezone conversion is the scheduler's job; this
module stays free of tz libraries and is testable
with an injected ``now`` and a fake ``notifier``.

Escalation per unlogged dose:
    T+0   patient_reminder   -> patient SMS
    T+30  patient_followup   -> patient SMS
    T+60  caregiver_alert    -> caregivers SMS

Catch-up rule (locked decision): send only the single most-advanced due stage
and record the earlier ones as superseded, so downtime never causes a burst.
"""

from __future__ import annotations

import logging
from datetime import datetime

from utils.authz import SYSTEM_CALLER

logger = logging.getLogger(__name__)

FOLLOWUP_MIN = 30
ALERT_MIN = 60

# Low -> high priority. Index order is the escalation order.
STAGES = ["patient_reminder", "patient_followup", "caregiver_alert"]


def tick(db, notifier, now: datetime) -> list[dict]:
    """Process every active patient's due doses once. Returns actions taken."""
    today = now.date().isoformat()
    actions: list[dict] = []

    for patient in _active_patients(db):
        try:
            meds = db.get_patient_medications(SYSTEM_CALLER, patient["id"])
        except Exception as exc:  # one patient's failure must not stop the tick
            logger.error("reminder tick: reading meds for %s failed: %s", patient.get("id"), exc)
            continue

        for med in meds:
            if med.get("frequency") == "as_needed":
                continue  # PRN meds are taken on demand — never nag
            for dose_time in med["times"]:
                try:
                    action = _process_dose(db, notifier, now, today, patient, med, dose_time)
                except Exception as exc:
                    logger.error(
                        "reminder tick: dose %s/%s@%s failed: %s",
                        patient.get("id"), med.get("name"), dose_time, exc,
                    )
                    continue
                if action:
                    actions.append(action)

    return actions


def _active_patients(db) -> list[dict]:
    return [u for u in db.get_users() if u.get("role") == "patient"]


def _process_dose(db, notifier, now, today, patient, med, dose_time) -> dict | None:
    """Send the most-advanced due-and-unsent stage for one dose, or nothing."""
    try:
        scheduled = datetime.combine(now.date(), datetime.strptime(dose_time, "%H:%M").time())
    except (ValueError, TypeError):
        return None  # unparseable stored time — skip rather than crash

    delta_min = (now - scheduled).total_seconds() / 60
    if delta_min < 0:
        return None  # dose is in the future

    # A dose logged (taken or explicitly missed) halts all escalation.
    logged = db.get_dose_log_for_date(SYSTEM_CALLER, patient["id"], med["name"], dose_time, today)
    if logged is not None:
        return None

    due = ["patient_reminder"]
    if delta_min >= FOLLOWUP_MIN:
        due.append("patient_followup")
    if delta_min >= ALERT_MIN:
        due.append("caregiver_alert")

    # Highest-priority due stage that hasn't been sent/superseded yet.
    target = next(
        (s for s in reversed(due)
         if not db.notification_sent(patient["id"], med["name"], dose_time, today, s)),
        None,
    )
    if target is None:
        return None  # every due stage already handled

    # Supersede the lower due stages so they never fire late (no burst).
    for stage in STAGES[:STAGES.index(target)]:
        if not db.notification_sent(patient["id"], med["name"], dose_time, today, stage):
            db.record_notification(patient["id"], med["name"], dose_time, today, stage)

    sent = _send_stage(db, notifier, patient, med, dose_time, target)
    if sent:
        db.record_notification(patient["id"], med["name"], dose_time, today, target)

    return {
        "patient_id": patient["id"],
        "medication": med["name"],
        "scheduled_time": dose_time,
        "stage": target,
        "result": "sent" if sent else "send_failed",
    }


def _send_stage(db, notifier, patient, med, dose_time, stage) -> bool:
    """Dispatch a stage to the notifier. Returns whether anything was sent —
    a False means the ledger is not written, so the tick retries next minute."""
    if stage == "patient_reminder":
        return notifier.send_dose_reminder(patient, med, dose_time)
    if stage == "patient_followup":
        return notifier.send_dose_followup(patient, med, dose_time)
    if stage == "caregiver_alert":
        contacts = db.get_caregiver_contacts(patient["id"])
        if not contacts:
            logger.warning("no caregiver with a phone to alert for patient %s", patient["id"])
            return False
        # Alert every caregiver (list, not a short-circuiting any()-generator,
        # so a success on the first doesn't skip the rest). Recorded as done if
        # at least one was reached; a per-recipient ledger would be
        # over-engineering for what is usually a single caregiver.
        results = [notifier.send_caregiver_alert(c, patient, med, dose_time) for c in contacts]
        return any(results)
    return False
