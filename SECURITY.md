# Security model and review limits

MedSync is a portfolio prototype. This is an implementation review, not a penetration test, compliance assessment, or authorization to handle real patient records. Evaluate it with synthetic data.

## Trust boundaries

- Streamlit executes application code on the server. The server keeps `SUPABASE_KEY`; no browser database client is configured.
- `PatientAuthorizationMixin` is shared by SQLite and Supabase. Patient reads require self-access or a shared-circle `view` grant; writes require self-access or `manage_meds`. Medication-ID mutations resolve ownership before authorizing. Denial raises `AuthorizationError`.
- `SYSTEM_CALLER` is an object sentinel for trusted worker reads. User-provided numeric IDs cannot become that sentinel. Its patient writes are denied; the worker separately writes its own notification ledger.
- User/account operations, some circle reads/membership operations, and worker-ledger methods remain trusted internal methods. Do not expose them directly as APIs or describe all database methods as independently authorized.

## Supabase: two different protections

**Application authorization protects one user from another through the app.** The server uses `service_role`, which bypasses RLS. The custom auth system does not supply per-user Supabase JWTs, so `auth.uid()` policies do not currently express this app's identities.

**Database API restrictions protect against bypassing the app.** Service-role bypass does not justify leaving client-accessible tables unprotected. The schema proposed in this PR enables RLS on all twelve tables, removes table/sequence privileges from `PUBLIC`, `anon`, and `authenticated`, and explicitly grants the server the operations it needs. No client policies are provided.

This corrects the old brief's recommendation to leave RLS off. See [Supabase RLS documentation](https://supabase.com/docs/guides/database/postgres/row-level-security) and [PostgreSQL row-security semantics](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

The schema is **not applied automatically**, and no hosted project was queried or modified in this review. Existing deployments need review of exposed schemas, grants, inherited roles, existing policies, functions, and keys before any approved migration. Local SQL tests model the role boundary; they are not hosted Supabase verification. A future Supabase Auth migration could add user-level RLS while retaining application checks.

## Authentication controls verified in source

- Passwords use bcrypt. OTP digests use HMAC-SHA256 with a server secret and constant-time digest comparison.
- OTPs expire after five minutes; wrong guesses and lockouts are tracked. Sequential issuance is limited to three requests per ten minutes, including failed provider sends. Distributed concurrent request races remain possible; counters are not transactionally reserved.
- Session tokens are generated with `secrets.token_urlsafe(32)`, stored server-side, expire after seven days, and are revalidated on every rerun. Revocation/expiry ends a loaded session on its next interaction. They are bearer secrets and are currently stored unhashed in the database and copied into a URL query parameter.
- Normal OTP generation does not log codes. SMS success/error logs omit recipient numbers and raw provider exception details. A test code requires both `MEDSYNC_LOCAL_DEMO=1` and `MEDSYNC_DEV_SHOW_OTP=1`, no Supabase setting, and no SMS client; never enable these flags in deployment. Without a delivery/test path, no pending code is created and sign-in fails closed.
- Guest/reset UI controls and legacy passwordless profile setup require explicit `MEDSYNC_LOCAL_DEMO=1` and no Supabase configuration. The isolated demo clears notification credentials and uses a disposable SQLite file.
- The checked-in Streamlit configuration enables both CORS and XSRF protection. This is configuration evidence, not a full browser-origin penetration test.

## Remaining risks, in priority order

| Priority | Finding | Follow-up |
| --- | --- | --- |
| High | Bearer tokens in `?token=` can enter history, copied links, screenshots, or infrastructure logs. The final review adds revalidation on every rerun and restores valid tokens after page switches; it does not replace URL transport or proactively erase an idle browser's already-rendered data. | Replace URL sessions with secure cookie/session handling or supported auth integration; hash stored bearer/reset tokens. |
| High | Verification/reset links are generated, but browser handlers are absent. Phone profile completion trusts the preceding UI step; phone uniqueness is not enforced by the schema. The legacy passwordless profile path is now restricted to explicit local demos. | Consolidate identity flows and enforce verified registration state at the service boundary; finish reset/verification UI and add negative tests. |
| High | Deployment grants/policies and hosted adapter behavior are unknown. The server holds broad database access. | Review and test in an isolated Supabase project before an approved deployment migration; verify denied direct-client access. |
| Medium | Dashboard, sidebar, settings, medication cards, and shared headings now escape user text. Email templates and other rendering paths still require broader review. | Complete output-context review; no claim of a confirmed script-execution exploit or comprehensive XSS protection is made. |
| Medium | SMS/email/scheduler logs can contain recipient/contact/medication information; messages contain medication details. | Minimize/redact logs, review retention and recipient consent, and define an appropriate deployment privacy model. |
| Medium | Circle invite codes used by the main UI are not expiring or attempt-limited; the expiring invite model is separate. | Wire one invitation path with expiration, revocation, and abuse limits. |
| Medium | Dependency versions are mostly open ranges. No complete advisory scan or supply-chain review was performed. | Add a reviewed lockfile and dependency/security scanning; update deliberately. |

## Repository exposure review

A pattern-based review scanned **194 unique reachable Git blobs across 46 commits**, plus current tracked paths, at baseline `e8e59c4`. It checked for private-key blocks, recognizable GitHub/AWS/Supabase/Twilio credentials, JWT-like values, credential URLs, suspicious literal assignments, environment files, database files, and phone literals. No matching committed credential or patient-data file was identified. Visible test contacts were synthetic 555/example fixtures; vendored CSVs contain design guidance.

This is bounded evidence, not a guarantee that history contains no secret or sensitive information. Live databases, deployment logs, GitHub secret values, external backups, and unreachable Git objects were not accessed. Commit authorship metadata was preserved. No credentials were uploaded and no production records were read.

If a real secret is discovered, avoid pasting it into an issue or PR. Contact the repository owner privately, revoke/rotate it at the provider, and assess exposure before discussing any history rewrite. This review did not rotate credentials or rewrite history.
