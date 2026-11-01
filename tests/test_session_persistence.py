"""P0 — persistent login: a session token survives a "page refresh".

A Streamlit refresh drops all in-memory session_state, so ``restore_session``
(utils/session.py) must be able to re-resolve the signed-in user from the token
alone — the token being the only thing carried across the reload in ``?token=``.
These tests exercise that durable round-trip against the SQLite backend, plus
the profile mapping the boot path repopulates, without needing a browser.
"""

import pytest

from services.auth import AuthService
from utils.database import MedicationDB
from utils.session import _profile_from_user


@pytest.fixture
def db(tmp_path):
    return MedicationDB(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def auth(db):
    return AuthService(db=db)


def _register(auth):
    """Register a phone user and return (user, token) as a login would."""
    result = auth.complete_phone_registration(
        phone="+14155550100", name="Pat Patient", age=78, role="patient"
    )
    assert result["success"]
    return result["user"], result["session_token"]


def test_token_from_a_fresh_connection_resolves_to_the_same_user(db, auth):
    """The core of restore_session: validating the token on a brand-new
    AuthService/DB (a fresh process/connection) returns the logged-in user."""
    user, token = _register(auth)

    fresh = AuthService(db=MedicationDB(db_path=db.db_path))
    restored = fresh.validate_session(token)

    assert restored is not None
    assert restored["id"] == user["id"]
    assert restored["name"] == "Pat Patient"


def test_restored_profile_has_the_shape_pages_expect(db, auth):
    user, token = _register(auth)
    restored = auth.validate_session(token)

    profile = _profile_from_user(restored)
    assert profile["id"] == user["id"]
    assert profile["type"] == "patient"          # pages branch on ``type``
    assert profile["relationship"] == "patient"  # role-derived, not hardcoded


def test_family_member_profile_maps_relationship_from_role(db, auth):
    result = auth.complete_phone_registration(
        phone="+14155550111", name="Cara Caregiver", role="family_member"
    )
    profile = _profile_from_user(auth.validate_session(result["session_token"]))
    assert profile["type"] == "family_member"
    assert profile["relationship"] == "family_member"


def test_signed_out_token_no_longer_resolves(db, auth):
    """After logout the token is dead, so a refresh cannot rehydrate from it."""
    _user, token = _register(auth)
    assert auth.validate_session(token) is not None

    auth.logout(token)
    assert auth.validate_session(token) is None


def test_expired_token_does_not_resolve(db, auth):
    """A session past its expiry must not rehydrate a user on refresh."""
    user, _token = _register(auth)
    # Mint a session that is already expired.
    stale = "expired-token-value"
    db.create_session(user_id=user["id"], session_token=stale, expiry_days=-1)
    assert auth.validate_session(stale) is None


def test_blank_app_base_url_uses_local_default(monkeypatch):
    import importlib
    from services import auth as auth_module
    monkeypatch.setenv("APP_BASE_URL", "")
    try:
        importlib.reload(auth_module)
        assert auth_module.APP_BASE_URL == "http://localhost:8501"
    finally:
        monkeypatch.delenv("APP_BASE_URL", raising=False)
        importlib.reload(auth_module)
