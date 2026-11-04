"""Finding 4 + 5 — OTP security properties (HARDENING_SPRINT.md).

Proves the properties that matter for phone-OTP auth, against the SQLite
backend with a tmp DB:
- a wrong code is rejected
- an expired code is rejected even when correct
- a code cannot be replayed after it succeeds once
- too many wrong guesses lock the account, and the correct code is then
  refused while locked
- OTP requests are rate limited once recent failures pile up
- the stored value is a keyed HMAC, not a trivially reversible plain digest

Each test is named for the property it proves.
"""

import hashlib

import pytest

from services.auth import AuthService
from utils.database import MedicationDB

# A number phonenumbers accepts as a valid US E.164.
PHONE = "+14155550100"
CODE = "123456"


@pytest.fixture
def db(tmp_path):
    return MedicationDB(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def auth(db, monkeypatch):
    # Explicit disposable local mode returns a test code without sending SMS.
    monkeypatch.setenv("MEDSYNC_LOCAL_DEMO", "1")
    monkeypatch.setenv("MEDSYNC_DEV_SHOW_OTP", "1")
    return AuthService(db=db)


def _seed_otp(db, auth, code=CODE, purpose="register", expiry_minutes=5):
    """Store an OTP with a known code, bypassing SMS. Returns the normalized
    phone the OTP is filed under."""
    phone = auth.normalize_phone(PHONE)
    db.create_otp(phone, auth._hash_otp(code), purpose=purpose, expiry_minutes=expiry_minutes)
    return phone


# --- Verification rejects bad codes -----------------------------------------

def test_otp_verification_fails_on_wrong_code(db, auth):
    _seed_otp(db, auth)
    result = auth.verify_otp(PHONE, "000000")
    assert result["success"] is False


def test_otp_verification_fails_on_expired_code_even_when_correct(db, auth):
    # Negative expiry => the OTP is already past its expires_at when stored.
    _seed_otp(db, auth, expiry_minutes=-1)
    result = auth.verify_otp(PHONE, CODE)  # correct code, but expired
    assert result["success"] is False


def test_otp_cannot_be_reused_after_a_successful_verification(db, auth):
    _seed_otp(db, auth)
    first = auth.verify_otp(PHONE, CODE)
    assert first["success"] is True

    replay = auth.verify_otp(PHONE, CODE)  # same code, second time
    assert replay["success"] is False


# --- Wrong guesses lock the account -----------------------------------------

def test_otp_locks_out_after_max_attempts_and_then_refuses_correct_code(db, auth):
    phone = _seed_otp(db, auth)

    # Burn through every allowed wrong guess.
    for _ in range(auth.MAX_OTP_ATTEMPTS):
        assert auth.verify_otp(PHONE, "000000")["success"] is False

    # The next attempt trips the lockout — and the correct code is refused.
    assert auth.verify_otp(PHONE, CODE)["success"] is False
    assert db.is_locked_out(phone) is True
    # Still refused on a subsequent correct attempt while locked out.
    assert auth.verify_otp(PHONE, CODE)["success"] is False


# --- Requests are rate limited ----------------------------------------------

def test_otp_requests_are_rate_limited_after_repeated_failures(db, auth):
    phone = auth.normalize_phone(PHONE)
    for _ in range(auth.MAX_OTP_REQUESTS):
        db.record_login_attempt(phone, "phone_otp", False)

    blocked = auth.request_otp(PHONE)
    assert blocked["success"] is False


def test_otp_request_succeeds_when_under_the_rate_limit(db, auth):
    # Control: with no recent failures, a request is allowed. Guards against a
    # rate limiter that simply denies everything.
    result = auth.request_otp(PHONE)
    assert result["success"] is True


# --- Storage is a keyed hash, not a reversible digest -----------------------

def test_otp_is_stored_as_keyed_hmac_not_plain_sha256(db, auth):
    """Finding 4: a 6-digit OTP hashed with bare SHA-256 is reversed by brute
    force in ~1s. The stored value must be the keyed HMAC, not that digest."""
    phone = _seed_otp(db, auth)
    stored = db.get_active_otp(phone)["otp_hash"]

    assert stored != hashlib.sha256(CODE.encode()).hexdigest()  # old, crackable
    assert stored == auth._hash_otp(CODE)  # keyed HMAC, stable within the process


def test_repeated_otp_requests_are_limited_without_wrong_guesses(db, auth):
    for _ in range(auth.MAX_OTP_REQUESTS):
        assert auth.request_otp(PHONE)["success"] is True
    assert auth.request_otp(PHONE)["success"] is False
    assert db.get_recent_otp_requests(auth.normalize_phone(PHONE)) == 3


def test_otp_request_window_expires(db, auth):
    import sqlite3
    from datetime import datetime, timedelta
    for _ in range(auth.MAX_OTP_REQUESTS):
        auth.request_otp(PHONE)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute("UPDATE login_attempts SET timestamp = ?",
                     ((datetime.now() - timedelta(minutes=11)).isoformat(),))
    assert auth.request_otp(PHONE)["success"] is True


def test_otp_and_full_phone_are_not_written_to_logs(auth, monkeypatch, caplog):
    monkeypatch.setattr(auth, "_generate_otp", lambda: CODE)
    with caplog.at_level("INFO"):
        assert auth.request_otp(PHONE)["success"]
    assert CODE not in caplog.text
    assert PHONE not in caplog.text


def test_failed_sms_delivery_still_counts_toward_request_limit(db):
    class FailingNotifier:
        twilio_client = object()
        def send_sms(self, *args):
            return False
    auth = AuthService(db, FailingNotifier())
    for _ in range(auth.MAX_OTP_REQUESTS):
        assert "Failed to send" in auth.request_otp(PHONE)["error"]
    assert "Too many OTP requests" in auth.request_otp(PHONE)["error"]
