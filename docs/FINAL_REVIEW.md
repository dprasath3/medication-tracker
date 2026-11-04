# PR #4 final engineering and security review

Review date: **November 4, 2026**. Starting PR head: `84860b944152d54d2fc56be7bc81f171b78cc4a9`; base: `e8e59c48208e42c7b6de9b0bffa45d75ed5ddfe1`.

## Recommendation

The portfolio changes are ready for owner review after the targeted fixes below. Merge only after the new commit's CI is green and the owner confirms that merging `main` will not start an unwanted external deployment. GitHub's conflict-free status alone does not establish deployment safety or production readiness.

The project now presents its actual software/security engineering clearly: shared authorization policy, two persistence adapters, separate reminder orchestration, tested failure behavior, and a reproducible synthetic demo. No ML implementation, medical outcome, security certification, or live deployment is asserted. Existing production-readiness limitations in [SECURITY.md](../SECURITY.md) remain explicit.

## Findings and fixes

| Finding | Origin and impact | Targeted correction / evidence |
| --- | --- | --- |
| Loaded profiles bypassed session validation | Pre-existing gap left open by the initial PR. A revoked/expired session could continue operating through an existing connection. | Revalidate before authenticated routing on every rerun; clear identity, routing state, and cached reads when invalid. Unit cases cover revoked, expired, and missing tokens; browser checks revoke a live synthetic viewer session and confirm return to sign-in. Idle already-rendered data is not proactively erased. |
| Development OTP disclosure was not blocked by cloud settings | Pre-existing escape hatch left open by the initial demo hardening. With SMS absent, one debug flag could return a code for any requested phone. | Require both local-demo flags and no Supabase configuration. Otherwise report unavailable phone sign-in without creating a code. Tests cover either cloud variable and normal opt-in local verification. |
| New Supabase issuance count treated a missing total as zero | Defensive review of the PR's new adapter method; hosted occurrence was not observed. Missing count evidence could allow more requests. | Request an exact HEAD count and fail closed when absent. Adapter contract tests cover zero, three, 1,500, and missing totals without a live client. Distributed issuance races remain open. |
| SQL restrictions guessed sequence names | Introduced by the PR's hardening block. Reapplying it after a legitimate sequence rename failed. | Resolve the owned serial/identity sequence with `pg_get_serial_sequence`. The old schema failed on the renamed-sequence fixture; the new SQL passes. Tests also assert table/column/sequence denial and server privileges, including an existing permissive policy. |
| SMS errors could log recipient or OTP-bearing provider text | Pre-existing provider logging, beyond the initial auth-layer logging fix. | Replace raw recipient/error interpolation with a generic event and exception class; regression test supplies synthetic sensitive values and verifies their absence from logs. Email/worker logging still needs broader privacy review. |
| User text remained interpolated into dashboard/profile HTML | Pre-existing gap outside the initial card/header escaping. HTML injection was visible in generated markup; script execution was not established. | Escape dashboard names, circle names, alerts, sidebar identity, and settings profile fields. Keep trusted structural HTML intact. |
| Back links, medication submission, and direct write-form access | Pre-existing UI gaps exposed during review of the PR's restored navigation. Successful medication creation left an empty selection screen; direct read-only access rendered a write form before submission was rejected. | Consume primary auth query routes once; retain legacy demo form routing; return to Dashboard after creating a medication; deny the write form up front. Browser checks cover submission, refresh, Back, read-only access, and forged patient IDs. Demo guest/profile entry now creates a normal expiring session to preserve functionality under revalidation. |
| Cross-origin protection disabled in checked-in Streamlit configuration | Pre-existing `enableCORS=false`; the installed Streamlit runtime explicitly warned that XSRF did not restrict cross-origin WebSocket connections. | Restore `enableCORS=true` and retain XSRF protection. This is a source/configuration correction, not a full origin-security penetration test. |
| Stale review/settings and source documentation | The audit still described settings as pending; auth/demo/session details changed during review. | Record the owner's completed settings, reconcile the README/security/architecture/demo/testing docs, and replace stale “future Commit 4 / behavior preserved verbatim” page docstrings. |

