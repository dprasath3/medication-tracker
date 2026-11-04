"""Medication Tracker — application entry point.

Thin router. Every screen lives in ``src/pages/<route>.py`` and exposes a
``render()`` callable. This file only wires up the theme, the session state,
the auth gate, the sidebar, and ``st.navigation``.

Design source of truth: ``../design-system/MASTER.md`` and ``../CLAUDE.md``.
"""

from __future__ import annotations

import os
import sys
from html import escape

# Make ``import ui`` / ``import pages`` / ``import utils`` work when Streamlit
# launches the app from the repo root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from dotenv import load_dotenv

# Load .env before anything selects a database backend. The Streamlit
# entrypoint does not read .env on its own, so without this SUPABASE_URL /
# SUPABASE_KEY (and MEDSYNC_OTP_SECRET) are absent and db_factory silently
# falls back to SQLite.
load_dotenv()

from ui import theme
from ui.icons import icon
from utils.session import current_user, init_session_state, restore_session, sign_out

from pages import (
    auth as auth_page,
    home as home_page,
    today as today_page,
    dashboard as dashboard_page,
    patient as patient_page,
    add_med as add_med_page,
    circle as circle_page,
    onboarding as onboarding_page,
    settings as settings_page,
)


# ---------------------------------------------------------------------------
# Page config — icon is an SVG data URI derived from our pill icon.
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Medications",
    page_icon=(
        "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' "
        "viewBox='0 0 24 24' fill='none' stroke='%23C2410C' stroke-width='2' "
        "stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z'/>"
        "<path d='m8.5 8.5 7 7'/></svg>"
    ),
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Boot: theme + session state, then auth gate.
# ---------------------------------------------------------------------------
theme.inject()
init_session_state()

# Rehydrate a signed-in user from a persisted ?token= after a browser refresh,
# before the router or sidebar read current_user(). Revalidate on every rerun.
restore_session()

# Hydrate theme from the persisted user profile if we don't have one for this session.
if st.session_state.get("theme") is None:
    user = current_user()
    if user and user.get("theme"):
        st.session_state["theme"] = user["theme"]


# ---------------------------------------------------------------------------
# Sidebar shell — rendered only when signed in.
# ---------------------------------------------------------------------------
def _render_sidebar() -> None:
    user = current_user()
    if user is None:
        return

    with st.sidebar:
        st.markdown(
            f"""
            <div style="padding: var(--space-3) 0 var(--space-4) 0;">
              <div style="font-family: var(--font-heading); font-size: 1.125rem;
                          font-weight: 600; color: var(--text-strong);">
                  {escape(user['name'])}
              </div>
              <div class="muted" style="font-size: 0.875rem; margin-top: 2px;">
                  {escape(user.get('type', 'user').title())}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Navigation — auth-gated. Signed-out users see only /auth.
# ---------------------------------------------------------------------------
def _build_nav():
    if current_user() is None:
        signin = st.Page(auth_page.render, url_path="", title="Sign in", default=True)
        st.session_state["_pages"] = {"auth": signin}
        return st.navigation([signin], position="hidden")

    user = current_user()
    is_patient = user.get("type") == "patient"

    # First page is default; order controls sidebar order.
    if is_patient:
        today = st.Page(today_page.render, url_path="", title="Today's meds", default=True)
        dashboard = st.Page(dashboard_page.render, url_path="dashboard", title="Dashboard")
        pages = [today, dashboard]
    else:
        dashboard = st.Page(dashboard_page.render, url_path="", title="Dashboard", default=True)
        today = st.Page(today_page.render, url_path="today", title="Today's meds")
        pages = [dashboard, today]

    registry = {
        "today": today,
        "dashboard": dashboard,
        "patient": st.Page(patient_page.render, url_path="patients", title="Patient"),
        "add_med": st.Page(add_med_page.render, url_path="add-med", title="Add med"),
        "circle": st.Page(circle_page.render, url_path="circle", title="Family circle"),
        "onboarding": st.Page(onboarding_page.render, url_path="onboarding", title="Getting started"),
        "settings": st.Page(settings_page.render, url_path="settings", title="Settings"),
        "home": st.Page(home_page.render, url_path="home", title="Home"),
    }
    # Pages call switch_to(key) against this registry; st.switch_page needs
    # the st.Page objects registered with st.navigation, not file paths.
    st.session_state["_pages"] = registry
    pages.extend(p for k, p in registry.items() if k not in ("today", "dashboard"))
    return st.navigation(pages)


_render_sidebar()

nav = _build_nav()
nav.run()
