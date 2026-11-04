"""Regression cases from PR #4's final review; synthetic data, no network."""
from types import SimpleNamespace

import pytest

from pages import auth as auth_page, add_med, dashboard
from services.auth import AuthService
from utils import session
from utils.database import MedicationDB


@pytest.fixture
def db(tmp_path):
    return MedicationDB(str(tmp_path / "review.db"))


@pytest.mark.parametrize("cloud_key", ["SUPABASE_URL", "SUPABASE_KEY"])
def test_development_otp_never_exposes_code_with_cloud_configuration(db, monkeypatch, cloud_key):
    monkeypatch.setenv("MEDSYNC_DEV_SHOW_OTP", "1")
    monkeypatch.setenv("MEDSYNC_LOCAL_DEMO", "1")
    monkeypatch.setenv(cloud_key, "synthetic-config-marker")
    result = AuthService(db).request_otp("+14155550100")
    assert result["success"] is False
    assert "dev_otp" not in result
    assert db.get_active_otp("+14155550100") is None


def test_sms_disabled_does_not_claim_a_code_was_sent(db, monkeypatch):
    monkeypatch.delenv("MEDSYNC_LOCAL_DEMO", raising=False)
    monkeypatch.setenv("MEDSYNC_DEV_SHOW_OTP", "1")
    result = AuthService(db).request_otp("+14155550100")
    assert result["success"] is False
    assert "dev_otp" not in result


def test_explicit_local_demo_can_still_test_phone_auth(db, monkeypatch):
    monkeypatch.setenv("MEDSYNC_LOCAL_DEMO", "1")
    monkeypatch.setenv("MEDSYNC_DEV_SHOW_OTP", "1")
    auth = AuthService(db)
    result = auth.request_otp("+14155550100")
    assert result["success"]
    assert auth.verify_otp("+14155550100", result["dev_otp"])["success"]


@pytest.mark.parametrize("invalid", ["revoked", "expired", "missing"])
def test_loaded_profile_cannot_outlive_its_session(db, monkeypatch, invalid):
    user_id = db.add_user("Synthetic patient", "session@example.test")
    auth = AuthService(db)
    token = "synthetic-session-token"
    db.create_session(user_id, token, expiry_days=-1 if invalid == "expired" else 7)
    if invalid == "revoked":
        auth.logout(token)
    state = {"user_profile": session._profile_from_user(db.get_user_by_id(user_id)),
             "session_token": None if invalid == "missing" else token,
             "selected_patient": user_id, "snoozed_meds": {"old": "value"}}
    query = {} if invalid == "missing" else {"token": token}
    monkeypatch.setattr(session, "st", SimpleNamespace(session_state=state, query_params=query))
    monkeypatch.setattr(session, "_auth_service_singleton", lambda: auth)
    monkeypatch.setattr(session, "invalidate_read_caches", lambda: None)
    session.restore_session()
    assert state.get("user_profile") is None
    assert state.get("session_token") is None
    assert "selected_patient" not in state
    assert "token" not in query


def test_navigation_preserves_refresh_for_valid_session(db, monkeypatch):
    user_id = db.add_user("Synthetic patient", "refresh@example.test")
    auth = AuthService(db)
    token = auth._create_session_token(user_id)
    state = {"user_profile": session._profile_from_user(db.get_user_by_id(user_id)),
             "session_token": token}
    query = {}
    monkeypatch.setattr(session, "st", SimpleNamespace(session_state=state, query_params=query))
    monkeypatch.setattr(session, "_auth_service_singleton", lambda: auth)
    monkeypatch.setattr(session, "_db_singleton", lambda: db)
    session.restore_session()
    assert state["user_profile"]["id"] == user_id
    assert query["token"] == token


