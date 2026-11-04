"""/dashboard — family caregiver overview.

Family members see patients they monitor, average adherence, alerts.
Patients see their circles and a shortcut to today's meds.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from ui.icons import icon
from ui.primitives import (
    page_shell,
    empty_state,
    status_pill,
    divider,
    stack_open,
    stack_close,
)
from utils.session import (
    db as _db,
    family_manager as _family_manager,
    current_user,
    init_session_state,
    cached_user_family_circles,
    switch_to,
)


def render() -> None:
    init_session_state()
    user = current_user()
    if user is None:
        st.info("Sign in to see the dashboard.")
        return

    db = _db()
    family_manager = _family_manager()

    page_shell(
        "Dashboard",
        eyebrow=f"Signed in as {user.get('type', 'user').title()}",
        subtitle=f"Welcome back, {user['name']}.",
    )

    if user["type"] == "patient":
        _render_patient_shortcut()

    circles = cached_user_family_circles(user["id"])

    if not circles:
        empty_state(
            "No family circles yet",
            "Create a circle to start monitoring together, or join one with an invite code.",
        )
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button("Create a circle", key="dash_create", type="primary", use_container_width=True):
                switch_to("circle")
        with cols[1]:
            if st.button("Join a circle", key="dash_join", use_container_width=True):
                # Set the session flag the circle page reads directly — query
                # params do not reliably survive st.switch_page.
                st.session_state["show_join_circle"] = True
                switch_to("circle")
        return

    # Circle creators can promote a second caregiver to write access.
    if any(c.get("created_by") == user["id"] for c in circles):
        if st.button("Manage caregivers", key="dash_manage_caregivers"):
            st.session_state["show_manage_circle"] = True
            switch_to("circle")

    data = family_manager.get_family_dashboard_data(user["id"])

    if data["total_patients"] == 0:
        _render_circles(circles)
        divider(5)
        empty_state(
            "No patients yet",
            "Add someone to a circle to start tracking their medications.",
        )
        # Adding a patient happens through the circle screen, which is the only
        # place that creates a patient row (via "add a patient now").
        if st.button("Add a patient", key="dash_add_patient", type="primary"):
            switch_to("circle")
        return

    _render_metrics(data)
    divider(5)
    _render_alerts(data)
    _render_patient_grid(db, data, user["id"])


# ---------------------------------------------------------------------------

def _render_patient_shortcut() -> None:
    """Prominent card at top of dashboard for patient personas."""
    st.markdown(
        """
        <div class="med-card page-fade" style="
            margin-bottom: var(--space-6);
            background: linear-gradient(135deg, var(--accent-subtle) 0%, var(--surface-card) 100%);
            border-color: var(--border-strong);">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:var(--space-5);">
            <div>
              <p class="eyebrow" style="color:var(--accent);">Right now</p>
              <h2 style="margin:0;">Your medications for today</h2>
              <p class="muted" style="margin: var(--space-2) 0 0 0;">Check them off as you take them.</p>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open today's list", key="dash_open_today", type="primary"):
        switch_to("today")
    divider(6)


def _render_circles(circles: list[dict]) -> None:
    st.markdown('<h2>Your family circles</h2>', unsafe_allow_html=True)
    stack_open()
    for c in circles:
        st.markdown(
            f"""
            <div class="med-card">
              <h3 style="margin:0 0 var(--space-1) 0;">{escape(c['name'])}</h3>
              <p class="muted tabular" style="margin:0;font-size:0.9375rem;">
                Invite code: <span style="font-family:var(--font-mono);color:var(--text);">{escape(c['invite_code'])}</span>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    stack_close()


def _render_metrics(data: dict) -> None:
    st.markdown('<h2 style="margin-top: var(--space-6);">Overview</h2>', unsafe_allow_html=True)
    cols = st.columns(4)
    with cols[0]:
        st.metric("Patients", data["total_patients"])
    with cols[1]:
        adh = data["average_adherence"]
        st.metric("Avg adherence", f"{adh}%" if adh > 0 else "—")
    with cols[2]:
        st.metric("Need attention", data["patients_needing_attention"])
    with cols[3]:
        st.metric("Circles", len(data["family_circles"]))


def _render_alerts(data: dict) -> None:
    alerts = data.get("alerts") or []
    if not alerts:
        return
    st.markdown('<h2 style="margin-top: var(--space-6);">Alerts</h2>', unsafe_allow_html=True)
    for alert in alerts:
        kind = "warning" if "low medication adherence" in alert else "success"
        bg = "var(--warning-subtle)" if kind == "warning" else "var(--success-subtle)"
        fg = "var(--warning)" if kind == "warning" else "var(--success)"
        st.markdown(
            f'<div class="med-card page-fade" style="background:{bg};color:{fg};'
            f'border-color:{fg};padding: var(--space-4) var(--space-5);">{escape(alert)}</div>',
            unsafe_allow_html=True,
        )
    divider(5)


def _render_patient_grid(db, data: dict, caller_id: int) -> None:
    st.markdown('<h2 style="margin-top: var(--space-6);">Patients</h2>', unsafe_allow_html=True)
    stack_open()
    for p in data["patients_status"]:
        adherence = p["adherence_rate"]
        pill_kind = "success" if adherence >= 90 else "warning" if adherence >= 70 else "error"
        adh_display = f"{adherence:.0f}% adherence" if adherence > 0 else "No data yet"
        # Only offer write actions (add med, log doses) to a caller who holds
        # manage_meds for this patient. A view-only member sees just "View".
        can_write = db.can_manage_patient(caller_id, p["id"])
        st.markdown(
            f"""
            <div class="med-card">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:var(--space-4);">
                <div>
                  <h3 style="margin:0 0 var(--space-1) 0;">{escape(p['name'])}</h3>
                  <p class="muted" style="margin:0;font-size:0.9375rem;">
                    Age {escape(str(p['age']))} · {escape(p['family_circle_name'])} · {p['total_medications']} meds
                  </p>
                </div>
                <div>{status_pill(adh_display, pill_kind)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if can_write:
            cols = st.columns([1, 1, 1])
            with cols[0]:
                if st.button("View", key=f"view_{p['id']}", use_container_width=True):
                    st.session_state["selected_patient"] = p["id"]
                    switch_to("patient")
            with cols[1]:
                if st.button("Add med", key=f"addmed_{p['id']}", use_container_width=True):
                    st.session_state["add_medication_for"] = p["id"]
                    switch_to("add_med")
            with cols[2]:
                if st.button("Log today", key=f"logtoday_{p['id']}", type="primary", use_container_width=True):
                    switch_to("today")
        else:
            if st.button("View", key=f"view_{p['id']}", use_container_width=True):
                st.session_state["selected_patient"] = p["id"]
                switch_to("patient")
        divider(3)
    stack_close()
