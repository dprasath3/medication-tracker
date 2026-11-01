"""Auth entrypoint regressions, with no database or network access."""
from types import SimpleNamespace

import pytest
from pages import auth


@pytest.mark.parametrize("cloud_key", ["SUPABASE_URL", "SUPABASE_KEY"])
def test_guest_controls_cannot_be_enabled_with_cloud_configuration(monkeypatch, cloud_key):
    monkeypatch.setenv("MEDSYNC_LOCAL_DEMO", "1")
    monkeypatch.setenv(cloud_key, "configured")
    assert not auth._local_demo_enabled()
    with pytest.raises(PermissionError):
        auth._sign_in_as_guest()


def test_guest_controls_are_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MEDSYNC_LOCAL_DEMO", raising=False)
    assert not auth._local_demo_enabled()


def test_email_signin_button_state_routes_to_email_form(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "st", SimpleNamespace(
        session_state={"auth_step": "email_login"}, query_params={}))
    monkeypatch.setattr(auth, "init_session_state", lambda: None)
    monkeypatch.setattr(auth, "show_email_login", lambda: calls.append("email"))
    monkeypatch.setattr(auth, "show_phone_login", lambda: calls.append("phone"))
    auth.render()
    assert calls == ["email"]


def test_legacy_passwordless_profile_is_disabled_outside_local_demo(monkeypatch):
    notices = []
    monkeypatch.delenv("MEDSYNC_LOCAL_DEMO", raising=False)
    monkeypatch.setattr(auth, "st", SimpleNamespace(info=notices.append))
    auth.show_profile_setup()
    assert notices == ["Use Create an account to register with authentication."]