The first new Python checks reproduced **10 failures and 1 pass** against the starting head. These were newly added checks, not a claim that ten vulnerabilities were introduced by the PR. Subsequent fixes and coverage bring the suite to **99 tests**, adding 17 review cases to the initial PR's 82.

## Verification

- Fresh Python 3.11.17 environment: starting suite **82 passed in 5.23s**; final suite **99 passed in 4.11s**; Ruff **passed**. Durations are single observations, not performance claims.
- Expanded Chromium/Streamlit walkthrough **passed** with synthetic SQLite: email sign-in, logging, snooze, caregiver View/Add/submit, refresh, view-only controls, denied write form, unrelated-patient rejection, loaded-session revocation, auth Back, guest refresh, and 375px rendering without an app exception.
- Strengthened SQL checks **passed locally with PGlite** after expanding psql includes. PostgreSQL 16 is also exercised by the PR's GitHub Actions job; check the current commit's result before merging. Local PGlite is not represented as hosted Supabase verification.
- The three original 1440×1280 screenshots were visually reviewed; the same application was recaptured locally into scratch for comparison. The committed November 1 images remain unchanged. No DOM manipulation or fabricated screenshot was used.
- A bounded rescan covered **240 unique reachable Git blobs across 50 commits** at the starting head plus current tracked/new files. No matching private-key, GitHub/AWS/Supabase/JWT credential, credential-URL, or sensitive database/environment-file candidate was found. Synthetic test tokens/numbers and screenshot fixtures were reviewed. This does not prove that every possible secret or private fact is absent.
- Relative documentation links and patch whitespace were checked; final results are recorded in [TESTING.md](TESTING.md). No real provider, production record, GitHub secret value, or hosted database was accessed.

The local commands are documented in [TESTING.md](TESTING.md); detailed initial scope and follow-up work remain in [AUDIT.md](AUDIT.md).

## Deployment assessment

| Surface | Verified evidence | Conclusion / limitation |
| --- | --- | --- |
| GitHub Actions | The sole tracked workflow on `main` and the PR is `.github/workflows/ci.yml`. It triggers on push/PR, installs dependencies, runs Ruff/pytest, and runs SQL in an ephemeral PostgreSQL 16 service. Workflow token permission is `contents: read`. Recent runs and current-head check runs show GitHub Actions checks only. | Merging triggers CI. There is no checked-in deploy command, deployment environment, hosting credential reference, or hosted SQL invocation. Dependencies/actions execute code, so this is not a complete supply-chain guarantee. |
| SQL/application startup | `supabase_schema.sql` is a manual script. The Supabase adapter's initialization creates a client; `init_database()` is a no-op. CI applies SQL only to its disposable service. | A merge alone does not run the schema through checked-in application/workflow code. No hosted schema was applied. |
| Railway / another web or worker host | `Procfile` defines a web process and a worker. Documentation gives a Railway recipe. No tracked Railway/Vercel/Netlify/Fly deployment configuration or deploy workflow was found. | A Procfile is evidence of intended process commands, not an active deployment. Git-connected hosting can deploy without a repository workflow. Actual linked services, source branches, PR preview triggers, and auto-deploy toggles could not be inspected. |
| Supabase branching/integrations | Repository schema and adapter source reviewed; no hosted control plane access. | Unknown whether an externally configured integration watches this repository. Plain SQL at the root is not itself proof of an automatic migration trigger. |
| GitHub hooks/apps and deployment metadata | Connector provides source, PR, Actions/check/status reads but does not expose the necessary settings/hook/deployment administration surfaces. No browser sign-in attempted, per owner instruction. | Absence of an external status check is not proof that no integration exists. The owner must check connected hosting before a merge intended to avoid deployment. |

**Owner action before merge:** in any connected hosting service, inspect the repository source branch and automatic deployment/PR-preview settings. Confirm that a `main` merge cannot cause an unwanted web/worker deployment or hosted database operation. If an automatic trigger exists, keep this PR unmerged until an appropriate deployment decision is made; this review did not change those settings. No further credentials are needed for the local portfolio review.

