"""/settings — profile, theme picker, sign out."""

from __future__ import annotations

from html import escape

import streamlit as st

from ui.theme import THEMES, THEME_LABELS, THEME_DESCRIPTIONS, get_current_theme, set_theme
from ui.primitives import page_shell, divider, card
from utils.session import init_session_state, current_user, sign_out


def render() -> None:
    init_session_state()
    user = current_user()
    if user is None:
        st.info("Sign in to change settings.")
        return

    page_shell(
        "Settings",
        eyebrow="Your account",
        subtitle="Preferences and profile. Changes apply immediately.",
    )

    st.markdown('<h2 style="margin-top: 2rem;">Theme</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="muted" style="margin-bottom: 1rem;">Pick the palette that feels right. '
        'Your choice is saved.</p>',
        unsafe_allow_html=True,
    )

    current = get_current_theme()
    picked = st.radio(
        "Theme",
        options=list(THEMES),
        index=list(THEMES).index(current) if current in THEMES else 0,
        format_func=lambda k: f"{THEME_LABELS[k]} — {THEME_DESCRIPTIONS[k]}",
        label_visibility="collapsed",
        key="theme_picker",
    )
    if picked != current:
        set_theme(picked)
        st.rerun()

    divider(6)

    st.markdown('<h2>Profile</h2>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="med-card"><p style="margin:0;"><strong>{escape(user["name"])}</strong></p>'
        f'<p class="muted" style="margin:0.25rem 0 0 0;">{escape(user.get("email") or "")}</p>'
        f'<p class="subtle" style="margin:0.25rem 0 0 0; font-size: 0.9375rem;">'
        f'{escape(user.get("type", "user").title())}</p></div>',
        unsafe_allow_html=True,
    )

    divider(6)

    if st.button("Sign out", key="signout"):
        sign_out()
        st.rerun()
