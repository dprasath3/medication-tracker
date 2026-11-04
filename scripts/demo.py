"""Run the real application with a disposable, synthetic SQLite dataset.

No production DB, phone numbers, notification credentials, or worker are used.
Run from the repository root: python scripts/demo.py
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def demo_environment(source: dict[str, str]) -> dict[str, str]:
    env = source.copy()
    for key in (
        "SUPABASE_URL", "SUPABASE_KEY", "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "EMAIL_ADDRESS",
        "EMAIL_PASSWORD", "MEDSYNC_DEV_SHOW_OTP",
    ):
        # Empty values also prevent load_dotenv(override=False) from filling them.
        env[key] = ""
    env.update(
        PYTHON_DOTENV_DISABLED="1", MEDSYNC_LOCAL_DEMO="1",
        MEDSYNC_OTP_SECRET=secrets.token_hex(32), APP_TIMEZONE="UTC",
        APP_BASE_URL="http://localhost:8501", SMTP_SERVER="localhost", SMTP_PORT="587",
        STREAMLIT_BROWSER_GATHER_USAGE_STATS="false",
    )
    return env


def seed_demo(directory: Path, password: str) -> dict[str, int]:
    """Create a NEW local DB. Refuse to overwrite any existing data."""
    import bcrypt
    from utils.database import MedicationDB

    path = directory / "data" / "medications.db"
    if path.exists():
        raise FileExistsError("Demo seeding requires a new database")
    db = MedicationDB(str(path))
    caregiver = db.add_user("Alex Rivera (demo)", "caregiver@example.test", role="family_member")
    patient = db.add_user("Jordan Rivera (demo)", "patient@example.test", age=72)
    viewer = db.add_user("Taylor Rivera (demo)", "viewer@example.test", role="family_member")
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    for user_id in (caregiver, patient, viewer):
        db.create_user_credentials(user_id, hashed)
    _, invite = db.create_family_circle("Rivera family · synthetic demo", caregiver)
    db.join_family_circle(invite, patient, "patient")
    db.join_family_circle(invite, viewer, "caregiver")
    meds = [
        ("Sample A (demo)", "1 demo tablet", "daily", ["08:00"]),
        ("Sample B (demo)", "1 demo capsule", "daily", ["13:00"]),
        ("Sample C (demo)", "1 demo tablet", "daily", ["20:00"]),
    ]
    for name, dosage, frequency, times in meds:
        db.add_medication(caregiver, patient, name, dosage, frequency, times,
                          "Synthetic example only — not a medication instruction.")
    # Seed a small historical dataset. The application API intentionally logs only today.
    with sqlite3.connect(path) as conn:
        for offset in range(1, 7):
            day = (date.today() - timedelta(days=offset)).isoformat()
            for index, (name, _, _, times) in enumerate(meds):
                taken = not (offset in (2, 5) and index == 2)
                conn.execute(
                    """INSERT INTO dose_logs (patient_id, medication_name, scheduled_time,
                       taken, actual_time, date, timestamp, logged_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (patient, name, times[0], taken, times[0], day, f"{day}T08:05:00", patient),
                )
    db.log_dose(patient, patient, meds[0][0], "08:00", True, "08:05")
    return {"patient": patient, "caregiver": caregiver, "viewer": viewer}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()
    env = demo_environment(dict(os.environ))
    env["APP_BASE_URL"] = f"http://localhost:{args.port}"
    password = "Demo1!" + secrets.token_urlsafe(12)
    with tempfile.TemporaryDirectory(prefix="medsync-demo-") as folder:
        seed_demo(Path(folder), password)
        print(f"\nSynthetic demo: http://localhost:{args.port}", flush=True)
        print("Choose 'Use email instead'. Accounts:", flush=True)
        print("  patient@example.test | caregiver@example.test | viewer@example.test", flush=True)
        print(f"Temporary password for all three: {password}", flush=True)
        print("No SMS/email credentials. No worker. Data is removed on exit.\n", flush=True)
        try:
            subprocess.run(
                [sys.executable, "-m", "streamlit", "run", str(ROOT / "src/web_app.py"),
                 "--server.address=127.0.0.1", f"--server.port={args.port}",
                 "--server.headless=true", "--browser.gatherUsageStats=false"],
                cwd=folder, env=env, check=True,
            )
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