## Merge conditions and remaining work

1. Review the functional/security diff and the latest green GitHub checks on the PR's current head.
2. Resolve the external deployment uncertainty above. This is the outstanding operational condition; it is not an observed broken test or confirmed deployment.
3. Give explicit merge approval. No merge, history rewrite, visibility change, or deployment was performed by the agent.

Before real patient use, the high-priority follow-ups are still secure session transport/token storage, complete identity/recovery verification, isolated hosted Supabase integration checks, and atomic/per-recipient reminder delivery. Dependency locking/advisory review, permission-cache invalidation across processes, reliable dose IDs, timezone correctness, and accessibility evaluation remain documented. Those larger projects are not represented as finished by this portfolio PR.

## Original 44 changed files reviewed

The diff and relevant surrounding implementations/callers were reviewed, with rendered inspection for PNGs. This inventory identifies review scope, not a blanket security guarantee.

| Files | Review focus |
| --- | --- |
| `.env.example`, `.gitignore`, `requirements.txt` | Empty credential examples, local demo flags, secret/SQLite exclusions, minimum Streamlit API support and open dependency ranges |
| `.github/workflows/ci.yml` | Triggers, permissions, test isolation, disposable SQL service, absence of deploy steps |
| `CLAUDE.md`, `HARDENING_SPRINT.md`, `REMINDER_ENGINE.md` | Scope/history reconciliation, obsolete RLS advice, source-backed reminder semantics and delivery gaps |
| `README.md`, `SECURITY.md` | Setup, features, source references, evidence, precise authorization/database boundaries, honest limitations |
| `design-system/MASTER.md`, `design-system/pages/README.md`, `design-system/pages/today.md` | Implemented routes vs design targets; removal of unverified accessibility claims |
| `docs/ARCHITECTURE.md`, `docs/AUDIT.md`, `docs/DEMO.md`, `docs/TESTING.md` | Source/data map, complete change record, reproducibility, settings status, exact testing scope |
| `docs/screenshots/caregiver-dashboard.png`, `docs/screenshots/patient-details.png`, `docs/screenshots/today.png` | Real rendered app, synthetic identities/medications/history, no visible credentials or real patient records |
| `scripts/demo.py`, `scripts/capture_demo.py` | Temporary database lifecycle, credential clearing, loopback binding, worker avoidance, actual browser actions and cleanup |
| `src/main.py`, `src/services/scheduler.py`, `src/services/reminder_engine.py` | Environment-before-import ordering, cron timezone, unchanged reconciliation algorithm, honest ledger/crash comments |
| `src/services/auth.py`, `src/utils/database.py`, `src/utils/database_supabase.py` | OTP issuance counters, logging, URL fallback, parameterized access, shared authorization, exact count handling |
| `src/pages/auth.py`, `src/pages/add_med.py`, `src/pages/circle.py`, `src/pages/dashboard.py`, `src/pages/patient.py`, `src/pages/today.py` | Auth and navigation state, demo isolation, patient IDs, read/write controls, mutation caches, HTML boundaries |
| `src/ui/primitives.py`, `src/ui/theme.py` | Text escaping, unchanged rendering structure, removal of unsupported conformance claim |
| `supabase_schema.sql`, `tests/sql/server_access.sql` | All twelve tables, RLS, direct-client/server grants, sequences, reruns, failure tests, deployment isolation |
| `tests/conftest.py`, `tests/test_auth_ui.py`, `tests/test_demo.py`, `tests/test_otp.py`, `tests/test_rendering.py`, `tests/test_scheduler.py`, `tests/test_session_persistence.py` | Test assertions, synthetic fixtures, network prevention, configuration leakage, missing coverage |

Additional files inspected and changed during the final review: `.streamlit/config.toml`, `src/utils/session.py`, `src/utils/db_factory.py`, `src/services/notifications.py`, `src/web_app.py`, `src/pages/settings.py`, plus `tests/test_final_review.py` and this review record. Supporting unchanged authorization, family-model, notification, and routing code was inspected to validate claims and callers.
