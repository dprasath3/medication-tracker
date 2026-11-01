"""Add Med page — split from the original monolithic web_app.py.

Behaviour is preserved verbatim from the pre-modernization app. The visual
redesign against ``design-system/MASTER.md`` happens in Commit 4.
"""

from __future__ import annotations

import sqlite3
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


def show_add_medication():
    """Show form to add medication for a patient."""
    if "add_medication_for" not in st.session_state:
        return

    db, family_manager = init_database()
    patient_id = st.session_state["add_medication_for"]

    user = current_user()
    if user is None:
        st.info("Sign in to add medications.")
        return

    # Authorized lookup — ?patient=<id> is untrusted input; this refuses
    # before the form ever renders if the caller has no relationship to
    # the patient (see utils/authz.py).
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
        "Add a medication",
        eyebrow=f"For {patient['name']}",
        subtitle="Name, dose, and when to take it. Notes are optional.",
    )

    if st.button("Back to dashboard", key="addmed_back"):
        st.session_state.pop("add_medication_for", None)
        # Drop only our own routing param — clearing all of them would also
        # wipe the persisted ?token= and sign the user out on next refresh.
        st.query_params.pop("patient", None)
        switch_to("dashboard")

    with st.form("add_medication_form"):
        col1, col2 = st.columns(2)

        with col1:
            medication_name = st.text_input(
                "Medication Name *", placeholder="e.g., Aspirin"
            )
            dosage = st.text_input("Dosage *", placeholder="e.g., 81mg")

        with col2:
            frequency = st.selectbox(
                "Frequency", ["daily", "twice_daily", "three_times_daily", "as_needed"]
            )
            notes = st.text_area("Notes", placeholder="Special instructions...")

        st.markdown("**Medication Times:**")
        if frequency == "daily":
            time1 = st.time_input(
                "Time", value=datetime.strptime("08:00", "%H:%M").time()
            )
            times = [time1.strftime("%H:%M")]
        elif frequency == "twice_daily":
            col1, col2 = st.columns(2)
            with col1:
                time1 = st.time_input(
                    "Morning", value=datetime.strptime("08:00", "%H:%M").time()
                )
            with col2:
                time2 = st.time_input(
                    "Evening", value=datetime.strptime("20:00", "%H:%M").time()
                )
            times = [time1.strftime("%H:%M"), time2.strftime("%H:%M")]
        else:
            time1 = st.time_input(
                "Time 1", value=datetime.strptime("08:00", "%H:%M").time()
            )
            time2 = st.time_input(
                "Time 2", value=datetime.strptime("14:00", "%H:%M").time()
            )
            time3 = st.time_input(
                "Time 3", value=datetime.strptime("20:00", "%H:%M").time()
            )
            times = [
                time1.strftime("%H:%M"),
                time2.strftime("%H:%M"),
                time3.strftime("%H:%M"),
            ]

        submitted = st.form_submit_button("Add Medication")

        if submitted:
            if medication_name and dosage:
                try:
                    family_manager.add_medication_for_patient(
                        user["id"],
                        patient_id,
                        {
                            "name": medication_name,
                            "dosage": dosage,
                            "frequency": frequency,
                            "times": times,
                            "notes": notes,
                        },
                    )
                except AuthorizationError:
                    st.error("You don't have permission to add medications for this patient.")
                    return
                invalidate_read_caches()
                st.success(f"Added {medication_name} for {patient['name']}")
                st.info("SMS reminders require a separately configured reminder worker.")
                st.balloons()

                # Clear form and return to dashboard
                del st.session_state["add_medication_for"]
                st.rerun()
            else:
                st.error("Please fill in medication name and dosage")




def render() -> None:
    init_session_state()
    pid = st.query_params.get("patient")
    if pid is not None:
        try:
            st.session_state["add_medication_for"] = int(pid)
        except (TypeError, ValueError):
            pass
    if "add_medication_for" not in st.session_state:
        st.info("No patient selected. Go to Dashboard to add meds for someone.")
        return
    show_add_medication()
