"""Session-level singletons and helpers shared across all pages.

Wraps DB, auth service, and notification service in Streamlit's cache to avoid
re-instantiating on every rerun (perf), and centralises initial session state
so every page starts from a known baseline.
"""

from __future__ import annotations

import streamlit as st

from models.family import FamilyCircleManager
from services.auth import AuthService
from services.notifications import NotificationService
from utils.db_factory import get_database


@st.cache_resource(show_spinner=False)
def _db_singleton():
    return get_database()


@st.cache_resource(show_spinner=False)
def _notification_service_singleton():
    return NotificationService()


@st.cache_resource(show_spinner=False)
def _family_manager_singleton():
    return FamilyCircleManager(_db_singleton())


@st.cache_resource(show_spinner=False)
def _auth_service_singleton():
    return AuthService(_db_singleton(), _notification_service_singleton())


def db():
    return _db_singleton()


def family_manager():
    return _family_manager_singleton()


def auth_service():
    return _auth_service_singleton()


def notification_service():
    return _notification_service_singleton()


def init_session_state() -> None:
    """Ensure baseline keys exist on session_state. Idempotent."""
    defaults = {
        "user_profile": None,
        "onboarding_complete": False,
        "family_circles": [],
        "show_login": True,
        "show_register": False,
        "auth_step": "phone",
        "auth_phone": None,
        "otp_sent_time": None,
        "session_token": None,
        "snoozed_meds": {},
        "theme": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def current_user() -> dict | None:
    """Return the logged-in user profile or None."""
    return st.session_state.get("user_profile")


def is_authenticated() -> bool:
    return current_user() is not None


# ---------------------------------------------------------------------------
# Persistent login
#
# Streamlit's session_state is per-connection and is wiped on a full browser
# reload, but the auth token in ``user_sessions`` is durable server-side. We
# stash the token in the URL (``?token=``) at login so a refresh can re-resolve
# it here on boot, before the router decides which pages to show.
#
# The token lives in the URL rather than session_state alone because that is
# the only place that survives a reload without adding a cookie component. It
# is a 32-byte urlsafe secret with a 7-day server-side expiry that is
# invalidated on sign-out; the same pattern the email-verify / reset links use.
# ---------------------------------------------------------------------------

TOKEN_PARAM = "token"


def _profile_from_user(user: dict) -> dict:
    """Map a DB user row to the session ``user_profile`` shape the pages expect."""
    role = user.get("role", "patient")
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user.get("email", ""),
        "age": user.get("age"),
        "type": role,
        "phone": user.get("phone", ""),
        "relationship": "patient" if role == "patient" else "family_member",
        "theme": user.get("theme"),
    }


def persist_session_token(token: str) -> None:
    """Record the auth token so the session survives a page refresh.

    Call this at every successful login. Stores the token in session_state
    (for this connection) and in the URL (so a reload can rehydrate it via
    ``restore_session``).
    """
    st.session_state["session_token"] = token
    if token:
        st.query_params[TOKEN_PARAM] = token


def restore_session() -> None:
    """Rehydrate the signed-in user from a persisted token. Idempotent.

    Validate on every rerun, including already-loaded profiles, so revocation
    and expiry take effect on the next interaction. URL transport is retained
    for compatibility; it is a documented security limitation.
    """
    previous_profile = st.session_state.get("user_profile")
    token = st.session_state.get("session_token") or st.query_params.get(TOKEN_PARAM)
    if not token:
        if previous_profile is not None:
            _clear_session_state()
        return

    user = _auth_service_singleton().validate_session(token)
    if not user:
        _clear_session_state()
        return

    st.session_state["session_token"] = token
    st.session_state["user_profile"] = _profile_from_user(user)
    if st.query_params.get(TOKEN_PARAM) != token:
        st.query_params[TOKEN_PARAM] = token

    if st.session_state.get("theme") is None and user.get("theme"):
        st.session_state["theme"] = user["theme"]

    if previous_profile is not None and previous_profile["id"] == user["id"]:
        return

    try:
        circles = _db_singleton().get_user_family_circles(user["id"])
        st.session_state["onboarding_complete"] = len(circles) > 0
    except Exception:
        # Best effort — a dashboard/onboarding read failing must not block login.
        pass


def switch_to(page_key: str) -> None:
    """Switch to a page from the registry web_app builds each run.

    st.switch_page must receive the st.Page objects passed to st.navigation;
    file-path strings only work with the legacy pages/ directory router.
    """
    page = st.session_state.get("_pages", {}).get(page_key)
    if page is None:
        raise KeyError(f"No page registered for {page_key!r}")
    st.switch_page(page)


def sign_out() -> None:
    """Clear all session state related to the user's session, keeping the DB caches."""
    token = st.session_state.get("session_token")
    if token:
        try:
            auth_service().logout(token)
        except Exception:
            pass
    _clear_session_state()


def _clear_session_state() -> None:
    """Discard identity, routing, and cached reads after logout/invalid auth."""
    # Drop the persisted token from the URL so a post-logout refresh does not
    # silently sign the user back in on a still-valid token.
    st.query_params.pop(TOKEN_PARAM, None)
    for key in list(st.session_state.keys()):
        if key in {"theme"}:
            continue
        del st.session_state[key]
    invalidate_read_caches()
    init_session_state()


# ---------------------------------------------------------------------------
# Cached reads
#
# Wraps the hottest DB reads with @st.cache_data. Callers should call
# ``invalidate_read_caches()`` after any mutation (log_dose, add_medication,
# add_patient, ...) so the next read sees fresh data.
# ---------------------------------------------------------------------------


# Cache keys include caller_id: entries are (caller, patient)-scoped so an
# authorized read is never served from cache to a different, unauthorized
# caller within the TTL. AuthorizationError propagates — st.cache_data does
# not memoize raised exceptions.


@st.cache_data(ttl=30, show_spinner=False)
def cached_patient_medications(caller_id: int, patient_id: int):
    return _db_singleton().get_patient_medications(caller_id, patient_id)


@st.cache_data(ttl=15, show_spinner=False)
def cached_dose_log(caller_id: int, patient_id: int, medication_name: str, scheduled_time: str, date: str):
    return _db_singleton().get_dose_log_for_date(
        caller_id, patient_id, medication_name, scheduled_time, date
    )


@st.cache_data(ttl=30, show_spinner=False)
def cached_family_patients_status(family_member_id: int):
    return _db_singleton().get_family_patients_status(family_member_id)


@st.cache_data(ttl=60, show_spinner=False)
def cached_user_family_circles(user_id: int):
    return _db_singleton().get_user_family_circles(user_id)


def invalidate_read_caches() -> None:
    """Clear all cached reads. Call after any DB mutation."""
    cached_patient_medications.clear()
    cached_dose_log.clear()
    cached_family_patients_status.clear()
    cached_user_family_circles.clear()
