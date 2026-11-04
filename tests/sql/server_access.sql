-- Disposable PostgreSQL database only: psql -v ON_ERROR_STOP=1 -f tests/sql/server_access.sql
-- This tests PostgreSQL grants/RLS, not the hosted Supabase/PostgREST adapter.
BEGIN;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
-- Reproduce permissive older project defaults before applying the schema.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
\ir ../../supabase_schema.sql
-- Model an existing project's renamed sequence and permissive old policy.
ALTER SEQUENCE public.users_id_seq RENAME TO imported_users_sequence;
CREATE POLICY old_client_read ON public.users FOR SELECT TO anon USING (true);
GRANT SELECT (name) ON public.users TO anon;
\ir ../../supabase_schema.sql

SET LOCAL ROLE service_role;
INSERT INTO public.users(name, email) VALUES ('Synthetic SQL test', 'sql@example.test');
DO $$ BEGIN
    IF (SELECT count(*) FROM public.users) <> 1 THEN
        RAISE EXCEPTION 'Service role cannot read its test row';
    END IF;
END $$;
UPDATE public.users SET age = 72 WHERE email = 'sql@example.test';
DELETE FROM public.users WHERE email = 'sql@example.test';
RESET ROLE;

DO $$
DECLARE
    client_role text;
    app_table text;
    operation text;
    id_sequence text;
    total integer;
BEGIN
    SELECT count(*) INTO total FROM pg_tables
    WHERE schemaname = 'public' AND rowsecurity;
    IF total <> 12 THEN RAISE EXCEPTION 'Expected RLS on all 12 app tables'; END IF;
    FOREACH client_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        FOR app_table IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
            FOREACH operation IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE'] LOOP
                IF has_table_privilege(client_role, 'public.' || app_table, operation) THEN
                    RAISE EXCEPTION 'Unexpected % privilege for % on %', operation, client_role, app_table;
                END IF;
            END LOOP;
            IF has_any_column_privilege(client_role, 'public.' || app_table, 'SELECT') THEN
                RAISE EXCEPTION 'Unexpected column read for % on %', client_role, app_table;
            END IF;
            id_sequence := pg_get_serial_sequence('public.' || app_table, 'id');
            FOREACH operation IN ARRAY ARRAY['USAGE', 'SELECT', 'UPDATE'] LOOP
                IF has_sequence_privilege(client_role, id_sequence, operation) THEN
                    RAISE EXCEPTION 'Unexpected % for % on sequence %', operation, client_role, id_sequence;
                END IF;
            END LOOP;
        END LOOP;
    END LOOP;
    FOR app_table IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        FOREACH operation IN ARRAY ARRAY['SELECT', 'INSERT', 'UPDATE', 'DELETE'] LOOP
            IF NOT has_table_privilege('service_role', 'public.' || app_table, operation) THEN
                RAISE EXCEPTION 'Missing server % on %', operation, app_table;
            END IF;
        END LOOP;
    END LOOP;
END $$;

SET LOCAL ROLE anon;
DO $$ BEGIN
    BEGIN
        PERFORM * FROM public.users;
        RAISE EXCEPTION 'Anon read unexpectedly allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        INSERT INTO public.users(name) VALUES ('Must not be inserted');
        RAISE EXCEPTION 'Anon insert unexpectedly allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
RESET ROLE;
SET LOCAL ROLE authenticated;
DO $$ BEGIN
    BEGIN
        PERFORM * FROM public.user_credentials;
        RAISE EXCEPTION 'Authenticated credential read unexpectedly allowed';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
END $$;
RESET ROLE;
ROLLBACK;
