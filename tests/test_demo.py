"""Verify demo isolation without starting a worker or contacting providers."""
import importlib.util
from pathlib import Path
import sqlite3

import pytest

spec = importlib.util.spec_from_file_location("medsync_demo", Path(__file__).parents[1] / "scripts/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_demo_clears_inherited_service_credentials():
    original = {key: "sentinel" for key in (
        "SUPABASE_URL", "SUPABASE_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER", "EMAIL_ADDRESS", "EMAIL_PASSWORD", "MEDSYNC_DEV_SHOW_OTP",
    )}
    env = demo.demo_environment(original)
    assert all(env[key] == "" for key in original)
    assert all(value == "sentinel" for value in original.values())
    assert env["PYTHON_DOTENV_DISABLED"] == "1"


def test_demo_is_real_sqlite_with_no_phone_numbers_and_permission_levels(tmp_path):
    from utils.database import MedicationDB
    ids = demo.seed_demo(tmp_path, "Demo-only-Password1!")
    db = MedicationDB(str(tmp_path / "data/medications.db"))
    assert all(user["phone"] is None for user in db.get_users())
    assert len(db.get_patient_medications(ids["viewer"], ids["patient"])) == 3
    assert not db.can_manage_patient(ids["viewer"], ids["patient"])
    assert db.can_manage_patient(ids["caregiver"], ids["patient"])
    with pytest.raises(FileExistsError):
        demo.seed_demo(tmp_path, "Demo-only-Password1!")
    with sqlite3.connect(db.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM dose_logs").fetchone()[0] == 19
