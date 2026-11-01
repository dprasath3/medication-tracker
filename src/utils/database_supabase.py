"""Supabase database adapter for medication tracking.
Uses the same interface as database.py but connects to Supabase.
"""
import os
import json
import uuid
import secrets
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from supabase import create_client, Client

from utils.authz import PatientAuthorizationMixin


class MedicationDB(PatientAuthorizationMixin):
    """Supabase database handler for medication tracking with family circle support."""

    def __init__(self, db_path: str = None):
        """Initialize Supabase client. db_path is ignored (kept for compatibility)."""
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY')

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY environment variables required")

        self.client: Client = create_client(supabase_url, supabase_key)
        # For compatibility with scheduler.py which accesses db_path
        self.db_path = None

    def init_database(self):
        """No-op for Supabase - tables created via SQL schema."""
        pass

    # USER MANAGEMENT
    def add_user(self, name: str, email: str = None, age: int = None,
                 role: str = 'patient', phone: str = None) -> int:
        """Add a new user and return their ID."""
        data = {
            'name': name,
            'email': email,
            'age': age,
            'role': role,
            'phone': phone,
            'created_date': datetime.now().isoformat()
        }
        result = self.client.table('users').insert(data).execute()
        return result.data[0]['id']

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email address."""
        result = self.client.table('users').select('*').eq('email', email).execute()
        return result.data[0] if result.data else None

    def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get user by phone number."""
        result = self.client.table('users').select('*').eq('phone', phone).execute()
        return result.data[0] if result.data else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        result = self.client.table('users').select('*').eq('id', user_id).execute()
        return result.data[0] if result.data else None

    def get_users(self) -> List[Dict[str, Any]]:
        """Get all users."""
        result = self.client.table('users').select('*').execute()
        return result.data

    def update_user(self, user_id: int, **kwargs) -> bool:
        """Update user fields."""
        if not kwargs:
            return False
        self.client.table('users').update(kwargs).eq('id', user_id).execute()
        return True

    # FAMILY CIRCLE MANAGEMENT
    def create_family_circle(self, name: str, created_by: int) -> tuple:
        """Create a family circle and return (circle_id, invite_code)."""
        invite_code = str(uuid.uuid4())[:8].upper()

        # Create family circle
        data = {
            'name': name,
            'invite_code': invite_code,
            'created_by': created_by,
            'created_date': datetime.now().isoformat()
        }
        result = self.client.table('family_circles').insert(data).execute()
        circle_id = result.data[0]['id']

        # Add creator as first member
        member_data = {
            'family_circle_id': circle_id,
            'user_id': created_by,
            'relationship': 'creator',
            'permissions': ['view', 'manage_meds', 'set_reminders', 'invite_members'],
            'joined_date': datetime.now().isoformat()
        }
        self.client.table('family_members').insert(member_data).execute()

        return circle_id, invite_code

    def join_family_circle(self, invite_code: str, user_id: int,
                           relationship: str = 'family_member') -> bool:
        """Join a family circle using invite code."""
        # Find family circle
        result = self.client.table('family_circles').select('id').eq('invite_code', invite_code).execute()
        if not result.data:
            return False

        circle_id = result.data[0]['id']

        # Add member to circle
        try:
            member_data = {
                'family_circle_id': circle_id,
                'user_id': user_id,
                'relationship': relationship,
                'permissions': ['view', 'set_reminders'],
                'joined_date': datetime.now().isoformat()
            }
            self.client.table('family_members').insert(member_data).execute()
            return True
        except Exception:
            return False

    def get_user_family_circles(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all family circles a user belongs to."""
        result = self.client.table('family_members').select(
            '*, family_circles(*)'
        ).eq('user_id', user_id).execute()

        circles = []
        for row in result.data:
            circle = row['family_circles']
            circle['relationship'] = row['relationship']
            circle['permissions'] = row['permissions']
            circles.append(circle)
        return circles

    def get_family_circle_members(self, circle_id: int) -> List[Dict[str, Any]]:
        """Get all members of a family circle."""
        result = self.client.table('family_members').select(
            '*, users(*)'
        ).eq('family_circle_id', circle_id).execute()

        members = []
        for row in result.data:
            member = row['users']
            member['relationship'] = row['relationship']
            member['permissions'] = row['permissions']
            member['joined_date'] = row['joined_date']
            members.append(member)
        return members

    def get_family_circle(self, circle_id: int) -> Optional[Dict[str, Any]]:
        """Get a single family circle row (includes ``created_by``)."""
        result = self.client.table('family_circles').select('*').eq('id', circle_id).execute()
        return result.data[0] if result.data else None

    def set_member_manage_meds(self, actor_id, circle_id: int, user_id: int,
                               can_manage: bool) -> bool:
        """Grant or revoke a member's ``manage_meds`` permission in a circle.

        Only the circle's creator may change permissions — verified here, not
        just in the UI. Raises ``PermissionError`` otherwise. Returns False if
        the target is not a member of the circle.
        """
        circle = self.get_family_circle(circle_id)
        if not circle or circle["created_by"] != actor_id:
            raise PermissionError("Only the circle creator can change permissions")
        result = self.client.table('family_members').select('permissions').eq(
            'family_circle_id', circle_id
        ).eq('user_id', user_id).execute()
        if not result.data:
            return False
        perms = set(result.data[0]['permissions'] or [])
        perms.add("manage_meds") if can_manage else perms.discard("manage_meds")
        self.client.table('family_members').update(
            {'permissions': sorted(perms)}
        ).eq('family_circle_id', circle_id).eq('user_id', user_id).execute()
        return True

    # AUTHORIZATION (see utils/authz.py — the single chokepoint)
    def _get_caller_permissions_for_patient(self, caller_id: int, patient_id: int) -> set:
        """Union of the caller's permissions across circles shared with the patient."""
        caller_rows = self.client.table('family_members').select(
            'family_circle_id, permissions'
        ).eq('user_id', caller_id).execute()
        patient_rows = self.client.table('family_members').select(
            'family_circle_id'
        ).eq('user_id', patient_id).execute()

        patient_circles = {row['family_circle_id'] for row in patient_rows.data}
        permissions = set()
        for row in caller_rows.data:
            if row['family_circle_id'] in patient_circles:
                permissions.update(row['permissions'])
        return permissions

    def get_patient(self, caller_id, patient_id: int) -> Optional[Dict[str, Any]]:
        """Authorized single-patient lookup (replaces get_users() scans in pages)."""
        self._assert_can_access_patient(caller_id, patient_id, "read")
        return self.get_user_by_id(patient_id)

    # MEDICATION MANAGEMENT
    def add_medication(self, caller_id, patient_id: int, name: str,
                       dosage: str, frequency: str, times: List[str],
                       notes: str = None) -> int:
        """Add a medication for a patient. The caller is recorded as its manager."""
        self._assert_can_access_patient(caller_id, patient_id, "write")
        data = {
            'patient_id': patient_id,
            'managed_by': caller_id,
            'name': name,
            'dosage': dosage,
            'frequency': frequency,
            'times': times,  # Supabase handles JSON natively
            'notes': notes,
            'created_date': datetime.now().isoformat()
        }
        result = self.client.table('medications').insert(data).execute()
        return result.data[0]['id']

    def get_patient_medications(self, caller_id, patient_id: int) -> List[Dict[str, Any]]:
        """Get all active medications for a patient."""
        self._assert_can_access_patient(caller_id, patient_id, "read")
        result = self.client.table('medications').select(
            '*, users!managed_by(name)'
        ).eq('patient_id', patient_id).eq('active', True).execute()

        medications = []
        for row in result.data:
            med = dict(row)
            if 'users' in med and med['users']:
                med['managed_by_name'] = med['users']['name']
            del med['users']
            medications.append(med)
        return medications

    def _get_medication_patient_id(self, medication_id: int) -> Optional[int]:
        """Resolve which patient a medication belongs to (for authorization)."""
        result = self.client.table('medications').select('patient_id').eq('id', medication_id).execute()
        return result.data[0]['patient_id'] if result.data else None

    def update_medication(self, caller_id, medication_id: int, dosage: str = None,
                          frequency: str = None, times: List[str] = None,
                          notes: str = None) -> bool:
        """Update an existing medication's dose/schedule/notes.

        Name is intentionally not updatable: dose_logs reference the medication
        by name, so a rename would detach history. Rename = deactivate + re-add.
        Authorized against the medication's patient through the write chokepoint.
        """
        patient_id = self._get_medication_patient_id(medication_id)
        if patient_id is None:
            return False
        self._assert_can_access_patient(caller_id, patient_id, "write")
        updates = {}
        if dosage is not None:
            updates["dosage"] = dosage
        if frequency is not None:
            updates["frequency"] = frequency
        if times is not None:
            updates["times"] = times  # Supabase handles JSON natively
        if notes is not None:
            updates["notes"] = notes
        if not updates:
            return False
        self.client.table('medications').update(updates).eq('id', medication_id).execute()
        return True

    def deactivate_medication(self, caller_id, medication_id: int) -> bool:
        """Soft-delete a medication (active = False) so it drops off the schedule.

        Past dose_logs are kept. Authorized through the write chokepoint.
        """
        patient_id = self._get_medication_patient_id(medication_id)
        if patient_id is None:
            return False
        self._assert_can_access_patient(caller_id, patient_id, "write")
        self.client.table('medications').update({'active': False}).eq('id', medication_id).execute()
        return True

    def get_inactive_medications(self, caller_id, patient_id: int) -> List[Dict[str, Any]]:
        """Get deactivated (active = False) medications for a patient (read access)."""
        self._assert_can_access_patient(caller_id, patient_id, "read")
        result = self.client.table('medications').select(
            '*, users!managed_by(name)'
        ).eq('patient_id', patient_id).eq('active', False).execute()

        medications = []
        for row in result.data:
            med = dict(row)
            if med.get('users'):
                med['managed_by_name'] = med['users']['name']
            med.pop('users', None)
            medications.append(med)
        return medications

    def reactivate_medication(self, caller_id, medication_id: int) -> bool:
        """Restore a soft-deleted medication (active = True). Write chokepoint."""
        patient_id = self._get_medication_patient_id(medication_id)
        if patient_id is None:
            return False
        self._assert_can_access_patient(caller_id, patient_id, "write")
        self.client.table('medications').update({'active': True}).eq('id', medication_id).execute()
        return True

    def log_dose(self, caller_id, patient_id: int, medication_name: str, scheduled_time: str,
                 taken: bool, actual_time: str = None) -> int:
        """Log a dose taken/missed. The caller is recorded as the logger."""
        self._assert_can_access_patient(caller_id, patient_id, "write")
        actual_time = actual_time or datetime.now().strftime("%H:%M")
        data = {
            'patient_id': patient_id,
            'medication_name': medication_name,
            'scheduled_time': scheduled_time,
            'taken': taken,
            'actual_time': actual_time,
            'date': datetime.now().date().isoformat(),
            'timestamp': datetime.now().isoformat(),
            'logged_by': caller_id
        }
        result = self.client.table('dose_logs').insert(data).execute()
        return result.data[0]['id']

    def get_dose_log_for_date(self, caller_id, patient_id: int, medication_name: str,
                              scheduled_time: str, date: str):
        """Return (taken, actual_time) tuple for a scheduled dose on a date, or None."""
        self._assert_can_access_patient(caller_id, patient_id, "read")
        result = self.client.table('dose_logs').select('taken, actual_time').eq(
            'patient_id', patient_id
        ).eq('medication_name', medication_name).eq(
            'scheduled_time', scheduled_time
        ).eq('date', date).execute()
        if result.data:
            return (result.data[0]['taken'], result.data[0]['actual_time'])
        return None

    # FAMILY DASHBOARD QUERIES
    def get_family_patients_status(self, family_member_id: int) -> List[Dict[str, Any]]:
        """Get medication status for all patients in family member's circles."""
        # Get family circles the member belongs to
        circles = self.get_user_family_circles(family_member_id)

        patients = []
        seen_ids = set()

        for circle in circles:
            members = self.get_family_circle_members(circle['id'])
            for member in members:
                if member['role'] == 'patient' and member['id'] not in seen_ids:
                    seen_ids.add(member['id'])
                    meds = self.get_patient_medications(family_member_id, member['id'])
                    patient = {
                        'id': member['id'],
                        'name': member['name'],
                        'age': member['age'],
                        'total_medications': len(meds),
                        'family_circle_name': circle['name'],
                        'adherence_rate': self.get_patient_adherence(family_member_id, member['id'], days=7)
                    }
                    patients.append(patient)

        return patients

    def get_patient_adherence(self, caller_id, patient_id: int, days: int = 7) -> float:
        """Calculate adherence rate for patient over last X days."""
        self._assert_can_access_patient(caller_id, patient_id, "read")
        start_date = (datetime.now() - timedelta(days=days)).date().isoformat()

        result = self.client.table('dose_logs').select('taken').eq(
            'patient_id', patient_id
        ).gte('date', start_date).execute()

        if not result.data:
            return 0.0

        total = len(result.data)
        taken = sum(1 for log in result.data if log['taken'])
        return (taken / total) * 100

    def get_daily_dose_counts(self, caller_id, patient_id: int, days: int = 7) -> List[Dict[str, Any]]:
        """Per-day dose totals for the last N days: [{'date', 'total', 'taken'}, ...].

        Replaces the raw dose_logs SQL that pages/patient.py and
        services/scheduler.py previously ran outside the data layer.
        """
        self._assert_can_access_patient(caller_id, patient_id, "read")
        start_date = (datetime.now() - timedelta(days=days)).date().isoformat()

        result = self.client.table('dose_logs').select('date, taken').eq(
            'patient_id', patient_id
        ).gte('date', start_date).execute()

        counts = {}
        for row in result.data:
            entry = counts.setdefault(row['date'], {'date': row['date'], 'total': 0, 'taken': 0})
            entry['total'] += 1
            entry['taken'] += 1 if row['taken'] else 0
        return [counts[d] for d in sorted(counts)]

    # USER CREDENTIALS
    def create_user_credentials(self, user_id: int, password_hash: str) -> int:
        """Create credentials entry for a user."""
        data = {
            'user_id': user_id,
            'password_hash': password_hash,
            'created_date': datetime.now().isoformat(),
            'updated_date': datetime.now().isoformat()
        }
        result = self.client.table('user_credentials').insert(data).execute()
        return result.data[0]['id']

    def get_user_credentials(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get credentials for a user."""
        result = self.client.table('user_credentials').select('*').eq('user_id', user_id).execute()
        return result.data[0] if result.data else None

    def update_password_hash(self, user_id: int, password_hash: str) -> bool:
        """Update user's password hash."""
        self.client.table('user_credentials').update({
            'password_hash': password_hash,
            'updated_date': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        return True

    def set_email_verification_token(self, user_id: int, token: str, expiry_hours: int = 24) -> bool:
        """Set email verification token."""
        expiry = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        self.client.table('user_credentials').update({
            'email_verification_token': token,
            'email_verification_expiry': expiry
        }).eq('user_id', user_id).execute()
        return True

    def verify_email_token(self, token: str) -> Optional[int]:
        """Verify email token and return user_id if valid."""
        result = self.client.table('user_credentials').select('user_id').eq(
            'email_verification_token', token
        ).gt('email_verification_expiry', datetime.now().isoformat()).execute()

        if result.data:
            user_id = result.data[0]['user_id']
            self.client.table('user_credentials').update({
                'email_verified': True,
                'email_verification_token': None
            }).eq('user_id', user_id).execute()
            return user_id
        return None

    def set_password_reset_token(self, user_id: int, token: str, expiry_hours: int = 1) -> bool:
        """Set password reset token."""
        expiry = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        self.client.table('user_credentials').update({
            'password_reset_token': token,
            'password_reset_expiry': expiry
        }).eq('user_id', user_id).execute()
        return True

    def verify_password_reset_token(self, token: str) -> Optional[int]:
        """Verify password reset token and return user_id if valid."""
        result = self.client.table('user_credentials').select('user_id').eq(
            'password_reset_token', token
        ).gt('password_reset_expiry', datetime.now().isoformat()).execute()
        return result.data[0]['user_id'] if result.data else None

    def clear_password_reset_token(self, user_id: int) -> bool:
        """Clear password reset token after use."""
        self.client.table('user_credentials').update({
            'password_reset_token': None
        }).eq('user_id', user_id).execute()
        return True

    # OTP VERIFICATIONS
    def create_otp(self, phone: str, otp_hash: str, purpose: str = 'login',
                   user_id: int = None, expiry_minutes: int = 5) -> int:
        """Create OTP verification entry."""
        # Delete existing unverified OTPs
        self.client.table('otp_verifications').delete().eq('phone', phone).eq('verified', False).execute()

        now = datetime.now()
        expires = now + timedelta(minutes=expiry_minutes)

        data = {
            'phone': phone,
            'otp_hash': otp_hash,
            'created_at': now.isoformat(),
            'expires_at': expires.isoformat(),
            'user_id': user_id,
            'purpose': purpose
        }
        result = self.client.table('otp_verifications').insert(data).execute()
        return result.data[0]['id']

    def get_active_otp(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get active (non-expired, non-verified) OTP for phone."""
        result = self.client.table('otp_verifications').select('*').eq(
            'phone', phone
        ).eq('verified', False).gt(
            'expires_at', datetime.now().isoformat()
        ).order('created_at', desc=True).limit(1).execute()
        return result.data[0] if result.data else None

    def increment_otp_attempts(self, otp_id: int) -> int:
        """Increment OTP attempt count and return new count."""
        result = self.client.table('otp_verifications').select('attempts').eq('id', otp_id).execute()
        current = result.data[0]['attempts'] if result.data else 0
        new_count = current + 1
        self.client.table('otp_verifications').update({'attempts': new_count}).eq('id', otp_id).execute()
        return new_count

    def mark_otp_verified(self, otp_id: int) -> bool:
        """Mark OTP as verified."""
        self.client.table('otp_verifications').update({'verified': True}).eq('id', otp_id).execute()
        return True

    def cleanup_expired_otps(self) -> int:
        """Remove expired OTPs."""
        result = self.client.table('otp_verifications').delete().lt(
            'expires_at', datetime.now().isoformat()
        ).execute()
        return len(result.data) if result.data else 0

    # USER SESSIONS
    def create_session(self, user_id: int, session_token: str, device_fingerprint: str = None,
                       device_name: str = None, ip_address: str = None, expiry_days: int = 7) -> int:
        """Create a new user session."""
        now = datetime.now()
        expires = now + timedelta(days=expiry_days)

        data = {
            'user_id': user_id,
            'session_token': session_token,
            'device_fingerprint': device_fingerprint,
            'device_name': device_name,
            'ip_address': ip_address,
            'created_at': now.isoformat(),
            'last_activity': now.isoformat(),
            'expires_at': expires.isoformat()
        }
        result = self.client.table('user_sessions').insert(data).execute()
        return result.data[0]['id']

    def get_session_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get session by token if active and not expired."""
        result = self.client.table('user_sessions').select('*').eq(
            'session_token', token
        ).eq('is_active', True).gt(
            'expires_at', datetime.now().isoformat()
        ).execute()
        return result.data[0] if result.data else None

    def update_session_activity(self, token: str) -> bool:
        """Update last activity timestamp for session."""
        self.client.table('user_sessions').update({
            'last_activity': datetime.now().isoformat()
        }).eq('session_token', token).execute()
        return True

    def invalidate_session(self, token: str) -> bool:
        """Invalidate a session (logout)."""
        self.client.table('user_sessions').update({'is_active': False}).eq('session_token', token).execute()
        return True

    def invalidate_all_user_sessions(self, user_id: int) -> int:
        """Invalidate all sessions for a user."""
        result = self.client.table('user_sessions').update(
            {'is_active': False}
        ).eq('user_id', user_id).execute()
        return len(result.data) if result.data else 0

    def get_user_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active sessions for a user."""
        result = self.client.table('user_sessions').select(
            'id, device_name, ip_address, created_at, last_activity'
        ).eq('user_id', user_id).eq('is_active', True).gt(
            'expires_at', datetime.now().isoformat()
        ).order('last_activity', desc=True).execute()
        return result.data

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions."""
        result = self.client.table('user_sessions').delete().lt(
            'expires_at', datetime.now().isoformat()
        ).execute()
        return len(result.data) if result.data else 0

    # INVITE CODES
    def create_invite_code(self, family_circle_id: int, created_by: int,
                           expiry_hours: int = 72, max_uses: int = 10) -> Dict[str, Any]:
        """Create an invite code with expiration."""
        code = str(uuid.uuid4())[:8].upper()
        deep_link_token = secrets.token_urlsafe(32)
        now = datetime.now()
        expires = now + timedelta(hours=expiry_hours)

        data = {
            'family_circle_id': family_circle_id,
            'code': code,
            'created_by': created_by,
            'created_at': now.isoformat(),
            'expires_at': expires.isoformat(),
            'max_uses': max_uses,
            'deep_link_token': deep_link_token
        }
        result = self.client.table('invite_codes').insert(data).execute()

        return {
            'id': result.data[0]['id'],
            'code': code,
            'deep_link_token': deep_link_token,
            'expires_at': expires.isoformat(),
            'max_uses': max_uses
        }

    def get_invite_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Get invite code if valid."""
        result = self.client.table('invite_codes').select(
            '*, family_circles(name)'
        ).eq('code', code.upper()).eq('is_active', True).gt(
            'expires_at', datetime.now().isoformat()
        ).execute()

        if result.data and result.data[0]['current_uses'] < result.data[0]['max_uses']:
            row = result.data[0]
            row['circle_name'] = row['family_circles']['name'] if row['family_circles'] else None
            return row
        return None

    def get_invite_by_deep_link(self, token: str) -> Optional[Dict[str, Any]]:
        """Get invite code by deep link token."""
        result = self.client.table('invite_codes').select(
            '*, family_circles(name)'
        ).eq('deep_link_token', token).eq('is_active', True).gt(
            'expires_at', datetime.now().isoformat()
        ).execute()

        if result.data and result.data[0]['current_uses'] < result.data[0]['max_uses']:
            row = result.data[0]
            row['circle_name'] = row['family_circles']['name'] if row['family_circles'] else None
            return row
        return None

    def use_invite_code(self, code: str, user_id: int, relationship: str = 'family_member') -> bool:
        """Use an invite code to join a family circle."""
        invite = self.get_invite_code(code)
        if not invite:
            return False

        # Increment usage count
        self.client.table('invite_codes').update({
            'current_uses': invite['current_uses'] + 1
        }).eq('code', code.upper()).execute()

        # Add member to circle
        try:
            member_data = {
                'family_circle_id': invite['family_circle_id'],
                'user_id': user_id,
                'relationship': relationship,
                'permissions': ['view', 'set_reminders'],
                'joined_date': datetime.now().isoformat()
            }
            self.client.table('family_members').insert(member_data).execute()
            return True
        except Exception:
            return False

    def deactivate_invite_code(self, code: str) -> bool:
        """Deactivate an invite code."""
        self.client.table('invite_codes').update({'is_active': False}).eq('code', code.upper()).execute()
        return True

    # LOGIN ATTEMPTS
    def record_login_attempt(self, identifier: str, attempt_type: str, success: bool,
                             ip_address: str = None, user_agent: str = None) -> int:
        """Record a login attempt."""
        data = {
            'identifier': identifier,
            'attempt_type': attempt_type,
            'success': success,
            'ip_address': ip_address,
            'user_agent': user_agent,
            'timestamp': datetime.now().isoformat()
        }
        result = self.client.table('login_attempts').insert(data).execute()
        return result.data[0]['id']

    def get_recent_failed_attempts(self, identifier: str, minutes: int = 15) -> int:
        """Get count of failed login attempts in the last X minutes."""
        since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        result = self.client.table('login_attempts').select('id').eq(
            'identifier', identifier
        ).eq('success', False).gt('timestamp', since).execute()
        return len(result.data)

    def get_recent_otp_requests(self, identifier: str, minutes: int = 10) -> int:
        """Count OTP issuance attempts independently of verification failures."""
        since = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        result = self.client.table('login_attempts').select('id', count='exact').eq(
            'identifier', identifier
        ).eq('attempt_type', 'otp_request').gt('timestamp', since).execute()
        return result.count or 0

    def set_lockout(self, identifier: str, lockout_minutes: int = 30) -> bool:
        """Set lockout for an identifier."""
        lockout_until = (datetime.now() + timedelta(minutes=lockout_minutes)).isoformat()
        # Get the most recent attempt
        result = self.client.table('login_attempts').select('id').eq(
            'identifier', identifier
        ).order('timestamp', desc=True).limit(1).execute()

        if result.data:
            self.client.table('login_attempts').update({
                'lockout_until': lockout_until
            }).eq('id', result.data[0]['id']).execute()
        return True

    def is_locked_out(self, identifier: str) -> bool:
        """Check if identifier is currently locked out."""
        result = self.client.table('login_attempts').select('lockout_until').eq(
            'identifier', identifier
        ).not_.is_('lockout_until', 'null').order('timestamp', desc=True).limit(1).execute()

        if result.data and result.data[0]['lockout_until']:
            return result.data[0]['lockout_until'] > datetime.now().isoformat()
        return False

    def cleanup_old_login_attempts(self, days: int = 30) -> int:
        """Remove old login attempts."""
        since = (datetime.now() - timedelta(days=days)).isoformat()
        result = self.client.table('login_attempts').delete().lt('timestamp', since).execute()
        return len(result.data) if result.data else 0

    # --- Reminder Engine Ledger (see REMINDER_ENGINE.md) ---

    def notification_sent(self, patient_id: int, medication_name: str, scheduled_time: str,
                          date: str, stage: str) -> bool:
        """Whether a reminder stage for this dose on this date is already recorded."""
        result = self.client.table('notification_log').select('id').eq(
            'patient_id', patient_id
        ).eq('medication_name', medication_name).eq(
            'scheduled_time', scheduled_time
        ).eq('date', date).eq('stage', stage).execute()
        return bool(result.data)

    def record_notification(self, patient_id: int, medication_name: str, scheduled_time: str,
                            date: str, stage: str) -> bool:
        """Record that a reminder stage was sent (or superseded). Idempotent.

        Returns True if newly recorded, False if it already existed. The
        client has no simple ON CONFLICT, so guard with notification_sent and
        let the UNIQUE constraint reject a lost race (caught -> False).
        """
        if self.notification_sent(patient_id, medication_name, scheduled_time, date, stage):
            return False
        try:
            self.client.table('notification_log').insert({
                'patient_id': patient_id,
                'medication_name': medication_name,
                'scheduled_time': scheduled_time,
                'date': date,
                'stage': stage,
                'sent_at': datetime.now().isoformat(),
            }).execute()
            return True
        except Exception:
            return False

    def get_caregiver_contacts(self, patient_id: int) -> List[Dict[str, Any]]:
        """Family members with a phone who share a circle with the patient.

        The recipients of a caregiver escalation alert, deduped by user id.
        """
        patient_rows = self.client.table('family_members').select(
            'family_circle_id'
        ).eq('user_id', patient_id).execute()
        circle_ids = {row['family_circle_id'] for row in patient_rows.data}

        contacts = {}
        for circle_id in circle_ids:
            for member in self.get_family_circle_members(circle_id):
                if member['role'] == 'family_member' and member.get('phone'):
                    contacts[member['id']] = {
                        'id': member['id'],
                        'name': member['name'],
                        'phone': member['phone'],
                        'email': member.get('email'),
                    }
        return list(contacts.values())
