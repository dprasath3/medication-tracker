# Repository audit and change record

**Initial review:** November 1, 2026. **Final review:** November 4, 2026. **Baseline:** `e8e59c4` on `main`.
**Goal:** make the existing MedSync project understandable, reproducible, and technically defensible for recruiting while preserving history and core functionality.

## Before → after

| Area | Before | This branch |
| --- | --- | --- |
| First impression | Generic repository title, run instructions before feature/engineering context | MedSync overview, verified feature/stack summary, source-linked engineering decisions, architecture, demo and testing sections |
| Visual evidence | No app screenshots | Three real Chromium captures from disposable synthetic SQLite, plus reproducible demo/capture scripts |
| Repository references | CI badge points at the former owner | Badge and clone instructions use `dprasath3/medication-tracker`; historical commit authors/messages remain intact |
| Testing | 67 passing tests, successful existing CI | 99 passing Python tests after final review, expanded browser smoke check, and a PostgreSQL access-boundary CI job |
| Security explanation | Conflates service-role RLS bypass with no need for a client boundary | Separates application authorization from direct database API protection; proposes explicit schema restrictions and documents residual risks |
| Reliability explanation | Claims restarting mid-send and multiple workers never duplicate SMS | Explains completed-ledger deduplication, send-before-record failure window, one-worker requirement, and partial-recipient behavior |
| Historical documents | “Zero tests,” deferred engine, stale routes and unchecked plans read as current | Adds reconciliation map and labels design intent; preserves original technical rationale |

## Scope reviewed

- All tracked application modules in `src/`, database schema, runtime configuration, dependency manifests, tests, workflow, primary documentation, and design specifications.
- Baseline GitHub repository metadata, default branch, workflow path, and recent runs. Repository is public and owned by `dprasath3`; description was “Python automation project for elderly medication management with family support circle”; topics were empty.
- Reachable Git history: 46 commits and 194 unique blobs scanned for recognized secret patterns and sensitive file paths. Vendored design CSV/tooling was inventoried and included in the scan, not treated as application functionality or independently re-audited as a third-party product.
- No production database, deployed app, patient records, GitHub secret values, or provider accounts were accessed.

## Strengths already present

Centralized patient authorization shared by two adapters; explicit read-only system identity; targeted security tests; separate web/worker processes; injectable reminder logic; persistent ledger and failure isolation; family permission management; medication lifecycle operations; real relational persistence; working themed Streamlit UI and Plotly history.

There is no trained model, inference pipeline, model evaluation, or demonstrated ML feature. Describe the project as backend/security engineering with an optional future data-science extension.

## Every modification, grouped by purpose

The table records the initial portfolio changes. [FINAL_REVIEW.md](FINAL_REVIEW.md) records the follow-up review, every additional fix, the complete 44-file review inventory, and merge/deployment conditions.

| Files | Change |
| --- | --- |
| `README.md` | Recruiter-first rewrite; corrected badge/clone links; actual features/stack, architecture diagram, safe quickstart, evidence and limitations; preserves design and authorization rationale through linked docs |
| `docs/ARCHITECTURE.md`, `SECURITY.md`, `docs/AUDIT.md`, `docs/TESTING.md` | Source map, data relationships/routes, explicit trust boundaries, audit findings, before/after, exact verification and proposed settings |
| `HARDENING_SPRINT.md` | Historical label and current-status table; original brief retained |
| `REMINDER_ENGINE.md` | Implemented status; corrected restart/idempotency/recipient semantics; deployment recipe and Mermaid diagram; timezone, midnight, snooze and metric caveats |
| `CLAUDE.md`, `design-system/MASTER.md`, `design-system/pages/README.md`, `design-system/pages/today.md` | Correct implemented routes and theme behavior context; distinguish design targets from verified behavior; allow explicitly authorized isolated demos/maintenance |
| `scripts/demo.py`, `scripts/capture_demo.py`, `docs/DEMO.md`, `docs/screenshots/*.png` | New disposable SQLite demo, generated temporary passwords, no phone numbers/provider credentials/worker, real browser captures and smoke steps |
| `src/services/auth.py` | Count issuance attempts rather than only wrong verification attempts; no raw OTP/phone logging; blank `APP_BASE_URL` falls back to localhost |
| `src/utils/database.py`, `src/utils/database_supabase.py` | Add recent OTP issuance-event count on both adapters; correct ledger comments |
| `src/pages/auth.py` | Route the email button to its form; restrict guest/reset and legacy passwordless setup to explicit local demos; make email guest entry use the existing guarded helper |
| `src/pages/dashboard.py` | Preserve selected patient through `st.switch_page` using session state |
| `src/pages/add_med.py`, `src/pages/circle.py` | Invalidate read caches after successful create/join/add; clarify that reminders require a worker |
| `src/pages/today.py`, `src/ui/primitives.py` | Fix raw HTML notes rendering; escape medication text and shared header/empty-state/pill text |
| `src/pages/patient.py`, `src/ui/theme.py` | Remove unsupported structural emoji in schedule text and unverified AAA claim from theme copy |
| `src/main.py`, `src/services/scheduler.py` | Load `.env` before scheduler import; explicitly use configured timezone for weekly cron |
| `src/services/reminder_engine.py` | Correct comments on side effects, deduplication, and crash limitations; scheduling algorithm unchanged |
| `supabase_schema.sql` | Enable RLS for all twelve app tables; revoke direct client/PUBLIC grants; explicitly allow service-role table/sequence access; correct misleading RLS/ledger comments. Proposed code only—no hosted migration run |
| `.github/workflows/ci.yml`, `tests/sql/server_access.sql` | Read-only workflow token, timeouts, ephemeral PostgreSQL 16 job; assert repeatable schema and allowed/denied role operations |
| `tests/test_otp.py`, `test_scheduler.py`, `test_session_persistence.py`, `test_auth_ui.py`, `test_demo.py`, `test_rendering.py`, `tests/conftest.py` | 15 added cases; isolate credentials and block external socket calls in tests |
| `requirements.txt`, `.env.example`, `.gitignore` | Correct Streamlit minimum; document server key/local-demo flags; local URL default; ignore env variants, Streamlit secrets, SQLite sidecars |

