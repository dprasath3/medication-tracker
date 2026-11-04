"""Phone/email authentication pages and explicitly gated local demo flows."""

from __future__ import annotations

import os
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
from utils.db_factory import local_demo_enabled as _local_demo_enabled
from utils.session import (
    db as _db, family_manager as _family_manager,
    auth_service as _auth_service, notification_service as _notification_service,
    init_session_state, current_user, sign_out, persist_session_token,
)


def init_database():
    """Compatibility shim — the legacy screens call this expecting (db, family_manager)."""
    return _db(), _family_manager()


def get_auth_service():
    return _auth_service()


def show_login_screen():
    """Show Life360-style login screen with phone-first approach."""
    auth_step = st.session_state.get("auth_step", "phone")

    if auth_step == "phone":
        show_phone_login()
    elif auth_step == "otp":
        show_otp_verification()
    elif auth_step == "complete_profile":
        show_complete_profile()
    elif auth_step == "email_login":
        show_email_login()
    else:
        show_phone_login()



def show_phone_login():
    """Show phone number login screen — warm, semi-formal welcome."""
    from ui.primitives import page_shell, divider

    # Warm welcome hero
    st.markdown(
        """
        <div class="page-fade" style="text-align: center; padding: var(--space-6) 0 var(--space-4) 0;">
          <p class="eyebrow" style="color: var(--accent);">Welcome</p>
          <h1 class="hero-heading" style="text-align: center;">Care, together.</h1>
          <p class="muted" style="font-size: 1.125rem; max-width: 480px; margin: var(--space-3) auto 0;">
            A gentler way to keep track of medications with the people you love.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Sign-in card
    st.markdown(
        """
        <div class="med-card page-fade" style="max-width: 520px; margin: var(--space-6) auto var(--space-5);">
          <p class="eyebrow">Sign in</p>
          <h2 style="margin-bottom: var(--space-2);">Continue with your phone</h2>
          <p class="muted" style="margin: 0 0 var(--space-5) 0;">We'll text you a six-digit code. No password to remember.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Centered form column
    _, form_col, _ = st.columns([1, 3, 1])
    with form_col:
        with st.form("phone_login_form"):
            phone = st.text_input(
                "Phone number",
                placeholder="+1 (555) 123-4567",
                help="We'll send you a verification code",
            )
            submitted = st.form_submit_button(
                "Send me a code", use_container_width=True, type="primary"
            )
            if submitted:
                if phone:
                    auth = get_auth_service()
                    result = auth.request_otp(phone, purpose="login")
                    if result["success"]:
                        st.session_state.auth_phone = result["phone"]
                        st.session_state.otp_sent_time = time.time()
                        st.session_state.dev_otp = result.get("dev_otp")
                        st.session_state.auth_step = "otp"
                        st.success(result["message"])
                        st.rerun()
                    else:
                        st.error(result["error"])
                else:
                    st.error("Please enter your phone number")

        divider(4)
        st.markdown(
            '<p style="text-align: center; color: var(--text-subtle); font-size: 0.9375rem;">or</p>',
            unsafe_allow_html=True,
        )
        alt_cols = st.columns(2)
        with alt_cols[0]:
            if st.button("Use email instead", use_container_width=True, key="alt_email"):
                st.session_state.auth_step = "email_login"
                st.rerun()
        with alt_cols[1]:
            if st.button("Create an account", use_container_width=True, key="alt_create"):
                st.session_state.show_login = False
                st.session_state.show_register = True
                st.rerun()

            # Demo options
    if _local_demo_enabled():
        st.markdown("---")
        with st.expander("Demo Options", expanded=False):
            st.markdown("**For demo/portfolio purposes:**")
            st.info(
                "Local demo only. Enable MEDSYNC_DEV_SHOW_OTP=1 to display a test code in the verification screen."
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Skip Login (Guest Mode)", type="secondary"):
                    _sign_in_as_guest()
                    st.rerun()
            with col2:
                if st.button("Reset All Data", type="secondary"):
                    db_path = "data/medications.db"
                    if os.path.exists(db_path):
                        os.remove(db_path)
                    # Clear DB/auth singletons so the next request re-initialises
                    # against the fresh (empty) database.
                    st.cache_resource.clear()
                    for key in list(st.session_state.keys()):
                        del st.session_state[key]
                    st.success("All data cleared. Signing you out.")
                    st.rerun()


def _sign_in_as_guest() -> None:
    """Guest bypass — create or fetch a real 'Guest' patient row and sign in as them.

    The new st.navigation-based router keys off ``user_profile`` (not the
    legacy ``show_login`` flag), so guest mode needs to populate that dict
    with a real user record. The Guest row lives in the DB like any other
    user, which keeps us honest about the "no fake data" rule in CLAUDE.md.
    """
    if not _local_demo_enabled():
        raise PermissionError("Guest access is available only in a local demo")
    db, _ = init_database()
    users = db.get_users()
    guest = next((u for u in users if u.get("email") == "guest@demo.local"), None)
    if guest is None:
        guest_id = db.add_user(
            name="Guest",
            email="guest@demo.local",
            age=65,
            role="patient",
        )
        guest = db.get_user_by_id(guest_id)

    persist_session_token(get_auth_service()._create_session_token(guest["id"]))
    st.session_state.user_profile = {
        "id": guest["id"],
        "name": guest["name"],
        "email": guest.get("email", ""),
        "age": guest.get("age"),
        "type": guest.get("role", "patient"),
        "phone": guest.get("phone", ""),
        "relationship": "patient",
        "theme": guest.get("theme"),
    }
    st.session_state.onboarding_complete = True
    if guest.get("theme"):
        st.session_state["theme"] = guest["theme"]



def show_otp_verification():
    """Show OTP verification screen."""
    st.markdown(
        '<h1 class="welcome-header"> Verify Your Phone</h1>', unsafe_allow_html=True
    )

    phone = st.session_state.auth_phone
    phone_display = (
        f"***-***-{phone[-4:]}" if phone and len(phone) >= 4 else "your phone"
    )
    st.markdown(
        f'<p class="welcome-subheader">We sent a 6-digit code to {phone_display}</p>',
        unsafe_allow_html=True,
    )

    # Calculate time remaining
    sent_time = st.session_state.get("otp_sent_time", time.time())
    elapsed = time.time() - sent_time
    remaining = max(0, 300 - elapsed)  # 5 minutes = 300 seconds

    if remaining > 0:
        mins, secs = divmod(int(remaining), 60)
        st.info(f"⏱ Code expires in {mins}:{secs:02d}")
    else:
        st.warning("Code may have expired. Request a new one.")

    if st.session_state.get("dev_otp"):
        st.warning(
            f"SMS is not configured on this machine, so no text was sent. "
            f"Your verification code is **{st.session_state.dev_otp}** "
            f"(shown because MEDSYNC_DEV_SHOW_OTP=1)."
        )

    with st.form("otp_form"):
        otp_code = st.text_input(
            "Verification Code",
            max_chars=6,
            placeholder="Enter 6-digit code",
            help="Check your SMS messages",
        )

        col1, col2 = st.columns(2)
        with col1:
            verify_submitted = st.form_submit_button(
                "Verify", use_container_width=True, type="primary"
            )
        with col2:
            back_submitted = st.form_submit_button("← Back", use_container_width=True)

        if verify_submitted:
            if otp_code and len(otp_code) == 6:
                auth = get_auth_service()
                result = auth.verify_otp(phone, otp_code)

                if result["success"]:
                    st.session_state.pop("dev_otp", None)
                    if result.get("is_new_user"):
                        # New user - need to complete profile
                        st.session_state.is_new_user = True
                        st.session_state.auth_step = "complete_profile"
                        st.success("Phone verified! Let's set up your profile.")
                        st.rerun()
                    else:
                        # Existing user - log them in
                        user = result["user"]
                        persist_session_token(result["session_token"])
                        st.session_state.user_profile = {
                            "id": user["id"],
                            "name": user["name"],
                            "email": user.get("email", ""),
                            "age": user.get("age"),
                            "type": user.get("role", "patient"),
                            "phone": user.get("phone", ""),
                            "relationship": "family_member",
                        }
                        db, _ = init_database()
                        user_circles = db.get_user_family_circles(user["id"])
                        st.session_state.onboarding_complete = len(user_circles) > 0
                        st.session_state.show_login = False
                        st.session_state.auth_step = "phone"
                        st.success(f"Welcome back, {user['name']}!")
                        st.rerun()
                else:
                    st.error(result["error"])
            else:
                st.error("Please enter the 6-digit code")

        if back_submitted:
            st.session_state.auth_step = "phone"
            st.rerun()

            # Resend option
    st.markdown("---")
    if remaining <= 0 or elapsed > 30:  # Allow resend after 30 seconds
        if st.button("Resend Code", use_container_width=True):
            auth = get_auth_service()
            result = auth.request_otp(phone, purpose="login")
            if result["success"]:
                st.session_state.otp_sent_time = time.time()
                st.session_state.dev_otp = result.get("dev_otp")
                st.success("New code sent!")
                st.rerun()
            else:
                st.error(result["error"])
    else:
        wait_time = 30 - int(elapsed)
        st.markdown(
            f"<p style='text-align:center; color:var(--text-muted);'>Resend available in {wait_time}s</p>",
            unsafe_allow_html=True,
        )



def show_complete_profile():
    """Show profile completion form for new users after OTP verification."""
    st.markdown(
        '<h1 class="welcome-header"> Complete Your Profile</h1>', unsafe_allow_html=True
    )
    st.markdown(
        '<p class="welcome-subheader">Just a few more details to get started</p>',
        unsafe_allow_html=True,
    )

    phone = st.session_state.auth_phone

    with st.form("complete_profile_form"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Full Name *", placeholder="Enter your full name")
            email = st.text_input(
                "Email (optional)", placeholder="your.email@example.com"
            )

        with col2:
            age = st.number_input("Age", min_value=1, max_value=120, value=30)
            user_type = st.selectbox(
                "I am a:",
                ["family_member", "patient"],
                format_func=lambda x: (
                    "Family Member (caring for someone)"
                    if x == "family_member"
                    else "Patient (managing my own health)"
                ),
            )

        st.markdown("---")
        st.markdown("**Optional: Set a password for email login**")
        st.caption("This allows you to also sign in with email & password")

        col1, col2 = st.columns(2)
        with col1:
            password = st.text_input(
                "Password (optional)",
                type="password",
                placeholder="At least 8 characters",
            )
        with col2:
            confirm_password = st.text_input(
                "Confirm Password", type="password", placeholder="Confirm password"
            )

        submitted = st.form_submit_button(
            "Create My Account", use_container_width=True, type="primary"
        )

        if submitted:
            if name:
                # Validate password if provided
                if password:
                    if password != confirm_password:
                        st.error("Passwords do not match")
                        st.stop()
                    auth = get_auth_service()
                    is_strong, errors = auth.validate_password_strength(password)
                    if not is_strong:
                        st.error(f"{errors[0]}")
                        st.stop()

                auth = get_auth_service()
                result = auth.complete_phone_registration(
                    phone=phone,
                    name=name,
                    email=email if email else None,
                    password=password if password else None,
                    age=age,
                    role=user_type,
                )

                if result["success"]:
                    user = result["user"]
                    persist_session_token(result["session_token"])
                    st.session_state.user_profile = {
                        "id": user["id"],
                        "name": user["name"],
                        "email": user.get("email", ""),
                        "age": user.get("age"),
                        "type": user.get("role", "patient"),
                        "phone": user.get("phone", ""),
                        "relationship": (
                            "family_member"
                            if user_type == "family_member"
                            else "patient"
                        ),
                    }
                    st.session_state.show_login = False
                    st.session_state.onboarding_complete = False
                    st.session_state.auth_step = "phone"
                    st.session_state.is_new_user = False
                    st.success(f"Welcome to FamilyCare, {name}!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error(result["error"])
            else:
                st.error("Please enter your name")

    if st.button("← Back"):
        st.session_state.auth_step = "phone"
        st.rerun()



def show_email_login():
    """Show email/password login screen."""
    st.markdown(
        '<h1 class="welcome-header"> Sign In with Email</h1>', unsafe_allow_html=True
    )
    st.markdown(
        '<p class="welcome-subheader">Use your email and password</p>',
        unsafe_allow_html=True,
    )

    with st.form("email_login_form"):
        email = st.text_input("Email Address", placeholder="your.email@example.com")
        password = st.text_input(
            "Password", type="password", placeholder="Enter your password"
        )

        col1, col2 = st.columns(2)
        with col1:
            login_submitted = st.form_submit_button(
                "Sign In", use_container_width=True, type="primary"
            )
        with col2:
            back_submitted = st.form_submit_button(
                "← Back to Phone", use_container_width=True
            )

        if login_submitted:
            if email and password:
                auth = get_auth_service()
                result = auth.login_with_email(email, password)

                if result["success"]:
                    user = result["user"]
                    persist_session_token(result["session_token"])
                    st.session_state.user_profile = {
                        "id": user["id"],
                        "name": user["name"],
                        "email": user.get("email", ""),
                        "age": user.get("age"),
                        "type": user.get("role", "patient"),
                        "phone": user.get("phone", ""),
                        "relationship": "family_member",
                    }
                    db, _ = init_database()
                    user_circles = db.get_user_family_circles(user["id"])
                    st.session_state.onboarding_complete = len(user_circles) > 0
                    st.session_state.show_login = False
                    st.session_state.auth_step = "phone"
                    st.success(f"Welcome back, {user['name']}!")
                    st.rerun()
                else:
                    st.error(result["error"])
            else:
                st.error("Please enter email and password")

        if back_submitted:
            st.session_state.auth_step = "phone"
            st.rerun()

    st.markdown("---")

    # Forgot password
    with st.expander("Forgot Password?"):
        with st.form("forgot_password_form"):
            reset_email = st.text_input("Enter your email address", key="reset_email")
            if st.form_submit_button("Send Reset Link"):
                if reset_email:
                    auth = get_auth_service()
                    result = auth.request_password_reset(reset_email)
                    st.success(result["message"])
                else:
                    st.error("Please enter your email address")

    if _local_demo_enabled():
        with st.expander("Demo Options", expanded=False):
            if st.button("Skip Login (Guest)", key="guest_email"):
                _sign_in_as_guest()
                st.rerun()



def show_register_screen():
    """Show registration screen — warm, semi-formal."""
    st.markdown(
        """
        <div class="page-fade" style="text-align: center; padding: var(--space-6) 0 var(--space-4) 0;">
          <p class="eyebrow" style="color: var(--accent);">Create an account</p>
          <h1 class="hero-heading" style="text-align: center;">Nice to meet you.</h1>
          <p class="muted" style="font-size: 1.125rem; max-width: 480px; margin: var(--space-3) auto 0;">
            Start managing meds together in about a minute.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, back_col, _ = st.columns([1, 3, 1])
    with back_col:
        if st.button("Back to sign in", key="reg_back"):
            st.session_state.show_register = False
            st.session_state.show_login = True
            st.session_state.auth_step = "phone"
            st.rerun()

    _, tab_col, _ = st.columns([1, 3, 1])
    with tab_col:
        tab1, tab2 = st.tabs(["Phone (recommended)", "Email"])

    with tab1:
        st.markdown(
            '<h3 style="margin-top: var(--space-5);">Register with your phone</h3>'
            '<p class="muted" style="margin-bottom: var(--space-4);">Quick and secure — '
            'we\'ll verify with a text message.</p>',
            unsafe_allow_html=True,
        )

        with st.form("register_phone_form"):
            phone = st.text_input(
                "Phone Number *",
                placeholder="+1 (555) 123-4567",
                help="We'll send a verification code to this number",
            )

            submitted = st.form_submit_button(
                "Send Verification Code", use_container_width=True, type="primary"
            )

            if submitted:
                if phone:
                    auth = get_auth_service()
                    # Check if phone already registered
                    db, _ = init_database()
                    existing = db.get_user_by_phone(auth.normalize_phone(phone))
                    if existing:
                        st.error(
                            "This phone number is already registered. Try signing in instead."
                        )
                    else:
                        result = auth.request_otp(phone, purpose="register")
                        if result["success"]:
                            st.session_state.auth_phone = result["phone"]
                            st.session_state.otp_sent_time = time.time()
                            st.session_state.dev_otp = result.get("dev_otp")
                            st.session_state.show_register = False
                            st.session_state.show_login = True
                            st.session_state.auth_step = "otp"
                            st.session_state.is_new_user = True
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result["error"])
                else:
                    st.error("Please enter your phone number")

    with tab2:
        st.markdown("#### Register with Email")
        st.caption("Traditional email and password registration")

        with st.form("register_email_form"):
            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input(
                    "Full Name *", placeholder="Enter your full name", key="reg_name"
                )
                email = st.text_input(
                    "Email Address *",
                    placeholder="your.email@example.com",
                    key="reg_email",
                )
                password = st.text_input(
                    "Password *",
                    type="password",
                    placeholder="At least 8 characters",
                    key="reg_pass",
                )

            with col2:
                age = st.number_input(
                    "Age", min_value=1, max_value=120, value=30, key="reg_age"
                )
                phone = st.text_input(
                    "Phone (optional)",
                    placeholder="+1 (555) 123-4567",
                    key="reg_phone_opt",
                )
                confirm_password = st.text_input(
                    "Confirm Password *",
                    type="password",
                    placeholder="Confirm password",
                    key="reg_confirm",
                )

            user_type = st.selectbox(
                "I am a:",
                ["family_member", "patient"],
                format_func=lambda x: (
                    "Family Member (caring for someone)"
                    if x == "family_member"
                    else "Patient (managing my own health)"
                ),
                key="reg_type",
            )

            st.markdown("---")
            register_submitted = st.form_submit_button(
                "Create Account", use_container_width=True, type="primary"
            )

            if register_submitted:
                if name and email and password:
                    if password != confirm_password:
                        st.error("Passwords do not match")
                    else:
                        auth = get_auth_service()
                        result = auth.register_with_email(
                            email=email,
                            password=password,
                            name=name,
                            phone=phone if phone else None,
                            age=age,
                            role=user_type,
                        )

                        if result["success"]:
                            user = result["user"]
                            persist_session_token(result["session_token"])
                            st.session_state.user_profile = {
                                "id": user["id"],
                                "name": user["name"],
                                "email": user.get("email", ""),
                                "age": user.get("age"),
                                "type": user.get("role", "patient"),
                                "phone": user.get("phone", ""),
                                "relationship": (
                                    "family_member"
                                    if user_type == "family_member"
                                    else "patient"
                                ),
                            }
                            st.session_state.show_register = False
                            st.session_state.onboarding_complete = False
                            st.success(f"Welcome to FamilyCare, {name}!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error(result["error"])
                            if result.get("password_errors"):
                                for err in result["password_errors"]:
                                    st.warning(f"• {err}")
                else:
                    st.error(
                        "Please fill in all required fields (Name, Email, Password)"
                    )



def show_welcome_screen():
    """Show welcome screen for guest mode (no login)."""
    st.markdown(
        '<h1 class="welcome-header"> Welcome to FamilyCare</h1>', unsafe_allow_html=True
    )
    st.markdown(
        '<p class="welcome-subheader">Keep your loved ones healthy and connected with smart medication management</p>',
        unsafe_allow_html=True,
    )

    st.info(
        "**Guest Mode** - You're exploring FamilyCare without an account. Create an account to save your data!"
    )

    # Feature showcase
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
 <div class="feature-card">
 <h3> Family Circles</h3>
 <p>Connect with family members to monitor and support elderly care remotely</p>
 </div>
 """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            """
 <div class="feature-card">
 <h3> Medication Tracking</h3>
 <p>Set up medication schedules and track adherence with smart reminders</p>
 </div>
 """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            """
 <div class="feature-card">
 <h3> Health Insights</h3>
 <p>View detailed analytics and receive alerts when attention is needed</p>
 </div>
 """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Getting started options
    st.markdown("## Create Your Profile")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### I'm a Family Member")
        st.markdown("I want to help monitor and manage a loved one's medications")
        if st.button(
            "‍‍‍ Start as Family Member", key="family_member", use_container_width=True
        ):
            st.session_state.user_type = "family_member"
            st.session_state.show_profile_setup = True
            st.rerun()

    with col2:
        st.markdown("### I'm a Patient")
        st.markdown("I want to manage my own medications and connect with family")
        if st.button("Start as Patient", key="patient", use_container_width=True):
            st.session_state.user_type = "patient"
            st.session_state.show_profile_setup = True
            st.rerun()

            # Login option
    st.markdown("---")
    st.markdown("### Already have an account?")
    if st.button(
        "Sign In to Your Account", key="go_to_login", use_container_width=True
    ):
        st.session_state.show_login = True
        st.rerun()



def show_profile_setup():
    """Show profile setup form."""
    if not _local_demo_enabled():
        st.info("Use Create an account to register with authentication.")
        return
    user_type = st.session_state.get("user_type", "family_member")

    st.markdown("# Set Up Your Profile")
    st.markdown(
        f"**Account Type:** {'Family Member' if user_type == 'family_member' else 'Patient'}"
    )

    with st.form("profile_setup"):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Full Name *", placeholder="Enter your full name")
            email = st.text_input(
                "Email Address *", placeholder="your.email@example.com"
            )

        with col2:
            age = st.number_input(
                "Age",
                min_value=1,
                max_value=120,
                value=30 if user_type == "family_member" else 70,
            )
            phone = st.text_input("Phone Number", placeholder="+1 (555) 123-4567")

        if user_type == "family_member":
            relationship = st.selectbox(
                "Your relationship to patients you'll monitor:",
                ["Child", "Spouse", "Sibling", "Caregiver", "Other"],
            )
        else:
            relationship = "patient"

        st.markdown("---")

        submitted = st.form_submit_button("Create My Profile", use_container_width=True)

        if submitted:
            if name and email:
                # Create user profile
                db, family_manager = init_database()

                # Check if email already exists
                existing_user = db.get_user_by_email(email)
                if existing_user:
                    st.error(
                        f"An account with email {email} already exists. Please use a different email or contact support."
                    )
                    st.info(
                        "For this demo, you can use a different email address to create a new profile."
                    )
                else:
                    try:
                        user_id = db.add_user(name, email, age, user_type, phone)

                        persist_session_token(get_auth_service()._create_session_token(user_id))
                        st.session_state.user_profile = {
                            "id": user_id,
                            "name": name,
                            "email": email,
                            "age": age,
                            "type": user_type,
                            "phone": phone,
                            "relationship": relationship,
                        }

                        st.session_state.show_profile_setup = False
                        st.session_state.profile_created = True
                        st.success(f"Welcome, {name}! Your profile has been created.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error creating profile: {str(e)}")
                        st.info("Please try with a different email address.")
            else:
                st.error("Please fill in your name and email address.")




def render() -> None:
    """Dispatch to the correct auth sub-screen based on session state."""
    init_session_state()
    # Consume primary auth links once so they cannot override Back or the next
    # OTP/registration step. Legacy demo forms retain their routing parameter.
    mode = st.query_params.get("mode")
    if mode in {"register", "email", "phone"}:
        st.query_params.pop("mode", None)
        st.session_state["show_register"] = mode == "register"
        st.session_state["auth_step"] = "email_login" if mode == "email" else "phone"
    if mode == "register":
        show_register_screen()
    elif mode == "email":
        show_email_login()
    elif mode == "welcome":
        show_welcome_screen()
    elif mode == "profile-setup":
        show_profile_setup()
    elif st.session_state.get("auth_step") == "email_login":
        show_email_login()
    elif st.session_state.get("auth_step") == "otp":
        show_otp_verification()
    elif st.session_state.get("auth_step") == "complete_profile":
        show_complete_profile()
    elif st.session_state.get("show_register"):
        show_register_screen()
    else:
        show_phone_login()
