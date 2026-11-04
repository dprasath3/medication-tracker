import os
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NotificationService:
    """Handle SMS and Email notifications for medication reminders."""
    
    def __init__(self):
        # Twilio credentials (from environment variables for security)
        self.twilio_account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        
        # Email credentials
        self.email_address = os.getenv('EMAIL_ADDRESS')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        
        # Initialize Twilio client if credentials exist
        if self.twilio_account_sid and self.twilio_auth_token:
            self.twilio_client = Client(self.twilio_account_sid, self.twilio_auth_token)
        else:
            self.twilio_client = None
            logger.warning("Twilio credentials not found. SMS notifications disabled.")
    
    def send_sms(self, to_phone: str, message: str) -> bool:
        """Send SMS reminder via Twilio."""
        if not self.twilio_client:
            logger.error("SMS service not configured")
            return False

        try:
            message = self.twilio_client.messages.create(
                body=message,
                from_=self.twilio_phone,
                to=to_phone
            )
            logger.info("SMS accepted by provider")
            return True
        except Exception as e:
            # Provider errors may include the recipient or message body (OTP).
            logger.error("SMS provider request failed (%s)", type(e).__name__)
            return False

    def send_otp(self, to_phone: str, otp_code: str, expiry_minutes: int = 5) -> bool:
        """
        Send OTP verification code via SMS.

        Args:
            to_phone: Phone number in E.164 format
            otp_code: The OTP code to send
            expiry_minutes: How long the code is valid

        Returns:
            True if sent successfully, False otherwise
        """
        message = f"Your FamilyCare verification code is: {otp_code}\n\nThis code expires in {expiry_minutes} minutes. Do not share this code with anyone."
        return self.send_sms(to_phone, message)

    # ==================== REMINDER ENGINE MESSAGES ====================
    # SMS-only, scheduled-time-aware messages for the escalation engine
    # (see REMINDER_ENGINE.md). Each returns send_sms's real result, so a
    # missing phone or a failed send is False and the engine will retry —
    # it never records a phantom send. Semi-formal copy: no emoji, no
    # exclamation marks, per the design pillars.

    def _format_time(self, hhmm: str) -> str:
        """Render a stored 'HH:MM' dose time as '8:00 AM' for message copy."""
        try:
            return datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p")
        except (ValueError, TypeError):
            return hhmm

    def send_dose_reminder(self, patient: Dict, medication: Dict, scheduled_time: str) -> bool:
        """T+0 reminder to the patient that a dose is due."""
        phone = patient.get('phone')
        if not phone:
            return False
        when = self._format_time(scheduled_time)
        message = (
            f"Time for your {medication['name']} ({medication['dosage']}), "
            f"scheduled for {when}. Mark it in the app once you've taken it."
        )
        return self.send_sms(phone, message)

    def send_dose_followup(self, patient: Dict, medication: Dict, scheduled_time: str) -> bool:
        """T+30 follow-up when the dose still isn't logged."""
        phone = patient.get('phone')
        if not phone:
            return False
        when = self._format_time(scheduled_time)
        message = (
            f"Your {medication['name']} ({medication['dosage']}) from {when} "
            f"isn't marked as taken yet. Please take it if you haven't already."
        )
        return self.send_sms(phone, message)

    def send_caregiver_alert(self, caregiver: Dict, patient: Dict, medication: Dict,
                             scheduled_time: str) -> bool:
        """T+60 alert to a caregiver that a patient's dose is still not logged."""
        phone = caregiver.get('phone')
        if not phone:
            return False
        when = self._format_time(scheduled_time)
        message = (
            f"FamilyCare: {patient['name']} hasn't logged {medication['name']} "
            f"({medication['dosage']}) scheduled for {when}. You may want to check in."
        )
        return self.send_sms(phone, message)

    def send_verification_email(self, to_email: str, user_name: str, verification_link: str) -> bool:
        """Send email verification link."""
        subject = "Verify Your FamilyCare Email"
        body = f"""
Hello {user_name},

Please verify your email address by clicking the link below:

{verification_link}

This link expires in 24 hours.

If you didn't create an account with FamilyCare, please ignore this email.

---
FamilyCare Medication Tracker
        """

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #2d5a27;">Verify Your Email</h2>
                <p>Hello {user_name},</p>
                <p>Please verify your email address by clicking the button below:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verification_link}"
                       style="display: inline-block; padding: 14px 28px; background-color: #4a7c59;
                              color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Verify Email Address
                    </a>
                </div>
                <p style="color: #666; font-size: 14px;">This link expires in 24 hours.</p>
                <p style="color: #666; font-size: 14px;">If you didn't create an account with FamilyCare, please ignore this email.</p>
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                <p style="font-size: 12px; color: #999;">FamilyCare Medication Tracker</p>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, body, html)

    def send_password_reset_email(self, to_email: str, user_name: str, reset_link: str) -> bool:
        """Send password reset link."""
        subject = "Reset Your FamilyCare Password"
        body = f"""
Hello {user_name},

We received a request to reset your password. Click the link below to create a new password:

{reset_link}

This link expires in 1 hour.

If you didn't request a password reset, please ignore this email. Your password will remain unchanged.

---
FamilyCare Medication Tracker
        """

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #2d5a27;">Reset Your Password</h2>
                <p>Hello {user_name},</p>
                <p>We received a request to reset your password. Click the button below to create a new password:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}"
                       style="display: inline-block; padding: 14px 28px; background-color: #4a7c59;
                              color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Reset Password
                    </a>
                </div>
                <p style="color: #666; font-size: 14px;">This link expires in 1 hour.</p>
                <p style="color: #666; font-size: 14px;">If you didn't request a password reset, please ignore this email. Your password will remain unchanged.</p>
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                <p style="font-size: 12px; color: #999;">FamilyCare Medication Tracker</p>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, body, html)

    def send_login_alert(self, to_email: str, user_name: str, device_info: str, login_time: str) -> bool:
        """Send alert for new login from unknown device."""
        subject = "New Login to Your FamilyCare Account"
        body = f"""
Hello {user_name},

A new login to your FamilyCare account was detected:

Device: {device_info}
Time: {login_time}

If this was you, no action is needed.

If you didn't log in, please secure your account immediately by changing your password.

---
FamilyCare Medication Tracker
        """

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #2d5a27;">New Login Detected</h2>
                <p>Hello {user_name},</p>
                <p>A new login to your FamilyCare account was detected:</p>
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Device:</strong> {device_info}</p>
                    <p style="margin: 5px 0;"><strong>Time:</strong> {login_time}</p>
                </div>
                <p>If this was you, no action is needed.</p>
                <p style="color: #d32f2f;">If you didn't log in, please secure your account immediately by changing your password.</p>
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                <p style="font-size: 12px; color: #999;">FamilyCare Medication Tracker</p>
            </div>
        </body>
        </html>
        """

        return self.send_email(to_email, subject, body, html)
    
    def send_email(self, to_email: str, subject: str, body: str, html_body: str = None) -> bool:
        """Send email reminder."""
        if not self.email_address or not self.email_password:
            logger.error("Email service not configured")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_address
            msg['To'] = to_email
            
            # Add text and HTML parts
            text_part = MIMEText(body, 'plain')
            msg.attach(text_part)
            
            if html_body:
                html_part = MIMEText(html_body, 'html')
                msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_medication_reminder(self, user: Dict, medication: Dict, reminder_method: str = 'both') -> bool:
        """Send medication reminder via preferred method."""
        med_name = medication['name']
        dosage = medication['dosage']
        time_str = datetime.now().strftime("%I:%M %p")
        
        # Create message
        sms_message = f"💊 Medication Reminder: Take {dosage} of {med_name} at {time_str}"
        
        email_subject = f"🔔 Time to Take Your Medication: {med_name}"
        email_body = f"""
