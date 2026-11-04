"""Background scheduler for the reminder engine.

Runs the reconciliation tick (services/reminder_engine.py) once a minute and
sends weekly compliance reports. The tick model replaces the old per-medication
cron jobs: because it recomputes due doses from the DB every minute, new and
edited medications are picked up automatically and pending reminders survive a
restart — no re-scheduling loop required.

See REMINDER_ENGINE.md.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services import reminder_engine
from services.notifications import NotificationService
from utils.authz import SYSTEM_CALLER

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")


class MedicationScheduler:
    """Runs the reminder tick every minute plus weekly reports.

    ``db`` is whatever ``utils.db_factory.get_database()`` returns — SQLite
    locally, Supabase in production. The scheduler never imports a concrete
    backend, so the worker shares the web app's database.
    """

    def __init__(self, db):
        self.db = db
        self.notification_service = NotificationService()
        try:
            self._tz = ZoneInfo(APP_TIMEZONE)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("Unknown APP_TIMEZONE %r; falling back to UTC", APP_TIMEZONE)
            self._tz = ZoneInfo("UTC")
        self.scheduler = BackgroundScheduler(timezone=self._tz)
        self.scheduler.start()
        logger.info("Medication Scheduler initialized (timezone=%s)", APP_TIMEZONE)

    def start(self) -> None:
        """Register the per-minute reminder tick and the weekly report cron."""
        self.scheduler.add_job(
            func=self._run_tick,
            trigger=IntervalTrigger(minutes=1),
            id="reminder_tick",
            name="Reminder escalation tick",
            replace_existing=True,
            max_instances=1,   # never overlap ticks
            coalesce=True,     # if runs pile up, collapse to one
        )
        self.schedule_weekly_reports()
        logger.info("Reminder tick scheduled (every minute)")

    def _now(self) -> datetime:
        """Local wall-clock in APP_TIMEZONE as a naive datetime — the shape
        reminder_engine.tick expects (it does no timezone math itself)."""
        return datetime.now(self._tz).replace(tzinfo=None)

    def _run_tick(self) -> None:
        """Invoke the reconciliation engine; log what it sent."""
        try:
            actions = reminder_engine.tick(self.db, self.notification_service, self._now())
        except Exception as exc:
            logger.error("reminder tick failed: %s", exc)
            return
        for a in actions:
            logger.info(
                "reminder %s -> patient %s / %s @ %s (%s)",
                a["stage"], a["patient_id"], a["medication"], a["scheduled_time"], a["result"],
            )

    # ---- Weekly compliance reports (unchanged behavior) -------------------

    def schedule_weekly_reports(self) -> None:
        """Schedule weekly compliance reports (every Sunday at 6 PM local)."""
        self.scheduler.add_job(
            func=self._generate_and_send_weekly_reports,
            trigger=CronTrigger(day_of_week='sun', hour=18, minute=0, timezone=self._tz),
            id='weekly_reports',
            name='Weekly Compliance Reports',
            replace_existing=True,
        )
        logger.info("Weekly reports scheduled for Sundays at 6 PM")

    def _generate_and_send_weekly_reports(self) -> None:
        """Generate and send weekly reports to all patients and their families."""
        users = self.db.get_users()

        for user in users:
            if user['role'] == 'patient':
                try:
                    adherence_data = self._calculate_weekly_adherence(user['id'])
                    family_emails = self._get_family_emails(user['id'])
                    self.notification_service.send_weekly_report(
                        user, adherence_data, family_emails
                    )
                    logger.info(f"Weekly report sent for {user['name']}")
                except Exception as e:
                    logger.error(f"Error generating report for {user['name']}: {str(e)}")

    def _calculate_weekly_adherence(self, patient_id: int) -> Dict:
        """Calculate adherence data for the past week."""
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)

        rows = self.db.get_daily_dose_counts(SYSTEM_CALLER, patient_id, days=7)
        by_date = {row['date']: row for row in rows}

        total_doses = sum(row['total'] for row in rows)
        taken_doses = sum(row['taken'] for row in rows)
        missed_doses = total_doses - taken_doses
        adherence_rate = (taken_doses / total_doses * 100) if total_doses > 0 else 0

        daily_data = []
        for i in range(7):
            day = end_date - timedelta(days=i)
            row = by_date.get(day.isoformat())
            day_taken = row['taken'] if row else 0
            day_total = row['total'] if row else 0
            day_rate = (day_taken / day_total * 100) if day_total > 0 else 0

            daily_data.append({
                'date': day.strftime('%A, %b %d'),
                'taken': day_taken,
                'missed': day_total - day_taken,
                'adherence_rate': day_rate
            })

        return {
            'adherence_rate': adherence_rate,
            'total_doses': total_doses,
            'taken_doses': taken_doses,
            'missed_doses': missed_doses,
            'week_start': start_date.strftime('%B %d, %Y'),
            'week_end': end_date.strftime('%B %d, %Y'),
            'daily_data': daily_data
        }

    def _get_family_emails(self, patient_id: int) -> List[str]:
        """Get email addresses of family members monitoring this patient."""
        circles = self.db.get_user_family_circles(patient_id)

        family_emails = []
        for circle in circles:
            members = self.db.get_family_circle_members(circle['id'])
            for member in members:
                if member['role'] == 'family_member' and member['email']:
                    family_emails.append(member['email'])

        return list(set(family_emails))

    def stop(self) -> None:
        """Stop the scheduler."""
        self.scheduler.shutdown()
        logger.info("Medication Scheduler stopped")
