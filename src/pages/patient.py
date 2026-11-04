"""Authorized patient history, schedule, and medication management."""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from models.family import FamilyCircleManager
from services.auth import AuthService
from services.notifications import NotificationService
from utils.authz import AuthorizationError
from utils.session import (
    db as _db, family_manager as _family_manager,
    auth_service as _auth_service, notification_service as _notification_service,
    init_session_state, current_user, sign_out, switch_to, invalidate_read_caches,
)


def init_database():
    """Compatibility shim — the legacy screens call this expecting (db, family_manager)."""
    return _db(), _family_manager()


def get_auth_service():
    return _auth_service()


def show_patient_details():
    """Show detailed view for a specific patient."""
    if "selected_patient" not in st.session_state:
        return

    db, family_manager = init_database()
    patient_id = st.session_state["selected_patient"]

    user = current_user()
    if user is None:
        st.info("Sign in to see patient details.")
        return

    # Authorized lookup — ?id=<id> is untrusted input; this refuses before
    # anything renders if the caller has no relationship to the patient
    # (see utils/authz.py).
    try:
        patient = db.get_patient(user["id"], patient_id)
    except AuthorizationError:
        st.error("You don't have access to this patient's information.")
        return

    if not patient:
        st.error("Patient not found")
        return

    from ui.primitives import page_shell
    page_shell(
        patient["name"],
        eyebrow="Patient",
        subtitle=f"Age {patient.get('age', '—')} · {patient.get('role', '').title()}",
    )

    if st.button("Back to dashboard", key="patient_back"):
        st.session_state.pop("selected_patient", None)
        # Drop only our own routing param — clearing all of them would also
        # wipe the persisted ?token= and sign the user out on next refresh.
        st.query_params.pop("id", None)
        switch_to("dashboard")

        # Create adherence chart
    st.markdown("## 7-Day Adherence Trend")

    # Get real adherence data from database
    logs = db.get_daily_dose_counts(user["id"], patient_id, days=7)

    if logs:
        dates = [datetime.fromisoformat(log["date"]) for log in logs]
        adherence_data = [(log["taken"] / log["total"] * 100) if log["total"] > 0 else 0 for log in logs]
    else:
        # Mock data if no logs
        dates = [datetime.now().date() - timedelta(days=x) for x in range(6, -1, -1)]
        adherence_data = [0] * 7

    fig = px.line(
        x=dates,
        y=adherence_data,
        title="Daily Medication Adherence",
        labels={"x": "Date", "y": "Adherence %"},
    )
    # Plotly needs literal color values (can't consume CSS vars). These match
    # the warm-cream theme; TODO expose theme_tokens() from ui.theme so this
    # can follow theme switches.
    fig.update_traces(
        line_color="#C2410C", line_width=3, marker_color="#C2410C", marker_size=8
    )
    fig.update_layout(
        yaxis_range=[0, 100],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        title_font_color="#2A241D",
        font_color="#3F372E",
        title_font_size=18,
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Medication schedule
    st.markdown("## Today's Medication Schedule")

    medications = db.get_patient_medications(user["id"], patient_id)

    if medications:
        today = datetime.now().date().isoformat()
        schedule_data = []

        for med in medications:
            for time in med["times"]:
                # Check if logged today
                log = db.get_dose_log_for_date(
                    user["id"], patient_id, med["name"], time, today
                )

                if log:
                    status = "Taken" if log[0] else "Missed"
                else:
                    status = "Pending"

                schedule_data.append(
                    {
                        "Time": time,
                        "Medication": med["name"],
                        "Dosage": med["dosage"],
                        "Status": status,
                    }
                )

        df = pd.DataFrame(schedule_data).sort_values("Time")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No medications scheduled for this patient yet.")

    # Manage medications — only for callers who can write for this patient.
    if db.can_manage_patient(user["id"], patient_id):
        inactive_meds = db.get_inactive_medications(user["id"], patient_id)
        if medications or inactive_meds:
            _render_medication_management(db, user, patient_id, medications, inactive_meds)


def _render_medication_management(db, user, patient_id: int, medications: list,
                                  inactive_meds: list) -> None:
    """Per-medication edit (dose/schedule/notes), deactivate, and reactivate.

    Writers only. Name is not editable here by design — dose history keys off
    it, so a rename would orphan past logs. Renaming means deactivate + add
    again.
    """
    st.markdown("## Manage medications")

    freq_options = ["daily", "twice_daily", "three_times_daily", "as_needed"]

    if medications:
        st.caption("Edit dose, schedule, or notes. To rename, deactivate and add it again.")

    for med in medications:
        with st.expander(f"{med['name']} — {med['dosage']}"):
            with st.form(f"edit_med_{med['id']}"):
                dosage = st.text_input("Dosage", value=med["dosage"], key=f"dose_{med['id']}")
                freq_index = (
                    freq_options.index(med["frequency"])
                    if med.get("frequency") in freq_options else 0
                )
                frequency = st.selectbox(
                    "Frequency", freq_options, index=freq_index, key=f"freq_{med['id']}"
                )

                new_times = []
                for i, t in enumerate(med["times"]):
                    try:
                        default_t = datetime.strptime(t, "%H:%M").time()
                    except (ValueError, TypeError):
                        default_t = datetime.strptime("08:00", "%H:%M").time()
                    picked = st.time_input(
                        f"Dose time {i + 1}", value=default_t, key=f"time_{med['id']}_{i}"
                    )
                    new_times.append(picked.strftime("%H:%M"))

                notes = st.text_area("Notes", value=med.get("notes") or "", key=f"notes_{med['id']}")

                if st.form_submit_button("Save changes", type="primary"):
                    try:
                        db.update_medication(
                            user["id"], med["id"],
                            dosage=dosage, frequency=frequency,
                            times=new_times, notes=notes,
                        )
                    except AuthorizationError:
                        st.error("You don't have permission to edit this medication.")
                    else:
                        invalidate_read_caches()
                        st.toast(f"Updated {med['name']}")
                        st.rerun()

            # Deactivate is a plain button (not a form submit) so it acts on click.
            if st.button("Deactivate", key=f"deact_{med['id']}"):
                try:
                    db.deactivate_medication(user["id"], med["id"])
                except AuthorizationError:
                    st.error("You don't have permission to deactivate this medication.")
                else:
                    invalidate_read_caches()
                    st.toast(f"Deactivated {med['name']}")
                    st.rerun()

    if inactive_meds:
        st.markdown("### Inactive medications")
        st.caption("Deactivated meds are kept here. Reactivate to put one back on the schedule.")
        for med in inactive_meds:
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(f"**{med['name']}** — {med['dosage']}")
            with cols[1]:
                if st.button("Reactivate", key=f"react_{med['id']}"):
                    try:
                        db.reactivate_medication(user["id"], med["id"])
                    except AuthorizationError:
                        st.error("You don't have permission to reactivate this medication.")
                    else:
                        invalidate_read_caches()
                        st.toast(f"Reactivated {med['name']}")
                        st.rerun()




def render() -> None:
    init_session_state()
    # ``show_patient_details`` reads st.session_state['selected_patient'].
    # Sync from ?id= for URL-driven navigation.
    pid = st.query_params.get("id")
    if pid is not None:
        try:
            st.session_state["selected_patient"] = int(pid)
        except (TypeError, ValueError):
            pass
    if "selected_patient" not in st.session_state:
        st.info("No patient selected. Go to Dashboard to pick one.")
        return
    show_patient_details()
