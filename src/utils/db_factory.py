"""Database factory - automatically selects SQLite or Supabase based on environment."""
import os


def local_demo_enabled() -> bool:
    """Explicit demo opt-in, disabled if either cloud setting is present."""
    return (
        os.getenv("MEDSYNC_LOCAL_DEMO") == "1"
        and not os.getenv("SUPABASE_URL")
        and not os.getenv("SUPABASE_KEY")
    )


def get_database():
    """Get the appropriate database instance based on environment.

    Uses Supabase if SUPABASE_URL and SUPABASE_KEY are set,
    otherwise falls back to SQLite for local development.
    """
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_KEY')

    if supabase_url and supabase_key:
        # Use Supabase in production
        from utils.database_supabase import MedicationDB
        print("Using Supabase database")
        return MedicationDB()
    else:
        # Use SQLite for local development
        from utils.database import MedicationDB
        print("Using SQLite database (local)")
        return MedicationDB()
