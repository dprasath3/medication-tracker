"""Circle page — split from the original monolithic web_app.py.

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


def show_create_family_circle():
    """Show family circle creation form."""
    from ui.primitives import page_shell

    page_shell(
        "Create a family circle",
        eyebrow="Family circle",
        subtitle="A circle links caregivers to patients so everyone sees the same schedule.",
    )

    if st.button("Back", key="circle_create_back"):
        st.session_state.show_create_circle = False
        st.rerun()

    with st.form("create_family_circle"):
        circle_name = st.text_input(
            "Family Circle Name *", placeholder="e.g., Johnson Family Care"
        )
        description = st.text_area(
            "Description (Optional)",
            placeholder="Brief description of your family circle...",
        )

        st.markdown("---")
        st.markdown("** Who will you be monitoring?**")
        add_patient_now = st.checkbox(
            "I want to add a patient now (elderly family member)"
        )

        if add_patient_now:
            st.markdown("**Patient Information:**")
            col1, col2 = st.columns(2)
            with col1:
                patient_name = st.text_input(
                    "Patient Name", placeholder="Enter patient's full name"
                )
                patient_age = st.number_input(
                    "Patient Age", min_value=1, max_value=120, value=75
                )
            with col2:
                patient_email = st.text_input(
                    "Patient Email (Optional)", placeholder="patient@email.com"
                )
                patient_phone = st.text_input(
                    "Patient Phone", placeholder="+1 (555) 123-4567"
                )

            relationship = st.selectbox(
                "Your relationship to this patient:",
                ["Parent", "Grandparent", "Spouse", "Other Family", "Care Recipient"],
            )

        submitted = st.form_submit_button(
            "Create Family Circle", use_container_width=True
        )

        if submitted:
            if circle_name:
                db, family_manager = init_database()
                user = st.session_state.user_profile

                # Create family circle
                circle_id, invite_code = family_manager.create_family_circle(
                    circle_name, user["id"]
                )

                # Add patient if specified
                patient_id = None
                if add_patient_now and patient_name:
                    patient_id = db.add_user(
                        patient_name,
                        patient_email or None,
                        patient_age,
                        "patient",
                        patient_phone,
                    )
                    db.join_family_circle(invite_code, patient_id, "patient")

                    # Store in session
                st.session_state.family_circles.append(
                    {
                        "id": circle_id,
                        "name": circle_name,
                        "invite_code": invite_code,
                        "patient_id": patient_id,
                    }
                )

                invalidate_read_caches()
                st.session_state.show_create_circle = False
                st.session_state.circle_created = True
                st.session_state.new_invite_code = invite_code
                # Remember the patient we just created (if any) so the success
                # screen's "Add Medications" can jump straight to their form.
                st.session_state.new_patient_id = patient_id
                st.rerun()
            else:
                st.error("Please enter a family circle name.")



def show_circle_created_success():
    """Show success message after circle creation."""
    invite_code = st.session_state.get("new_invite_code")

    st.markdown(
        """
 <div class="success-message">
 <h2> Family Circle Created Successfully!</h2>
 <p>Your family care network is now active</p>
 </div>
 """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Invite Family Members")
        st.info(f"""
        **Invite Code:** `{invite_code}`
        
        Share this code with family members so they can join your care circle and help monitor medications together.
        """)

    with col2:
        st.markdown("### Next Steps")
        new_patient_id = st.session_state.get("new_patient_id")
        if new_patient_id:
            if st.button("Add Medications", key="add_first_med", use_container_width=True):
                st.session_state.circle_created = False
                # Set the session key the add-med page reads directly — query
                # params do not reliably survive st.switch_page.
                st.session_state["add_medication_for"] = new_patient_id
                switch_to("add_med")
        else:
            st.caption(
                "Add a patient to this circle (or share the invite code) to start "
                "tracking medications."
            )

        if st.button("Go to Dashboard", key="go_dashboard", use_container_width=True):
            st.session_state.circle_created = False
            st.session_state.onboarding_complete = True
            switch_to("dashboard")



def show_join_family_circle():
    """Show join family circle form."""
    from ui.primitives import page_shell

    page_shell(
        "Join a family circle",
        eyebrow="Family circle",
        subtitle="Enter the invite code someone shared with you.",
    )

    if st.button("Back", key="circle_join_back"):
        st.session_state.show_join_circle = False
        st.rerun()

    with st.form("join_family_circle"):
        invite_code = st.text_input(
            "Invite Code *", placeholder="e.g., A1B2C3D4", max_chars=8
        )

        submitted = st.form_submit_button(
            "Join Family Circle", use_container_width=True
        )

        if submitted:
            if invite_code:
                db, family_manager = init_database()
                user = st.session_state.user_profile

                # Attempt to join circle
                success = db.join_family_circle(
                    invite_code.upper(),
                    user["id"],
                    user.get("relationship", "family_member"),
                )

                if success:
                    invalidate_read_caches()
                    st.success("Successfully joined the family circle!")
                    st.session_state.show_join_circle = False
                    st.session_state.onboarding_complete = True
                    st.balloons()
                    st.rerun()
                else:
                    st.error(
                        "Invalid invite code or you're already a member of this circle."
                    )
            else:
                st.error("Please enter an invite code.")




def show_manage_caregivers():
    """Let a circle creator grant/revoke manage_meds for other caregivers."""
    from ui.primitives import page_shell, divider

    db, _ = init_database()
    user = current_user()

    page_shell(
        "Manage caregivers",
        eyebrow="Family circle",
        subtitle="Give a trusted family member permission to add and log medications.",
    )

    if st.button("Back", key="manage_back"):
        st.session_state.pop("show_manage_circle", None)
        switch_to("dashboard")

    # Only circles this user created can have their permissions changed.
    circles = [
        c for c in db.get_user_family_circles(user["id"])
        if c.get("created_by") == user["id"]
    ]
    if not circles:
        st.info("You can only manage circles you created.")
        return

    for circle in circles:
        st.markdown(f"### {circle['name']}")
        members = db.get_family_circle_members(circle["id"])
        # Patients aren't caregivers; the creator already has full access.
        caregivers = [
            m for m in members
            if m["role"] != "patient" and m["id"] != user["id"]
        ]
        if not caregivers:
            st.caption("No other caregivers yet. Share the invite code to add one.")
            divider(4)
            continue

        for m in caregivers:
            can_manage = "manage_meds" in m["permissions"]
            new_val = st.checkbox(
                f"{m['name']} can add and log medications",
                value=can_manage,
                key=f"manage_{circle['id']}_{m['id']}",
            )
            if new_val != can_manage:
                try:
                    db.set_member_manage_meds(user["id"], circle["id"], m["id"], new_val)
                    invalidate_read_caches()
                    st.toast(f"Updated {m['name']}'s access")
                    st.rerun()
                except PermissionError:
                    st.error("Only the circle creator can change permissions.")
        divider(4)


def render() -> None:
    init_session_state()
    action = st.query_params.get("action")
    if action == "join" or st.session_state.get("show_join_circle"):
        show_join_family_circle()
    elif st.session_state.get("circle_created"):
        show_circle_created_success()
    elif action == "manage" or st.session_state.get("show_manage_circle"):
        show_manage_caregivers()
    else:
        show_create_family_circle()