## Remaining findings and targeted follow-up

| Priority | Finding | Recommended next work |
| --- | --- | --- |
| P1 | URL bearer sessions, incomplete reset/verification UI, trusted phone-registration state, missing unique phone constraint | Consolidate auth flow, use secure session transport, enforce verified state and identity uniqueness; add browser expiry/revocation/reset tests |
| P1 | No hosted database/API integration verification | Use a disposable Supabase project to test both authorized adapter operations and denied direct-client access; review schema migration before any deployment |
| P1 | Non-atomic SMS send/ledger writes; one successful caregiver marks the whole stage complete | Introduce an outbox/claim protocol, provider-status reconciliation, per-recipient outcomes, and failure-injection tests |
| P2 | Name/time-based dose identity, duplicate dose logs, host-local/UI date vs worker timezone, current-day catch-up only | Add medication/dose IDs and unique scheduled-dose records, define timestamp semantics, test midnight/DST and reactivation/schedule edits |
| P2 | User-controlled text remains interpolated into some HTML views; sensitive fields can reach notification/worker logs | Finish escaping all render boundaries and redact logging; define retention and review recipient sharing |
| P2 | Main invite flow uses non-expiring circle code; dynamic circle-create form fields can require an extra rerun; description/relationship fields are collected but not all persisted | Unify invitation implementation, audit forms with browser tests, either persist fields or clarify their UI |
| P2 | Session revocation now takes effect on the next rerun. Caller-scoped caches can still retain reads until TTL expiry after permission changes in another process | Test multi-session/multi-process permission invalidation; replace URL bearer transport |
| P2 | Historical adherence excludes unlogged doses and the “7-day” query boundary can include an extra date; duplicate/name-colliding logs distort values | Define the metric and denominator, reconcile schedule instances, test exact date windows |
| P2 | SQLite foreign-key enforcement is not enabled on each connection; permissive generic update methods rely on trusted kwargs | Add connection-level integrity checks and allowed-field validation with migration tests |
| P2 | Dependencies are open ranges; optional Google Sheets/PDF packages are not evidence of working product integrations | Lock a reviewed environment, scan advisories, remove unused packages only after confirming consumers |
| P3 | Accessibility claims/design details exceed validation; Plotly colors are tied to one theme | Contrast/keyboard/screen-reader/reduced-motion review across themes and mobile; follow theme tokens in charts |
| P3 | Legacy CLI statistics directly open SQLite and are not Supabase-compatible | Route statistics through backend-neutral methods, or clearly scope the CLI command to SQLite |
| P3 | Per-minute full patient/medication scans and broad `get_users()` reads | Measure first, then introduce indexed due-work queries and pagination; no performance claims yet |

### Next three highest-impact milestones

1. **Authentication and hosted security:** secure sessions, finish identity/recovery flows, and validate a disposable Supabase environment. Acceptance: browser lifecycle tests and denied direct-client access with the production-style adapter.
2. **Reliable dose/delivery model:** stable dose IDs, transactional claiming/outbox, per-recipient status, and consistent timezones. Acceptance: crash, duplicate-worker, partial-failure, midnight and DST tests.
3. **Reproducible evaluation:** dependency locking, browser/backend contract coverage, accessibility checks; then an optional offline ML experiment on synthetic/licensed data with temporal splits, a simple baseline, calibration and leakage analysis. No clinical decision-making or predictive claims without evidence.

## GitHub presentation settings — completed by owner

The owner confirmed on November 4 that the exact description, all twelve topics, and the MedSync profile pin were completed manually. These actions were not repeated; no browser authentication was attempted during the final review.

**Description**

> MedSync: Python/Streamlit medication tracker with family permissions, SQLite/Supabase persistence, OTP authentication, tested reminder scheduling, and a synthetic demo.

**Topics**

`python`, `streamlit`, `postgresql`, `sqlite`, `supabase`, `authentication`, `authorization`, `application-security`, `apscheduler`, `pytest`, `github-actions`, `medication-tracker`

No ML/compliance/deployment claim should be inferred from these topics. Existing profile pins were not removed by the agent.

## Preservation and actions not taken

No merge, force push, history rewrite, visibility change, deployment change, credential upload, real notification, or production-data access was performed by the agent. Settings/pinning were completed by the owner as recorded above. The original technical history and core workflows are retained; demo controls remain available only through explicit local opt-in. Testing and screenshots demonstrate a local synthetic application, not a deployed medical product.