Hello {user['name']},

This is your friendly reminder to take your medication:

Medication: {med_name}
Dosage: {dosage}
Time: {time_str}

Stay healthy!

---
FamilyCare Medication Tracker
        """
        
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px;">
                <h2 style="color: #2d5a27;">💊 Medication Reminder</h2>
                <p>Hello {user['name']},</p>
                <p>This is your friendly reminder to take your medication:</p>
                <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>Medication:</strong> {med_name}</p>
                    <p style="margin: 5px 0;"><strong>Dosage:</strong> {dosage}</p>
                    <p style="margin: 5px 0;"><strong>Time:</strong> {time_str}</p>
                </div>
                <p>Stay healthy!</p>
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 20px 0;">
                <p style="font-size: 12px; color: #666;">FamilyCare Medication Tracker</p>
            </div>
        </body>
        </html>
        """
        
        success = True
        
        # Send based on user preference
        if reminder_method in ['sms', 'both'] and user.get('phone'):
            success &= self.send_sms(user['phone'], sms_message)
        
        if reminder_method in ['email', 'both'] and user.get('email'):
            success &= self.send_email(user['email'], email_subject, email_body, email_html)
        
        return success
    
    def send_weekly_report(self, user: Dict, adherence_data: Dict, family_emails: List[str] = None) -> bool:
        """Send weekly compliance report to user and family members."""
        report_html = self._generate_weekly_report_html(user, adherence_data)
        
        subject = f"📊 Weekly Medication Report for {user['name']}"
        body = f"Weekly medication adherence report for {user['name']}. Please view the HTML version for details."
        
        # Send to user
        success = self.send_email(user['email'], subject, body, report_html)
        
        # Send to family members
        if family_emails:
            for family_email in family_emails:
                self.send_email(family_email, subject, body, report_html)
        
        return success
    
    def _generate_weekly_report_html(self, user: Dict, adherence_data: Dict) -> str:
        """Generate HTML for weekly report."""
        adherence_rate = adherence_data.get('adherence_rate', 0)
        total_doses = adherence_data.get('total_doses', 0)
        taken_doses = adherence_data.get('taken_doses', 0)
        missed_doses = adherence_data.get('missed_doses', 0)
        
        # Color coding based on adherence
        if adherence_rate >= 90:
            color = "#4caf50"
            status = "Excellent"
        elif adherence_rate >= 70:
            color = "#ff9800"
            status = "Good"
        else:
            color = "#f44336"
            status = "Needs Improvement"
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
            <div style="max-width: 700px; margin: 0 auto; background-color: white; padding: 40px; border-radius: 10px;">
                <h1 style="color: #2d5a27; text-align: center;">📊 Weekly Medication Report</h1>
                <h3 style="color: #4a7c59; text-align: center;">For {user['name']}</h3>
                <p style="text-align: center; color: #666;">Week of {adherence_data.get('week_start')} to {adherence_data.get('week_end')}</p>
                
                <div style="background-color: {color}; color: white; padding: 30px; border-radius: 10px; text-align: center; margin: 30px 0;">
                    <h2 style="margin: 0; font-size: 48px;">{adherence_rate:.1f}%</h2>
                    <p style="margin: 10px 0 0 0; font-size: 18px;">Medication Adherence - {status}</p>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 30px 0;">
                    <div style="background-color: #e8f5e8; padding: 20px; border-radius: 8px; text-align: center;">
                        <h3 style="color: #2d5a27; margin: 0;">✅ {taken_doses}</h3>
                        <p style="color: #4a7c59; margin: 10px 0 0 0;">Doses Taken</p>
                    </div>
                    <div style="background-color: #fff3e0; padding: 20px; border-radius: 8px; text-align: center;">
                        <h3 style="color: #f57c00; margin: 0;">❌ {missed_doses}</h3>
                        <p style="color: #ef6c00; margin: 10px 0 0 0;">Doses Missed</p>
                    </div>
                    <div style="background-color: #e3f2fd; padding: 20px; border-radius: 8px; text-align: center;">
                        <h3 style="color: #1976d2; margin: 0;">💊 {total_doses}</h3>
                        <p style="color: #1565c0; margin: 10px 0 0 0;">Total Scheduled</p>
                    </div>
                </div>
                
                <h3 style="color: #2d5a27; margin-top: 40px;">Daily Breakdown:</h3>
                {self._generate_daily_breakdown_html(adherence_data.get('daily_data', []))}
                
                <div style="background-color: #f5f5f5; padding: 20px; border-radius: 8px; margin-top: 30px;">
                    <h4 style="color: #2d5a27; margin-top: 0;">💡 Tips for Better Adherence:</h4>
                    <ul style="color: #555; line-height: 1.8;">
                        <li>Set alarms on your phone for medication times</li>
                        <li>Keep medications in a visible location</li>
                        <li>Use a pill organizer to track weekly doses</li>
                        <li>Take medications at the same time as daily routines (meals, bedtime)</li>
                    </ul>
                </div>
                
                <p style="text-align: center; margin-top: 40px; color: #888;">
                    Keep up the great work! Your health is important to us. 💚
                </p>
                
                <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 30px 0;">
                <p style="font-size: 12px; color: #999; text-align: center;">
                    This report was automatically generated by FamilyCare Medication Tracker
                </p>
            </div>
        </body>
        </html>
        """
        return html
    
    def _generate_daily_breakdown_html(self, daily_data: List[Dict]) -> str:
        """Generate HTML table for daily breakdown."""
        if not daily_data:
            return "<p>No data available for this period.</p>"
        
        rows = ""
        for day in daily_data:
            date = day.get('date', '')
            taken = day.get('taken', 0)
            missed = day.get('missed', 0)
            rate = day.get('adherence_rate', 0)
            
            # Color code the rate
            if rate >= 90:
                rate_color = "#4caf50"
            elif rate >= 70:
                rate_color = "#ff9800"
            else:
                rate_color = "#f44336"
            
            rows += f"""
            <tr>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0;">{date}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; text-align: center;">✅ {taken}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; text-align: center;">❌ {missed}</td>
                <td style="padding: 12px; border-bottom: 1px solid #e0e0e0; text-align: center; color: {rate_color}; font-weight: bold;">{rate:.0f}%</td>
            </tr>
            """
        
        return f"""
        <table style="width: 100%; border-collapse: collapse; background-color: white;">
            <thead>
                <tr style="background-color: #e8f5e8;">
                    <th style="padding: 12px; text-align: left; color: #2d5a27;">Date</th>
                    <th style="padding: 12px; text-align: center; color: #2d5a27;">Taken</th>
                    <th style="padding: 12px; text-align: center; color: #2d5a27;">Missed</th>
                    <th style="padding: 12px; text-align: center; color: #2d5a27;">Rate</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """
