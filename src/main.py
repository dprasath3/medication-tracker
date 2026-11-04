#!/usr/bin/env python3
"""
Medication Tracker - Background Service
Runs automated reminders and weekly reports in the background.
This should be run alongside the Streamlit web app.
"""

import sys
import os
import time
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add the current directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Scheduler configuration is resolved during import. Load .env first.
load_dotenv()

from utils.authz import SYSTEM_CALLER
from utils.db_factory import get_database
from services.scheduler import MedicationScheduler
from services.notifications import NotificationService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('medication_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_environment():
    """Load environment variables from .env file."""
    load_dotenv()
    logger.info("Environment variables loaded")
    
    # Check if critical env variables are set
    required_vars = ['EMAIL_ADDRESS', 'EMAIL_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.warning(f"Missing environment variables: {', '.join(missing_vars)}")
        logger.warning("Email notifications may not work. Please configure .env file.")
    
    # Check optional Twilio variables
    twilio_vars = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER']
    missing_twilio = [var for var in twilio_vars if not os.getenv(var)]
    
    if missing_twilio:
        logger.warning(f"Twilio not configured: {', '.join(missing_twilio)}")
        logger.warning("SMS notifications disabled. Email only.")

def test_notifications():
    """Test the notification system."""
    logger.info("Testing notification system...")
    
    db = get_database()
    notification_service = NotificationService()
    
    # Get first user for testing
    users = db.get_users()
    if not users:
        logger.warning("No users found in database. Create a user through the web app first.")
        return False
    
    test_user = users[0]
    
    # Test medication data
    test_medication = {
        'name': 'Test Medication',
        'dosage': '100mg',
        'times': [datetime.now().strftime("%H:%M")]
    }
    
    # Try sending test notification
    logger.info(f"Sending test notification to {test_user['name']} ({test_user['email']})")
    
    try:
        success = notification_service.send_medication_reminder(
            test_user, 
            test_medication, 
            reminder_method='email'
        )
        
        if success:
            logger.info("✅ Test notification sent successfully!")
            return True
        else:
            logger.error("❌ Failed to send test notification")
            return False
    except Exception as e:
        logger.error(f"❌ Error sending test notification: {str(e)}")
        return False

def start_scheduler():
    """Start the background scheduler for automated reminders."""
    logger.info("Starting Medication Reminder Service...")
    
    try:
        # Initialize database
        db = get_database()
        logger.info("Database initialized")
        
        # Initialize scheduler and register the per-minute reminder tick +
        # weekly reports. The tick reads due doses from the DB each minute, so
        # new/edited medications are picked up automatically — no re-scheduling.
        scheduler = MedicationScheduler(db)
        scheduler.start()
        logger.info("Scheduler initialized")

        logger.info("=" * 60)
        logger.info("🎉 Medication Tracker Background Service Started!")
        logger.info("=" * 60)
        logger.info("✅ Reminder escalation tick: ACTIVE (every minute)")
        logger.info("✅ Weekly reports: SCHEDULED (Sundays at 6 PM)")
        logger.info("=" * 60)

        # Keep the service running; the scheduler thread does the work.
        try:
            while True:
                time.sleep(60)

        except KeyboardInterrupt:
            logger.info("\n🛑 Shutting down Medication Tracker Service...")
            scheduler.stop()
            logger.info("✅ Service stopped gracefully")
            
    except Exception as e:
        logger.error(f"❌ Error starting scheduler: {str(e)}")
        raise

def show_scheduled_jobs():
    """Display all currently scheduled reminder jobs."""
    logger.info("=" * 60)
    logger.info("📋 SCHEDULED MEDICATION REMINDERS")
    logger.info("=" * 60)
    
    db = get_database()
    users = db.get_users()
    
    if not users:
        logger.info("No users found in database.")
        return
    
    total_reminders = 0
    
    for user in users:
        if user['role'] == 'patient':
            medications = db.get_patient_medications(SYSTEM_CALLER, user['id'])
            
            if medications:
                logger.info(f"\n👤 {user['name']} ({user['email']})")
                logger.info(f"   Phone: {user['phone'] or 'Not provided'}")
                
                for med in medications:
                    logger.info(f"\n   💊 {med['name']} - {med['dosage']}")
                    for time in med['times']:
                        logger.info(f"      ⏰ {time} - Daily reminder")
                        total_reminders += 1
                    if med.get('notes'):
                        logger.info(f"      📝 {med['notes']}")
    
    logger.info("\n" + "=" * 60)
    logger.info(f"Total scheduled reminders: {total_reminders}")
    logger.info("=" * 60)

def run_menu():
    """Interactive menu for testing and management."""
    print("\n" + "=" * 60)
    print("🏥 FAMILYCARE MEDICATION TRACKER - BACKGROUND SERVICE")
    print("=" * 60)
    print("\nWhat would you like to do?")
    print("\n1. 🚀 Start Automated Reminder Service (Production)")
    print("2. 📋 View Scheduled Reminders")
    print("3. 🧪 Test Notification System")
    print("4. 📊 View Database Statistics")
    print("5. 🔧 Check Environment Configuration")
    print("6. ❌ Exit")
    print("\n" + "=" * 60)
    
    choice = input("\nEnter your choice (1-6): ").strip()
    
    if choice == '1':
        start_scheduler()
    
    elif choice == '2':
        show_scheduled_jobs()
        input("\nPress Enter to continue...")
        run_menu()
    
    elif choice == '3':
        test_notifications()
        input("\nPress Enter to continue...")
        run_menu()
    
    elif choice == '4':
        show_database_stats()
        input("\nPress Enter to continue...")
        run_menu()
    
    elif choice == '5':
        check_environment()
        input("\nPress Enter to continue...")
        run_menu()
    
    elif choice == '6':
        print("\n👋 Goodbye! Stay healthy!")
        sys.exit(0)
    
    else:
        print("\n❌ Invalid choice. Please try again.")
        time.sleep(1)
        run_menu()

def show_database_stats():
    """Display database statistics."""
    logger.info("=" * 60)
    logger.info("📊 DATABASE STATISTICS")
    logger.info("=" * 60)
    
    db = get_database()
    
    # Count users
    users = db.get_users()
    patients = [u for u in users if u['role'] == 'patient']
    family_members = [u for u in users if u['role'] == 'family_member']
    
    logger.info("\n👥 Users:")
    logger.info(f"   Total: {len(users)}")
    logger.info(f"   Patients: {len(patients)}")
    logger.info(f"   Family Members: {len(family_members)}")
    
    # Count medications
    total_medications = 0
    for user in users:
        if user['role'] == 'patient':
            meds = db.get_patient_medications(SYSTEM_CALLER, user['id'])
            total_medications += len(meds)
    
    logger.info("\n💊 Medications:")
    logger.info(f"   Total Active: {total_medications}")
    
    # Count dose logs
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM dose_logs")
        total_logs = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM dose_logs WHERE taken = 1")
        taken_logs = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM family_circles")
        total_circles = cursor.fetchone()[0]
    
    logger.info("\n📝 Dose Logs:")
    logger.info(f"   Total: {total_logs}")
    logger.info(f"   Taken: {taken_logs}")
    logger.info(f"   Missed: {total_logs - taken_logs}")
    
    if total_logs > 0:
        adherence = (taken_logs / total_logs) * 100
        logger.info(f"   Overall Adherence: {adherence:.1f}%")
    
    logger.info("\n👨‍👩‍👧‍👦 Family Circles:")
    logger.info(f"   Total: {total_circles}")
    
    logger.info("\n" + "=" * 60)

def check_environment():
    """Check environment configuration."""
    logger.info("=" * 60)
    logger.info("🔧 ENVIRONMENT CONFIGURATION")
    logger.info("=" * 60)
    
    # Check .env file exists
    if os.path.exists('.env'):
        logger.info("\n✅ .env file found")
    else:
        logger.error("\n❌ .env file NOT found")
        logger.info("Create a .env file in the project root with your credentials")
    
    # Check email configuration
    logger.info("\n📧 Email Configuration:")
    email_vars = {
        'EMAIL_ADDRESS': os.getenv('EMAIL_ADDRESS'),
        'EMAIL_PASSWORD': os.getenv('EMAIL_PASSWORD'),
        'SMTP_SERVER': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'SMTP_PORT': os.getenv('SMTP_PORT', '587')
    }
    
    for var, value in email_vars.items():
        if value:
            if 'PASSWORD' in var:
                logger.info(f"   ✅ {var}: ****** (hidden)")
            else:
                logger.info(f"   ✅ {var}: {value}")
        else:
            logger.error(f"   ❌ {var}: Not set")
    
    # Check Twilio configuration
    logger.info("\n📱 SMS Configuration (Twilio):")
    twilio_vars = {
        'TWILIO_ACCOUNT_SID': os.getenv('TWILIO_ACCOUNT_SID'),
        'TWILIO_AUTH_TOKEN': os.getenv('TWILIO_AUTH_TOKEN'),
        'TWILIO_PHONE_NUMBER': os.getenv('TWILIO_PHONE_NUMBER')
    }
    
    for var, value in twilio_vars.items():
        if value:
            if 'TOKEN' in var:
                logger.info(f"   ✅ {var}: ****** (hidden)")
            else:
                logger.info(f"   ✅ {var}: {value}")
        else:
            logger.warning(f"   ⚠️  {var}: Not set (SMS disabled)")
    
    # Database check
    logger.info("\n💾 Database:")
    db_path = "data/medications.db"
    if os.path.exists(db_path):
        size = os.path.getsize(db_path) / 1024  # KB
        logger.info(f"   ✅ Database exists: {db_path}")
        logger.info(f"   Size: {size:.2f} KB")
    else:
        logger.warning("   ⚠️  Database not found (will be created on first use)")
    
    logger.info("\n" + "=" * 60)

def quick_start_guide():
    """Display quick start guide."""
    print("\n" + "=" * 60)
    print("📖 QUICK START GUIDE")
    print("=" * 60)
    print("""
This background service handles automated medication reminders
and weekly compliance reports.

SETUP STEPS:
1. Configure your .env file with email/SMS credentials
2. Create users and medications through the web app
3. Run this service to enable automated reminders

RUNNING THE SERVICE:
• Option 1: python src/main.py (interactive menu)
• Option 2: python src/main.py --start (direct start)

CREDENTIALS NEEDED:
• Email: Gmail address and App Password
• SMS (optional): Twilio account credentials

For detailed setup instructions, see the README file.
    """)
    print("=" * 60 + "\n")

if __name__ == "__main__":
    # Load environment variables
    load_environment()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--start':
            # Direct start without menu
            start_scheduler()
        elif sys.argv[1] == '--test':
            # Test notifications
            test_notifications()
        elif sys.argv[1] == '--stats':
            # Show stats
            show_database_stats()
        elif sys.argv[1] == '--help':
            # Show help
            quick_start_guide()
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Usage: python main.py [--start|--test|--stats|--help]")
    else:
        # Show interactive menu
        quick_start_guide()
        run_menu()