def test_email_query_route_does_not_override_back_button_forever(monkeypatch):
    state = {"auth_step": "phone"}
    query = {"mode": "email"}
    calls = []
    monkeypatch.setattr(auth_page, "st", SimpleNamespace(session_state=state, query_params=query))
    monkeypatch.setattr(auth_page, "init_session_state", lambda: None)
    monkeypatch.setattr(auth_page, "show_email_login", lambda: calls.append("email"))
    monkeypatch.setattr(auth_page, "show_phone_login", lambda: calls.append("phone"))
    auth_page.render()
    state["auth_step"] = "phone"  # the actual Back-to-Phone action
    auth_page.render()
    assert calls == ["email", "phone"]
    assert "mode" not in query


def test_legacy_demo_form_keeps_its_route_for_form_submission(monkeypatch):
    calls = []
    query = {"mode": "profile-setup"}
    monkeypatch.setattr(auth_page, "st", SimpleNamespace(session_state={}, query_params=query))
    monkeypatch.setattr(auth_page, "init_session_state", lambda: None)
    monkeypatch.setattr(auth_page, "show_profile_setup", lambda: calls.append("profile"))
    auth_page.render()
    auth_page.render()
    assert calls == ["profile", "profile"]


def test_read_only_caregiver_cannot_open_medication_write_form(monkeypatch):
    errors = []
    fake_db = SimpleNamespace(get_patient=lambda *a: {"id": 1, "name": "Synthetic patient"},
                              can_manage_patient=lambda *a: False)
    monkeypatch.setattr(add_med, "init_database", lambda: (fake_db, None))
    monkeypatch.setattr(add_med, "current_user", lambda: {"id": 2})
    monkeypatch.setattr(add_med, "st", SimpleNamespace(
        session_state={"add_medication_for": 1}, error=errors.append))
    add_med.show_add_medication()
    assert errors == ["You don't have permission to add medications for this patient."]


def test_dashboard_circle_names_and_alerts_are_text(monkeypatch):
    rendered = []
    monkeypatch.setattr(dashboard, "st", SimpleNamespace(markdown=lambda v, **kw: rendered.append(v)))
    monkeypatch.setattr(dashboard, "stack_open", lambda: None)
    monkeypatch.setattr(dashboard, "stack_close", lambda: None)
    monkeypatch.setattr(dashboard, "divider", lambda *a: None)
    dashboard._render_circles([{"name": "<img src=x>", "invite_code": "<b>demo</b>"}])
    dashboard._render_alerts({"alerts": ["<img src=x> low medication adherence"]})
    assert "<img src=x>" not in "".join(rendered)
    assert "&lt;img src=x&gt;" in "".join(rendered)


def test_sms_provider_errors_cannot_log_recipient_or_otp(monkeypatch, caplog):
    from services.notifications import NotificationService
    notifier = NotificationService()
    phone, code = "+14155550100", "123456"
    def fail(**kwargs):
        raise ValueError(f"Rejected {phone}: {code}")
    notifier.twilio_client = SimpleNamespace(messages=SimpleNamespace(create=fail))
    assert not notifier.send_sms(phone, code)
    assert phone not in caplog.text
    assert code not in caplog.text


@pytest.mark.parametrize("count", [0, 3, 1500, None])
def test_supabase_otp_limit_uses_total_count_and_fails_closed(count):
    from utils.database_supabase import MedicationDB as SupabaseDB
    calls = []
    class Query:
        def select(self, *args, **kwargs):
            calls.append((args, kwargs))
            return self
        def eq(self, field, value):
            calls.append((field, value))
            return self
        def gt(self, field, value):
            calls.append((field, value))
            return self
        def execute(self):
            return SimpleNamespace(data=[], count=count)
    adapter = object.__new__(SupabaseDB)  # no client or network construction
    adapter.client = SimpleNamespace(table=lambda name: Query() if name == "login_attempts" else None)
    if count is None:
        with pytest.raises(RuntimeError, match="count is unavailable"):
            adapter.get_recent_otp_requests("+14155550100")
    else:
        assert adapter.get_recent_otp_requests("+14155550100") == count
    assert calls[0] == (("id",), {"count": "exact", "head": True})
    assert ("identifier", "+14155550100") in calls
    assert ("attempt_type", "otp_request") in calls
