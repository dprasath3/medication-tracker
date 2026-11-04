-- =============================================================================
-- MEDSYNC - Supabase Database Schema
-- =============================================================================
-- Run this in Supabase SQL Editor:
-- 1. Go to your Supabase Dashboard
-- 2. Click "SQL Editor" in the left sidebar
-- 3. Click "New Query"
-- 4. Paste this entire file
-- 5. Click "Run"
-- =============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    age INTEGER,
    role TEXT DEFAULT 'patient',
    phone TEXT,
    created_date TIMESTAMPTZ DEFAULT NOW(),
    phone_verified BOOLEAN DEFAULT FALSE,
    primary_auth_method TEXT DEFAULT 'phone',
    account_status TEXT DEFAULT 'active',
    last_login TIMESTAMPTZ,
    theme TEXT DEFAULT 'warm-cream'
);

-- Idempotent migration for pre-existing deployments (safe to re-run).
ALTER TABLE users ADD COLUMN IF NOT EXISTS theme TEXT DEFAULT 'warm-cream';

-- Family circles table
CREATE TABLE IF NOT EXISTS family_circles (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    invite_code TEXT UNIQUE,
    created_by BIGINT REFERENCES users(id),
    created_date TIMESTAMPTZ DEFAULT NOW()
);

-- Family members relationship table
CREATE TABLE IF NOT EXISTS family_members (
    id BIGSERIAL PRIMARY KEY,
    family_circle_id BIGINT REFERENCES family_circles(id),
    user_id BIGINT REFERENCES users(id),
    relationship TEXT,
    permissions JSONB DEFAULT '["view", "set_reminders"]',
    joined_date TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(family_circle_id, user_id)
);

-- Medications table
CREATE TABLE IF NOT EXISTS medications (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT REFERENCES users(id),
    managed_by BIGINT REFERENCES users(id),
    name TEXT NOT NULL,
    dosage TEXT NOT NULL,
    frequency TEXT NOT NULL,
    times JSONB NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    notes TEXT,
    created_date TIMESTAMPTZ DEFAULT NOW()
);

-- Dose logs table
CREATE TABLE IF NOT EXISTS dose_logs (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT REFERENCES users(id),
    medication_name TEXT,
    scheduled_time TEXT,
    taken BOOLEAN,
    actual_time TEXT,
    date DATE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    logged_by BIGINT REFERENCES users(id)
);

-- Reminders table
CREATE TABLE IF NOT EXISTS reminders (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT REFERENCES users(id),
    created_by BIGINT REFERENCES users(id),
    medication_name TEXT,
    reminder_time TEXT,
    message TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_date TIMESTAMPTZ DEFAULT NOW()
);

-- User credentials (password-based auth)
CREATE TABLE IF NOT EXISTS user_credentials (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    email_verification_token TEXT,
    email_verification_expiry TIMESTAMPTZ,
    password_reset_token TEXT,
    password_reset_expiry TIMESTAMPTZ,
    created_date TIMESTAMPTZ DEFAULT NOW(),
    updated_date TIMESTAMPTZ DEFAULT NOW()
);

-- OTP verifications (phone-based auth)
CREATE TABLE IF NOT EXISTS otp_verifications (
    id BIGSERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    user_id BIGINT REFERENCES users(id),
    purpose TEXT DEFAULT 'login'
);

-- User sessions (bearer tokens; transport/storage limitations in SECURITY.md)
CREATE TABLE IF NOT EXISTS user_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token TEXT UNIQUE NOT NULL,
    device_fingerprint TEXT,
    device_name TEXT,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_activity TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

-- Enhanced invite codes with expiration
CREATE TABLE IF NOT EXISTS invite_codes (
    id BIGSERIAL PRIMARY KEY,
    family_circle_id BIGINT NOT NULL REFERENCES family_circles(id),
    code TEXT UNIQUE NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    max_uses INTEGER DEFAULT 1,
    current_uses INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    deep_link_token TEXT UNIQUE
);

-- Login attempts tracking (security/rate limiting)
CREATE TABLE IF NOT EXISTS login_attempts (
    id BIGSERIAL PRIMARY KEY,
    identifier TEXT NOT NULL,
    attempt_type TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    lockout_until TIMESTAMPTZ
);

-- Reminder-engine ledger: one row per (dose, stage) sent or superseded.
-- The UNIQUE constraint deduplicates ledger rows, not external SMS sends.
-- See REMINDER_ENGINE.md for the send-before-record crash window.
CREATE TABLE IF NOT EXISTS notification_log (
    id BIGSERIAL PRIMARY KEY,
    patient_id BIGINT REFERENCES users(id),
    medication_name TEXT,
    scheduled_time TEXT,
    date DATE,
    stage TEXT,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(patient_id, medication_name, scheduled_time, date, stage)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_medications_patient ON medications(patient_id);
CREATE INDEX IF NOT EXISTS idx_dose_logs_patient_date ON dose_logs(patient_id, date);
CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);
CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_verifications(phone);
CREATE INDEX IF NOT EXISTS idx_notification_log_lookup ON notification_log(patient_id, date);

-- =============================================================================
-- Server-only database API boundary
-- =============================================================================
-- Custom authentication has no Supabase user JWT. Application authorization in
-- src/utils/authz.py therefore remains mandatory for the service_role client.
-- RLS does not constrain that BYPASSRLS role, but DOES protect against direct
-- access by API client roles. No client policies are intentionally provided.
-- Explicit grants avoid depending on a project's default privilege settings.
--
-- Review before applying to an existing project: this revokes direct client
-- access to these app tables. It does not remove pre-existing RLS policies;
-- review those separately. This file is NOT run automatically by the app.
-- No changes have been applied to any hosted database as part of the audit.
-- https://supabase.com/docs/guides/database/postgres/row-level-security
DO $$
DECLARE
    app_table text;
    id_sequence text;
BEGIN
    FOREACH app_table IN ARRAY ARRAY[
        'users', 'family_circles', 'family_members', 'medications', 'dose_logs',
        'reminders', 'user_credentials', 'otp_verifications', 'user_sessions',
        'invite_codes', 'login_attempts', 'notification_log'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', app_table);
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC, anon, authenticated', app_table);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.%I TO service_role', app_table);
        -- Existing projects may have renamed serial/identity sequences. Resolve
        -- ownership from PostgreSQL instead of guessing the default name.
        id_sequence := pg_get_serial_sequence(format('public.%I', app_table), 'id');
        IF id_sequence IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated', id_sequence);
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', id_sequence);
        END IF;
    END LOOP;
END $$;
