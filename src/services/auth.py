"""
Authentication service for FamilyCare Medication Tracker.
Handles phone OTP, email/password, and session management.
"""

import os
import re
import secrets
import hashlib
import hmac
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List

import bcrypt
import phonenumbers
from phonenumbers import NumberParseException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# OTP hashes are keyed with HMAC-SHA256 rather than a bare digest. A 6-digit
# OTP has only 10^6 possible values, so an unkeyed hash (the old plain SHA-256)
# is reversed by brute force in about a second by anyone with DB read access.
# The security here comes from the server-side secret, not a work factor, so
# verification stays fast — HMAC is the right fit, not bcrypt.
#
# Set MEDSYNC_OTP_SECRET in production. Without it we fall back to a random
# per-process secret: OTPs are short-lived (5 min), so invalidating any pending
# codes on restart is harmless, and a random key is still strong. The secret is
# resolved once at import so every AuthService instance in the process shares
# it — a per-instance secret would make request and verify disagree.
_OTP_SECRET = os.getenv('MEDSYNC_OTP_SECRET')
if not _OTP_SECRET:
    logger.warning(
        "MEDSYNC_OTP_SECRET is not set; using a random per-process secret. "
        "Pending OTPs will not survive a restart. Set it in production."
    )
    _OTP_SECRET = secrets.token_hex(32)
_OTP_SECRET_BYTES = _OTP_SECRET.encode()


# Base URL used to build the email verification and password-reset links. In
# local dev the Streamlit app serves on :8501, which is the default here so
# nothing changes for a developer. In a real deployment the emailed link must
# point at the public domain, so set APP_BASE_URL (e.g. https://app.example.com).
# Trailing slashes are stripped so the "{base}/?verify_email=..." join never
# produces a double slash. Resolved once at import, matching APP_TIMEZONE.
APP_BASE_URL = (os.getenv('APP_BASE_URL') or 'http://localhost:8501').rstrip('/')
if 'localhost' in APP_BASE_URL or '127.0.0.1' in APP_BASE_URL:
    logger.warning(
        "APP_BASE_URL is %r; emailed verify/reset links will point at localhost. "
        "Set APP_BASE_URL to the public domain in production.",
        APP_BASE_URL,
    )


