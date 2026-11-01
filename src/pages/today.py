"""/today — patient's today's medications.

The most-used screen in the product. See ``design-system/pages/today.md``
for the per-page override that governs this file.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

import streamlit as st

from ui.primitives import (
    page_shell,
    empty_state,
    progress_ring,
    status_pill,
    divider,
    stack_open,
    stack_close,
)
from utils.authz import AuthorizationError
from utils.session import (
    db as _db,
    current_user,
    init_session_state,
    cached_patient_medications,
    cached_dose_log,
    cached_family_patients_status,
    invalidate_read_caches,
)


def render() -> None:
    init_session_state()
    if "snoozed_meds" not in st.session_state:
        st.session_state.snoozed_meds = {}

    db = _db()
    user = current_user()
    if user is None:
        st.info("Sign in to see today's medications.")
        return

    patient_id, patient_name = _resolve_patient(db, user)
    if patient_id is None:
        return

    today_str = datetime.now().strftime("%A, %B %-d")

    # Header
    if user.get("type") == "patient":
        page_shell("Today's medications", eyebrow=today_str)
    else:
        page_shell(
            "Today's medications",
            eyebrow=f"{today_str} · {patient_name}",
        )

    medications = cached_patient_medications(user["id"], patient_id)

    if not medications:
        empty_state(
            "No medications scheduled",
            f"There's nothing scheduled for {patient_name} today. "
            "Add a medication from the dashboard when you're ready.",
        )
        return

    doses = _build_doses(db, user, patient_id, medications)

    # A caller may see a patient's day (view) without being able to log doses
    # for them (manage_meds). Resolve once and let the cards render read-only
    # rather than offering a button that would raise on click.
    can_write = db.can_manage_patient(user["id"], patient_id)

    total = len(doses)
    taken = sum(1 for d in doses if d["existing_log"] and d["existing_log"][0])
    percent = (taken / total) if total else 0.0

    # Progress ring + count
    progress_ring(
        percent,
        label=f"{taken}/{total}",
        sublabel="taken today",
    )

    if total and taken == total:
        st.markdown(
            '<p class="page-fade" style="text-align:center;font-size:1.125rem;'
            'color:var(--success);margin:0 0 var(--space-6) 0;">'
            "You're all set for today.</p>",
            unsafe_allow_html=True,
        )

    divider(5)

    # Per-dose cards
    stack_open()
    for dose in doses:
        _render_dose_card(db, user, patient_id, dose, can_write)
    stack_close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_patient(db, user):
    """Return (patient_id, patient_name). Family members pick from their circles."""
    if user.get("type") == "patient":
        return user["id"], user["name"]

    circles = db.get_user_family_circles(user["id"])
    if not circles:
        empty_state(
            "No family circles yet",
            "Create one from Family Circle to start tracking meds together.",
        )
        return None, None

    statuses = db.get_family_patients_status(user["id"])
    if not statuses:
        empty_state(
            "No patients yet",
            "Invite a patient to your family circle to see their schedule here.",
        )
        return None, None

    names = {p["id"]: p["name"] for p in statuses}
    picked = st.selectbox(
        "Patient",
        options=list(names.keys()),
        format_func=lambda x: names[x],
        key="today_patient_selector",
    )
    return picked, names[picked]


def _build_doses(db, user: dict, patient_id: int, medications: list[dict]) -> list[dict]:
    """Expand medications into per-dose entries, resolve snooze + existing logs, sort by time."""
    today = datetime.now().date().isoformat()
    doses: list[dict] = []

    for med in medications:
        for med_time in med["times"]:
            snooze_key = f"{med['id']}_{med_time}"
            snoozed_until = st.session_state.snoozed_meds.get(snooze_key)
            if snoozed_until and datetime.now() < snoozed_until:
                display_time = snoozed_until.strftime("%H:%M")
                is_snoozed = True
            else:
                if snoozed_until:
                    del st.session_state.snoozed_meds[snooze_key]
                display_time = med_time
                is_snoozed = False

            existing_log = _lookup_dose_log(db, user["id"], patient_id, med["name"], med_time, today)

            doses.append({
                "medication": med,
                "scheduled_time": med_time,
                "display_time": display_time,
                "is_snoozed": is_snoozed,
                "existing_log": existing_log,
                "sort_time": datetime.strptime(display_time, "%H:%M").time(),
            })

    doses.sort(key=lambda x: x["sort_time"])
    return doses


def _lookup_dose_log(db, caller_id: int, patient_id: int, med_name: str, scheduled: str, date: str):
    """Cached (taken, actual_time) tuple or None. Cache invalidates on log_dose."""
    return cached_dose_log(caller_id, patient_id, med_name, scheduled, date)


def _render_dose_card(db, user, patient_id: int, dose: dict, can_write: bool) -> None:
    med = dose["medication"]
    med_time = dose["scheduled_time"]
    display_time = dose["display_time"]
    existing_log = dose["existing_log"]
    is_snoozed = dose["is_snoozed"]
    taken = bool(existing_log and existing_log[0])

    try:
        formatted_time = datetime.strptime(display_time, "%H:%M").strftime("%-I:%M %p")
    except ValueError:
        formatted_time = display_time

    card_style = (
        "background: var(--surface-inset); opacity: 0.85;"
        if taken
        else "background: var(--surface-card);"
    )

    st.markdown(
        f"""
        <div class="med-card" style="{card_style}">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:var(--space-5);">
            <div style="flex:1;">
              <h3 style="margin:0 0 var(--space-1) 0;">{escape(med['name'])}</h3>
              <p class="tabular" style="margin:0;color:var(--text-muted);font-size:1rem;">
                {escape(med['dosage'])}<span style="color:var(--text-subtle);margin:0 0.5rem;">·</span>{formatted_time}
              </p>
              {'<div style="margin-top: var(--space-3);">' + status_pill(f"Snoozed from {datetime.strptime(med_time, '%H:%M').strftime('%-I:%M %p')}", 'warning') + '</div>' if is_snoozed else ''}
              {f'<p class="muted" style="margin: var(--space-3) 0 0 0; padding-top: var(--space-3); border-top: 1px solid var(--border); font-size: 0.9375rem;">{escape(med.get("notes", ""))}</p>' if med.get('notes') else ''}
            </div>
          </div>
        </div>
        """.strip().replace("\n", ""),
        unsafe_allow_html=True,
    )

    # Streamlit buttons render below the card — visually attach with negative margin via a helper div.
    if taken:
        taken_time = existing_log[1]
        try:
            taken_formatted = datetime.strptime(taken_time, "%H:%M").strftime("%-I:%M %p")
        except ValueError:
            taken_formatted = taken_time
        st.markdown(
            '<div style="margin: calc(-1 * var(--space-5)) 0 var(--space-3) 0; text-align: right;">'
            + status_pill(f"Taken at {taken_formatted}", "success")
            + "</div>",
            unsafe_allow_html=True,
        )
    elif existing_log and not existing_log[0]:
        st.markdown(
            '<div style="margin: calc(-1 * var(--space-5)) 0 var(--space-3) 0; text-align: right;">'
            + status_pill("Missed", "error")
            + "</div>",
            unsafe_allow_html=True,
        )
    elif not can_write:
        # View-only caller (e.g. a family member with 'view' but not
        # 'manage_meds'): show the dose but no actions it can't perform.
        st.markdown(
            '<div style="margin: calc(-1 * var(--space-5)) 0 var(--space-3) 0; text-align: right;">'
            + status_pill("View only", "muted")
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        cols = st.columns([1, 1])
        with cols[0]:
            if st.button(
                "I took it",
                key=f"take_{med['id']}_{med_time}",
                use_container_width=True,
                type="primary",
            ):
                try:
                    db.log_dose(
                        user["id"],
                        patient_id,
                        med["name"],
                        med_time,
                        True,
                        datetime.now().strftime("%H:%M"),
                    )
                except AuthorizationError:
                    # Backstop: permissions could have been revoked between
                    # render and click. Never surface a raw exception page.
                    st.error("You don't have permission to log doses for this patient.")
                    return
                invalidate_read_caches()
                st.rerun()
        with cols[1]:
            if st.button(
                "Snooze 30 min",
                key=f"snooze_{med['id']}_{med_time}",
                use_container_width=True,
            ):
                st.session_state.snoozed_meds[f"{med['id']}_{med_time}"] = (
                    datetime.now() + timedelta(minutes=30)
                )
                st.toast(f"Snoozed {med['name']} for 30 minutes")
                st.rerun()

    divider(3)