class AuthService:
    """Core authentication service handling phone OTP, email/password, and sessions."""

    # Configuration
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    MAX_OTP_ATTEMPTS = 5
    SESSION_EXPIRY_DAYS = 7
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_MINUTES = 30
    OTP_RATE_LIMIT_MINUTES = 10
    MAX_OTP_REQUESTS = 3

    # Password requirements
    MIN_PASSWORD_LENGTH = 8

    def __init__(self, db, notification_service=None):
        """
        Initialize auth service.

        Args:
            db: MedicationDB instance
            notification_service: NotificationService instance for sending OTPs
        """
        self.db = db
        self.notifications = notification_service

    # ==================== PHONE NUMBER UTILITIES ====================

    def normalize_phone(self, phone: str, default_region: str = 'US') -> Optional[str]:
        """
        Normalize phone number to E.164 format.

        Args:
            phone: Phone number string
            default_region: Default region code (e.g., 'US')

        Returns:
            Normalized phone number or None if invalid
        """
        try:
            parsed = phonenumbers.parse(phone, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            return None
        except NumberParseException:
            return None

    def format_phone_display(self, phone: str) -> str:
        """Format phone number for display (masked)."""
        if len(phone) >= 10:
            return f"***-***-{phone[-4:]}"
        return "***-****"

    # ==================== OTP AUTHENTICATION ====================

    def _generate_otp(self) -> str:
        """Generate a secure 6-digit OTP."""
        return ''.join(secrets.choice('0123456789') for _ in range(self.OTP_LENGTH))

    def _hash_otp(self, otp: str) -> str:
        """Hash an OTP with HMAC-SHA256 keyed by a server-side secret.

        Keyed so DB read access alone cannot reverse the tiny 10^6 OTP
        keyspace. Compare hashes with ``hmac.compare_digest`` at the call site.
        """
        return hmac.new(_OTP_SECRET_BYTES, otp.encode(), hashlib.sha256).hexdigest()

    def _check_otp_rate_limit(self, phone: str) -> Tuple[bool, str]:
        """
        Check if phone has exceeded OTP request rate limit.

        Returns:
            (is_allowed, error_message)
        """
        # Check if locked out
        if self.db.is_locked_out(phone):
            return False, "Too many attempts. Please try again later."

        # Count recent OTP requests (within rate limit window)
        recent_attempts = self.db.get_recent_failed_attempts(
            phone, minutes=self.OTP_RATE_LIMIT_MINUTES
        )

        recent_requests = self.db.get_recent_otp_requests(
            phone, minutes=self.OTP_RATE_LIMIT_MINUTES
        )
        if max(recent_attempts, recent_requests) >= self.MAX_OTP_REQUESTS:
            return False, f"Too many OTP requests. Please wait {self.OTP_RATE_LIMIT_MINUTES} minutes."

        return True, ""

    def request_otp(self, phone: str, purpose: str = 'login') -> Dict[str, Any]:
        """
        Request OTP for phone authentication.

        Args:
            phone: Phone number
            purpose: 'login', 'register', or 'verify_phone'

        Returns:
            Dict with success status and message
        """
        # Normalize phone number
        normalized_phone = self.normalize_phone(phone)
        if not normalized_phone:
            return {
                'success': False,
                'error': 'Invalid phone number format'
            }

        # Check rate limiting
        allowed, error = self._check_otp_rate_limit(normalized_phone)
        if not allowed:
            return {'success': False, 'error': error}

        # Check if user exists for login
        user = self.db.get_user_by_phone(normalized_phone)
        user_id = user['id'] if user else None

        if purpose == 'login' and not user:
            # For login, user must exist - but don't reveal this for security
            # Still send OTP to prevent phone enumeration
            pass

        # Count issuance attempts, including failed delivery, separately from
        # verification failures. Replacing a pending OTP must not reset the limit.
        self.db.record_login_attempt(normalized_phone, "otp_request", True)

        # Generate OTP
        otp = self._generate_otp()
        otp_hash = self._hash_otp(otp)

        # Store OTP
        self.db.create_otp(
            phone=normalized_phone,
            otp_hash=otp_hash,
            purpose=purpose,
            user_id=user_id,
            expiry_minutes=self.OTP_EXPIRY_MINUTES
        )

        # Send OTP via SMS. Having a NotificationService instance is not the
        # same as SMS being configured — without Twilio credentials send_sms
        # always fails, which used to dead-end signup on dev machines.
        sms_configured = bool(
            self.notifications and getattr(self.notifications, 'twilio_client', None)
        )
        if sms_configured:
            message = f"Your FamilyCare verification code is: {otp}. Valid for {self.OTP_EXPIRY_MINUTES} minutes."
            sent = self.notifications.send_sms(normalized_phone, message)
            if not sent:
                logger.warning(f"Failed to send OTP SMS to {self.format_phone_display(normalized_phone)}")
                return {
                    'success': False,
                    'error': 'Failed to send verification code. Please try again.'
                }
        else:
            # For development without SMS configured
            logger.info("SMS is disabled; no verification message was sent.")

        result = {
            'success': True,
            'message': f'Verification code sent to {self.format_phone_display(normalized_phone)}',
            'phone': normalized_phone,
            'expires_in': self.OTP_EXPIRY_MINUTES * 60  # seconds
        }
        if not sms_configured and os.getenv('MEDSYNC_DEV_SHOW_OTP') == '1':
            # Dev-only escape hatch: exposing the OTP to the requester lets
            # anyone sign in as any phone number, so it must never be on in
            # production. Requires the env var to be set explicitly.
            result['dev_otp'] = otp
        return result

    def verify_otp(self, phone: str, otp_code: str) -> Dict[str, Any]:
        """
        Verify OTP and authenticate user.

        Args:
            phone: Phone number
            otp_code: The OTP code entered by user

        Returns:
            Dict with success status, user data, and session token
        """
        normalized_phone = self.normalize_phone(phone)
        if not normalized_phone:
            return {'success': False, 'error': 'Invalid phone number'}

        # Check lockout
        if self.db.is_locked_out(normalized_phone):
            return {
                'success': False,
                'error': f'Account temporarily locked. Try again in {self.LOCKOUT_MINUTES} minutes.'
            }

        # Get active OTP
        otp_record = self.db.get_active_otp(normalized_phone)
        if not otp_record:
            self.db.record_login_attempt(normalized_phone, 'phone_otp', False)
            return {
                'success': False,
                'error': 'Verification code expired or not found. Please request a new one.'
            }

        # Check max attempts
        if otp_record['attempts'] >= self.MAX_OTP_ATTEMPTS:
            self.db.set_lockout(normalized_phone, self.LOCKOUT_MINUTES)
            return {
                'success': False,
                'error': 'Too many failed attempts. Please request a new code.'
            }

        # Verify OTP
        otp_hash = self._hash_otp(otp_code)
        if not hmac.compare_digest(otp_hash, otp_record['otp_hash']):
            self.db.increment_otp_attempts(otp_record['id'])
            remaining = self.MAX_OTP_ATTEMPTS - otp_record['attempts'] - 1
            self.db.record_login_attempt(normalized_phone, 'phone_otp', False)
            return {
                'success': False,
                'error': f'Invalid code. {remaining} attempts remaining.'
            }

        # OTP verified
        self.db.mark_otp_verified(otp_record['id'])
        self.db.record_login_attempt(normalized_phone, 'phone_otp', True)

        # Get or create user
        user = self.db.get_user_by_phone(normalized_phone)

        if user:
            # Existing user - update phone verification and last login
            self.db.update_user(user['id'], phone_verified=1, last_login=datetime.now().isoformat())

            # Create session
            session_token = self._create_session_token(user['id'])

            return {
                'success': True,
                'user': user,
                'session_token': session_token,
                'is_new_user': False
            }
        else:
            # New user - return success but indicate registration needed
            return {
                'success': True,
                'phone': normalized_phone,
                'is_new_user': True,
                'purpose': otp_record['purpose']
            }

    # ==================== PASSWORD AUTHENTICATION ====================

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash."""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False

    def validate_password_strength(self, password: str) -> Tuple[bool, List[str]]:
        """
        Validate password meets requirements.

        Returns:
            (is_valid, list of error messages)
        """
        errors = []

        if len(password) < self.MIN_PASSWORD_LENGTH:
            errors.append(f"Password must be at least {self.MIN_PASSWORD_LENGTH} characters")

        if not re.search(r'[A-Z]', password):
            errors.append("Password must contain at least one uppercase letter")

        if not re.search(r'[a-z]', password):
            errors.append("Password must contain at least one lowercase letter")

        if not re.search(r'\d', password):
            errors.append("Password must contain at least one digit")

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("Password must contain at least one special character")

        return len(errors) == 0, errors

    def register_with_email(self, email: str, password: str, name: str,
                            phone: str = None, age: int = None,
                            role: str = 'patient') -> Dict[str, Any]:
        """
        Register new user with email and password.

        Returns:
            Dict with success status, user data, and session token
        """
        # Validate email format
        if not self._is_valid_email(email):
            return {'success': False, 'error': 'Invalid email format'}

        # Check if email already exists
        existing = self.db.get_user_by_email(email)
        if existing:
            return {'success': False, 'error': 'Email already registered'}

        # Validate password strength
        is_strong, errors = self.validate_password_strength(password)
        if not is_strong:
            return {'success': False, 'error': errors[0], 'password_errors': errors}

        # Normalize phone if provided
        normalized_phone = None
        if phone:
            normalized_phone = self.normalize_phone(phone)

        # Create user
        user_id = self.db.add_user(
            name=name,
            email=email,
            age=age,
            role=role,
            phone=normalized_phone
        )

        # Create credentials
        password_hash = self.hash_password(password)
        self.db.create_user_credentials(user_id, password_hash)

        # Get created user
        user = self.db.get_user_by_id(user_id)

        # Create session
        session_token = self._create_session_token(user_id)

        # Send email verification (optional)
        self._send_email_verification(user_id, email)

        return {
            'success': True,
            'user': user,
            'session_token': session_token,
            'message': 'Account created successfully'
        }

    def login_with_email(self, email: str, password: str) -> Dict[str, Any]:
        """
        Login with email and password.

        Returns:
            Dict with success status, user data, and session token
        """
        # Check lockout
        if self.db.is_locked_out(email):
            return {
                'success': False,
                'error': f'Account temporarily locked. Try again in {self.LOCKOUT_MINUTES} minutes.'
            }

        # Find user
        user = self.db.get_user_by_email(email)
        if not user:
            self.db.record_login_attempt(email, 'password', False)
            return {'success': False, 'error': 'Invalid email or password'}

        # Get credentials
        credentials = self.db.get_user_credentials(user['id'])
        if not credentials:
            return {'success': False, 'error': 'No password set for this account. Use phone login.'}

        # Verify password
        if not self.verify_password(password, credentials['password_hash']):
            self.db.record_login_attempt(email, 'password', False)

            # Check if should lock out
            failed_attempts = self.db.get_recent_failed_attempts(email, minutes=15)
            if failed_attempts >= self.MAX_LOGIN_ATTEMPTS:
                self.db.set_lockout(email, self.LOCKOUT_MINUTES)
                return {
                    'success': False,
                    'error': f'Too many failed attempts. Account locked for {self.LOCKOUT_MINUTES} minutes.'
                }

            return {'success': False, 'error': 'Invalid email or password'}

        # Success
        self.db.record_login_attempt(email, 'password', True)
        self.db.update_user(user['id'], last_login=datetime.now().isoformat())

        # Create session
        session_token = self._create_session_token(user['id'])

        return {
            'success': True,
            'user': user,
            'session_token': session_token,
            'email_verified': credentials.get('email_verified', False)
        }

    def _is_valid_email(self, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _send_email_verification(self, user_id: int, email: str) -> bool:
        """Send email verification link."""
        token = secrets.token_urlsafe(32)
        self.db.set_email_verification_token(user_id, token, expiry_hours=24)

        if self.notifications:
            verification_link = f"{APP_BASE_URL}/?verify_email={token}"
            subject = "Verify Your FamilyCare Email"
            body = f"Click the link to verify your email: {verification_link}"
            html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #2d5a27;">Verify Your Email</h2>
                <p>Click the button below to verify your email address:</p>
                <a href="{verification_link}"
                   style="display: inline-block; padding: 12px 24px; background-color: #4a7c59;
                          color: white; text-decoration: none; border-radius: 5px;">
                    Verify Email
                </a>
                <p style="color: #666; margin-top: 20px;">
                    This link expires in 24 hours.
                </p>
            </body>
            </html>
            """
            return self.notifications.send_email(email, subject, body, html)
        return False

    # ==================== PASSWORD RESET ====================

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        """
        Request password reset email.

        Returns:
            Dict with success status (always true to prevent enumeration)
        """
        user = self.db.get_user_by_email(email)

        if user:
            credentials = self.db.get_user_credentials(user['id'])
            if credentials:
                token = secrets.token_urlsafe(32)
                self.db.set_password_reset_token(user['id'], token, expiry_hours=1)

                if self.notifications:
                    reset_link = f"{APP_BASE_URL}/?reset_password={token}"
                    subject = "Reset Your FamilyCare Password"
                    body = f"Click the link to reset your password: {reset_link}"
                    html = f"""
                    <html>
                    <body style="font-family: Arial, sans-serif; padding: 20px;">
                        <h2 style="color: #2d5a27;">Reset Your Password</h2>
                        <p>Click the button below to reset your password:</p>
                        <a href="{reset_link}"
                           style="display: inline-block; padding: 12px 24px; background-color: #4a7c59;
                                  color: white; text-decoration: none; border-radius: 5px;">
                            Reset Password
                        </a>
                        <p style="color: #666; margin-top: 20px;">
                            This link expires in 1 hour. If you didn't request this, ignore this email.
                        </p>
                    </body>
                    </html>
                    """
                    self.notifications.send_email(email, subject, body, html)

        # Always return success to prevent email enumeration
        return {
            'success': True,
            'message': 'If an account exists with this email, you will receive a reset link.'
        }

    def reset_password(self, token: str, new_password: str) -> Dict[str, Any]:
        """
        Reset password using token.

        Returns:
            Dict with success status
        """
        # Validate token
        user_id = self.db.verify_password_reset_token(token)
        if not user_id:
            return {'success': False, 'error': 'Invalid or expired reset link'}

        # Validate new password
        is_strong, errors = self.validate_password_strength(new_password)
        if not is_strong:
            return {'success': False, 'error': errors[0], 'password_errors': errors}

        # Update password
        password_hash = self.hash_password(new_password)
        self.db.update_password_hash(user_id, password_hash)
        self.db.clear_password_reset_token(user_id)

        # Invalidate all existing sessions for security
        self.db.invalidate_all_user_sessions(user_id)

        return {
            'success': True,
            'message': 'Password reset successfully. Please login with your new password.'
        }

    # ==================== SESSION MANAGEMENT ====================

    def _create_session_token(self, user_id: int, device_name: str = None,
                               ip_address: str = None) -> str:
        """Create a new session and return the token."""
        token = secrets.token_urlsafe(32)

        self.db.create_session(
            user_id=user_id,
            session_token=token,
            device_name=device_name,
            ip_address=ip_address,
            expiry_days=self.SESSION_EXPIRY_DAYS
        )

        return token

    def validate_session(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Validate session token and return user data.

        Returns:
            User dict if valid, None otherwise
        """
        if not token:
            return None

        session = self.db.get_session_by_token(token)
        if not session:
            return None

        # Update last activity
        self.db.update_session_activity(token)

        # Get user
        user = self.db.get_user_by_id(session['user_id'])
        return user

    def logout(self, token: str) -> bool:
        """Invalidate session (logout)."""
        return self.db.invalidate_session(token)

    def logout_all_devices(self, user_id: int) -> int:
        """Logout from all devices."""
        return self.db.invalidate_all_user_sessions(user_id)

    def get_active_sessions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active sessions for a user."""
        return self.db.get_user_active_sessions(user_id)

    # ==================== USER REGISTRATION ====================

    def complete_phone_registration(self, phone: str, name: str, email: str = None,
                                    password: str = None, age: int = None,
                                    role: str = 'patient') -> Dict[str, Any]:
        """
        Complete registration after phone OTP verification.

        Args:
            phone: Verified phone number
            name: User's name
            email: Optional email
            password: Optional password (for email login)
            age: Optional age
            role: 'patient' or 'family_member'

        Returns:
            Dict with success status, user data, and session token
        """
        normalized_phone = self.normalize_phone(phone)
        if not normalized_phone:
            return {'success': False, 'error': 'Invalid phone number'}

        # Check if phone already registered
        existing = self.db.get_user_by_phone(normalized_phone)
        if existing:
            return {'success': False, 'error': 'Phone number already registered'}

        # Validate email if provided
        if email:
            if not self._is_valid_email(email):
                return {'success': False, 'error': 'Invalid email format'}
            if self.db.get_user_by_email(email):
                return {'success': False, 'error': 'Email already registered'}

        # Validate password if provided
        if password:
            is_strong, errors = self.validate_password_strength(password)
            if not is_strong:
                return {'success': False, 'error': errors[0], 'password_errors': errors}

        # Create user
        user_id = self.db.add_user(
            name=name,
            email=email,
            age=age,
            role=role,
            phone=normalized_phone
        )

        # Mark phone as verified
        self.db.update_user(user_id, phone_verified=1, primary_auth_method='phone')

        # Create credentials if password provided
        if password:
            password_hash = self.hash_password(password)
            self.db.create_user_credentials(user_id, password_hash)

        # Get created user
        user = self.db.get_user_by_id(user_id)

        # Create session
        session_token = self._create_session_token(user_id)

        return {
            'success': True,
            'user': user,
            'session_token': session_token,
            'message': 'Account created successfully'
        }

    # ==================== CLEANUP UTILITIES ====================

    def cleanup(self) -> Dict[str, int]:
        """Run cleanup tasks for expired data."""
        return {
            'expired_otps': self.db.cleanup_expired_otps(),
            'expired_sessions': self.db.cleanup_expired_sessions(),
            'old_login_attempts': self.db.cleanup_old_login_attempts(days=30)
        }
